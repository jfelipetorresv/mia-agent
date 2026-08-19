# F0 — Preflight mínimo: primera evidencia + tope de gasto

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`, sección "F0".
Estado del plan: adelgazado por refutación de Codex — nada de organización del repo puede retrasar
la primera evidencia real contra un modelo vivo.

## Objetivo
Conseguir la primera señal real del riesgo #76 (ningún gate corre contra un modelo real) con tope de
gasto fail-closed, y en paralelo dejar el repo organizado (specs, hooks, higiene) sin tocar código de
producto.

## Camino crítico (bloquea F1) — NO es este frente
- ~~Push de los commits~~ — **RESUELTO**: Pipe aprobó y el push ya se ejecutó; `origin/feat/fase1-inc1-cleanup-scaffolding`
  está en `c19c680` == `HEAD` (0 commits por delante, verificado con `git rev-list --count
  origin/feat/fase1-inc1-cleanup-scaffolding..HEAD`). Pendiente: el merge/PR de esa rama a `main`.
- Telemetría de coste + tope fail-closed en `execution/run_eval.py` + `backend/mia/eval/harness.py`:
  tokens/coste/duración por llamada; tope por corrida, por sesión (USD 30) y global, con reserva
  para cierre limpio y corte ANTES de exceder. Prueba de mutación: una corrida que lo excede corta.
- F0.5 — Smoke vertical (USD 5): una corrida real política "nube" + expediente sintético, punta a
  punta. Confirma plomería (despacho efímero, candado de datos, scoring, coste).
- Desdeclarar Modo A (Docker) YA en `CLAUDE.md`/docs — capacidad inexistente es deuda comercial.

## Esta spec cubre — Retrofit de organización (FRENTE D, ESTA SESIÓN)
Del impulso `/new-proyects`, sin tocar código de producto:

1. **Estructura `specs/`**: `specs/todo/`, `specs/done/`, `specs/handoffs/` con `.gitkeep` donde
   queden vacíos. — **HECHO en esta sesión.**
2. **Materializar el plan maestro como specs ejecutables**: una spec por fase (esta serie de 8
   archivos, prefijo numérico). — **HECHO en esta sesión** (el plan queda como norte; las specs son
   las órdenes de trabajo para `/EA-build → /EA-validate → /EA-review → /EA-commit`).
3. **`.mcp.json`** con servidor Playwright (para los recorridos E2E de F3). — **HECHO en esta
   sesión.**
4. **`.claude/settings.json`**: hooks damage-control a nivel de proyecto. **Diagnóstico verificado
   en esta sesión**: existe una versión GLOBAL en `C:/Users/USER/.claude/settings.json` con hooks
   `PreToolUse` (Bash → `bash-tool-guard.py`, Edit → `edit-tool-guard.py`, Write →
   `write-tool-guard.py`) y `PostToolUse` (Bash → `bash-output-validator.py`), todos apuntando a
   `C:/Users/USER/.claude/hooks/damage-control/*.py` sin restricción de directorio — **ya cubren
   este repo sin duplicación**. `patterns.yaml` bloquea `rm -rf`, `git push --force`/`-f`,
   `git reset --hard`, `DROP/TRUNCATE/DELETE FROM sin WHERE`, etc., y protege `.env`/`*.env`/`*.key`
   contra escritura y borrado (`readOnlyPaths`/`noDeletePaths`), aunque los deja legibles (necesario
   para operación legítima). **Decisión: documentar la reutilización en `.claude/settings.json` del
   proyecto en vez de duplicar la lógica** (archivo nuevo, minimalista, con nota explícita).
5. **`APRENDIZAJES.md`** en la raíz: lecciones ya constatadas en el repo (de
   `memory/bugs-and-risks.md` y retrospectivas) convertidas en regla accionable, consumido por
   `/EA-apply-learnings` al cierre de cada fase. — **HECHO en esta sesión.**

## Diagnóstico sin actuar (reportar, NO ejecutar) — HECHO en esta sesión
- **`.git` fantasma** en `D:\Inteligencia Artificial\Mia-Super Agent\.git` (directorio PADRE de
  `mia/`): NO es un repositorio git funcional. `git status`/`git log` fallan con "not a git
  repository" porque solo contiene `info/exclude` (301 bytes, patrones de runtime de Claude Code) —
  no hay `HEAD`, `refs/`, `objects/` ni `config`. Total 1 KB. No tiene commits ni remoto porque no
  es un repo real; probablemente quedó de un `git init` que nunca se completó o de una copia parcial.
  **Recomendación: es seguro borrarlo** (no representa historia real ni trabajo recuperable), pero
  **NO se borra aquí** — es irreversible y la decisión es de Pipe. El repo git real y funcional del
  proyecto vive en `mia/.git` (rama `feat/fase1-inc1-cleanup-scaffolding`). **Actualización: el push
  ya se hizo** — `origin/feat/fase1-inc1-cleanup-scaffolding` está en `c19c680` == `HEAD` (0 commits
  por delante, verificado con `git rev-list --count origin/feat/fase1-inc1-cleanup-scaffolding..HEAD`).
  Lo que sigue pendiente es el merge/PR de esa rama a `main`.
- **Ramas mergeadas podables** (evidencia: `git branch --merged main` / `git branch -r --merged
  main`, corridos en `mia/`):
  - Local: solo `main` aparece mergeada a sí misma — ninguna rama local aparte de `main` está
    mergeada a `main` hoy (`feat/fase1-inc1-cleanup-scaffolding`, `feature/robustecimiento-sin-aws`,
    `research/cory-audit`, `backup/local-fases-20260707` NO están mergeadas).
  - Remoto: `origin/feat/cp-c4b-wizard-onboarding`, `origin/feat/cp-p1-motor-vigilancia`,
    `origin/feat/cp-s1-cuarentena-universal`, `origin/feat/cp-s2-secretos`,
    `origin/feat/cp-s3-endurecimiento`, `origin/feat/cp6-una-sola-voz`,
    `origin/feat/cp9-equipo-especialistas` SÍ aparecen mergeadas a `origin/main` — son candidatas
    reales a poda remota.
  - **NO se borró ninguna** — solo se lista con evidencia; podar ramas remotas es decisión de Pipe
    (afecta a `origin`, potencialmente compartido).
- **`Abrir Mia.cmd` (raíz de `mia/`) NO arranca la base de datos portable** — CONFIRMADO leyendo la
  cadena completa: `Abrir Mia.cmd` → `scripts\start_all.ps1` (`-NoProfile -ExecutionPolicy Bypass`)
  → `start_all.ps1` solo invoca `Start-Part` para tres servicios: `scripts\start_litellm.ps1`
  (puerto 4000), `scripts\start_api.ps1` (puerto 8000) y `scripts\start_frontend.ps1` (puerto 3100).
  **No hay ninguna llamada a `pg_ctl` ni a nada que levante Postgres/pgvector en el puerto 55432.**
  Si la DB portable no está corriendo ya, `start_api.ps1` (uvicorn) fallará o se quedará esperando
  conexión. Esto coincide con lo que ya documenta `docs/trampas-entorno-windows.md` (clúster portable
  en el puerto 55432, arranque manual con `pg_ctl`). **El arreglo es de F5** ("Arreglar el bug del
  minuto cero" — el plan maestro ya lo tiene listado ahí explícitamente); esta spec solo documenta el
  hallazgo, no lo corrige.

## Gates
Ninguno de código se toca en este frente — no aplica HALT de producto. Verificación de este frente:
- `.mcp.json` parsea como JSON válido.
- `.claude/settings.json` parsea como JSON válido y no rompe el `settings.json` global (no lo toca).
- Las 8 specs existen con prefijo numérico correcto y contenido ejecutable (objetivo, entradas,
  archivos críticos, pasos, salida medible, gates — copiados del plan maestro, no resumidos a bulto).
- `APRENDIZAJES.md` existe y cada entrada es una regla, no una anécdota.

## Salida medible de F0 completo (del plan maestro, referencia — el resto lo hace otro frente)
Smoke vertical completado con coste registrado; el tope corta (demostrado); push hecho o diferido
explícito; Modo A desdeclarado; pista paralela con docs corregidos bajo revisión adversarial y hooks
probados (un `rm -rf` de prueba bloqueado — ya lo cubre el hook global, ver diagnóstico arriba).
