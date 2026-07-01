# Mia - regresion completa execution/test_*.py
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $root 'backend'
Set-Location $root

# Gate del Riesgo #32 primero: si el venv fue degradado, la regresion no es confiable.
Write-Host "`n=== check_env_pins.py (gate Riesgo #32) ===" -ForegroundColor Cyan
& $py execution\check_env_pins.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nABORTADO: pins del venv alterados (Riesgo #32)." -ForegroundColor Red
    exit 1
}

$failed = @()
Get-ChildItem execution\test_*.py | Sort-Object Name | ForEach-Object {
    Write-Host "`n=== $($_.Name) ===" -ForegroundColor Cyan
    & $py $_.FullName
    if ($LASTEXITCODE -ne 0) { $failed += $_.Name }
}

if ($failed.Count) {
    Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nALL PASS ($((Get-ChildItem execution\test_*.py).Count) suites)" -ForegroundColor Green
exit 0
