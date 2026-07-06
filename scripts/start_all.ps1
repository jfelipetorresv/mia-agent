# Mia - Abrir Mia (Modo B). Enciende lo que falte y abre el navegador solo.
# Pensado para doble-clic (via "Abrir Mia.cmd"). ASCII puro a proposito
# (Windows PowerShell 5.1 parsea mal UTF-8 con acentos).
$root = Split-Path -Parent $PSScriptRoot      # scripts\ -> mia\

function Test-Port($p) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $p); $c.Close(); return $true
  } catch { return $false }
}

function Start-Part($name, $script, $port) {
  if (Test-Port $port) {
    Write-Host ("[ya encendido] {0} (puerto {1})" -f $name, $port)
  } else {
    Write-Host ("[encendiendo]  {0} (puerto {1})..." -f $name, $port)
    # Comillas explicitas: la ruta contiene espacios y -ArgumentList no cita solo.
    Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f (Join-Path $root $script))
  }
}

Write-Host "Encendiendo Mia..."
Write-Host ""
Start-Part 'Motor de IA'     'scripts\start_litellm.ps1'  4000
Start-Part 'Cerebro de Mia'  'scripts\start_api.ps1'      8000
Start-Part 'Pantalla de Mia' 'scripts\start_frontend.ps1' 3000

Write-Host ""
Write-Host "Esperando a que la pantalla de Mia este lista (puede tardar hasta 1 minuto la primera vez)..."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  if (Test-Port 3000) { $ok = $true; break }
  Start-Sleep -Seconds 1
}
if ($ok) {
  Start-Sleep -Seconds 5   # margen para que Next.js compile la primera pagina
  Write-Host "Abriendo Mia en el navegador..."
  Start-Process 'http://localhost:3000'
} else {
  Write-Host "La pantalla tardo mas de lo normal. Abre tu navegador en http://localhost:3000"
}

Write-Host ""
Write-Host "Listo. Mia esta abierta en http://localhost:3000"
Write-Host "Puedes MINIMIZAR las ventanas negras que se abrieron, pero NO las cierres mientras uses Mia."
Write-Host "Para apagar Mia, cierra esas ventanas negras."
Start-Sleep -Seconds 6
