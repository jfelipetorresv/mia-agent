# Mia - build reproducible del backend empaquetado (PyInstaller onedir).
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
#
# Usa SIEMPRE el pyinstaller instalado dentro de mia/.venv (nunca uno global),
# para que el bundle refleje exactamente los pins de backend/pyproject.toml.
# Limpia dist/ y build/ previos (build no incremental, reproducible), corre
# mia-backend.spec y reporta tamano final. Salida: packaging/dist/mia-backend/.
#
# Uso:  powershell -File packaging\build_backend.ps1 -Profile core
param(
    [ValidateSet('core', 'ocr', 'voice', 'full')]
    [string]$Profile = 'core'
)

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
# silencio. Instalamos pyinstaller con --no-deps y sus CUATRO dependencias
# reales (altgraph, pefile, pywin32-ctypes, pyinstaller-hooks-contrib) con
# pines explícitos propios — nunca dejamos que pip resuelva versiones libres
# para nada que toque el venv de la app.
#
# CRITICO — pyinstaller-hooks-contrib (fix F4): la lista original omitía esta
# dependencia REAL de pyinstaller. Sin ella no existe hook-cryptography.py,
# PyInstaller no recolecta _cffi_backend (dependencia oculta del binding Rust
# de cryptography, invisible al análisis estático), el primer import de
# cryptography falla dentro de un try/except silencioso y el reintento de
# PyJWT revienta con "PyO3 modules compiled for CPython 3.8 or older may only
# be initialized once per interpreter process" (el guard de PyO3 enmascara el
# ModuleNotFoundError real de _cffi_backend). hooks-contrib es solo
# infraestructura de build: no toca ningún pin de la app (gate 12/12 verde).
$PyInstallerVersion   = '6.21.0'
$AltgraphVersion      = '0.17.5'
$PefileVersion        = '2024.8.26'
$PywinCtypesVersion   = '0.2.3'
$HooksContribVersion  = '2026.6'

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
        "pywin32-ctypes==$PywinCtypesVersion" `
        "pyinstaller-hooks-contrib==$HooksContribVersion"
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

# GATE DURO (fix F4 · PyO3/_cffi_backend): aunque pyinstaller.exe ya exista,
# el venv puede haber quedado del estado viejo SIN pyinstaller-hooks-contrib
# (la lista --no-deps original lo omitia). Sin hooks-contrib el build "sale
# bien" pero el exe revienta en runtime con el error de PyO3 al importar
# cryptography. Verificamos SIEMPRE y auto-reparamos con pin explicito.
$VenvPythonCheck = Join-Path $RepoRoot '.venv\Scripts\python.exe'
& $VenvPythonCheck -c "import _pyinstaller_hooks_contrib" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyinstaller-hooks-contrib ausente en el venv (estado viejo). Instalando pin $HooksContribVersion..." -ForegroundColor Yellow
    & $VenvPythonCheck -m pip install --quiet --no-deps "pyinstaller-hooks-contrib==$HooksContribVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la instalacion de pyinstaller-hooks-contrib (--no-deps). Sin ella el bundle de cryptography queda roto (PyO3). Build ABORTADO."
    }
    & $VenvPythonCheck (Join-Path $RepoRoot 'execution\check_env_pins.py')
    if ($LASTEXITCODE -ne 0) {
        throw "check_env_pins.py fallo tras instalar pyinstaller-hooks-contrib (Riesgo #32). Build ABORTADO."
    }
}

Write-Host "Repo:        $RepoRoot" -ForegroundColor Cyan
Write-Host "PyInstaller: $VenvPyInstaller" -ForegroundColor Cyan
Write-Host "Spec:        $SpecFile" -ForegroundColor Cyan
Write-Host "Perfil:      $Profile" -ForegroundColor Cyan

# Borrado robusto (sesion 52): el arbol de PyInstaller contiene rutas que
# superan MAX_PATH (p.ej. _internal\PIL\...), y ahi Remove-Item falla con
# "No se puede encontrar una parte de la ruta de acceso" y ABORTA el build
# entero por $ErrorActionPreference='Stop'. robocopy /MIR contra una carpeta
# vacia si maneja rutas largas; se usa como vaciado previo y luego se quita
# el directorio ya vacio.
function Remove-TreeRobusto([string]$path) {
    if (-not (Test-Path $path)) { return }
    Write-Host "Limpiando $path ..." -ForegroundColor Yellow
    $empty = Join-Path ([System.IO.Path]::GetTempPath()) 'mia_empty_dir'
    if (-not (Test-Path $empty)) { New-Item -ItemType Directory -Path $empty | Out-Null }
    $null = robocopy $empty $path /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1
    $global:LASTEXITCODE = 0
    Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
    if (Test-Path $path) { throw "No se pudo limpiar $path (queda contenido). Cierra procesos que lo esten usando." }
}

# Se limpia SOLO lo que este build produce (sesion 52). $DistPath es
# packaging/dist COMPLETO, compartido con los payloads de litellm y frontend:
# borrarlo entero dejaba el arbol inservible para `build_installer -SkipPayloads`
# (los otros dos payloads desaparecian sin aviso). build_litellm y build_frontend
# ya limpian solo su subcarpeta; este ahora hace lo mismo.
Remove-TreeRobusto (Join-Path $DistPath 'mia-backend')
Remove-TreeRobusto (Join-Path $WorkPath 'mia-backend')

$start = Get-Date
# PyInstaller escribe su log INFO/WARNING a stderr. En PowerShell 5.1, con
# $ErrorActionPreference='Stop' eso se promueve a error TERMINANTE en la
# primera linea (aunque el proceso vaya a salir con exit 0), matando el build
# de inmediato. Bajamos la preferencia solo para esta llamada nativa y
# restauramos despues; el resultado real se valida con $LASTEXITCODE.
$prevEap = $ErrorActionPreference
$previousProfile = $env:MIA_BUNDLE_PROFILE
$ErrorActionPreference = 'Continue'
try {
    $env:MIA_BUNDLE_PROFILE = $Profile
    & $VenvPyInstaller $SpecFile --distpath $DistPath --workpath $WorkPath --noconfirm
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEap
    if ($null -eq $previousProfile) { Remove-Item Env:MIA_BUNDLE_PROFILE -ErrorAction SilentlyContinue }
    else { $env:MIA_BUNDLE_PROFILE = $previousProfile }
}
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
# Verificacion de componentes opcionales y contenido prohibido.
# ---------------------------------------------------------------------------
function Assert-NoForbiddenSegments([string]$Root) {
    $forbidden = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'tests', 'test', 'docs', 'harness', '.git')
    $bad = @(Get-ChildItem -LiteralPath $Root -Recurse -Directory | Where-Object { $forbidden -contains $_.Name.ToLowerInvariant() })
    if ($bad.Count -gt 0) { throw "El bundle contiene carpetas no distribuibles:`n  $($bad.FullName -join "`n  ")" }
}
Assert-NoForbiddenSegments $exeDir

