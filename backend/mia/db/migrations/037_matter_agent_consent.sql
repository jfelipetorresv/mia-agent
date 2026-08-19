-- Mia · 037_matter_agent_consent.sql · "no me preguntes más por este ayudante en este asunto"
--
-- CP-HUB2 ("Mia decide y me pregunta"): cuando Mia PROPONE por su cuenta un ayudante externo,
-- el abogado aprueba viendo el texto EXACTO que va a salir. Si además marca "no me preguntes
-- más por este ayudante en este asunto", la autorización queda aquí y las próximas propuestas
-- de ESE ayudante en ESE asunto se ejecutan sin volver a preguntar.
--
-- POR QUÉ (asunto, ayudante) Y NO GLOBAL: el consentimiento del abogado es contextual. Que
-- acepte que el asistente de navegación consulte el estado de un radicado en un ejecutivo
-- público no dice NADA sobre un asunto reservado de otro cliente. Una casilla global sería
-- exactamente la casilla que se marca una vez y se olvida — lo contrario del control que Pipe
-- pidió. La PK compuesta (tenant_id, matter_id, agent_key) ES la regla.
--
-- LO QUE ESTA TABLA **NO** ES: no es un permiso. Una fila aquí NO autoriza a sacar nada del
-- equipo: solo suprime la PREGUNTA. El candado de confidencialidad (gateway/hub_gate.py:
-- política ≠ 'soberano' + opt-in del despacho en hub_config) se evalúa SIEMPRE y ANTES, en
-- cada turno. Un despacho que pasa a "Todo en mi equipo" deja de delegar aunque estas filas
-- existan; volver a "suscripción" no las resucita como permiso, solo vuelven a suprimir la
-- pregunta de algo que el candado ya autorizó por otra vía.
--
-- REVOCAR = BORRAR LA FILA (DELETE .../delegation/memoria/{slug}): el efecto es inmediato y
-- el estado por defecto vuelve a ser "pregúntame" — el modo seguro. Sin fila, Mia pregunta.
--
-- ON DELETE CASCADE en matter_id: cerrar/borrar el asunto se lleva su memoria. Correcto: la
-- autorización era DE ese asunto y no debe sobrevivirle ni migrar a otro.
--
-- RLS fail-closed por tenant, patrón idéntico al resto de tablas por-despacho
-- (023_personas / 032_gold_cases / 033_warroom_results): ENABLE + FORCE + política ALL con
-- app_current_tenant(). Sin el GUC app.tenant_id → 0 filas (y `remembered()` cae a False =
-- preguntar). Migración aplicada por `postgres`. Idempotente.

CREATE TABLE IF NOT EXISTS matter_agent_consent (
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id   uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  -- Clave INTERNA del conector (gateway/agent_hub.CONNECTORS): 'openclaw', 'hermes'…
  -- No se usa el slug público porque el slug es contrato de UI y puede renombrarse.
  agent_key   text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, matter_id, agent_key)
);

ALTER TABLE matter_agent_consent ENABLE ROW LEVEL SECURITY;
ALTER TABLE matter_agent_consent FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_matter_agent_consent ON matter_agent_consent;
CREATE POLICY p_matter_agent_consent ON matter_agent_consent
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON matter_agent_consent TO mia_app;
