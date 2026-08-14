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
    [string]$PgSource = '',  # ruta al pgsql portable; por defecto se autodetecta
    [ValidateSet('core', 'ocr', 'voice', 'full')]
    [string]$BackendProfile = 'core',
    [ValidateSet('Compact', 'Offline')]
    [string]$WebViewProfile = 'Compact'
)

$ErrorActionPreference = 'Stop'

$PackagingDir = $PSScriptRoot
$RepoRoot     = Split-Path -Parent $PackagingDir
$DistDir      = Join-Path $PackagingDir 'dist'
$DesktopDir   = Join-Path $RepoRoot 'desktop'
$BuildStartedUtc = [DateTime]::UtcNow
$CompactTauriConfig = Join-Path $DesktopDir 'src-tauri\tauri.compact.conf.json'
$CompactWebViewHook = Join-Path $DesktopDir 'src-tauri\windows\webview2-required.nsh'

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Get-Sha256Hex([string]$Path) {
    # .NET puro: funciona incluso si el host de PowerShell no logra cargar
    # Microsoft.PowerShell.Utility durante un build largo.
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

# Un release no puede mezclar versiones ni salir de fuentes modificadas. Los
# artefactos de build están ignorados; cualquier entrada de status restante es
# código/documentación que todavía no pertenece a un commit reproducible.
$TauriConfig = Get-Content -Raw -LiteralPath (Join-Path $DesktopDir 'src-tauri\tauri.conf.json') | ConvertFrom-Json
$FrontendPackage = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot 'frontend\package.json') | ConvertFrom-Json
$DesktopPackage = Get-Content -Raw -LiteralPath (Join-Path $DesktopDir 'package.json') | ConvertFrom-Json
$CargoVersionLine = Select-String -LiteralPath (Join-Path $DesktopDir 'src-tauri\Cargo.toml') -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $CargoVersionLine) { throw 'Cargo.toml no declara version del paquete.' }
$CargoVersion = $CargoVersionLine.Matches[0].Groups[1].Value
$Versions = @([string]$TauriConfig.version, [string]$FrontendPackage.version, [string]$DesktopPackage.version, [string]$CargoVersion)
if (@($Versions | Select-Object -Unique).Count -ne 1) {
    throw "Versiones incoherentes (tauri/frontend/desktop/cargo): $($Versions -join ' / ')"
}
$AppVersion = $Versions[0]
$SourceStatus = @(& git -C $RepoRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'No se pudo determinar el estado Git del release.' }
if ($SourceStatus.Count -gt 0) {
    throw "Release rechazado: el checkout no esta limpio.`n$($SourceStatus -join "`n")"
}
$SourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $SourceCommit) { throw 'No se pudo determinar el commit del release.' }

if ($WebViewProfile -eq 'Compact') {
    if (-not (Test-Path $CompactTauriConfig)) { throw "Falta el perfil compacto: $CompactTauriConfig" }
    if (-not (Test-Path $CompactWebViewHook)) { throw "Falta el gate de WebView2: $CompactWebViewHook" }
    $compactConfig = Get-Content -Raw -LiteralPath $CompactTauriConfig | ConvertFrom-Json
    if ([string]$compactConfig.bundle.windows.webviewInstallMode.type -ne 'skip') {
        throw "El perfil compacto debe usar WebView2 Evergreen del sistema (type=skip)."
    }
    $hookText = Get-Content -Raw -LiteralPath $CompactWebViewHook
    if ($hookText -notmatch 'F3017226-FE2A-4295-8BDF-00C3A9A7E4C5' -or $hookText -notmatch '(?m)^\s*Abort\s*$') {
        throw 'El perfil compacto no tiene un preflight WebView2 fail-closed verificable.'
    }
}

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
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_backend.ps1') -Profile $BackendProfile
    if ($LASTEXITCODE -ne 0) { throw "build_backend.ps1 fallo (exit $LASTEXITCODE)" }

    Write-Step 'Recompilando LiteLLM (PyInstaller)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_litellm.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build_litellm.ps1 fallo (exit $LASTEXITCODE)" }

    Write-Step 'Recompilando frontend (Next.js standalone)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir 'build_frontend.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build_frontend.ps1 fallo (exit $LASTEXITCODE)" }
}

$ComponentManifestPath = Join-Path $DistDir 'mia-backend\mia-component-manifest.json'
if (-not (Test-Path $ComponentManifestPath)) {
    throw 'El backend no tiene mia-component-manifest.json; no se puede afirmar que OCR/voz esten incluidos o ausentes.'
}
$ComponentManifest = Get-Content -Raw -LiteralPath $ComponentManifestPath | ConvertFrom-Json
if ([string]$ComponentManifest.profile -ne $BackendProfile) {
    throw "Perfil backend incoherente: se pidio '$BackendProfile' pero el payload declara '$($ComponentManifest.profile)'."
}
if ([bool]$ComponentManifest.source_dirty) {
    throw 'El payload backend fue construido desde fuentes sucias y no es autorizable para un release.'
}
if ([string]$ComponentManifest.source_commit -ne $SourceCommit) {
    throw 'El payload backend no corresponde al commit actual; recompila sin -SkipPayloads.'
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

# Manifiesto de integridad consumido por el backend empaquetado antes de entregar
# PGPASSWORD a pg_dump. Si un ejecutable del bundle cambia, Mia bloquea el backup
# en vez de ejecutar una herramienta sustituida.
$PgToolHashes = [ordered]@{}
foreach ($tool in @('pg_dump.exe', 'pg_restore.exe', 'pg_ctl.exe', 'pg_isready.exe')) {
    $toolPath = Join-Path $PgDest "bin\$tool"
    if (-not (Test-Path $toolPath)) { throw "pgsql copiado sin bin\$tool" }
    $PgToolHashes[$tool] = Get-Sha256Hex $toolPath
}

$PgManifest = [ordered]@{ version = 1; sha256 = $PgToolHashes } | ConvertTo-Json -Depth 3
Set-Content -LiteralPath (Join-Path $PgDest 'mia-pg-tools.sha256.json') -Value $PgManifest -Encoding UTF8

# --------------------------------------------------------------------------
# 3. Verificar que las 6 fuentes de bundle.resources existan antes del bundler
#    (Tauri aborta si una fuente de resource no existe; fallar aqui es mas claro).
# --------------------------------------------------------------------------
Write-Step 'Verificando payloads antes del bundler'
$required = @(
    (Join-Path $DistDir 'mia-backend\mia-backend.exe'),
    $ComponentManifestPath,
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

function Assert-NoPrivateBuildContent([string]$Root) {
    $forbidden = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'tests', 'test', 'docs', 'harness', '.git')
    $bad = @(Get-ChildItem -LiteralPath $Root -Recurse -Directory | Where-Object { $forbidden -contains $_.Name.ToLowerInvariant() })
    if ($bad.Count -gt 0) { throw "Payload con caches/tests/docs/harness privados:`n  $($bad.FullName -join "`n  ")" }
}
foreach ($payloadName in @('mia-backend', 'mia-litellm', 'mia-frontend', 'pgsql')) {
    Assert-NoPrivateBuildContent (Join-Path $DistDir $payloadName)
}

