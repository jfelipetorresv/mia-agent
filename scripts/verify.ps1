param(
    [ValidateSet('quick', 'full')]
    [string]$Mode = 'quick',
    [int]$TimeoutSeconds = 0
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$catalog = Get-Content -Raw -LiteralPath (Join-Path $root 'config\verification.json') | ConvertFrom-Json
$python = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "PRECHECK: Python de Mia no existe: $python"
    exit 2
}

$timeout = [int]$catalog.default_timeout_seconds
if ($TimeoutSeconds -gt 0) { $timeout = $TimeoutSeconds }

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
    $tests = @($catalog.quick | ForEach-Object { Join-Path $root $_ })
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
$started = Get-Date
foreach ($test in $tests) {
    $name = Split-Path -Leaf $test
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
            WindowStyle = 'Hidden'
            PassThru = $true
        }
        $proc = Start-Process @startArgs
        # Windows PowerShell pierde ExitCode con redirección si el handle no se materializa
        # antes de que el proceso termine.
        $processHandle = $proc.Handle
        if (-not $proc.WaitForExit($timeout * 1000)) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $timedOut += $name
            Write-Host "TIMEOUT: $name" -ForegroundColor Red
        } else {
            $proc.WaitForExit()
            $proc.Refresh()
            Get-Content -Encoding UTF8 -LiteralPath $stdout -ErrorAction SilentlyContinue
            $exitCode = $proc.ExitCode
            if ($exitCode -ne 0) {
                Get-Content -Encoding UTF8 -LiteralPath $stderr -ErrorAction SilentlyContinue | Write-Host
                $failed += $name
                Write-Host "EXIT $exitCode`: $name" -ForegroundColor Red
            }
        }
    } finally {
        Remove-Item -Force -LiteralPath $stdout,$stderr -ErrorAction SilentlyContinue
    }
}

$elapsed = [Math]::Round(((Get-Date) - $started).TotalSeconds, 1)
if ($failed.Count -gt 0 -or $timedOut.Count -gt 0) {
    Write-Host "`nVERIFICACION ROJA | modo=$Mode | $elapsed s" -ForegroundColor Red
    if ($failed.Count -gt 0) { Write-Host "Fallaron: $($failed -join ', ')" }
    if ($timedOut.Count -gt 0) { Write-Host "Timeout: $($timedOut -join ', ')" }
    exit 1
}

Write-Host "`nVERIFICACION VERDE | modo=$Mode | $($tests.Count) suites | $elapsed s" -ForegroundColor Green
exit 0
