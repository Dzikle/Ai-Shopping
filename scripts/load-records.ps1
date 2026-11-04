# Loads one CLI run (records.ndjson + snapshots.ndjson + manifest.json) into
# the target database. Refuses quarantined runs unless -Force is given.
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $true)][string]$RunKey,
    [string]$Database = '',
    [string]$DbUser = '',
    [string]$SourceSlug = '',
    [string]$WorkerId = '',
    [switch]$Force
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
if (-not $DbUser) { $DbUser = $POSTGRES_USER }
if (-not $WorkerId) {
    $workerHostname = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } elseif ($env:HOSTNAME) { $env:HOSTNAME } else { 'unknown' }
    $WorkerId = "$($workerHostname):$PID"
}

$recordsPath = Join-Path $OutDir 'records.ndjson'
$snapshotsPath = Join-Path $OutDir 'snapshots.ndjson'
$manifestPath = Join-Path $OutDir 'manifest.json'
foreach ($p in @($recordsPath, $snapshotsPath, $manifestPath)) {
    if (-not (Test-Path $p)) { throw "missing loader input: $p" }
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
if (-not $SourceSlug) { $SourceSlug = $manifest.source_slug }
if (-not $SourceSlug) { $SourceSlug = 'vero' }
if ($manifest.quarantined -and -not $Force) {
    $qSql = @"
INSERT INTO ingestion_runs (run_key, source_slug, status, finished_at, pages_seen, rows_seen, rows_stored, rows_skipped, quarantined, quarantine_reason, worker_id)
VALUES (:'run_key', :'source_slug', 'quarantined', now(), (:'pages_seen')::int, (:'rows_seen')::int, 0, (:'rows_skipped')::int, true, :'quarantine_reason', NULLIF(:'worker_id', ''))
ON CONFLICT (run_key) DO UPDATE SET
    status = 'quarantined',
    finished_at = now(),
    pages_seen = EXCLUDED.pages_seen,
    rows_seen = EXCLUDED.rows_seen,
    rows_stored = 0,
    rows_skipped = EXCLUDED.rows_skipped,
    quarantined = true,
    quarantine_reason = EXCLUDED.quarantine_reason,
    worker_id = COALESCE(EXCLUDED.worker_id, ingestion_runs.worker_id);
"@
    $qSql | docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 `
        -v run_key="$RunKey" `
        -v source_slug="$SourceSlug" `
        -v pages_seen="$($manifest.pages_seen)" `
        -v rows_seen="$($manifest.rows_seen)" `
        -v rows_skipped="$($manifest.rows_skipped)" `
        -v quarantine_reason="$($manifest.quarantine_reason)" `
        -v worker_id="$WorkerId" `
        -f - | Out-Null

    $alertScript = Join-Path $PSScriptRoot 'alert.ps1'
    if (Test-Path $alertScript) {
        $firstStore = if ($manifest.pages -and $manifest.pages.Count -gt 0) { "$($manifest.pages[0].store_external_key)" } else { 'unknown' }
        & $psExe -NoProfile -ExecutionPolicy Bypass -File $alertScript `
            -Level 'error' `
            -Retailer $SourceSlug `
            -Store $firstStore `
            -Message "Quarantined: $($manifest.quarantine_reason)" `
            -RunKey $RunKey
    }
    Write-Output "QUARANTINED run refused: $($manifest.quarantine_reason)"
    exit 2
}

$status = 'completed'
if ($manifest.quarantined) { $status = 'quarantined' }
if ($manifest.rows_stored -eq 0 -and -not $manifest.quarantined) { $status = 'failed' }

docker compose exec -T postgres mkdir -p /tmp/aishopping
docker compose cp scripts/load-records.sql "postgres:/tmp/aishopping/load-records.sql"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp loader sql failed' }
docker compose cp $recordsPath "postgres:/tmp/aishopping/records.ndjson"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp records failed' }
docker compose cp $snapshotsPath "postgres:/tmp/aishopping/snapshots.ndjson"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp snapshots failed' }

docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 `
    -v run_key="$RunKey" `
    -v source_slug="$SourceSlug" `
    -v status="$status" `
    -v pages_seen="$($manifest.pages_seen)" `
    -v rows_seen="$($manifest.rows_seen)" `
    -v rows_stored="$($manifest.rows_stored)" `
    -v rows_skipped="$($manifest.rows_skipped)" `
    -v quarantined="$($manifest.quarantined.ToString().ToLower())" `
    -v quarantine_reason="$($manifest.quarantine_reason)" `
    -v worker_id="$WorkerId" `
    -f /tmp/aishopping/load-records.sql
if ($LASTEXITCODE -ne 0) { throw 'load-records.sql failed' }

Write-Output "LOADED run_key=$RunKey status=$status rows_stored=$($manifest.rows_stored)"
