@echo off
REM Mia — init_db + migraciones + test_rls
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_db.ps1"
exit /b %ERRORLEVEL%
