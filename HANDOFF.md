# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP1 + CP4 — Expedientes grandes e importación de guías (2026-07-01)

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
