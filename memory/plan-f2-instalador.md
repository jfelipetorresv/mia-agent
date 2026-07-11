# Plan F2 — Primer arranque automático (bloque instalador, sesión 43)

> Diseño aprobado por Fable (orquestador) sobre el recon de la sesión 43. Es el CONTRATO
> entre los 3 ejecutores (E1 bootstrap Python, E2 LiteLLM exe, E3 cáscara Rust).
> Objetivo F2: en una máquina limpia, la cáscara detecta que no hay datos y deja MIA
> funcionando sola: carpeta de datos, .env semilla, initdb, migraciones, checkpointer,
> LiteLLM como 4º servicio supervisado.

## Hechos del recon (no re-descubrir)

- La cáscara (`desktop/src-tauri/src/lib.rs`) orquesta DB→backend→frontend leyendo
  `orchestration.json` (junto al exe → cwd → fallback dev). Structs `DbCfg/BackendCfg/
  FrontendCfg/OrchCfg` en `lib.rs:85-117`. `app_dir` → inyecta `MIA_APP_DIR` al backend.
  NO hay initdb: `pg_ctl start` asume cluster existente. NO orquesta LiteLLM.
- `backend/mia/config.py:15-31` ya resuelve PROJECT_ROOT: `MIA_APP_DIR` → si frozen
  `%LOCALAPPDATA%\Mia` → dev repo. Nadie crea la carpeta ni el .env.
- Setup SQL hoy: `execution/init_db.py` (rol `mia_app`, DB `mia`, extensiones vector+
  pgcrypto, `backend/mia/db/schema.sql`) + migraciones `backend/mia/db/migrations/003→030`
  (28 archivos idempotentes, SIN tabla de control — se re-ejecutan todas, como superusuario,
  autocommit) + `execution/init_checkpointer.py` (AsyncPostgresSaver.setup() como
  superusuario + GRANT checkpoint% a mia_app). `scripts/setup_db.ps1` apunta a un Postgres
  de Program Files DESALINEADO — no reutilizar.
- `.env` obligatorios para arrancar: `JWT_SECRET` (≥32 chars, HALT) y `DATABASE_URL`.
  `PG_PASSWORD` (superusuario) se usa TAMBIÉN en runtime (cron/curator/dreams/feedback/gepa)
  — debe quedar en el .env semilla. CORS default es 3000; el frontend instalado corre en
  3100 → el semilla DEBE fijar `MIA_CORS_ORIGINS` con 3100.
- LiteLLM dev: `.venv-litellm` NO existe aún (pin `litellm[proxy]==1.74.8`), puerto 4000,
  `litellm_config.yaml` con `os.environ/<KEY>`. Blindajes de dev que hay que portar al exe:
  (1) `LITELLM_LOCAL_MODEL_COST_MAP=True` ANTES de importar litellm; (2) scrub de
  DATABASE_URL/PG_* (Prisma); (3) el parche en caliente de `proxy_server.py` NO es
  trasladable a un exe → se reemplaza por allowlist de env + neutralizar `dotenv.load_dotenv`.
- Patrón packaging F1 (replicar): entry que fuerza imports + spec onedir `upx=False`
  `console=True` + build.ps1 que usa el pyinstaller DEL VENV correspondiente (instalado
  con --no-deps + pins) + humo post-build real + gate string-literal en frío.
- Identidad (incidente voicebox): NADIE se adopta por responder 200. Backend = claves de
  /health; frontend = huella de cabeceras; DB = pg_isready tri-estado.

## Decisiones de diseño (Fable, declaradas)

1. **El bootstrap es Python, no Rust**: módulo nuevo `backend/mia/setup/first_run.py`,
   invocable como `mia-backend.exe --first-run ...` (frozen) y `python -m mia.setup.first_run ...`
   (dev). La cáscara solo decide CUÁNDO llamarlo y muestra el progreso.
