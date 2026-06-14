# Mia - start LiteLLM proxy (Modo B, terminal 1). Puerto 4000.
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
$envFile = Join-Path $root '.env'
# Cargar .env al entorno del proceso (LiteLLM lee las claves desde os.environ).
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*([^#=][^=]*)\s*=\s*(.*)$') {
    $name = $matches[1].Trim()
    $val = $matches[2].Trim().Trim('"').Trim("'")
    [Environment]::SetEnvironmentVariable($name, $val, 'Process')
  }
}
$cfg = Join-Path $root 'litellm_config.yaml'
Write-Host "Iniciando LiteLLM proxy en http://127.0.0.1:4000 (config: $cfg)"
litellm --config $cfg --port 4000
