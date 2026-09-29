<#
  .SYNOPSIS
    Mia · build_frontend.ps1 — ensambla el frontend Next.js 14 como paquete
    autocontenido para el instalador (Fase 1, bloque instalador, frente B).

  .DESCRIPTION
    1. Corre `npm run build` en frontend/ (genera .next/standalone gracias a
       `output: "standalone"` en next.config.mjs).
    2. Ensambla packaging/dist/mia-frontend/ con:
         - server.js + node_modules mínimos (de .next/standalone/)
         - .next/static  (assets del cliente — standalone NO los incluye solo)
         - public/       (si existe — standalone tampoco lo incluye)
         - node.exe      (Node portable, SOLO el binario — no se necesita npm
                          para correr un server.js ya compilado)
    3. Prueba de humo: arranca el ensamblado con el node.exe PORTABLE (no el
       del PATH), espera código 200 en GET /, y lo apaga. Si el puerto pedido
       ya está ocupado (squatter), busca automáticamente uno libre desde 3190;
       si el proceso muere durante el arranque, conserva las rutas de sus logs y
       aborta de inmediato (no espera el timeout completo); y tras el 200,
       confirma que el proceso que sigue vivo y escuchando en el puerto es
       realmente el nuestro (fix Fase 1 · capa 2 · M3).

    El binario de Node portable se selecciona por PIN EXACTO (packaging\
    node-version.txt, hoy "v22.23.1") — nunca "la primera carpeta node-v*
    que aparezca" (fix Fase 1 · capa 2 · m6), para que el build sea
    determinista si algún día conviven dos versiones en tools\node-portable\.

    Gotcha documentado (verificado empíricamente 2026-07-10): server.js hace
    `const hostname = process.env.HOSTNAME || '0.0.0.0'`. En máquinas donde
    HOSTNAME ya está seteado en el entorno (ej. Windows expone HOSTNAME=<nombre
    de equipo>, y ese nombre puede resolver a una IP de VPN/Tailscale en vez de
    loopback), el server escucha SOLO en esa IP y "localhost" no conecta. Este
    script siempre limpia $env:HOSTNAME antes de lanzar node para forzar bind
    en 0.0.0.0. El instalador final debe replicar esto (no heredar HOSTNAME del
    entorno del usuario).

  .PARAMETER SkipBuild
    Omite `npm run build` y reusa el .next existente (útil para iterar rápido
    sobre el ensamblado/empaquetado sin recompilar).

  .PARAMETER SkipSmokeTest
    Omite la prueba de humo tras ensamblar (no recomendado).

  .PARAMETER Port
    Puerto para la prueba de humo. Default 3100 (el puerto real del frontend).

  .EXAMPLE
    powershell -File packaging\build_frontend.ps1
#>

param(
    [switch]$SkipBuild,
    [switch]$SkipSmokeTest,
    [int]$Port = 3100
)

$ErrorActionPreference = "Stop"

$RepoRoot     = Split-Path -Parent $PSScriptRoot
$FrontendDir  = Join-Path $RepoRoot "frontend"
$DistDir      = Join-Path $RepoRoot "packaging\dist\mia-frontend"
$ToolsNodeDir = Join-Path (Split-Path -Parent $RepoRoot) "tools\node-portable"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "== $msg ==" -ForegroundColor Cyan
}

function Get-DirSizeMB($path) {
    if (-not (Test-Path $path)) { return 0 }
    $bytes = (Get-ChildItem -Recurse -File -Force $path | Measure-Object -Property Length -Sum).Sum
    return [math]::Round($bytes / 1MB, 1)
}

# ---------------------------------------------------------------------------
# 1. Build
# ---------------------------------------------------------------------------
if (-not $SkipBuild) {
    Write-Step "npm run build (frontend/)"
    Push-Location $FrontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build salió con código $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
} else {
    Write-Step "SkipBuild activo: se reusa .next existente"
}

