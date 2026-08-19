## Checkpoint: conector NotebookLM + regla de agnosticismo de jurisdicción (2026-07-15)

**Rama:** `feature/robustecimiento-sin-aws` (sin commitear a `main`). **Entorno de la sesión:**
Postgres apagado → los tests que dependen de DB no se corrieron aquí (dan PoolTimeout, NO es
regresión); los tests-script sin DB sí corrieron y pasan.

### A · Conector NotebookLM (CP-NLM) — nuevo
Cada despacho puede conectar SU propio NotebookLM como fuente (jurisdiction-neutral). Piezas:
- **Consulta viva gated** (`backend/mia/connectors/notebooklm/{__init__,gate,client}.py`): MIA
  consulta el NotebookLM del abogado durante la investigación (`agents/graph.py::_notebooklm_context`
  en `_research_single`). Pasa por candado de confidencialidad `gate.query_allowed` (bloquea en
  política `soberano`, exige opt-in `allow_notebooklm`, fail-closed). La respuesta entra SELLADA
  como contexto no confiable con `[VERIFICAR]`, NUNCA como cita respaldada.
- **Instalador in-app** (`connectors/notebooklm/setup.py` + `api/routes/notebooklm.py`, registrado
  en `api/main.py`): instalar (venv aislado 3.12/3.11 + `notebooklm-py[browser]` + chromium),
  conectar (login de Google, navegador visible) y selector de notebooks. Verificación REAL de
  sesión con `notebooklm auth check` analizando el TEXTO (no el exit code) + `list --json`.
- **UI** (`frontend/app/_components/ConexionesSection.tsx`): tarjeta "Consultar mi NotebookLM"
  multi-estado (instalar → conectar → elegir notebook → activar) con aviso "cada pregunta viaja a
  Google" y bloqueo en modo soberano.
- **Verificación:** `execution/test_notebooklm_gate.py` **33/33** (gate + client + instalador +
  auth por texto). Frontend `tsc --noEmit` limpio. Dos revisiones independientes (consulta viva +
  instalador): 0 bloqueantes; 2 MAYORES del instalador YA corregidos (instalación parcial disfrazada
  de "instalado" → marcador `installed.ok`; subprocess del CLI de terceros heredaba secretos → saneado).
- **PENDIENTE:** (1) capa 3 de Pipe = E2E en vivo en su Windows (instalar/login reales + confirmar
  flags `[VERIFICAR]` del CLII contra el `--help`). (2) **Siguiente terminal:** capacidades restantes
  del spec (sources_list, notebook_create, source_add con COMPUERTA de confidencialidad para datos de
  cliente, artifacts_list, generate, download a carpeta segura) + gobernanza + auditoría (solo
  acción/fecha/tipo/cuaderno, sin contenido). Se acordó construir el envoltorio MCP stdio SOLO cuando
  exista el consumidor (el chat/agente principal), que está diferido.

### B · MIA es AGNÓSTICA DE JURISDICCIÓN (regla dura — los tres agentes)
Corrección de Pipe: MIA NO es colombiana; se adapta al despacho que la instala (Colombia, México,
España…). La jurisdicción se resuelve por despacho (packs de `jurisdiction/`, default `generic`).
Regla propagada a `TRASPASO-MODELO.md` (visión) para Claude/Codex/Antigravity.
- **Hecho (seguro):** `memory/profile_manager.py:150` y `missions/decompose.py:58` — quitado el
  default `'colombia'` y el "Español de Colombia".
- **BACKLOG "des-colombianizar" (necesita DB viva; NO tocar a ciegas):** raíz = el pack tiene
  `id_formats`/`doc_markers`/`holidays` diseñados pero SIN cablear. Puntos: defaults `'co'` en
  `rag/sat_graph.py:171,209` + migración para `DEFAULT` de columna (`003/007/011`); anonimizador
  `security/anonymize.py` (cédula/NIT/teléfono/dirección CO → riesgo de confidencialidad, mover al
  pack); remitentes `.gov.co` y léxico "tutela/desacato" en `connectors/mailbox/base.py`; seed de
  corpus CO en `rag/ingest_corpus.py` → opt-in del pack; cosméticos (`es-CO`, voz TTS, `SMLMV`, FTS
  `spanish`). Inventario completo en la auditoría de Claude de esta sesión.
