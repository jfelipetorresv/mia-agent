# Mia - build reproducible del proxy LiteLLM empaquetado (PyInstaller onedir).
# ASCII puro a proposito (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
#
# Usa SIEMPRE el pyinstaller instalado dentro de .venv-litellm (nunca el de la
# app .venv, ni uno global), igual criterio que packaging\build_backend.ps1 pero
# aplicado al venv DEDICADO del proxy (packaging\setup_venv_litellm.ps1 debe
# haberse corrido antes -- este script NO lo crea, solo lo consume).
#
# Tras el build corre un HUMO REAL: lanza mia-litellm.exe con el config
# instalador y una master key de prueba, valida /health/liveliness (200),
# /v1/models con Bearer (200 + alias del config) y /v1/models SIN Bearer
# (401/403), y mata el proceso. El humo FALLA EL BUILD si algo no cuadra --
# no es un warning opcional (a diferencia del smoke de OCR de build_backend.ps1).
#
# Uso:  powershell -File packaging\build_litellm.ps1
$ErrorActionPreference = 'Stop'

$PackagingDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $PackagingDir
$LitellmVenvDir = Join-Path $RepoRoot '.venv-litellm'
$LitellmVenvPython = Join-Path $RepoRoot '.venv-litellm\Scripts\python.exe'
$LitellmVenvPyInstaller = Join-Path $RepoRoot '.venv-litellm\Scripts\pyinstaller.exe'
$SpecFile = Join-Path $PackagingDir 'mia-litellm.spec'
$ConfigInstaller = Join-Path $PackagingDir 'litellm_config.installer.yaml'
$DistBase = Join-Path $PackagingDir 'dist'
$WorkBase = Join-Path $PackagingDir 'build'
$OutDir = Join-Path $DistBase 'mia-litellm'
$WorkSubDir = Join-Path $WorkBase 'mia-litellm'

$ExpectedLitellmVersion = '1.74.8'

if (-not (Test-Path $LitellmVenvPython)) {
    throw "No se encontro $LitellmVenvPython. Corre primero: powershell -File packaging\setup_venv_litellm.ps1"
}
if (-not (Test-Path $SpecFile)) {
    throw "No se encontro el spec: $SpecFile"
}
if (-not (Test-Path $ConfigInstaller)) {
    throw "No se encontro el config instalador: $ConfigInstaller"
}

function Get-InstalledVersion {
    param([string]$PythonExe, [string]$PackageName)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = & $PythonExe -m pip show $PackageName 2>&1
    $exit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($exit -ne 0) {
        return $null
    }
    $versionLine = $out | Where-Object { $_ -match '^Version:\s*(.+)$' } | Select-Object -First 1
    if (-not $versionLine) {
        return $null
    }
    return ($versionLine -split ':', 2)[1].Trim()
}

# --- pyinstaller pineado en .venv-litellm (--no-deps + pines propios) ------
# Mismos pines que build_backend.ps1 (misma version de Python 3.11 base para
# ambos venvs -- ver setup_venv_litellm.ps1), MAS pyinstaller-hooks-contrib:
# build_backend.ps1 no lo pinea porque en el venv de la app ya estaba presente
# (2026.6), pero aqui es OBLIGATORIO -- trae hook-certifi, sin el cual el exe
# muere en el import de litellm con FileNotFoundError (certifi.where() apunta
# fuera del bundle; leccion del primer build real 2026-07-10, ver el
# comentario "certifi EXPLICITO" en mia-litellm.spec).
$PyInstallerVersion  = '6.21.0'
$AltgraphVersion     = '0.17.5'
$PefileVersion       = '2024.8.26'
$PywinCtypesVersion  = '0.2.3'
$HooksContribVersion = '2026.6'

