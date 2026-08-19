# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

# CIERRE — 2026-08-18 · Mapa al día + mock del swarm alineado a la firma real · EMPEZAR AQUÍ

## Resultado de esta sesión

`CLAUDE.md` ya describía el producto del 18 ago 2026; este HANDOFF no. Quedó alineado.
No se inventó servidor MCP. `Plan/Plan.md` vive en el workspace padre (fuera de
`mia-agent`) y no entra en este PR.

HEAD de trabajo: rama `feat/fase1-inc1-cleanup-scaffolding`. El mapa de abajo es el
contrato vigente — no reabrir «5 pantallas» ni «LiteLLM primero».

## Mapa vigente (18 ago 2026)

- **Packs fail-closed.** Un pack vacío o un handoff roto no finge cotejo verde: cero
  fuentes ≠ preflight OK. El recorte de drafts conserva la matriz. Migración
  `059_packs_handoff_cost_status.sql` (handoffs, fact-pack por hash, `cost_status`
  honesto: medido / estimado / no_medida). Gate: `execution/test_packs_preflight.py`.
- **HITL por hash + tesis one-shot.** Approve/edit exigen `draft_hash` del borrador
  actual (409 si cambió; 422 si falta huella o attest). Cambiar la matriz en revisión
  autoriza UNA pasada extra de redacción+verificador (`selection_redraft_used`), no
  el bucle automático draft↔gate.
- **Packet destilado.** El cruce recibe hash / pasaje / locator `[doc n]`, no el dump
  de investigación. Vive en `metadata.source_packet`.
- **MCP vacío honesto.** Sin servidores en `tenant_settings.config['mcp']['servers']`
  el despacho ve un dict vacío. Catálogo curado; `resolve_server` es fail-closed.
  No hay servidor MCP de producto que inventar para un test rojo.
- **CI verde (sin bajar gates).** SHA de migraciones sin psycopg; checkpointer en el
  job legal; JWT_SECRET ≥ 32 caracteres; stubs de Tauri; `verify.ps1` usa el Python
  de PATH (`MIA_VERIFY_PYTHON`) y no usa `WindowStyle` en Ubuntu; el catálogo quick
  corre junto a Postgres en Ubuntu; el blindaje BatBadBut del CLI se afirma solo en
  Windows. Commits 56631c8 → 7ef8709 sobre el cierre del 15.
- **Cron suggestions.** El job `generate_suggestions` alimenta
  `GET /api/automations/suggestions` (consent-first; el abogado acepta o descarta).
- **Telegram en el lifespan.** `start_bridge_if_configured()` arranca con la API si
  hay token. No es un proceso suelto obligatorio para que el producto viva.
- **Agent Hub.** Cinco conectores (investigación, documentos, automatización,
  escritorio, navegación). Solo `invocation_ready` si el binario está en PATH y
  `--help` confirma los flags. Si no, razón honesta — nunca `[VERIFICAR]` en el
  catálogo.
- **Router LLM.** `agent/llm.py` con política por defecto `quality_adaptive`.
  LiteLLM es proxy opcional de respaldo, no el camino primero del abogado.
- **Frontend.** No son «5 pantallas». Hay asunto, revisión HITL, memoria,
  configuración (conexiones, ayudantes, protección), automatizaciones, misiones y
  sala de estrategia. Login JWT. ~14 routers `/api`.

## Gate de esta sesión

`execution/test_research_swarm.py`: los mocks de `resolve_jurisdictions_for` y
`citation_patterns_for` tenían un solo argumento; el grafo llama
`(tenant_id, matter_id)` desde la sesión 58 y el fail-soft de `_turn_jurisdictions`
tragaba el `TypeError` (misma clase que el arreglo de `test_projects.py` el 15 ago,
regla 78). Firmas alineadas a las reales, incluido el stub de `resolve_jurisdictions`
del check de dedup. Suite 21/21 PASS. No se inventó servidor MCP: el gate vacío
bloquea y el turno sigue.

## Pendientes que deja esta sesión

