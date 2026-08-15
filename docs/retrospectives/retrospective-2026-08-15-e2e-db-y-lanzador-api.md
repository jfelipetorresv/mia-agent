# Retrospectiva técnica — 2026-08-15 · E2E con DB, first_run capturado y dos defectos corregidos

Rama `feat/fase1-inc1-cleanup-scaffolding`, commits 8e77dc5 → 12bf5e9.

## Defecto 1 · El lanzador canónico de la API estaba roto en Windows

**Síntoma**: `python -m mia.api.run` (el camino de `scripts/start_api.ps1`) moría al
instante con `UnboundLocalError: cannot access local variable 'config'`.

**Causa raíz**: en `backend/mia/api/run.py` la rama Windows creaba
`config = uvicorn.Config(...)`; Python marca `config` como local para TODA la función,
así que la línea anterior `host = config.MIA_API_HOST` (que quería el MÓDULO `config`)
dejó de resolver. El defecto entró junto con la rama del SelectorEventLoop y nadie lo
vio porque ningún gate ejecuta ese lanzador: los tests montan la app con TestClient o
uvicorn directo.

**Corrección**: renombrado a `uv_config` (12bf5e9).

**Barrera pendiente**: un gate que arranque `mia.api.run` de verdad y espere el health.
Mientras no exista, el lanzador canónico está «roto hasta que se demuestre lo contrario».

## Defecto 2 · Mocks de jurisdicción con firma vieja: 8 checks rojos que parecían regresión

**Síntoma**: `execution/test_projects.py` 53/61 — todos los checks de «ordenamiento» y
dos del «guardián» rojos.

**Causa raíz**: la sesión 58 amplió la firma de
`research.resolve_jurisdictions_for(tenant_id)` a `(tenant_id, matter_id=None)`
(herencia real de jurisdicción). Los 5 dobles de prueba del suite conservaban la firma
de un argumento. Como `_turn_jurisdictions` es fail-soft (atrapa cualquier excepción y
degrada al código genérico), el `TypeError` no reventó: todo el flujo cayó a la rama
restrictiva y, sin jurisdicción, la cita del mensaje se omite en lugar de marcarse
(comportamiento nuevo intencional), tumbando también los checks del guardián.

**Corrección**: los 5 mocks aceptan la firma vigente; suite 61/61 (12bf5e9).

**Lección-barrera**: al cambiar la firma de una función productiva, grep de todos los
mocks/monkeypatch de ese nombre en `execution/` en el MISMO commit. Un fail-soft
convierte el error de contrato en falsos negativos lejos del punto de cambio.

## Nota de entorno (no es defecto de producto)

El `.env` de desarrollo se eliminó en la sesión anterior y era la única copia de las
contraseñas del clúster portable 55432. Recuperación: `trust` temporal en `pg_hba.conf`
(con backup y restauración a scram), contraseñas nuevas para
`postgres`/`mia_app`/`mia_curator` y `.env` regenerado con las claves del semilla de
`first_run.py`. Si un archivo con secretos se borra a propósito, el cierre debe decir
cómo regenerar cada secreto.

## Verificación

`verify.ps1 -Mode quick` VERDE 16 suites · test_rls 19/19 · test_e2e 59/59 ·
test_hitl_flow 21/21 · test_citation_seals 20/20 · test_projects 61/61 ·
test_first_run 73/73 (salida capturada). Pantallas nuevas revisadas en vivo con
Playwright (activar, motor, protección de datos, chips de contexto jurídico); P3 nuevo
anotado: div dentro de p en /configurar#conexiones (aviso de hidratación).
