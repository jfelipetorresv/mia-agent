-- 063 · Latencia y llamadas a herramientas por llamada al LLM (mecanismo portado del
-- harness de litigio, 2026-08-24). Hasta ahora el único reloj era md["latency_ms"] del
-- turno COMPLETO (graph.finalize_node): con 4+ nodos LLM en el turno nadie podía decir
-- qué etapa se llevó el tiempo. Y los tool-calls se iteraban (agents/retrieval.py,
-- mcp/turn.py) sin que nadie los contara.
--
--   latency_ms  = milisegundos de ESTA llamada al proveedor (reloj alrededor de
--                 _call_with_retries en agent/llm.call_llm). Se agrega por nodo en
--                 eval.harness.usage_by_node. NULL = fila anterior a esta columna.
--   tool_calls  = cuántas llamadas a herramientas pidió la RESPUESTA de esta llamada
--                 (len(message.tool_calls)). Cuenta las rondas de la lectura agéntica
--                 y del turno MCP sin tocar sus bucles: ambas pasan por call_llm.
--                 NULL = fila anterior; 0 = respuesta sin herramientas.
--
-- Compatibilidad: columnas ADITIVAS y anulables — las filas viejas no rompen nada y
-- los agregados usan coalesce. Idempotente: re-ejecutable sin efecto.
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS latency_ms double precision;
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS tool_calls integer;
