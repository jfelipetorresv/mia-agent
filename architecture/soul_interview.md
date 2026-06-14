# Mia · SOP — SOUL.md + entrevista de onboarding (Módulo 5)
# Última actualización: 2026-06-14 (cierre del proyecto)

## Qué es
El SOUL.md es la **identidad del agente** por despacho: la Capa 1 del prompt de 10
capas (1b) y el `soul_snapshot` que el grafo carga al iniciar cada turno. La
entrevista de onboarding lo construye conversacionalmente a partir de 19 preguntas.

NO confundir con las otras "memorias":
- `/memory/` raíz = memoria de construcción (Claude Code).
- `backend/mia/memory/` = memoria en ejecución 2a-2d (perfil, playbooks, trazas).
- **SOUL.md = persona/identidad** del agente (este módulo) — el que menciona
  CLAUDE.md §A como `$MIA_HOME/SOUL.md`.

## Dónde vive
`$MIA_HOME/soul_{tenant_id}.md` (+ `soul_{tenant_id}.responses.json` con las
respuestas crudas para "Revisar mi perfil"). `$MIA_HOME` = `config.MIA_HOME`
(default `mia-data/`, gitignored; el `.env` trae `MIA_HOME=.\mia-data`). Una ruta
relativa se ancla a `PROJECT_ROOT`. Es estado de INSTANCIA por despacho, como las API
keys: el producto se entrega sin SOUL.md y cada despacho lo crea en el onboarding.

## Las 19 preguntas (Doc 4)
5 bloques: `identity` (P1-4) · `jurisdiction` (P5-9) · `legal_voice` (P10-14) ·
`mission_rhythm` (P15-18) · `triad_mode` (P19, opcional). Cada pregunta:
`{id, block, field, question, example}`. Las respuestas llegan como `{field: texto}`.
NOTA: el spec hablaba de "18 preguntas"; el Doc 4 trae **19** (la 19ª, triad_mode, es
opcional). Se implementaron las 19 con conteo dinámico ("Pregunta X de 19").

## El template (9 secciones, exactas del Doc 4)
`## identity · ## jurisdiction · ## mission · ## legal_voice · ## hard_nos ·
## doctrinal_stance · ## memory · ## rhythm · ## triad_mode`. `SOUL_TEMPLATE` y
`SOUL_SECTIONS` en `soul_interview.py` son la fuente. El LLM
(`call_llm(task="soul")` = claude-sonnet) rellena el template con las respuestas;
**los campos sin respuesta se conservan como placeholder** entre corchetes (no se
inventan datos — regla de citación, §G).

## API (en `api/routes/ux.py`, prefijo /api)
- `GET  /api/onboarding/questions` → las 19 preguntas.
- `POST /api/onboarding/complete`  → `{responses}` → genera y guarda el SOUL.md →
  `{soul_content, path}`.
- `GET  /api/onboarding/status`    → `{completed, last_updated, responses}`
  (derivado de la existencia/mtime del archivo — **sin tabla en DB**).

## Wiring al prompt (las DOS rutas)
1. **Grafo (turno real del producto):** `agents/state.py::initial_state` carga
   `soul_snapshot` con `load_soul_snapshot(tenant_id)` si el archivo existe;
   `agents/graph.py::_system_with_soul` antepone la identidad al system de
   `analysis_node`, `draft_node` y el EDIT de `finalize_node`. Sin SOUL.md →
   `soul_snapshot=None` → system base sin cambios (gate 1d intacto). **Resuelve el
   problema que tenía el Riesgo #11**: la costura `soul_snapshot` existía pero nadie
   la llenaba.
2. **MiaAgent.run_turn (path de prueba/futuro):** `agent/core.py::__post_init__`
   carga el SOUL.md en `self.identity` (Capa 1 del prompt_builder) si existe y el
   caller no pasó identidad propia. Sin archivo → `DEFAULT_IDENTITY` (placeholder).

`prompt_builder.py` NO se tocó: la Capa 1 ya leía `agent.identity`; ahora esa
identidad se nutre del SOUL.md.

## Revisión trimestral
`SoulInterview.update_soul(tenant_id, updates)` aplica cambios puntuales sobre el
SOUL.md existente vía LLM, conservando el resto, y mezcla las respuestas guardadas.
El header del template registra "Próxima revisión: generación + 3 meses".

## Gate
`execution/test_e2e.py` (25/25) — recorrido completo del abogado: onboarding (19
preguntas, SOUL con las 9 secciones, wiring al turno), asunto, documento, chat+SSE,
HITL, memoria, dashboard. Es el GATE FINAL del proyecto.

## Self-Annealing
1. **El SOUL.md no trae las 9 secciones** → el LLM ignoró el template; endurecer
   `_GEN_SYSTEM` o subir el peso del modelo (ya es sonnet). El gate mockea el LLM, así
   que esto solo aparece en vivo.
2. **El borrador no usa la voz del despacho** → no hay `$MIA_HOME/soul_{tenant}.md`
   (onboarding incompleto) → `soul_snapshot=None`. Verifica `config.MIA_HOME` y que el
   archivo exista para ese tenant.
3. **Import circular al cargar el grafo** → `state.py`/`core.py` importan los helpers
   de `onboarding.soul_interview` de forma DIFERIDA (dentro de la función) justo para
   evitarlo; no los muevas al top del módulo.
4. **triad_mode no "hace" nada** → hoy es solo una preferencia almacenada en el
   SOUL.md; no existe un modo de ejecución de tres modelos en el grafo (trabajo
   futuro — ver bugs-and-risks #27).
