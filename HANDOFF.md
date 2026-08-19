# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

# CIERRE — 2026-08-19 · sesión 46 · F4 CERRADA (instalador existe) + 23 observaciones de UX de Pipe · EMPEZAR AQUÍ

## TL;DR

Se cerró el bloque instalador: **existe un instalador funcional** y Pipe lo instaló y usó
por primera vez. De ese uso salieron **23 observaciones de UX/diseño** que son el próximo
bloque de trabajo. Están todas, con causa raíz verificada en el código y solución
propuesta, en **`memory/bitacora-feedback-ux-2026-08-19.md` — ese archivo es la fuente de
verdad del bloque UX. Leerlo completo antes de tocar `frontend/`.**

Pipe cambia de computador en este punto: este HANDOFF + la bitácora son el traspaso.

## Lo que se logró hoy

**1 · F4 (última fase del bloque instalador) — CERRADA.**
`Mia_0.3.0_x64-setup.exe`, 156.4 MB (meta ≤335 MB cumplida y medida), NSIS vía
`tauri build`, SHA-256 `453ce456ca07279a470792c4702589e85e8a96453673f0836ade9bcaf72d777e`,
manifiesto en `bundle/nsis/mia-release-manifest.json` (commit `c94594c`, `reused_payloads:false`).
Verificado: smoke de LiteLLM (health + `/v1/models` con y sin Bearer + bind solo a
`127.0.0.1` con acceso LAN rechazado), smoke de frontend en 3100 con node portable,
**primer arranque en frío sobre datos temporales limpios: 21.852 ms, exit 0** (initdb +
migraciones con el pgsql empaquetado), pgvector presente, pgAdmin excluido. Revisor
independiente sin contexto previo lo auditó y lo declaró entregable.
Pipe lo instaló y la app arrancó.

**2 · Bug de packaging arreglado (`c94594c`).** `build_backend.ps1` instalaba PyInstaller con
`--no-deps` y omitía `pyinstaller-hooks-contrib`. Sin él no existe `hook-cryptography.py`,
PyInstaller no recoge `_cffi_backend`, el primer import de `cryptography` muere en un
try/except silencioso y el reintento de PyJWT explota con *"PyO3 modules compiled for
CPython 3.8 or older may only be initialized once per interpreter process"* — el guard de
PyO3 enmascaraba el `ModuleNotFoundError` real. `mia-backend.exe` crasheaba en `--first-run`.
Se agregó el pin `2026.6` + un gate de auto-reparación para venvs viejos. No toca pins de la app.

**3 · Protección de datos: pestaña 100% muerta → arreglada (`0a0f020`, ya en main).**
Causa raíz: `lib.rs:~1400` navega la ventana a `http://localhost:3100`, que para Tauri v2 es
**origen remoto**; por endurecimiento deliberado (sin capability `remote`, sin
`dangerousRemoteUrlIpcAccess`) los orígenes remotos no reciben IPC, así que `window.__TAURI__`
nunca existe ahí y **cada botón de Protección estaba muerto desde siempre** (`restart_litellm`
de `/activar` también). No era regresión: nunca pudo funcionar como estaba diseñado.
Arreglo **sin debilitar la seguridad**: puente por esquema URI propio `mia-shell`
(`http://mia-shell.localhost`) interceptado en proceso por WebView2 — sin puerto TCP,
inalcanzable desde otro programa o la LAN — con allowlist de `Origin` exacta, solo POST y
rutas cerradas, reusando los comandos de mantenimiento existentes. Nuevo `frontend/lib/shell.ts`.

**4 · La bienvenida ya respeta el tema del abogado (`10d447e`).**
`WelcomeShell.tsx:52` forzaba `dark` + `bg-[#060606]` cableado: login, registro, `/activar` y
`/onboarding` salían **negros aunque el abogado eligiera claro**, mientras el resto de la app
sí era clara. Era la queja #1 de Pipe. Ahora usa `bg-background` + tokens del tema, y la
viñeta negra fija pasó a la utilidad `bg-vignette-welcome` con variante por tema.
Verificado con capturas de Playwright en claro y oscuro.

