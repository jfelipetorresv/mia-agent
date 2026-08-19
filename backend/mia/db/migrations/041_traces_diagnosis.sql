-- Mia · 041_traces_diagnosis.sql · Riesgo #68 — persistir el diagnóstico del turno
--
-- El diagnóstico jurídico (analysis_node) vivía SOLO en el checkpoint de LangGraph, que
-- `prepare_new_turn` borra al arrancar el siguiente turno. Efecto: la captura automática del
-- banco de oro (gold_cases) leía el diagnóstico VACÍO y las `conclusiones_clave` quedaban en
-- blanco; de fondo, cada turno tiraba la parte más valiosa del razonamiento.
--
-- La tabla `traces` (013) ya es "una fila por turno finalizado", con RLS por-tenant y el índice
-- que usa la captura. Añadir el diagnóstico aquí (en vez de una tabla nueva) reusa esa RLS y ese
-- índice, y evita un segundo punto de fallo en `finalize_node`.
--
--   diagnosis          — el diagnóstico en prosa (sin el bloque de cierre de máquina).
--   diagnosis_summary  — el cierre estructurado {problema, normas, riesgo} ya parseado.
--
-- No se toca el trigger `content_tsv`: el diagnóstico no entra a la búsqueda FTS del asunto.
-- Idempotente (IF NOT EXISTS). Migración por `postgres`.

ALTER TABLE traces ADD COLUMN IF NOT EXISTS diagnosis         text;
ALTER TABLE traces ADD COLUMN IF NOT EXISTS diagnosis_summary jsonb;
