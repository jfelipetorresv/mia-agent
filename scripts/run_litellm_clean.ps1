# Mia - internal LiteLLM launcher with DB env scrubbed.
# -LiteLLM debe apuntar al exe del venv DEDICADO del proxy (.venv-litellm),
# nunca al venv de la app (.venv). Ver Riesgo #32.
param(
  [Parameter(Mandatory = $true)][string]$LiteLLM,
  [Parameter(Mandatory = $true)][string]$Config
)
$ErrorActionPreference = 'Stop'

foreach ($name in @(
  'DATABASE_URL',
  'DIRECT_URL',
  'PG_DB',
  'PGPASSWORD',
  'PG_PASSWORD',
  'PG_APP_PASSWORD',
  'POSTGRES_HOST',
  'POSTGRES_PORT',
  'POSTGRES_USER',
  'POSTGRES_PASSWORD',
  'DATABASE_HOST',
  'DATABASE_PORT',
  'DATABASE_USERNAME',
  'DATABASE_PASSWORD',
  'DATABASE_NAME',
  'DATABASE_SCHEMA'
)) {
  Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

# Aislar el CWD de litellm: corre desde la carpeta del config (runtime, SIN .env).
# Critico en Windows PowerShell: Set-Location NO cambia el CWD Win32 que heredan los
# procesos hijos, asi que litellm.exe correria con CWD=proyecto y su load_dotenv()
# reinyectaria DATABASE_URL desde .env -> intentaria Prisma y moriria al arrancar.
# Mia NO usa la BD interna de LiteLLM (solo es proxy de modelos).
$runtimeDir = Split-Path -Parent $Config
Set-Location -LiteralPath $runtimeDir
[Environment]::CurrentDirectory = $runtimeDir

# Defensa en profundidad: forzar que get_secret('DATABASE_URL') devuelva None en el
# arranque del proxy (auto-sana tras un reinstall de litellm; idempotente).
$proxyServer = Join-Path (Split-Path -Parent (Split-Path -Parent $LiteLLM)) 'Lib\site-packages\litellm\proxy\proxy_server.py'
if (Test-Path $proxyServer) {
  $source = Get-Content -LiteralPath $proxyServer -Raw
  if ($source -match 'get_secret\("DATABASE_URL", None\)') {
    $source = $source -replace 'get_secret\("DATABASE_URL", None\)', 'None  # MIA: BD interna de LiteLLM deshabilitada'
    [System.IO.File]::WriteAllText($proxyServer, $source, (New-Object System.Text.UTF8Encoding($false)))
  }
}

& $LiteLLM --config $Config --port 4000
