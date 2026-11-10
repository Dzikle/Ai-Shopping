# Read-only active product-identity impact audit. NEVER mutates PostgreSQL.
# Example:
#   ./scripts/run-match-identity-audit.ps1 -Database ai_shopping_m10_diff_py
param(
    [Parameter(Mandatory = $true)][string]$Database,
    [string]$DbUser = '',
    [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
if (-not $DbUser) {
    if (-not (Test-Path '.env')) { throw 'Missing .env: specify -DbUser or create .env' }
    Get-Content '.env' | ForEach-Object {
        if ($_ -match '^\s*POSTGRES_USER\s*=\s*(.*)\s*$') { $DbUser = $Matches[1].Trim('"').Trim("'") }
    }
}
if (-not $DbUser) { throw 'DB user not specified' }
if (-not $OutDir) {
    $tag = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    # Snapshot folders can be root-owned after Docker bind mounts; keep
    # audit reports in the invoking user's home directory by default.
    $OutDir = Join-Path (Join-Path $HOME 'ai-shopping-match-audits') "audit-$tag"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$export = Join-Path $OutDir 'current_active_matches.csv'

docker compose exec -T postgres mkdir -p /tmp/aishopping
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare PostgreSQL container output directory' }
docker compose cp scripts/export-match-identity-audit.sql 'postgres:/tmp/aishopping/export-match-identity-audit.sql'
if ($LASTEXITCODE -ne 0) { throw 'Cannot stage read-only export SQL' }
docker compose exec -T postgres psql -X -U $DbUser -d $Database -v ON_ERROR_STOP=1 -f /tmp/aishopping/export-match-identity-audit.sql
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL read-only export failed' }
docker compose cp 'postgres:/tmp/aishopping/current_active_matches.csv' $export
if ($LASTEXITCODE -ne 0) { throw 'Cannot retrieve active-match export' }
docker compose cp 'postgres:/tmp/aishopping/human_review_matches.csv' (Join-Path $OutDir 'human_review_matches.csv')
if ($LASTEXITCODE -ne 0) { throw 'Cannot retrieve protected human-review export' }

python -B matching/reconciliation_audit.py --input $export --out $OutDir
if ($LASTEXITCODE -ne 0) { throw 'Read-only identity analysis failed' }
Write-Output "READ_ONLY_AUDIT_OK database=$Database out=$OutDir"
Write-Output "Review $OutDir/summary.json, review_required.csv and human_review_matches.csv before any DB change."
