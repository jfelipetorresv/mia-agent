# architecture/windows_notes.md
# Notas de plataforma Windows (Modo B nativo)
# Última actualización: 2026-06-30

> Mia se desarrolla y se entrega en Modo B sobre **Windows 11 nativo** (CLAUDE.md §A/§G).
> Este archivo recoge las trampas específicas de la plataforma que NO aparecen en Linux/macOS
> y que los gates offline no detectan (solo se manifiestan al arrancar procesos reales).

---

## 1 · asyncio + psycopg: la API DEBE correr sobre `SelectorEventLoop`, no `ProactorEventLoop`

**Síntoma (smoke vivo 2026-06-30):** al arrancar la API con uvicorn, la conexión a PostgreSQL se
rompía / el pool async de psycopg fallaba, pese a que la DB estaba sana (mismas credenciales
funcionaban desde `psql` y desde scripts). El fallo aparecía **solo** al levantar el servidor, no
en los gates.

**Causa raíz:** `psycopg` async **no es compatible con el `ProactorEventLoop`** de Windows (su
backend de I/O usa APIs que Proactor no soporta para sockets de la forma que psycopg necesita).
Desde **uvicorn ≥ 0.36**, uvicorn fuerza `ProactorEventLoop` en Windows vía su `loop_factory`
interno, **ignorando** la `asyncio` event loop policy del proceso. Resultado: aunque el proceso
fijara `WindowsSelectorEventLoopPolicy`, uvicorn montaba el servidor sobre Proactor igual → psycopg
moría.

**Fix (`backend/mia/api/run.py` — launcher Windows-safe):** en el arranque single-process se monta
el servidor a mano sobre un `SelectorEventLoop` propio, en vez de delegar en `uvicorn.run`:

```python
if sys.platform == "win32" and not reload:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    config = uvicorn.Config("mia.api.main:app", host=host, port=port,
                            reload=False, loop="none")   # loop="none" → NO crear loop propio
    server = uvicorn.Server(config)
    asyncio.run(server.serve())                          # corre sobre NUESTRO Selector loop
    return
```

Las dos claves son **`loop="none"`** (uvicorn no instala su propio loop_factory de Proactor) +
arrancar el servidor desde un `asyncio.run(...)` que ya está sobre `WindowsSelectorEventLoopPolicy`.

**Caso `--reload`:** con reload, uvicorn levanta el server en un **subprocess** cuyo `loop_factory`
sí devuelve `SelectorEventLoop`, así que ese camino no necesita el workaround (solo se fija la
policy por si acaso).

**Invariante / regla:**
- Arrancar la API SIEMPRE por `mia.api.run:main` (lo hace `scripts/start_api.ps1`), **nunca** con
  un `uvicorn mia.api.main:app` crudo en Windows → ese atajo vuelve a montar Proactor y rompe la DB.
- Si algún día se sube la versión de uvicorn, **re-verificar en vivo** que la API sigue arrancando
  sobre Selector (un turno real que toque la DB), porque el comportamiento del `loop_factory` de
  uvicorn ya cambió una vez (≥0.36) y podría volver a cambiar.

---

## 2 · Otras trampas Windows ya registradas (referencias)

- **LiteLLM comparte el `.venv` de la app** y al reinstalar `litellm[proxy]` degrada
  `uvicorn`/`sse-starlette`/`fastapi`/`starlette`/`python-multipart` → **Riesgo #32**
  (`memory/bugs-and-risks.md`). Acción: separar LiteLLM en su propio venv antes de reiniciar la API
  en producción. Relacionado con el punto 1: un downgrade silencioso de uvicorn podría reintroducir
  el bug del event loop.
- **Arranque de LiteLLM con CWD aislado + DB env scrubbed** (`scripts/run_litellm_clean.ps1`):
  `Set-Location` NO cambia el CWD Win32 que heredan los procesos hijos, así que sin aislar el dir,
  `litellm.exe` corre con CWD=proyecto, su `load_dotenv()` reinyecta `DATABASE_URL` e intenta Prisma
  y muere. Ver el encabezado del script.
- **Ruta del proyecto con espacios** (`D:\Codex\Mia-Super Agent\mia`) → **Riesgo #1**: toda ruta
  entre comillas en comandos PowerShell/subprocess.
- **PowerShell 5.1 parsea mal UTF-8 con acentos** → los scripts `.ps1` se escriben en ASCII puro a
  propósito (ver `scripts/start_litellm.ps1`).
