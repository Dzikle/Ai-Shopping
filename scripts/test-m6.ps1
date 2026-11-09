# M6 integration test:
# 1. Recreates scratch PostgreSQL database (`ai_shopping_m6_test`) and applies
#    migrations V1 + V2 + V3 + V4 (+ V5 since M9).
# 2. Runs the M6 daily pipeline (`scripts/run-daily-pipeline.ps1 -FromSnapshots`)
#    twice to verify end-to-end orchestration and idempotency across Vero,
#    Stokomak, Zito, and KAM + deterministic matching + cross-retailer report.
# 3. Builds and starts the Spring Boot backend container on port $ApiPort.
# 4. Verifies `GET /api/v1/freshness` and `scripts/check-freshness.ps1`:
#    - Store-level staleness detection (`staleThresholdHours=48` -> DEGRADED,
#      `staleThresholdHours=8760` -> FRESH).
# 5. Verifies quarantine handling and alerting (`scripts/alert.ps1`):
#    - Runs a quarantined Zito store capture (`empty_1_1.html`) through the
#      pipeline, asserts `offers_current` remains untouched (5,145 offers
#      preserved across all four retailers), asserts `scripts/alert.ps1`
#      emitted the structured JSON alert, and asserts `/api/v1/freshness`
#      and `scripts/check-freshness.ps1` flag the quarantined run.
# 6. Optional `-LiveSmoke` switch: polite 1-page live scrape of one store per retailer.
param(
    [string]$Database = 'ai_shopping_m6_test',
    [int]$ApiPort = 18086,
    [switch]$LiveSmoke,
    [switch]$KeepDb
)
$ErrorActionPreference = 'Stop'
$psExe = if ($env:OS -eq 'Windows_NT') { 'powershell' } else { 'pwsh' }
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}
$DbUser = $POSTGRES_USER
$DbPass = $POSTGRES_PASSWORD
$DbPort = if ($POSTGRES_PORT) { $POSTGRES_PORT } else { '5432' }

$apiContainer = 'aishopping-m6-backend'
$tempQuarantineDir = 'snapshots/tmp-m6-quarantine-test'
$alertLogFile = Join-Path $PWD 'snapshots/tmp-m6-quarantine-test/alerts.ndjson'

function Cleanup-Resources() {
    docker rm -f $apiContainer 2>$null | Out-Null
    foreach ($p in @(
        $tempQuarantineDir,
        'snapshots/scheduler',
        'snapshots/.leases'
    )) {
        if (Test-Path $p) {
            Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue
        }
    }
    Get-ChildItem 'snapshots' -Directory -Recurse -Filter 'm6-*' -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
    }
    $env:AISHOPPING_ALERT_LOG = $null
}

Cleanup-Resources

