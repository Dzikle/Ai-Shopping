# M8 Operations Monitoring — Prometheus-style metrics exporter.
# Queries PostgreSQL directly (via docker compose postgres) and emits
# metrics in Prometheus text exposition format for scraping/alerting.
#
# Usage:
#   ./scripts/metrics.ps1 -Database ai_shopping
#   ./scripts/metrics.ps1 -Database ai_shopping -OutputFile metrics.txt
#   ./scripts/metrics.ps1 -Database ai_shopping -Json  # JSON output instead
param(
    [string]$Database = '',
    [string]$DbUser = '',
    [switch]$Json,
    [string]$OutputFile = ''
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

function Invoke-Sql($query) {
    $result = docker compose exec -T postgres psql -U $DbUser -d $Database -t -A -c $query
    if ($LASTEXITCODE -ne 0) { throw "SQL query failed: $query" }
    ($result | Out-String).Trim()
}

$metrics = [ordered]@{}

# --- Ingestion runs by status and retailer ---
$runCounts = Invoke-Sql "SELECT source_slug, status, COUNT(*) FROM ingestion_runs GROUP BY source_slug, status ORDER BY source_slug, status;"
foreach ($line in ($runCounts -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 3) { continue }
    $slug = $parts[0].Trim()
    $status = $parts[1].Trim()
    $count = [int]$parts[2].Trim()
    $key = "aishopping_ingestion_runs_total{source_slug=`"$slug`",status=`"$status`"}"
    $metrics[$key] = $count
}

# --- Offers current by retailer ---
$offerCounts = Invoke-Sql 'SELECT r.slug, COUNT(*) FROM offers_current oc JOIN stores s ON s.id=oc.store_id JOIN retailers r ON r.id=s.retailer_id GROUP BY r.slug ORDER BY r.slug;'
foreach ($line in ($offerCounts -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 2) { continue }
    $slug = $parts[0].Trim()
    $count = [int]$parts[1].Trim()
    $key = "aishopping_offers_current_total{retailer_slug=`"$slug`"}"
    $metrics[$key] = $count
}

# --- Price observations total ---
$obsCount = Invoke-Sql "SELECT COUNT(*) FROM price_observations;"
$metrics["aishopping_price_observations_total"] = [int]($obsCount.Trim())

# --- Canonical products ---
$canonicalCount = Invoke-Sql "SELECT COUNT(*) FROM canonical_products;"
$metrics["aishopping_canonical_products_total"] = [int]($canonicalCount.Trim())

# --- Product matches by review status ---
$matchCounts = Invoke-Sql "SELECT review_status, COUNT(*) FROM product_matches GROUP BY review_status ORDER BY review_status;"
foreach ($line in ($matchCounts -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 2) { continue }
    $status = $parts[0].Trim()
    $count = [int]$parts[1].Trim()
    $key = "aishopping_product_matches_total{review_status=`"$status`"}"
    $metrics[$key] = $count
}

# --- Stale stores (no offers updated in > 48h) ---
$staleCounts = Invoke-Sql 'SELECT sub.slug, COUNT(*) FROM (SELECT s.id, r.slug FROM stores s JOIN retailers r ON r.id=s.retailer_id JOIN offers_current oc ON oc.store_id=s.id GROUP BY s.id, r.slug HAVING MAX(oc.published_ts) < now() - INTERVAL ''48 hours'') sub GROUP BY sub.slug ORDER BY sub.slug;'
foreach ($line in ($staleCounts -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 2) { continue }
    $slug = $parts[0].Trim()
    $count = [int]$parts[1].Trim()
    $key = "aishopping_stale_stores_total{retailer_slug=`"$slug`"}"
    $metrics[$key] = $count
}

# --- Quarantined runs (last 7 days) ---
$quarCounts = Invoke-Sql "SELECT source_slug, COUNT(*) FROM ingestion_runs WHERE quarantined = true AND started_at >= now() - INTERVAL '7 days' GROUP BY source_slug ORDER BY source_slug;"
foreach ($line in ($quarCounts -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 2) { continue }
    $slug = $parts[0].Trim()
    $count = [int]$parts[1].Trim()
    $key = "aishopping_quarantined_runs_total{retailer_slug=`"$slug`"}"
    $metrics[$key] = $count
}

# --- Last run timestamp per retailer (Unix epoch) ---
$lastRun = Invoke-Sql "SELECT source_slug, EXTRACT(EPOCH FROM MAX(started_at))::bigint FROM ingestion_runs WHERE status IN ('completed','quarantined') GROUP BY source_slug ORDER BY source_slug;"
foreach ($line in ($lastRun -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 2) { continue }
    $slug = $parts[0].Trim()
    $epoch = $parts[1].Trim()
    $key = "aishopping_pipeline_last_run_timestamp_seconds{retailer_slug=`"$slug`"}"
    $metrics[$key] = [long]$epoch
}

# --- Populated stores ---
$popStores = Invoke-Sql "SELECT COUNT(DISTINCT store_id) FROM offers_current;"
$metrics["aishopping_populated_stores_total"] = [int]($popStores.Trim())

# --- Average run duration (last 7 days) ---
$avgDur = Invoke-Sql "SELECT COALESCE(ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))), 2), 0) FROM ingestion_runs WHERE started_at >= now() - INTERVAL '7 days' AND status IN ('completed','quarantined');"
$metrics["aishopping_pipeline_avg_duration_seconds"] = [double]($avgDur.Trim())

# --- Output ---
if ($Json) {
    $output = $metrics | ConvertTo-Json -Depth 3
} else {
    $lines = @()
    $lines += "# HELP aishopping_ingestion_runs_total Total ingestion runs by retailer and status"
    $lines += "# TYPE aishopping_ingestion_runs_total counter"
    foreach ($k in ($metrics.Keys | Sort-Object)) {
        $lines += "$k $($metrics[$k])"
    }
    $output = $lines -join "`n"
}

if ($OutputFile) {
    $dir = Split-Path -Parent $OutputFile
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Set-Content -LiteralPath $OutputFile -Value $output -Encoding UTF8
    Write-Output "Metrics written to $OutputFile ($($metrics.Count) metrics)"
} else {
    Write-Output $output
}