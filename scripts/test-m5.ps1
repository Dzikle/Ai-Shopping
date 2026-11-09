# M5 integration test:
# 1. Recreates scratch PostgreSQL database (`ai_shopping_m5_test`), applies
#    migrations V1 + V2 + V3, and loads Vero + Stokomak + Zito fixtures and
#    deterministic product matches via `scripts/test-m2.ps1 -KeepDb`.
# 2. Syncs (uv, locked) and boots the FastAPI backend container exposing the MCP server
#    at `/mcp` on port $ApiPort.
# 3. Performs full Model Context Protocol 2024-11-05 handshake:
#    - GET /mcp (server info & discovery)
#    - POST /mcp initialize
#    - POST /mcp notifications/initialized
#    - POST /mcp ping
#    - POST /mcp tools/list (verifies all 7 tools registered)
# 4. Executes all 7 MCP tools via tools/call over HTTP:
#    - search_products
#    - compare_product_prices
#    - get_price_history
#    - list_stores
#    - find_current_discounts
#    - optimize_shopping_basket (verifies that totals match POST /api/v1/baskets/optimize exactly)
#    - suggest_product_substitutes
param(
    [string]$Database = 'ai_shopping_m5_test',
    [int]$ApiPort = 18085,
    [switch]$KeepDb
)
$ErrorActionPreference = 'Stop'
$psExe = if ($env:OS -eq 'Windows_NT') { 'powershell' } else { 'pwsh' }
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
$DbUser = $POSTGRES_USER
$DbPass = $POSTGRES_PASSWORD
$DbPort = if ($POSTGRES_PORT) { $POSTGRES_PORT } else { '5432' }

$apiContainer = 'aishopping-m5-backend'

function Cleanup-Containers() {
    docker rm -f $apiContainer 2>$null | Out-Null
}

Cleanup-Containers

