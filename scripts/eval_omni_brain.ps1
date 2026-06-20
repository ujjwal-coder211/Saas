# M1 — Omni brain pre-promote checklist
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

$VersionArg = $args -join " "
& $Python (Join-Path $Root "omni_training\brain_eval.py") @args
exit $LASTEXITCODE
