# Mia · SOP — Curator (mantenimiento semántico de playbooks)
# Última actualización: 2026-06-14 (Módulo 3b)

## Qué hace el Curator
El Curator mantiene sanos los playbooks de cada despacho: detecta los que se solapan, los
**consolida** en uno mejor, y **poda** los que llevan tiempo sin usarse. Vive en
`backend/mia/memory/curator.py` (clase `Curator`). Por cada tenant, `run(tenant_id)` ejecuta:
1. `load_playbooks` — SELECT de los playbooks `status='active'`.
2. `find_candidates` — pares con similitud coseno > 0.85 (ver abajo).
3. `consolidate` — fusiona cada par con un LLM fuerte y archiva los originales.
4. `prune` — archiva los que no se usan hace > 90 días.
Devuelve `{analyzed, consolidated, pruned, errors}`. `run_all_tenants()` lo corre para todos.

## Cuándo corre
Job `curator_weekly` registrado en `cron/scheduler.py`, intervalo **168h (semanal)**. Pensado
para **domingos 2am**, pero el scheduler v1 NO tiene timezone awareness: dispara por intervalo
desde el arranque, no a una hora exacta. Si se necesita la hora exacta del domingo, añadir
soporte de cron/timezone al scheduler.

## Por qué se añadió persistencia a PlaybookManager (decisión #18)
El Módulo 2b (`PlaybookManager`) se construyó **in-memory** (dataclasses frozen, sin tabla). Un
cron semanal no puede operar sobre estado en memoria que se pierde al reiniciar, así que 3b
añade la tabla `playbooks` (migración 005) y un backend de DB al manager. **La interfaz pública
de 2b no cambió**: con `PlaybookManager()` (sin pool) el manager sigue 100% in-memory (el gate
`test_playbook_manager.py` pasa sin tocarse); con `PlaybookManager(pool=db.pool, tenant_id=…)` se
activan los métodos async `register_playbook` / `get_index` / `get_playbook` / `mark_used` /
`list_active`, que leen/escriben en `playbooks` bajo RLS.

## Tabla `playbooks` (migración 005, RLS por-tenant)
`id, tenant_id, title, summary, applies_when, content, status (active|archived|draft),
usage_count, last_used_at, embedding vector(1024), metadata jsonb, created_at, updated_at`.
`UNIQUE(tenant_id, title)`; HNSW en embedding; BTREE en (tenant_id, status). El embedding se
genera de `summary + applies_when` con voyage-law-2 al registrar (`register_playbook`).

## Criterio de consolidación (umbral 0.85)
`find_candidates` usa el operador `<=>` de pgvector (distancia coseno) sobre el embedding:
`1 - (a.embedding <=> b.embedding)` = similitud coseno. Devuelve los pares activos (con
`a.id < b.id`, sin auto-pares ni duplicados) cuya similitud **> 0.85**. `consolidate` pide a
`call_llm(task="curator")` (→ alias `claude-sonnet` = `anthropic/claude-sonnet-4-6`) un playbook
fusionado, lo inserta como nuevo `active` (título `Consolidado: A + B`, linaje en `metadata`) y
pone los dos originales en `archived`. **Idempotente:** si un original ya no está activo (ya se
consolidó), el par se salta.

## Criterio de poda (90 días)
`prune` archiva los playbooks `active` con `last_used_at < now() - 90 días`. Los que **nunca se
usaron** (`last_used_at NULL`) NO se podan (no se castiga un playbook nuevo por antigüedad).
`mark_used` (en PlaybookManager) actualiza `usage_count` y `last_used_at` cuando un playbook se
usa de verdad.

## Cómo forzar una corrida manual
```python
from mia.cron import build_scheduler
sched = build_scheduler()
await sched.run_job("curator_weekly")     # corre run_all_tenants ya mismo
# o, para un solo despacho:
from mia.memory.curator import Curator
await Curator().run("<tenant_uuid>")
```
(Requiere el pool abierto: `await mia.db.pool.open_pool()`.)

## Self-Annealing — si el gate falla, revisar en este orden
1. **¿Corrió la migración 005?** `init_playbooks.py` debe reportar `mia_app INSERT=True
   RLS=True`. Re-correr (idempotente).
2. **`find_candidates` no encuentra nada:** confirmar que los playbooks tienen `embedding` NO
   NULL (se llena en `register_playbook`; los inserts directos del gate lo pasan explícito) y
   que el umbral es `> 0.85` ESTRICTO. `<=>` es distancia coseno → similitud = `1 - distancia`.
3. **`consolidate` duplica:** revisar el chequeo "ambos activos" (idempotencia) y el
   `ON CONFLICT (tenant_id, title) DO NOTHING`.
4. **`prune` archiva de más/menos:** recordar que `last_used_at IS NULL` NO se poda; el corte es
   estricto `< now() - 90 días`.
5. **404 del modelo:** `task="curator"` debe mapear al **alias** `claude-sonnet` (existe en
   `litellm_config.yaml`), no al id crudo `claude-sonnet-4-6`.
6. **El gate 2b se rompió:** los métodos sync de PlaybookManager NO deben cambiar; con
   `pool=None` el comportamiento es el in-memory original.
7. **Enumeración de tenants:** `run_all_tenants` usa una conexión admin para listar tenants
   (cross-tenant, Riesgo #15); la curaduría por tenant sí va por RLS.