2. **Ownership limpio de Postgres**: si first_run arranca el postgres temporal, lo DETIENE
   al terminar (pg_ctl stop -m fast). Así la cáscara siempre enciende/apaga su DB con el
   flujo ya blindado (evita huérfanos por adopción).
3. **Secretos**: el .env semilla se genera UNA sola vez (si existe, JAMÁS se regeneran
   secretos). `JWT_SECRET=token_urlsafe(48)`; `PG_PASSWORD`/`PG_APP_PASSWORD`=token_urlsafe(24);
   `LITELLM_MASTER_KEY = LITELLM_API_KEY = "sk-mia-" + token_urlsafe(24)` (mismo valor:
   el backend manda LITELLM_API_KEY como Bearer y el proxy exige master_key). UTF-8 sin BOM.
4. **LiteLLM instalado LLEVA master_key** (`packaging/litellm_config.installer.yaml` con
   `general_settings: {master_key: os.environ/LITELLM_MASTER_KEY}`); el dev
   (`litellm_config.yaml`) NO cambia. Puerto 4000 también en instalado (la protección es la
   identidad, no el número de puerto).
5. **orchestration.json v2 con tokens**: la cáscara expande `${exe_dir}` y
   `${local_app_data}` en todos los strings del JSON al cargarlo. Así el JSON del
   instalador es estático (F4/NSIS no templa nada). Campos nuevos OPCIONALES `setup` y
   `litellm` — si faltan, comportamiento actual intacto (compat dev 3 servicios).
6. **Orden de arranque**: setup(si hace falta) → db → litellm → backend → frontend.
   Apagado inverso. LiteLLM entra al Job Object como backend/frontend.
7. **initdb endurecido**: `-U postgres --pwfile=<tmp> -E UTF8 --locale=C
   --auth=scram-sha-256`; tras initdb escribir en `postgresql.conf`:
   `listen_addresses = '127.0.0.1'` y `port = <pg-port>` (solo loopback).
