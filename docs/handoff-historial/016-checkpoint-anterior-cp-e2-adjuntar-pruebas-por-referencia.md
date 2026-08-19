## Checkpoint anterior: CP-E2 — Adjuntar pruebas por referencia (@expediente / @carpeta) (2026-07-03)

### Qué cambió (lenguaje simple)

- El abogado ya puede **traer evidencia a la conversación escribiéndola con `@`**: en el
  chat de un asunto o con Mia (Telegram/asistente) puede escribir `@expediente` (los
  documentos del asunto en curso), `@expediente:"Banco Popular vs Zurich"` (otro asunto
  del despacho, por su nombre) o `@carpeta:"Pruebas Zurich"` (una carpeta de trabajo
  registrada). Mia **expande la mención** e incorpora esa evidencia a su análisis del
  turno, sin que el abogado copie y pegue nada.
- Es donde más sirve **hablando con Mia libremente** (por Telegram o el asistente), que
  antes no traía documentos sola: ahora `@expediente:"..."` mete el expediente a la charla.
- **Privacidad primero:** una mención SOLO resuelve a expedientes y carpetas **del propio
  despacho** (nunca de otro), y **nunca abre un archivo del disco** — lee lo que Mia ya
  tiene indexado. Si el nombre no existe, está deshabilitado, o parece una ruta de
  computador, Mia lo dice en llano y no adjunta nada. Toda la evidencia entra **sellada**
  (Mia la trata como datos del caso, no como órdenes). Si el material referenciado es muy
  grande, se adjunta **recortado con aviso honesto** (nunca finge tener la prueba completa).

### Frontend (Cursor — capa 3): NO hay UI nueva

- CP-E2 es **sintaxis de mensaje** — el abogado escribe `@expediente`/`@carpeta` en el campo
  de chat que YA existe (asunto y, sobre todo, Telegram). No toca `frontend/`. **No hay nada
  que construir ni revisar** en la interfaz para este checkpoint.
- Trabajo FUTURO opcional (no de este checkpoint): un autocompletado que sugiera nombres de
  expedientes/carpetas al teclear `@` en el chat del asunto. Los datos ya existen
  (`GET /api/matters`, `GET /api/folders`). No es necesario para que la función trabaje hoy.
- Nota: sigue pendiente de Cursor el control del tope de gasto de **CP-E1** (ver abajo);
  ese trabajo NO se mezcló con CP-E2.

### Comportamiento esperado

- En un asunto: "Analiza @expediente a fondo" → Mia trabaja con los documentos del asunto
  (igual que antes, pero ahora explícito); "compara con @expediente:\"Otro caso\"" cruza con
  otro expediente del despacho. La búsqueda interna del turno usa el texto SIN la mención
  (no se ensucia con el documento adjunto).
- Con Mia libre (Telegram): "Según @expediente:\"Zurich\" ¿qué defensa tengo?" trae ese
  expediente a la respuesta. Nombre ambiguo o inexistente → aviso en llano, sin adjuntar.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_context_references.py` **43/43** (parseo + denylist de rutas +
  resolución por título/etiqueta con RLS + AISLAMIENTO entre despachos + sellado
  anti-inyección + techo de tokens con recorte marcado + query de recuperación limpia);
  regresión **ALL PASS (54 suites)** (test_rls 12/12 HALT). Sin frontend web → sin npm build.
- Capa 2 (revisor adversarial independiente): confidencialidad/RLS, confinamiento a las
  filas del despacho (nunca disco), anti-inyección (CP-S1), escape LIKE y fail-open/closed
  CONFIRMADOS. 2 MAYORES (fetch sin LIMIT en SQL → tope de recursos; techo de tokens en el
  listado de carpeta → presupuestado por archivo) + 2 MENORES (`@expedientes` plural;
  query solo-referencia) corregidos y RE-VERIFICADOS CERRADOS antes del commit. Ver
  memory/progress.md sesión 31.
- Capa 3: NO APLICA (sin frontend en este checkpoint).

---

