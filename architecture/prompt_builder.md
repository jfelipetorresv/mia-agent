# architecture/prompt_builder.md
# Núcleo del agente (MiaAgent) + router call_llm · 10 capas · AuxiliaryClient
# Última actualización: 2026-06-12 · Módulo 1b

> Estado: 1a (núcleo + router) y 1b (10 capas + AuxiliaryClient) entregados.
> Gates offline: `test_agent_core.py` 15/15 · `test_prompt_builder.py` 32/32.

---

## 1 · Qué se construyó en 1a (núcleo mínimo)

- `backend/mia/agent/llm.py` — router `call_llm(task=...)` por el gateway LiteLLM.
- `backend/mia/agent/core.py` — clase `MiaAgent` (identidad + un turno de conversación).
- `backend/mia/agent/__init__.py` — exporta `MiaAgent`, `call_llm`, `resolve_model`.
- `backend/mia/config.py` — `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `MIA_MODEL`.
- `execution/test_agent_core.py` — **15/15 PASS** (offline, sin red).

El núcleo es deliberadamente pequeño (CLAUDE.md §"Simplicity First"): fija las
costuras sin adelantar trabajo de 1b–1e.

---

## 2 · Decisión de diseño — router delgado sobre LiteLLM

Hermes resuelve proveedor + auth + formato para ~20 proveedores a mano: su
`agent/auxiliary_client.py` tiene ~5.800 líneas. **En Mia ese trabajo lo hace
LiteLLM** (decisión #3): el proxy expone UN endpoint OpenAI-compatible y los
modelos se nombran por *alias*. Por eso `call_llm` de Mia es delgado:

- Solo mapea `task -> alias` y delega el resto al gateway.
- El agente habla wire OpenAI contra `localhost:4000`; queda provider-agnostic.
- Caching de prefijo, coste y observabilidad se centralizan en el proxy.

**Alias como fuente única.** Los nombres (`claude-haiku`, `claude-sonnet`) viven
en `litellm_config.yaml`. El router NUNCA usa ids largos del proveedor; el
gateway resuelve `claude-haiku -> anthropic/claude-haiku-4-5-20251001`. Cambiar
de modelo subyacente = editar el yaml, no el código del agente.

### 2.1 · INVARIANTE crítica — compression BLOQUEADA a la cadena barata/local

CLAUDE.md §D · decisión #7. Implementado como **bloqueo** (`_LOCKED_TASKS`), no como
default. `compression` está en `_LOCKED_TASKS`: un `model=` explícito se IGNORA (con
warning) y NO puede cambiar su cadena desde ningún call-site. Lo que NO está fijo es el
modelo concreto — lo decide la política de modelo del despacho (`_POLICY_CHAINS`, CP2):

```
_LOCKED_TASKS = frozenset({"compression"})     # el override de model no la toca
# cadena de compression por política:
#   suscripcion → ["cli-claude-haiku", "claude-haiku"]
#   nube        → ["claude-haiku"]
#   soberano    → ["mia-local"]           (Ollama, cero salida de datos)
#   openrouter  → ["openrouter-haiku", "mia-local"]
```

`resolve_fallback_chain("compression", model="claude-sonnet")` ignora el override y
devuelve la cadena BLOQUEADA de la política activa. El test cubre el override de sonnet
y de opus. La regla no se puede romper por accidente desde un call-site; el modelo
concreto SÍ depende de la política del despacho. No cambiar el bloqueo sin documentar en
`memory/decisions.md`.

### 2.2 · Router por política + cadenas de fallback (`_TASK_FALLBACK_CHAINS` + `_POLICY_CHAINS`)

El router ya **no** es `task -> alias único`. Son dos capas (en `agent/llm.py`):

- **`_TASK_FALLBACK_CHAINS`** — mapa BASE `task -> [alias, …]`: cada task trae una CADENA
  de fallback, no un solo alias. Se conserva por compat con los gates que lo leen/mutan.
- **`_POLICY_CHAINS`** (CP2 · decisión #27) — por cada **política de tenant**
  (`suscripcion` | `nube` | `soberano` | `openrouter`), la cadena que de verdad se usa.
  `_active_chains()` superpone la política activa sobre el mapa base y
  `resolve_fallback_chain(task, model)` la resuelve.

`call_llm` recorre la cadena en orden: si un alias se agota con un error "saltable"
(`should_fallback`), pasa al siguiente. Aliases: `cli-claude*` (CLI de la suscripción de
Claude Code del abogado), `claude-sonnet`/`claude-haiku` (API Anthropic vía proxy),
`openrouter-*` (cuenta de OpenRouter del despacho), `mia-local` (Ollama). Cadenas por
política (default `suscripcion`):

| task                          | suscripcion                            | nube                      | soberano  | openrouter                    |
|-------------------------------|----------------------------------------|---------------------------|-----------|-------------------------------|
| `main` / `curator` / None     | cli-claude → claude-sonnet → mia-local | claude-sonnet → mia-local | mia-local | openrouter-sonnet → mia-local |
| `compression` (**bloqueada**) | cli-claude-haiku → claude-haiku        | claude-haiku              | mia-local | openrouter-haiku → mia-local  |
| auxiliares (`verification`, `vision`, `title_generation`, `session_search`, `web_extract`, `soul`, …) | cli-claude-haiku → mia-local | claude-haiku → mia-local | mia-local | openrouter-haiku → mia-local |

Notas: en `soberano` TODO resuelve a `mia-local` (cero salida de datos). OpenRouter
también puede entrar como **respaldo/overflow opcional** de `main`/`curator` en las
políticas `nube`/`suscripcion`, pero SOLO con opt-in explícito del despacho **y** clave
presente (`_with_openrouter_fallback`). Solo se referencian alias que **existen** en
`litellm_config.yaml`; un alias inexistente sería un 404 latente.

---

## 3 · Capas de prompt (stable / context / volatile)

Patrón adoptado de Hermes (`agent/system_prompt.py::build_system_prompt_parts`):
el system prompt se arma en 3 tiers ordenados *cache-friendly* y se construye una
vez por sesión (se rearma solo tras compresión) para mantener caliente el prefix
cache aguas arriba.

- **stable** (prefix cacheado, capas ~1–6): identidad (luego SOUL.md), guías de
  herramientas, índice de skills, hints de entorno/plataforma.
- **context** (estable por sesión): `system_message` del caller, archivos de
  contexto.
- **volatile** (por turno, nunca cacheado): memoria, perfil de usuario, línea de
  timestamp (date-only para no invalidar el cache cada minuto).

**En 1b** las 10 capas viven en una sola tabla ordenada (`prompt_builder.LAYERS`):
fuente única del orden, del tier y de la marca de cacheo. El prompt ensamblado,
la vista por tiers (`build_system_prompt_parts`) y la inspección capa-a-capa
(`build_layers`) se derivan de ahí. La identidad por defecto (`DEFAULT_IDENTITY`)
será sustituible por `SOUL.md` en el Módulo 5.

### 3.1 · Las 10 capas

| #  | capa                   | tier     | cached | estado                |
|----|------------------------|----------|--------|-----------------------|
| 1  | `identity`             | stable   | ✅     | activa (→ SOUL.md M5) |
| 2  | `methodology`          | stable   | ✅     | activa                |
| 3  | `citation`             | stable   | ✅     | activa                |
| 4  | `tools`                | stable   | ✅     | costura (1c/1d)       |
| 5  | `user_comms`           | stable   | ✅     | activa (§G)           |
| 6  | `skills`               | stable   | ✅     | costura (skills)      |
| 7  | `matter`               | context  | —      | costura (asunto)      |
| 8  | `session_instructions` | context  | —      | activa (system_message) |
| 9  | `memory`               | volatile | —      | costura (2a/2b)       |
| 10 | `metadata`             | volatile | —      | activa (date-only)    |

`cached` ⇔ `tier == "stable"` ⇔ capas **1–6** = el prefijo byte-estable que se
**marca** para el prefix caching de Anthropic (`cache_control` en el último bloque
estable; `agent/llm.py::cache_split` parte el system SOLO para los aliases de la API
directa de Anthropic; `STABLE_CACHE_TTL_SECONDS = 3600` documenta la intención de TTL 1h).
El builder no promete ningún ahorro fijo: si el prefijo no alcanza el mínimo cacheable o
el alias no es de Anthropic, no se cachea y no se rompe nada (degradación limpia). El
ahorro REAL se MIDE en el panel (`metrics/usage`, cache hit-rate), no se afirma un
porcentaje. Las **costuras** (4, 6, 7, 9) renderizan `""` hasta que el módulo correspondiente
llena el estado del agente; el `_join` descarta las vacías, así que no ensucian el
prompt ni rompen el orden.

### 3.2 · AuxiliaryClient (`agent/auxiliary_client.py`)

Fachada delgada sobre `call_llm` para tareas auxiliares; `complete()` devuelve
**texto** (no el objeto OpenAI crudo) y acepta un string o una lista de mensajes.
Hereda el bloqueo de compression por construcción: `complete(task="compression",
model="claude-sonnet")` IGNORA el override y resuelve a la cadena bloqueada de la
política activa (p. ej. `cli-claude-haiku` en 'suscripcion', `mia-local` en 'soberano'),
NUNCA a claude-sonnet — el bloqueo vive en `resolve_fallback_chain`, que `call_llm`
invoca. `AuxiliaryClient.model_for(task, model)` expone el modelo resuelto sin llamar al
LLM (inspección/tests).

---

## 4 · Multi-tenant en el núcleo

`MiaAgent` se ata a un `tenant_id` desde su construcción (aislamiento RLS, §G).
El núcleo 1a aún no toca la DB, pero lleva el tenant en la firma para que 1b+ no
la reescriban.

---

## 5 · Costuras hacia adelante

- **1b** ✅ — prompt_builder de 10 capas (3 tiers) + AuxiliaryClient completo
  (router con vision, web_extract, session_search, title_generation). El mapa
  `task -> alias único` de 1b ya se **reemplazó** por cadenas de fallback
  (`_TASK_FALLBACK_CHAINS`, H.5) superpuestas por la política del tenant
  (`_POLICY_CHAINS`, CP2 · §2.2). Streaming en `call_llm` sigue pendiente opcional.
- **1c** — plugins (6 hooks) alrededor del turno.
- **1d** — LangGraph StateGraph + SSE + HITL (`interrupt()`); el turno único de
  `run_turn` se convierte en nodo del grafo.
- **1e** — Agent Hub.

---

## 6 · Divergencia conocida a reconciliar

`embeddings.py` (Módulo 0) usa LiteLLM como **librería** (`litellm.embedding`),
mientras que el agente usa el **proxy** (wire OpenAI a localhost:4000). Ambos
caminos son válidos en LiteLLM; conviene unificar el criterio al construir 1b
(probablemente todo por el proxy, para centralizar caching/observabilidad).
No bloquea 1a.

---

## 7 · Cómo verificar

```
.venv\Scripts\python.exe execution\test_agent_core.py       # 15/15 PASS (offline)
.venv\Scripts\python.exe execution\test_prompt_builder.py   # 32/32 PASS (offline)
.venv\Scripts\python.exe execution\test_plugins.py          # 16/16 PASS (offline)
```

Smoke real contra el proxy (requiere los 3 terminales de Modo B levantados):
construir un `MiaAgent(tenant_id=...)` y llamar `run_turn("hola")` con el proxy
LiteLLM en `localhost:4000`.

---

## 8 · Plugins (`agent/plugins.py`, 1c)

Sistema de plugins con **exactamente 6 hooks** de ciclo de vida (patrón Hermes
`hermes_cli/plugins.py`, recortado a 6). `HOOKS` es el contrato, en orden:

```
on_session_start · pre_llm_call · pre_tool_call · post_tool_call · post_llm_call · on_session_end
```

- **`PluginManager`** — `register(plugin)` (orden de registro) + `dispatch(hook,
  ctx)`. Un hook desconocido lanza `ValueError` (fail-fast, a diferencia de Hermes
  que solo avisa). `dispatch` recorre los plugins en orden y pasa un `ctx` (dict
  mutable); un plugin **intercepta** mutando el ctx in-place o devolviendo uno nuevo.
- **`Plugin`** — base con los 6 métodos no-op; heredar es opcional (duck-typing:
  basta exponer métodos con el nombre del hook, así un plugin cubre un subconjunto).
- **Bloqueo de herramientas** — `pre_tool_call` marca `ctx["blocked"] = True`; lo
  honra el executor de tools (1d).
- **Wiring en `MiaAgent`** — `pre_llm_call`/`post_llm_call` se disparan en
  `run_turn` (con `ctx["messages"]`/`ctx["content"]`; sin plugins es no-op y el
  turno no cambia). `on_session_start`/`on_session_end` en `start_session`/
  `end_session`. `pre_tool_call`/`post_tool_call` se cablearán en el executor de
  herramientas (1d). Gate: `execution/test_plugins.py` (16/16).
