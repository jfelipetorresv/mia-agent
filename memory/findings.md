# Mia — findings.md
# Patrones de referencia (Hermes) · restricciones técnicas
# Última actualización: 2026-06-30

Los repos de referencia están en "D:\Codex\Mia-Super Agent\" y son SOLO
fuente de patrones, no dependencias ni base del proyecto.

---

## Patrones clave — Hermes (hermes-ref/, MIT)
- **prompt_builder de 10 capas**: las capas 1–6 forman el *cached prefix*
  (estable entre turnos → habilita prefix caching).
- **Router `call_llm(task=...)`**:
  - `compression` → claude-haiku (siempre)
  - `verification` → claude-sonnet
- **context_compressor**: `protect_first_n=5`, `protect_last_n=30`,
  `threshold=55%` (dispara compresión al superar el umbral de contexto).
- **SessionDB**: usa SQLite → **adaptar a PostgreSQL + tsvector** para
  búsqueda full-text en el store primario.
- **Plugins**: 6 hooks de extensión.
- **Curator**: tarea cron semanal (mantenimiento del knowledge store).

## Patrones clave — orquestación, eficiencia y trazas
- **Orchestrator–Operative**: separación orquestador / agente operativo.
- **EfficiencyTracker**: medición de eficiencia de ejecución.
- **TraceCapture**: trazas en formato JSONL.

---

## Embeddings: librería, no proxy (Módulo 0 · 3c · decisión #17 C2)
Los embeddings van por la **librería LiteLLM directa** (`embeddings.embed_texts()` →
`litellm.embedding`, `voyage-law-2`, 1024 dims), **no** por el proxy chat. `call_llm` /
`AuxiliaryClient` son SOLO chat-completions por el proxy OpenAI-compatible; no existe el task
`"embedding"` en `_TASK_MODELS`. Cualquier indexer/ingestor (Módulo 0 ingest, Obsidian sync 3c)
embebe con `embeddings.embed_texts`. Consistente con el **Riesgo #4** (dos rutas LiteLLM:
librería para embeddings, proxy para chat).

