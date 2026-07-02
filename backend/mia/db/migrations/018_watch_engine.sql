-- Mia · 018_watch_engine.sql · CP-P1 (Ola 2) — motor de vigilancia programada
--
-- Eleva los recordatorios de CP-B3 a un MOTOR que vigila condiciones en el tiempo con:
--   1. ejecución AT-MOST-ONCE entre procesos (claim CAS) — cierra el Riesgo #22/#35.3
--      (con >1 worker de uvicorn habría N schedulers disparando el MISMO job).
--   2. wake-gate: un chequeo barato decide si vale la pena despertar al agente (LLM).
--   3. jobs no_agent: vigilancias que solo escanean + avisan, SIN gastar tokens.
--
-- Dos objetos:
--
--   scheduled_claims — tabla de SISTEMA (NO por-tenant): un job del scheduler es una
--     operación de instalación (enumera tenants internamente), así que el claim es
--     global. La accede SOLO la conexión admin (postgres), igual que la enumeración
--     cross-tenant de scheduler.py. Sin tenant_id → sin RLS (no es dato de despacho);
--     mia_app no la toca.
--
--   reminders.heads_up_sent_at — la vigilancia de plazos PRÓXIMOS (aviso anticipado,
--     distinto del despacho al vencer de CP-B3) marca aquí que ya avisó, para no
--     repetir el aviso anticipado del MISMO recordatorio en cada ciclo.

CREATE TABLE IF NOT EXISTS scheduled_claims (
  job_name    text PRIMARY KEY,          -- nombre del job/vigilancia
  claimed_at  timestamptz NOT NULL DEFAULT now(),
  claimed_by  text NOT NULL              -- identificador del worker (pid@host)
);

-- Aviso anticipado de un plazo procesal PRÓXIMO (heads-up), a lo sumo una vez por
-- recordatorio. NULL = aún no se ha avisado con anticipación. Distinto de sent_at
-- (que marca el despacho al VENCER, CP-B3).
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS heads_up_sent_at timestamptz;
