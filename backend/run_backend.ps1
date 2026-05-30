#!/usr/bin/env pwsh

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Expected virtual environment python at $pythonExe"
}

Write-Host "Applying backend migrations..."
& $pythonExe "$root\backend\scripts\migrate.py"
if ($LASTEXITCODE -ne 0) {
    throw "Migration step failed."
}

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
& $pythonExe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