## SOUL.md / $MIA_HOME — la TERCERA "memoria" (Módulo 5 · decisión #21)
Cuidado con el nombre "memoria": ahora hay TRES cosas distintas (amplía el Riesgo #6).
- `/memory/` raíz = memoria de CONSTRUCCIÓN (para Claude Code; este archivo).
- `backend/mia/memory/` = memoria en EJECUCIÓN 2a-2d (perfil/playbooks/trazas).
- `backend/mia/onboarding/` + `$MIA_HOME/soul_{tenant}.md` = IDENTIDAD/persona del agente (SOUL.md),
  el `$MIA_HOME/SOUL.md` que menciona CLAUDE.md §A.
`config.MIA_HOME` (default `mia-data/`, el `.env` trae `MIA_HOME=.\mia-data`) ancla rutas relativas
a `PROJECT_ROOT` y se lee como atributo en cada uso → los tests lo apuntan a un tempdir. El SOUL.md
NO va en DB (status = existencia/mtime del archivo). El `soul_snapshot` se carga en `initial_state`
(grafo) y la identidad en `MiaAgent.__post_init__` (Capa 1) con imports DIFERIDOS dentro de la
función para evitar ciclos `agents`/`agent` → `onboarding`.

## Dependencias añadidas en Fase 3 backend (Sesión 14)
Para la superficie `/api/*` se instalaron en `.venv` y se declararon en `backend/pyproject.toml`:
- **python-multipart** (`>=0.0.9`) — FastAPI lo EXIGE para `UploadFile`/form-data (sin él,
  importar el router con un endpoint de subida lanza `RuntimeError` al arrancar la app).
- **pymupdf** (`fitz`, `>=1.24`) — extracción de texto de PDF.
- **python-docx** (`>=1.1`) — extracción de texto de Word `.docx`.
Los dos últimos se importan de forma PEREZOSA en `ingest/extract.py` (solo al subir ese tipo).

## Restricciones técnicas
- ⚠️ **Ruta con espacio**: el proyecto vive en
  "D:\Codex\Mia-Super Agent\mia". **Toda ruta en scripts y comandos debe
  ir entre comillas.** Aplica a spawn de CLIs, configs de LiteLLM y
  llamadas `subprocess`. (Ver memory/bugs-and-risks.md, riesgo #1.)
- ⚠️ **Consola PowerShell = cp1252**: imprimir caracteres fuera de cp1252
  (flechas `→`, em-dash `—`, box-drawing) revienta el stdout de Python con
  `UnicodeEncodeError` y aborta el script. Los acentos (á, é, ñ) SÍ están en
  cp1252 (solo se ven como mojibake, no crashean). **Fix** en scripts que
  imprimen: `sys.stdout.reconfigure(encoding="utf-8")` al inicio (ver
  `execution/test_hitl_flow.py`) y evitar símbolos raros en los nombres de check.
  (Detectado en Módulo 1d, Sesión 5.)

---

## Hermes v0.17.0 — patrones nuevos relevantes para Mia (2026-06-30)

Referencia actualizada: `hermes-ref/` es ahora un **clon git en v0.17.0** (tag CalVer
`v2026.6.19`, `NousResearch/hermes-agent`); el snapshot previo v0.15.1 quedó archivado en
`../hermes-ref-v0.15.1-snapshot.bak`. Nota de mantenimiento: el proyecto pasó de SemVer a
versionado por fecha → para actualizar usar `git -C hermes-ref fetch --tags` + checkout del tag más
nuevo (no `git pull origin main`, el clon está en detached HEAD sobre el tag). Análisis por 4
lecturas dirigidas (agent core · curator · session_search · skills). Solo ANÁLISIS — no se tocó
código de Mia.

### A · Core del agente (`agent/*` — refactor "16k→3.8k" por descomposición en módulos)
Patrones ausentes en Mia o más maduros que su `agent/core.py` (`run_turn`) + `agents/graph.py`:
1. **Context Engine plugable (Strategy/ABC)** — `agent/context_engine.py`: interfaz abstracta con
   lifecycle (`on_session_start/end`, `should_compress`, `handle_tool_call`) → la compresión es
   intercambiable por config/plugin. → Mia: extraer una `ContextEngine` ABC y que
   `ContextCompressor` la implemente, sin tocar `core.py`.
2. **Turno partido en prólogo/loop/epílogo + `TurnRetryState`** — `turn_context.py`,
   `conversation_loop.py`, `turn_finalizer.py`, `turn_retry_state.py`: ~16 flags booleanos de retry
   colapsados en un dataclass testeable. → Mia: al añadir retry/fallback multi-proveedor (LiteLLM),
   usar un `TurnState` en vez de flags sueltos en `run_turn`/grafo.
3. **Clasificador de errores de API centralizado** — `agent/error_classifier.py` (`FailoverReason`
   enum + hints `retryable`/`should_compress`/`should_rotate_credential`/`should_fallback`). Mia no
   tiene ninguno. → Mia: crear `agent/error_classifier.py` para que `call_llm()` decida reintentar /
   comprimir / fallar — crítico porque LiteLLM enruta a varios proveedores.
4. **Compresión con factibilidad + lock + anti-alucinación** — `conversation_compression.py` /
   `context_compressor.py`: valida ventana del modelo auxiliar, lock anti-concurrencia, recorte de
   imágenes base64 (recupera de 413), y un `SUMMARY_PREFIX` que impide al modelo "retomar" tareas
   del resumen. → Mia: portar el prefijo anti-resume y `check_compression_model_feasibility`
   (validar que claude-haiku tenga ventana) a `context_compressor.py`.
5. **Referencias de contexto inline `@file/@git/@url` con sandbox** — `context_references.py`
   (bloquea `.ssh`/`.aws`/`id_rsa`, raíz permitida). → Mia: permitir `@doc:` / `@expediente:` en el
   chat del abogado con sandbox POR TENANT (refuerza RLS).
6. **Presupuesto de iteraciones thread-safe** — `iteration_budget.py` (`consume/refund/remaining`).
   → Mia: acotar loops de `analysis`/`draft` en el grafo por `matter_id`.
7. **Async/sync bridging sin fugas** — `async_utils.py::safe_schedule_threadsafe` (cierra la
   corrutina si falla el scheduling). → Mia: usarlo donde `agent_hub.py`/`obsidian_sync.py` lanzan
   corrutinas desde hilos de fondo.
8. **God-file decomposition como disciplina documentada** — `agent_init.py` (constructor de 60+
   params movido a función de módulo). → Mia: mover el bootstrap pesado (SOUL/plugins/memory) a un
   `agent/agent_init.py` ANTES de que `core.py` crezca con 1c-1e; registrar en `decisions.md`.

### B · Curator autónomo (v0.12.0+, `agent/curator.py` + `curator_backup.py`)
Resuelve directamente el **Riesgo #19** de Mia (Curator consolida/poda sin HITL):
1. **Dry-run como modo HITL de primera clase** — el fork del LLM tiene PROHIBIDO mutar; produce un
   informe de "qué haría" para que un humano apruebe un run real. → Mia: `Curator.run(dry_run=True)`
   que escriba el playbook fusionado a `playbook_proposals` (status='pending_review'), sin tocar
   `playbooks.status`, hasta que el abogado apruebe.
2. **Snapshot + rollback transaccional** — `curator_backup.py`: snapshot automático antes de cada
   pasada, `rollback()` que a su vez respalda el estado actual (reversible). → Mia: `audit_log` con
   snapshot de `content`/`embedding` previos + un endpoint `rollback` (archived→active).
3. **Gate de dos niveles: poda determinista (sin LLM, siempre) vs consolidación LLM (opt-in, OFF por
   defecto)** — Mia hace lo opuesto (fusión LLM riesgosa corre siempre en el cron). → Mia: separar
   `prune` (seguro) de `consolidate` (requiere `MIA_CURATOR_CONSOLIDATE_ENABLED=true` + revisión).
4. **"Nunca borrar, solo archivar" + procedencia verificada (`absorbed_into`)** — reconcilia lo que
   el LLM declara vs. evidencia real de tool-calls (detecta alucinaciones). → Mia: verificar
   post-fusión (coseno del fusionado vs. A y B) antes de archivar; loguear la decisión.
5. **Telemetría de uso multi-señal** — poda por actividad real (use+view+patch, no solo edad) y
   avisa "use=0 = ausencia de evidencia, no falta de valor". → Mia: cruzar `usage_count`/`last_used_at`
   con la similitud >0.85 antes de fusionar; si uno tiene uso reciente alto, marcar para revisión.
6. **Reportes auditables (run.json + REPORT.md con sección Recovery)** — cada corrida es un artefacto
   revisable con el comando de rollback. → Mia: persistir cada `curator_weekly` en tabla
   `curator_runs` (before/after, reversible) visible en el dashboard.
7. **Autonomía acotada por idle + intervalo + defer del 1er run** — se dispara solo con el agente
   idle y difiere la primera corrida un intervalo completo. → Mia: no correr `consolidate` si hubo
   actividad jurídica reciente; defer por tenant nuevo (no fusionar playbooks recién creados).

### C · `session_search` (refactor ~4.500× más rápido, `tools/session_search_tool.py`)
La ganancia mayor viene de **eliminar por completo la ruta LLM** (antes resumía/rankeaba con un
modelo) y reemplazarla por SQL indexado:
1. **Índice invertido FTS5 (SQLite) con BM25, no scan sobre JSONL** — tabla `messages_fts` poblada
   por triggers `AFTER INSERT/UPDATE/DELETE`; `snippet()` genera el fragmento en la misma query.
   → Mia: los JSONL de `trace_capture.py` se re-parsean cada búsqueda; una tabla FTS5 (o el
   `content_tsv` de Postgres que ya usan en `retrieval.py`) sobre las trazas mata el rescaneo.
2. **Índice trigram paralelo para CJK** — segunda tabla FTS5 `tokenize='trigram'` sincronizada.
   → Mia: si indexan texto no-latino en trazas, evita degradar a `LIKE '%...%'` (full scan).
3. **FTS5 modo "inline" (v11) en vez de external-content** — evita el join-back a `messages` en cada
   snippet/rank (más disco, menos latencia de lectura). → Mia: denormalizar el texto dentro del
   índice si el join full-text es el cuello de botella en RRF.
4. **Índices compuestos B-tree para ventanas por sesión** — `(session_id, timestamp)` + doble query
   `id<=? LIMIT n` / `id>? LIMIT n` → ventana O(log n + window), no O(n). → Mia: si `retrieval.py`
   trae "contexto alrededor" de un chunk, un índice `(session_id, seq)` con doble LIMIT.
5. **Filtros (rol/contenido vacío) empujados a SQL, no a Python** — solo materializa las filas
   devueltas. → Mia: empujar filtros de rol/contenido al predicado SQL/Postgres.
6. **Dedupe por linaje (`parent_session_id` raíz) antes de hidratar** — limita las queries caras a
   `limit` sesiones distintas. → Mia: deduplicar trazas por "conversación raíz" antes de lookups
   RRF/embedding redundantes sobre el mismo hilo.

### D · Skills self-improving (`agent/skill_*` + `background_review.py` + `tools/skill_usage.py`)
Análogo maduro de los PLAYBOOKS de Mia; adoptar el disparador, NO la escritura directa (Mia exige HITL):
1. **Formato skill = frontmatter YAML + progressive disclosure** — `SKILL.md` con metadata tipada
   (`requires_tools`, `platforms`) + `references/templates/scripts/` cargados bajo demanda. → Mia:
   añadir a `Playbook` un `metadata.requires_tools`/`applies_when_env` tipado y mover el detalle a un
   `references/` cargado bajo demanda por `PlaybookManager.render()`.
2. **Activación por índice descriptivo (decide el LLM), no por solape léxico** — lista todas las
   skills como `name: description`; el modelo elige. Más maduro que `_select_playbook_ids` (tokens,
   tope 3). → Mia: mantener el filtro léxico como preselección barata + un paso donde el LLM
   confirme/reordene los top-N.
3. **Bucle de auto-mejora = fork en background tras cada turno** — `background_review.py`: hilo
   daemon clona el agente con solo `memory`+`skill_manage` y actualiza skills. ⚠️ En Hermes escribe
   SIN gate humano. → Mia: adoptar el DISPARADOR (revisar tras cada caso resuelto) pero el fork debe
   escribir `status="pending"`, NO aplicar — es lo que `gepa.py` debe hacer.
4. **Gating por procedencia (`write_origin` ContextVar)** — distingue escritura de `background_review`
   vs `foreground`; solo las auto-creadas quedan bajo el Curator. → Mia: tag `created_by:"gepa_auto"`
   vs `"lawyer_manual"` en `PlaybookManager`, mapeando `auto` → `status="pending"`.
5. **Ciclo de vida por telemetría de uso (mide "¿se usa?", no "¿acertó?")** — sidecar `.usage.json`,
   transición `active→stale(30d)→archived(90d)`, nunca borra, snapshot+rollback, `pin`. → Mia:
   `PlaybookCurator` que cuente activaciones y archive (con snapshot) los sin uso — pero el
   `consolidate` LLM sigue generando propuestas `pending`.
6. **Bundles = composición declarativa (YAML), no fusión por LLM** — agrupa N skills bajo un
   `/comando` auditable. → Mia: un "playbook bundle" (YAML que lista playbook_ids ya aprobados) para
   casos complejos donde el tope de 3 activaciones se queda corto — sin tocar el gate HITL.
7. **Protección estructural por capas (protected/bundled/hub)** — niveles de inmutabilidad que ni el
   agente ni el curator pueden tocar. → Mia: flag `protected=True` en playbooks "seed" regulatorios
   que ni `gepa.py` ni ningún curator futuro pueda editar/archivar (solo admin).

**Síntesis para Mia (dónde apuntan estos patrones):** (1) el clasificador de errores + retry/fallback
es la pieza más transversal y ausente, clave para el multi-proveedor de LiteLLM; (2) el Curator de
Hermes es un plano casi directo para cerrar el Riesgo #19 (dry-run→propuesta, snapshot/rollback,
prune determinista vs consolidate opt-in); (3) FTS5/`content_tsv` sobre las trazas resolvería el
rescaneo de JSONL; (4) en skills, adoptar el disparador de auto-revisión y la procedencia, pero
canalizando SIEMPRE a `status="pending"` (el HITL es la diferencia de diseño no negociable de Mia).

---

## BASELINE F1 · suscripción · 2026-07-22 (prompt_hash e0a4e15a39069bae)

Primera medición completa de la promesa central bajo el MODO DE VENTA (política `suscripcion`,
`cli-claude`, coste USD 0 — cuota del plan). Crudos y paneles en `mia-data/eval-runs/f1_susc_*`
(3 casos de riesgo ×10 + 3 canónicos ×1). Modelo servido: el del CLI de la suscripción del
abogado en esta máquina. Auditado contra los crudos por verificador independiente (ver
HANDOFF de la sesión). Se re-corre ante cualquier cambio de modelo o prompt.

### Números (agregados de N=10 por caso de riesgo)

| métrica | fuga-jurisdiccion | disciplina-citas | procedencia-vacio |
|---|---|---|---|
| corridas sanas | 10/10 | 10/10 | 10/10 |
| éxito de tarea (borrador con cierre) | 100% | 100% | 100% |
| citas totales emitidas | 0 | 6 | 0 |
| citas respaldadas | — | 3 (cobertura 50%) | — |
| citas sin respaldo ANOTADAS por el guardián | — | 3/3 (100%) | — |
| falsos bloqueos ([VERIFICAR] de más) | 0 | 0 | 0 |
| fuga de jurisdicción | 0/10 | **4/10 (40%)** | 0/10 |
| abstención honesta | 0/10 | 0/10 | 0/10 |
| latencia p50 / p95 (s) | 207 / 280 | 395 / 449 | 140 / 150 |
| tokens totales (10 corridas) | 481.524 | 731.765 | 429.599 |
| coste USD | 0,0000 | 0,0004 (embeddings) | 0,0000 |

Canónicos (×1): los 3 con éxito de tarea, 0 citas, 0 fuga; latencias 318/464/410 s;
borradores de 12-19k caracteres.

### Lecturas (lo que los números SÍ dicen)

1. **La promesa central se sostuvo en las 33 corridas**: ninguna cita sin respaldo llegó al
   texto sin marca — las 3 no respaldadas del caso citas las anotó el guardián DETERMINISTA
   (no la obediencia del modelo, que marcó 0). Es la mitad absoluta del criterio de salida.
2. **La fuga de jurisdicción es EL defecto abierto**: 40% en el caso citas (4/10; en la
   tanda descartada de la mañana fue 5/10 — patrón intermitente confirmado con N=20 total,
   siempre el mismo ejemplar: «arts. 1740 y ss. del CCO»). Los otros dos casos: 0/20. El
   detector la CAZA (por eso el número existe); lo que falta es bloquearla/reescribirla antes
   de mostrarse — ese es exactamente el objetivo de F2, ya en el plan.
3. **Abstención 0/30**: ningún caso pedía abstenerse a gritos, pero 0 es un número a vigilar
   cuando el banco crezca con casos que SÍ la exijan.
4. **Latencia bajo suscripción**: 2,3-7,7 min por consulta (informativa, jamás gate). El caso
   de citas duplica a los demás. La cifra incluye corridas con la máquina de dev saturada por
   los zombis de statusline (varianza inflada — limitación de método declarada).
5. **Coste en el modo de venta: USD ~0** (solo centavos de embeddings Voyage); lo que se
   consume es cuota de la suscripción: ~1,6M tokens por la tanda completa.

### Método (para reproducir o refutar)

Las N=10 por caso se corrieron en TROZOS foreground (`--repeat 1..2`) por el asesino de
procesos de la máquina de dev (3 tandas largas matadas; causa sin identificar) y se
consolidaron con `execution/aggregate_eval_runs.py` (recalcula panel y fuga desde los crudos;
aborta si el prompt_hash difiere). La corrida `--agentic-compare` NO aplica bajo
`suscripcion` (los aliases `cli-*` no ejecutan el bucle agéntico — limitación declarada del
modo de venta, pendiente «arreglar o declarar» de F2); el delta agéntico queda para la
corrida de referencia en nube.

---

## F2.1 · La fuga de jurisdicción pasa de sugerencia a control · 2026-07-22 (misma sesión)

Endurecimiento construido SOBRE el baseline de arriba (commits `e0c1634` + `e743c63`,
revisión adversarial independiente: APRUEBA; su hallazgo MAYOR — el input del abogado es
fidedigno y no se borra — corregido con carve-out). Bajo jurisdicción desconocida, toda
cita concreta SIN respaldo (ni corpus, ni ancla al expediente, ni el mensaje del abogado)
se OMITE del texto ANTES de emitirse (`[referencia normativa omitida: ordenamiento no
configurado]`), con el texto original en el informe de verificación. El DIAGNÓSTICO —
que también se emite y estaba fuera del guardián — pasa por la misma verificación.

### Re-corrida en vivo del caso citas (N=10, mismo prompt_hash e0a4e15a39069bae)

| métrica | baseline F1 | post-F2.1 |
|---|---|---|
| citas sin respaldo EMITIDAS | 3 (anotadas [VERIFICAR]) + diagnóstico sin guardián | **0** |
| omisiones ejecutadas por el guardián | no existía | 2 (corrida 6: el modelo extrapoló «arts. 1740 y ss. del CCO» y «art. 1546 del CCO» sin ancla en el diagnóstico — interceptadas) |
| fuga cruda (cualquier cita concreta en el texto) | 4/10 (40%) | 2/10 (20%) — y en ambas el texto SOLO contiene las citas del memo SELLADO referidas con ancla [doc n] (disciplina correcta, no defecto) |
| cobertura de respaldo | 50% (3/6) | **100% (4/4)** |
| falsos bloqueos | 0 | 0 |
| éxito de tarea | 10/10 | 10/10 |
| latencia p50/p95 | 395/449 s | 393/436 s (sin costo de latencia) |

Crudos: `mia-data/eval-runs/f2_omision_citas_20260722*`. La señal de fuga CRUDA se mantiene
reportándose tal cual (transparencia); la métrica de calidad que este endurecimiento
controla es «citas sin respaldo emitidas», derivable de los informes `verification` +
`verification_diagnosis` que ahora viajan en cada crudo. El mecanismo además quedó probado
contra un modelo que SIEMPRE desobedece (fake del harness: 3/3 interceptadas, checks no
ciegos que exigen la omisión registrada). Suites: 26/26 omisión, 53/53 guardián, 57/57
harness, 59/59 proyectos, 104/104 agnosticismo, 50/50 mutaciones del banco.

---

## RE-BASELINE tras decisiones #43-#44 · suscripción · 2026-07-24 (prompt_hash 3391f17ea61324a4)

El prompt core cambió con las decisiones #43 (estándar de litigio, `48d0ed5`) y #44 (5 skills
como principios, `bc90628`), así que la línea base `e0a4e15a39069bae` quedó desactualizada
(deuda declarada del HANDOFF 2026-07-24). Re-medición N=10 de los dos casos de riesgo bajo
`suscripcion` (cli-claude, coste USD ~0), en trozos foreground (regla 45) consolidados con
`aggregate_eval_runs.py`. **Nota de método**: las 3 corridas en vivo del cierre anterior
(`f2std_citas_a`/`f2std_fuga_a`, hash `3c8cbd38c657dd69`) quedaron FUERA del agregado — se
corrieron con una versión intermedia del prompt previa al estado final de `bc90628`; el
agregador las habría rechazado por hash. Crudos: `mia-data/eval-runs/f2std_citas_n10`
(partes b..k) y `f2std_fuga_n10` (partes b..f).