$hooksContribInstalled = Get-InstalledVersion -PythonExe $LitellmVenvPython -PackageName 'pyinstaller-hooks-contrib'
if ((-not (Test-Path $LitellmVenvPyInstaller)) -or ($hooksContribInstalled -ne $HooksContribVersion)) {
    Write-Host "Instalando pyinstaller + hooks pineados en .venv-litellm (--no-deps, sin tocar el pin de litellm)..." -ForegroundColor Yellow
    & $LitellmVenvPython -m pip install --quiet --no-deps `
        "pyinstaller==$PyInstallerVersion" `
        "altgraph==$AltgraphVersion" `
        "pefile==$PefileVersion" `
        "pywin32-ctypes==$PywinCtypesVersion" `
        "pyinstaller-hooks-contrib==$HooksContribVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la instalacion de pyinstaller (--no-deps) en .venv-litellm."
    }
    if (-not (Test-Path $LitellmVenvPyInstaller)) {
        throw "pyinstaller se instalo pero no aparece en $LitellmVenvPyInstaller"
    }

    # GATE DURO: check_env_pins.py (Riesgo #32) NO aplica a este venv (no tiene
    # fastapi/uvicorn/etc. de la app) -- el equivalente aqui es verificar que
    # instalar pyinstaller no corrio pip resolver y desvio litellm de su pin.
    Write-Host "Verificando que litellm sigue en $ExpectedLitellmVersion tras instalar pyinstaller..." -ForegroundColor Cyan
    $litellmVersionAfter = Get-InstalledVersion -PythonExe $LitellmVenvPython -PackageName 'litellm'
    if ($litellmVersionAfter -ne $ExpectedLitellmVersion) {
        throw "litellm quedo en '$litellmVersionAfter' (esperado $ExpectedLitellmVersion) tras instalar pyinstaller en .venv-litellm. Build ABORTADO antes de compilar -- recrea el venv (setup_venv_litellm.ps1) e investiga el resolver de pip."
    }
    Write-Host "litellm==$ExpectedLitellmVersion OK tras instalar pyinstaller. Continuando con el build." -ForegroundColor Green
} else {
    $litellmVersionNow = Get-InstalledVersion -PythonExe $LitellmVenvPython -PackageName 'litellm'
    if ($litellmVersionNow -ne $ExpectedLitellmVersion) {
        throw "litellm esta en '$litellmVersionNow' en .venv-litellm (esperado $ExpectedLitellmVersion). Recrea el venv: powershell -File packaging\setup_venv_litellm.ps1"
    }
}

Write-Host "Repo:        $RepoRoot" -ForegroundColor Cyan
Write-Host "PyInstaller: $LitellmVenvPyInstaller" -ForegroundColor Cyan
Write-Host "Spec:        $SpecFile" -ForegroundColor Cyan

# Solo se limpia el subdirectorio DE ESTE bundle (mia-litellm), nunca dist/ ni
# build/ completos: ambos son compartidos con mia-backend.spec (E1) y borrarlos
# enteros destruiria un build del backend ya compilado (archivos por ejecutor
# disjuntos, plan F2).
# Borrado robusto (sesion 52): ver build_backend.ps1. El arbol onedir de
# PyInstaller supera MAX_PATH y Remove-Item aborta el build entero.
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

Remove-TreeRobusto $OutDir
Remove-TreeRobusto $WorkSubDir

$start = Get-Date
# Igual que build_backend.ps1: PyInstaller escribe su log INFO/WARNING a
# stderr, y con ErrorActionPreference='Stop' eso mataria el build de inmediato
# aunque el proceso vaya a salir con exit 0. Se valida con $LASTEXITCODE, no
# con la promocion automatica de stderr a excepcion.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $LitellmVenvPyInstaller $SpecFile --distpath $DistBase --workpath $WorkBase --noconfirm
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
$elapsed = (Get-Date) - $start

if ($exitCode -ne 0) {
    throw "PyInstaller termino con codigo $exitCode (duracion $($elapsed.ToString('mm\:ss')))"
}

$exePath = Join-Path $OutDir 'mia-litellm.exe'
if (-not (Test-Path $exePath)) {
    throw "El build termino OK pero no se encontro el ejecutable: $exePath"
}

$sizeBytes = (Get-ChildItem -Recurse $OutDir | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($sizeBytes / 1MB, 1)

Write-Host ""
Write-Host "Build OK en $($elapsed.ToString('mm\:ss'))" -ForegroundColor Green
Write-Host "Salida:      $OutDir" -ForegroundColor Green
Write-Host "Tamano:      $sizeMB MB" -ForegroundColor Green

# ---------------------------------------------------------------------------
# HUMO real post-build (NO opcional -- falla el build si algo no cuadra).
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Humo post-build: arrancando mia-litellm.exe real..." -ForegroundColor Cyan

function Get-FreeTcpPort {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

$smokePort = Get-FreeTcpPort
$smokeMasterKey = 'sk-mia-smoketest-' + [Guid]::NewGuid().ToString('N')
$smokeAppDir = Join-Path $env:TEMP ('mia-litellm-smoke-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $smokeAppDir | Out-Null
# OJO: $smokeAppDir se deja A PROPOSITO sin .env -- si entry_litellm.py tuviera
# un bug y SI leyera el .env real del repo, este humo lo detectaria (el .env
# real no tiene la master key de prueba, /v1/models con Bearer fallaria).

$baseUrl = "http://127.0.0.1:$smokePort"
$proc = $null
$smokeOk = $true
$smokeFailures = @()
$smokeLogTail = @()
# stdout/stderr del exe van a ARCHIVOS (no a pipes de .NET sin lector: si el
# proxy loguea mas de lo que cabe en el buffer del pipe, el hijo se BLOQUEA a
# mitad de un write y el humo falla por timeout sin causa visible). Ademas los
# archivos permiten reportar el traceback real cuando el humo falla.
$smokeOutLog = Join-Path $smokeAppDir 'litellm-stdout.log'
$smokeErrLog = Join-Path $smokeAppDir 'litellm-stderr.log'

try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    # Se lanza via cmd /S /C para poder redirigir stdout/stderr a archivos sin
    # lectores de pipe; taskkill /T (arbol) mata cmd y al exe hijo juntos.
    $psi.FileName = "$env:SystemRoot\System32\cmd.exe"
    $psi.Arguments = "/S /C `"`"$exePath`" --config `"$ConfigInstaller`" --port $smokePort > `"$smokeOutLog`" 2> `"$smokeErrLog`"`""
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = $smokeAppDir

    # Entorno del proceso hijo: parte del entorno heredado (PATH, etc.) pero se
    # fija la master key de prueba y MIA_APP_DIR al directorio temporal SIN
    # .env, y se scrubbean DATABASE_URL/PG_* por si la terminal actual los
    # tuviera (defensa en profundidad -- el entry ya hace su propio scrub).
    $psi.EnvironmentVariables['LITELLM_MASTER_KEY'] = $smokeMasterKey
    $psi.EnvironmentVariables['MIA_APP_DIR'] = $smokeAppDir
    foreach ($dbVar in @('DATABASE_URL', 'DIRECT_URL', 'PG_DB', 'PGPASSWORD', 'PG_PASSWORD', 'PG_APP_PASSWORD')) {
        if ($psi.EnvironmentVariables.ContainsKey($dbVar)) {
            $psi.EnvironmentVariables.Remove($dbVar)
        }
    }

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()

    # Esperar /health/liveliness (arranque en frio: cargar model_list, tokenizers,
    # etc. puede tardar varios segundos la primera vez).
    $healthOk = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            $smokeFailures += "el proceso mia-litellm.exe termino solo (exit $($proc.ExitCode)) antes de responder /health/liveliness"
            break
        }
        try {
            $resp = Invoke-WebRequest -Uri "$baseUrl/health/liveliness" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                $healthOk = $true
                break
            }
        } catch {
            # Todavia no levanta -- normal en los primeros segundos.
        }
        Start-Sleep -Milliseconds 750
    }

    if (-not $healthOk) {
        $smokeOk = $false
        $smokeFailures += "/health/liveliness no respondio 200 dentro del timeout de 60s"
    } else {
        Write-Host "  /health/liveliness -> 200 OK" -ForegroundColor Green

        # /v1/models CON Bearer correcto -> 200 + alias del config presentes.
        try {
            $headers = @{ Authorization = "Bearer $smokeMasterKey" }
            $modelsResp = Invoke-WebRequest -Uri "$baseUrl/v1/models" -Headers $headers -UseBasicParsing -TimeoutSec 10
            if ($modelsResp.StatusCode -eq 200) {
                $body = $modelsResp.Content
                if ($body -like '*claude-haiku*' -and $body -like '*mia-local*') {
                    Write-Host "  /v1/models con Bearer -> 200 OK (alias claude-haiku y mia-local presentes)" -ForegroundColor Green
                } else {
                    $smokeOk = $false
                    $smokeFailures += "/v1/models con Bearer respondio 200 pero no contiene los alias esperados (claude-haiku, mia-local)"
                }
            } else {
                $smokeOk = $false
                $smokeFailures += "/v1/models con Bearer respondio $($modelsResp.StatusCode) (esperado 200)"
            }
        } catch {
            $smokeOk = $false
            $statusCode = $null
            if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
            $smokeFailures += "/v1/models con Bearer fallo (status=$statusCode): $($_.Exception.Message)"
        }

        # /v1/models SIN Bearer -> 401 o 403.
        try {
            $noAuthResp = Invoke-WebRequest -Uri "$baseUrl/v1/models" -UseBasicParsing -TimeoutSec 10
            $smokeOk = $false
            $smokeFailures += "/v1/models SIN Bearer respondio $($noAuthResp.StatusCode) (esperado 401/403 -- NO deberia dejar pasar peticiones sin llave)"
        } catch {
            $statusCode = $null
            if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
            if ($statusCode -eq 401 -or $statusCode -eq 403) {
                Write-Host "  /v1/models SIN Bearer -> $statusCode OK (rechazado como se esperaba)" -ForegroundColor Green
            } else {
                $smokeOk = $false
                $smokeFailures += "/v1/models SIN Bearer fallo con status=$statusCode (esperado 401/403): $($_.Exception.Message)"
            }
        }

        # ---------------------------------------------------------------
        # Verificacion de bind loopback (correccion de seguridad -- el CLI
        # de litellm bindea en 0.0.0.0 por defecto, exponiendo el gateway de
        # modelos -- llaves de API + prompts juridicos -- a toda la red del
        # despacho). El humo debe FALLAR el build si el listener no queda
        # SOLO en 127.0.0.1.
        # ---------------------------------------------------------------
        Write-Host "  Verificando bind loopback (netstat)..." -ForegroundColor Cyan
        $listeners = @(Get-NetTCPConnection -LocalPort $smokePort -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) {
            $smokeOk = $false
            $smokeFailures += "no se encontro ningun listener TCP en el puerto $smokePort (netstat/Get-NetTCPConnection vacio)"
        } else {
            $badListeners = @($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' })
            if ($badListeners.Count -gt 0) {
                $smokeOk = $false
                $badAddrs = ($badListeners | ForEach-Object { $_.LocalAddress }) -join ', '
                $smokeFailures += "el listener del puerto $smokePort NO esta restringido a 127.0.0.1 (direcciones encontradas: $badAddrs) -- riesgo de exposicion a la red local"
            } else {
                Write-Host "  listener en 127.0.0.1:$smokePort (NO 0.0.0.0) OK" -ForegroundColor Green
            }
        }

        # Si la maquina tiene una IP LAN real, un intento de acceso externo
        # DEBE fallar (conexion rechazada) -- confirma que el bind loopback
        # tambien es inalcanzable desde fuera de la maquina, no solo que
        # netstat reporte 127.0.0.1.
        $lanIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' })
        if ($lanIps.Count -eq 0) {
            Write-Host "  sin IP LAN detectada en esta maquina -- se omite el sub-check de acceso externo." -ForegroundColor Yellow
        } else {
            $lanIp = $lanIps[0].IPAddress
            try {
                $lanResp = Invoke-WebRequest -Uri "http://$lanIp`:$smokePort/health/liveliness" -UseBasicParsing -TimeoutSec 3
                $smokeOk = $false
                $smokeFailures += "el acceso externo via IP LAN ($lanIp`:$smokePort) respondio $($lanResp.StatusCode) -- DEBERIA haber sido rechazado (bind no es loopback puro)"
            } catch {
                Write-Host "  acceso externo via IP LAN ($lanIp`:$smokePort) rechazado como se esperaba OK" -ForegroundColor Green
            }
        }
    }
} finally {
    if ($proc -and -not $proc.HasExited) {
        try {
            & taskkill /T /F /PID $proc.Id | Out-Null
        } catch {
            # best-effort
        }
    }
    # Antes de limpiar: si el humo fallo, rescatar la cola de los logs del exe
    # para que el reporte de falla traiga la causa real (traceback, etc.).
    if (-not $smokeOk) {
        foreach ($logFile in @($smokeErrLog, $smokeOutLog)) {
            if (Test-Path $logFile) {
                $tailLines = Get-Content -LiteralPath $logFile -Tail 30 -ErrorAction SilentlyContinue
                if ($tailLines) {
                    $smokeLogTail += ("--- " + (Split-Path -Leaf $logFile) + " (ultimas lineas) ---")
                    $smokeLogTail += $tailLines
                }
            }
        }
    }
    if (Test-Path $smokeAppDir) {
        Remove-Item -Recurse -Force $smokeAppDir -ErrorAction SilentlyContinue
    }
}

if (-not $smokeOk) {
    Write-Host ""
    Write-Host "HUMO FALLO:" -ForegroundColor Red
    foreach ($f in $smokeFailures) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    foreach ($line in $smokeLogTail) {
        Write-Host "  $line" -ForegroundColor DarkYellow
    }
    throw "El humo post-build de mia-litellm.exe fallo -- build considerado NO apto para distribuir. Ver fallas arriba."
}

Write-Host ""
Write-Host "Humo post-build: PASS (health, /v1/models con y sin Bearer OK)." -ForegroundColor Green
