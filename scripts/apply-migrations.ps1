# Applies migrations/*.sql to a database inside the postgres service, in
# filename order, tracking applied versions in schema_migrations.
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

docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"
if ($LASTEXITCODE -ne 0) { throw 'schema_migrations bootstrap failed' }

$migrations = Get-ChildItem 'migrations' -Filter '*.sql' | Sort-Object Name
if (-not $migrations) { throw 'no migration files found' }

foreach ($mig in $migrations) {
    $version = $mig.BaseName
    $applied = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -c "SELECT count(*) FROM schema_migrations WHERE version = '$version';"
    if ($LASTEXITCODE -ne 0) { throw "version check failed for $version" }
    if ($applied -eq '1') {
        Write-Output "SKIP $version (already applied)"
        continue
    }
    docker compose cp $mig.FullName "postgres:/tmp/$($mig.Name)"
    if ($LASTEXITCODE -ne 0) { throw "docker compose cp failed for $version" }
    docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 -f "/tmp/$($mig.Name)"
    if ($LASTEXITCODE -ne 0) { throw "migration failed: $version" }
    docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 -c "INSERT INTO schema_migrations (version) VALUES ('$version');"
    if ($LASTEXITCODE -ne 0) { throw "recording schema_migrations failed: $version" }
    Write-Output "APPLIED $version"
}

Write-Output 'MIGRATIONS OK'
