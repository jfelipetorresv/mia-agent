# Mia - inicializa DB + migraciones + gate RLS (Modo B).
# ASCII puro a proposito.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
if (Test-Path $pgBin) { $env:Path = "$pgBin;$env:Path" }

Set-Location $root

# Verificar que pgvector este en el servidor antes de init_db.
$pgBin = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'
if (Test-Path $pgBin) {
    $check = & $pgBin -h 127.0.0.1 -U postgres -d postgres -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" 2>$null
    if (-not ($check -match '1')) {
        Write-Host ''
        Write-Host 'ERROR: la extension pgvector no esta instalada en PostgreSQL 16.'
        Write-Host 'Ejecuta como ADMIN:'
        Write-Host "  & `"$root\scripts\install_pgvector.cmd`""
        exit 1
    }
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
    & $py -c @"
import os, psycopg
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(r'$root') / '.env')
sql = Path(r'$($m.FullName)').read_text(encoding='utf-8')
with psycopg.connect(host=os.getenv('PG_HOST','127.0.0.1'), port=os.getenv('PG_PORT','5432'),
    dbname=os.getenv('PG_DB','mia'), user='postgres', password=os.getenv('PG_PASSWORD',''),
    autocommit=True) as conn:
    conn.execute(sql)
print('OK')
"@
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
