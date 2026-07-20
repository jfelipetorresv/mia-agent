@echo off
REM Abrir Mia (Modo B) — doble-clic. Enciende motor + cerebro + pantalla y abre el navegador.
REM Las ventanas de servicio salen minimizadas; NO las cierres mientras uses Mia (cerrarlas la apaga).
title Abrir Mia
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_all.ps1"
