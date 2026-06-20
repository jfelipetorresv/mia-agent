# Mia - internal LiteLLM launcher with DB env scrubbed.
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

$proxyServer = Join-Path (Split-Path -Parent (Split-Path -Parent $LiteLLM)) 'Lib\site-packages\litellm\proxy\proxy_server.py'
if (Test-Path $proxyServer) {
  $source = Get-Content -LiteralPath $proxyServer -Raw
  $source = $source -replace 'if _db_url is not None:', 'if False and _db_url is not None:'
  Set-Content -LiteralPath $proxyServer -Value $source -Encoding UTF8
}

& $LiteLLM --config $Config --port 4000
