# M10 differential regression: Spring Boot jar vs FastAPI on identical data.
# 1. mvn -B test package (Java suite still green on this branch).
# 2. Two scratch databases (javaDB + pythonDB) with migrations; run the daily
#    pipeline from consumer snapshots into the java DB; clone -> python DB.
# 3. Reindex OpenSearch from the java DB (shared, read-only for search).
# 4. Start java jar (port 18088) and uvicorn (port 18089).
# 5. Run backend_py/tools/diff_harness.py and report PASS/FAIL per pair.
# 6. Cleanup containers + DBs.

param(
    [int]$JavaPort = 18088,
    [int]$PythonPort = 18089,
    [string]$JavaDb = 'ai_shopping_m10_diff_java',
    [string]$PythonDb = 'ai_shopping_m10_diff_py',
    [switch]$SkipCleanup,
    [switch]$KeepDatabases
)

$ErrorActionPreference = 'Continue'
$psExe = (Get-Command powershell.exe).Source

# Load .env
$Script:DbUser = $null; $Script:DbPass = $null; $Script:DbDefault = $null; $Script:OsUrl = $null
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*POSTGRES_USER=(.+)\s*$')    { $Script:DbUser = $Matches[1].Trim() }
    if ($line -match '^\s*POSTGRES_PASSWORD=(.+)\s*$'){ $Script:DbPass = $Matches[1].Trim() }
    if ($line -match '^\s*POSTGRES_DB=(.+)\s*$')      { $Script:DbDefault = $Matches[1].Trim() }
    if ($line -match '^\s*OPENSEARCH_URL=(.+)\s*$')   { $Script:OsUrl = $Matches[1].Trim() }
}
if (-not $Script:DbUser)   { throw 'POSTGRES_USER missing in .env' }
if (-not $Script:DbPass)   { throw 'POSTGRES_PASSWORD missing in .env' }
if (-not $Script:DbDefault){ throw 'POSTGRES_DB missing in .env' }
if (-not $Script:OsUrl)    { $Script:OsUrl = 'http://localhost:9200' }
$DbPort = 5432

function Invoke-Sql([string]$Database, [string]$Sql) {
    docker compose exec -T postgres psql -U $DbUser -d $Database -v ON_ERROR_STOP=1 -c "$Sql"
    if ($LASTEXITCODE -ne 0) { throw "sql failed ($Database): $Sql" }
}

