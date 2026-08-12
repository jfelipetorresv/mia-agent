# Compatibilidad para lanzadores existentes: la regresión completa ahora pasa por la entrada
# única, con preflight de infraestructura y timeout por suite.
& (Join-Path $PSScriptRoot 'verify.ps1') -Mode full
exit $LASTEXITCODE