## ⚠️ Estado y lo que NO está verificado (no reportar como cerrado)

| Cosa | Estado |
|---|---|
| Puente `mia-shell` de Protección | Capa 1 OK (`cargo check` + `tsc` limpios). **Capa 3 PENDIENTE**: hay que reconstruir el instalador y probar los botones en la app empaquetada. Ver «Cómo verificar» abajo |
| `RuntimeHealthBanner` | **Sigue roto** por la misma causa (usa `__TAURI__.event.listen`). Migrarlo al puente `mia-shell`. Tarea abierta |
| Prueba en frío en máquina limpia | No se hizo: no hay una máquina virgen disponible. Se hizo lo más cercano posible (primer arranque sobre `%LOCALAPPDATA%` temporal limpio) |
| Firma del instalador | Sin firmar. Windows lo marca como "publicador desconocido". Funciona igual. Pipe debe registrar Azure Trusted Signing cuando quiera quitar el aviso |
| `console=True` en los dos `.spec` | Se dejó en `True` **a propósito y está documentado**: la cáscara Tauri lanza los hijos con `CREATE_NO_WINDOW` (`lib.rs:36`, ~15 puntos de spawn), así que el abogado no ve consolas. Solo se vería si alguien hace doble clic directo en `mia-backend.exe` |
| Los 22 puntos de UX restantes | Sin empezar. Ver la bitácora |

## ⚠️ Corrección importante sobre el diseño canónico

En esta sesión **describí mal** `frontend_design_spec.md` (lo llamé "dorado/cristal de lujo"),
Pipe eligió esa opción sobre esa premisa falsa, y luego lo detectó: *"no, ese no es el diseño
que habíamos establecido. Además era claro"*.

- **El canónico es** "MIA Onboarding Unificado": **Neumorfismo Pro, paleta Teal / Azul
  Oxígeno, tema CLARO y oscuro** (`CLAUDE.md` §I), que es lo **ya implementado** en
  `globals.css` (commit `f52c945`, hecho con Antigravity). **NADA dorado.**