$apiContainer = 'ai-shopping-m10-diff-api'
$pyApiContainer = 'ai-shopping-m10-diff-py-api'
$uvicornJob = $null
try {
    Write-Output '=== Step 1: mvn -B test package (Java suite) ==='
    docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test package
    if ($LASTEXITCODE -ne 0) { throw 'java build failed' }

    Write-Output '=== Step 2: Preparing databases ==='
    Invoke-Sql $DbDefault "DROP DATABASE IF EXISTS $JavaDb WITH (FORCE);"
    Invoke-Sql $DbDefault "CREATE DATABASE $JavaDb;"
    Invoke-Sql $DbDefault "DROP DATABASE IF EXISTS $PythonDb WITH (FORCE);"
    Invoke-Sql $DbDefault "CREATE DATABASE $PythonDb;"

    Write-Output "=== Step 3: Migrations + pipeline ($JavaDb) ==="
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/apply-migrations.ps1 -Database $JavaDb -DbUser $DbUser
    if ($LASTEXITCODE -ne 0) { throw 'migrations failed' }
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/run-daily-pipeline.ps1 -Database $JavaDb -FromSnapshots
    if ($LASTEXITCODE -ne 0) { throw 'pipeline failed' }

    Write-Output '=== Step 4: Clone java DB -> python DB ==='
    docker exec aoshopping-postgres-1 sh -c "pg_dump -U $DbUser $JavaDb | psql -U $DbUser -d $PythonDb -v ON_ERROR_STOP=1 -q"
    if ($LASTEXITCODE -ne 0) { throw 'clone failed' }

    Write-Output '=== Step 5: Reindex OpenSearch from java DB ==='
    & $psExe -NoProfile -ExecutionPolicy Bypass -File scripts/reindex-opensearch.ps1 -Database $JavaDb -DbUser $DbUser -OpenSearchUrl $OsUrl -VersionTag 'v1_m10_diff'
    if ($LASTEXITCODE -ne 0) { throw 'reindex failed' }

    Write-Output "=== Step 6: Start java jar (port $JavaPort) ==="
    docker rm -f $apiContainer 2>$null | Out-Null
    docker run -d --name $apiContainer `
        --add-host=host.docker.internal:host-gateway `
        -p "${JavaPort}:8080" `
        -e "SPRING_DATASOURCE_URL=jdbc:postgresql://host.docker.internal:${DbPort}/${JavaDb}" `
        -e "SPRING_DATASOURCE_USERNAME=${DbUser}" `
        -e "SPRING_DATASOURCE_PASSWORD=${DbPass}" `
        -e "AISHOPPING_OPENSEARCH_URL=http://host.docker.internal:9200" `
        -e "SERVER_PORT=8080" `
        -v "${PWD}/backend:/w" -w /w maven:3.9.9-eclipse-temurin-21 `
        java -jar target/ai-shopping-backend-0.3.0-SNAPSHOT.jar | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start java container' }

    Write-Output "=== Step 6b: Start uvicorn container (port $PythonPort) ==="
    docker rm -f $pyApiContainer 2>$null | Out-Null
    docker run -d --name $pyApiContainer `
        --add-host=host.docker.internal:host-gateway `
        -p "${PythonPort}:8000" `
        -e "POSTGRES_HOST=host.docker.internal" `
        -e "POSTGRES_PORT=${DbPort}" `
        -e "POSTGRES_DB=${PythonDb}" `
        -e "POSTGRES_USER=${DbUser}" `
        -e "POSTGRES_PASSWORD=${DbPass}" `
        -e "OPENSEARCH_URL=http://host.docker.internal:9200" `
        -v "${PWD}/backend_py:/w" -v aoshopping-uv-cache:/root/.cache/uv -v aoshopping-uv-venv:/w/.venv -w /w `
        ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
        uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'failed to start python container' }

    Write-Output '=== Step 7: Wait for both services ==='
    $javaReady = $false; $pyReady = $false
    for ($i = 0; $i -lt 240; $i++) {
        if (-not $javaReady) {
            try { Invoke-RestMethod "http://localhost:$JavaPort/api/v1/health" | Out-Null; $javaReady = $true } catch {}
        }
        if (-not $pyReady) {
            try { Invoke-RestMethod "http://localhost:$PythonPort/api/v1/health" | Out-Null; $pyReady = $true } catch {}
        }
        if ($javaReady -and $pyReady) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $javaReady) { throw 'java service did not become ready' }
    if (-not $pyReady) {
        docker logs --tail 30 $pyApiContainer
        throw 'python service did not become ready'
    }
    # Let the new container's connection pool settle before the corpus starts
    # (first-request DB failures only appear in the seconds after boot).
    Start-Sleep -Seconds 10
    if (-not $javaReady) { throw 'java service did not become ready' }
    if (-not $pyReady) {
        docker logs --tail 30 $pyApiContainer
        throw 'python service did not become ready'
    }

    Write-Output '=== Step 8: Differential corpus ==='
    docker run --rm --add-host=host.docker.internal:host-gateway `
        -e "PYTHONIOENCODING=utf-8" `
        -v "${PWD}/backend_py:/w" -v aoshopping-uv-cache:/root/.cache/uv -v aoshopping-uv-venv:/w/.venv -w /w `
        ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
        uv run python tools/diff_harness.py `
        --java "http://host.docker.internal:$JavaPort" `
        --python "http://host.docker.internal:$PythonPort"
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) { throw "diff harness reported failures (exit=$exitCode)" }
    Write-Output 'DIFF-SUITE PASS'
    exit 0
}
finally {
    if (-not $SkipCleanup) {
        Write-Output '=== Cleanup ==='
        docker rm -f $apiContainer 2>$null | Out-Null
        docker rm -f $pyApiContainer 2>$null | Out-Null
        if (-not $KeepDatabases) {
            try { Invoke-Sql $DbDefault "DROP DATABASE IF EXISTS $JavaDb WITH (FORCE);" } catch {}
            try { Invoke-Sql $DbDefault "DROP DATABASE IF EXISTS $PythonDb WITH (FORCE);" } catch {}
        }
    }
}
