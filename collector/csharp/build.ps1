# WinScope C# Collector Build Script
param(
    [string]$Configuration = "Release"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceFile = Join-Path $scriptDir "Program.cs"
$binDir = Join-Path $scriptDir "bin"
$outputExe = Join-Path $binDir "WinScope.Collector.exe"

if (!(Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
}

# Locate C# compiler (prefer Roslyn if available, fallback to Framework64)
$cscCandidates = @(
    "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\Roslyn\csc.exe",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\Roslyn\csc.exe",
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)

$cscPath = $null
foreach ($cand in $cscCandidates) {
    if (Test-Path $cand) {
        $cscPath = $cand
        break
    }
}

if ($null -eq $cscPath) {
    Write-Error "Could not find a valid C# compiler (csc.exe)."
    exit 1
}

Write-Host "[WinScope Build] Using compiler: $cscPath"
Write-Host "[WinScope Build] Compiling $sourceFile -> $outputExe"

$cscArgs = @(
    "/target:exe",
    "/optimize+",
    "/platform:anycpu",
    "/warn:4",
    "/out:$outputExe",
    "/reference:System.dll",
    "/reference:System.Core.dll",
    $sourceFile
)

& $cscPath $cscArgs

if ($LASTEXITCODE -eq 0 -and (Test-Path $outputExe)) {
    Write-Host "[WinScope Build] Build successful: $outputExe" -ForegroundColor Green
    exit 0
} else {
    Write-Error "[WinScope Build] Compilation failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}