try {
    # 1. Populate $Database via M2 pipeline
    Write-Output "=== Step 1: Populate $Database via M2 pipeline (V1+V2+V3) ==="
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/test-m2.ps1 -Database $Database -KeepDb
    if ($LASTEXITCODE -ne 0) { throw 'test-m2 setup failed' }

    # 2. Sync FastAPI backend dependencies and run its test suite (uv, locked)
    Write-Output '=== Step 2: Sync and test FastAPI backend (uv) ==='
    docker run --rm -v "${PWD}/backend_py:/w" -v aoshopping-uv-cache:/root/.cache/uv -v aoshopping-uv-venv:/w/.venv -w /w `
        ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
        sh -c "uv sync --locked && uv run pytest -q"
    if ($LASTEXITCODE -ne 0) { throw 'fastapi backend tests failed' }

    # 3. Start FastAPI backend container connected to $Database
    Write-Output "=== Step 3: Start FastAPI MCP server container on port $ApiPort ==="
    docker run -d --name $apiContainer --add-host=host.docker.internal:host-gateway `
        -p "${ApiPort}:8000" `
        -e "POSTGRES_HOST=host.docker.internal" `
        -e "POSTGRES_PORT=${DbPort}" `
        -e "POSTGRES_DB=${Database}" `
        -e "POSTGRES_USER=${DbUser}" `
        -e "POSTGRES_PASSWORD=${DbPass}" `
        -e "OPENSEARCH_URL=http://127.0.0.1:1" `
        -v "${PWD}/backend_py:/w" -v aoshopping-uv-cache:/root/.cache/uv -v aoshopping-uv-venv:/w/.venv -w /w `
        ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
        uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start backend container' }

    $mcpBase = "http://localhost:$ApiPort/mcp"
    $restBase = "http://localhost:$ApiPort/api/v1"
    $serverReady = $false
    for ($i = 0; $i -lt 240; $i++) {
        try {
            $info = Invoke-RestMethod -Uri $mcpBase -TimeoutSec 2
            if ($info.server -eq 'ai-shopping-mcp-server') { $serverReady = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $serverReady) {
        docker logs --tail 15 $apiContainer
        "::error::mcp_server_not_healthy port=$ApiPort containers=$((docker ps -a --format '{{.Names}} {{.Status}}') -join ' | ')"
        throw 'MCP server did not become healthy'
    }

    function Invoke-Utf8Rest($method, $uri, $bodyObj = $null) {
        $params = @{
            Uri = $uri
            Method = $method
            UseBasicParsing = $true
        }
        if ($null -ne $bodyObj) {
            $json = $bodyObj | ConvertTo-Json -Depth 8 -Compress
            $params['Body'] = [System.Text.Encoding]::UTF8.GetBytes($json)
            $params['ContentType'] = 'application/json; charset=utf-8'
        }
        $res = Invoke-WebRequest @params
        $jsonStr = [System.Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray())
        return ($jsonStr | ConvertFrom-Json)
    }

    # 4. MCP Protocol Handshake
    Write-Output '=== Step 4: MCP Protocol Handshake ==='
    $info = Invoke-Utf8Rest 'Get' $mcpBase
    if ($info.protocolVersion -ne '2024-11-05' -or $info.endpoint -ne '/mcp') {
        throw "Unexpected GET /mcp response: $($info | ConvertTo-Json -Compress)"
    }
    Write-Output "PASS mcp_server_info_discovery (server=$($info.server), version=$($info.version))"

    function Invoke-McpRpc($id, $method, $params) {
        $resp = Invoke-Utf8Rest 'Post' $mcpBase @{
            jsonrpc = '2.0'
            id = $id
            method = $method
            params = $params
        }
        if ($resp.error) {
            throw "JSON-RPC error in $method : $($resp.error | ConvertTo-Json -Compress)"
        }
        return $resp.result
    }

    $initRes = Invoke-McpRpc 1 'initialize' @{
        protocolVersion = '2024-11-05'
        clientInfo = @{ name = 'test-client'; version = '1.0' }
    }
    if ($initRes.protocolVersion -ne '2024-11-05' -or -not $initRes.capabilities.tools) {
        throw "Failed initialize: $($initRes | ConvertTo-Json -Compress)"
    }
    Write-Output 'PASS mcp_initialize'

    # Notification (no id)
    $notifPayload = '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
    $notifBytes = [System.Text.Encoding]::UTF8.GetBytes($notifPayload)
    $notifResp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $mcpBase -ContentType 'application/json; charset=utf-8' -Body $notifBytes
    if ($notifResp.StatusCode -ne 204) {
        throw "Expected 204 No Content on notification, got $($notifResp.StatusCode)"
    }
    Write-Output 'PASS mcp_notifications_initialized'

    $pingRes = Invoke-McpRpc 2 'ping' @{}
    Write-Output 'PASS mcp_ping'

    $toolsListRes = Invoke-McpRpc 3 'tools/list' @{}
    if ($toolsListRes.tools.Count -ne 7) {
        throw "Expected 7 MCP tools, got $($toolsListRes.tools.Count)"
    }
    Write-Output "PASS mcp_tools_list (registered_tools=$($toolsListRes.tools.Count))"

    # 5. Execute Tools
    Write-Output '=== Step 5: Execute Tools via tools/call ==='

    # Lookup real canonical products from REST to get search term without hardcoding non-ASCII literals in ps1
    $comparisonsAll = Invoke-Utf8Rest 'Get' "$restBase/products/compare?minRetailers=2&size=20"
    if ($comparisonsAll.total -lt 3) { throw "Expected >=3 cross-retailer canonical products, got $($comparisonsAll.total)" }

    $veroZito = $comparisonsAll.items | Where-Object { $_.normalizedSize -match '400g' } | Select-Object -First 1
    $soups = @($comparisonsAll.items | Where-Object { $_.normalizedSize -match '60g' })
    if (-not $veroZito -or $soups.Count -lt 2) {
        throw 'Expected 400g Vero+Zito product and two 60g soup products in comparisons'
    }

    $searchTerm = $veroZito.canonicalName.Split(' ')[0]
    $kadaifId = $veroZito.canonicalProductId

    # Tool 1: search_products
    $searchRes = Invoke-McpRpc 4 'tools/call' @{
        name = 'search_products'
        arguments = @{ query = $searchTerm; inStockOnly = $true; size = 5 }
    }
    $searchData = $searchRes.content[0].text | ConvertFrom-Json
    if ($searchData.totalMatches -lt 1 -or -not $searchData.items[0].sourceUrl) {
        throw 'search_products returned no matches or missing provenance'
    }
    Write-Output "PASS tool_search_products (matches=$($searchData.totalMatches), sampleSourceUrl=$($searchData.items[0].sourceUrl))"

    # Tool 2: compare_product_prices
    $cmpRes = Invoke-McpRpc 5 'tools/call' @{
        name = 'compare_product_prices'
        arguments = @{ query = $searchTerm; minRetailers = 2; size = 5 }
    }
    $cmpData = $cmpRes.content[0].text | ConvertFrom-Json
    if ($cmpData.totalComparisons -lt 1 -or -not $cmpData.comparisons[0].cheapestMkd) {
        throw 'compare_product_prices failed'
    }
    Write-Output "PASS tool_compare_product_prices (canonicalId=$kadaifId, spread=$($cmpData.comparisons[0].spreadMkd) MKD)"

    # Tool 3: get_price_history
    $histRes = Invoke-McpRpc 6 'tools/call' @{
        name = 'get_price_history'
        arguments = @{ canonicalProductId = $kadaifId }
    }
    $histData = $histRes.content[0].text | ConvertFrom-Json
    if ($histData.totalObservations -lt 2) {
        throw "Expected >=2 observations for canonicalId $kadaifId"
    }
    Write-Output "PASS tool_get_price_history (observations=$($histData.totalObservations))"

    # Tool 4: list_stores
    $storesRes = Invoke-McpRpc 7 'tools/call' @{
        name = 'list_stores'
        arguments = @{ retailer = 'vero' }
    }
    $storesData = $storesRes.content[0].text | ConvertFrom-Json
    if ($storesData.totalStores -ne 17) {
        throw "Expected 17 Vero stores, got $($storesData.totalStores)"
    }
    Write-Output "PASS tool_list_stores (vero stores=$($storesData.totalStores))"

    # Tool 5: find_current_discounts
    $discRes = Invoke-McpRpc 8 'tools/call' @{
        name = 'find_current_discounts'
        arguments = @{ retailer = 'stokomak'; size = 5 }
    }
    $discData = $discRes.content[0].text | ConvertFrom-Json
    if ($discData.totalDiscounts -lt 1 -or -not $discData.discounts[0].isPromo) {
        throw 'find_current_discounts returned no promotional items'
    }
    Write-Output "PASS tool_find_current_discounts (discounts=$($discData.totalDiscounts))"

    # Tool 6: optimize_shopping_basket
    # Compare verbatim against REST POST /api/v1/baskets/optimize
    $basketItems = @(
        @{ canonicalProductId = $veroZito.canonicalProductId; quantity = 800; unit = 'g'; itemLabel = 'Kadaif' },
        @{ canonicalProductId = $soups[0].canonicalProductId; quantity = 2; unit = 'pack'; itemLabel = 'Soup 1' },
        @{ canonicalProductId = $soups[1].canonicalProductId; quantity = 1; unit = 'pack'; itemLabel = 'Soup 2' }
    )
    $basketArgs = @{
        items = $basketItems
        maxStores = 2
        minSplitSavingsMkd = 5.00
        allowSubstitutes = $false
        inStockOnly = $true
    }

    $mcpBasketRes = Invoke-McpRpc 9 'tools/call' @{
        name = 'optimize_shopping_basket'
        arguments = $basketArgs
    }
    $mcpBasket = $mcpBasketRes.content[0].text | ConvertFrom-Json

    $restBasket = Invoke-Utf8Rest 'Post' "$restBase/baskets/optimize" $basketArgs

    if ($mcpBasket.bestSingleStore.totalMkd -ne $restBasket.bestSingleStore.totalMkd -or `
        $mcpBasket.bestMultiStorePlan.totalMkd -ne $restBasket.bestMultiStorePlan.totalMkd) {
        throw "Mismatch between MCP and REST basket totals! MCP single=$($mcpBasket.bestSingleStore.totalMkd), REST single=$($restBasket.bestSingleStore.totalMkd)"
    }
    Write-Output "PASS tool_optimize_shopping_basket_deterministic_match (bestSingle=$($mcpBasket.bestSingleStore.totalMkd) MKD, bestMulti=$($mcpBasket.bestMultiStorePlan.totalMkd) MKD)"

    # Tool 7: suggest_product_substitutes
    $subsRes = Invoke-McpRpc 10 'tools/call' @{
        name = 'suggest_product_substitutes'
        arguments = @{ limit = 5 }
    }
    $subsData = $subsRes.content[0].text | ConvertFrom-Json
    if ($subsData.substitutesCount -lt 1 -or -not $subsData.candidates[0].evidence) {
        throw 'suggest_product_substitutes returned no candidates'
    }
    Write-Output "PASS tool_suggest_product_substitutes (candidates=$($subsData.substitutesCount), sampleConfidence=$($subsData.candidates[0].confidence))"

} catch {
    "::error::M5-TEST-FAILED: $($_.Exception.Message)"
    Write-Output "=== ERROR CAUGHT: Dumping $apiContainer logs ==="
    docker logs --tail 80 $apiContainer 2>&1 | Out-String | Write-Output
    throw
} finally {
    Cleanup-Containers
    if (-not $KeepDb) {
        docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;" 2>$null | Out-Null
    }
}

Write-Output 'M5 TEST OK'
