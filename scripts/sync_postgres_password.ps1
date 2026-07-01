# Mia - sincroniza la contrasena de postgres con PG_PASSWORD del .env (requiere ADMIN).
# ASCII puro a proposito (evita errores de encoding en PowerShell Windows).
# Uso: PowerShell como administrador:
#   & "D:\Codex\Mia-Super Agent\mia\scripts\sync_postgres_password.cmd"
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { throw "No existe $envFile" }
$pgPassword = (Get-Content $envFile | Where-Object { $_ -match '^PG_PASSWORD=' }) -replace '^PG_PASSWORD=', ''
if (-not $pgPassword) { throw 'PG_PASSWORD vacio en .env' }

$pgData = 'C:\Program Files\PostgreSQL\16\data'
$pgHba = Join-Path $pgData 'pg_hba.conf'
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
$svc = 'postgresql-x64-16'
$backup = "$pgHba.bak-mia-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

if (-not (Test-Path $pgHba)) { throw "No se encontro $pgHba - ajusta la ruta de PostgreSQL." }

Copy-Item $pgHba $backup
Write-Host "Backup: $backup"

$content = Get-Content $pgHba -Raw
$content = $content -replace '127\.0\.0\.1/32\s+scram-sha-256', '127.0.0.1/32            trust'
$content = $content -replace '::1/128\s+scram-sha-256', '::1/128                 trust'
Set-Content -Path $pgHba -Value $content -NoNewline

Restart-Service $svc
Start-Sleep -Seconds 3

$escaped = $pgPassword.Replace("'", "''")
& "$pgBin\psql.exe" -h 127.0.0.1 -U postgres -d postgres -c "ALTER USER postgres PASSWORD '$escaped';"
if ($LASTEXITCODE -ne 0) { throw 'ALTER USER fallo - revisa el servicio postgres.' }

Copy-Item $backup $pgHba -Force
Restart-Service $svc
Start-Sleep -Seconds 2

Write-Host 'OK - contrasena de postgres sincronizada con PG_PASSWORD del .env.'
