# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP-B2 + CP-C1 — Telegram y carpetas del abogado (2026-07-01)

### Qué cambió (lenguaje simple)

- CP-B2: Mia ya puede atender por Telegram — un bot privado que solo
  responde al chat del abogado autorizado, con comando de apagado de
  emergencia. Guía de activación en 5 pasos: docs/telegram-setup.md
  (requiere que Pipe cree su bot con @BotFather — 3 minutos).
- CP-C1: Mia puede conocer las carpetas de trabajo del abogado (disco
  local, OneDrive y Google Drive vía sus carpetas de escritorio) y
  mantener su conocimiento al día sola — SOLO las carpetas que el
  abogado autorice expresamente, nunca escanea por su cuenta.

### Frontend a revisar (Cursor — capa 3)

- Ninguno todavía: los endpoints /api/folders/* y el puente de Telegram
  no tienen pantalla aún (la UI de conectores llega en CP7).

### Comportamiento esperado

- Con el bot configurado: escribirle al bot en Telegram = hablar con la
  asistente de Mia; cualquier otro chat es ignorado por completo.
- Registrar una carpeta → sus documentos quedan en el conocimiento del
  despacho; carpetas del sistema (AppData, Windows...) se rechazan y
  excluyen SIEMPRE, incluso en subcarpetas.

### Bugs conocidos / fuera de alcance

- El puente de Telegram queda apagado (opt-in) hasta que Pipe cree el
  bot y ponga sus 2 claves en la configuración.
- La detección de "Tu Google Drive" puede sugerir una unidad equivocada
  con nombre parecido (el registro sigue siendo manual y validado).
- Sync de carpetas muy grandes puede ralentizar la API mientras corre
  (patrón heredado del sync de Obsidian; anotado para endurecimiento).

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): gates test_telegram_bridge 22/22 y
  test_local_folders 39/39; test_obsidian_sync 22/22 sin regresión;
  pins 9/9 tras instalar la librería de Telegram; regresión completa
  al cierre (ver commit).
- Capa 2 (revisores independientes): CP-B2 aprobado con 2 mayores
  CORREGIDOS (el token del bot se filtraba en los registros de consola;
  el instructivo fallaba por los espacios de la ruta). CP-C1 aprobado
  con reservas y 2 mayores CORREGIDOS (subcarpetas de sistema ahora se
  excluyen también en el descenso recursivo; carpetas con más de 2000
  archivos ya no pierden conocimiento indexado) + UNIQUE anti-duplicado.
  Revisión por lectura de patrones, no auditoría con herramientas.
- Capa 3 (Cursor): no aplica — sin frontend en estos checkpoints.

### Checkpoint anterior: CP5 + CP-B1 — Diagnóstico visible y modo asistente (2026-07-01)

### Qué cambió (lenguaje simple)

- CP5: el diagnóstico jurídico de Mia por fin se VE en pantalla — la
  pantalla del asunto muestra un panel "Diagnóstico" con el análisis
  completo, y la lista de asuntos marca con un punto naranja los que
  tienen un borrador esperando la revisión del abogado.
- CP-B1: nace el modo asistente — ahora se le puede hablar a Mia de lo
  que sea (no solo dentro de un expediente): recuerda la conversación,
  conoce el estado de los asuntos del despacho, y nunca da un plazo
  procesal como definitivo sin marcarlo para verificación. Es la base
  para tenerla en el celular por Telegram (próximo checkpoint).

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/page.tsx`: punto naranja en la lista de asuntos cuando
  hay borrador pendiente (title="Borrador esperando tu revisión").
- `frontend/app/asuntos/[id]/page.tsx`: panel "Diagnóstico" nuevo
  (reemplaza los 3 paneles que siempre estaban vacíos); texto con
  scroll interno; estado vacío: "Mia aún no ha analizado este asunto."
- El chat del asistente personal NO tiene pantalla aún (llega con CP7/
  CP-B2); por ahora es solo API.

### Comportamiento esperado

- Al preguntar algo en un asunto y llegar el borrador, el panel
  Diagnóstico se llena y el asunto queda marcado con el punto naranja
  hasta que el abogado apruebe o rechace.

### Bugs conocidos / fuera de alcance

- Dos ventanas de carrera de milisegundos anotadas por el revisor de
  CP5 (punto naranja que podría quedar desactualizado si la conexión
  se corta justo en el instante equivocado — se autocorrige al abrir
  el asunto o completar el siguiente turno).
- El panel puede mostrar el diagnóstico del último turno ya decidido
  (decisión de producto pendiente: ¿ocultarlo tras aprobar?).
- Conversaciones del asistente: hoy son visibles a nivel de despacho
  (cualquier abogado del despacho puede verlas) — decisión de producto
  pendiente con Pipe; anotado por el revisor.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): regresión completa en curso al cierre — gates
  individuales: test_ux 29/29 (incluye npm run build), test_hitl_flow
  19/19, test_assistant 32/32, test_rls 12/12 HALT PASS.
- Capa 2 (subagente revisor independiente): CP5 aprobado (4 menores
  anotados arriba). CP-B1: el revisor encontró 1 BLOQUEANTE de
  confidencialidad entre despachos (el compresor de conversaciones
  compartía memoria entre clientes) + 2 mayores (inyección por título
  de asunto, conversaciones gigantes) — LOS 4 CORREGIDOS y cubiertos
  con 6 checks nuevos antes del commit. Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — revisar los 2 archivos de frontend de
  arriba y devolver hallazgos en la sección final.

### Checkpoint anterior: CP1 + CP4 — Expedientes grandes e importación de guías (2026-07-01)

### Qué cambió (lenguaje simple)

- CP1: un expediente muy grande ya no le devuelve un error al abogado —
  Mia recorta con criterio el material menos esencial (documentos
  extensos, guías) conservando siempre la conclusión del diagnóstico, y
  reintenta sola. Si el recorte no ayudaría, no desperdicia el intento.
- CP4: nuevo mecanismo para importar las guías de trabajo del despacho
  (archivos Word, texto o Markdown, varios a la vez): cada título de
  nivel 1 se vuelve una guía que Mia activará al redactar. Las guías
  pueden marcarse como protegidas para que el mantenimiento automático
  nunca las modifique.

### Frontend a revisar

- Ninguno aún — el botón "Importar guías" llega en CP7. El endpoint ya
  está listo: POST /api/playbooks/import (multipart, .md/.txt/.docx).

### Comportamiento esperado

- Con documentos enormes en un asunto, la consulta tarda lo mismo o un
  poco más, pero SIEMPRE llega a un diagnóstico y borrador (nunca un
  error de "contexto demasiado largo").
- Al importar un archivo de guías, la respuesta lista qué se importó,
  qué se omitió por repetido y qué falló — en lenguaje claro.

### Bugs conocidos / fuera de alcance

- El recorte de emergencia se usa UNA vez por consulta (si el análisis
  la consumió, la redacción del mismo turno ya no la tiene) — decisión
  consciente, anotada por el revisor.
- Endurecimiento diferido a CP8 (anotado por el revisor de CP4, son
  patrones heredados del endpoint de documentos preexistente): archivos
  comprimidos maliciosos (.docx bomba) y lectura del archivo completo
  en memoria antes de validar tamaño.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): VERDE — regresión completa 35/35 suites PASS
  (test_rls 12/12 HALT PASS; gates nuevos: test_context_recovery 34/34
  y test_playbook_import 21/21).
- Capa 2 (subagente revisor independiente): dos revisores con contexto
  fresco, ambos veredicto "apto/aprobado". Hallazgos mayores corregidos
  antes del commit: guard de reducción estricta (CP1-H1), fallo puntual
  de guardado no aborta el batch, tope de 100 guías por archivo y cap
  de longitud del campo que viaja al prompt (CP4). Revisión por lectura
  de patrones, no auditoría con herramientas.
- Capa 3 (revisión visual de Cursor): no aplica — sin cambios de
  frontend; Cursor confirma en la sección siguiente.

### Checkpoint anterior: CP2 — Motor por suscripción (2026-07-01)

Mia piensa con la suscripción de Claude del abogado (sin costo por
consumo); tres modos por despacho ("Mi suscripción" / "Nube" / "Todo en
mi equipo"); respaldo local restaurado. Verificado: 33/33 suites + turno
vivo de 176s con borrador de 19.098 caracteres y citas correctas, cero
facturación por API. Revisor independiente: 2 mayores corregidos
(aislamiento de credenciales, blindaje de ejecutable).

---

## Hallazgos de Cursor (capa 3)

(Vacío. Cursor: escribe aquí tus hallazgos de la revisión visual —
diseño de interfaz, accesibilidad, consistencia de UX y superficies de
seguridad visibles en frontend. Si no hay frontend que revisar en el
checkpoint, déjalo indicado explícitamente.)
