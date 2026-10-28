# Loads one CLI run (records.ndjson + snapshots.ndjson + manifest.json) into
# the target database. Refuses quarantined runs unless -Force is given.
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $true)][string]$RunKey,
    [string]$Database = '',
    [string]$DbUser = '',
    [string]$SourceSlug = '',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
if (-not $Database) { $Database = $POSTGRES_DB }
if (-not $DbUser) { $DbUser = $POSTGRES_USER }

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
    -f /tmp/aishopping/load-records.sql
if ($LASTEXITCODE -ne 0) { throw 'load-records.sql failed' }

Write-Output "LOADED run_key=$RunKey status=$status rows_stored=$($manifest.rows_stored)"
