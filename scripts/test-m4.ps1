# M4 integration test:
# 1. Recreates a scratch PostgreSQL database (`ai_shopping_m4_test`), applies
#    migrations V1 + V2 + V3, and loads Vero + Stokomak + Zito fixtures and
#    deterministic product matches via `scripts/test-m2.ps1 -KeepDb`.
# 2. Packages and boots the Spring Boot REST API container connected to
#    `ai_shopping_m4_test`.
# 3. Queries cross-retailer canonical products and Stage-2 pending_review items
#    to construct a real multi-item shopping basket:
#    - Item 1: Vero+Zito 400g product (`800 g` requested -> verifies deterministic 2-pack scaling)
#    - Item 2: Vero+Stokomak 60g product #1 (`2 pack` requested)
#    - Item 3: Vero+Stokomak 60g product #2 (`1 pack` requested)
# 4. Verifies `POST /api/v1/baskets/lists`, `GET /api/v1/baskets/lists/{id}`,
#    `POST /api/v1/baskets/lists/{id}/optimize`, and `POST /api/v1/baskets/optimize`
#    (including repeatable totals across two identical calls, coverage-first ranking,
#    explicit missing-item reporting, multi-store split savings, and `allowSubstitutes=true`
#    on a Stage-2 `pending_review` product).
param(
    [string]$Database = 'ai_shopping_m4_test',
    [int]$ApiPort = 18084,
    [switch]$KeepDb
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
$DbUser = $POSTGRES_USER
$DbPass = $POSTGRES_PASSWORD
$DbPort = if ($POSTGRES_PORT) { $POSTGRES_PORT } else { '5432' }

$apiContainer = 'aishopping-m4-backend'

function Cleanup-Containers() {
    docker rm -f $apiContainer 2>$null | Out-Null
}

Cleanup-Containers

try {
    # 1. Populate $Database via M2 pipeline (applies V1 + V2 + V3 migrations)
    Write-Output "=== Step 1: Populate $Database via M2 pipeline (V1+V2+V3) ==="
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-m2.ps1 -Database $Database -KeepDb
    if ($LASTEXITCODE -ne 0) { throw 'test-m2 setup failed' }

    # Verify V3 tables exist
    $v3Check = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -v ON_ERROR_STOP=1 `
        -c "SELECT CASE WHEN to_regclass('public.shopping_lists') IS NOT NULL AND to_regclass('public.shopping_list_items') IS NOT NULL THEN 1 ELSE 0 END;"
    if ($v3Check -ne '1') { throw 'V3 shopping_lists tables missing' }
    Write-Output 'PASS v3_schema_tables_present'

    # 2. Build & test Spring Boot backend JAR
    Write-Output '=== Step 2: Build and test Spring Boot backend ==='
    docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test package
    if ($LASTEXITCODE -ne 0) { throw 'maven test package failed' }

    # 3. Start Spring Boot backend container connected to $Database
    Write-Output "=== Step 3: Start Spring Boot REST API container on port $ApiPort ==="
    docker run -d --name $apiContainer --add-host=host.docker.internal:host-gateway `
        -p "${ApiPort}:8080" `
        -e "SPRING_DATASOURCE_URL=jdbc:postgresql://host.docker.internal:${DbPort}/${Database}" `
        -e "SPRING_DATASOURCE_USERNAME=${DbUser}" `
        -e "SPRING_DATASOURCE_PASSWORD=${DbPass}" `
        -e "AISHOPPING_OPENSEARCH_URL=http://127.0.0.1:1" `
        -v "${PWD}/backend:/w" -w /w maven:3.9.9-eclipse-temurin-21 `
        java -jar target/ai-shopping-backend-0.3.0-SNAPSHOT.jar | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start backend container' }

    $apiBase = "http://localhost:$ApiPort/api/v1"
    $apiReady = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $health = Invoke-RestMethod -Uri "$apiBase/health" -TimeoutSec 2
            if ($health.status -eq 'UP') { $apiReady = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $apiReady) {
        docker logs $apiContainer
        throw 'Spring Boot API did not become healthy'
    }

    # 4. Lookup real canonical product IDs from /products/compare
    Write-Output '=== Step 4: Lookup real catalog IDs for basket test ==='
    $comparisons = Invoke-RestMethod -Uri "$apiBase/products/compare?minRetailers=2&size=20"
    if ($comparisons.total -lt 3) { throw "Expected >=3 cross-retailer canonical products, got $($comparisons.total)" }

    # Select Vero+Zito 400g product (Kadaif) and the two Vero+Stokomak 60g products (Maggi & Podravka soups)
    $veroZitoItem = $comparisons.items | Where-Object {
        $_.normalizedSize -match '400g'
    } | Select-Object -First 1

    $veroStokoItems = @($comparisons.items | Where-Object {
        $_.normalizedSize -match '60g'
    })

    if (-not $veroZitoItem -or $veroStokoItems.Count -lt 2) {
        throw "Expected 400g Vero+Zito product and two 60g Vero+Stokomak products in comparisons, got sizes: $(($comparisons.items | ForEach-Object { $_.normalizedSize }) -join ',')"
    }

    # 5. Create a persisted shopping list via POST /api/v1/baskets/lists
    Write-Output '=== Step 5: Create persisted shopping list and verify GET /lists/{id} ==='
    $createPayload = @{
        name = 'M4 Integration Basket'
        cityFilter = $null
        items = @(
            @{
                canonicalProductId = $veroZitoItem.canonicalProductId
                quantity = 800
                unit = 'g'
                itemLabel = 'Kadaif 800g (2x400g)'
            },
            @{
                canonicalProductId = $veroStokoItems[0].canonicalProductId
                quantity = 2
                unit = 'pack'
                itemLabel = 'Soup 1 (2 packs)'
            },
            @{
                canonicalProductId = $veroStokoItems[1].canonicalProductId
                quantity = 1
                unit = 'pack'
                itemLabel = 'Soup 2 (1 pack)'
            }
        )
    } | ConvertTo-Json -Depth 6 -Compress

    $createdList = Invoke-RestMethod -Method Post -Uri "$apiBase/baskets/lists" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($createPayload))

    if (-not $createdList.id -or $createdList.items.Count -ne 3) {
        throw "Failed to create shopping list with 3 items: $($createdList | ConvertTo-Json -Compress)"
    }
    $listId = $createdList.id
    Write-Output "PASS shopping_list_created (id=$listId, items=$($createdList.items.Count))"

    $fetchedList = Invoke-RestMethod -Uri "$apiBase/baskets/lists/$listId"
    if ($fetchedList.id -ne $listId -or $fetchedList.items.Count -ne 3) {
        throw 'GET /baskets/lists/{id} mismatch'
    }
    Write-Output 'PASS shopping_list_get_verified'

    # 6. Run optimization on the saved shopping list twice to verify repeatable totals
    Write-Output '=== Step 6: Optimize persisted shopping list and verify repeatable totals ==='
    $optParams = @{
        maxStores = 2
        minSplitSavingsMkd = 5.00
        allowSubstitutes = $false
        inStockOnly = $true
    } | ConvertTo-Json -Compress

    $opt1 = Invoke-RestMethod -Method Post -Uri "$apiBase/baskets/lists/$listId/optimize" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($optParams))

    $opt2 = Invoke-RestMethod -Method Post -Uri "$apiBase/baskets/lists/$listId/optimize" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($optParams))

    if ($opt1.bestSingleStore.totalMkd -ne $opt2.bestSingleStore.totalMkd -or `
        $opt1.bestMultiStorePlan.totalMkd -ne $opt2.bestMultiStorePlan.totalMkd) {
        throw 'Basket optimization totals are not repeatable across runs!'
    }
    Write-Output "PASS repeatable_basket_totals (bestSingle=$($opt1.bestSingleStore.totalMkd) MKD, bestMulti=$($opt1.bestMultiStorePlan.totalMkd) MKD)"

    # Verify unit conversion: item 0 requested 800g of 400g Kadaif -> packsNeeded == 2
    $kadaifLine = $opt1.bestSingleStore.coveredItems | Where-Object { $_.itemIndex -eq 0 } | Select-Object -First 1
    if (-not $kadaifLine -or $kadaifLine.packsNeeded -ne 2) {
        throw "Expected packsNeeded=2 for 800g of 400g product, got $($kadaifLine | ConvertTo-Json -Compress)"
    }
    Write-Output "PASS unit_conversion_pack_scaling (800g -> packsNeeded=$($kadaifLine.packsNeeded), lineTotal=$($kadaifLine.lineTotalMkd) MKD)"

    # Verify coverage-first ranking and explicit missingItems on stores missing items
    if ($opt1.bestSingleStore.itemsCovered -ne 3) {
        throw "Expected bestSingleStore to cover all 3 items, got covered=$($opt1.bestSingleStore.itemsCovered) retailer=$($opt1.bestSingleStore.retailerSlug)"
    }
    $partialStore = $opt1.singleStoreRankings | Where-Object { $_.itemsCovered -lt 3 } | Select-Object -First 1
    if (-not $partialStore -or $partialStore.missingItems.Count -lt 1) {
        throw 'Expected partial store with itemsCovered<3 and explicit missingItems'
    }
    Write-Output "PASS explicit_missing_items_and_coverage_ranking (bestSingle covered=$($opt1.bestSingleStore.itemsCovered)/3 at $($opt1.bestSingleStore.retailerSlug), partialStore covered=$($partialStore.itemsCovered)/3 at $($partialStore.retailerSlug) missingReason=$($partialStore.missingItems[0].reason))"

    # Verify multi-store split saves money by buying Kadaif at Zito (318 MKD) + soups at Stokomak (138 MKD) = 456 MKD vs Vero single-store 519 MKD (saves 63 MKD)
    if ($opt1.bestMultiStorePlan.itemsCovered -ne 3 -or $opt1.bestMultiStorePlan.totalMkd -ge $opt1.bestSingleStore.totalMkd) {
        throw "Expected 2-store split to save MKD vs single store: multi=$($opt1.bestMultiStorePlan.totalMkd) vs single=$($opt1.bestSingleStore.totalMkd)"
    }
    Write-Output "PASS multi_store_split_optimization (storesUsed=$($opt1.bestMultiStorePlan.storesUsed), totalMkd=$($opt1.bestMultiStorePlan.totalMkd), savingsVsBestSingle=$($opt1.bestMultiStorePlan.savingsVsBestSingleStoreMkd) MKD)"

    # 7. Verify ADR-0003 substitute behavior on a Stage-2 pending_review candidate
    Write-Output '=== Step 7: Verify ADR-0003 allowSubstitutes=false vs allowSubstitutes=true ==='
    $reviewQueue = Invoke-RestMethod -Uri "$apiBase/matches/review-queue?limit=5"
    if ($reviewQueue.Count -lt 1) { throw 'Expected at least 1 pending_review candidate in review queue' }
    $cand = $reviewQueue[0]

    $strictBody = @{
        items = @(@{ canonicalProductId = $cand.candidateCanonicalId; quantity = 1; unit = 'pack' })
        retailers = @($cand.sourceRetailerSlug)
        allowSubstitutes = $false
        inStockOnly = $false
    } | ConvertTo-Json -Depth 5 -Compress

    $subBody = @{
        items = @(@{ canonicalProductId = $cand.candidateCanonicalId; quantity = 1; unit = 'pack' })
        retailers = @($cand.sourceRetailerSlug)
        allowSubstitutes = $true
        inStockOnly = $false
    } | ConvertTo-Json -Depth 5 -Compress

    $strictResp = Invoke-RestMethod -Method Post -Uri "$apiBase/baskets/optimize" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($strictBody))

    $subResp = Invoke-RestMethod -Method Post -Uri "$apiBase/baskets/optimize" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($subBody))

    if ($strictResp.singleStoreRankings.Count -ne 0) {
        throw "Expected 0 stores covering candidateCanonicalId=$($cand.candidateCanonicalId) at retailer=$($cand.sourceRetailerSlug) when allowSubstitutes=false"
    }
    if ($subResp.singleStoreRankings.Count -lt 1 -or -not $subResp.bestSingleStore.coveredItems[0].isSubstitute) {
        throw 'Expected substitute offer with isSubstitute=true when allowSubstitutes=true'
    }
    Write-Output "PASS adr0003_substitute_flagging (canonicalId=$($cand.candidateCanonicalId), retailer=$($cand.sourceRetailerSlug), isSubstitute=$($subResp.bestSingleStore.coveredItems[0].isSubstitute), confidence=$($subResp.bestSingleStore.coveredItems[0].matchConfidence))"

} catch {
    Write-Output "=== ERROR CAUGHT: Dumping $apiContainer logs ==="
    docker logs --tail 80 $apiContainer 2>&1 | Out-String | Write-Output
    throw
} finally {
    Cleanup-Containers
    if (-not $KeepDb) {
        docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;" 2>$null | Out-Null
    }
}

Write-Output 'M4 TEST OK'
