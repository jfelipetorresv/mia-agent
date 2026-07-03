# Mia - descarga de los modelos de dictado local (CP-Z1, Ola 3)
#
# Baja a mia-data/models/speech/ (gitignored) los pesos que el motor de voz
# necesita — los MISMOS que Lexter valido en espanol juridico:
#   - Parakeet TDT 0.6B v3 int8 (STT, ~650 MB extraido)  [NVIDIA CC-BY-4.0]
#   - silero_vad.onnx (detector de voz)                    [MIT]
# Los pesos NO se versionan en git (tamano + licencias propias): este script
# corre UNA vez por instalacion. Idempotente: si ya estan, no re-descarga.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root 'mia-data\models\speech'
New-Item -ItemType Directory -Force $dest | Out-Null

$parakeetDir = Join-Path $dest 'sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8'
$release = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models'

# -f: un 404/500 debe FALLAR, no escribir la pagina de error al archivo destino
# (hallazgo del revisor de capa 2). Limite conocido: no hay checksum de integridad.
if (-not (Test-Path (Join-Path $parakeetDir 'encoder.int8.onnx'))) {
    Write-Host "Descargando Parakeet TDT 0.6B v3 int8 (~460 MB)..." -ForegroundColor Cyan
    $tarball = Join-Path $dest 'parakeet-v3-int8.tar.bz2'
    curl.exe -fSL -o $tarball "$release/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
    if ($LASTEXITCODE -ne 0) { throw "Fallo la descarga del modelo de dictado." }
    tar -xjf $tarball -C $dest
    if ($LASTEXITCODE -ne 0) { throw "Fallo la extraccion del modelo de dictado." }
    Remove-Item $tarball
    Write-Host "Parakeet v3 listo en $parakeetDir" -ForegroundColor Green
} else {
    Write-Host "Parakeet v3 ya estaba descargado." -ForegroundColor Green
}

$vad = Join-Path $dest 'silero_vad.onnx'
if (-not (Test-Path $vad)) {
    Write-Host "Descargando Silero VAD..." -ForegroundColor Cyan
    curl.exe -fSL -o $vad "$release/silero_vad.onnx"
    if ($LASTEXITCODE -ne 0) { throw "Fallo la descarga del detector de voz." }
    if ((Get-Item $vad).Length -lt 500KB) {
        Remove-Item $vad
        throw "El detector de voz descargado no tiene el tamano esperado."
    }
    Write-Host "Silero VAD listo." -ForegroundColor Green
} else {
    Write-Host "Silero VAD ya estaba descargado." -ForegroundColor Green
}

Write-Host "`nModelos de dictado listos. Reinicia el API para activar el microfono." -ForegroundColor Green
