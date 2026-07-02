# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP3 + CP-C2 — Conocimiento del despacho y vault de Obsidian (2026-07-01)

### Qué cambió (lenguaje simple)

- CP3: Mia ya analiza con el MÉTODO DEL DESPACHO — al diagnosticar un
  asunto usa las notas y criterios internos del despacho (lo indexado
  desde Obsidian y las carpetas de trabajo), siempre como orientación
  de método, nunca en reemplazo de la norma o la sentencia. APROBADO
  por Pipe con una comparación en vivo (mismo caso, con y sin el
  conocimiento del despacho).
- CP-C2: Mia escribe su memoria donde el abogado la ve — su vault de
  Obsidian. Los conceptos que aprende y los reportes semanales quedan
  como notas normales bajo la carpeta `Mia/` del vault; Mia JAMÁS toca
  las notas del abogado. Incluye instalación guiada de Obsidian para
  quien no lo tenga (con confirmación explícita).

### Frontend a revisar (Cursor — capa 3)

- CP3 y CP-C2 no traen pantalla nueva (la UI de conectores llega en
  CP7). Siguen PENDIENTES de la capa 3 los 2 archivos de CP5:
- `frontend/app/page.tsx`: punto naranja en la lista de asuntos cuando
  hay borrador pendiente (title="Borrador esperando tu revisión").
- `frontend/app/asuntos/[id]/page.tsx`: panel "Diagnóstico" (texto con
  scroll interno; estado vacío: "Mia aún no ha analizado este asunto.").

### Comportamiento esperado

- Con notas del despacho indexadas, al preguntar en un asunto el
  análisis refleja el método interno (y sigue marcando [VERIFICAR] lo
  que corresponda). Si el despacho no tiene notas indexadas, todo se
  comporta EXACTAMENTE igual que antes.
- Al consolidarse un concepto o generarse el reporte semanal, aparece
  una nota nueva en `{vault}/Mia/conceptos/` o `{vault}/Mia/reportes/`
  visible en Obsidian; las notas del abogado quedan intactas.

### Bugs conocidos / fuera de alcance

- Menores anotados por los revisores: el presupuesto del 15% para las
  notas usa un estimador de tokens aproximado (podría quedarse corto o
  largo en casos límite); si el disco/OneDrive del vault no está
  disponible, la nota espejo no se escribe (queda solo en el registro
  interno — no se pierde nada, se reintenta en el siguiente ciclo).
- Decisiones de producto pendientes de Pipe (ver bugs-and-risks.md):
  privacidad de las conversaciones del asistente, diagnóstico visible
  tras aprobar, y deshabilitar la instalación de Obsidian en Modo A.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): regresión completa **40/40 suites PASS**
  (test_rls 12/12 HALT PASS); gates nuevos: test_retrieval_knowledge
  **35/35** y test_vault_write **34/34**.
- Capa 2 (revisores independientes con contexto fresco): CP3 aprobado
  con 1 mayor CORREGIDO (las notas del despacho entran al prompt
  delimitadas y con orden de no obedecer instrucciones embebidas —
  anti-inyección — más margen de recorte y limpieza de metadatos).
  CP-C2 aprobado con 2 mayores CORREGIDOS (escape por junction/symlink
  de Windows hacia fuera del vault BLOQUEADO fail-closed — reproducido
  con mklink /J; escritura al vault ya no congela el servidor con
  discos lentos). Revisión por lectura de patrones conocidos, no
  auditoría con herramientas de escaneo.
- Capa 3 (Cursor): PENDIENTE — revisar los 2 archivos de CP5 listados
  arriba y devolver hallazgos en la sección final.

### Checkpoint anterior: CP-B2 + CP-C1 — Telegram y carpetas del abogado (2026-07-01)

Mia atiende por Telegram (bot privado single-chat, opt-in hasta que
Pipe cree su bot — guía docs/telegram-setup.md) y conoce las carpetas
de trabajo autorizadas (disco, OneDrive, Google Drive); carpetas de
sistema excluidas SIEMPRE. Gates: test_telegram_bridge 22/22 y
test_local_folders 39/39; test_obsidian_sync 22/22 sin regresión.
Revisores: CP-B2 con 2 mayores corregidos (token del bot filtrado a
logs; instructivo roto por espacios de la ruta); CP-C1 con 2 mayores
de privacidad corregidos (subcarpetas de sistema excluidas también en
el descenso recursivo; carpetas >2000 archivos sin pérdida de
conocimiento). Sin frontend (capa 3 no aplica).

### Checkpoint anterior: CP5 + CP-B1 — Diagnóstico visible y modo asistente (2026-07-01)

CP5: panel "Diagnóstico" en la pantalla del asunto + punto naranja de
borrador pendiente en la lista (gate test_ux 29/29 con npm run build);
2 ventanas de carrera de milisegundos anotadas (se autocorrigen solas).
CP-B1: modo asistente — conversación libre con memoria por tenant y
usuario (test_assistant 32/32); el revisor encontró 1 BLOQUEANTE de
confidencialidad entre despachos (compresor compartido) + 2 mayores —
LOS 4 hallazgos corregidos y cubiertos con checks antes del commit.
Capa 3 de Cursor PENDIENTE sobre sus 2 archivos de frontend (los
mismos listados en el checkpoint actual).

---

## Hallazgos de Cursor (capa 3)

(Vacío. Cursor: escribe aquí tus hallazgos de la revisión visual —
diseño de interfaz, accesibilidad, consistencia de UX y superficies de
seguridad visibles en frontend. Si no hay frontend que revisar en el
checkpoint, déjalo indicado explícitamente.)