# Medicion real de primer arranque sobre un directorio nuevo. No reutiliza el
# perfil del usuario ni su base local; el temporal se elimina al terminar.
function Get-FreeTcpPort {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}

Write-Step 'Midiendo primer arranque sobre datos temporales limpios'
$FirstRunDir = Join-Path ([System.IO.Path]::GetTempPath()) ('mia-first-run-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $FirstRunDir | Out-Null
$FirstRunStdout = Join-Path $FirstRunDir 'stdout.log'
$FirstRunStderr = Join-Path $FirstRunDir 'stderr.log'
$FirstRunPort = Get-FreeTcpPort
$FirstRunWatch = [System.Diagnostics.Stopwatch]::StartNew()
$FirstRunProcess = $null
try {
    $backendExe = Join-Path $DistDir 'mia-backend\mia-backend.exe'
    $pgBin = Join-Path $PgDest 'bin'
    $pgData = Join-Path $FirstRunDir 'pgdata'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "$env:SystemRoot\System32\cmd.exe"
    $psi.Arguments = "/S /C `"`"$backendExe`" --first-run --pg-bin `"$pgBin`" --pg-data `"$pgData`" --pg-port $FirstRunPort > `"$FirstRunStdout`" 2> `"$FirstRunStderr`"`""
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = $FirstRunDir
    $psi.EnvironmentVariables['MIA_APP_DIR'] = $FirstRunDir
    $psi.EnvironmentVariables['MIA_BUNDLE_MANIFEST'] = $ComponentManifestPath
    $FirstRunProcess = New-Object System.Diagnostics.Process
    $FirstRunProcess.StartInfo = $psi
    [void]$FirstRunProcess.Start()
    if (-not $FirstRunProcess.WaitForExit(900000)) {
        & taskkill /T /F /PID $FirstRunProcess.Id | Out-Null
        throw 'El primer arranque excedio 15 minutos.'
    }
    if ($FirstRunProcess.ExitCode -ne 0 -or -not (Test-Path (Join-Path $FirstRunDir '.mia-setup-complete'))) {
        $tail = @()
        foreach ($log in @($FirstRunStderr, $FirstRunStdout)) {
            if (Test-Path $log) { $tail += Get-Content -LiteralPath $log -Tail 30 }
        }
        throw "Primer arranque fallido (exit $($FirstRunProcess.ExitCode)):`n$($tail -join "`n")"
    }
    $FirstRunWatch.Stop()
    $FirstRunMs = [long]$FirstRunWatch.ElapsedMilliseconds
    Write-Host "Primer arranque: $FirstRunMs ms" -ForegroundColor Green
} finally {
    if ($FirstRunProcess -and -not $FirstRunProcess.HasExited) {
        & taskkill /T /F /PID $FirstRunProcess.Id | Out-Null
    }
    if (Test-Path $FirstRunDir) { Remove-Item -LiteralPath $FirstRunDir -Recurse -Force -ErrorAction SilentlyContinue }
}

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
    if ($WebViewProfile -eq 'Compact') {
        & npm run tauri build -- --config 'src-tauri/tauri.compact.conf.json'
    } else {
        & npm run tauri build
    }
    if ($LASTEXITCODE -ne 0) { throw "npm run tauri build fallo (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# --------------------------------------------------------------------------
# 5. Reportar el instalador producido.
# --------------------------------------------------------------------------
$NsisDir = Join-Path $DesktopDir 'src-tauri\target\release\bundle\nsis'
$ExpectedSetupName = "Mia_${AppVersion}_x64-setup.exe"
$setup = Get-Item -LiteralPath (Join-Path $NsisDir $ExpectedSetupName) -ErrorAction SilentlyContinue
if ($setup) {
    if ($setup.LastWriteTimeUtc -lt $BuildStartedUtc.AddSeconds(-5)) {
        throw "El instalador esperado existe pero es anterior a esta corrida: $($setup.FullName)"
    }
    $sizeMB = [math]::Round($setup.Length / 1MB, 1)
    $setupSha = Get-Sha256Hex $setup.FullName
    $payloads = [ordered]@{}
    foreach ($payloadName in @('mia-backend', 'mia-litellm', 'mia-frontend', 'pgsql')) {
        $payloadPath = Join-Path $DistDir $payloadName
        $payloadFiles = @(Get-ChildItem -LiteralPath $payloadPath -Recurse -File)
        $payloads[$payloadName] = [ordered]@{
            files = $payloadFiles.Count
            bytes = [long](($payloadFiles | Measure-Object -Property Length -Sum).Sum)
        }
    }
    $installedPayloadBytes = [long](($payloads.Values | ForEach-Object { $_.bytes } | Measure-Object -Sum).Sum)
    # La meta comercial se expresa en MB decimales, no en MiB de PowerShell.
    $targetInstallerBytes = [long](335 * 1000 * 1000)
    $targetApplicable = $WebViewProfile -eq 'Compact'
    $manifest = [ordered]@{
        schema_version = 1
        product = 'Mia'
        version = $AppVersion
        commit = $SourceCommit
        created_at_utc = [DateTime]::UtcNow.ToString('o')
        reused_payloads = [bool]$SkipPayloads
        backend_profile = $BackendProfile
        webview_profile = $WebViewProfile.ToLowerInvariant()
        capabilities = $ComponentManifest.capabilities
        first_run_ms = $FirstRunMs
        installed_payload_bytes = $installedPayloadBytes
        target_installer_bytes = $targetInstallerBytes
        target_applicable = [bool]$targetApplicable
        target_met = if ($targetApplicable) { [bool]($setup.Length -le $targetInstallerBytes) } else { $null }
        installer = [ordered]@{ file = $setup.Name; bytes = $setup.Length; sha256 = $setupSha }
        payloads = $payloads
    }
    $manifestPath = Join-Path $NsisDir 'mia-release-manifest.json'
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Step "INSTALADOR LISTO"
    Write-Host "  $($setup.FullName)" -ForegroundColor Green
    Write-Host "  $sizeMB MB" -ForegroundColor Green
    Write-Host "  SHA-256 $setupSha" -ForegroundColor Green
    Write-Host "  Manifiesto $manifestPath" -ForegroundColor Green
    if (-not $targetApplicable) {
        Write-Host '  Perfil Offline: incluye WebView2; la meta de 335 MB no aplica a esta variante de compatibilidad.' -ForegroundColor Yellow
    } elseif ($setup.Length -le $targetInstallerBytes) {
        Write-Host '  Meta de instalador <=335 MB: CUMPLIDA y medida.' -ForegroundColor Green
    } else {
        Write-Host '  Meta de instalador <=335 MB: NO cumplida; no se declara ahorro sin evidencia.' -ForegroundColor Yellow
    }
    if ($SkipPayloads) {
        Write-Host '  ADVERTENCIA: reutilizo payloads; este artefacto NO es autorizable como release final.' -ForegroundColor Yellow
    }
} else {
    throw "El bundler termino sin error pero no produjo el nombre/version esperados: $ExpectedSetupName"
}
