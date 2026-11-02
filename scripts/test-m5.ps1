# M5 integration test (bounded read-only MCP server):
# 1. Runs the stdlib-only MCP contract suite (`mcp_server/tests.py`) against the
#    in-process mock of the M3/M4 REST API: JSON-RPC lifecycle, tool schemas,
#    hard bounds, determinism, provenance, identity labelling, read-only
#    allowlist enforcement, upstream failure handling and stdio round-trip.
# 2. Validates the published `v1` tool contract snapshot: every tool declares
#    `readOnlyHint`, and the read-only route allowlist stays at 6 entries.
# 3. If `-ApiBase` is supplied (or AI_SHOPPING_API_BASE is set), additionally
#    verifies the live Spring Boot API through a real stdio MCP handshake:
#    initialize -> tools/list -> tools/call(get_catalog_health) and compares the
#    reported engine/counts with a direct REST call.
param(
    [string]$ApiBase = $env:AI_SHOPPING_API_BASE,
    [switch]$SkipLive
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

$python = $null
foreach ($candidate in @('python3', 'python')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
$useDocker = $false
if (-not $python) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Neither python nor docker is available to run the MCP tests'
    }
    $useDocker = $true
    Write-Output 'INFO python not found; using python:3.12-slim via docker'
}

function Invoke-RepoPython {
    param([string[]]$RepoArgs)
    if ($useDocker) {
        $output = docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B @RepoArgs
    } else {
        $output = & $python -B @RepoArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "python failed: $($RepoArgs -join ' ')" }
    return $output
}

function Invoke-RepoPythonStdio {
    param([string[]]$RepoArgs, [string]$InputText)
    if ($useDocker) {
        $output = $InputText | docker run --rm -i -v "${PWD}:/w" -w /w python:3.12-slim python -B @RepoArgs
    } else {
        $output = $InputText | & $python -B @RepoArgs 2>$null
    }
    if ($LASTEXITCODE -ne 0) { throw "python stdio run failed: $($RepoArgs -join ' ')" }
    return $output
}

Write-Output '=== Step 1: MCP contract tests (stdlib only, mock REST API) ==='
$testOutput = Invoke-RepoPython @('mcp_server/tests.py')
$testOutput | Write-Output
if (-not ($testOutput -match 'OK')) { throw 'MCP contract tests did not report OK' }
Write-Output 'PASS mcp_contract_tests'

Write-Output '=== Step 2: v1 tool contract snapshot ==='
$contractRaw = (Invoke-RepoPython @('mcp_server/cli.py', '--list-tools')) -join "`n"
$contract = $contractRaw | ConvertFrom-Json
if ($contract.tools.Count -ne 9) { throw "expected 9 MCP tools, got $($contract.tools.Count)" }
foreach ($tool in $contract.tools) {
    if (-not $tool.annotations.readOnlyHint) { throw "tool $($tool.name) is not marked read-only" }
    if ($tool.annotations.destructiveHint) { throw "tool $($tool.name) is marked destructive" }
}
if ($contract.allowedRoutes.Count -ne 6) {
    throw "expected 6 allowlisted read-only routes, got $($contract.allowedRoutes.Count)"
}
foreach ($route in $contract.allowedRoutes) {
    if ($route -match 'baskets/lists' -or $route -match 'review-queue') {
        throw "mutating or internal route leaked into the MCP allowlist: $route"
    }
}
Write-Output "PASS mcp_tool_contract (tools=$($contract.tools.Count), routes=$($contract.allowedRoutes.Count), version=$($contract.toolsVersion))"

if ($SkipLive) {
    Write-Output 'SKIP live MCP handshake (-SkipLive)'
} elseif (-not $ApiBase) {
    Write-Output 'SKIP live MCP handshake (no -ApiBase / AI_SHOPPING_API_BASE supplied)'
} else {
    Write-Output "=== Step 3: live MCP handshake against $ApiBase ==="
    $health = Invoke-RestMethod -Uri "$ApiBase/api/v1/health" -TimeoutSec 20
    if ($health.status -ne 'UP') { throw "live API health is $($health.status)" }
    Write-Output "PASS live_api_health (engine=$($health.activeSearchEngine))"

    $frames = @(
        (@{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{ protocolVersion = '2025-06-18'; capabilities = @{} } } | ConvertTo-Json -Compress -Depth 8),
        (@{ jsonrpc = '2.0'; method = 'notifications/initialized' } | ConvertTo-Json -Compress -Depth 8),
        (@{ jsonrpc = '2.0'; id = 2; method = 'tools/list' } | ConvertTo-Json -Compress -Depth 8),
        (@{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{ name = 'get_catalog_health'; arguments = @{} } } | ConvertTo-Json -Compress -Depth 8)
    ) -join "`n"

    $handshakeRaw = Invoke-RepoPythonStdio @('mcp_server/cli.py', '--api-base', $ApiBase) ($frames + "`n")
    $responses = @($handshakeRaw | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
    if ($responses.Count -ne 3) { throw "expected 3 MCP responses, got $($responses.Count)" }
    if ($responses[0].result.serverInfo.name -ne 'ai-shopping-mcp') { throw 'unexpected MCP server name' }
    if ($responses[1].result.tools.Count -ne 9) { throw "tools/list returned $($responses[1].result.tools.Count) tools" }
    $liveHealth = $responses[2].result.structuredContent
    if ($responses[2].result.isError) { throw 'get_catalog_health returned isError=true over stdio' }
    if ($liveHealth.activeSearchEngine -ne $health.activeSearchEngine) {
        throw "engine mismatch: mcp=$($liveHealth.activeSearchEngine) rest=$($health.activeSearchEngine)"
    }
    if ($liveHealth.counts.offers_current -ne $health.counts.offers_current) {
        throw "offer count mismatch: mcp=$($liveHealth.counts.offers_current) rest=$($health.counts.offers_current)"
    }
    Write-Output "PASS live_mcp_handshake (offers_current=$($liveHealth.counts.offers_current), engine=$($liveHealth.activeSearchEngine))"
}

Write-Output 'M5 TEST OK'
