# M0 baseline validation. Requires Docker Compose v2+ and a local .env copied from .env.example.
param(
    [switch]$SkipOpenSearch
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Output 'Created .env from .env.example'
}

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}

$services = @('postgres')
if (-not $SkipOpenSearch) { $services += 'opensearch' }

docker compose up -d --wait @services
if ($LASTEXITCODE -ne 0) { throw 'docker compose up --wait failed' }

$pgVersion = docker compose exec -T postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -t -A -c "SHOW server_version;"
if ($LASTEXITCODE -ne 0) { throw 'psql version query failed' }
Write-Output "PostgreSQL server_version: $pgVersion"
if ($pgVersion -notlike '18.*') { throw "Unexpected PostgreSQL major version: $pgVersion" }

if (-not $SkipOpenSearch) {
    $osInfo = Invoke-RestMethod -Uri 'http://localhost:9200/' -Method Get
    Write-Output "OpenSearch version: $($osInfo.version.number) (distribution $($osInfo.version.distribution_name))"
    if ($osInfo.version.number -ne '3.9.0') { throw "Unexpected OpenSearch version: $($osInfo.version.number)" }

    $health = Invoke-RestMethod -Uri 'http://localhost:9200/_cluster/health' -Method Get
    Write-Output "OpenSearch cluster status: $($health.status) (cluster_name $($health.cluster_name))"
} else {
    Write-Output 'OpenSearch check skipped (-SkipOpenSearch)'
}

Write-Output 'BASELINE OK'
