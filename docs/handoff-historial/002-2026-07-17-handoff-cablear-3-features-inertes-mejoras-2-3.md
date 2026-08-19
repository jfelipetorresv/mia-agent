## 2026-07-17 — HANDOFF: cablear 3 features inertes + mejoras 2/3 del análisis claudeclaw

**Para quien retome (terminal fresca).** Rama `feature/robustecimiento-sin-aws`. Repo git en `D:\Inteligencia Artificial\Mia-Super Agent\mia`. Intérprete `.venv\Scripts\python.exe`. DB portable en 127.0.0.1:55432 (encender con pg_ctl si no escucha, ver memoria "mia-arranque-entorno-local"). Los tests son scripts: `.venv\Scripts\python.exe execution\test_X.py`. **HALT si `test_rls.py` falla.**

### Contexto: qué se hizo hoy (commits en la rama)
- `8cdc7a3` — cerró 6 de 8 riesgos de la sesión 48 (#68/#69/#70/#71/#72/#73).
- `ac7ed31` — fix contraste del control "Apariencia" (validación visual de las 13 pantallas: todas OK).
- `e8ce3b3` — **caching medido y CABLEADO** (antes el "~75%" era falso: ni medido ni activado) + arreglos de integridad de una auditoría de 4 frentes (datos jurídicos fabricados neutralizados, métricas del panel honestas, afirmaciones de docs corregidas).
- Análisis de referencia: `docs/analisis-claudeclaw-os.md` (de dónde salen las mejoras 2/3).

### REGLAS DE EJECUCIÓN (respetar)
- Si usas equipo de agentes: **grupos de archivos DISJUNTOS**, ningún agente hace git (el coordinador commitea), y **reservar el número de migración al EMPEZAR** (última usada = `042`; siguiente libre = `043`). El migrador ya bloquea prefijos duplicados (Riesgo #73).
- Cada cambio con su gate VERDE. §G: el abogado nunca ve jerga técnica.
- No degradar lo que ya es superior (migrador con ledger, personas en RLS, política de modelo).

### TRABAJO PENDIENTE (metas claras)

**A. Cablear Pinecone (hoy captura la clave de nube y muestra "activo" sin usarla).**
- Meta: que los vectores se escriban/consulten en Pinecone como store SECUNDARIO, detrás del opt-in por tenant que YA existe (`tenant_settings.config['pinecone']`).
- Archivos: `backend/mia/connectors/pinecone_connector.py` (interfaz `upsert/query/delete` + `get_pinecone_connector()`, hoy CERO llamadores en producción). Cablear `.upsert()` en el pipeline de ingesta (`backend/mia/ingest/`, `connectors/local_folders.py`, `connectors/obsidian_sync.py` — hoy solo escriben pgvector) y `.query()` en `agents/retrieval.py` como store secundario. Corregir el indicador "external_store: active" de `api/routes/ux.py` (~1676) para que refleje uso real.
- Nota: `pip install "pinecone>=3"` + pinnear en `pyproject` (Riesgo #18); crear índice dim 1024 coseno. Gate: extender `test_pinecone*` si existe; verificar aislamiento por namespace `{prefix}_{tenant_id}` (Riesgo #17).

**B. Cablear MCP (hoy guarda secretos y dice "conectado" sin lanzar nada).**
- Meta: un ejecutor que, para los servidores MCP habilitados del tenant, los levante y exponga sus tools al turno.
- Archivos: `backend/mia/mcp/service.py` (`resolve_server()` → `ResolvedMCPServer`, hoy sin consumidor), `mcp/catalog.py`, `mcp/security.py`, ruta `api/routes/mcp.py`. Falta el punto en `agents/graph.py` (o `agents/research.py`) que resuelva el server habilitado, lo levante como subproceso (cliente MCP stdio) y ofrezca sus tools durante el turno. Gate: `test_mcp.py` + uno nuevo de invocación real.
- Seguridad: los subprocesos MCP corren fuera del RLS (Riesgo #10) — acotar cwd/entorno como hace `agent_hub.sanitize_subprocess_env`.

**C. Conectar el Banco de oro al examen (hoy el abogado aprueba casos que no alimentan nada).**
- Meta: que `eval/cases.py::load_tenant_gold_cases()` (hoy CERO llamadores) alimente `eval/harness.py::run_suite` (hoy usa los casos SINTÉTICOS `GOLDEN_CASES`).
- Entrega: un endpoint "evaluar contra mi banco" o un job periódico, gated por `allow_eval_real_data` (ya existe). Correr `run_eval.py` deja de ser solo-dev. Gate: `test_gold_cases_api` + nuevo de que el banco confirmado influye en el examen.

**D. Mejora 2 — blindaje del instalador (antes de la prueba en vivo de Pipe).** Detalle en `docs/analisis-claudeclaw-os.md` §2.
- **Preservar secretos en upgrade (ALTO):** verificar que `backend/mia/setup/first_run.py`/`env_writer.py` NUNCA regeneran `DB_ENCRYPTION_KEY` ni el `.env` semilla si ya existen (leer-existente-o-generar). Un fallo aquí = datos cifrados irrecuperables al reinstalar.
- **Smoke-test post-first-run (ALTO):** al final del first-run, health-check real (FastAPI `/health`, LiteLLM.exe vivo, nº migraciones aplicadas == esperadas, checkpointer OK) y reportar. "Instaló" → "instaló y arranca".
- **Backup pre-migración (MEDIO-ALTO):** `pg_dump` a `app_dir/backups/pre-{ver}.dump` con rotación (3) ANTES de aplicar migraciones; enganchar `backend/mia/setup/backup.py` a `db_bootstrap.apply_migrations`.
- **Root de config canónico (ALTO/S):** auditar que TODO derive de `paths.py`/`app_dir`; nada hardcodee `%APPDATA%`/`expanduser` en paralelo.

**E. Mejora 3 — atajos de despacho + health-check de playbooks.** Detalle en `docs/analisis-claudeclaw-os.md` §5.
- **Atajos:** comando del abogado → PROMPT CANÓNICO reproducible que dispara un playbook/persona (capitaliza `playbooks`+`personas` que ya existen). Reservar migración si hace falta tabla.
- **Health-check de playbooks:** check que valida que cada playbook sigue "sano" (referencias resuelven, citas verificables), persistiendo estado. Alineado con la cultura [VERIFICAR].

**F. Limpieza trivial:** borrar `cron/scheduler.py::gepa_run_all_tenants()` (función huérfana, nunca registrada; Dreams ya llama GEPA internamente).

### VERIFICACIÓN PENDIENTE (capa 3 de Pipe, en vivo)
- **Caching:** confirmar el hit-rate REAL con API de Anthropic y un `SOUL.md` representativo (el prefijo estable debe superar el mínimo de ~1024 tok; sin SOUL real, la medición lee 0 — correcto pero da falsa impresión de "no funciona").
- **`test_ux.py`** (hace `next build`, ~10 min): confirma el panel nuevo (bloque "En el despacho" + caché) end-to-end.
- E2E del instalador en máquina limpia + delegación D3 (Riesgo #66) + banco de oro de punta a punta.

### Hallazgos de la auditoría NO críticos que quedaron anotados (no bloquean)
- Precios LLM hardcodeados con fecha (`metrics/usage.py:37`) — externalizar a config con `last_verified` algún día.
- Slugs de OpenRouter sin confirmar (Riesgo #62) — validar contra openrouter.ai/models antes de vender.
- Metadatos jurídicos del catálogo: cross-check ya añadido (corpus_factory); completar festivos trasladables/pascuales de `holidays.json` es trabajo de verificación jurídica (no inventar).

---

