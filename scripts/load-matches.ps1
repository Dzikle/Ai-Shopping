# Loads canonical_products.ndjson + product_matches.ndjson into PostgreSQL.
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Database = '',
    [string]$DbUser = ''
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

$canonicalPath = Join-Path $OutDir 'canonical_products.ndjson'
$matchesPath = Join-Path $OutDir 'product_matches.ndjson'
$manifestPath = Join-Path $OutDir 'matches_manifest.json'
foreach ($p in @($canonicalPath, $matchesPath, $manifestPath)) {
    if (-not (Test-Path $p)) { throw "missing match loader input: $p" }
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

docker compose exec -T postgres mkdir -p /tmp/aishopping
docker compose cp scripts/load-matches.sql "postgres:/tmp/aishopping/load-matches.sql"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp load-matches.sql failed' }
docker compose cp $canonicalPath "postgres:/tmp/aishopping/canonical_products.ndjson"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp canonical_products.ndjson failed' }
docker compose cp $matchesPath "postgres:/tmp/aishopping/product_matches.ndjson"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp product_matches.ndjson failed' }

docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 `
    -f /tmp/aishopping/load-matches.sql
if ($LASTEXITCODE -ne 0) { throw 'load-matches.sql failed' }

Write-Output "LOADED_MATCHES canonical=$($manifest.canonical_products) cross_retailer=$($manifest.cross_retailer_canonical_products) stage1=$($manifest.stage1_auto_accepted) stage2_queue=$($manifest.stage2_pending_review)"