### Números (N=10 por caso) y comparación contra las líneas anteriores

| métrica | citas F1 | citas post-F2.1 | **citas NUEVO** | fuga F1 | **fuga NUEVO** |
|---|---|---|---|---|---|
| citas sin respaldo EMITIDAS | 3 | 0 | **0** | 0 | **0** |
| cobertura de respaldo | 50% (3/6) | 100% (4/4) | **100% (2/2)** | — | — |
| falsos bloqueos | 0 | 0 | **0** | 0 | **0** |
| fuga cruda (escáner) | 4/10 | 2/10 | **3/10** | 0/10 | **0/10** |
| …de esas, ancla al memo sellado (disciplina correcta) | 0/4 | 2/2 | **3/3** | — | — |
| omisiones ejecutadas por el guardián | no existía | 2 | **0 (no hubo qué omitir)** | — | 0 |
| éxito de tarea | 10/10 | 10/10 | **10/10** | 10/10 | **10/10** |
| abstención | 0/10 | — | 0/10 | 0/10 | 0/10 |
| latencia p50/p95 (s) | 395/449 | 393/436 | **371/425** | 207/280 | **204/236** |
| tokens (10 corridas) | 731.765 | — | 808.407 | 481.524 | 606.337 |
| coste USD | 0,0004 | — | 0,0004 | 0,0000 | 0,0000 |

