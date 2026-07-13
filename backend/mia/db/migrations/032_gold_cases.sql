-- Mia · 032_gold_cases.sql · Banco de oro (gold-set de calidad por-despacho, Fase 1)
--
-- Un "caso de oro" es un asunto REAL ya resuelto que el despacho guarda como examen fijo de
-- calidad: pregunta + documentos + borrador aprobado + rúbrica (citas y conclusiones clave que
-- el abogado confirma). Sirve de CANDADO: ninguna mejora de Mia se da por buena si baja la nota
-- sobre estos casos (detecta regresiones silenciosas de calidad).
--
-- CONFIDENCIALIDAD (regla dura): NADA identificable se guarda aquí. El asunto se ANONIMIZA
-- ANTES de persistir (backend/mia/security/anonymize.py); a la tabla solo llega texto ya
-- anonimizado + el HASH del mapa marcador→valor real (`anon_map_ref`) — NUNCA el mapa en claro.
-- Los casos SINTÉTICOS del banco de pruebas (eval/cases.py) siguen viviendo como JSONL en disco;
-- esta tabla es para los casos guardados POR-DESPACHO, que sí tocan datos reales anonimizados.
--
-- `status`: draft → el abogado aún revisa la anonimización y las claves; confirmed → él lo
-- aprobó (ÚNICA vía, endpoint :confirm); archived → retirado del examen sin borrar histórico.
--
-- RLS fail-closed IGUAL que el resto de tablas por-tenant (schema.sql, patrón 015): ENABLE +
-- FORCE + política ALL con USING/WITH CHECK = app_current_tenant(). Sin GUC `app.tenant_id` →
-- 0 filas. Migración aplicada por `postgres`. Idempotente.

CREATE TABLE IF NOT EXISTS gold_cases (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- procedencia (auditoría): de qué asunto salió. SET NULL si el asunto se borra: el caso de
  -- oro ya es anónimo y autónomo, no debe morir con el expediente que lo originó.
  source_matter_id  uuid REFERENCES matters(id) ON DELETE SET NULL,
  title             varchar(200) NOT NULL,
  message           text NOT NULL,                        -- pregunta ANONIMIZADA
  documents         jsonb NOT NULL DEFAULT '[]'::jsonb,    -- [{filename, chunks:[...]}] ANONIMIZADOS
  gold_answer       text NOT NULL DEFAULT '',              -- borrador aprobado ANONIMIZADO
  rubric            jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {citas_clave:[...], conclusiones_clave:[...]}
  -- HASH (sha256) del mapa marcador→valor real. NUNCA el mapa en claro: solo permite auditar
  -- que la anonimización fue reproducible, sin poder reidentificar desde la DB.
  anon_map_ref      text,
  status            varchar(16) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'confirmed', 'archived')),
  synthetic         boolean NOT NULL DEFAULT false,
  created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Listado del banco por despacho (los confirmados, más recientes primero).
CREATE INDEX IF NOT EXISTS idx_gold_cases_tenant_status
  ON gold_cases(tenant_id, status, updated_at DESC);

-- RLS fail-closed (política estándar del proyecto — ver schema.sql / 015_assistant.sql).
ALTER TABLE gold_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE gold_cases FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_gold_cases ON gold_cases;
CREATE POLICY p_gold_cases ON gold_cases
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON gold_cases TO mia_app;
