# Análisis de claudeclaw-os — qué nos sirve para MIA

**Fecha:** 2026-07-17 · **Fuente:** `D:/Claude Code Business/claudeclaw-os` (v1.5.0)
**Método:** exploración por subsistemas con 4 subagentes + Codex (mirada de RFCs, pendiente en cola al cerrar).

---

## 0 · Qué es claudeclaw-os y su relación con MIA

claudeclaw-os es un "OS" para orquestar **agentes autónomos de Claude** (TypeScript/Node, SQLite,
canal principal por Telegram, dashboard web, despliegue en VPS). Comparte **linaje** con MIA: el
propio `personas.py` de MIA cita "ClaudeOS Pantheon" como referencia adaptada. Es decir, MIA ya
bebió de esta familia y en varios ejes **la superó**.

**Veredicto de conjunto (honesto):** en casi todo lo *estructural*, MIA ya es más maduro —
multi-tenant con RLS, migrador con ledger+checksums+advisory-lock, política de modelo con candado de
confidencialidad, panel de "valor neto", Sala de estrategia con moderador y citación, y seguridad de
delegación (subprocesos aislados + scrub de credenciales). Lo aprovechable de claudeclaw es
**operacional y puntual**, no arquitectónico. Abajo, lo que sí vale la pena, priorizado.

---

## 1 · Recomendación priorizada

| # | Mejora | Valor | Esfuerzo | Estado en MIA |
|---|--------|-------|----------|----------------|
| 1 | **Medir cache hit-rate** en `turn_usage` | ALTO | S | Falta: MIA *afirma* "75% de ahorro por caching" pero no lo mide |
| 2 | **Preservar secretos en upgrade** del instalador | ALTO | S | Verificar: no regenerar `DB_ENCRYPTION_KEY`/.env al reinstalar |
| 3 | **Root de config canónico** (todo deriva de `paths.py`) | ALTO | S | Auditar: que nada hardcodee `%APPDATA%` en paralelo |
| 4 | **Smoke-test post-first-run** (instaló = instaló y arranca) | ALTO | M | Falta: health-check real al final del first-run |
| 5 | **Atajos de despacho** (comando → prompt canónico) | ALTO | M | Falta: capa comando→playbook/persona reproducible |
| 6 | **Health-check de playbooks/skills** | MEDIO-ALTO | S | Falta: verificar que cada playbook sigue "sano" |
| 7 | **Backup `pg_dump` pre-migración** con rotación | MEDIO-ALTO | S | Enganchar `backup.py` antes de aplicar migraciones |
| 8 | **Telemetría por turno** (`stop_reason`/`is_error`) | MEDIO | S | Falta: visibilidad de failure-modes (refusals, budget) |
| 9 | **Delegación "gather" async** en el agent hub | MEDIO | M | Falta, pero solo si se necesitan delegaciones de larga duración |

---

## 2 · Detalle por mejora

### 1. Cache hit-rate (la joya) — ALTO / S
MIA declara en su constitución que el prefix caching de LiteLLM "ahorra ~75%", pero
`metrics/usage.py::record()` solo lee `prompt/completion/total_tokens` — **ignora** los campos de
caché que LiteLLM sí expone (`prompt_tokens_details.cached_tokens`, y en passthrough Anthropic
`cache_read_input_tokens`/`cache_creation_input_tokens`). No hay **un solo número** que verifique la
afirmación en producción.
- **Cómo:** migración aditiva (`ALTER TABLE turn_usage ADD COLUMN cache_read_tokens/cache_creation_tokens`),
  ~10 líneas en `record()`, un query `SUM(...) GROUP BY model/task` bajo RLS, y una línea en el panel:
  "Caché: X% de la entrada servida desde caché".
- **Ventaja de MIA sobre claudeclaw:** ellos tuvieron un bug (medían la *última* llamada, donde la
  caché siempre está caliente → hit-rate falso ~100%); MIA ya inserta una fila por llamada, así que el
  `SUM` del turno sale bien de forma natural.
- **Límite honesto a declarar:** solo será real en el path API/OpenRouter; con `cli-claude`
  (suscripción) y `mia-local` (Ollama) probablemente no hay señal de caché reportada.
- **Lección de proceso robada:** claudeclaw borró su métrica de "dólares ahorrados" por deshonesta
  (tarifa plana). MIA ya calcula costo real por modelo — no repetir ese error.

### 2. Preservar secretos en upgrade — ALTO / S
claudeclaw nunca rota `DASHBOARD_TOKEN`/`DB_ENCRYPTION_KEY` si ya existen (`preserve()`: leer-existente-o-generar).
Para MIA es **crítico**: al reinstalar el `.exe`, regenerar `DB_ENCRYPTION_KEY` rompería los datos
cifrados. Verificar que `env_writer.py`/`first_run.py` hacen exactamente esto. Barato de comprobar,
catastrófico si falta.

### 3. Root de config canónico — ALTO / S
Lección del commit `f233035`: tenían rutas (`BUNKER_DIR`) hardcodeadas a `~/.claudeclaw` en vez de
derivar del root único `CLAUDECLAW_CONFIG`. Para MIA: auditar que **todo** (db seed, .env, logs,
backups, config LiteLLM) derive del `app_dir` central (`paths.py`) y que nada hardcodee
`%APPDATA%`/`expanduser` en paralelo. Previene una clase entera de bugs de configuración partida.

### 4. Smoke-test post-first-run — ALTO / M
Tras instalar, claudeclaw hace `systemctl is-active` + un `curl` de humo al dashboard y reporta. Para
MIA: al final del first-run, un health-check explícito (¿FastAPI responde `/health`? ¿LiteLLM.exe
vivo? ¿nº de migraciones aplicadas == esperadas? ¿checkpointer OK?). Convierte "instaló" en "instaló
**y arranca**" — confianza directa para un instalador de doble-clic de despacho.

