# Run NeuralRouter locally with .env loaded
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (Test-Path "$Root\.env") {
    Get-Content "$Root\.env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $p = $_ -split '=', 2
        if ($p.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($p[0].Trim(), $p[1].Trim(), 'Process')
        }
    }
}

$env:PYTHONPATH = $Root
Write-Host "Starting NeuralRouter at http://127.0.0.1:8000"
Write-Host "Docs: http://127.0.0.1:8000/docs"
python -m uvicorn neuralrouter.main:app --host 127.0.0.1 --port 8000 --reload
