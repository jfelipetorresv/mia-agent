-- Mia · 042_turn_usage_cache.sql · Observabilidad de caché de prompt (medir, no afirmar)
--
-- La constitución afirma que el prefix caching de LiteLLM "ahorra ~75%", pero hasta ahora
-- `metrics/usage.record()` solo guardaba prompt/completion/total y DESCARTABA los campos de
-- caché que la respuesta sí trae. Resultado: una afirmación de arquitectura sin un solo número
-- que la verifique en producción. Estas columnas convierten esa afirmación en un KPI real.
--
--   cache_read_tokens      — tokens de entrada servidos DESDE la caché (no se recomputan).
--   cache_creation_tokens  — tokens de entrada ESCRITOS a la caché (primer uso, "cold").
--   stop_reason            — por qué terminó la generación (stop | length | tool_calls | …);
--                            'length' revela respuestas truncadas por tope de tokens.
--
-- Hit-rate = read / (read + creation + prompt_no_cacheado). Solo hay señal real en el path
-- API/OpenRouter; con cli-* (suscripción) y mia-local (Ollama) estos campos quedan en 0 —
-- se declara el límite en el panel, no se inventa un número.
--
-- Aditivo e idempotente (mismo patrón que MIA ya usa). Migración por `postgres`.

ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS cache_read_tokens     integer NOT NULL DEFAULT 0;
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS cache_creation_tokens integer NOT NULL DEFAULT 0;
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS stop_reason           varchar(32);
