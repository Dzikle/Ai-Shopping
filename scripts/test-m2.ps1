# M2 integration test: replay Vero + Stokomak + Zito fixtures through their
# adapters and loaders into a scratch database, run deterministic matching +
# review-queue generation, verify idempotency across all three retailers and
# matcher tables, and run the cross-retailer comparison report.
param(
    [string]$Database = 'ai_shopping_m2_test',
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

function Get-DbCounts() {
    $q = @"
SELECT (SELECT count(*) FROM price_observations),
       (SELECT count(*) FROM offers_current),
       (SELECT count(*) FROM promotions),
       (SELECT count(*) FROM raw_snapshots),
       (SELECT count(*) FROM retailer_products),
       (SELECT count(*) FROM canonical_products),
       (SELECT count(*) FROM product_matches WHERE review_status = 'auto_accepted'),
       (SELECT count(*) FROM product_matches WHERE review_status = 'pending_review');
"@
    $res = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c $q
    if ($LASTEXITCODE -ne 0) { throw 'counts query failed' }
    return $res
}

# 1. Start postgres only
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'postgres failed to start' }

# 2. Recreate scratch database
docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
if ($LASTEXITCODE -ne 0) { throw 'drop test db failed' }
docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database;"
if ($LASTEXITCODE -ne 0) { throw 'create test db failed' }

# 3. Apply migrations (V1 + V2)
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/apply-migrations.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'migrations failed' }

$date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$veroRunKey = 'm2-vero-replay'
$stokoRunKey = 'm2-stokomak-replay'
$zitoRunKey = 'm2-zito-replay'
$veroOut = "snapshots/vero/$date/$veroRunKey"
$stokoOut = "snapshots/stokomak/$date/$stokoRunKey"
$zitoOut = "snapshots/zito/$date/$zitoRunKey"
$matchOut = "snapshots/matching/$date/m2-match-replay"

