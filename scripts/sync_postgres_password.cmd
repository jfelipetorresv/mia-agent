@echo off
REM Mia — sincroniza contraseña postgres con .env (ejecutar como Administrador)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_postgres_password.ps1"
pause