- **Auditorías:** Claude entregó inventario completo; **Codex** corre en su runtime (task
  `task-mrmuhgo0-3utkp8`) — su cross-check se folará la próxima sesión (sacar con `/codex:result`).

### C · Revisiones pendientes (read-only, correr DESPUÉS de este commit, sin escribir el repo a la vez)
- **Cursor:** revisión frontend/UX + jurisdicción-neutral + jerga (instrucción entregada a Pipe).
- **Antigravity:** revisión estética/visual del producto renderizado (instrucción entregada a Pipe).

### NOTA PARA ANTIGRAVITY — implementación de diseño (frontend)
Antigravity ya entregó su auditoría estética; ESTOS son los 6 arreglos que debe **implementar**
(su ventaja: puede renderizar y VERIFICAR visualmente). **Reglas:** trabaja sobre el commit más
reciente y LIMPIO (no edites si otro agente está escribiendo el repo — un escritor a la vez);
NO toques el backend; verifica en tema CLARO y OSCURO; mantén todo jurisdiction-neutral y sin
jerga técnica; commitea al terminar. Los items de config por-despacho (moneda USD, "tarjeta
profesional") NO son tuyos — los lleva Claude en el backend.

1. **Contraste del CTA en modo claro (Alta · WCAG).** `frontend/app/globals.css:29` (`--cta: 160 100% 42%`);
   usos `app/page.tsx:142`, `app/dashboard/page.tsx:182` (`bg-cta/15 text-cta`). En claro, `text-cta`
   sobre fondo claro da ~1.90:1 (ilegible). Arreglo: en tema CLARO usa un verde oscuro para
   texto/bordes (p. ej. `hsl(160 100% 25%)` / `#008050`) — idealmente un token aparte
   (`--cta-strong`/foreground) para no dañar `bg-cta/15`; reserva el neón para fondos oscuros.
   **Resultado esperado:** texto/insignias CTA ≥ 4.5:1 en claro; modo oscuro intacto.
2. **Tildes faltantes (Media · pulido).** `frontend/app/asuntos/[id]/page.tsx` líneas 229, 243, 297, 347:
   "Mia esta analizando/redactando/preparando" → "está"; "revision" → "revisión"; etc. **Resultado:**
   mismos textos de streaming con ortografía correcta, como ya lo hace `proyectos/[id]/page.tsx`.
3. **Locale `es-CO` → neutro (Media · agnosticismo).** `app/page.tsx:34`, `app/asuntos/[id]/page.tsx:51`,
   `app/memoria/page.tsx:258`, `app/proyectos/page.tsx:37`, `app/proyectos/[id]/page.tsx:43`,
   `_components/MailSearchDialog.tsx:43`, `_components/PanelUI.tsx:12,22`. Reemplaza `"es-CO"` por
   `undefined` en `toLocale*String(...)` para usar el locale del navegador. **Resultado:** fechas
   según el equipo del abogado; sin literal `es-CO`.
4. **Ejemplo con jerga colombiana (Baja · agnosticismo).** `app/dashboard/page.tsx:259`: «recuérdame
   radicar la tutela mañana a las 9» → ejemplo pan-hispano neutro, p. ej. «recuérdame presentar la
   contestación mañana a las 9». **Resultado:** sin modismos procesales de un solo país.
5. **Animación del menú móvil (Baja · premium).** `_components/Sidebar.tsx:113` (`DialogContent`).
   Añade deslizamiento: `data-[state=open]:animate-in data-[state=closed]:animate-out
   data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left duration-250`.
   **Resultado:** el drawer entra/sale deslizando, coherente con la bienvenida.
6. **Errores sin estilo en `FuentesPanel` (Baja · estados).** `_components/FuentesPanel.tsx:158`.
   Envuelve el error de carga en un contenedor con estilo de alerta suave (borde sutil, fondo
   desaturado, ícono de aviso pequeño), coherente con las tarjetas del sistema. **Resultado:** el
   error se ve cuidado, no texto plano.

Cierre: `npx tsc --noEmit` limpio y revisión visual en claro+oscuro antes de commitear.

### HALLAZGOS DE CURSOR (capa 3, 2026-07-15) — backlog para la terminal nueva
Cursor hizo revisión read-only de frontend/UX. Los 3 audits (Cursor, Antigravity, Claude)
COINCIDEN en el sesgo de jurisdicción. Prioridad:

**CRÍTICO — ✅ RESUELTO (2026-07-16, commit `ca7cd74`).** Ruta corregida a `/settings/model-policy`
y el fallo dejó de ser silencioso: si la elección de motor no se persiste, la bienvenida se detiene
con un motivo en llano en vez de decir "listo". Test de regresión en `test_second_brain_ui.py`
(frontend 14/14); `tsc --noEmit` limpio. Descripción original abajo:
- `frontend/app/activar/page.tsx` hace `PUT /api/settings/model-policy`, pero el backend expone
  `PUT /settings/model-policy` (SIN `/api`; `ConexionesSection.tsx` sí usa la ruta buena). En el
  viaje de bienvenida, elegir motor / opt-in OpenRouter **falla en silencio** (catch vacío) → el
  abogado cree que quedó "Todo en tu equipo"/OpenRouter y Mia sigue con otra política. OJO: es el
  MISMO endpoint que extendí para `allow_notebooklm` → desde Activar tampoco se podría fijar el
  opt-in de NotebookLM (Configuración sí). Arreglo: corregir la ruta + no tragar el error.

**ALTO — promesas/UX que dañan confianza:**
- Promesas contradictorias: "Notas del despacho" marcado *Próximamente* en onboarding pero Obsidian
  YA se instala/sincroniza en Conexiones; Telegram ofrecido como checkbox "normal" pero su activación
  real es un wizard @BotFather + `.env`, no OAuth. Alinear expectativa.
- Deep-links de borrador: "Para tu decisión" y el badge llevan a `/asuntos/{id}`, no a
  `/asuntos/{id}/revisar`; y `?sin_borrador=true` no se consume (el abogado vuelve al chat sin
  explicación). Añadir CTA "Revisar borrador" + leer el query.
- Fallos tragados: `memoria/page.tsx::act()` con `.catch(()=>{})`; detección de drift del curator por
  `message.includes("409")` es frágil → usar `err.status === 409`.

**MEDIO — sesgo de jurisdicción en frontend (se suma al backlog de "des-colombianizar"):**
- Placeholders CO: "Fajardo & Asociados S.A.S." (forma societaria), "tarjeta profesional",
  "Lexia Abogados" (register). Empty state "radicar la tutela". Detonador `SMLMV/SMMLV`
  (`revisar/page.tsx`). Copy "Rama Judicial" en el MCP de consulta de procesos. `es-CO` en fechas
  (ya listado). Moneda fija USD (Panel/Configuración) → moneda por despacho. CountrySelector pone
  Colombia primero (deliberado, no bug). Solo el pack `co` instalado en backend.
- Jerga técnica que se filtra: placeholder "Nombre del índice" (Pinecone) — el abogado no sabe qué
  es; fallback de automatizaciones muestra `clave: valor` crudo.
- Capacidades muertas: `/settings/agents` (Agent Hub) y `gold-cases` tienen backend pero NO UI →
  orquestar o esconder hasta que haya pantalla.
- `AuthGate` renderiza `null` mientras valida el token → pantalla en blanco (poner un loader).

Nota: Cursor confirma que §G se cumple en general (no hay "MCP/HITL/tenant/pgvector" en el copy).

---

