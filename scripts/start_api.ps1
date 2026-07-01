# Mia - start API (uvicorn, Modo B, terminal 2). Puerto 8000.
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
# Evita que litellm baje su tabla de precios desde la red en la 1a llamada
# (cold-start de ~40s en embeddings). Usa el mapa embebido.
$env:LITELLM_LOCAL_MODEL_COST_MAP = "True"
$port = if ($env:MIA_API_PORT) { $env:MIA_API_PORT } else { "8000" }
# Gate del Riesgo #32: si el venv de la app fue degradado, no arrancar.
& $py (Join-Path $root 'execution\check_env_pins.py')
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORTADO: pins del venv alterados (Riesgo #32). Ver execution/check_env_pins.py"
    exit 1
}
Write-Host "Iniciando API en http://127.0.0.1:$port (PYTHONPATH=$env:PYTHONPATH)"
& $py -m mia.api.run
