# Mia - start LiteLLM proxy (Modo B, terminal 1). Puerto 4000.
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
$envFile = Join-Path $root '.env'
$env:PYTHONIOENCODING = 'utf-8'
# Cargar .env al entorno del proceso (LiteLLM lee las claves desde os.environ).
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*([^#=][^=]*)\s*=\s*(.*)$') {
    $name = $matches[1].Trim()
    $val = $matches[2].Trim().Trim('"').Trim("'")
    if ($name -in @('DATABASE_URL', 'PG_DB', 'PG_PASSWORD', 'PG_APP_PASSWORD')) {
      return
    }
    [Environment]::SetEnvironmentVariable($name, $val, 'Process')
  }
}
# LiteLLM hereda el entorno del proceso. Si ve DATABASE_URL asume que debe
# gestionar su BD interna e intenta importar Prisma (No module named 'prisma').
# Mia NO usa la BD de LiteLLM (solo es proxy de modelos) -> la quitamos del proceso.
foreach ($dbVar in @('DATABASE_URL', 'PG_DB', 'PG_PASSWORD', 'PG_APP_PASSWORD')) {
  [Environment]::SetEnvironmentVariable($dbVar, $null, 'Process')
}
$env:LITELLM_LOCAL_MODEL_COST_MAP = "True"
$cfg = Join-Path $root 'litellm_config.yaml'
# Riesgo #32: el proxy corre en su PROPIO venv (.venv-litellm) para que sus
# reinstalaciones no degraden las dependencias del venv de la app (.venv).
$litellm = Join-Path $root '.venv-litellm\Scripts\litellm.exe'
if (-not (Test-Path $litellm)) {
  throw "No se encontro $litellm. Crea el venv del proxy: python -m venv .venv-litellm; luego .venv-litellm\Scripts\python.exe -m pip install 'litellm[proxy]==1.74.8'"
}
$runtimeDir = Join-Path $env:TEMP 'mia-litellm-runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$runtimeCfg = Join-Path $runtimeDir 'litellm_config.yaml'
Copy-Item -LiteralPath $cfg -Destination $runtimeCfg -Force
Set-Location $runtimeDir
Write-Host "Iniciando LiteLLM proxy en http://127.0.0.1:4000 (config: $runtimeCfg)"
$cleanLauncher = Join-Path $root 'scripts\run_litellm_clean.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $cleanLauncher -LiteLLM $litellm -Config $runtimeCfg
