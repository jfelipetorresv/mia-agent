param(
    [ValidateSet('quick', 'full')]
    [string]$Mode = 'quick',
    [int]$TimeoutSeconds = 0,
    [string]$ResultPath = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$catalog = Get-Content -Raw -LiteralPath (Join-Path $root 'config\verification.json') | ConvertFrom-Json
$python = if ($env:MIA_VERIFY_PYTHON) { $env:MIA_VERIFY_PYTHON } else {
    Join-Path $root '.venv\Scripts\python.exe'
}
$env:PYTHONPATH = Join-Path $root 'backend'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# CI pasa `python` (comando en PATH de setup-python), no una ruta de archivo.
# Start-Process necesita el ejecutable resuelto.
if (-not (Test-Path -LiteralPath $python)) {
    $resolved = Get-Command $python -ErrorAction SilentlyContinue
    if ($resolved -and $resolved.Source) {
        $python = $resolved.Source
    }
}
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "PRECHECK: Python de Mia no existe: $python"
    exit 2
}

$timeout = [int]$catalog.default_timeout_seconds
if ($TimeoutSeconds -gt 0) { $timeout = $TimeoutSeconds }

if ($Mode -eq 'quick') {
    # One rule shared with the isolated fixtures; this only validates configuration.
    $executionDir = Join-Path $root 'execution'
    $precheckCode = @'
import os, sys
sys.path.insert(0, sys.argv[1])
from isolated_test_env import select
try:
    select(os.environ)
except (RuntimeError, ValueError, OSError):
    sys.exit(2)
'@
    & $python -B -c $precheckCode $executionDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'PRECHECK: quick requiere MIA_TEST_ENV_FILE valido de una base temporal; CI admite PG_* explicitas del servicio efimero. No se ejecutaron suites.' -ErrorAction Continue
        exit 2
    }
    # Recuento 2026-10-11: siete suites con base leen PG_* del entorno del proceso y no
    # de MIA_TEST_ENV_FILE. Sin estas variables caian al 5432 y daban un rojo de entorno
    # (ConnectionTimeout) que parecia del codigo. Se exportan las PG_* de la base aislada
    # que valida `select` (nunca la 55432 instalada) y el mismo MIA_ENV que fija
    # `isolated_test_env.load`. Los valores no se imprimen. Dentro de este Python NUNCA
    # comillas dobles: PowerShell 5.1 las borra al pasar el argumento a un ejecutable nativo.
    # Ademas: `mia.config` carga el .env del REPO si DATABASE_URL no viene en el entorno, y
    # ese .env apunta a la base INSTALADA. Se exporta la DATABASE_URL de la base aislada y,
    # con archivo, MIA_APP_DIR apunta a su carpeta para que config lea ESE .env. Si la URL
    # falta o usa el puerto 55432, no corre ninguna suite (fail-closed).
    $exportCode = @'
import json, os, sys
from urllib.parse import urlparse
sys.path.insert(0, sys.argv[1])
from isolated_test_env import select
values = select(os.environ)
out = {k: v for k, v in values.items() if k.startswith('PG_') and v is not None}
ci = any(str(os.environ.get(k, '')).lower() == 'true' for k in ('CI', 'GITHUB_ACTIONS'))
url = values.get('DATABASE_URL') or (os.environ.get('DATABASE_URL') if ci else '') or ''
if not url or urlparse(url).port is None or (not ci and urlparse(url).port == 55432):
    sys.exit(3)
out['DATABASE_URL'] = url
print(json.dumps(out))
'@
    $pgJson = & $python -B -c $exportCode $executionDir
    if ($LASTEXITCODE -ne 0 -or -not $pgJson) {
        Write-Error 'PRECHECK: la base aislada no trae DATABASE_URL propia o apunta a la base instalada (55432). No se ejecutaron suites.' -ErrorAction Continue
        exit 2
    }
    foreach ($pgVar in ($pgJson | ConvertFrom-Json).PSObject.Properties) {
        Set-Item -LiteralPath ('Env:' + $pgVar.Name) -Value ([string]$pgVar.Value)
    }
    if ($env:MIA_TEST_ENV_FILE) {
        $env:MIA_APP_DIR = Split-Path -Parent $env:MIA_TEST_ENV_FILE
    }
    $env:MIA_ENV = 'dev'
}

