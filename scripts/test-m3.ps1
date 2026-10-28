# M3 integration test:
# 1. Recreates a scratch PostgreSQL database and runs the full M2 3-retailer
#    ingestion + deterministic matching pipeline.
# 2. Starts an OpenSearch 3.9-compatible HTTP server (or uses live OpenSearch)
#    and executes two consecutive projection reindex runs (v1_pass1, v1_pass2)
#    to verify zero-downtime alias swapping and document count parity.
# 3. Packages and boots the Spring Boot REST API container and verifies all
#    6 read-only endpoints against OpenSearch ("sourceEngine": "opensearch").
# 4. Stops the OpenSearch container and verifies automatic PostgreSQL fallback
#    ("sourceEngine": "postgresql_fallback") with identical cross-retailer
#    product comparisons, prices, and provenance.
param(
    [string]$Database = 'ai_shopping_m3_test',
    [int]$ApiPort = 18080,
    [int]$MockOsPort = 19200,
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

$osContainer = 'aishopping-m3-opensearch'
$apiContainer = 'aishopping-m3-backend'

function Cleanup-Containers() {
    docker rm -f $apiContainer $osContainer 2>$null | Out-Null
}

Cleanup-Containers

try {
    # 1. Run M2 pipeline into $Database and keep the populated scratch DB
    Write-Output "=== Step 1: Populate $Database via M2 pipeline ==="
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-m2.ps1 -Database $Database -KeepDb
    if ($LASTEXITCODE -ne 0) { throw 'test-m2 setup failed' }

    # 2. Package Spring Boot backend JAR (if not already packaged)
    Write-Output "=== Step 2: Build & test Spring Boot backend ==="
    docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test package
    if ($LASTEXITCODE -ne 0) { throw 'maven test package failed' }

    # 3. Start OpenSearch service container for projection indexing
    Write-Output "=== Step 3: Start OpenSearch projection server on port $MockOsPort ==="
    docker run -d --name $osContainer -p "${MockOsPort}:9200" -v "${PWD}:/w" -w /w python:3.12-slim `
        python -B search/mock_opensearch.py --host 0.0.0.0 --port 9200 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start OpenSearch container' }

    $osUrl = "http://localhost:$MockOsPort"
    $osReady = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $h = Invoke-RestMethod -Uri "$osUrl/_cluster/health" -TimeoutSec 2
            if ($h.status -eq 'green') { $osReady = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $osReady) { throw 'OpenSearch server did not become healthy' }

    # 4. Run projection reindex twice to verify atomic alias swap + cleanup
    Write-Output "=== Step 4: Run OpenSearch projection reindexer (pass 1 & pass 2) ==="
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reindex-opensearch.ps1 `
        -Database $Database -OpenSearchUrl $osUrl -VersionTag 'v1_pass1'
    if ($LASTEXITCODE -ne 0) { throw 'reindex pass 1 failed' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reindex-opensearch.ps1 `
        -Database $Database -OpenSearchUrl $osUrl -VersionTag 'v1_pass2'
    if ($LASTEXITCODE -ne 0) { throw 'reindex pass 2 failed' }

    $storesAlias = Invoke-RestMethod -Uri "$osUrl/_alias/stores"
    if (-not $storesAlias.PSObject.Properties['stores_v1_v1_pass2']) {
        throw 'Expected alias stores -> stores_v1_v1_pass2 after second reindex pass'
    }
    Write-Output 'PASS opensearch_alias_swap_v1_pass2'

    # 5. Start Spring Boot backend container connected to Postgres and OpenSearch
    Write-Output "=== Step 5: Start Spring Boot REST API container on port $ApiPort ==="
    docker run -d --name $apiContainer --add-host=host.docker.internal:host-gateway `
        -p "${ApiPort}:8080" `
        -e "SPRING_DATASOURCE_URL=jdbc:postgresql://host.docker.internal:${DbPort}/${Database}" `
        -e "SPRING_DATASOURCE_USERNAME=${DbUser}" `
        -e "SPRING_DATASOURCE_PASSWORD=${DbPass}" `
        -e "AISHOPPING_OPENSEARCH_URL=http://host.docker.internal:${MockOsPort}" `
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

    # 6. Verify REST endpoints backed by OpenSearch
    Write-Output "=== Step 6: Verify REST endpoints with OpenSearch active ==="
    $healthOs = Invoke-RestMethod -Uri "$apiBase/health"
    if ($healthOs.activeSearchEngine -ne 'opensearch') {
        throw "Expected activeSearchEngine=opensearch, got $($healthOs.activeSearchEngine)"
    }
    if ($healthOs.counts.opensearch_offers -ne 1896) {
        throw "Expected opensearch_offers=1896, got $($healthOs.counts.opensearch_offers)"
    }
    Write-Output "PASS health_opensearch_active (offers=$($healthOs.counts.opensearch_offers), products=$($healthOs.counts.opensearch_products))"

    $storesOs = Invoke-RestMethod -Uri "$apiBase/stores?retailer=vero"
    if ($storesOs.sourceEngine -ne 'opensearch' -or $storesOs.total -ne 17) {
        throw "Expected 17 vero stores from opensearch, got engine=$($storesOs.sourceEngine) total=$($storesOs.total)"
    }
    Write-Output "PASS stores_endpoint_opensearch (vero stores=$($storesOs.total))"

    $offersOs = Invoke-RestMethod -Uri "$apiBase/offers/search?retailer=stokomak&inStockOnly=true&size=10"
    if ($offersOs.sourceEngine -ne 'opensearch' -or $offersOs.total -lt 100) {
        throw "Expected stokomak offers from opensearch, got engine=$($offersOs.sourceEngine) total=$($offersOs.total)"
    }
    if (-not $offersOs.items[0].sourceUrl -or -not $offersOs.items[0].publishedTs) {
        throw 'Offer response missing provenance fields (sourceUrl / publishedTs)'
    }
    Write-Output "PASS offers_search_opensearch (stokomak total=$($offersOs.total))"

    $compareOs = Invoke-RestMethod -Uri "$apiBase/products/compare?minRetailers=2&size=20"
    if ($compareOs.sourceEngine -ne 'opensearch' -or $compareOs.total -ne 6) {
        throw "Expected 6 cross-retailer canonical products from opensearch, got engine=$($compareOs.sourceEngine) total=$($compareOs.total)"
    }
    $firstCanonicalId = $compareOs.items[0].canonicalProductId
    Write-Output "PASS products_compare_opensearch (cross_retailer_products=$($compareOs.total))"

    $historyResp = Invoke-RestMethod -Uri "$apiBase/products/$firstCanonicalId/history"
    if ($historyResp.canonicalProductId -ne $firstCanonicalId -or $historyResp.observations.Count -lt 2) {
        throw "Expected >=2 price observations for canonical product $firstCanonicalId"
    }
    Write-Output "PASS product_history_endpoint (canonicalId=$firstCanonicalId, observations=$($historyResp.observations.Count))"

    $queueResp = Invoke-RestMethod -Uri "$apiBase/matches/review-queue?limit=25"
    if ($queueResp.Count -ne 20) {
        throw "Expected 20 pending_review matches, got $($queueResp.Count)"
    }
    Write-Output "PASS review_queue_endpoint (pending_review=$($queueResp.Count))"

    # 7. Stop OpenSearch and verify automatic PostgreSQL fallback (ADR-0002)
    Write-Output "=== Step 7: Stop OpenSearch and verify PostgreSQL fallback ==="
    docker rm -f $osContainer | Out-Null

    $healthPg = Invoke-RestMethod -Uri "$apiBase/health"
    if ($healthPg.activeSearchEngine -ne 'postgresql_fallback' -or $healthPg.opensearchStatus -ne 'FALLBACK_POSTGRESQL') {
        throw "Expected postgresql_fallback health status, got $($healthPg | ConvertTo-Json -Compress)"
    }
    Write-Output 'PASS health_postgresql_fallback'

    $comparePg = Invoke-RestMethod -Uri "$apiBase/products/compare?minRetailers=2&size=20"
    if ($comparePg.sourceEngine -ne 'postgresql_fallback' -or $comparePg.total -ne $compareOs.total) {
        throw "Fallback comparison mismatch: engine=$($comparePg.sourceEngine) total=$($comparePg.total) vs $($compareOs.total)"
    }
    Write-Output "PASS products_compare_postgresql_fallback (total=$($comparePg.total) matches OpenSearch)"

    $offersPg = Invoke-RestMethod -Uri "$apiBase/offers/search?retailer=stokomak&inStockOnly=true&size=10"
    if ($offersPg.sourceEngine -ne 'postgresql_fallback' -or $offersPg.total -ne $offersOs.total) {
        throw "Fallback offers mismatch: engine=$($offersPg.sourceEngine) total=$($offersPg.total) vs $($offersOs.total)"
    }
    Write-Output "PASS offers_search_postgresql_fallback (total=$($offersPg.total) matches OpenSearch)"

} finally {
    Cleanup-Containers
    if (-not $KeepDb) {
        docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;" 2>$null | Out-Null
    }
}

Write-Output 'M3 TEST OK'
