# M7 Stage-2 Review Queue CLI (PowerShell).
# Lists pending_review product match candidates and supports approve/reject
# decisions with audit trail (reviewed_by, reviewed_at, review_notes).
#
# Examples:
#   # List pending review candidates
#   ./scripts/review-queue.ps1 --ApiUrl http://localhost:8080 --List
#
#   # Approve a match
#   ./scripts/review-queue.ps1 --ApiUrl http://localhost:8080 --Approve 42 --ReviewedBy operator@example.com --Notes "Confirmed same product"
#
#   # Reject a match
#   ./scripts/review-queue.ps1 --ApiUrl http://localhost:8080 --Reject 43 --ReviewedBy operator@example.com --Notes "Different pack size"
param(
    [string]$ApiUrl = 'http://localhost:8080',
    [switch]$List,
    [int]$Approve = 0,
    [int]$Reject = 0,
    [string]$ReviewedBy = '',
    [string]$ReviewNotes = '',
    [int]$Limit = 25
)
$ErrorActionPreference = 'Stop'

Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Variable -Name $Matches[1] -Value $Matches[2] -Scope Script
    }
}

$base = $ApiUrl.TrimEnd('/')

function Invoke-Get($path) {
    $uri = "$base$path"
    $res = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $uri -TimeoutSec 15
    $jsonStr = [System.Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray())
    $jsonStr | ConvertFrom-Json -Depth 10
}

function Invoke-Post($path, $body) {
    $uri = "$base$path"
    $jsonBody = $body | ConvertTo-Json -Depth 10
    $res = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $uri -ContentType 'application/json; charset=utf-8' -Body $jsonBody -TimeoutSec 15
    $jsonStr = [System.Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray())
    $jsonStr | ConvertFrom-Json -Depth 10
}

if ($List) {
    $queue = Invoke-Get "/api/v1/matches/review-queue?limit=$Limit"
    Write-Output ("STAGE-2 REVIEW QUEUE (pending_review, limit=$Limit)" | Out-String)
    Write-Output ("=" * 80 | Out-String)
    if ($null -eq $queue -or $queue.Count -eq 0) {
        Write-Output "No pending review candidates."
        exit 0
    }
    foreach ($item in $queue) {
        $ev = $item.evidence
        Write-Output ("MatchId={0}  SourceRetailer={1}  SourceProduct={2}" -f $item.matchId, $item.sourceRetailerSlug, $item.sourceListingName)
        Write-Output ("  CandidateCanonical={0} ({1})  Confidence={2}  Size={3}" -f $item.candidateCanonicalId, $item.candidateCanonicalName, $item.confidence, $item.normalizedSize)
        if ($null -ne $ev -and $ev.shared_tokens) {
            Write-Output ("  SharedTokens={0}" -f ($ev.shared_tokens -join ', '))
        }
        Write-Output ""
    }
    Write-Output ("Total returned: {0}" -f $queue.Count)
    exit 0
}

if ($Approve -gt 0) {
    if (-not $ReviewedBy) { throw '--ReviewedBy is required when approving' }
    $body = @{ reviewedBy = $ReviewedBy; reviewNotes = $ReviewNotes }
    $result = Invoke-Post "/api/v1/matches/review-queue/$Approve/approve" $body
    Write-Output ("APPROVED matchId={0} status={1} reviewedBy={2}" -f $result.matchId, $result.reviewStatus, $result.reviewedBy)
    exit 0
}

if ($Reject -gt 0) {
    if (-not $ReviewedBy) { throw '--ReviewedBy is required when rejecting' }
    $body = @{ reviewedBy = $ReviewedBy; reviewNotes = $ReviewNotes }
    $result = Invoke-Post "/api/v1/matches/review-queue/$Reject/reject" $body
    Write-Output ("REJECTED matchId={0} status={1} reviewedBy={2}" -f $result.matchId, $result.reviewStatus, $result.reviewedBy)
    exit 0
}

Write-Output "No action specified. Use --List, --Approve <id>, or --Reject <id>."
exit 1