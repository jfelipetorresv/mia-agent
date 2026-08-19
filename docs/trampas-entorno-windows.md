# Trampas del entorno (Windows) — MIA

Trampas **confirmadas y medidas** en este repo y esta máquina. Todas se repitieron en más de
una sesión. Léelas antes de diagnosticar: la mayoría se disfrazan de bugs de producto.

Fuente: retrospectivas 2026-07-17-003, 2026-07-18-001, 2026-07-19-001, 2026-07-20-001.

---

## 1. Herramientas que cuelgan el shell

| Herramienta | Qué pasa | Usa en su lugar |
|---|---|---|
| `Test-NetConnection`, `netstat` | Cuelgan hasta timeout (~2 min) | `python -c "import socket;s=socket.socket();s.settimeout(1.5);print(s.connect_ex(('127.0.0.1',P)))"` (`0` = abierto) |
| `Glob` sobre la raíz del proyecto | Timeout a los 20 s, sin resultados | `git ls-files \| grep -i <patrón>` (resuelve en 1 s) |
| `find` recursivo | Timeout a los 120 s | `git ls-files` |
| `curl` sin límite | Se queda esperando | `curl --max-time 5` |

El directorio primario mezcla el repo con material pesado. **Nunca lances `Glob`/`Grep` sin
`path` acotado.** Para inventarios, `git ls-files` siempre.

## 2. Procesos zombis de `statusline.js`

Claude Code deja procesos `node` huérfanos que ahogan la máquina. Medido: **2.060 procesos**
acumulados en un día → terminal a 5736 ms, `ChunkLoadError` de Next, perfiles a 2650 ms.
Tras limpiar (2086 → 24 procesos): 1917 ms.

**Regla: ante "todo va lento", cuenta procesos ANTES de culpar al síntoma visible.** El
sospechoso obvio (el perfil de PowerShell) no tenía nada que optimizar.

```powershell
Get-Process node -ErrorAction SilentlyContinue | Measure-Object | Select-Object Count
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like '*statusline*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Mata **solo** los `statusline.js`. Nunca todos los `node.exe`: te llevas los servicios de dev.
Causa raíz aún sin diagnosticar.

## 3. Arrancar los servicios de MIA

- **Funciona**: lanzarlos con el mecanismo de fondo del harness (Bash con
  `run_in_background: true`). Los procesos sobreviven entre turnos. Esta es la vía recomendada
  para verificación visual (hallazgo 2026-07-20).
- **No funciona**: `Start-Process`, `cmd /c start`, `Win32_Process.Create` desde la sesión —
  el árbol muere al terminar el comando y la app "se cierra sola".
- Para que los arranque Pipe: `Abrir Mia.cmd` (doble clic).
- Comandos para un no-técnico: **una sola línea**. Nunca con backtick de continuación (`` ` ``):
  PowerShell parte el comando al pegarlo y ejecuta cada trozo suelto.

## 4. `ChunkLoadError` de Next: tres causas distintas

Un mismo error tuvo tres orígenes en una sola sesión:

1. Saturación por los zombis del punto 2.
2. Recompilación en curso tras borrar `.next` (50 s). **Espera el `✓ Compiled`.**
3. Caché del navegador con la página vieja → abre por `127.0.0.1:3100` (otro origen, caché
   limpio) en vez de `localhost:3100`.

**Antes de concluir que es un bug: pide el recurso por HTTP.** Si el servidor devuelve 200 en
los chunks, el problema es del cliente.

## 5. Base de datos

- El clúster portable va en el **puerto 55432**, no en el 5432 del sistema (confirmado vivo).
- **`scripts/setup_db.ps1` ya lee la base del `.env`** (`PG_HOST`/`PG_PORT`/`PG_DB`, líneas
  12-34 del script) en vez de asumir el PostgreSQL del sistema en el 5432 — arreglado en el
  commit `fdad1f1`. Antes de ese commit el chequeo previo de pgvector apuntaba con ruta fija al
  PostgreSQL del sistema y abortaba con `exit 1` aunque la base portable sí tuviera pgvector
  (falsa alarma reproducida 2026-07-19); ya no es el caso.
- **Consulta el esquema real antes de escribir SQL exploratorio.** `matters` tiene `title`, no
  `name` (`psycopg.errors.UndefinedColumn` costó una iteración). Descubre columnas vía
  `information_schema`.

## 6. Salidas y codificación

- Todo script Python que imprima texto del proyecto (español + símbolos) **fija UTF-8 en
  stdout desde la primera línea**. Si no: `UnicodeEncodeError: 'charmap' codec can't encode`.
  ```python
  import sys, io
  sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
  ```
- Mensajes de commit largos: **siempre `git commit -F <archivo>`**. Un here-string
  (`@'...'@`) con la ruta con espacios se parsea mal y dispara el guard de seguridad.
  Reserva `-m` para una línea.
- Separa borrados de rutas de comandos que contengan flags tipo `/c`: un guard interpretó mal
  un `cmd.exe /c` en la misma línea y bloqueó el `Remove-Item`.

## 7. Red frágil

- El envío de imágenes por chat falla con PNG de ~1 MB (400/timeout). **Guardar en la carpeta
  del proyecto es el flujo por defecto**, no un fallback.
- Delega arranque y captura visual a subagentes aislados: protege el contexto de la terminal
  principal y devuelve un veredicto en tabla en vez de imágenes.

## 8. Workflows multiagente

- **Resultado truncado**: no relances. Edita el `return` del script y re-invoca con
  `resumeFromRunId`; los agentes replican desde caché (23 ms, 0 tokens). Guarda el `runId` de
  toda corrida larga apenas empiece.
- **Un escritor por archivo.** Ningún subagente hace git; los archivos compartidos
  (dependencias, routers, numeración de migraciones) los toca solo el coordinador. Avísales de
  que verán cambios ajenos en `git diff`: son de sus hermanos, no suyos.
- Verifica `git status` inmediatamente antes de cada commit.
