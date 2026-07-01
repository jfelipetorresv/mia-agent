# Mia - arranque Modo B. Abre las terminales del stack en ventanas separadas.
# ASCII puro a proposito.
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
# LiteLLM corre en su venv dedicado (.venv-litellm); start_litellm.ps1 lo resuelve.
# Comillas explicitas: la ruta contiene espacios y -ArgumentList no cita solo.
Start-Process powershell -ArgumentList '-NoExit', '-File', ('"{0}"' -f (Join-Path $root 'scripts\start_litellm.ps1'))
Start-Process powershell -ArgumentList '-NoExit', '-File', ('"{0}"' -f (Join-Path $root 'scripts\start_api.ps1'))
Write-Host "Lanzados: LiteLLM (4000) y API (8000)."
Write-Host "Frontend (npm run dev) pendiente - Fase 3."
