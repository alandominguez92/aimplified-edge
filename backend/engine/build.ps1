# Build the C++ EV/Kelly engine -> kelly_engine.exe (standalone, static).
# Uses g++ from PATH, else the WinLibs winget install location.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gpp = (Get-Command g++ -ErrorAction SilentlyContinue).Source
if (-not $gpp) {
    $winlibs = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter g++.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winlibs) { $gpp = $winlibs.FullName }
}
if (-not $gpp) { throw "g++ not found. Install e.g.: winget install BrechtSanders.WinLibs.POSIX.UCRT" }

& $gpp -O2 -std=c++17 -static -o kelly_engine.exe main.cpp kelly.cpp
& .\kelly_engine.exe selftest
Write-Output "built kelly_engine.exe"
