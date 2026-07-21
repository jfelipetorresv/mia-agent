# F4 — Seguridad pre-cliente (frente A3 de la auditoría competitiva)

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F4".

## Regla dura que esta fase custodia
**Ningún expediente REAL de cliente entra a MIA — ni en dogfooding ni en piloto — antes de cerrar
esta fase.** Las corridas de F1-F3 usan solo material sintético o público (el candado de datos del
runner ya lo exige fail-closed). Enviar material de cliente a una política de nube exige además la
regla vigente de Lexia: aprobación previa de Pipe para datos identificables hacia cualquier proveedor
de IA.

## Objetivo
Cerrar los riesgos de seguridad conocidos que bloquean el primer expediente real de un cliente.

## Pasos
1. Cerrar con test de regresión cada uno:
   - **#29** — login usa función `SECURITY DEFINER` para resolver email ANTES de RLS
     (`memory/bugs-and-risks.md`); auditar antes de multi-tenant productivo, considerar rol auth
     dedicado.
   - **#30** — Pinecone API key sin cifrar en `tenant_settings.config`; reusar el patrón de
     `test_secret_at_rest.py`/`test_secret_scope.py`.
   - **#56** — navegador de carpetas fail-open → fail-closed.
2. **Gate de borrado total** al tramo HALT: borrar un despacho borra TODO (pgvector, archivos,
   trazas) — con test que lo demuestre, corriendo SOLO sobre despachos-fixture aislados creados para
   la prueba (jamás sobre un despacho vivo).
3. #35 (canal único Telegram) y #3 (pgvector para clientes en Windows nativo, binario de terceros no
   oficial): documentar como limitación conocida v1 salvo que Pipe los priorice.
4. Regresión obligatoria: el E2E de F3 se re-corre tras cada cambio de esta fase (#29 toca auth;
   romper login rompe todo).

## Archivos críticos
Auth/RLS (#29), `tenant_settings` (#30), navegador de carpetas (#56), tramo HALT.

## Salida medible (copiada del plan maestro)
#29/#30/#56 cerrados con regresión; gate de borrado en HALT y verde; `memory/bugs-and-risks.md` fiel
a la realidad.

## Gates
HALT completo + suite de borrado total sobre fixtures aislados + E2E de F3 re-corrido en verde tras
cada cambio de esta fase.

## Modelos (matriz del plan)
Lógica crítica de seguridad (auth/RLS #29): Opus (high) implementa, Codex (xhigh) verifica — cruce de
proveedor donde más paga.
