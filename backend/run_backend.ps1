#!/usr/bin/env pwsh
# Activate virtual environment (if created as .venv) and run the backend
if (Test-Path -Path .\.venv\Scripts\Activate.ps1) {
    Write-Host "Activating .venv..."
    & .\.venv\Scripts\Activate.ps1
}

Write-Host "Starting backend (uvicorn) on :8000..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
