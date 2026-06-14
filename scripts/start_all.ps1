# Mia - arranque Modo B. Abre las terminales del stack en ventanas separadas.
# ASCII puro a proposito.
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
Start-Process powershell -ArgumentList '-NoExit', '-File', (Join-Path $root 'scripts\start_litellm.ps1')
Start-Process powershell -ArgumentList '-NoExit', '-File', (Join-Path $root 'scripts\start_api.ps1')
Write-Host "Lanzados: LiteLLM (4000) y API (8000)."
Write-Host "Frontend (npm run dev) pendiente - Fase 3."
