## Checkpoint anterior: CP9 — Equipo de especialistas para producir documentos (2026-07-02)

> Estado: APROBADO por Pipe y mergeado a `main` (2026-07-02). Falta la UI del
> frontend (botón Word + informe de verificación) — ver abajo.

### Qué cambió (lenguaje simple)

- Al preguntar en un asunto, Mia ya no trabaja "de un solo envión": ahora un
  equipo de especialistas hace el trabajo por etapas, cada uno con el estilo
  del despacho — uno establece los HECHOS del expediente, otro INVESTIGA las
  normas y sentencias aplicables según el país del despacho (usando primero el
  corpus jurídico interno del sistema), otro CRUZA hechos con derecho y emite
  el diagnóstico, otro REDACTA el borrador, y un VERIFICADOR revisa cita por
  cita: toda cita sin respaldo queda marcada [VERIFICAR] automáticamente
  (antes se nos escapaban sentencias sin marca — el riesgo detectado en la
  comparación de CP6).
- El avance se ve en vivo en el chat: "estableciendo los hechos…",
  "investigando normas…", "cruzando los hechos con el derecho…",
  "verificando las citas…".
- Botón nuevo posible: **descargar el borrador como documento Word** con
  formato de escrito judicial (el backend ya lo sirve).

### Frontend a revisar (Cursor — capa 3)

- NO se tocó ningún archivo del frontend en este checkpoint: el backend emite
  datos nuevos que la UI puede aprovechar. Trabajo sugerido para la
  Pantalla 2/3 (`frontend/app/asuntos/[id]/page.tsx`):
  1. Botón "Descargar en Word" → `GET /api/matters/{id}/draft.docx`
     (descarga directa; 404 si no hay borrador).
  2. Mostrar el informe del verificador de citas: el SSE `awaiting_review` y
     `GET /api/matters/{id}/draft` ahora traen `verification`:
     `{citas, marcadas, respaldadas, anotadas, detalle:[{cita, estado}]}`.
     Sugerencia: una línea sobria bajo el borrador ("Mia revisó N citas; M
     quedaron marcadas para tu verificación") con detalle expandible.
  3. Los mensajes nuevos del avance ya llegan por el evento `thinking`
     existente — no requiere cambio, solo verificar que se vean bien.

### Comportamiento esperado

- Al preguntar en un asunto: los mensajes de avance cambian por etapa (5
  frases distintas antes de "Borrador listo"); el turno tarda MÁS que antes
  (son 4 pasos de razonamiento en vez de 2 — calidad sobre velocidad).
- El borrador llega con TODAS las citas específicas o marcadas [VERIFICAR] o
  respaldadas en el corpus del sistema; el diagnóstico conserva el resumen en
  3 líneas (problema/normas/riesgo) de CP6.
- El Word descarga con encabezados, viñetas y el pie "no radicar sin
  verificar las citas marcadas".

### Bugs conocidos / fuera de alcance

- El detector de citas es conservador: puede marcar de más (inofensivo — el
  abogado revisa algo que estaba bien), y no detecta una marca escrita ANTES
  de la cita. Artículos con numerales intercalados ("artículo 164, numeral 2,
  literal i del CPACA") pueden escapar al detector — deuda anotada.
- El costo por turno aproximadamente se duplica (4 llamadas de razonamiento
  en vez de 2). Decisión consciente: calidad del documento sobre costo.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_document_pipeline` **41/41**; regresión completa
  del repo en verde (43 suites; test_rls 12/12 HALT); `test_hitl_flow`
  actualizado al orden nuevo del equipo (19/19).
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 2 mayores
  CORREGIDOS antes del commit: (M1) los expedientes grandes recuperaban su
  turno solo una vez por conversación y ahora cada etapa tiene su propio
  rescate; (M2) un patrón del verificador podía congelar el servidor con
  texto malicioso (confirmado con medición) — reescrito y movido fuera del
  hilo principal; ambos con checks de regresión (cp9-37..41). Menores
  corregidos: nombre de archivo Word con caracteres especiales, contexto
  impreciso al especialista de hechos, color/limpieza del Word. Revisión por
  lectura de patrones conocidos, no auditoría con herramientas de escaneo.
- Capa 3 (Cursor): NO APLICA aún (sin cambios de frontend en este
  checkpoint); queda el trabajo sugerido arriba para cuando se apruebe CP9.

---

