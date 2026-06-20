# M0 — Foundation verification wrapper (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "Aksh M0 verify_setup" -ForegroundColor Cyan
& $Python (Join-Path $Root "scripts\verify_setup.py")
exit $LASTEXITCODE
