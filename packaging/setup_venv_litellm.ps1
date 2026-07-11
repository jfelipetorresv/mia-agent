# Mia - crea el venv DEDICADO del proxy LiteLLM (.venv-litellm en la raiz del repo).
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
#
# Por que un venv separado del venv de la app (.venv): el proxy LiteLLM se empaqueta
# como su PROPIO ejecutable (mia-litellm.exe, ver mia-litellm.spec) y necesita
# pyinstaller + sus dependencias de build instaladas SOLO ahi. Si se instalara
# pyinstaller en .venv (el venv del backend), correria el mismo riesgo que ya
# resolvimos para el backend (Riesgo #32): degradar en silencio los pins de
# backend/pyproject.toml. Ver tambien scripts/start_litellm.ps1, que documenta el
# mismo aislamiento para el arranque en Modo B (dev).
#
# Usa el MISMO interprete BASE que .venv (no un Python del sistema al azar): se lee
# de .venv\pyvenv.cfg -> "home". Asi el venv de litellm queda en la misma version
# exacta de Python (3.11.x) que el resto del proyecto, sin depender de que haya
# otro Python instalado o en el PATH de la maquina de build.
#
# Idempotente: si .venv-litellm ya existe y litellm ya esta pineado a la version
# esperada, no reinstala nada (evita perder minutos en cada corrida del build).
#
# Uso:  powershell -File packaging\setup_venv_litellm.ps1
$ErrorActionPreference = 'Stop'

$PackagingDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $PackagingDir
$AppVenvCfg = Join-Path $RepoRoot '.venv\pyvenv.cfg'
$LitellmVenvDir = Join-Path $RepoRoot '.venv-litellm'
$LitellmVenvPython = Join-Path $LitellmVenvDir 'Scripts\python.exe'
$LitellmVenvExe = Join-Path $LitellmVenvDir 'Scripts\litellm.exe'

$LitellmVersion = '1.74.8'

if (-not (Test-Path $AppVenvCfg)) {
    throw "No se encontro $AppVenvCfg. Crea primero el venv de la app (.venv) antes de correr este script."
}

# Leer "home = <ruta>" de pyvenv.cfg: es la carpeta del interprete BASE que uv/venv
# uso para crear .venv (no la carpeta de .venv en si). Ahi vive python.exe real.
$homeLine = Get-Content -LiteralPath $AppVenvCfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
if (-not $homeLine) {
    throw "No se encontro la linea 'home = ...' en $AppVenvCfg -- no se puede determinar el interprete base."
}
$baseHome = ($homeLine -split '=', 2)[1].Trim()
$basePython = Join-Path $baseHome 'python.exe'
if (-not (Test-Path $basePython)) {
    throw "El interprete base referenciado por .venv (home=$baseHome) no tiene python.exe en $basePython."
}

Write-Host "Interprete base (mismo que .venv): $basePython" -ForegroundColor Cyan
Write-Host "Venv destino:                      $LitellmVenvDir" -ForegroundColor Cyan

function Test-LitellmPinOk {
    if (-not (Test-Path $LitellmVenvPython)) {
        return $false
    }
    if (-not (Test-Path $LitellmVenvExe)) {
        return $false
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $installed = & $LitellmVenvPython -m pip show litellm 2>&1
    $showExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($showExit -ne 0) {
        return $false
    }
    $versionLine = $installed | Where-Object { $_ -match '^Version:\s*(.+)$' } | Select-Object -First 1
    if (-not $versionLine) {
        return $false
    }
    $installedVersion = ($versionLine -split ':', 2)[1].Trim()
    return $installedVersion -eq $LitellmVersion
}

if (Test-LitellmPinOk) {
    Write-Host ""
    Write-Host ".venv-litellm ya existe con litellm==$LitellmVersion -- nada que hacer (idempotente)." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $LitellmVenvDir)) {
    Write-Host "Creando .venv-litellm..." -ForegroundColor Yellow
    & $basePython -m venv $LitellmVenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la creacion del venv en $LitellmVenvDir (exit $LASTEXITCODE)."
    }
}

if (-not (Test-Path $LitellmVenvPython)) {
    throw "El venv se creo pero no aparece python.exe en $LitellmVenvPython"
}

Write-Host "Instalando litellm[proxy]==$LitellmVersion en .venv-litellm (puede tardar varios minutos)..." -ForegroundColor Yellow
& $LitellmVenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Fallo 'pip install --upgrade pip' en .venv-litellm (exit $LASTEXITCODE)."
}

& $LitellmVenvPython -m pip install "litellm[proxy]==$LitellmVersion"
if ($LASTEXITCODE -ne 0) {
    throw "Fallo 'pip install litellm[proxy]==$LitellmVersion' en .venv-litellm (exit $LASTEXITCODE)."
}

if (-not (Test-LitellmPinOk)) {
    throw "Tras instalar, litellm no quedo pineado a $LitellmVersion en .venv-litellm -- revisar salida de pip arriba."
}

Write-Host ""
Write-Host "OK: .venv-litellm listo con litellm[proxy]==$LitellmVersion" -ForegroundColor Green
Write-Host "    Python:  $LitellmVenvPython" -ForegroundColor Green
Write-Host "    litellm: $LitellmVenvExe" -ForegroundColor Green
