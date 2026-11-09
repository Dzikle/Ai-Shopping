# M9 integration test: replay the KAM Market fixtures through the M6 scheduler
# (kam registered as fourth retailer), load via scripts/load-records.ps1 into a
# scratch database, verify idempotency across two passes and assert record
# counts, coordinates columns (V5), promotions and quarantine-safe loading.
param(
    [string]$Database = 'ai_shopping_m9_test',
    [switch]$KeepDb
)
$ErrorActionPreference = 'Stop'
$psExe = if ($env:OS -eq 'Windows_NT') { 'powershell' } else { 'pwsh' }
trap { "::error::M9-TEST-FAILED: $($_.Exception.Message)"; exit 1 }
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
$DbUser = $POSTGRES_USER

function Invoke-Assert($name, $sql) {
    $result = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -v ON_ERROR_STOP=1 -c $sql
    if ($LASTEXITCODE -ne 0) { throw "assert query failed: $name" }
    if ($result -ne '1') { throw "ASSERT FAILED: $name (got $result)" }
    Write-Output "PASS $name"
}

function Get-DbCounts() {
    $q = @"
SELECT (SELECT count(*) FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam'),
       (SELECT count(*) FROM price_observations po JOIN stores s ON s.id = po.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam'),
       (SELECT count(*) FROM promotions p JOIN retailer_products rp ON rp.id = p.retailer_product_id JOIN retailers r ON r.id = rp.retailer_id WHERE r.slug = 'kam'),
       (SELECT count(*) FROM raw_snapshots WHERE source_slug = 'kam'),
       (SELECT count(*) FROM retailer_products rp JOIN retailers r ON r.id = rp.retailer_id WHERE r.slug = 'kam'),
       (SELECT count(*) FROM ingestion_runs WHERE source_slug = 'kam' AND status = 'completed');
"@
    $res = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c $q
    if ($LASTEXITCODE -ne 0) { throw 'counts query failed' }
    return $res
}

# 1. Start postgres only and apply migrations V1..V5
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'postgres failed to start' }

docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
if ($LASTEXITCODE -ne 0) { throw 'drop test db failed' }
docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database;"
if ($LASTEXITCODE -ne 0) { throw 'create test db failed' }

& $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/apply-migrations.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'migrations failed' }

Invoke-Assert 'v5_kam_retailer_present' "SELECT CASE WHEN count(*) = 1 THEN 1 ELSE 0 END FROM retailers WHERE slug = 'kam';"
Invoke-Assert 'v5_kam_stores_86' "SELECT CASE WHEN count(*) = 86 THEN 1 ELSE 0 END FROM stores WHERE retailer_id = (SELECT id FROM retailers WHERE slug = 'kam');"
Invoke-Assert 'v5_kam_coordinates_seeded' "SELECT CASE WHEN count(*) = 86 THEN 1 ELSE 0 END FROM stores WHERE retailer_id = (SELECT id FROM retailers WHERE slug = 'kam') AND latitude IS NOT NULL AND longitude IS NOT NULL;"
Invoke-Assert 'v5_coordinates_column_exists' "SELECT CASE WHEN count(*) = 1 THEN 1 ELSE 0 END FROM information_schema.columns WHERE table_name = 'stores' AND column_name = 'latitude';"

# 2. Scheduler replay pass for KAM only (single --once run)
$date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$runTag = 'm9-kam-replay'

function Invoke-SchedulerPass() {
    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/scheduler/cli.py --once --from-snapshots --retailers kam --run-tag $runTag
    if ($LASTEXITCODE -ne 0) { throw 'scheduler cli failed' }
}

