# Mia - F4 - build del instalador final (NSIS, doble clic).
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
#
# Ensambla el instalador de escritorio que un abogado instala con doble clic,
# SIN Python/Node/Postgres en su maquina. La cascara Tauri (mia-desktop.exe)
# orquesta 4 servicios leyendo orchestration.json junto al exe; este script deja
# junto al exe TODOS los payloads que ese JSON referencia via ${exe_dir}/...:
#
#   ${exe_dir}\mia-backend\      (PyInstaller onedir, con --first-run + .sql + welcome)
#   ${exe_dir}\mia-litellm\      (PyInstaller onedir, proxy de modelos, loopback default)
#   ${exe_dir}\mia-frontend\     (Next.js standalone + node.exe portable)
#   ${exe_dir}\pgsql\            (PostgreSQL 16 portable + pgvector)
#   ${exe_dir}\litellm_config.installer.yaml
#   ${exe_dir}\orchestration.json   (renombrado de orchestration.installer.json)
#
# El wiring "junto al exe" lo declara desktop/src-tauri/tauri.conf.json en
# bundle.resources (mapa con destino explicito). Este script solo garantiza que
# las CARPETAS FUENTE existan en packaging/dist/ antes de invocar el bundler, y
# corre el bundler NSIS de Tauri.
#
# El renombrado orchestration.installer.json -> orchestration.json lo hace el
# propio mapa de resources de tauri.conf.json (destino "orchestration.json").
# Aqui NO se renombra nada: la cascara busca literalmente "orchestration.json"
# junto al exe (lib.rs find_config).
#
# Uso:
#   powershell -File packaging\build_installer.ps1                 # build completo
#   powershell -File packaging\build_installer.ps1 -SkipPayloads   # reusa dist/ ya compilado
#   powershell -File packaging\build_installer.ps1 -PayloadsOnly   # ensambla payloads, NO corre el bundler
#
# Salida del bundler: desktop/src-tauri/target/release/bundle/nsis/*-setup.exe

param(
    [switch]$SkipPayloads,   # no recompila backend/litellm/frontend; reusa packaging/dist/
    [switch]$PayloadsOnly,   # deja los payloads listos pero no corre cargo tauri build
    [string]$PgSource = ''   # ruta al pgsql portable; por defecto se autodetecta
)

$ErrorActionPreference = 'Stop'

$PackagingDir = $PSScriptRoot
$RepoRoot     = Split-Path -Parent $PackagingDir
$DistDir      = Join-Path $PackagingDir 'dist'
$DesktopDir   = Join-Path $RepoRoot 'desktop'

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# --------------------------------------------------------------------------
# 0. Autodeteccion del Postgres portable (con pgvector) si no se paso -PgSource.
#    En el entorno de dev vive fuera del repo, en <parent>\tools\...\pgsql.
# --------------------------------------------------------------------------
if (-not $PgSource) {
    $candidates = @(
        (Join-Path (Split-Path -Parent $RepoRoot) 'tools\postgres16-portable-full\pgsql'),
        (Join-Path $RepoRoot 'tools\postgres16-portable-full\pgsql')
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c 'bin\initdb.exe')) { $PgSource = $c; break }
    }
}
if (-not $PgSource -or -not (Test-Path (Join-Path $PgSource 'bin\initdb.exe'))) {
    throw "No se encontro el PostgreSQL portable. Pasa -PgSource '<ruta a ...\pgsql>' (debe contener bin\initdb.exe)."
}
# Verificacion dura: pgvector DEBE estar (MIA lo exige; una PG16 vanilla no lo trae).
if (-not (Test-Path (Join-Path $PgSource 'lib\vector.dll'))) {
    throw "El Postgres portable en '$PgSource' NO tiene pgvector (lib\vector.dll). MIA no arrancaria."
}
Write-Host "Postgres portable: $PgSource" -ForegroundColor Green

# --------------------------------------------------------------------------
# 1. Recompilar los 3 payloads Python/Node (a menos que -SkipPayloads).
#    Secuencial a proposito: nunca 2 builds de Next concurrentes; y los
#    PyInstaller comparten packaging/build/ como WorkPath.
# --------------------------------------------------------------------------
if ($SkipPayloads) {
    Write-Step 'Payloads: -SkipPayloads (reusando packaging/dist/ existente)'
} else {
    Write-Step 'Recompilando backend (PyInstaller)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_backend.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build_backend.ps1 fallo (exit $LASTEXITCODE)" }

    Write-Step 'Recompilando LiteLLM (PyInstaller)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_litellm.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build_litellm.ps1 fallo (exit $LASTEXITCODE)" }

    Write-Step 'Recompilando frontend (Next.js standalone)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_frontend.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build_frontend.ps1 fallo (exit $LASTEXITCODE)" }
}