$StandaloneDir = Join-Path $FrontendDir ".next\standalone"
$ServerJs      = Join-Path $StandaloneDir "server.js"
if (-not (Test-Path $ServerJs)) {
    throw "No existe $ServerJs. ¿Falta 'output: `"standalone`"' en next.config.mjs, o falló el build?"
}

# ---------------------------------------------------------------------------
# 2. Localizar node.exe portable (versión FIJADA por pin, fix Fase 1 · capa 2 · m6)
# ---------------------------------------------------------------------------
# Antes este paso tomaba "la primera carpeta node-v*-win-x64 que aparezca" —
# no determinista si alguna vez conviven dos versiones de Node portable en
# tools\node-portable\ (p. ej. tras una actualización manual a medias). Ahora
# el script exige la versión EXACTA declarada en packaging\node-version.txt.
Write-Step "Localizando Node portable en $ToolsNodeDir (pin: node-version.txt)"
$NodeVersionPinFile = Join-Path $PSScriptRoot "node-version.txt"
if (-not (Test-Path $NodeVersionPinFile)) {
    throw "No se encontró el pin de versión de Node: $NodeVersionPinFile. Crea el archivo con una sola línea 'vX.Y.Z' (ej. v22.23.1) para fijar determinismo del build."
}
$PinnedVersion = (Get-Content $NodeVersionPinFile -Raw).Trim()
if (-not $PinnedVersion) {
    throw "$NodeVersionPinFile está vacío. Debe contener la versión exacta de Node portable a usar (ej. v22.23.1)."
}
$ExpectedFolderName = "node-$PinnedVersion-win-x64"
$NodeVersionDirs = @(Get-ChildItem -Path $ToolsNodeDir -Directory -Filter $ExpectedFolderName -ErrorAction SilentlyContinue)
if ($NodeVersionDirs.Count -eq 0) {
    $available = Get-ChildItem -Path $ToolsNodeDir -Directory -Filter "node-v*-win-x64" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Name
    $availableTxt = if ($available) { $available -join ", " } else { "(ninguna)" }
    throw "No se encontró la versión de Node pineada ($PinnedVersion) en $ToolsNodeDir\$ExpectedFolderName. Carpetas disponibles: $availableTxt. Descarga exactamente $PinnedVersion desde nodejs.org/dist, o actualiza el pin en $NodeVersionPinFile si el cambio de versión es intencional (ver packaging\README-frontend.md)."
}
if ($NodeVersionDirs.Count -gt 1) {
    throw "Ambigüedad: se encontró más de una carpeta '$ExpectedFolderName' en $ToolsNodeDir. Deja solo una."
}
$NodeVersionDir = $NodeVersionDirs[0]
$NodeExe = Join-Path $NodeVersionDir.FullName "node.exe"
if (-not (Test-Path $NodeExe)) {
    throw "No se encontró node.exe dentro de $($NodeVersionDir.FullName)"
}
Write-Host "  Node portable (pin $PinnedVersion): $($NodeVersionDir.Name) -> $NodeExe"

# ---------------------------------------------------------------------------
# 3. Ensamblar packaging/dist/mia-frontend/
# ---------------------------------------------------------------------------
Write-Step "Ensamblando $DistDir"
if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# 3a. server.js + node_modules mínimos + package.json (todo lo que standalone genera)
Copy-Item -Path (Join-Path $StandaloneDir "*") -Destination $DistDir -Recurse -Force

# 3b. assets estáticos del cliente (standalone NO los incluye por diseño de Next)
$StaticSrc = Join-Path $FrontendDir ".next\static"
$StaticDst = Join-Path $DistDir ".next\static"
if (-not (Test-Path $StaticSrc)) { throw "No existe $StaticSrc — build incompleto." }
New-Item -ItemType Directory -Path (Join-Path $DistDir ".next") -Force | Out-Null
Copy-Item -Path $StaticSrc -Destination $StaticDst -Recurse -Force

# 3c. public/ (si existe — hoy el repo no tiene carpeta public/)
$PublicSrc = Join-Path $FrontendDir "public"
if (Test-Path $PublicSrc) {
    Copy-Item -Path $PublicSrc -Destination (Join-Path $DistDir "public") -Recurse -Force
    Write-Host "  public/ copiado."
} else {
    Write-Host "  (frontend/public no existe hoy — nada que copiar; el ensamblaje lo soporta si aparece)"
}

# 3d. node.exe portable (solo el binario; no se necesita npm para correr server.js ya compilado)
Copy-Item -Path $NodeExe -Destination (Join-Path $DistDir "node.exe") -Force

$DistSizeMB = Get-DirSizeMB $DistDir
Write-Host ""
Write-Host "Ensamblado en: $DistDir"
Write-Host "Tamaño total del ensamblado: $DistSizeMB MB"

# ---------------------------------------------------------------------------
# 4. Prueba de humo — SOLO con el node.exe portable, no el del PATH
# ---------------------------------------------------------------------------
if ($SkipSmokeTest) {
    Write-Step "SkipSmokeTest activo: no se prueba el ensamblado"
    return
}

Write-Step "Prueba de humo (puerto $Port) con node.exe portable"

# Gotcha HOSTNAME (ver docstring arriba): limpiar antes de lanzar.
$prevHostname = $env:HOSTNAME

# ---------------------------------------------------------------------------
# 4a. Selección robusta de puerto (fix Fase 1 · capa 2 · M3)
# ---------------------------------------------------------------------------
# Si el puerto pedido ya tiene ALGO escuchando, el node.exe empaquetado muere
# con EADDRINUSE al arrancar, y sin este chequeo el lazo de polling de más
# abajo puede recibir un 200 de ESE OTRO proceso ("squatter") — dando un PASS
# falso sin haber probado nuestro propio ensamblado. En vez de asumir que el
# puerto está libre, lo verificamos primero; si está ocupado, buscamos
# automáticamente uno libre en un rango alto poco probable de chocar con los
# servicios reales de Mia (3100 frontend real, 8000/8099 backend, 55432
# Postgres), en vez de simplemente abortar el build por una colisión de humo.
function Test-PortListening([int]$TestPort) {
    $conn = Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue
    if ($conn) { return $true }
    # Fallback si Get-NetTCPConnection no está disponible o no ve el listener:
    # intento de conexión TCP directa con timeout corto.
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect("127.0.0.1", $TestPort, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(200)
        $isConnected = $connected -and $client.Connected
        $client.Close()
        return [bool]$isConnected
    } catch {
        return $false
    }
}

$RequestedPort = $Port
if (Test-PortListening -TestPort $Port) {
    Write-Host "  Puerto $Port ya tiene algo escuchando (posible squatter) -- buscando puerto libre desde 3190..." -ForegroundColor Yellow
    $foundFreePort = $false
    for ($candidate = 3190; $candidate -le 3290; $candidate++) {
        if (-not (Test-PortListening -TestPort $candidate)) {
            $Port = $candidate
            $foundFreePort = $true
            break
        }
    }
    if (-not $foundFreePort) {
        throw "El puerto $RequestedPort está ocupado y no se encontró ninguno libre en el rango 3190-3290 para la prueba de humo. Libera un puerto o pasa -Port explícito."
    }
    Write-Host "  Puerto libre encontrado: $Port" -ForegroundColor Yellow
}
$prevPort = $env:PORT
$env:PORT = "$Port"

$proc = $null
try {
    $smokeLogBase = Join-Path ([System.IO.Path]::GetTempPath()) ("mia-frontend-smoke-" + [Guid]::NewGuid().ToString('N'))
    $stdoutLog = "$smokeLogBase.stdout.log"
    $stderrLog = "$smokeLogBase.stderr.log"
    Remove-Item Env:\HOSTNAME -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath (Join-Path $DistDir "node.exe") `
        -ArgumentList "server.js" `
        -WorkingDirectory $DistDir `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError  $stderrLog
    # Keep the process handle so PowerShell 5 can report an early exit code.
    $null = $proc.Handle

    # Gotcha verificado empíricamente (2026-07-10): en esta máquina "localhost" resuelve
    # primero a ::1 (IPv6) vía Invoke-WebRequest/.NET, y como Node solo escucha en la
    # interfaz IPv4 (0.0.0.0), la petición a "localhost" se queda esperando el fallback a
    # IPv4 y agota el TimeoutSec sin conectar (Test-NetConnection confirmó: TCP a ::1
    # falla, TCP a 127.0.0.1 conecta). Se usa 127.0.0.1 explícito para evitar esta espera.
    $ready = $false
    $deadline = (Get-Date).AddSeconds(180)
    $lastProbe = "No request completed"
    while ((Get-Date) -lt $deadline) {
        # Fix M3: si el proceso ya murió (crash de arranque, EADDRINUSE tardío,
        # etc.), seguir haciendo polling hasta agotar el timeout solo produce un
        # mensaje genérico e inútil. Detectamos la muerte del proceso de
        # inmediato y conservamos sus logs fuera del payload al abortar.
        if ($proc.HasExited) {
            $proc.WaitForExit()
            Write-Host "  El proceso node.exe (PID $($proc.Id)) terminó inesperadamente (exit code $($proc.ExitCode)) durante el arranque." -ForegroundColor Red
            throw "El proceso del ensamblado terminó antes de responder (exit code $($proc.ExitCode)); ultimo sondeo: $lastProbe."
        }
        Start-Sleep -Milliseconds 500
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 4
            $lastProbe = "HTTP $($resp.StatusCode)"
            if ($resp.StatusCode -eq 200) { $ready = $true; break }
        } catch {
            # Retain only error type/status; response bodies and private values stay out of diagnostics.
            $httpCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'none' }
            $networkStatus = if ($_.Exception -is [System.Net.WebException]) { $_.Exception.Status } else { 'none' }
            $lastProbe = "type=$($_.Exception.GetType().Name); status=$networkStatus; HTTP=$httpCode"
        }
    }

    if (-not $ready) {
        throw "El ensamblado no respondió 200 en http://127.0.0.1:$Port/ dentro de 180s; ultimo sondeo: $lastProbe."
    }

    Write-Host "  GET / -> $($resp.StatusCode) OK"

    # Fix M3 -- verificación de identidad mínima: un 200 no basta para probar
    # que fue NUESTRO proceso quien respondió (condición de carrera: otro
    # proceso pudo tomar el puerto justo después de verificarlo libre, o el
    # nuestro pudo morir justo tras responder). Confirmamos (a) que $proc
    # sigue vivo TRAS la respuesta, y (b) que el proceso que realmente escucha
    # ahora mismo en $Port es, en efecto, $proc.Id.
    if ($proc.HasExited) {
        throw "El proceso $($proc.Id) ya había terminado cuando llegó la respuesta 200 -- ese 200 no puede venir de nuestro ensamblado. Posible squatter en el puerto $Port."
    }
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $proc.Id }
    if (-not $listener) {
        throw "El puerto $Port respondió 200 pero el proceso que escucha no es nuestro node.exe (PID $($proc.Id)) -- posible squatter. Se aborta el PASS."
    }
    Write-Host "  Identidad confirmada: PID $($proc.Id) (nuestro node.exe) es quien escucha en el puerto $Port."

    $hasXFO = $resp.Headers["X-Frame-Options"] -eq "DENY"
    $hasXCTO = $resp.Headers["X-Content-Type-Options"] -eq "nosniff"
    Write-Host "  X-Frame-Options: $($resp.Headers['X-Frame-Options'])"
    Write-Host "  X-Content-Type-Options: $($resp.Headers['X-Content-Type-Options'])"
    if (-not ($hasXFO -and $hasXCTO)) {
        throw "Faltan cabeceras de seguridad en la respuesta del ensamblado."
    }

    Write-Host ""
    Write-Host "PRUEBA DE HUMO: PASS" -ForegroundColor Green
} catch {
    Write-Host "Logs conservados fuera del payload: $stdoutLog ; $stderrLog"
    throw
} finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        [void]$proc.WaitForExit(5000)
    }
    if ($null -ne $prevHostname) { $env:HOSTNAME = $prevHostname }
    else { Remove-Item Env:\HOSTNAME -ErrorAction SilentlyContinue }
    if ($null -ne $prevPort) { $env:PORT = $prevPort }
    else { Remove-Item Env:\PORT -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "Tamaño final del ensamblado: $(Get-DirSizeMB $DistDir) MB"