Invoke-SchedulerPass
$manifestPath = "snapshots/scheduler/$date/$runTag/scheduler_manifest.json"
if (-not (Test-Path $manifestPath)) { throw "scheduler manifest not found: $manifestPath" }
$schedManifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$kamRes = $schedManifest.retailers | Where-Object { $_.retailer -eq 'kam' }
if ($kamRes.status -ne 'completed') { throw "scheduler kam run status: $($kamRes.status)" }
if ($kamRes.quarantined) { throw 'scheduler kam run quarantined' }
Write-Output "PASS scheduler_kam_replay (rows_stored=$($kamRes.rows_stored))"

# 3. Loader pass 1
& $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 `
    -OutDir $kamRes.out_dir `
    -RunKey $kamRes.run_key `
    -SourceSlug kam `
    -Database $Database `
    -WorkerId $schedManifest.worker_id
if ($LASTEXITCODE -ne 0) { throw 'kam load failed' }

$counts1 = Get-DbCounts
Write-Output "COUNTS_AFTER_FIRST_PASS: $counts1"

Invoke-Assert 'kam_offers_3249' "SELECT CASE WHEN (SELECT count(*) FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam') = 3249 THEN 1 ELSE 0 END;"
Invoke-Assert 'kam_snapshots_2' "SELECT CASE WHEN count(*) = 2 THEN 1 ELSE 0 END FROM raw_snapshots WHERE source_slug = 'kam';"
Invoke-Assert 'kam_two_stores_with_offers' "SELECT CASE WHEN count(DISTINCT s.external_key) = 2 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam';"
Invoke-Assert 'kam_products_1853' "SELECT CASE WHEN count(*) = 1853 THEN 1 ELSE 0 END FROM retailer_products rp JOIN retailers r ON r.id = rp.retailer_id WHERE r.slug = 'kam';"
Invoke-Assert 'kam_run_completed' "SELECT CASE WHEN count(*) = 1 THEN 1 ELSE 0 END FROM ingestion_runs WHERE run_key = '$runTag-kam' AND status = 'completed' AND rows_stored = 3258;"
Invoke-Assert 'kam_promotions_79' "SELECT CASE WHEN count(*) = 79 THEN 1 ELSE 0 END FROM promotions p JOIN retailer_products rp ON rp.id = p.retailer_product_id JOIN retailers r ON r.id = rp.retailer_id WHERE r.slug = 'kam';"
Invoke-Assert 'kam_promo_dates_populated' "SELECT CASE WHEN count(*) = 79 THEN 1 ELSE 0 END FROM promotions p JOIN retailer_products rp ON rp.id = p.retailer_product_id JOIN retailers r ON r.id = rp.retailer_id WHERE r.slug = 'kam' AND p.starts_on IS NOT NULL AND p.ends_on IS NOT NULL;"

# 4. Second identical pass (idempotency through parser, scheduler and loader)
Invoke-SchedulerPass
$kamRes2 = (Get-Content "snapshots/scheduler/$date/$runTag/scheduler_manifest.json" -Raw | ConvertFrom-Json).retailers | Where-Object { $_.retailer -eq 'kam' }
& $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 `
    -OutDir $kamRes2.out_dir `
    -RunKey $kamRes2.run_key `
    -SourceSlug kam `
    -Database $Database `
    -WorkerId $schedManifest.worker_id
if ($LASTEXITCODE -ne 0) { throw 'kam load pass 2 failed' }

$counts2 = Get-DbCounts
Write-Output "COUNTS_AFTER_SECOND_PASS: $counts2"
if ($counts1 -ne $counts2) { throw "M9 idempotency violated: $counts1 vs $counts2" }

# 5. Price identity: unit prices, availability mapping sanity
Invoke-Assert 'kam_unit_prices_populated' "SELECT CASE WHEN count(*) = 2248 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam' AND oc.unit_price IS NOT NULL;"
Invoke-Assert 'kam_published_ts_present' "SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'kam' AND oc.published_ts IS NULL;"

if (-not $KeepDb) {
    docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
    if ($LASTEXITCODE -ne 0) { Write-Output 'WARNING: test db cleanup failed' }
}

Write-Output 'M9 TEST OK'
