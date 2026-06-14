# Mia · SOP — Aislamiento multi-tenant por RLS
# Cómo Mia impide que un despacho (tenant) vea datos de otro.
# Última actualización: 2026-06-14

## Principio
Cada fila de datos de cliente lleva `tenant_id uuid`. PostgreSQL Row-Level
Security (RLS) filtra automáticamente por el tenant activo, fijado en el GUC
de sesión/transacción `app.tenant_id`.

## Reglas no negociables
1. **La app NUNCA se conecta como superusuario.** Los superusuarios y los
   roles con `BYPASSRLS` IGNORAN las políticas RLS. La app usa el rol
   `mia_app` (LOGIN, NOSUPERUSER, NOBYPASSRLS). El superusuario `postgres`
   se usa SOLO para migraciones (`execution/init_db.py`).
2. **Fail-closed.** `app_current_tenant()` =
   `NULLIF(current_setting('app.tenant_id', true), '')::uuid` → devuelve NULL
   si el GUC no está fijado → las políticas no devuelven ninguna fila.
   Sin contexto de tenant = 0 datos.
3. **ENABLE + FORCE ROW LEVEL SECURITY** en toda tabla con `tenant_id`.
4. Política `ALL` con `USING` y `WITH CHECK` = `tenant_id = app_current_tenant()`.
   El `WITH CHECK` impide INSERT/UPDATE que apunten a un tenant ajeno.

## Flujo en runtime
- El JWT del usuario trae el claim `tenant_id`.
- `api/middleware.py` lo valida y lo pone en `request.state.tenant_id`
  (rutas abiertas: `/health`, `/docs`, `/openapi.json`, `/redoc`).
- Los handlers usan `db.pool.tenant_connection(tenant_id)`, que ejecuta
  `SELECT set_config('app.tenant_id', <id>, true)` (SET LOCAL) dentro de una
  transacción → RLS queda activo solo para esa request, y se limpia al cerrar.

## Verificación (GATE)
`execution/test_rls.py` DEBE pasar **12/12**. Conecta como `mia_app` y prueba:
- `mia_app` no es superusuario ni tiene BYPASSRLS (primera aserción).
- Fail-closed: sin GUC, 0 filas.
- Tenant A no ve nada de B vía SELECT/UPDATE/DELETE (rowcount 0).
- INSERT con `tenant_id` de B bajo GUC=A → rechazado (WITH CHECK).
- Tenant B aislado de A.
HALT si falla: no se avanza (CLAUDE.md §G).

## Lección aprendida (Sesión 2 · 2026-06-12)
El error más fácil y más grave es dejar que la app use el rol `postgres`:
RLS se vuelve decorativo porque el superusuario lo ignora. Por eso
`init_db.py` crea `mia_app` explícitamente NOSUPERUSER/NOBYPASSRLS y
`test_rls.py` lo verifica como **primera** aserción antes de cualquier otra.

## Corpus compartido (SAT-Graph) vs datos por-tenant  (Módulo 3a · decisión #16)
No todo dato lleva `tenant_id`. El **SAT-Graph** (`legal_norms`, `norm_relations`,
`jurisprudence`) es **corpus jurídico público COMPARTIDO** entre todos los despachos: las
normas y sentencias de Colombia son las mismas para todos. Es la **excepción documentada**
al patrón por-tenant de las reglas de arriba.

Diferencias frente a las tablas por-tenant:
- **Sin `tenant_id`.** No hay columna de aislamiento; el corpus es uno solo.
- **RLS habilitado, política ABIERTA.** `ENABLE ROW LEVEL SECURITY` + una sola policy
  `USING (true) WITH CHECK (true)`. No se usa `FORCE` (el dueño es `postgres`, superusuario).
- **Lectura pública, escritura por GRANT.** Cualquier conexión `mia_app` lee el corpus; la
  escritura (curaduría) se restringe a `mia_app` vía `GRANT` — no hay otro rol
  no-superusuario que pueda escribir.
- **Por qué `WITH CHECK (true)` y no solo una policy SELECT:** bajo `NOBYPASSRLS`, una tabla
  con RLS habilitado y sin política permisiva para el comando RECHAZA la escritura. Sin
  `WITH CHECK (true)`, el propio `mia_app` no podría ingerir el corpus. La policy abierta es
  deliberada y segura: el corpus no tiene nada que aislar entre tenants.
- **Acceso desde el código:** `SATGraph` usa `pool.connection()` (sin fijar `app.tenant_id`).
  Esto NO debilita el aislamiento: las tablas por-tenant siguen **fail-closed** sin GUC
  (0 filas); una conexión sin-GUC solo ve el corpus compartido. **NUNCA** usar
  `pool.connection()` para datos por-tenant.

Regla: una tabla nueva o lleva `tenant_id` + política por-tenant (regla general), o es corpus
compartido con política abierta + justificación escrita (esta sección). No hay terceras
opciones sin decisión registrada.