if ($Mode -eq 'full' -and $catalog.full_requires_database) {
    $pgReady = 'D:\Inteligencia Artificial\Mia-Super Agent\tools\postgres16-portable\pgsql\bin\pg_isready.exe'
    if (-not (Test-Path -LiteralPath $pgReady)) {
        Write-Error 'PRECHECK: pg_isready portable no existe; regresion cancelada.'
        exit 2
    }
    & $pgReady -h 127.0.0.1 -p 55432 *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'PRECHECK: PostgreSQL portable 127.0.0.1:55432 esta apagado; regresion cancelada.'
        exit 2
    }
}

if ($Mode -eq 'quick') {
    # Los contratos criticos (test_rls es HALT segun CLAUDE.md) corren siempre en quick;
    # antes solo CI los ejecutaba y un quick verde se leia como aislamiento aprobado.
    $tests = @(@($catalog.quick) + @($catalog.critical_contracts) |
        Select-Object -Unique | ForEach-Object { Join-Path $root $_ })
} else {
    $tests = @(Get-ChildItem -LiteralPath (Join-Path $root 'execution') -Filter 'test_*.py' |
        Sort-Object Name | Select-Object -ExpandProperty FullName)
}

$missing = @($tests | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
    Write-Error "CATALOGO INVALIDO: $($missing -join ', ')"
    exit 2
}

$failed = @()
$timedOut = @()
$results = @()
$started = Get-Date

# SAT-Graph abre/cierra su propio pool para validar aislamiento. En Windows, tras una
# regresión larga puede quedar un cierre de conexión transitorio entre procesos. Un único
# reintento nuevo distingue esa condición de un fallo funcional persistente.
$retryableFullTests = @('test_sat_graph_jurisdiction.py')

function Stop-ProcessTree([int]$ProcessId) {
    # Stop-Process solo mata al Python padre; npm/Next puede conservar abiertos los
    # archivos redirigidos y colgar el verificador para siempre. Recorremos únicamente
    # los descendientes del PID que acabamos de crear, de abajo hacia arriba.
    if ($IsWindows) {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" |
            Select-Object -ExpandProperty ProcessId)
    } else {
        $children = @()
        try {
            $children = @(Get-Process -ErrorAction SilentlyContinue |
                Where-Object { $_.Parent -and $_.Parent.Id -eq $ProcessId } |
                Select-Object -ExpandProperty Id)
        } catch {
            $children = @()
        }
    }
    foreach ($child in $children) { Stop-ProcessTree -ProcessId ([int]$child) }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

