# Runs the cross-retailer comparison and price-history report against PostgreSQL.
param(
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

docker compose exec -T postgres mkdir -p /tmp/aishopping
docker compose cp scripts/report-cross-retailer.sql "postgres:/tmp/aishopping/report-cross-retailer.sql"
if ($LASTEXITCODE -ne 0) { throw 'docker compose cp report-cross-retailer.sql failed' }

docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 `
    -f /tmp/aishopping/report-cross-retailer.sql
if ($LASTEXITCODE -ne 0) { throw 'report-cross-retailer.sql failed' }