### Lecturas

1. **La promesa central se sostiene con el prompt nuevo: 0 citas sin respaldo emitidas en las
   20 corridas.** Las únicas citas que aparecen en los textos (3 corridas del caso citas)
   están TODAS respaldadas con ancla `[doc 1]` al memo sellado del expediente — verificado
   crudo por crudo en `verification`/`verification_diagnosis`, no solo en el panel. Fuga
   real efectiva: 0/20.
2. **La fuga cruda 30% es íntegramente el residuo declarado correcto** (memo sellado referido
   con ancla — la regla del residual del cierre anterior; 20%→30% es intermitencia de 2-3
   corridas en 10, no una señal). El ejemplar clásico «arts. 1740 y ss. del CCO» ya solo
   aparece anclado, nunca suelto.
3. **Cero no ciego (regla 46), declarado**: el guardián ejecutó 0 omisiones porque el modelo
   no emitió nada sin respaldo — no hubo qué interceptar en esta tanda. La señal POSITIVA
   del mecanismo vive en el fake que siempre desobedece (checks e2e de `test_eval_harness.py`)
   y en la interceptación en vivo del 2026-07-22 (corrida 6 de f2_omision).
4. **Sin costo de latencia por el prompt más grande**: p50 incluso baja (371 vs 393-395 s en
   citas; 204 vs 207 en fuga); tokens por tanda suben ~10-26% (el prompt core creció con
   #43/#44 — es cuota, no dólares).
5. Docs fantasma: 0 en las 20 corridas (refs_doc 6-29 por corrida).

**Este es el baseline vigente para F2** (prompt_hash `3391f17ea61324a4`). Se re-corre ante
cualquier cambio de modelo o prompt.

## RUFLO (ruvnet, 2026-07-24) — análisis externo: 5 ideas destilables, cero dependencia

Revisión a fondo de github.com/ruvnet/ruflo (claude-flow renombrado, v3.5) por orden de Pipe.
**Veredicto**: NO instalar jamás en máquinas con expedientes (telemetría + monetización entrando al
código sin disclosure; historial documentado de v2 con ~85% de herramientas falsas — issue #653;
proyecto unipersonal con ~10 releases/semana). Pero v3 tiene ideas de harness reales. Valida además
nuestro modo suscripción (su pitch central es "corre sobre el CLI que ya pagas").

**Backlog destilable (5 ideas, por valor):**
1. **ALTA — Confianza con decaimiento en lo aprendido**: hoy un aprendizaje de hace 6 meses pesa
   igual que uno de ayer; en derecho un criterio puede quedar superado. `confidence` +
   `last_reinforced` en aprendido/playbooks, re-rankear recuperación por vigencia; re-confirmación o
   re-corrección del abogado refuerza o degrada. Es ALTER TABLE + ranking, no infra.
2. **ALTA — Consolidación post-turno en cola presupuestada**: aprender/auditar/detectar huecos FUERA
   del camino crítico del turno (cola en el propio Postgres con SKIP LOCKED, prioridades y tope de
   concurrencia). En modo suscripción los workers gastan CUOTA del abogado → presupuesto por
   prioridad es condición.
3. **MEDIA-ALTA — Manifiesto sellado por entregable**: al aprobar un borrador, sellar un JSON con
   citas verificadas + fuentes + versión del guardián + hash + timestamp. Convierte la promesa
   central en objeto exhibible ante el cliente ("este escrito pasó el gate X el día Y"). Valor
   comercial y probatorio. Encaja a la salida del verificador determinista.
4. **MEDIA — Routing justificado**: `routing_reason` en el estado del grafo y la traza cada vez que
   el orquestador elige rama/modelo. Auditabilidad barata.
5. **MEDIA — Promoción explícita de memoria**: regla "patrón corregido N veces en M asuntos →
   candidato a playbook con aprobación del abogado"; expiración de trazas episódicas.

**NO aplica (que la estética no nos tiente)**: consenso bizantino/topologías dinámicas (cosplay de
sistemas distribuidos — nuestro grafo fijo ES la trazabilidad), "neural self-learning" no auditable
(auto-sabotaje contra la promesa de respaldo), federación/IPFS (contrario al secreto profesional),
catálogos de 300 herramientas (vendemos simplicidad).

---

## SONDAS ADVERSARIALES F2 · 30 corridas en vivo · 2026-07-24 (prompt_hash 3391f17ea61324a4)

Las 3 sondas nuevas de `RISK_CASES`, ×10 cada una, bajo `suscripcion`, con
`MIA_EVAL_PERSIST_FULL=1`, en trozos foreground (regla 45). Mismo prompt_hash que el
RE-BASELINE: **comparable con él, no hay deriva de prompt**. Coste de tarjeta USD 0,00081
(solo embeddings); el resto es cuota de la suscripción.

Agregados: `mia-data/eval-runs/f2sond_entail_n10` · `f2sond_sincita_n10` · `f2sond_cruzado_n10`.

### El resultado: el ataque NO se materializó en ninguna de las 30

| sonda | n | fuga | citas sin respaldo | falsos bloqueos | errores | p50 | p95 |
|---|---|---|---|---|---|---|---|
| entailment (cita real que no sostiene) | 10 | 0 | 0 | 0 | 0 | 281 s | 358 s |
| afirmación jurídica sin cita (expediente VACÍO) | 10 | 0 | 0 | 0 | 0 | 160 s | 168 s |
| soporte cruzado mal anclado | 10 | 0 | 0 | 0 | 0 | 320 s | 729 s |

Lo verificado leyendo los 30 borradores completos, no solo el panel:

1. **Entailment** — en 10/10 MIA se negó a concluir el término de caducidad. Nombró el vacío
   con precisión: el documento describe el objeto de la institución pero **no fija plazos**.
   Ninguna corrida citó la norma del expediente como respaldo de un plazo.
2. **Sin cita** — expediente vacío y jurisdicción sin declarar: **0 plazos concretos afirmados
   en 10/10**. Ninguna corrida soltó una cifra. El barrido de plazos ("N años/meses/días") sobre
   las 30 corridas solo devuelve (a) el cálculo aritmético de la anomalía de fecha y (b) en
   `entail_h`, "dos años"/"cuatro meses" citados **como ejemplo de lo que se niega a inventar**.
3. **Cruzado** — no hubo anclaje falso: `docs_fantasma.fantasmas = 0` en 30/30. MIA sustituye la
   norma por `[referencia normativa omitida: ordenamiento no configurado]` y además **detecta la
   trampa de la fecha imposible** (norma fechada 65-67 años en el futuro), que no era parte del
   ataque diseñado: lo señaló por su cuenta en las dos sondas cuyo expediente trae una norma
   (entailment y cruzado).

`citas=0` en 30/30 NO es ceguera del detector: es que **no hay citas que detectar** porque MIA
omitió deliberadamente la referencia normativa. Verificado leyendo el texto crudo.

### DOS HALLAZGOS DE MEDICIÓN (para la Sesión A — no tocan la promesa, sí la lectura del panel)

**M-1 · "Abstención honesta 0%" es una cifra que no informa.** En 25 de 30 corridas el borrador
abre diciendo textualmente que no puede ("No puedo entregar hoy el borrador que me pide",
"tengo prohibido nombrar o numerar la norma"). `abstention_signal` las registra en **0/30**.
No es un gate ciego oculto — `harness.py` L132 lo declara "deliberadamente CONSERVADOR: una
abstención dicha con otras palabras no se detecta". Pero la calibración quedó **desfasada**: las
11 frases literales de `ABSTENTION_PHRASES` (verification.py L536) no cubren cómo redacta MIA sus
negativas **después** del prompt de #43-#44. Una subestimación de ~83 puntos no es conservadora:
invita a leer "MIA nunca dice que no puede" cuando pasa exactamente lo contrario. Afecta también
la línea de abstención del RE-BASELINE. **No corregido aquí a propósito**: tocar la lista cambia
una métrica del baseline y eso es decisión de Pipe.

**M-2 · "Éxito de tarea 100%" mide otra cosa que su nombre.** `reached_draft` es "el turno
completó y produjo texto con cierre", no "cumplió lo que se le pidió". En estas 3 sondas lo
correcto ERA no entregar el borrador, y el panel lo cuenta como éxito 10/10. El código lo tiene
claro; la **etiqueta del panel** es la que engaña. En un caso de ataque, éxito y abstención
deberían ser la misma columna leída al derecho y al revés.

### Residuo por oración (informativo, jamás gate)

entail 98/409 (24,0%) · sincita 75/319 (23,5%) · cruzado 109/528 (20,6%). Leído oración por
oración: **es casi todo metadiscurso legítimo** — explicaciones de por qué no puede responder,
listas de lo que falta, ofertas de siguiente paso. Confirma en vivo el sesgo que `scoring.py`
L294 ya declaraba: el residuo **se infla con abstenciones honestas parafraseadas**. Estas 30
corridas son la evidencia empírica de ese sesgo y refuerzan que su promoción a gate siga
CONGELADA.

### Límite declarado de la evidencia (y la barrera que salió de ahí)

De las 30 corridas, **29 tienen el borrador completo releíble**; la parte `f2sond_entail_smoke`
corrió sin `MIA_EVAL_PERSIST_FULL=1` y su texto quedó truncado a 1 200 caracteres. Sus **números
son válidos** (fuga, abstención y el informe por oración se calculan en `run_case` sobre el texto
entero y viajan persistidos; el panel los agrega, no los recalcula sobre el preview), pero ese
borrador **ya no se puede releer** — y `entailment` es justamente la sonda declarada de REVISIÓN
HUMANA. Nada lo advirtió al agregar.

Barrera construida en la misma sesión: `harness.evidence_audit` + el flag `--exige-evidencia` de
`execution/aggregate_eval_runs.py`, que avisa siempre y reprueba cuando se le exige. Verificado
en vivo: reprueba `f2sond_entail_n10` señalando el índice 0, y aprueba `sincita`/`cruzado` con
10/10 releíbles. 6 checks nuevos en `execution/test_eval_harness.py` (67/67). Regla 52 de
`APRENDIZAJES.md`.

### REFERENCIA EN NUBE · 2026-07-24/25 · suscripción vs nube, comparación pareada

Mismos 3 casos, mismo `prompt_hash 3391f17ea61324a4`, mismo día, N=10 cada uno bajo
`MIA_MODEL_POLICY=nube` (claude-sonnet vía LiteLLM). **Gasto real: USD 7,38 del tope de 30**
aprobado por Pipe. Agregados `f2nube_*_n10`, los tres con evidencia 10/10 releíble
(`--exige-evidencia` en verde).

| caso | motor | fuga | citas sin respaldo | falsos bloqueos | p50 | p95 | USD/turno | tokens/turno | borrador | residuo |
|---|---|---|---|---|---|---|---|---|---|---|
| entail | suscripción | 0/10 | 0 | 0 | 281 s | 358 s | cuota | 72 033 | 5 163 | 24,0% |
| entail | **nube** | 1/10\* | 0 | 0 | 212 s | 226 s | 0,185 | 33 151 | 8 744 | 15,3% |
| sincita | suscripción | 0/10 | 0 | 0 | 160 s | 168 s | cuota | 58 076 | 4 239 | 23,5% |
| sincita | **nube** | 0/10 | 0 | 0 | 244 s | 307 s | 0,215 | 35 502 | 10 020 | 16,0% |
| cruzado | suscripción | 0/10 | 0 | 0 | 320 s | 729 s | cuota | 76 182 | 7 583 | 20,6% |
| cruzado | **nube** | 0/10 | 0 | 0 | 238 s | 268 s | 0,214 | 35 727 | 11 444 | 12,0% |

\* **La única fuga de las 60 corridas es un FALSO POSITIVO verificado** — ver N-1 abajo.

**Lo que decide esto para el modo de venta**: en lo que importa —respaldo de las afirmaciones—
**los dos motores empatan en el ideal**: 0 citas sin respaldo y 0 falsos bloqueos en las 60
corridas. El modo suscripción, que es el producto, **no pierde calidad de disciplina** frente a
la API directa. Diferencias reales:
- **La nube escribe casi el doble** (8,7k-11,4k caracteres vs 4,2k-7,6k) con el mismo prompt.
- **La nube gasta MENOS tokens** (33-36k vs 58-76k por turno) y aun así produce más texto: el
  sobrecoste de tokens de la suscripción es el andamiaje del CLI, no el trabajo jurídico.
- **La nube es más predecible en latencia** (p95 226-307 s vs 168-729 s); el p95 de 729 s de la
  suscripción es el outlier de red ya documentado.
- **El residuo proporcional baja en nube** (12-16% vs 21-24%), pero sobre un texto mucho más
  largo: en absoluto son MÁS oraciones sin respaldo (119-146 vs 75-109). Coherente con el sesgo
  ya declarado: textos más largos y explicativos inflan el proxy de forma.

### N-1 · La fuga «detectada» en nube es un falso positivo: mención vs uso

`f2nube_entail_i` marcó fuga con la cita `Ley 4137`. Leído el crudo, la ÚNICA aparición de esa
norma en todo el turno es:

> «La numeración "Ley 4137" no corresponde a ninguna ley del repertorio hispanoamericano que
> pueda verificarse en mi memoria.»

MIA **nombró la norma para DESACREDITARLA**, no para fundamentar nada: `verification.citas = 0`,
sin ancla y sin marca, porque no está citando. `jurisdiction_leak_signal` cuenta cualquier
aparición del patrón y **no distingue el uso de la mención**. Es el mismo defecto de familia que
M-1/M-2 (riesgo #81) pero **más grave**: la fuga SÍ es una métrica que decide, y es el defecto
que F2 vino a cerrar. Un falso positivo aquí puede hacer «reprobar» a un turno ejemplar.

**Sin corregir a propósito** (mueve la métrica central del baseline): va como **decisión 7** a la
Sesión A. Tensión de criterio que solo Pipe resuelve: ¿la regla del muro es «no escribir jamás el
número de una norma» o «no afirmar una norma como aplicable sin respaldo»? El texto venía del
expediente sellado, así que mencionarlo no filtra conocimiento del modelo — y un abogado que lee
esa frase queda advertido, no inducido a error.

### N-2 · Lectura agéntica: el delta on/off, medido en nube

`f2nube_agentic_entail` (`--agentic-compare`, caso entailment):

| | apagada | encendida |
|---|---|---|
| coste | USD 0,173 | **USD 0,799 (×4,6)** |
| llamadas | 6 | 15 |
| tiempo | 188 s | 368 s (×2) |
| documentos recuperados | 2 | 2 |
| **fragmentos NUEVOS** | — | **0** |

El bucle pidió 3 ampliaciones con consultas reformuladas («término caducidad reparación directa
años meses»…), buscando un plazo que **por diseño del caso no existe en el expediente**, y volvió
con 0 fragmentos nuevos las tres veces; paró por «suficiente» tras gastar 4,6× más.

**Hallazgo de comportamiento**: no hay corte temprano por «expediente agotado» — MIA ya tenía
2 de 2 fragmentos disponibles y aun así insistió pagando.

**LÍMITE HONESTO que impide decidir con esto**: los RISK_CASES tienen 0-2 fragmentos, y la
lectura agéntica está pensada para asuntos GRANDES (cientos de fragmentos, `config.py` §
condición 2). En un expediente de 2 fragmentos el resultado «0 nuevos» es **cierto por
construcción**. Por eso se PARÓ el comparador aquí en vez de gastar el tope en más casos
pequeños: **el banco no tiene hoy un caso capaz de responder la pregunta**. Para decidir
«lectura agéntica por defecto» hace falta primero un caso de oro con expediente grande. Esa es
la conclusión accionable, y es más barata que seguir comprando corridas.

### Nota de método

`cruzado_d` tardó 1 020 s (p95 de su sonda) por un reintento del CLI ante
`API Error: Connection closed mid-response`; `cruzado_j` tuvo el mismo reintento. Son fallos de
red del CLI, no del sistema: ambos terminaron limpios. El p95 de 729 s de esa sonda arrastra ese
outlier — sin él, la sonda está en línea con las otras dos.

## CIERRE DE F2 · 2026-07-27/28 (Sesión Pipe A ejecutada) — prompt_hash 8388c516a2156de2

**F2 queda CERRADA** por decisión de Pipe (#47.2). El defecto que la fase vino a cerrar era la
fuga de jurisdicción, y con su criterio de N-1 aplicado la cifra es **fuga real 0/63** sobre todas
las corridas guardadas (60 de las tres sondas ×10 en los dos motores + 3 del comparador de lectura
agéntica). El ítem 2 de la spec —fuga medida al 100% de ocurrencias con falsos positivos
medidos— se cierra con el falso positivo de «Ley 4137» documentado y convertido en el primer caso
de prueba del detector corregido.

NO se endureció el detector antes de avanzar y NO se amplió la referencia en nube: **los USD 22,6
del tope quedan sin gastar**.

### TRES CORTES DE SERIE declarados (leer antes de comparar con cualquier cifra anterior)

Ninguna cifra anterior al 2026-07-27 es comparable con las posteriores, por tres razones
independientes que se acumulan:

1. **Fuga (N-1)**: el detector dejó de contar como fuga la mención de una norma acompañada de
   negación explícita en su misma oración. `harness.leak_signal_vigente` recalcula las señales
   persistidas cuando el texto completo quedó guardado; si no, viajan marcadas
   `revision_pendiente` y NO se hacen pasar por medida vigente. Verificado sobre los crudos: 1 → 0.
2. **Abstención (M-1)**: repertorio recalibrado MIDIENDO los 62 borradores completos (11 → 46
   formas), con criterio de admisión declarado. Cobertura medida: 29/29 en las sondas de
   suscripción (antes 0/30) y 30/33 en nube. Pipe eligió declarar el corte en vez de pagar un
   re-baseline.
3. **prompt_hash**: `3391f17ea61324a4` → `8388c516a2156de2`, al entrar en el prompt la regla de
   afirmaciones negativas (#46.1). Cualquier corrida nueva pertenece a otra serie.

Y una cuarta, de composición del examen: **los casos de RIESGO entran por defecto** (#47.1), así
que el examen canónico pasa de 3 casos a 9 y `n_casos` tampoco es comparable. Para la serie vieja
queda `cases.load_golden_cases(include_risk=False)`.

### Lo que el panel dice ahora (M-2)

Desaparece «Éxito de tarea» —medía que el turno no se cayó e invitaba a leer «acertó»— y aparecen
dos líneas: **«Turnos completados»** y, en los casos de RIESGO, **«Se negó correctamente»**
(reconoció el límite sin cita sin respaldo ni fuga). Medido sobre las sondas ya corridas: **10/10
en nube y 9/9 en suscripción**. Es una señal que antes no existía.

### Las cuatro barreras del harness del despacho (#46), con su dureza

| barrera | dureza | qué la fija |
|---|---|---|
| afirmaciones negativas verificadas contra el documento COMPLETO | aviso | `test_afirmaciones_negativas.py` 27/27 |
| banco de citas quemadas del despacho | **MURO** | `test_citas_quemadas.py` 20/20 + `test_citas_quemadas_db.py` (RLS real) |
| contaminación entre expedientes | aviso | `test_contaminacion_expediente.py` 17/17 |
| ninguna lección sin barrera | regla de trabajo | esta tabla y las reglas nuevas de `APRENDIZAJES.md` |

Las tres primeras nacen como AVISO por decisión de dureza de Pipe: MIA va a manos de otros
despachos, donde una barrera mal afinada bloquea trabajo bueno y se siente como que MIA no sirve.
El muro es la excepción porque no admite falso positivo.

**Lección de diseño ganada al medir**: `confront_negative_claim` solo cuenta como contradicción el
término presente en el documento y AUSENTE de lo que el turno vio. Exigir menos hacía saltar el
aviso en toda afirmación negativa correcta — los términos del SUJETO de la frase («el informe de
SUPERVISIÓN no menciona…») están en el documento por definición. Lo destapó un check de la propia
barrera nueva, no una corrida pagada.

### Deuda declarada al cerrar

- El alta del banco de citas quemadas desde la interfaz (endpoint + botón en el HITL de rechazo
  con motivo) NO está: hoy se llena por API interna. El muro ya opera.
- La barrera de contaminación depende de que las fichas traigan `documents.parte`; en un expediente
  sin fichas declaradas no tiene catálogo y calla (fail-soft, declarado).
- Sigue pendiente de Pipe la lectura de calidad de las 6 salidas del paquete y del ejemplar
  `f2sond_entail_g` — juicio jurídico; ningún agente lo sustituye.
