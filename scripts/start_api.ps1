# Mia - start API (uvicorn, Modo B, terminal 2). Puerto 8000.
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
# Evita que litellm baje su tabla de precios desde la red en la 1a llamada
# (cold-start de ~40s en embeddings). Usa el mapa embebido.
$env:LITELLM_LOCAL_MODEL_COST_MAP = "True"
Write-Host "Iniciando API en http://127.0.0.1:8000 (PYTHONPATH=$env:PYTHONPATH)"
& $py -m uvicorn mia.api.main:app --host 127.0.0.1 --port 8000 --reload
