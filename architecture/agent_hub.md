# architecture/agent_hub.md
# Agent Hub — conectores a CLIs de agentes externos (Módulo 1e)
# Última actualización: 2026-06-13

> Estado: 1e entregado. Gate `execution/test_agent_hub.py` **38/38** (subprocess
> mockeado + config por tenant contra la DB real + endpoints de settings).
> Decisión #12 (tenant_settings) · defaults D2 (subprocess), D3 (flags), D4 (delegación).

---

## 1 · Qué es

El Agent Hub deja que Mia delegue trabajo a **CLIs de agentes externos** corriendo
cada uno como **subproceso aislado**. Son **OPCIONALES por tenant** y por defecto
**todos deshabilitados**; un despacho los activa desde el Dashboard.

`backend/mia/gateway/`:
- `agent_hub.py` — `AgentHub` + registro de conectores (`CONNECTORS`).
- `hub_config.py` — config por tenant (enable/disable, persistida en DB).

### Los 5 conectores
| key (interno) | slug (público) | display (§G, español)              | bin_candidates       |
|---------------|----------------|------------------------------------|----------------------|
| `hermes`      | investigacion  | Asistente de investigación jurídica| `hermes`             |
| `claude_code` | documentos     | Editor de documentos               | `claude`, `claude-code` |
| `codex`       | automatizacion | Asistente de automatización        | `codex`              |
| `antigravity` | escritorio     | Asistente de escritorio            | `antigravity`        |
| `openclaw`    | navegacion     | Asistente de navegación web        | `openclaw`           |

§G: el abogado solo ve el `display` (español) y el `slug` (id neutro en las URLs);
NUNCA la marca del CLI.

---

## 2 · Invocación segura (PASO 1 · riesgo #1)

`AgentHub.invoke(key, prompt, tenant_id)` (y los 5 `invoke_<name>`):
1. **Detecta el binario**: variable de override (`MIA_<NAME>_BIN`, si el archivo
   existe) > `shutil.which`. Si no lo encuentra → `"[no disponible] …"`. NUNCA
   hardcodea rutas.
2. **Construye el comando con argumentos en LISTA** (`[binario, *build_args(prompt)]`)
   y corre `subprocess.run(..., shell=False)`. Así una ruta con espacio
   ("Mia-Super Agent") va **intacta como un elemento** — sin comillas manuales, que
   son frágiles (decisión D2, mitigación robusta del riesgo #1). El gate lo verifica.
3. `timeout=120s`, captura stdout/stderr.
4. **Graceful degradation**: ante binario ausente, `exit≠0`, timeout o excepción →
   loguea y DEVUELVE un string `"[error] …"` o `"[no disponible] …"`; **nunca**
   propaga una excepción al caller.

> NOTA [VERIFICAR] (decisión D3): los flags de cada CLI (`build_args`) están SIN
> confirmar contra el `--help` real; el gate mockea el subprocess. Confirmar antes
> de invocar en vivo. Mientras tanto, como los CLIs son opt-in por tenant y default
> OFF, no se invoca nada sin que el despacho lo active.

---

## 3 · Config por tenant (PASO 2 · decisión #12)

`hub_config.py` persiste el estado en la tabla **`tenant_settings`** (jsonb), bajo
`config->'agent_hub' = { "<key>": true/false }`. Una fila por tenant, **aislada por
RLS** (todas las ops pasan por `tenant_connection` → GUC `app.tenant_id`,
fail-closed). `set_enabled` hace read-modify-write dentro de una transacción.
Default: `{}` = todos deshabilitados.

> No se usó "la tabla profiles" (no existe; `ProfileManager` 2a es in-memory). Se
> creó `tenant_settings` nueva para evitar la colisión de nombres (decisión #12).

---

## 4 · Endpoints de settings (PASO 3)

`api/routes/settings.py`:
- **GET `/settings/agents`** → `{agentes: [{id(slug), nombre(es), instalado, habilitado}]}`.
  Combina `list_available()` (instalado) con la config del tenant (habilitado).
- **POST `/settings/agents/{slug}/enable`** / **`/disable`** → upsert por tenant.
- Desconocido → 404 ; sin token → 401. Solo español, sin marcas (§G).

---

## 5 · Delegación desde el grafo (PASO 4)

`agents/graph.py::MatterGraphBuilder._maybe_delegate(state)` — seam **OFF por
defecto**. Solo delega si:
1. `state.metadata['delegate'] = {'agent': <key>, 'prompt'?: str}` (señal explícita
   puesta por una capa superior), **y**
2. el tenant tiene ese agente **habilitado** (`hub_config.is_enabled`).

`intake_node` lo llama; si devuelve texto, lo guarda en `metadata['delegation']`. El
CLI corre en hilo aparte (`asyncio.to_thread`, subprocess síncrono). Transparente al
abogado; degrada con gracia (si no está instalado, devuelve el `"[no disponible]"`).
La "detección" de cuándo delegar se deja como costura explícita (no heurística
agresiva) para no sorprender.

---

## 6 · Cómo verificar

```
.venv\Scripts\python.exe execution\test_agent_hub.py   # 38/38 (subprocess mockeado + DB)
```

Gate mínimo (subconjunto): list_available() sin crashes ✓ · CLI no disponible →
error descriptivo, no excepción ✓ · rutas con espacio intactas ✓ · config por tenant
persiste en DB ✓.

---

## 7 · Costuras hacia adelante
- Confirmar `build_args` de cada CLI contra su `--help` real ([VERIFICAR]) antes de
  invocar en vivo.
- `tenant_settings` es reutilizable: futuros ajustes del despacho (notificaciones,
  preferencias de redacción, etc.) caben bajo otras keys del mismo `config` jsonb.
