# Mia · SOP — Feedback processor (aprende de las trazas, propone mejoras)
# Última actualización: 2026-06-14 (Módulo 3e)

## Qué hace
El Feedback processor cierra el bucle de aprendizaje: lee las trazas del trabajo de Mia (2d),
detecta dónde falló o el abogado tuvo que intervenir, y **propone** mejoras a los playbooks. NO
aplica nada — las propuestas quedan `pending` para que el abogado las revise (Pantalla 4,
Memoria, en Fase 3). Vive en `backend/mia/memory/feedback_processor.py` (clase
`FeedbackProcessor`). `run(tenant_id)` ejecuta: `load_traces → analyze → propose →
save_proposals → mark_traces_processed`, y devuelve `{traces_analyzed, proposals_created,
errors}`. `run_all_tenants()` lo corre para todos (job `feedback_daily`, 24h — diario 1am, sin
timezone en v1).

## Señales que detecta (decisión #19 · trazas v2)
Para que las señales fueran detectables hubo que ENRIQUECER la traza en el origen (las trazas
v1 solo guardaban input/output/model/tokens/latency). `finalize_node` (graph.py) ahora escribe
4 campos opcionales → schema `mia.trace.v2`:
- `hitl_outcome` ('approved' | 'rejected' | 'edited')
- `draft_original` / `draft_final` (borrador antes/después de la edición del abogado)
- `retrieved_doc_ids` (ids de los documentos recuperados; [] = no se citó nada)

`analyze` cuenta tres señales:
- **HITL_REJECTION** — `hitl_outcome == 'rejected'` (el abogado rechazó el borrador).
- **HITL_EDIT** — `hitl_outcome == 'edited'` Y el cambio de caracteres entre `draft_original` y
  `draft_final` supera el **20%** (`difflib.SequenceMatcher`; edición significativa, no un retoque).
- **NO_RESULT** — `retrieved_doc_ids` vacío o ausente (Mia respondió sin documentos → gap en los
  knowledge stores).

## Formato v1 vs. v2 (compatibilidad)
Los campos v2 son OPCIONALES (default None/[]). Una traza histórica v1 sigue siendo válida: el
processor trata la ausencia como None (una v1 cuenta como NO_RESULT, que es correcto: no hay
constancia de documentos). Los gates 2d (`test_trace_capture`) y 1d (`test_hitl_flow`) usan
`issubset` para los campos y cuentan 1 traza por turno → los campos extra no los rompen.

## Umbral de 2 ocurrencias y tipos de propuesta
`propose` solo genera una propuesta cuando un patrón se repite **≥ 2 veces** en el período (una
señal aislada es ruido). El tipo:
- **NO_RESULT** → `flag_gap` (vacío de conocimiento; no apunta a un playbook).
- **HITL_REJECTION / HITL_EDIT** → `improve_playbook` (si el despacho ya tiene playbooks
  activos; apunta al más usado) o `new_playbook` (si no tiene ninguno).
`call_llm(task="curator")` (claude-sonnet, decisión #18) redacta el `suggested_content`. La
propuesta lleva `{type, target_playbook_id|None, suggested_content, rationale, signal_count,
trace_ids}` y se guarda en `feedback_proposals` con `status='pending'`.

## Watermark vs. marcar el JSONL
Las trazas son JSONL **append-only**, sin id estable por línea, así que NO se mutan ni se marca
traza por traza. En su lugar, `processed_traces_watermark(tenant_id, trace_date,
last_processed_at, traces_processed)` registra hasta qué día se procesó. `load_traces` excluye
las trazas cuyo día ya está en el watermark → idempotencia: una segunda corrida sobre el mismo
día no reanaliza ni duplica propuestas.

## Cómo revisar las propuestas (Pantalla 4, futura)
Las propuestas viven en `feedback_proposals` (`status` pending → approved | rejected | applied;
`reviewed_at` / `reviewed_by`). La Pantalla 4 (Memoria) de Fase 3 las listará para que el
abogado apruebe/rechace; aprobar una `improve_playbook`/`new_playbook` debería conectarse con el
`PlaybookManager` (registrar/actualizar el playbook). Hoy el processor solo PROPONE.

## Forzar una corrida manual
```python
from mia.memory.feedback_processor import FeedbackProcessor
await mia.db.pool.open_pool()
await FeedbackProcessor().run("<tenant_uuid>")     # usa mia-data/traces/ por defecto
```

## Arranque en producción
El scheduler se arranca en el **lifespan de FastAPI** (`backend/mia/api/main.py`): tras abrir el
pool, `build_scheduler()` se lanza como tarea de fondo (`asyncio.create_task(scheduler.start())`)
y se detiene en el shutdown (`scheduler.stop()` + cancelación de la tarea). **Sin esto, los 3
jobs (`sync_obsidian_all_tenants` 6h, `curator_weekly` 168h, `feedback_daily` 24h) no se
disparan en producción** (cerró el Riesgo #22). La PRIMERA corrida de cada job se agenda a un
intervalo de distancia (no en el arranque): un job diario/semanal no debe ejecutarse en cada
reinicio. Para forzar una corrida inmediata (p. ej. en operación o debugging), usar
`run_job("feedback_daily")`. Nota: el scheduler v1 no tiene timezone; dispara por intervalo
desde el arranque, no a una hora exacta.

## Self-Annealing — si el gate falla, revisar en este orden
1. **¿Corrió la migración 006?** `init_feedback.py` debe reportar las 2 tablas con
   `mia_app INSERT=True RLS=True`.
2. **`load_traces` no carga nada:** revisar la ventana `since_hours` (default 24) y que el día
   no esté ya en el watermark. Los registros de evento (`mia.trace.event.v1`) se ignoran a
   propósito.
3. **HITL_EDIT no se detecta:** el umbral es 20% de cambio de caracteres (`1 - ratio`); ediciones
   menores no cuentan. Requiere `draft_original` y `draft_final` no vacíos.
4. **Propuestas duplicadas:** la idempotencia es por watermark — confirmar que `run` llama a
   `mark_traces_processed` al final y que `load_traces` excluye los días procesados.
5. **Tipo de propuesta inesperado:** NO_RESULT siempre es flag_gap; rejection/edit dependen de si
   el tenant tiene playbooks activos.
6. **Gate 1d/2d roto tras tocar la traza:** los campos v2 son opcionales; capturar sin ellos debe
   seguir dando `schema='mia.trace.v1'` y 1 sola línea por finalize.
7. **Enumeración de tenants:** `run_all_tenants` usa conexión admin (cross-tenant, Riesgo #15).