try {
    # 1. Start postgres and recreate scratch database
    Write-Output "=== Step 1: Recreate scratch database $Database ==="
    docker compose up -d --wait postgres
    if ($LASTEXITCODE -ne 0) { throw 'postgres failed to start' }

    docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;"
    if ($LASTEXITCODE -ne 0) { throw 'drop test db failed' }
    docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database;"
    if ($LASTEXITCODE -ne 0) { throw 'create test db failed' }

    # 2. Run M6 scheduler unit tests
    Write-Output '=== Step 2: Run M6 scheduler unit tests ==='
    docker run --rm -v "${PWD}:/w" -w /w/adapters/scheduler python:3.12-slim python -B tests.py
    if ($LASTEXITCODE -ne 0) { throw 'scheduler unit tests failed' }

    # 3. Run M6 daily pipeline twice (--from-snapshots) and verify idempotency
    Write-Output '=== Step 3: Run M6 daily pipeline (pass 1 & pass 2 idempotency) ==='
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/run-daily-pipeline.ps1 `
        -Database $Database `
        -RunTag 'm6-replay-test' `
        -FromSnapshots
    if ($LASTEXITCODE -ne 0) { throw 'daily pipeline pass 1 failed' }

    $counts1 = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c "SELECT (SELECT count(*) FROM offers_current), (SELECT count(*) FROM price_observations), (SELECT count(*) FROM canonical_products), (SELECT count(*) FROM ingestion_runs WHERE status = 'completed');"
    if ($LASTEXITCODE -ne 0) { throw 'counts1 query failed' }
    Write-Output "PASS daily_pipeline_pass1 (counts=$counts1)"

    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/run-daily-pipeline.ps1 `
        -Database $Database `
        -RunTag 'm6-replay-test' `
        -FromSnapshots
    if ($LASTEXITCODE -ne 0) { throw 'daily pipeline pass 2 failed' }

    $counts2 = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -F ',' -c "SELECT (SELECT count(*) FROM offers_current), (SELECT count(*) FROM price_observations), (SELECT count(*) FROM canonical_products), (SELECT count(*) FROM ingestion_runs WHERE status = 'completed');"
    if ($LASTEXITCODE -ne 0) { throw 'counts2 query failed' }
    if ($counts1 -ne $counts2) {
        throw "M6 pipeline idempotency violated: $counts1 vs $counts2"
    }
    Write-Output "PASS daily_pipeline_idempotent (counts=$counts2)"

    # 4. Build & start Spring Boot backend container
    Write-Output '=== Step 4: Build & start Spring Boot backend container ==='
    docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test package
    if ($LASTEXITCODE -ne 0) { throw 'maven test package failed' }

    docker run -d --name $apiContainer --add-host=host.docker.internal:host-gateway `
        -p "${ApiPort}:8080" `
        -e "SPRING_DATASOURCE_URL=jdbc:postgresql://host.docker.internal:${DbPort}/${Database}" `
        -e "SPRING_DATASOURCE_USERNAME=${DbUser}" `
        -e "SPRING_DATASOURCE_PASSWORD=${DbPass}" `
        -e "AISHOPPING_OPENSEARCH_URL=http://127.0.0.1:1" `
        -v "${PWD}/backend:/w" -w /w maven:3.9.9-eclipse-temurin-21 `
        java -jar target/ai-shopping-backend-0.3.0-SNAPSHOT.jar | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start backend container' }

    $apiBase = "http://localhost:$ApiPort"
    $serverReady = $false
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $h = Invoke-RestMethod -Uri "$apiBase/api/v1/health" -TimeoutSec 2
            if ($h.status -eq 'UP') { $serverReady = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $serverReady) {
        docker logs --tail 15 $apiContainer
        "::error::backend_not_healthy port=$ApiPort containers=$((docker ps -a --format '{{.Names}} {{.Status}}') -join ' | ')"
        throw 'Backend server did not become healthy'
    }

    function Invoke-Utf8Get($uri) {
        $res = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $uri
        $jsonStr = [System.Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray())
        return ($jsonStr | ConvertFrom-Json)
    }

    # 5. Verify /api/v1/freshness and check-freshness.ps1
    Write-Output '=== Step 5: Verify /api/v1/freshness and scripts/check-freshness.ps1 ==='
    $freshWide = Invoke-Utf8Get "$apiBase/api/v1/freshness?staleThresholdHours=8760&quarantineWindowDays=7"
    if ($freshWide.status -ne 'FRESH' -or $freshWide.totalOffers -ne 5145 -or $freshWide.totalPopulatedStores -ne 9 -or $freshWide.totalStaleStores -ne 0 -or $freshWide.totalQuarantinedRuns -ne 0) {
        throw "Unexpected wide freshness response: $($freshWide | ConvertTo-Json -Compress)"
    }
    $kamRows = @($freshWide.retailers | Where-Object { $_.retailerSlug -eq 'kam' })
    if ($kamRows.Count -ne 1 -or $kamRows[0].offerCount -ne 3249 -or $kamRows[0].seededStoresCount -ne 86) {
        throw "Unexpected KAM freshness row: $($kamRows | ConvertTo-Json -Compress)"
    }
    Write-Output "PASS freshness_endpoint_healthy (status=$($freshWide.status), totalOffers=$($freshWide.totalOffers), populatedStores=$($freshWide.totalPopulatedStores), retailers=$(@($freshWide.retailers).Count))"

    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/check-freshness.ps1 -ApiUrl $apiBase -StaleThresholdHours 8760 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'check-freshness.ps1 should exit 0 when FRESH' }
    Write-Output 'PASS check_freshness_script_pass'

    # Tight threshold (1 hour) against fixture ages must flag all 9 populated stores as stale
    $freshTight = Invoke-Utf8Get "$apiBase/api/v1/freshness?staleThresholdHours=1&quarantineWindowDays=7"
    if ($freshTight.status -ne 'DEGRADED' -or $freshTight.totalStaleStores -ne 9) {
        throw "Expected 9 stale stores under 1h threshold, got status=$($freshTight.status) stale=$($freshTight.totalStaleStores)"
    }
    Write-Output "PASS freshness_stale_store_detection (staleStores=$($freshTight.totalStaleStores))"

    # 6. Quarantine detection, alerting, and data preservation test
    Write-Output '=== Step 6: Verify quarantine refusal, alerting, and offer preservation ==='
    $badZitoFixtureDir = 'snapshots/tmp-m6-quarantine-test/zito_empty'
    New-Item -ItemType Directory -Force -Path $badZitoFixtureDir | Out-Null
    Copy-Item -LiteralPath 'tests/fixtures/zito/empty_1_1.html' -Destination (Join-Path $badZitoFixtureDir '1_1.html')
    $env:AISHOPPING_ALERT_LOG = $alertLogFile

    $ErrorActionPreference = 'Continue'
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/run-daily-pipeline.ps1 `
        -Database $Database `
        -RunTag 'm6-quarantine-test' `
        -Retailers 'zito' `
        -FromSnapshots `
        -SnapshotMap "zito=$badZitoFixtureDir"
    $qPipeExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    if ($qPipeExit -ne 2) {
        throw "Expected pipeline exit code 2 on quarantined run, got $qPipeExit"
    }
    Write-Output 'PASS pipeline_quarantine_exit_code_2'

    # Verify offers_current was NOT deleted or corrupted (still 5,145 offers)
    $offersAfterQ = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -c "SELECT count(*) FROM offers_current;"
    if ($offersAfterQ -ne '5145') {
        throw "AGENTS.md #6 violated: offers_current changed after quarantined run ($offersAfterQ != 5145)"
    }
    Write-Output 'PASS offers_preserved_on_quarantine (offers_current=5145)'

    # Verify alert.ps1 wrote structured JSON alert
    if (-not (Test-Path $alertLogFile)) {
        throw "Expected alert log file at $alertLogFile"
    }
    $alertLines = @(Get-Content $alertLogFile | Where-Object { $_.Trim() -ne '' })
    if ($alertLines.Count -lt 1) {
        throw 'Alert log file is empty'
    }
    $alertObj = $alertLines[0] | ConvertFrom-Json
    if ($alertObj.retailer -ne 'zito' -or $alertObj.level -ne 'error' -or $alertObj.runKey -ne 'm6-quarantine-test-zito') {
        throw "Unexpected alert payload: $($alertLines[0])"
    }
    Write-Output "PASS alert_hook_emitted_json (retailer=$($alertObj.retailer), runKey=$($alertObj.runKey))"

    # Verify /api/v1/freshness now reports totalQuarantinedRuns == 1 and status == DEGRADED
    $freshAfterQ = Invoke-Utf8Get "$apiBase/api/v1/freshness?staleThresholdHours=8760&quarantineWindowDays=7"
    if ($freshAfterQ.status -ne 'DEGRADED' -or $freshAfterQ.totalQuarantinedRuns -ne 1 -or $freshAfterQ.quarantinedRuns[0].runKey -ne 'm6-quarantine-test-zito') {
        throw "Expected quarantined run in /api/v1/freshness, got: $($freshAfterQ | ConvertTo-Json -Compress)"
    }
    Write-Output "PASS freshness_reports_quarantined_run (quarantinedRuns=$($freshAfterQ.totalQuarantinedRuns))"

    $ErrorActionPreference = 'Continue'
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/check-freshness.ps1 -ApiUrl $apiBase -StaleThresholdHours 8760 | Out-Null
    $checkQExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($checkQExit -eq 0) {
        throw 'check-freshness.ps1 should exit non-zero when quarantinedRuns > 0'
    }
    Write-Output 'PASS check_freshness_fails_on_quarantine'

    # 7. Optional live smoke test against 1 store per retailer
    if ($LiveSmoke) {
        Write-Output '=== Step 7: Live 1-store smoke test ==='
        & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/run-daily-pipeline.ps1 `
            -Database $Database `
            -RunTag 'm6-live-smoke' `
            -Live `
            -StoresMap 'vero=89,stokomak=1,zito=2,kam=73' `
            -MaxPages 1
        if ($LASTEXITCODE -ne 0) { throw 'live smoke pipeline failed' }
        Write-Output 'PASS live_smoke_pipeline'
    }

} catch {
    "::error::M6-TEST-FAILED: $($_.Exception.Message)"
    Write-Output "=== ERROR CAUGHT: Dumping $apiContainer logs ==="
    docker logs --tail 80 $apiContainer 2>&1 | Out-String | Write-Output
    throw
} finally {
    Cleanup-Resources
    if (-not $KeepDb) {
        docker compose exec -T postgres psql -U $DbUser -d $POSTGRES_DB -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database;" 2>$null | Out-Null
    }
}

Write-Output 'M6 TEST OK'