8. **El E2E con los exes reales en máquina limpia sigue siendo de F4** (Riesgo #59).
   F2 verifica con: gates en frío + initdb REAL vía venv (test_first_run) + build real del
   exe de LiteLLM con humo. No se re-buildea el exe del backend en esta fase salvo que la
   capa 2 lo exija.

## Contrato 1 — CLI de first_run (E1 implementa, E3 consume)

```
mia-backend.exe --first-run --pg-bin <dir> --pg-data <dir> --pg-port <port> [--app-dir <dir>]
python -m mia.setup.first_run --pg-bin <dir> --pg-data <dir> --pg-port <port> [--app-dir <dir>]
```

- Resolución de app_dir: `--app-dir` > env `MIA_APP_DIR` > la misma lógica de
  `config.PROJECT_ROOT` (importarla, no duplicarla).
- Pasos (cada uno idempotente y con línea de progreso `MIA-SETUP: <texto en llano>` a stdout):
  1. Crear app_dir si falta.
  2. `.env` semilla si NO existe (claves: JWT_SECRET, PG_HOST=127.0.0.1, PG_PORT, PG_DB=mia,
     PG_PASSWORD, PG_APP_PASSWORD, DATABASE_URL=postgresql://mia_app:<pw>@127.0.0.1:<port>/mia,
     LITELLM_BASE_URL=http://127.0.0.1:4000, LITELLM_API_KEY, LITELLM_MASTER_KEY,
     MIA_CORS_ORIGINS=http://localhost:3100,http://127.0.0.1:3100, VOYAGE_API_KEY= vacío).
     Si existe: cargarlo y seguir (nunca pisar).
     `MIA_ENV`: E1 revisa los usos reales en el código y elige el valor seguro (meta: prod).
  3. `initdb` si `<pg-data>/PG_VERSION` no existe (flags de la decisión 7).
  4. Postgres arriba: si el puerto ya responde como Postgres (pg_isready), usarlo y NO
     detenerlo al final; si no, `pg_ctl -w start` propio (y detenerlo al final SIEMPRE).
  5. Rol/DB/extensiones/schema.sql (lógica de init_db.py) + migraciones 003→030 en orden
     (runner Python nuevo, superusuario, autocommit) + checkpointer (lógica de
     init_checkpointer.py). Reusar/importar, no copiar-pegar donde sea posible.
  6. Exit 0. Cualquier fallo: exit ≠0 y ÚLTIMA línea de stdout = mensaje en llano (§G).
- Los `.sql` (schema + migrations) deben entrar al bundle: `datas` explícitas en
  `mia-backend.spec` con destino `mia/db/...`, y first_run debe resolverlos frozen
  (sys._MEIPASS) y dev (paquete). OJO: `test_packaging.py` exige exactamente 2 `collect_*`
  — usar `datas=[...]`, no collect.

## Contrato 2 — orchestration.json v2 (E3 implementa)

```jsonc
{
  "app_dir": "${local_app_data}/Mia",            // tokens en cualquier string
  "setup":  { "cmd": ["...mia-backend.exe", "--first-run", "--pg-bin", "...", "--pg-data", "...", "--pg-port", "55432"], "cwd": "..." },  // opcional
  "db":      { ... como hoy ... },
  "litellm": { "cmd": [".../mia-litellm.exe", "--config", ".../litellm_config.installer.yaml", "--port", "4000"],
               "cwd": "...", "env": {}, "health_url": "http://127.0.0.1:4000/health/liveliness", "port": 4000 },  // opcional
  "backend": { ... }, "frontend": { ... }
}
```

- Gatillo del setup: correrlo si `db.data_dir/PG_VERSION` NO existe **o** `app_dir/.env`
  NO existe (con app_dir configurado). Timeout 15 min, stage splash `"setup"` con texto en
  llano ("Preparando MIA por primera vez, puede tardar unos minutos…"). Exit ≠0 → stage
  error con la última línea de stdout del setup.
- LiteLLM: si el bloque existe → arranca ANTES del backend, stage `"litellm"`. Adopción de
  puerto ya ocupado exige IDENTIDAD: GET `/v1/models` con `Authorization: Bearer
  <LITELLM_MASTER_KEY leído del app_dir/.env>` debe responder 200 y contener los alias
  `claude-haiku` y `mia-local`; si no hay app_dir/.env o sin master key → NO adoptar
  (error en llano). Proceso lanzado por la cáscara: basta health_url 200 (hijo propio +
  Job Object). Shutdown: taskkill por PID, orden inverso.
- El JSON dev del repo (`desktop/orchestration.json`) gana el bloque `litellm` apuntando a
  `.venv-litellm/Scripts/litellm.exe --config <runtime dir> --port 4000` replicando el
  saneo de `scripts/run_litellm_clean.ps1` vía `env` del bloque… si eso NO es replicable
  limpio (el saneo es scrubbing, no seteo), dev puede quedar SIN bloque litellm
  (3 terminales como hoy) — decisión del ejecutor E3, documentada en desktop/README.md.
- Plantilla del instalador: `packaging/orchestration.installer.json` (estática, con tokens),
  documentada para F4.

## Contrato 3 — LiteLLM 2º exe (E2)

- `packaging/entry_litellm.py`, orden ESTRICTO:
  1. `os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")` (primera línea efectiva).
  2. Allowlist-load del `.env` de app_dir (resuelta como config.PROJECT_ROOT pero SIN
     importar mia — duplicación mínima consciente): SOLO `ANTHROPIC_API_KEY`,
     `VOYAGE_API_KEY`, `OPENROUTER_API_KEY`, `LITELLM_MASTER_KEY` y `LITELLM_*`.
  3. Scrub duro de `DATABASE_URL`, `PG_*` y las 15 variables de run_litellm_clean.ps1.
  4. Neutralizar `dotenv.load_dotenv` (no-op) ANTES de cualquier import de litellm.
  5. Delegar al CLI real de litellm (`--config`, `--port` desde argv).
- `.venv-litellm`: crearlo desde el MISMO intérprete base del `.venv` (sys.base_prefix),
  `pip install "litellm[proxy]==1.74.8"`; pyinstaller pineado con --no-deps + pins
  (patrón build_backend.ps1). Script: `packaging/setup_venv_litellm.ps1` (ASCII puro, PS 5.1).
- `packaging/mia-litellm.spec`: onedir, `upx=False`, `console=True`, collect de litellm
  completo (proxy trae data files) + tiktoken_ext; NADA de prisma; salida
  `packaging/dist/mia-litellm/`.
- `packaging/build_litellm.ps1`: patrón F1 (venv correcto, clean build, $LASTEXITCODE,
  check_env_pins NO aplica al venv litellm — en su lugar verificar pin litellm==1.74.8 del
  propio venv) + HUMO real post-build: puerto libre, config installer con master key en env,
  `/health/liveliness` 200, `/v1/models` 200 con Bearer y 401/403 sin Bearer, kill limpio.
- `packaging/litellm_config.installer.yaml`: copia del dev + `general_settings.master_key:
  os.environ/LITELLM_MASTER_KEY`.

## Gates nuevos (capa 1)

- E1 → `execution/test_first_run.py`: initdb REAL con el pg portable de
  `desktop/orchestration.json` (dev), puerto efímero libre, `--app-dir` temporal.
  Verifica: .env creado (JWT_SECRET ≥32; claves esperadas), PG_VERSION, rol mia_app sin
  SUPERUSER/BYPASSRLS, extensiones vector+pgcrypto, tablas núcleo + una tabla de migración
  tardía (p.ej. persona_playbooks), tablas checkpoint*, listen_addresses/port en
  postgresql.conf, postgres DETENIDO al final, idempotencia (2ª corrida OK y .env intacto
  byte a byte), fallo limpio con pg-bin inválido (exit ≠0 + mensaje en llano). Cleanup total.
- E2 → `execution/test_litellm_packaging.py`: gate en frío estilo test_packaging (existencia,
  orden cost-map→dotenv→import, allowlist, scrub, upx=False, onedir, venv correcto en el
  build script, .gitignore de dist/build, master_key en el yaml installer y NO en el dev).
- E3 → extender `execution/test_shell_hardening.py`: LitellmCfg + SetupCfg en OrchCfg,
  expansión de tokens, gatillo del setup (PG_VERSION/.env), orden litellm<backend,
  identidad de adopción litellm (models + Bearer), taskkill litellm en shutdown, stages
  nuevos. Mismo patrón de strip de comentarios.
- La integración de los gates a `scripts/run_tests.ps1` la hace el ORQUESTADOR al final
  (no los ejecutores — evita conflictos de edición).

## Reglas para TODOS los ejecutores

- Windows + PowerShell 5.1: scripts .ps1 en ASCII puro (sin tildes en código; los mensajes
  al usuario final en llano van en la UI/stdout de Python, que sí es UTF-8).
- Mensajes visibles para el abogado: español llano, §G (cero jerga técnica).
- Idempotencia en todo el bootstrap; nunca regenerar secretos existentes.
- No tocar: flujo HITL, test_rls, check_env_pins, litellm_config.yaml (dev), puertos dev.
- Cada ejecutor corre su gate y lo deja en verde antes de reportar. Los tests son scripts
  (`python execution/test_X.py`), NO pytest.
- Archivos por ejecutor (disjuntos): E1 = `backend/mia/setup/*`, `packaging/entry_backend.py`,
  `packaging/mia-backend.spec`, `execution/test_first_run.py` (+ ajuste quirúrgico de
  `execution/test_packaging.py` SOLO si las datas nuevas lo rompen). E2 = `packaging/*litellm*`,
  `execution/test_litellm_packaging.py`. E3 = `desktop/**`, `packaging/orchestration.installer.json`,
  `execution/test_shell_hardening.py`.
