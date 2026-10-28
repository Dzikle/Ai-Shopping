# Exports authoritative PostgreSQL state and reindexes OpenSearch projections
# (stores_v1, offers_v1, products_v1) with atomic alias swap (ADR-0002).
param(
    [string]$Database = '',
    [string]$DbUser = '',
    [string]$OpenSearchUrl = '',
    [string]$VersionTag = ''
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
if (-not $OpenSearchUrl) { $OpenSearchUrl = $OPENSEARCH_URL }
if (-not $VersionTag) { $VersionTag = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss') }

$tmpHostDir = "snapshots/opensearch/$VersionTag"
New-Item -ItemType Directory -Force -Path $tmpHostDir | Out-Null

docker compose exec -T postgres mkdir -p /tmp/aishopping
docker compose cp scripts/export-projection-docs.sql "postgres:/tmp/aishopping/export-projection-docs.sql"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp export-projection-docs.sql failed' }

docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 `
    -f /tmp/aishopping/export-projection-docs.sql
if ($LASTEXITCODE -ne 0) { throw 'export-projection-docs.sql failed' }

foreach ($f in @('projection_stores.ndjson', 'projection_offers.ndjson', 'projection_products.ndjson')) {
    docker compose cp "postgres:/tmp/aishopping/$f" (Join-Path $tmpHostDir $f)
    if ($LASTEXITCODE -ne 0) { throw "docker compose cp $f failed" }
}

# Run reindexer against OpenSearch URL (supports host.docker.internal when targeting a host port)
$containerOsUrl = $OpenSearchUrl -replace 'localhost|127\.0\.0\.1', 'host.docker.internal'
docker run --rm --add-host=host.docker.internal:host-gateway -v "${PWD}:/w" -w /w python:3.12-slim `
    python -B search/reindexer.py `
    --opensearch-url $containerOsUrl `
    --stores-ndjson "$tmpHostDir/projection_stores.ndjson" `
    --offers-ndjson "$tmpHostDir/projection_offers.ndjson" `
    --products-ndjson "$tmpHostDir/projection_products.ndjson" `
    --version-tag $VersionTag
if ($LASTEXITCODE -ne 0) { throw 'OpenSearch reindexer failed' }

Write-Output "REINDEX OK version_tag=$VersionTag"
