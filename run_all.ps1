#!/usr/bin/env pwsh

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Start-Window {
    param(
        [string]$Title,
        [string]$Command,
        [string]$WorkDir
    )

    $shellExe = Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shellExe) {
        $shellExe = Get-Command powershell.exe -ErrorAction Stop
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $shellExe.Source
    $psi.Arguments = "-NoExit -Command Set-Location '$WorkDir'; $Command"
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Write-Host "Started $Title in new terminal at $WorkDir"
}

Write-Host "Starting SafeChat AI services..."
Start-Window "Backend" "& '$root\.venv\Scripts\python.exe' -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000" $root
Start-Window "WhatsApp Bridge" "cd whatsapp; npm.cmd install; npm.cmd run dev" $root
Start-Window "Frontend" "cd frontend; npm.cmd install; npm.cmd run dev -- --host 0.0.0.0" $root

Write-Host "All windows started. Keep this terminal open."
