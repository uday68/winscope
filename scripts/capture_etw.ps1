# WinScope - Windows Performance Recorder (ETW) Capture Script
param(
    [string]$TraceName = "WinScopeExperiment",
    [int]$DurationSeconds = 5,
    [string]$OutputDir = "data\traces"
)

$wpr = "C:\Windows\System32\wpr.exe"
if (!(Test-Path $wpr)) {
    Write-Error "wpr.exe not found in System32."
    exit 1
}

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$traceFile = Join-Path (Get-Location) "$OutputDir\$TraceName.etl"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " WinScope ETW Capture via Windows Performance Recorder" -ForegroundColor Cyan
Write-Host " Trace File: $traceFile"
Write-Host " Duration:   $DurationSeconds seconds"
Write-Host " Profile:    GeneralProfile (CPU, Disk, Memory, Process)"
Write-Host "=========================================================="

# Check if an existing WPR session is active and cancel if needed
& $wpr -status 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[ETW] Existing WPR recording active. Canceling prior trace..."
    & $wpr -cancel
}

Write-Host "[ETW] Starting ETW recording session into memory circular buffer..."
& $wpr -start GeneralProfile -filemode
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start ETW recording. (Note: WPR requires elevated administrator privileges)."
    exit $LASTEXITCODE
}

Write-Host "[ETW] Recording active. Waiting for experiment ($DurationSeconds s)..."
Start-Sleep -Seconds $DurationSeconds

Write-Host "[ETW] Stopping trace and flushing to $traceFile..."
& $wpr -stop $traceFile "WinScope Controlled Experiment"

if (Test-Path $traceFile) {
    $sizeMb = [math]::Round(((Get-Item $traceFile).Length / 1MB), 2)
    Write-Host "[ETW] Successfully captured trace! Size: $sizeMb MB" -ForegroundColor Green
    Write-Host "[ETW] To inspect in Windows Performance Analyzer (WPA):" -ForegroundColor Yellow
    Write-Host "      wpa.exe `"$traceFile`"" -ForegroundColor Yellow
} else {
    Write-Error "[ETW] Failed to produce trace file."
}
