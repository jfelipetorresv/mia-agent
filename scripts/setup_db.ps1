# Mia - inicializa DB + migraciones + gate RLS (Modo B).
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
if (Test-Path $pgBin) { $env:Path = "$pgBin;$env:Path" }

Set-Location $root

# Verificar que pgvector este en el servidor que REALMENTE se va a usar.
# ANTES: se consultaba el PostgreSQL del SISTEMA con ruta fija (C:\Program Files\...\psql.exe)
# y su puerto por defecto (5432). Si la instalacion usa la base PORTABLE (PG_PORT del .env,
# p.ej. 55432), ese chequeo miraba la base EQUIVOCADA y abortaba las migraciones con
# 'pgvector no esta instalada' aunque si lo estuviera (falsa alarma reproducida 2026-07-19).
# AHORA: se consulta la base configurada en .env, con el mismo venv que corre las migraciones.
# Si no se puede verificar, NO bloquea (fail-open con aviso): init_db dara el error real.
# El Python vive en scripts\setup_db_steps.py: los here-strings con Python embebido
# reventaban en Windows PowerShell 5.1 (deuda del HANDOFF 2026-08-15/18).
& $py scripts\setup_db_steps.py check-pgvector
if ($LASTEXITCODE -eq 2) {
    Write-Host ''
    Write-Host 'ERROR: la extension pgvector no esta disponible en la base configurada en .env.'
    Write-Host 'Ejecuta como ADMIN:'
    Write-Host "  & `"$root\scripts\install_pgvector.cmd`""
    exit 1
}

Write-Host '== init_db =='
& $py execution\init_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'Si fallo la autenticacion, ejecuta como ADMIN:'
    Write-Host "  & `"$root\scripts\sync_postgres_password.cmd`""
    exit $LASTEXITCODE
}

$migrations = Get-ChildItem backend\mia\db\migrations\*.sql | Sort-Object Name
foreach ($m in $migrations) {
    Write-Host "== migration $($m.Name) =="
    & $py scripts\setup_db_steps.py apply-migration $m.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (Test-Path execution\init_checkpointer.py) {
    Write-Host '== init_checkpointer =='
    & $py execution\init_checkpointer.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host '== test_rls (gate) =='
& $py execution\test_rls.py
exit $LASTEXITCODE
