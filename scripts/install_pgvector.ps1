# Mia - instala pgvector precompilado para PostgreSQL 16 en Windows (requiere ADMIN).
# Fuente: andreiramani/pgvector_pgsql_windows (binario de terceros, valido para dev Modo B).
# ASCII puro a proposito.
# Uso: PowerShell como administrador:
#   & "D:\Codex\Mia-Super Agent\mia\scripts\install_pgvector.cmd"
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pgRoot = 'C:\Program Files\PostgreSQL\16'
$pgLib = Join-Path $pgRoot 'lib'
$pgExt = Join-Path $pgRoot 'share\extension'
$url = 'https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.3_16.14/vector.v0.8.3-pg16.zip'
$tmp = Join-Path $root '.tmp\pgvector'
$zip = Join-Path $tmp 'vector.zip'

if (-not (Test-Path $pgRoot)) {
    throw "No se encontro $pgRoot - instala PostgreSQL 16 primero."
}

New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Write-Host "Descargando pgvector..."
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $tmp -Force

$dll = Get-ChildItem $tmp -Recurse -Filter 'vector.dll' | Select-Object -First 1
if (-not $dll) { throw 'vector.dll no encontrado dentro del zip.' }

$extFiles = @(Get-ChildItem $tmp -Recurse -Filter 'vector.control')
$extFiles += @(Get-ChildItem $tmp -Recurse -Filter 'vector--*.sql')
if ($extFiles.Count -lt 2) { throw 'Faltan archivos vector.control o vector--*.sql en el zip.' }

Write-Host "Copiando a $pgLib y $pgExt ..."
Copy-Item $dll.FullName $pgLib -Force
foreach ($f in $extFiles) {
    Copy-Item $f.FullName $pgExt -Force
    Write-Host "  $($f.Name)"
}

$pgBin = Join-Path $pgRoot 'bin\psql.exe'
& $pgBin -h 127.0.0.1 -U postgres -d postgres -c "SELECT 1" | Out-Null
Write-Host 'OK - pgvector instalado en el servidor PostgreSQL 16.'
Write-Host 'Siguiente paso (terminal normal):'
Write-Host "  & `"$root\scripts\setup_db.cmd`""
