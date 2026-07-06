# Mia - start frontend (Next.js dev, Modo B, terminal 3). Puerto 3000.
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\
Set-Location (Join-Path $root 'frontend')
Write-Host "Iniciando la pantalla de Mia en http://localhost:3000"
npm run dev
