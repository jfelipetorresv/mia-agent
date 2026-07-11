# Mia - build reproducible del backend empaquetado (PyInstaller onedir).
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
#
# Usa SIEMPRE el pyinstaller instalado dentro de mia/.venv (nunca uno global),
# para que el bundle refleje exactamente los pins de backend/pyproject.toml.
# Limpia dist/ y build/ previos (build no incremental, reproducible), corre
# mia-backend.spec y reporta tamano final. Salida: packaging/dist/mia-backend/.
#
# Uso:  powershell -File packaging\build_backend.ps1
$ErrorActionPreference = 'Stop'

$PackagingDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $PackagingDir
$VenvPyInstaller = Join-Path $RepoRoot '.venv\Scripts\pyinstaller.exe'
$SpecFile = Join-Path $PackagingDir 'mia-backend.spec'
$DistPath = Join-Path $PackagingDir 'dist'
$WorkPath = Join-Path $PackagingDir 'build'

if (-not (Test-Path $SpecFile)) {
    throw "No se encontro el spec: $SpecFile"
}

# Fix Fase 1 · capa 2 · m5: "pip install pyinstaller" SIN --no-deps puede
# subir (o bajar) versiones de dependencias que la app YA usa fijadas en
# backend/pyproject.toml (p. ej. si pyinstaller alguna vez declara un rango
# compartido con fastapi/starlette/etc.), degradando el venv de la app en
# silencio. Instalamos pyinstaller con --no-deps y sus TRES dependencias
# reales (altgraph, pefile, pywin32-ctypes) con pines explícitos propios —
# nunca dejamos que pip resuelva versiones libres para nada que toque el
# venv de la app.
$PyInstallerVersion   = '6.21.0'
$AltgraphVersion      = '0.17.5'
$PefileVersion        = '2024.8.26'
$PywinCtypesVersion   = '0.2.3'

if (-not (Test-Path $VenvPyInstaller)) {
    Write-Host "pyinstaller no esta en el venv de la app. Instalando (--no-deps, sin tocar otros pins)..." -ForegroundColor Yellow
    $VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $VenvPython)) {
        throw "No se encontro el venv de la app en $RepoRoot\.venv. Crea el venv primero (ver docs de arranque)."
    }
    & $VenvPython -m pip install --quiet --no-deps `
        "pyinstaller==$PyInstallerVersion" `
        "altgraph==$AltgraphVersion" `
        "pefile==$PefileVersion" `
        "pywin32-ctypes==$PywinCtypesVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la instalacion de pyinstaller (--no-deps) en el venv de la app."
    }
    if (-not (Test-Path $VenvPyInstaller)) {
        throw "pyinstaller se instalo pero no aparece en $VenvPyInstaller"
    }

    # GATE DURO (fix m5): cualquier instalacion en el venv de la app -- aunque
    # sea con --no-deps y pines propios -- puede en teoria interactuar mal con
    # el resolutor de pip si algo mas quedo instalado antes. No asumimos que
    # "--no-deps" es garantia suficiente: corremos el gate real del Riesgo #32
    # AHORA MISMO, antes de compilar nada, y abortamos el build si falla.
    Write-Host "Corriendo gate de pins del venv (execution\check_env_pins.py) tras instalar pyinstaller..." -ForegroundColor Cyan
    & $VenvPython (Join-Path $RepoRoot 'execution\check_env_pins.py')
    if ($LASTEXITCODE -ne 0) {
        throw "check_env_pins.py fallo tras instalar pyinstaller -- el venv de la app quedo alterado (Riesgo #32). Build ABORTADO antes de compilar. Revisa el venv (recrearlo si hace falta) y vuelve a intentar."
    }
    Write-Host "Pins del venv OK (9/9). Continuando con el build." -ForegroundColor Green
}

Write-Host "Repo:        $RepoRoot" -ForegroundColor Cyan
Write-Host "PyInstaller: $VenvPyInstaller" -ForegroundColor Cyan
Write-Host "Spec:        $SpecFile" -ForegroundColor Cyan

if (Test-Path $DistPath) {
    Write-Host "Limpiando dist/ previo..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $DistPath
}
if (Test-Path $WorkPath) {
    Write-Host "Limpiando build/ previo..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $WorkPath
}

$start = Get-Date
# PyInstaller escribe su log INFO/WARNING a stderr. En PowerShell 5.1, con
# $ErrorActionPreference='Stop' eso se promueve a error TERMINANTE en la
# primera linea (aunque el proceso vaya a salir con exit 0), matando el build
# de inmediato. Bajamos la preferencia solo para esta llamada nativa y
# restauramos despues; el resultado real se valida con $LASTEXITCODE.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $VenvPyInstaller $SpecFile --distpath $DistPath --workpath $WorkPath --noconfirm
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
$elapsed = (Get-Date) - $start

if ($exitCode -ne 0) {
    throw "PyInstaller termino con codigo $exitCode (duracion $($elapsed.ToString('mm\:ss')))"
}

$exeDir = Join-Path $DistPath 'mia-backend'
$exePath = Join-Path $exeDir 'mia-backend.exe'
if (-not (Test-Path $exePath)) {
    throw "El build termino OK pero no se encontro el ejecutable: $exePath"
}

$sizeBytes = (Get-ChildItem -Recurse $exeDir | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($sizeBytes / 1MB, 1)

Write-Host ""
Write-Host "Build OK en $($elapsed.ToString('mm\:ss'))" -ForegroundColor Green
Write-Host "Salida:      $exeDir" -ForegroundColor Green
Write-Host "Tamano:      $sizeMB MB" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Smoke OCR post-build (fix Fase 1 · capa 2 · m4) — OPCIONAL, no HALT.
# ---------------------------------------------------------------------------
# entry_backend.py (--ocr-smoke-test) instancia RapidOCR() REAL desde el
# bundle recien compilado, sin levantar el servidor. Esto es "barato" (unos
# segundos, ya que el modelo ya esta en disco dentro de dist\mia-backend\) y
# atrapa el caso mas comun de corrupcion: modelos .onnx faltantes o truncados
# tras el empaquetado. Es un WARNING, no un HALT: una falla aqui no aborta el
# build (el resto del bundle puede ser perfectamente utilizable sin OCR), pero
# SI debe investigarse antes de distribuir el instalador.
#
# TODO explicito (no cubierto por este smoke, ni prometido en el entry): el
# unico gate REAL de que el OCR funciona end-to-end es subir un PDF escaneado
# de verdad a traves de la API y confirmar que el texto extraido es correcto.
# Ese E2E vive documentado como pendiente para Fase 4 (validacion de la
# instalacion completa) — no se implementa aqui.
Write-Host ""
Write-Host "Smoke OCR post-build (opcional): instanciando RapidOCR() desde el bundle..." -ForegroundColor Cyan
$prevEap2 = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$ocrSmokeOutput = & $exePath --ocr-smoke-test 2>&1
$ocrSmokeExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap2
Write-Host "  $ocrSmokeOutput"
if ($ocrSmokeExit -ne 0) {
    Write-Host "  ADVERTENCIA: el smoke de OCR post-build FALLO (exit $ocrSmokeExit). Los .onnx del bundle podrian estar incompletos o corruptos -- investigar antes de distribuir el instalador. El build NO se aborta por esto (ver TODO de Fase 4 E2E arriba)." -ForegroundColor Yellow
} else {
    Write-Host "  Smoke OCR post-build: PASS (RapidOCR instancio correctamente desde el bundle)." -ForegroundColor Green
}
