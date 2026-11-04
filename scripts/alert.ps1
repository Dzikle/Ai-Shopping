# Pluggable M6 alerting hook (PowerShell).
# Accepts structured parameters or a raw JSON payload, writes a single-line JSON
# alert object to stderr (for CI/log capture), optionally appends to
# $env:AISHOPPING_ALERT_LOG, and optionally POSTs to $env:AISHOPPING_ALERT_WEBHOOK_URL.
param(
    [ValidateSet('info', 'warn', 'error')]
    [string]$Level = 'error',
    [string]$Retailer = 'unknown',
    [string]$Store = 'unknown',
    [string]$Message = '',
    [string]$RunKey = '',
    [string]$PayloadJson = ''
)
$ErrorActionPreference = 'Stop'

if ($PayloadJson) {
    $obj = $PayloadJson | ConvertFrom-Json
    $alert = [ordered]@{
        timestamp = if ($obj.timestamp) { $obj.timestamp } else { (Get-Date).ToUniversalTime().ToString('o') }
        level     = if ($obj.level) { $obj.level } else { $Level }
        retailer  = if ($obj.retailer) { $obj.retailer } else { $Retailer }
        store     = if ($obj.store) { "$($obj.store)" } else { $Store }
        message   = if ($obj.message) { $obj.message } else { $Message }
        runKey    = if ($obj.runKey) { $obj.runKey } else { $RunKey }
    }
} else {
    $alert = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        level     = $Level
        retailer  = $Retailer
        store     = $Store
        message   = $Message
        runKey    = $RunKey
    }
}

$jsonLine = $alert | ConvertTo-Json -Compress
[Console]::Error.WriteLine($jsonLine)

if ($env:AISHOPPING_ALERT_LOG) {
    $logDir = Split-Path -Parent $env:AISHOPPING_ALERT_LOG
    if ($logDir -and -not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -LiteralPath $env:AISHOPPING_ALERT_LOG -Value $jsonLine -Encoding UTF8
}

if ($env:AISHOPPING_ALERT_WEBHOOK_URL) {
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonLine)
        Invoke-WebRequest -UseBasicParsing -Method Post -Uri $env:AISHOPPING_ALERT_WEBHOOK_URL `
            -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 10 | Out-Null
    } catch {
        [Console]::Error.WriteLine("ALERT_WEBHOOK_ERROR: $($_.Exception.Message)")
    }
}
