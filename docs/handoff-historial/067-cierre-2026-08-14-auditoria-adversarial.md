# CIERRE — 2026-08-14 (tarde) · Auditoría adversarial integral post-b93d9ab: 4 P0 corregidos

Archivado desde `HANDOFF.md` el 2026-08-18 (regla: solo vigente + anterior).

## Qué encontró y cerró la auditoría (informe completo en la conversación; barreras en los gates)

Cuatro P0, todos corregidos fail-closed con gate que reproduce la falla:

1. **El cotejo de SELLOS respaldaba por substring**: un sello de «Ley 80» resolvía como
   sellada la cita inventada «Ley 800 de 1993» y podía saltar el gate LLM. Ahora coteja
   por piezas (`_tokens_match`), la regla que ya cerraba esta clase para cita↔fuente.
   Gate: bloque 1-bis de `test_citation_seals.py` (parte pura verde; la parte DB corre en CI).
2. **4 migraciones históricas editadas (05c8f8c) bloqueaban el upgrade**: el ledger de
   checksums de `db_bootstrap` es fail-closed y toda instalación existente habría quedado
   sin arrancar al actualizar a 0.3.0. Revertidas al contenido registrado; el vocabulario
   vive en la migración nueva 058; `config/migration_shas.json` congela cada sha
   (gate: `test_migration_contracts.py`, ahora con checks de inmutabilidad y `--sellar`).
3. **El aviso de costo afirmaba «crédito de pago» al caer a mia-local (gratis)** — un cobro
   inventado. Excluido en `aviso_cambio_de_motor`; y la pantalla de activación había perdido
   la recomendación del plan Max (petición expresa de Pipe, s52) — restaurada compatible con
   el gate 10c de model_policy. Gate: `test_cambio_de_motor_aviso.py` 46/46.
4. **`test_restore_cli.py` y `test_production_reachability.py` (estilo pytest) salían verdes
   sin correr una aserción** bajo el runner de scripts. Ahora se autoejecutan con pytest
   (3+2 aserciones reales verdes); pytest declarado en `backend[full]`.

P1/P2 también corregidos: marca Tauri de Codex solo del PROCESO (un `.env` ya no la
enciende; checks 0f/0g funcionales), conector Codex del Agent Hub con el aislamiento del
proveedor productivo (stdin + efímero + sandbox read-only + tools apagadas), timeout de
`cli-*` sin reintentos dentro del alias (eran hasta 4×300 s por nodo en cadenas de un
alias), notas `{vault}/Mia/` excluidas como respaldo de citas (bucle de realimentación;
mutación en `test_projects.py`), dedupe del aprendizaje durable con `matter_id` (dos
asuntos con final idéntico aprenden ambos), re-cotejo del banco de quemadas al sellar
(ventana quemar↔aprobar), 413 de Codex clasificado CONTEXT_TOO_LONG, veredicto del
revisor solo con «APTO» limpio, los 409 del backend llegan al abogado (plainMessage en
revisar/Conexiones), copy honesto del 409 de Codex, catálogo quick sin duplicados y con
2 gates offline nuevos, `test_citation_seals` en el job de CI con Postgres, y 3 tests
obsoletos actualizados al contrato vigente (skill_improver, connector_hardening,
citation_seals DB con contrato hash-bound).

## Verificación de este cierre