foreach ($test in $tests) {
    $name = Split-Path -Leaf $test
    $testStarted = Get-Date
    $status = 'passed'
    Write-Host "`n=== $name (timeout $timeout s) ===" -ForegroundColor Cyan
    $stdout = Join-Path ([System.IO.Path]::GetTempPath()) ("mia-verify-" + [guid]::NewGuid() + '.out.log')
    $stderr = Join-Path ([System.IO.Path]::GetTempPath()) ("mia-verify-" + [guid]::NewGuid() + '.err.log')
    try {
        $startArgs = @{
            FilePath = $python
            ArgumentList = @('-u', ('"' + $test + '"'))
            WorkingDirectory = $root
            RedirectStandardOutput = $stdout
            RedirectStandardError = $stderr
            PassThru = $true
        }
        # $IsWindows NO existe en Windows PowerShell 5.1 (solo en PowerShell Core): aquí
        # evaluaba a $null y cada suite abría una consola negra visible sobre el escritorio
        # del abogado (reportado por Pipe 2026-08-24). Se detecta Windows por $env:OS.
        if ($env:OS -eq 'Windows_NT' -or $IsWindows) {
            $startArgs['WindowStyle'] = 'Hidden'
        }
        $proc = Start-Process @startArgs
        # Windows PowerShell pierde ExitCode con redirección si el handle no se materializa
        # antes de que el proceso termine.
        $processHandle = $proc.Handle
        if (-not $proc.WaitForExit($timeout * 1000)) {
            Stop-ProcessTree -ProcessId $proc.Id
            $proc.WaitForExit()
            $timedOut += $name
            $status = 'timeout'
            Write-Host "TIMEOUT: $name" -ForegroundColor Red
        } else {
            $proc.WaitForExit()
            $proc.Refresh()
            Get-Content -Encoding UTF8 -LiteralPath $stdout -ErrorAction SilentlyContinue
            $exitCode = $proc.ExitCode
            if ($exitCode -ne 0) {
                Get-Content -Encoding UTF8 -LiteralPath $stderr -ErrorAction SilentlyContinue | Write-Host
                $failed += $name
                $status = 'failed'
                Write-Host "EXIT $exitCode`: $name" -ForegroundColor Red
            }
        }
    } finally {
        $results += [pscustomobject]@{
            name = $name
            status = $status
            duration_seconds = [Math]::Round(((Get-Date) - $testStarted).TotalSeconds, 3)
        }
        Remove-Item -Force -LiteralPath $stdout,$stderr -ErrorAction SilentlyContinue
    }
}

if ($Mode -eq 'full') {
    foreach ($name in @($failed | Where-Object { $_ -in $retryableFullTests })) {
        $test = $tests | Where-Object { (Split-Path -Leaf $_) -eq $name } | Select-Object -First 1
        Write-Host "`nRETRY: $name en proceso limpio tras fallo transitorio" -ForegroundColor Yellow
        & $python -u $test
        if ($LASTEXITCODE -eq 0) {
            $failed = @($failed | Where-Object { $_ -ne $name })
            $results = @($results | ForEach-Object {
                if ($_.name -eq $name) {
                    [pscustomobject]@{ name = $_.name; status = 'passed_after_retry'; duration_seconds = $_.duration_seconds }
                } else { $_ }
            })
            Write-Host "RETRY PASS: $name" -ForegroundColor Green
        } else {
            Write-Host "RETRY FAIL: $name (se conserva bloqueo)" -ForegroundColor Red
        }
    }
}

$elapsed = [Math]::Round(((Get-Date) - $started).TotalSeconds, 1)
$verificationStatus = if ($failed.Count -gt 0 -or $timedOut.Count -gt 0) { 'failed' } else { 'passed' }
if ($ResultPath) {
    $resolvedResult = if ([System.IO.Path]::IsPathRooted($ResultPath)) {
        $ResultPath
    } else {
        Join-Path $root $ResultPath
    }
    $resultDir = Split-Path -Parent $resolvedResult
    if ($resultDir) { New-Item -ItemType Directory -Force -Path $resultDir | Out-Null }
    [pscustomobject]@{
        schema_version = 1
        mode = $Mode
        status = $verificationStatus
        started_at = $started.ToUniversalTime().ToString('o')
        duration_seconds = $elapsed
        suite_count = $tests.Count
        failed = @($failed)
        timed_out = @($timedOut)
        suites = @($results)
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resolvedResult -Encoding utf8
}
if ($failed.Count -gt 0 -or $timedOut.Count -gt 0) {
    Write-Host "`nVERIFICACION ROJA | modo=$Mode | $elapsed s" -ForegroundColor Red
    if ($failed.Count -gt 0) { Write-Host "Fallaron: $($failed -join ', ')" }
    if ($timedOut.Count -gt 0) { Write-Host "Timeout: $($timedOut -join ', ')" }
    exit 1
}

Write-Host "`nVERIFICACION VERDE | modo=$Mode | $($tests.Count) suites | $elapsed s" -ForegroundColor Green
exit 0
