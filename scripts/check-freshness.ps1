# Queries GET /api/v1/freshness, emits a structured JSON summary, and exits
# non-zero (exit code 2) if any retailer has staleStores > 0 or quarantinedRuns > 0
# (unless -AllowStale / -AllowQuarantined is explicitly passed).
param(
    [string]$ApiUrl = 'http://localhost:8080',
    [string]$Retailer = '',
    [int]$StaleThresholdHours = 48,
    [int]$QuarantineWindowDays = 7,
    [switch]$AllowStale,
    [switch]$AllowQuarantined
)
$ErrorActionPreference = 'Stop'

$base = $ApiUrl.TrimEnd('/')
$query = "staleThresholdHours=$StaleThresholdHours&quarantineWindowDays=$QuarantineWindowDays"
if ($Retailer) {
    $query += "&retailer=$([uri]::EscapeDataString($Retailer))"
}
$uri = "$base/api/v1/freshness?$query"

$res = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $uri -TimeoutSec 15
$jsonStr = [System.Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray())
$data = $jsonStr | ConvertFrom-Json

Write-Output ($data | ConvertTo-Json -Depth 8 -Compress)

$failed = $false
if ($data.totalOffers -le 0) {
    $failed = $true
}
if (-not $AllowStale -and $data.totalStaleStores -gt 0) {
    $failed = $true
}
if (-not $AllowQuarantined -and $data.totalQuarantinedRuns -gt 0) {
    $failed = $true
}

if ($failed) {
    exit 2
}
exit 0