`verify.ps1 -Mode quick` VERDE 16 suites (16,3 s) · jurisdicción 29/29 · sentence_report
47/47 · codex provider 17/17 · citas_quemadas 20/20 · cambio_de_motor 46/46 ·
connector_hardening 37/37 · migration_contracts 6/6 · compileall limpio · `tsc --noEmit`
limpio. Sin `.env`: test_rls/test_e2e/test_hitl_flow/test_citation_seals(DB)/test_projects
NO ejecutables localmente (van en CI con Postgres). `test_first_run.py` sigue SIN contar
como verde (pendiente #2 del cierre anterior). No se llamó a ningún modelo ni se creó
credencial alguna; `validation/provider-benchmark-full-2026-08-14/` intacta.

## Cierre de la sesión (regla 11)

Estado al cerrar: repo limpio, 4 commits de esta sesión (4084300 → a23f386) pusheados.
Última verificación: `verify.ps1 -Mode quick` VERDE 16 suites · model_policy 58/58 ·
cambio_de_motor 46/46 · restore_cli 4/4 · `cargo check` limpio · compileall y `tsc
--noEmit` limpios. Ajuste final tras el cierre: `harvest_lessons` (cosecha en background) pasó de
`task="main"` a `task="curator"` — con el default nuevo habría gastado Opus por cosecha
(commit 69fa24b, pusheado). PRIMERA TAREA del próximo arranque con entorno completo:
E2E con DB, `test_first_run.py` con salida capturada y revisar en vivo las pantallas
nuevas (activar, Ajustes/motor, chips de jurisdicción, Recuperar desde una copia).
Ningún trabajo queda corriendo en background. Retrospectiva:
`Pipe-OS/01-operacion/retrospectivas/retrospective-2026-08-14-auditoria-adversarial-mia.md`.

Qué revisar en pantalla cuando haya entorno con DB: la tarjeta «Calidad jurídica
adaptativa» y «Mi suscripción» en /activar (copy nuevo), el selector de motor en Ajustes
(Codex deshabilitado con razón si no está), los chips de jurisdicción del asunto (pintan
lo efectivo) y la tarjeta «Recuperar desde una copia» en Protección de datos.
Comportamiento esperado del restore: preparar → cerrar y reabrir Mia → arranca con los
datos de la copia y una copia previa del estado anterior en la carpeta de respaldos.
Bugs conocidos sin cambio: riesgo #86 (test_hitl_flow, sin poder re-verificar sin DB) y
los P2 listados abajo.

---

## Pendientes que deja la auditoría — ACTUALIZADO tras la 2ª pasada (mismo día)

CERRADOS en la 2ª pasada (commit posterior a 4084300): la traza lleva el desenlace
EFECTIVO (el ledger corre ANTES de capturar; sin final registrado la traza dice
`verification_required` y wiki/banco de oro/skills la ignoran — checks nuevos en
`test_p0_legal_ledger.py`); jurisdicción hereda de VERDAD (sin selección se guarda `[]`,
el GET expone `jurisdictions_effective`, los chips pintan lo efectivo y el primer clic ya
no estrecha — check en `test_matter_jurisdictions.py`); una señal de aprendizaje
`failed`×5 se reencola al re-encolarse la misma señal (check en `test_durable_learning.py`);
`--effort` VERIFICADO contra `claude --help` real 2026-08-14 (low/medium/high/xhigh/max,
coincide con `_ACCEPTED_EFFORTS`); `capabilities` ya tiene consumidor (Ajustes deshabilita
Codex no disponible y muestra la razón — check 10c-bis en `test_model_policy.py`); el
restore quedó documentado con su sintaxis real en
`docs/guia-primera-instalacion-y-onboarding.md`.

DECISIONES DE PIPE (mismo día, aplicadas en el 3er commit): (1) `quality_adaptive` ya no
es «Sonnet estándar, Opus excepcional»: el más inteligente PIENSA Y ORQUESTA — main y
legal_analysis van en Opus/xhigh primero con degradación dentro de la misma suscripción a
Sonnet; la ejecución dirigida (hechos/investigación/redacción/verificación/edición) en
Sonnet y lo mecánico en Haiku (checks 1g/1g-bis, 57/57). (2) «Mia aprende lo que
aprueba»: aprobar con cambios (editing) también encola wiki y skills — los 4 jobs van
juntos bajo final_ready (check en test_durable_learning). (3) Botón de recuperación:
la restauración se PREPARA desde Protección de datos (lista de copias + confirmación por
nombre de base) y se APLICA en el próximo arranque vía `--maintenance startup` (servicios
apagados = la condición segura de pg_restore); fail-open del arranque si falla (marca
`.failed`, aviso en la UI). Comandos Tauri maintenance_list_backups/stage_restore;
acciones CLI stage-restore/list-backups; tests en test_restore_cli (4 passed);
`cargo check` limpio. (4) El default de política es
`quality_adaptive` también en el backend (config + fallback de llm): un tenant que nunca
guarda la pantalla queda en la política que la pantalla le mostró. Gate 10b-bis en
test_model_policy (58/58); el gate del breaker fija ahora 'suscripcion' explícita.
Con esto, CERO decisiones de producto pendientes de este bloque.

- **P2**: `capabilities` del backend sin lector en frontend; `legal_export_events` sin
  lector; `anydoc_available()` muerto justo donde haría falta; quemar no retira finales ya
  emitidos (ledger append-only sin retractación); techo del guardián de docs fantasma
  tomado del mensaje del usuario; render docx no ligado al hash; `verify.ps1 -Mode full`
  con ruta absoluta de esta máquina; jurisdicción no llega a la memoria durable (global al
  tenant); test_provider_benchmark ejecuta CLI real (solo pasa aquí).
- **Codex/OpenAI API y Claude API por instalador**: NO existen como ruta productiva (cero
  restos de OPENAI_API_KEY; `nube` sí usa ANTHROPIC_API_KEY por decisión #27). La lista
  concreta de 7 piezas para el alta por instalador quedó en el informe de la auditoría.
