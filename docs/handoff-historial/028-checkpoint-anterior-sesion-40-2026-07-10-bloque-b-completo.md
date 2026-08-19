## Checkpoint anterior: Sesión 40 (2026-07-10) — BLOQUE B COMPLETO: guías asistidas + gobernanza de lo aprendido

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque B del plan de evolución de producto (aprobado por Pipe), con la
misma orquestación multi-agente autorizada desde la sesión 38:

- **"Crear con Mia" (nuevo):** el abogado ya no tiene que redactar una guía de trabajo desde
  cero — le abre una entrevista corta (3 a 6 preguntas), Mia arma un borrador, el abogado lo edita
  libremente y SOLO se guarda cuando él pulsa Guardar (nada toca la base de datos antes de eso).
  Disponible desde Conocimiento y también desde un asunto ya resuelto ("Convertir en guía"),
  donde precarga lo que se hizo en ese caso.
- **Gobernanza completa de guías:** historial de versiones con restaurar, archivar/reactivar,
  editar aunque la guía esté protegida (protegida solo bloquea que Mia la cambie sola), y las
  sugerencias de mejora de Mia ahora se pueden editar antes de aplicarlas (antes era solo
  aprobar o rechazar tal cual).
- **Una sola pantalla para "lo que Mia sabe hacer":** se fusionaron dos pestañas que mostraban
  la misma información partida en dos vistas (guías y habilidades) en una sola, con el origen de
  cada guía en lenguaje llano (manual, importada, con Mia, aprendida) y de dónde viene cada
  sugerencia ("Aprendí esto trabajando en...").
- **Corrección importante de comportamiento:** crear una guía con un nombre que ya existe ya NO
  la sobrescribe en silencio — avisa en llano que ya existe una guía con ese nombre.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (76 suites)** — línea base sube de 74 a 76:
  `test_playbook_versions` 59/59 (48 iniciales, sube tras la capa 2), `test_guide_interview` 25/25.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `test_ux` sube a 37/37,
  `test_second_brain_ui` 26/26. `npm run build` verde (14 páginas). Hubo 1 ciclo de corrección en
  el gate (un test buscaba el nombre viejo de una pestaña; se actualizó al nuevo copy sin
  debilitar la aserción).
- **Capa 2: revisión adversarial con 4 agentes independientes (contexto fresco)** — 10 hallazgos
  CONFIRMADOS, todos corregidos y re-verificados antes del commit:
  3 MAYORES (restaurar una versión con un título repetido daba un error técnico en vez de un
  aviso en llano; crear una guía con nombre repetido sobrescribía en silencio la existente sin
  dejar rastro; "Editar antes de aplicar" descartaba la corrección que el abogado acababa de
  escribir), 7 menores (varios casos de identificadores mal escritos que daban error técnico en
  vez de aviso en llano; una guía nueva creada por Mia no quedaba indexada para búsquedas
  futuras; el botón "Convertir en guía" aparecía en casos donde no debía). Detalle completo en
  `memory/progress.md` sesión 40.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Conocimiento → "Guías y habilidades"**: pulsar "Crear con Mia", responder la entrevista
   (mínimo 3 preguntas), revisar que el borrador es editable y que cancelar a mitad de camino NO
   deja ninguna guía creada; guardarla y verla aparecer con el sello "Creada con Mia".
2. Editar una guía existente, ver su Historial y restaurar una versión anterior.
3. Desactivar y reactivar una guía.
4. En Sugerencias: usar "Editar antes de aplicar" sobre una propuesta.
5. En un asunto con borrador APROBADO: usar el botón "Convertir en guía" (y verificar que NO
   aparece si el borrador fue rechazado o aprobado con cambios).

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque C** del plan (agentes jurídicos con conocimiento propio + perfil del
   despacho editable y unificado + Configuración reorganizada en subtabs). El plan vive en
   `memory/plan-evolucion-producto.md` (Bloques A y B ya marcados completados).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el endpoint de entrevista para crear agentes (`kind='agente'`) responde
   "próximamente" hasta el Bloque C — el componente de entrevista ya quedó reusable para ese caso
   (Riesgo #58).

### Trabajo en background sin leer

Nada.

### Decisiones tomadas y suposiciones declaradas

- Crear una guía (por el wizard o manualmente) ya NO sobrescribe en silencio una guía con el
  mismo nombre — avisa en llano y el abogado decide. Antes de esta sesión, un nombre repetido
  podía hacer "desaparecer" una guía existente sin que nadie se diera cuenta.
- El resultado de la revisión de un borrador ("aprobado" vs. "aprobado con cambios" vs.
  "rechazado") ahora es visible para la pantalla del asunto, no solo para el backend — es lo que
  decide si aparece el botón "Convertir en guía". Un borrador "aprobado con cambios" NO cuenta
  como evidencia suficiente (mismo criterio que usa la entrevista para decidir qué mostrarle a
  Mia).
- Crear agentes jurídicos con "Crear con Mia" queda para el Bloque C a propósito — el wizard de
  entrevista de esta sesión ya se construyó pensando en reusarse para ese caso.

---

