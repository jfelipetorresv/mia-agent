# Plan — Banco de oro (gold-set de calidad por-despacho)

> Objetivo (aprobado por Pipe, 2026-07-12): un examen fijo de casos jurídicos reales con
> "respuesta de oro" validada a mano, que actúa como candado — ninguna mejora de MIA se da por
> buena si no iguala o mejora esa nota (detecta regresiones silenciosas de calidad).
> Construir MUY SIMPLE y AMIGABLE para el abogado. Se construye ENCIMA del motor ya existente
> (`backend/mia/eval/`, mergeado a main, commit 8fe8654), no se reinventa.

## Decisiones de Pipe (ya tomadas)
1. **Origen:** casos de ASUNTOS REALES resueltos, **ANONIMIZADOS al guardar**.
2. **Calificación HÍBRIDA:** (a) LISTA DE CLAVES que el abogado confirma (citas + conclusiones) =
   candado DURO, determinista, transparente, idéntico cada corrida; MÁS (b) JUEZ LLM ACOTADO
   (modelo grande, temp 0) = señal secundaria/advisory que explica el matiz en llano. El
   determinista MANDA pasa/no-pasa; el juez nunca bloquea solo.
3. **Motor del juez:** el MISMO que ya usa MIA (si la firma está en nube, el juez es nube, pero
   SOLO ve texto ANONIMIZADO, nunca datos reales).

## Experiencia del abogado (UX objetivo)
1. Trabaja un asunto normal, MIA da resultado, lo aprueba.
2. Si quedó ejemplar → botón "Guardar como caso de oro". MIA anonimiza y PROPONE las claves; el
   abogado REVISA la versión anonimizada (con spans PII resaltados) + edita/confirma las claves.
   Nada se guarda hasta su confirmación.
3. Cuando quiera / antes de cada cambio → "Correr examen de calidad": MIA responde sola todos los
   casos y muestra un tablero llano (✅/❌ por caso + explicación + semáforo "igual o mejor / bajó").
4. Ninguna mejora se aprueba si el examen baja.

## Motor existente (NO reinventar — construir encima)
`backend/mia/eval/`: `cases.py` (GoldenCase frozen dataclass + 3 casos sintéticos),
`scoring.py::score_turn` (PURO, determinista, SIN LLM-juez, mide disciplina: citas sin respaldo
del verificador CP9, cierre, borrador vacío), `compare.py::compare_reports` (antes/después,
fail-safe: una regresión manda), `harness.py` (runner por el grafo real hasta HITL, siembra con
embeddings, persiste JSONL en mia-data/eval-runs/, candado `read_eval_policy`/`EvalConsentError`),
`execution/run_eval.py` (CLI), gate `execution/test_eval_harness.py` (25/25).

## Diseño buildable (Fase 1 — backend)

### A. Modelo de datos — tabla `gold_cases` con RLS FORCE (migración 032)
Patrón idéntico a la migración 015 (`ENABLE`+`FORCE ROW LEVEL SECURITY`, policy `app_current_tenant()`,
`GRANT ... TO mia_app`). Los JSONL de eval-runs siguen para CORRIDAS (sintéticas, sin PII); los CASOS
guardados por-despacho van a DB.
```
gold_cases(
  id uuid pk default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  source_matter_id uuid references matters(id) on delete set null,   -- procedencia (auditoría)
  title varchar(200) not null,
  message text not null,                 -- pregunta ANONIMIZADA
  documents jsonb not null default '[]',  -- [{filename, chunks:[...]}] ANONIMIZADOS
  gold_answer text not null default '',   -- borrador aprobado ANONIMIZADO
  rubric jsonb not null default '{}',     -- {citas_clave:[...], conclusiones_clave:[...]}
  anon_map_ref text,                      -- HASH del mapa PERSONA_1→real (NUNCA el mapa en claro)
  status varchar(16) not null default 'draft' check (status in ('draft','confirmed','archived')),
  synthetic boolean not null default false,
  created_by uuid references users(id) on delete set null,
  created_at/updated_at timestamptz default now()
)
```
Índice `(tenant_id, status, updated_at desc)`. `GoldenCase` gana `rubric` opcional + loader
`load_tenant_gold_cases(tenant_id)` que hidrata desde la tabla y produce los mismos `GoldenCase`
que el harness ya consume (sin tocar el harness). El `anon_map` en claro NUNCA se persiste: vive
en sesión hasta confirmar, luego se descarta (solo su hash queda, para auditar reversibilidad).

### B. Anonimización — `backend/mia/security/anonymize.py` (NUEVO, lo crítico)
`security/redact.py` sirve de PATRÓN de estilo (regex idempotente siempre-activo), no cubre PII de
personas. NO hay spaCy en deps. SÍ hay modelo local `mia-local` = `ollama/qwen2.5:7b-instruct`
(requiere Ollama instalado — NO garantizado en toda máquina).
- **Pasada 1 — regex determinista** (estructurados, alta precisión): cédula, NIT, radicado 23 díg.
  CSJ, email, teléfono (+57/celulares), cuentas, URLs. Reemplazo por marcador CONSISTENTE y tipado
  (`CEDULA_1`, `NIT_1`, `RADICADO_1`, `EMAIL_1`…) vía diccionario de sesión (misma entidad → mismo
  marcador) para preservar sentido jurídico.
- **Pasada 2 — NER LOCAL para nombres/entidades** (personas, empresas, direcciones): `call_llm`
  con modelo LOCAL (mia-local), temp 0, prompt de extracción de entidades → spans → marcadores
  `PERSONA_1`, `EMPRESA_1`, `DIRECCION_1`. DEBE correr LOCAL (nunca nube: opera sobre texto aún
  identificable). Si NO hay modelo local disponible → degradar: solo estructurados + la revisión
  humana carga el peso de los nombres (avisar en llano). Fechas: se CONSERVAN por defecto
  (relevantes para caducidad/prescripción); generalizar solo si el abogado lo marca.
