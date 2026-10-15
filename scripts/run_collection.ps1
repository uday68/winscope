# WinScope Session Runner
param(
    [int]$DurationSeconds = 5,
    [int]$IntervalMs = 1000,
    [int]$TargetPid = 0,
    [switch]$UseCSharp
)

$targetDir = Join-Path (Get-Location) "data\raw"
if (!(Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
}

$sessionId = [guid]::NewGuid().ToString()
$outFile = Join-Path $targetDir "session_$sessionId.jsonl"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " WinScope Telemetry Collection Session" -ForegroundColor Cyan
Write-Host " Session ID: $sessionId"
Write-Host " Output:     $outFile"
Write-Host " Duration:   $DurationSeconds seconds"
Write-Host " Interval:   $IntervalMs ms"
Write-Host " Engine:     $(if ($UseCSharp) { 'C# Native' } else { 'Python' })"
Write-Host "=========================================================="

if ($UseCSharp) {
    $csharpExe = Join-Path (Get-Location) "collector\csharp\bin\WinScope.Collector.exe"
    if (!(Test-Path $csharpExe)) {
        Write-Host "Compiling C# collector..."
        & .\collector\csharp\build.ps1
    }
    $argsList = @("--interval", $IntervalMs, "--duration", $DurationSeconds, "--output", $outFile)
    if ($TargetPid -gt 0) {
        $argsList += @("--pid", $TargetPid)
    }
    & $csharpExe $argsList
} else {
    $pyScript = "from collector.python.collector import WindowsTelemetryCollector`n" +
                "c = WindowsTelemetryCollector(sampling_interval_ms=$IntervalMs" +
                $(if ($TargetPid -gt 0) { ", target_pid=$TargetPid" } else { "" }) +
                ")`n" +
                "c.run_session(duration_seconds=$DurationSeconds, output_file=r'$outFile')`n"
    & C:\Python312\python.exe -c $pyScript
}

Write-Host "`n[WinScope] Collection complete! Generated: $outFile" -ForegroundColor Green
$lineCount = (Get-Content $outFile).Count
Write-Host "[WinScope] Total emitted records: $lineCount" -ForegroundColor Green
