# Mia - start puente de Telegram (CP-B2, opt-in). Requiere el API corriendo (start_api.ps1).
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
# Gate del Riesgo #32: si el venv de la app fue degradado, no arrancar.
& $py (Join-Path $root 'execution\check_env_pins.py')
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORTADO: pins del venv alterados (Riesgo #32). Ver execution/check_env_pins.py"
    exit 1
}
Write-Host "Iniciando el puente de Telegram de Mia (guia: docs\telegram-setup.md)..."
Write-Host "Recuerda: el API de Mia debe estar corriendo (scripts\start_api.ps1)."
& $py -m mia.channels.telegram_bridge
exit $LASTEXITCODE
