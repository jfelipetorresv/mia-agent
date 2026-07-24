# Mia - sonda de salud de la maquina de dev (retrospectiva 2026-07-22-007).
# ASCII puro a proposito. Correrla al ARRANCAR la sesion y ante CUALQUIER lentitud
# (Glob/ripgrep con timeout = primera senal). La saturacion por zombis de
# statusline.js paso DOS veces el 2026-07-22 (616 y 3.346 procesos; CPU 100%,
# 1,3 GB RAM libre) y se detecto tarde en ambas.
#
# Uso:  powershell -File scripts\sonda_salud.ps1 [-Segar]
#   -Segar: mata los node.exe de statusline con >30 s de vida (mismo criterio del
#           segador externo) ademas de reportar.
param([switch]$Segar)

$nodes = Get-CimInstance Win32_Process -Filter "Name='node.exe'"
$zombis = @($nodes | Where-Object { $_.CommandLine -like '*statusline*' })
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$os = Get-CimInstance Win32_OperatingSystem
$ramLibre = [Math]::Round($os.FreePhysicalMemory / 1MB, 1)
$reaper = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -like '*statusline-reaper*' })

Write-Host "node.exe totales:      $(@($nodes).Count)"
Write-Host "  de statusline:       $($zombis.Count)"
Write-Host "CPU:                   $([Math]::Round($cpu))%"
Write-Host "RAM libre:             $ramLibre GB de $([Math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB"
Write-Host "segador corriendo:     $($reaper.Count -gt 0)"

# DB portable (retrospectiva 2026-07-24-001: test_rls fallo con ConnectionTimeout
# porque la DB estaba apagada y nadie lo sabia hasta correr la suite).
$pgIsReady = "D:\Inteligencia Artificial\Mia-Super Agent\tools\postgres16-portable\pgsql\bin\pg_isready.exe"
$dbOk = $false
if (Test-Path $pgIsReady) {
    & $pgIsReady -h 127.0.0.1 -p 55432 *> $null
    $dbOk = ($LASTEXITCODE -eq 0)
}
Write-Host "DB portable (55432):   $(if ($dbOk) { 'acepta conexiones' } else { 'APAGADA' })"
if (-not $dbOk) {
    Write-Host "AVISO: DB portable apagada - test_rls y toda suite con DB fallara con ConnectionTimeout. Encender:"
    Write-Host '  & "D:\Inteligencia Artificial\Mia-Super Agent\tools\postgres16-portable\pgsql\bin\pg_ctl.exe" -D "D:\Inteligencia Artificial\Mia-Super Agent\tools\pgdata-portable" -l "D:\Inteligencia Artificial\Mia-Super Agent\tools\pgdata-portable\arranque.log" start'
}

$alerta = $false
if ($zombis.Count -gt 50) { Write-Host "ALERTA: zombis de statusline acumulados - segar y relanzar el segador."; $alerta = $true }
if ($cpu -gt 90) { Write-Host "ALERTA: CPU saturada."; $alerta = $true }
if ($ramLibre -lt 3) { Write-Host "ALERTA: RAM libre critica."; $alerta = $true }
# Desde 2026-07-23 existe la tarea programada permanente "statusline-reaper" (cada 5 min);
# si esta registrada, el loop de 8 h ya no hace falta y no se avisa por su ausencia.
$tareaPermanente = $null
try { $tareaPermanente = Get-ScheduledTask -TaskName "statusline-reaper" -ErrorAction Stop } catch {}
Write-Host "tarea programada:      $(if ($tareaPermanente) { $tareaPermanente.State } else { 'NO REGISTRADA' })"
if ($reaper.Count -eq 0 -and -not $tareaPermanente) { Write-Host "AVISO: ni el segador de 8 h ni la tarea programada estan activos. Relanzar el loop:"; Write-Host '  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = ''powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\USER\.claude\statusline-reaper-loop.ps1"'' }' }

if ($Segar -and $zombis.Count -gt 0) {
    $cutoff = (Get-Date).AddSeconds(-30)
    $viejos = @($zombis | Where-Object { $_.CreationDate -lt $cutoff })
    $muertos = 0
    foreach ($z in $viejos) { try { Stop-Process -Id $z.ProcessId -Force -Confirm:$false -ErrorAction Stop; $muertos++ } catch {} }
    Write-Host "segados: $muertos"
}

if ($alerta) { exit 1 } else { exit 0 }
