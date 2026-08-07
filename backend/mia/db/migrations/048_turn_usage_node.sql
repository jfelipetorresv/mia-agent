-- 048 · F0.1 del plan de eficiencia (PLAN-principios-harness-llos-eficiencia.md):
-- atribución del gasto POR NODO del grafo. Hasta ahora turn_usage registraba alias y task,
-- pero todo el turno se acumulaba sin poder saber qué etapa (facts/research/analysis/draft/
-- verificador_citas/harvest/edit/work) gastó qué — y sin eso ninguna optimización es medible.
-- NULL = llamada fuera del grafo (auxiliares, compresión, onboarding) o anterior a esta columna.
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS node varchar(64);
