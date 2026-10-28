# M1 integration test: replay the captured Vero fixtures through the adapter
# and loader into a scratch database, then verify idempotent replay and data
# integrity. Uses cached docker images; no OpenSearch required.
param(
    [string]$Database = 'ai_shopping_test',
    [switch]$KeepDb
)
$ErrorActionPreference = 'Stop'
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

# 1. Start postgres only
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'postgres failed to start' }

# 2. Recreate scratch database
docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
if ($LASTEXITCODE -ne 0) { throw 'drop test db failed' }
docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database;"
if ($LASTEXITCODE -ne 0) { throw 'create test db failed' }

# 3. Apply migrations
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/apply-migrations.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'migrations failed' }

# 4. Adapter replay (unit container, offline, fixture-driven; default snapshot layout)
$runKey = 'm1-replay-test'
$date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$outDir = "snapshots/vero/$date/$runKey"
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/vero/cli.py --from-snapshots tests/fixtures/vero --out $outDir --run-key $runKey
if ($LASTEXITCODE -ne 0) { throw 'adapter replay failed' }

# 5. First load
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 -OutDir $outDir -RunKey $runKey -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'first load failed' }

$counts1 = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c "SELECT (SELECT count(*) FROM price_observations), (SELECT count(*) FROM offers_current), (SELECT count(*) FROM promotions), (SELECT count(*) FROM raw_snapshots), (SELECT count(*) FROM retailer_products);"
if ($LASTEXITCODE -ne 0) { throw 'counts query failed' }
Write-Output "COUNTS_AFTER_FIRST_LOAD: $counts1"

# 6. Idempotent second replay + load (same run key, re-generated snapshot dir)
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/vero/cli.py --from-snapshots tests/fixtures/vero --out $outDir --run-key $runKey
if ($LASTEXITCODE -ne 0) { throw 'second adapter replay failed' }
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 -OutDir $outDir -RunKey $runKey -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'second load failed' }

$counts2 = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c "SELECT (SELECT count(*) FROM price_observations), (SELECT count(*) FROM offers_current), (SELECT count(*) FROM promotions), (SELECT count(*) FROM raw_snapshots), (SELECT count(*) FROM retailer_products);"
if ($LASTEXITCODE -ne 0) { throw 'second counts query failed' }
Write-Output "COUNTS_AFTER_SECOND_LOAD: $counts2"
if ($counts1 -ne $counts2) { throw "idempotency violated: $counts1 vs $counts2" }

# 7. Integrity asserts
Invoke-Assert 'observation_count_is_1000' "SELECT CASE WHEN count(*) = 1000 THEN 1 ELSE 0 END FROM price_observations;"
Invoke-Assert 'no_duplicate_observations' "SELECT CASE WHEN count(*) = (SELECT count(*) FROM (SELECT DISTINCT retailer_product_id, store_id, published_ts, price_current FROM price_observations) d) THEN 1 ELSE 0 END FROM price_observations;"
Invoke-Assert 'published_ts_roundtrip' "SELECT CASE WHEN count(*) = 1000 THEN 1 ELSE 0 END FROM price_observations WHERE published_ts = '2026-10-28 07:02:00+00'::timestamptz;"
Invoke-Assert 'offers_match_observations' "SELECT CASE WHEN (SELECT count(*) FROM offers_current) = (SELECT count(DISTINCT (store_id, retailer_product_id)) FROM price_observations) THEN 1 ELSE 0 END;"
Invoke-Assert 'promotions_present' "SELECT CASE WHEN count(*) > 0 THEN 1 ELSE 0 END FROM promotions;"
Invoke-Assert 'snapshots_linked' "SELECT CASE WHEN count(*) = 1000 THEN 1 ELSE 0 END FROM price_observations WHERE raw_snapshot_id IS NOT NULL;"
Invoke-Assert 'stores_seeded_17' "SELECT CASE WHEN count(*) = 17 THEN 1 ELSE 0 END FROM stores;"
Invoke-Assert 'run_completed' "SELECT CASE WHEN count(*) = 1 THEN 1 ELSE 0 END FROM ingestion_runs WHERE run_key = 'm1-replay-test' AND status = 'completed' AND rows_stored = 1000;"

# 8. Sample record for the evidence log
docker compose exec -T postgres psql -U $DbUser -d $Database -c "SELECT rp.listing_name, o.price_current, o.unit_price, o.availability, o.published_ts FROM offers_current o JOIN retailer_products rp ON rp.id = o.retailer_product_id ORDER BY rp.listing_name LIMIT 3;"

if (-not $KeepDb) {
    docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
    if ($LASTEXITCODE -ne 0) { Write-Output 'WARNING: test db cleanup failed' }
}

Write-Output 'M1 TEST OK'
