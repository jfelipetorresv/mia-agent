@echo off
REM Mia — regresion completa execution/test_*.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_tests.ps1"
exit /b %ERRORLEVEL%
