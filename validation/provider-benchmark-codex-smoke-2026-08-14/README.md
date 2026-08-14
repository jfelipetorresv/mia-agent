# Smoke Codex — fallo de transporte UTF-8

Ejecución diagnóstica de un solo brazo; no es comparable ni certifica proveedor.
El primer nodo jurídico terminó antes de producir contenido porque Windows codificó
`stdin` con la página local y Codex exige UTF-8. `run-state.json` conserva la unidad
como `inflight`, por lo que el runner rechaza repetirla automáticamente.

El adaptador se corrigió para usar `encoding="utf-8"` y `errors="strict"`. Esta
carpeta se conserva como evidencia del fallo; el reintento válido usa otra sesión y
otro directorio.
