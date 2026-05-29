#!/usr/bin/env pwsh
Write-Host "Installing frontend dependencies (if needed) and starting Vite dev server..."
cd frontend
npm install
npm run dev -- --host 0.0.0.0