### 5. Atajos de despacho (comando → prompt canónico) — ALTO / M
En claudeclaw, `agent.yaml` define `commands:` — cada comando es una intención fija que se **expande a
una instrucción canónica completa** y se auto-registra en el menú. Para MIA: "atajos" que el abogado
dispara y que ejecutan un playbook/persona con un **prompt canónico verificable y reproducible** (en
vez de reescribir la intención cada vez). Encaja con playbooks+personas que MIA ya tiene; falta solo
la capa "comando→prompt canónico" expuesta en la UI.

### 6. Health-check de playbooks/skills — MEDIO-ALTO / S
`skill-health.ts` corre un check por skill y persiste `healthy/unhealthy/timeout`. Para MIA: un check
que valide que cada playbook/skill sigue sano (sus referencias/scripts resuelven, sus citas siguen
verificables). Muy alineado con la cultura [VERIFICAR]/gates de MIA.

### 7. Backup `pg_dump` pre-migración — MEDIO-ALTO / S
claudeclaw copia la DB a `.pre-{version}.bak` antes de migrar, con rotación a 3. MIA tiene migrador
atómico con checksums, pero conviene confirmar que hace un `pg_dump` a `app_dir/backups/pre-{ver}.dump`
**antes** de aplicar y rota. Postgres ≠ SQLite (no es copiar un archivo). Alto valor para datos de
despacho irrecuperables. MIA ya tiene `backup.py` — probablemente es solo engancharlo.

### 8. Telemetría por turno — MEDIO / S
`stop_reason`/`is_error`/`duration_ms` por fila dan visibilidad de failure-modes (refusals, max_tokens,
turnos muertos por presupuesto) casi gratis, leídos de la respuesta ya parseada. Conecta con el
`enforce_budget` que MIA ya tiene.

### 9. Delegación "gather" async en el agent hub — MEDIO / M
El único primitivo genuinamente ausente en MIA. Hoy el agent hub (`AgentHub.invoke`) es
`subprocess.run` **bloqueante** de un solo tiro y todo es request-scoped. claudeclaw tiene un patrón
para "que el agente-A redacte mientras el agente-B investiga, y el sistema avise al terminar ambos"
**fuera del ciclo de una petición**: tabla con `group_id`/`role`/estado `waiting`, un worker que libera
el "join" cuando todos los hijos son terminales, y un **race-guard atómico**
(`UPDATE … WHERE status='waiting' RETURNING`, solo gana quien ve rowcount==1). Portable a Postgres con
`SELECT … FOR UPDATE SKIP LOCKED`. **Solo** vale la pena si MIA realmente necesita delegaciones
multi-CLI de larga duración; para casi todo, el `await` en memoria que MIA ya tiene basta.

---

## 3 · Lo que explícitamente NO copiar

- **Todo el aparato VPS/Unix:** installer de VPS, Tailscale, systemd hardening, launchd, ufw/fail2ban,
  usuario sin-privilegios, clone con token efímero. Es la mitad "más vistosa" del repo y es
  **inaplicable** a un instalador `.exe` de escritorio Windows.
- **`agent.yaml` como formato de agentes:** mover personas de la DB (RLS) a ficheros YAML sería un
  **retroceso** de seguridad y gobierno multi-tenant. MIA ya lo hace mejor.
- **Control de modelo por-agente libre:** claudeclaw deja que un YAML fije la nube; MIA tiene el candado
  de confidencialidad (persona elige un *nivel*, no un modelo crudo). No degradar.
- **`/savings` en dólares:** MIA ya calcula costo real por modelo; no repetir la tarifa plana que
  claudeclaw tuvo que borrar por deshonesta.
- **Panel de "valor":** MIA (horas×tarifa − costo IA, configurable por despacho) es estrictamente
  superior; claudeclaw ni lo intenta.
- **`warroom/` de claudeclaw:** es un servidor de **voz** (Gemini Live), no orquestación. No confundir
  con la Sala de estrategia de MIA, que es superior (rondas, moderador, citación, sellado, presupuesto).
- **Path-scanner de migraciones:** innecesario con migraciones SQL puras (no hay `.ts` ejecutable).
- **Self-location / hive-cli, handback determinista:** resuelven problemas de agentes autónomos que
  eligen destinatario/DB por su cuenta; la arquitectura centralizada de MIA (grafo LangGraph +
  `sanitize_subprocess_env`) ya los evita.
- **No degradar el migrador:** el `.applied.json` file-based de claudeclaw es inferior al ledger con
  `sha256`+advisory-lock de MIA.

---

## 4 · Los tres movimientos recomendados

1. **Medir el caching (mejora 1) + telemetría por turno (8).** Barato, alto valor, convierte una
   afirmación de la constitución en un KPI real y da visibilidad de failure-modes.
2. **Blindar el instalador (2, 3, 4, 7):** preservar secretos en upgrade, root de config canónico,
   smoke-test post-first-run y backup pre-migración. Todos S/M, todos donde un fallo silencioso más
   duele a un despacho, y justo antes de que Pipe pruebe el instalador en vivo.
3. **Atajos de despacho (5) + health-check de playbooks (6):** capitalizan lo que MIA ya tiene
   (playbooks+personas) con dos capas operativas de alto retorno.

> Nota: la pasada de Codex sobre los RFCs/arquitectura general quedó **encolada** en background al
> cerrar este documento (`task-mrpfp12l-gd3koe`); es complementaria y su núcleo (el RFC de Agent
> Awareness & Deterministic Comms) ya está cubierto en la mejora 9. Se integrará cuando termine.