# --------------------------------------------------------------------------
# 2. Copiar el Postgres portable a packaging/dist/pgsql (ruta in-repo estable
#    que tauri.conf.json referencia). robocopy /MIR es idempotente y rapido.
#    Codigos de salida de robocopy 0-7 = exito (8+ = error real).
# --------------------------------------------------------------------------
Write-Step 'Copiando Postgres portable a packaging/dist/pgsql'
$PgDest = Join-Path $DistDir 'pgsql'
# EXCLUSIONES (capa 2 · sesion 45): el pgsql portable trae pgAdmin 4 (~700 MB,
# un panel web de administracion con su propio Python) y StackBuilder, que MIA
# NUNCA lanza (solo usa bin/lib/share via psycopg + initdb/pg_ctl). Empaquetarlos
# infla el disco del abogado y deja una app admin como superficie de ataque
# innecesaria. doc/ e include/ tampoco se usan en runtime. Se excluyen.
$PgExcludeDirs = @('pgAdmin 4', 'StackBuilder', 'doc', 'include')
$xd = @()
foreach ($d in $PgExcludeDirs) { $xd += '/XD'; $xd += (Join-Path $PgSource $d) }
$null = robocopy $PgSource $PgDest /MIR @xd /NFL /NDL /NJH /NJS /NP /R:2 /W:2
if ($LASTEXITCODE -ge 8) { throw "robocopy del pgsql fallo (exit $LASTEXITCODE)" }
$global:LASTEXITCODE = 0
# Barrido de seguridad: /XD no purga carpetas ya presentes en el destino de una
# corrida previa SIN exclusiones -> las quitamos explicitamente para que no
# viajen al instalador.
foreach ($d in $PgExcludeDirs) {
    $p = Join-Path $PgDest $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
if (-not (Test-Path (Join-Path $PgDest 'bin\initdb.exe'))) { throw "pgsql copiado sin bin\initdb.exe" }
if (-not (Test-Path (Join-Path $PgDest 'lib\vector.dll'))) { throw "pgsql copiado sin lib\vector.dll (pgvector)" }
if (Test-Path (Join-Path $PgDest 'pgAdmin 4')) { throw "pgAdmin 4 no se excluyo del pgsql copiado" }

# --------------------------------------------------------------------------
# 3. Verificar que las 6 fuentes de bundle.resources existan antes del bundler
#    (Tauri aborta si una fuente de resource no existe; fallar aqui es mas claro).
# --------------------------------------------------------------------------
Write-Step 'Verificando payloads antes del bundler'
$required = @(
    (Join-Path $DistDir 'mia-backend\mia-backend.exe'),
    (Join-Path $DistDir 'mia-litellm\mia-litellm.exe'),
    (Join-Path $DistDir 'mia-frontend\server.js'),
    (Join-Path $DistDir 'mia-frontend\node.exe'),
    (Join-Path $DistDir 'pgsql\bin\initdb.exe'),
    (Join-Path $PackagingDir 'litellm_config.installer.yaml'),
    (Join-Path $PackagingDir 'orchestration.installer.json')
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "Faltan payloads requeridos:`n  $($missing -join "`n  ")" }
Write-Host "Todos los payloads presentes." -ForegroundColor Green

if ($PayloadsOnly) {
    Write-Step 'PayloadsOnly: payloads listos; NO se corre el bundler'
    Write-Host "Para producir el instalador: cd desktop; npm run tauri build" -ForegroundColor Yellow
    return
}

# --------------------------------------------------------------------------
# 4. Correr el bundler NSIS de Tauri. La CLI local vive en desktop/node_modules.
#    Produce desktop/src-tauri/target/release/bundle/nsis/*-setup.exe.
# --------------------------------------------------------------------------
Write-Step 'Corriendo el bundler NSIS de Tauri (npm run tauri build)'
Push-Location $DesktopDir
try {
    & npm run tauri build
    if ($LASTEXITCODE -ne 0) { throw "npm run tauri build fallo (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# --------------------------------------------------------------------------
# 5. Reportar el instalador producido.
# --------------------------------------------------------------------------
$NsisDir = Join-Path $DesktopDir 'src-tauri\target\release\bundle\nsis'
$setup = Get-ChildItem -Path $NsisDir -Filter '*-setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($setup) {
    $sizeMB = [math]::Round($setup.Length / 1MB, 1)
    Write-Step "INSTALADOR LISTO"
    Write-Host "  $($setup.FullName)" -ForegroundColor Green
    Write-Host "  $sizeMB MB" -ForegroundColor Green
} else {
    throw "El bundler termino sin error pero no se encontro *-setup.exe en $NsisDir"
}