- El commit de diseño más reciente (`ef3ed33`, "paleta monocromática negro/platino/cristal
  + isotipo octaedro 3D") **solo modificó `BrandMark.tsx`** — el logo. Nunca tocó pantallas.
  Por eso Pipe recordaba un diseño que no veía aplicado: **no se aplicó**.
- Las imágenes de referencia de Antigravity (`mia_onboarding_unified_*.jpg`) **no están en el
  repo ni en el disco**. **Pipe las tiene en otro computador y las va a traer** — cotejar el
  diseño contra ellas antes de rediseñar pantallas a gran escala.
- **Lección de proceso:** cuando la decisión es visual, el insumo debe ser visual (capturas de
  la app corriendo), no mi lectura de un `.md`. Registrada en la bitácora §4.

## Cómo continuar (sesión siguiente)

1. **Leer `memory/bitacora-feedback-ux-2026-08-19.md` completo.** Trae los 23 puntos con
   archivo, línea y causa raíz — no hace falta re-explorar el código.
2. **Esperar/pedir las imágenes de Antigravity** antes de rediseñar pantallas. Sin ellas, el
   trabajo de diseño es adivinar (ya pasó una vez en esta sesión).
3. **Verificar el puente de Protección** (capa 3) reconstruyendo el instalador — ver abajo.
4. **Migrar `RuntimeHealthBanner`** al puente `mia-shell` (misma causa raíz, tarea abierta).
5. Atacar los puntos de la bitácora. Sugerencia de orden por dependencia: primero lo que no
   depende del diseño visual (D3 Casos, D4 motor único, D7 atajos, D8 capacidades de agente,
   D9/D10 y los arreglos de copy del onboarding #7/#8/#12), y dejar para después lo puramente
   visual (#16 dashboard, #17 Configuración, #21 Conocimiento, sidebar de D2) hasta tener las
   imágenes de referencia.

## Cómo reconstruir el instalador y verificar Protección

```powershell
cd "<ruta-del-repo>\mia"
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

El script exige **checkout limpio** (rechaza el release si hay cambios sin commitear) y
reconstruye los 3 payloads + el bundle NSIS. Tarda ~25-40 min. Con `-SkipPayloads` reusa
`packaging/dist/` existente, pero **solo funciona si esos payloads se construyeron desde un
checkout limpio** (si no, aborta: "payload construido desde fuentes sucias").

Luego, en la app instalada: **Configuración → Protección**. "Guardar llave" debe reportar la
llave escrita en `Documentos\Llave-de-recuperacion-Mia.txt`; "Ya la guardé" limpia el aviso;
"Crear copia ahora" reporta copia verificada; "Recuperar…" lista los `.mia-backup`.
**Re-chequeo de seguridad obligatorio** desde DevTools de esa ventana: `window.__TAURI__ === undefined`
debe seguir siendo `true`, y un `fetch("http://mia-shell.localhost/maintenance/status", {method:"POST"})`
desde **cualquier otro origen** (una pestaña normal de Chrome) debe fallar.

## Trampas del entorno (le costaron horas a esta sesión)

- **Ruta del proyecto:** `CLAUDE.md` §A y §G y `desktop/orchestration.json` todavía dicen
  `D:\Inteligencia Artificial\Mia-Super Agent\mia`. **Esa carpeta ya no existe.** En este equipo
  el repo estaba en `D:\Codex\Mia-Super Agent\mia`. Al clonar en el equipo nuevo, la ruta será
  otra vez distinta: **corregir esas referencias** (o mejor, hacerlas relativas).
- **Binarios portables NO están en el repo** (correctamente, por peso) y hay que
  reprovisionarlos en cada equipo antes de poder construir el instalador:
  - **Node portable** v22.23.1 (versión fijada en `packaging/node-version.txt`).
  - **PostgreSQL 16 portable** (binarios de EDB, ~300 MB comprimido) **+ pgvector 0.8.0
    compilado contra él** (`nmake /F Makefile.win` con las Build Tools de VS, `PGROOT` apuntando
    al pgsql portable). Sin `lib\vector.dll` el build del instalador **aborta en duro**.
  - Ambos vivían en `<workspace>\tools\` (fuera de `mia\`).
- **Rust/Tauri:** hace falta el toolchain de Rust (`rustup`) + VS Build Tools. `desktop/README.md`
  los daba por instalados; en este equipo no estaban. `npm install` en `desktop/` instala
  `@tauri-apps/cli`. Tauri descarga NSIS solo en el primer `tauri build`.
- **Smart App Control de Windows** bloquea los `.exe` recién compilados sin firma
  (*"bloqueado por la directiva de Device Guard"*), y el smoke post-build falla con eso. Pipe lo
  **desactivó manualmente** en este equipo (Seguridad de Windows → Control de aplicaciones y
  navegador → Smart App Control → Desactivado). **Es irreversible sin reinstalar Windows.**
  En el equipo nuevo puede volver a aparecer: la alternativa limpia es firmar los ejecutables.
- **Dependencias del frontend desactualizadas:** tras traer 252 commits, `build_frontend.ps1`
  falló con `error: unknown option '--webpack'` hasta correr `npm install` en `frontend/`.
- **`.claude/launch.json`** (para levantar el dev server desde el agente) está gitignorado —
  hay que recrearlo en el equipo nuevo. Contenido: `npm run dev` en `cwd: frontend`, puerto 3100.

---

# CIERRE — 2026-08-18 · Mapa al día + mock del swarm alineado a la firma real · EMPEZAR AQUÍ

## Resultado de esta sesión

`CLAUDE.md` ya describía el producto del 18 ago 2026; este HANDOFF no. Quedó alineado.
No se inventó servidor MCP. `Plan/Plan.md` vive en el workspace padre (fuera de
`mia-agent`) y no entra en este PR.

HEAD de trabajo: rama `feat/fase1-inc1-cleanup-scaffolding`. El mapa de abajo es el
contrato vigente — no reabrir «5 pantallas» ni «LiteLLM primero».

## Mapa vigente (18 ago 2026)

- **Packs fail-closed.** Un pack vacío o un handoff roto no finge cotejo verde: cero
  fuentes ≠ preflight OK. El recorte de drafts conserva la matriz. Migración
  `059_packs_handoff_cost_status.sql` (handoffs, fact-pack por hash, `cost_status`
  honesto: medido / estimado / no_medida). Gate: `execution/test_packs_preflight.py`.
- **HITL por hash + tesis one-shot.** Approve/edit exigen `draft_hash` del borrador
  actual (409 si cambió; 422 si falta huella o attest). Cambiar la matriz en revisión
  autoriza UNA pasada extra de redacción+verificador (`selection_redraft_used`), no
  el bucle automático draft↔gate.
- **Packet destilado.** El cruce recibe hash / pasaje / locator `[doc n]`, no el dump
  de investigación. Vive en `metadata.source_packet`.
- **MCP vacío honesto.** Sin servidores en `tenant_settings.config['mcp']['servers']`
  el despacho ve un dict vacío. Catálogo curado; `resolve_server` es fail-closed.
  No hay servidor MCP de producto que inventar para un test rojo.
- **CI verde (sin bajar gates).** SHA de migraciones sin psycopg; checkpointer en el
  job legal; JWT_SECRET ≥ 32 caracteres; stubs de Tauri; `verify.ps1` usa el Python
  de PATH (`MIA_VERIFY_PYTHON`) y no usa `WindowStyle` en Ubuntu; el catálogo quick
  corre junto a Postgres en Ubuntu; el blindaje BatBadBut del CLI se afirma solo en
  Windows. Commits 56631c8 → 7ef8709 sobre el cierre del 15.
- **Cron suggestions.** El job `generate_suggestions` alimenta
  `GET /api/automations/suggestions` (consent-first; el abogado acepta o descarta).
- **Telegram en el lifespan.** `start_bridge_if_configured()` arranca con la API si
  hay token. No es un proceso suelto obligatorio para que el producto viva.
- **Agent Hub.** Cinco conectores (investigación, documentos, automatización,
  escritorio, navegación). Solo `invocation_ready` si el binario está en PATH y
  `--help` confirma los flags. Si no, razón honesta — nunca `[VERIFICAR]` en el
  catálogo.
- **Router LLM.** `agent/llm.py` con política por defecto `quality_adaptive`.
  LiteLLM es proxy opcional de respaldo, no el camino primero del abogado.
- **Frontend.** No son «5 pantallas». Hay asunto, revisión HITL, memoria,
  configuración (conexiones, ayudantes, protección), automatizaciones, misiones y
  sala de estrategia. Login JWT. ~14 routers `/api`.

## Gate de esta sesión

`execution/test_research_swarm.py`: los mocks de `resolve_jurisdictions_for` y
`citation_patterns_for` tenían un solo argumento; el grafo llama
`(tenant_id, matter_id)` desde la sesión 58 y el fail-soft de `_turn_jurisdictions`
tragaba el `TypeError` (misma clase que el arreglo de `test_projects.py` el 15 ago,
regla 78). Firmas alineadas a las reales, incluido el stub de `resolve_jurisdictions`
del check de dedup. Suite 21/21 PASS. No se inventó servidor MCP: el gate vacío
bloquea y el turno sigue.

## Pendientes que deja esta sesión

Siguen abiertos los del 15 ago (no se tocaron):

- **P3**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev).
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o
  tramo rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- **API propia por instalación** (decisión de Pipe). Benchmark solo por decisión de
  negocio. Distribución sin prometer ≤335 MB.

PRIMERA TAREA del próximo arranque con entorno completo: la misma del 15 — E2E con
DB, `test_first_run.py` con salida capturada, y revisar en vivo las pantallas nuevas
si el entorno lo permite. No reabrir el mapa de producto.

---

# CIERRE — 2026-08-15 · E2E con DB verde, first_run capturado y pantallas revisadas en vivo

## Resultado de esta sesión (commits 12bf5e9 + cierre, pusheados)

Los tres puntos de la «primera tarea» del cierre anterior quedaron cerrados con evidencia:

1. **`test_first_run.py` VERDE 73/73 con salida capturada** (exit 0). Ya cuenta como gate.
2. **E2E con DB, todo verde**: test_rls 19/19 · test_e2e 59/59 · test_hitl_flow 21/21
   (el riesgo #86 queda re-verificado: la suite pasa con DB) · test_citation_seals 20/20 ·
   test_projects 61/61 · `verify.ps1 -Mode quick` VERDE 16 suites (14,3 s).
3. **Pantallas nuevas revisadas en vivo** (Playwright + `seed_despacho_demo.py`):
   /activar con «Calidad jurídica adaptativa» RECOMENDADO y el copy del plan Max en
   «Mi suscripción»; selector de motor en Conexiones con «Codex en este equipo (no
   disponible en este equipo)» deshabilitado con su razón; chips «Contexto jurídico
   [General]» pintando lo efectivo; tarjeta «Recuperar desde una copia» con su copy y el
   aviso de aplicación al reinicio. En dev /activar redirige a /onboarding
   (`instalado=false`, correcto); para verla se interceptó `/api/welcome/status`.

Dos defectos REALES corregidos en 12bf5e9:

- **El lanzador canónico de la API estaba roto en Windows**: en `backend/mia/api/run.py`
  una local `config = uvicorn.Config(...)` sombreaba el módulo `config` y
  `python -m mia.api.run` (el camino de `start_api.ps1`) moría con `UnboundLocalError`.
  Ningún gate lo ejecutaba. Pendiente: gate que lo arranque de verdad (regla 79).
- **8 checks rojos de test_projects que parecían regresión**: los 5 mocks de
  `resolve_jurisdictions_for` tenían la firma vieja de 1 argumento (la sesión 58 la
  amplió a `(tenant_id, matter_id)`); el fail-soft de `_turn_jurisdictions` tragaba el
  `TypeError` y degradaba a la rama restrictiva. Mocks actualizados (regla 78).

**Entorno reconstruido**: el `.env` eliminado el 2026-08-14 era la única copia de las
contraseñas del clúster portable 55432. Se resetearon (`trust` temporal en `pg_hba.conf`
con backup, restaurado a scram) las contraseñas de `postgres`/`mia_app`/`mia_curator` y
se regeneró el `.env` con las claves del semilla de `first_run.py` (regla 80). Las 56
migraciones se re-aplicaron idempotentes (3 fallos esperados: constraints viejos
superados por migraciones posteriores; los vigentes quedaron intactos).

## Pendientes que deja esta sesión

- **P3 nuevo**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev). Ubicar y corregir.
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o tramo
  rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- El bloque grande sigue siendo el del cierre 2026-08-14: **API propia por instalación**
  (decisión de Pipe), benchmark solo por decisión de negocio, y distribución sin
  prometer ≤335 MB.

Retrospectivas: técnica en `docs/retrospectives/retrospective-2026-08-15-e2e-db-y-lanzador-api.md`;
de sesión en `Pipe-OS/01-operacion/retrospectivas/retrospective-2026-08-15-002-mia-e2e-db-first-run-pantallas.md`.
Reglas nuevas 78-81 en `APRENDIZAJES.md`.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---