Siguen abiertos los del 15 ago (no se tocaron):

- **P3**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev).
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o
  tramo rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- **API propia por instalación** (decisión de Pipe). Benchmark solo por decisión de
  negocio. Distribución sin prometer ≤335 MB.

PRIMERA TAREA del próximo arranque con entorno completo: la misma del 15 — E2E con
DB, `test_first_run.py` con salida capturada, y revisar en vivo las pantallas nuevas
si el entorno lo permite. No reabrir el mapa de producto.

---

# CIERRE — 2026-08-15 · E2E con DB verde, first_run capturado y pantallas revisadas en vivo

## Resultado de esta sesión (commits 12bf5e9 + cierre, pusheados)

Los tres puntos de la «primera tarea» del cierre anterior quedaron cerrados con evidencia:

1. **`test_first_run.py` VERDE 73/73 con salida capturada** (exit 0). Ya cuenta como gate.
2. **E2E con DB, todo verde**: test_rls 19/19 · test_e2e 59/59 · test_hitl_flow 21/21
   (el riesgo #86 queda re-verificado: la suite pasa con DB) · test_citation_seals 20/20 ·
   test_projects 61/61 · `verify.ps1 -Mode quick` VERDE 16 suites (14,3 s).
3. **Pantallas nuevas revisadas en vivo** (Playwright + `seed_despacho_demo.py`):
   /activar con «Calidad jurídica adaptativa» RECOMENDADO y el copy del plan Max en
   «Mi suscripción»; selector de motor en Conexiones con «Codex en este equipo (no
   disponible en este equipo)» deshabilitado con su razón; chips «Contexto jurídico
   [General]» pintando lo efectivo; tarjeta «Recuperar desde una copia» con su copy y el
   aviso de aplicación al reinicio. En dev /activar redirige a /onboarding
   (`instalado=false`, correcto); para verla se interceptó `/api/welcome/status`.

Dos defectos REALES corregidos en 12bf5e9:

- **El lanzador canónico de la API estaba roto en Windows**: en `backend/mia/api/run.py`
  una local `config = uvicorn.Config(...)` sombreaba el módulo `config` y
  `python -m mia.api.run` (el camino de `start_api.ps1`) moría con `UnboundLocalError`.
  Ningún gate lo ejecutaba. Pendiente: gate que lo arranque de verdad (regla 79).
- **8 checks rojos de test_projects que parecían regresión**: los 5 mocks de
  `resolve_jurisdictions_for` tenían la firma vieja de 1 argumento (la sesión 58 la
  amplió a `(tenant_id, matter_id)`); el fail-soft de `_turn_jurisdictions` tragaba el
  `TypeError` y degradaba a la rama restrictiva. Mocks actualizados (regla 78).

**Entorno reconstruido**: el `.env` eliminado el 2026-08-14 era la única copia de las
contraseñas del clúster portable 55432. Se resetearon (`trust` temporal en `pg_hba.conf`
con backup, restaurado a scram) las contraseñas de `postgres`/`mia_app`/`mia_curator` y
se regeneró el `.env` con las claves del semilla de `first_run.py` (regla 80). Las 56
migraciones se re-aplicaron idempotentes (3 fallos esperados: constraints viejos
superados por migraciones posteriores; los vigentes quedaron intactos).

## Pendientes que deja esta sesión

- **P3 nuevo**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev). Ubicar y corregir.
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o tramo
  rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- El bloque grande sigue siendo el del cierre 2026-08-14: **API propia por instalación**
  (decisión de Pipe), benchmark solo por decisión de negocio, y distribución sin
  prometer ≤335 MB.

Retrospectivas: técnica en `docs/retrospectives/retrospective-2026-08-15-e2e-db-y-lanzador-api.md`;
de sesión en `Pipe-OS/01-operacion/retrospectivas/retrospective-2026-08-15-002-mia-e2e-db-first-run-pantallas.md`.
Reglas nuevas 78-81 en `APRENDIZAJES.md`.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---
