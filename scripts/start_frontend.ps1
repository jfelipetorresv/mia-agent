# Mia - start frontend (Next.js dev, Modo B, terminal 3). Puerto 3100.
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
Set-Location (Join-Path $root 'frontend')
# Mia usa el puerto 3100 (definido en frontend/package.json: "next dev -p 3100")
# para no chocar con otro proyecto del equipo que usa el 3000.
Write-Host "Iniciando la pantalla de Mia en http://localhost:3100"
npm run dev
