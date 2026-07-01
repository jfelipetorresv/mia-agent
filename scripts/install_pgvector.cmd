@echo off
REM Mia - instala pgvector para PostgreSQL 16 (ejecutar como Administrador)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_pgvector.ps1"
pause