- **Verificación (dos redes):** (1) segundo pase automático re-escanea el texto ya anonimizado con
  TODOS los patrones; si algo quedó, bloquear y marcar el span. (2) **REVISIÓN HUMANA OBLIGATORIA**
  — el abogado ve el texto anonimizado con spans resaltados y puede editar; `status='confirmed'`
  solo lo pone él. Es parte del contrato, no un extra.
- **Riesgo residual (honesto):** ninguna anonimización automática es perfecta (apodos, hechos
  únicos que reidentifican por contexto, OCR sucio) → la revisión humana es la única red real.

### C. Endpoints REST
- `POST /matters/{id}/gold-cases:draft` → toma asunto resuelto (message+docs+borrador aprobado),
  anonimiza + propone rúbrica (citas clave con `verification.scan_citations` sobre el borrador
  aprobado; conclusiones del bloque de cierre del diagnóstico). Responde
  `{gold_case_id(draft), message_anon, documents_anon, gold_answer_anon, rubric_propuesta, spans_pii_restantes[]}`.
  NO persiste PII: guarda ya-anonimizado con `status='draft'`.
- `PATCH /gold-cases/{id}` → el abogado edita texto anonimizado + rúbrica. Valida con segundo pase
  de PII: rechaza si halla PII.
- `POST /gold-cases/{id}:confirm` → `status='confirmed'`, descarta el anon_map en claro.
- `GET /gold-cases` / `DELETE /gold-cases/{id}`.
Reusa el candado de consentimiento existente (`allow_eval_real_data`/`EvalConsentError`) — pero el
caso confirmado YA es anónimo → corre sin fricción como los sintéticos.

### D. Scoring híbrido — extender `scoring.py`
`substantive_score(draft, diagnosis, rubric, *, judge=None)` (mantener `score_turn` intacto y puro;
el híbrido lo ENVUELVE):
- **(a) Determinista — AUTORITATIVO.** Por cada `cita_clave`: coincidencia ROBUSTA (normalizar
  minúsculas, "art."↔"artículo", quitar puntuación) contra `scan_citations(draft)`. Por cada
  `conclusion_clave`: match por conjunto de términos/lemas con umbral (≥~70% keywords), no exacto.
  Salida: `cobertura_citas`, `cobertura_conclusiones`, `faltantes[]`, flags nuevos
  `FLAG_MISSING_KEY_CITATION` / `FLAG_MISSING_KEY_CONCLUSION` (entran en `flags`; `ok = len(flags)==0`).
- **(b) Juez LLM — ADVISORY.** `call_llm(task="judge", temperature=0, model=<grande via policy MIA>)`
  recibe SOLO: message anonimizado + rúbrica + respuesta nueva (nunca PII, nunca originales).
  Devuelve `{"veredicto":"solido|debilitado","explicacion_llana":str}`. NUNCA bloquea solo.
- **Combinación:** determinista manda pasa/no-pasa; juez adjunta señal. `build_report` suma
  `n_faltantes_clave` y expone `judge_flags[]` como columna informativa.

### E. Integración + gate
- `harness.run_case`: tras `score_turn`, si el caso trae `rubric`, llamar `substantive_score` y
  anexar bajo `result["substantive"]`. El juez corre FUERA de la ruta pura (efecto de red) —
  callback opcional, default `None`, para que `score_turn` siga puro y testeable.
- `compare.py`: criterio de regresión dura NUEVO = "un caso confirmado perdió cobertura de una
  cita/conclusión clave que antes tenía" (encaja en el fail-safe existente).
- **Gate nuevo `execution/test_gold_cases.py`:** (1) anonimización — corpus con PII conocida → 0
  fugas tras 2 pasadas + idempotencia; (2) `substantive_score` determinista con rúbrica fija (juez
  MOCKEADO, sin LLM/Ollama/DB); (3) RLS de `gold_cases` (patrón `test_rls.py`, requiere DB);
  (4) candado de consentimiento. Correr como candado antes de un cambio: `run_eval` before/after →
  `compare_reports`, cero regresiones.

## Fases
- **Fase 0 — Diseño:** ✅ COMPLETA (este documento).
- **Fase 1 — Backend:** migración 032 + `security/anonymize.py` + `eval/cases.py` (loader+rúbrica) +
  `eval/scoring.py` (substantive_score) + `eval/harness.py` (hook) + `eval/compare.py` (criterio) +
  endpoints + gate `test_gold_cases.py`. Verificación 3 capas (incl. revisión adversarial de la
  anonimización — que NO fugue PII).
- **Fase 2 — Frontend:** botón "Guardar como caso de oro" (desde asunto resuelto, con la revisión
  del texto anonimizado + edición de claves) + pantalla "Banco de oro" con el tablero llano.
- **Fase 3 — Candado + historial:** correr el examen automáticamente antes de cada cambio +
  historial de notas / tendencia.

## Archivos a tocar (Fase 1)
`backend/mia/db/migrations/032_gold_cases.sql` (nuevo) · `backend/mia/security/anonymize.py` (nuevo) ·
`backend/mia/eval/cases.py` · `backend/mia/eval/scoring.py` · `backend/mia/eval/harness.py` ·
`backend/mia/eval/compare.py` · endpoints en `backend/mia/api/routes/` · `execution/test_gold_cases.py` (nuevo).
Confirmar el número de migración real (última vista = 031 → sigue 032) antes de crear.
