# M6 end-to-end daily ingestion pipeline orchestrator.
# Executes:
# 1. Postgres startup + migrations (V1..V4)
# 2. Scheduler worker (`adapters/scheduler/cli.py --once`) for Vero, Stokomak, Zito
# 3. Loader (`scripts/load-records.ps1`) per retailer (quarantined runs record status='quarantined'
#    and fire `scripts/alert.ps1` while preserving live `offers_current`)
# 4. Deterministic product matching (`matching/cli.py` + `scripts/load-matches.ps1`)
# 5. Optional OpenSearch projection reindex (`scripts/reindex-opensearch.ps1`)
# 6. Cross-retailer comparison report (`scripts/report-cross-retailer.ps1`)
# 7. Optional freshness verification (`scripts/check-freshness.ps1`)
param(
    [string]$Database = '',
    [string]$RunTag = '',
    [string]$Retailers = 'vero,stokomak,zito,kam',
    [switch]$FromSnapshots,
    [switch]$Live,
    [string]$SnapshotMap = '',
    [string]$StoresMap = 'vero=89,stokomak=1,zito=2,kam=73',
    [int]$MaxPages = 50,
    [double]$Delay = 1.0,
    [string]$OpenSearchUrl = '',
    [string]$ApiUrl = '',
    [int]$StaleThresholdHours = 48
)
$ErrorActionPreference = 'Stop'
$psExe = if ($env:OS -eq 'Windows_NT') { 'powershell' } else { 'pwsh' }
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
if (-not $Database) { $Database = $POSTGRES_DB }
$dateStr = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
if (-not $RunTag) {
    $RunTag = 'm6-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
}

# 1. Ensure PostgreSQL is running and migrations are applied
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'postgres failed to start' }

& $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/apply-migrations.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'migrations failed' }

# 2. Run scheduler worker (--once)
$schedArgs = @(
    '-B', 'adapters/scheduler/cli.py',
    '--once',
    '--retailers', $Retailers,
    '--run-tag', $RunTag,
    '--max-pages', "$MaxPages",
    '--delay', "$Delay"
)
if ($Live) {
    $schedArgs += '--live'
    if ($StoresMap) {
        $schedArgs += @('--stores-map', $StoresMap)
    }
} else {
    $schedArgs += '--from-snapshots'
    if ($SnapshotMap) {
        $schedArgs += @('--snapshot-map', $SnapshotMap)
    }
}

docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python @schedArgs
$schedExit = $LASTEXITCODE
if ($schedExit -ne 0 -and $schedExit -ne 2) {
    throw "scheduler cli failed with exit code $schedExit"
}

$manifestPath = "snapshots/scheduler/$dateStr/$RunTag/scheduler_manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "scheduler manifest not found: $manifestPath"
}
$schedManifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

# 3. Load each retailer run into PostgreSQL
$healthyDirs = @()
$anyQuarantined = $false

foreach ($r in $schedManifest.retailers) {
    if (-not $r.out_dir) {
        throw "retailer $($r.retailer) produced no output directory"
    }
    $ErrorActionPreference = 'Continue'
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 `
        -OutDir $r.out_dir `
        -RunKey $r.run_key `
        -SourceSlug $r.retailer `
        -Database $Database `
        -WorkerId $schedManifest.worker_id
    $loadExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    if ($loadExit -eq 2) {
        $anyQuarantined = $true
        Write-Output "PIPELINE_QUARANTINED: retailer=$($r.retailer) run_key=$($r.run_key)"
    } elseif ($loadExit -ne 0) {
        throw "load-records failed for $($r.retailer) (exit=$loadExit)"
    } else {
        $healthyDirs += $r.out_dir
    }
}

# 4. Run deterministic product matching across loaded runs
if ($healthyDirs.Count -gt 0) {
    $matchOut = "snapshots/matching/$dateStr/$RunTag-match"
    $runDirsArg = ($healthyDirs -join ',')
    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B matching/cli.py --run-dirs $runDirsArg --out $matchOut
    if ($LASTEXITCODE -ne 0) { throw 'matching cli failed' }

    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/load-matches.ps1 -OutDir $matchOut -Database $Database
    if ($LASTEXITCODE -ne 0) { throw 'load-matches failed' }
}

# 5. Optional OpenSearch projection reindex
if ($OpenSearchUrl) {
    $versionTag = "v1_$($RunTag -replace '[^a-zA-Z0-9_]', '_')"
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/reindex-opensearch.ps1 `
        -Database $Database `
        -OpenSearchUrl $OpenSearchUrl `
        -VersionTag $versionTag
    if ($LASTEXITCODE -ne 0) { throw 'reindex-opensearch failed' }
}

# 6. Cross-retailer comparison report
& $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/report-cross-retailer.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'report-cross-retailer failed' }

# 7. Optional freshness check
if ($ApiUrl) {
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/check-freshness.ps1 `
        -ApiUrl $ApiUrl `
        -StaleThresholdHours $StaleThresholdHours
    if ($LASTEXITCODE -ne 0) {
        throw "freshness check failed against $ApiUrl"
    }
}

if ($anyQuarantined) {
    Write-Output "PIPELINE COMPLETED WITH QUARANTINED RUNS (run_tag=$RunTag)"
    exit 2
}

Write-Output "PIPELINE OK (run_tag=$RunTag)"
exit 0