$withOcr = $Profile -in @('ocr', 'full')
$withVoice = $Profile -in @('voice', 'full')
$allPaths = @(Get-ChildItem -LiteralPath $exeDir -Recurse | ForEach-Object { $_.FullName.ToLowerInvariant() })

if (-not $withOcr -and @($allPaths | Where-Object { $_ -match '[\\/](rapidocr_onnxruntime|onnxruntime|cv2)([\\/]|$)' }).Count -gt 0) {
    throw 'El perfil core/voice contiene binarios OCR que debian estar excluidos.'
}
if (-not $withVoice -and @($allPaths | Where-Object { $_ -match '[\\/](sherpa_onnx|av|av\.libs)([\\/]|$)' }).Count -gt 0) {
    throw 'El perfil core/ocr contiene binarios de voz que debian estar excluidos.'
}

function Invoke-RequiredSmoke([string]$Flag, [string]$Name) {
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $exePath $Flag 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousEap
    }
    Write-Host "  $output"
    if ($code -ne 0) { throw "$Name esta incluido pero su smoke test fallo (exit $code)." }
    Write-Host "  ${Name}: PASS" -ForegroundColor Green
}

if ($withOcr) {
    Write-Host 'Validando componente OCR incluido...' -ForegroundColor Cyan
    Invoke-RequiredSmoke '--ocr-smoke-test' 'OCR'
} else {
    Write-Host 'OCR no incluido: los PDF con texto siguen disponibles; los escaneados requieren perfil ocr/full.' -ForegroundColor Yellow
}
if ($withVoice) {
    Write-Host 'Validando componente de voz incluido...' -ForegroundColor Cyan
    Invoke-RequiredSmoke '--voice-smoke-test' 'Voz'
} else {
    Write-Host 'Voz no incluida en este perfil.' -ForegroundColor Yellow
}

$sourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
$sourceDirty = @(& git -C $RepoRoot status --porcelain --untracked-files=all).Count -gt 0
$files = @(Get-ChildItem -LiteralPath $exeDir -Recurse -File)
$manifest = [ordered]@{
    schema_version = 1
    profile = $Profile
    capabilities = [ordered]@{ ocr = [bool]$withOcr; voice = [bool]$withVoice }
    source_commit = $sourceCommit
    source_dirty = [bool]$sourceDirty
    payload_bytes_excluding_manifest = [long](($files | Measure-Object -Property Length -Sum).Sum)
    files_excluding_manifest = $files.Count
    built_at_utc = [DateTime]::UtcNow.ToString('o')
}
$manifestPath = Join-Path $exeDir 'mia-component-manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Componentes: $manifestPath" -ForegroundColor Green