function Invoke-PipelinePass() {
    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/vero/cli.py --from-snapshots tests/fixtures/vero --out $veroOut --run-key $veroRunKey
    if ($LASTEXITCODE -ne 0) { throw 'vero replay failed' }

    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/stokomak/cli.py --retailer stokomak --from-snapshots tests/fixtures/stokomak --out $stokoOut --run-key $stokoRunKey
    if ($LASTEXITCODE -ne 0) { throw 'stokomak replay failed' }

    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/stokomak/cli.py --retailer zito --from-snapshots tests/fixtures/zito --out $zitoOut --run-key $zitoRunKey
    if ($LASTEXITCODE -ne 0) { throw 'zito replay failed' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 -OutDir $veroOut -RunKey $veroRunKey -SourceSlug vero -Database $Database
    if ($LASTEXITCODE -ne 0) { throw 'vero load failed' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 -OutDir $stokoOut -RunKey $stokoRunKey -SourceSlug stokomak -Database $Database
    if ($LASTEXITCODE -ne 0) { throw 'stokomak load failed' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-records.ps1 -OutDir $zitoOut -RunKey $zitoRunKey -SourceSlug zito -Database $Database
    if ($LASTEXITCODE -ne 0) { throw 'zito load failed' }

    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B matching/cli.py --run-dirs "$veroOut,$stokoOut,$zitoOut" --out $matchOut
    if ($LASTEXITCODE -ne 0) { throw 'matching cli failed' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load-matches.ps1 -OutDir $matchOut -Database $Database
    if ($LASTEXITCODE -ne 0) { throw 'load-matches failed' }
}

# 4. First full pass
Invoke-PipelinePass
$counts1 = Get-DbCounts
Write-Output "COUNTS_AFTER_FIRST_PASS: $counts1"

# 5. Second identical pass (idempotency verification across all 3 retailers + matcher)
Invoke-PipelinePass
$counts2 = Get-DbCounts
Write-Output "COUNTS_AFTER_SECOND_PASS: $counts2"
if ($counts1 -ne $counts2) { throw "M2 idempotency violated: $counts1 vs $counts2" }

# 6. Integrity and ADR-0003 asserts
Invoke-Assert 'three_retailers_loaded' "SELECT CASE WHEN count(DISTINCT r.slug) = 3 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id;"
Invoke-Assert 'stokomak_three_stores_loaded' "SELECT CASE WHEN count(DISTINCT s.external_key) = 3 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'stokomak';"
Invoke-Assert 'zito_three_stores_loaded' "SELECT CASE WHEN count(DISTINCT s.external_key) = 3 THEN 1 ELSE 0 END FROM offers_current oc JOIN stores s ON s.id = oc.store_id JOIN retailers r ON r.id = s.retailer_id WHERE r.slug = 'zito';"
Invoke-Assert 'cross_retailer_exact_matches_ge_5' @"
SELECT CASE WHEN count(*) >= 5 THEN 1 ELSE 0 END FROM (
    SELECT pm.canonical_product_id
    FROM product_matches pm
    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
    WHERE pm.review_status IN ('auto_accepted', 'approved')
    GROUP BY pm.canonical_product_id
    HAVING count(DISTINCT rp.retailer_id) >= 2
) x;
"@
Invoke-Assert 'vero_stokomak_overlap_present' @"
SELECT CASE WHEN count(*) >= 1 THEN 1 ELSE 0 END FROM (
    SELECT pm.canonical_product_id
    FROM product_matches pm
    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
    JOIN retailers r ON r.id = rp.retailer_id
    WHERE pm.review_status IN ('auto_accepted', 'approved')
      AND r.slug IN ('vero', 'stokomak')
    GROUP BY pm.canonical_product_id
    HAVING count(DISTINCT r.slug) = 2
) x;
"@
Invoke-Assert 'vero_zito_overlap_present' @"
SELECT CASE WHEN count(*) >= 1 THEN 1 ELSE 0 END FROM (
    SELECT pm.canonical_product_id
    FROM product_matches pm
    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
    JOIN retailers r ON r.id = rp.retailer_id
    WHERE pm.review_status IN ('auto_accepted', 'approved')
      AND r.slug IN ('vero', 'zito')
    GROUP BY pm.canonical_product_id
    HAVING count(DISTINCT r.slug) = 2
) x;
"@
Invoke-Assert 'stokomak_zito_overlap_present' @"
SELECT CASE WHEN count(*) >= 1 THEN 1 ELSE 0 END FROM (
    SELECT pm.canonical_product_id
    FROM product_matches pm
    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
    JOIN retailers r ON r.id = rp.retailer_id
    WHERE pm.review_status IN ('auto_accepted', 'approved')
      AND r.slug IN ('stokomak', 'zito')
    GROUP BY pm.canonical_product_id
    HAVING count(DISTINCT r.slug) = 2
) x;
"@
Invoke-Assert 'stage2_review_queue_present' "SELECT CASE WHEN count(*) > 0 THEN 1 ELSE 0 END FROM product_matches WHERE review_status = 'pending_review' AND method = 'candidate_token_size_v1';"
Invoke-Assert 'no_silent_merges_without_evidence' "SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM product_matches WHERE evidence = '{}'::jsonb OR confidence IS NULL;"
Invoke-Assert 'active_identity_unique_per_retailer_product' @"
SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM (
    SELECT retailer_product_id
    FROM product_matches
    WHERE review_status IN ('auto_accepted', 'approved')
    GROUP BY retailer_product_id
    HAVING count(*) > 1
) dup;
"@

# 7. Cross-retailer comparison and history report
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/report-cross-retailer.ps1 -Database $Database
if ($LASTEXITCODE -ne 0) { throw 'report-cross-retailer failed' }

if (-not $KeepDb) {
    docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
    if ($LASTEXITCODE -ne 0) { Write-Output 'WARNING: test db cleanup failed' }
}

Write-Output 'M2 TEST OK'
