# Build script for WinScope CrashApp diagnostic utility
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceFile = Join-Path $scriptDir "CrashApp.cs"
$outputExe = Join-Path $scriptDir "CrashApp.exe"

$cscCandidates = @(
    "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\Roslyn\csc.exe",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\Roslyn\csc.exe",
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)

$cscPath = $null
foreach ($cand in $cscCandidates) {
    if (Test-Path $cand) {
        $cscPath = $cand
        break
    }
}

if ($null -eq $cscPath) {
    Write-Error "Could not find csc.exe compiler."
    exit 1
}

Write-Host "[WinScope Diagnostics] Compiling $sourceFile -> $outputExe"
& $cscPath /debug:full /optimize- /out:$outputExe $sourceFile

if ($LASTEXITCODE -eq 0 -and (Test-Path $outputExe)) {
    Write-Host "[WinScope Diagnostics] Successfully compiled CrashApp.exe" -ForegroundColor Green
} else {
    Write-Error "Failed to compile CrashApp.exe"
}
