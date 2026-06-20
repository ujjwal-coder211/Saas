# M3 — Training flywheel pipeline: curate → build_dataset → research_report → scheduler
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Write-Host "Aksh M3 — run_pipeline" -ForegroundColor Cyan

Write-Host "`n[1/4] curate.py" -ForegroundColor Yellow
& $Python (Join-Path $Root "omni_training\curate.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[2/4] build_dataset.py" -ForegroundColor Yellow
& $Python (Join-Path $Root "omni_training\build_dataset.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[3/4] research_report.py" -ForegroundColor Yellow
& $Python (Join-Path $Root "omni_training\research_report.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[4/4] scheduler.py" -ForegroundColor Yellow
& $Python (Join-Path $Root "omni_training\scheduler.py")
exit $LASTEXITCODE
