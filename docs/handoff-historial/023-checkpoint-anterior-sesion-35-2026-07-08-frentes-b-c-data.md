## Checkpoint anterior: Sesión 35 (2026-07-08) — Frentes B/C + Data Factory del corpus + bugfix FTS

### Qué se hizo esta sesión

Sesión de retoma: había ~5h de trabajo de una sesión previa sin commitear ni documentar (nunca corrió
`/cierre`). Se reconstruyó por lectura de código, se verificó y se corrigió antes de commitear:

- **Bugfix** `agents/research.py`: la consulta FTS de investigación mandaba el mensaje completo del
  abogado (0 resultados casi siempre) → ahora usa términos clave + citas exactas en OR.
- **Frente B (aprendizaje):** motivo del rechazo en la traza (B1), botón "Revisar ahora" en
  Conocimiento → `POST /api/learning/run` (B2), aprobar una corrección de wiki ya la aplica de verdad
  al archivo del concepto (B4).
- **Fase 3 · frente C + Data Factory del corpus:** `rag/corpus_factory.py` (motor único, jurisdicción
  por pack JSON — nada de Colombia hardcodeado, ver decisión de Pipe en `memory/progress.md` sesión
  35) + `connectors/vault_export.py` (backfill de playbooks y fichas del corpus al vault de Obsidian).

Detalle completo, con los 5 hallazgos de capa 2 y sus correcciones, en `memory/progress.md` (sesión 35).

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/memoria/page.tsx` (pestaña Sugerencias): botón nuevo **"Revisar ahora"** sobre la
  lista de propuestas — dispara `POST /api/learning/run`, muestra spinner mientras corre y un mensaje
  de resultado ("Mia propuso N mejoras nuevas" / "no encontró nada nuevo"). `npm run build` verde y
  cubierto por gate de API; falta el recorrido visual en vivo (clic real, estados de carga/error).
- Nada más cambió en `frontend/`; el resto de esta sesión fue backend puro (Data Factory, vault export,
  bugfix de investigación) sin superficie nueva para el abogado más allá del botón de arriba.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **66/66 suites verdes** (dos corridas — antes y después de aplicar las
  correcciones de capa 2), `test_rls`/`check_env_pins` HALT intactos. Gates nuevos: `test_research_query`
  11/11, `test_corpus_factory` 12/12, `test_vault_export` 38/38.
- Capa 2 (revisor adversarial independiente, workflow multi-agente): 5 hallazgos CONFIRMADOS, los 5
  corregidos y RE-VERIFICADOS antes del commit (colisión de slug al exportar playbooks; parseo frágil
  del concepto de una wiki_correction → columna dedicada; conexión pooled sostenida durante E/S de
  disco; lógica de identidad duplicada entre adaptadores del corpus; fetches secuenciales evitables).
- Capa 3: **PENDIENTE** — sin navegador conectado en esta sesión para el recorrido en vivo del botón.

**6 commits en `main`, YA PUSHEADOS a `origin/main`:** `9f62b4e`, `4ea4126`, `cb32ebb`, `00728c8`,
`8376726`, `c11fb71` (el último añade 3 de los 5 quick wins de
`docs/analisis-claude-for-legal.md` — detalle en `memory/progress.md`, regresión 66/66 y capa 2
con 3 hallazgos corregidos antes del commit).

**Pendiente real para la próxima sesión (ya no queda nada "chico" en la cola):**
1. Capa 3 visual en vivo (botón "Revisar ahora" en Conocimiento + los quick wins de prompt no
   tienen UI que revisar, son solo texto de sistema).
2. **Gmail/OneDrive vía Graph API** (bloque 2 de la Fase 3, `mia-decisiones-pipe-fase3` en
   memoria) — es la siguiente pieza grande. Antes de construirla a ciegas, vale la pena que Pipe
   confirme alcance: ¿Gmail primero (correos+adjuntos del caso como parte del expediente) o
   OneDrive vía Graph API primero (la sincronización LOCAL de OneDrive/Google Drive Desktop ya la
   cubre `local_folder_sources`/F3.1 para quien tenga el cliente de escritorio instalado — el
   Graph API solo aporta valor si el abogado NO usa el cliente de escritorio)? Necesita también
   que Pipe registre la app OAuth (mismo patrón "activación diferida" que Microsoft 365/Google ya
   tienen: backend/UI listos, 503 hasta que lleguen las llaves).
3. Quick win #5 (checklist de pre-entrega ejecutado en el gate de aprobación) — requiere
   aprobación previa de Pipe por tocar `hitl_checkpoint`.

---

