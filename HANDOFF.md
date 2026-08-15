# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

# CIERRE — 2026-08-14 (tarde) · Auditoría adversarial integral post-b93d9ab: 4 P0 corregidos · EMPEZAR AQUÍ

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
--noEmit` limpios. Ningún trabajo queda corriendo en background. Retrospectiva:
`Pipe-OS-operacionetrospectivasetrospectiva-2026-08-14-auditoria-adversarial-mia.md`.

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

---

# CIERRE — 2026-08-14 · Jurisdicción, proveedores y evaluación: correcciones cerradas; API por instalador pendiente

## Resultado de esta sesión

Mia ya separa el dato aportado por el abogado de la evidencia que autoriza una cita
generada: sin jurisdicción configurada, una referencia repetida desde el mensaje se
omite del borrador y queda trazada, pero el mensaje original no se altera. La ruta
configurada conserva el marcado clásico. Gate: `execution/test_jurisdiction_omission.py`
29/29 y `execution/test_sentence_report.py` 47/47.

La selección de proveedor dejó de gastar o cambiar datos de asunto en silencio:
calidad estándar inicia Sonnet, Opus/Max solo entra por escalada excepcional y las
políticas de membresía fallan claro para `main` y tareas jurídicas. Codex es una
política explícita de membresía local: no es el alias de evaluación, no usa API ni
cae a Claude/local. Gate: `execution/test_model_policy.py` 55/55.

Codex por membresía está limitado a la app Tauri del titular: Tauri inyecta en cada
arranque/reinicio una marca efímera, host loopback y CORS local; el bootstrap no
persiste esas marcas. Un servidor o reverse-proxy ordinario queda apagado; esto NO
es una frontera contra el administrador del mismo host. Gate adversarial:
`execution/test_codex_production_provider.py` 15/15. Pasaron también compilación
Python, lint/typecheck frontend, `cargo check` Tauri y `git diff --check`.

Se eliminó el `.env` local con configuración personal. No se hicieron llamadas a
modelos ni se guardó una clave nueva. La corrida de benchmark `validation/provider-
benchmark-full-2026-08-14/` fue detenida por Pipe: es evidencia parcial, no una
comparación ni una certificación, y no debe borrarse ni usarse en comunicación comercial.

## Próximo bloque — no asumir, ejecutar en este orden

1. **API propia por instalación (decisión ya tomada por Pipe):** construir en el
   instalador el alta separada de Claude API y Codex/OpenAI API. Cada computador
   aporta y guarda su propia credencial local ignorada; no reutilizar claves de
   desarrollo. Antes de cualquier llamada OpenAI, aplicar el gate de credenciales
   seguro y pedir/recibir la clave de esa instalación.
2. **Cierre de instalación:** correr `execution/test_first_run.py` hasta obtener
   exit/result capturado y la colección rápida/CI desde entorno limpio. Esta sesión
   no cuenta ese gate como verde porque la ejecución larga terminó sin salida capturable.
3. **Benchmark solo por decisión de negocio:** definir qué afirmación se quiere
   demostrar, tiempo, presupuesto y criterio; entonces usar el runner durable en
   carriles separados. No reanudar la matriz actual automáticamente.
4. **Distribución:** no prometer aún la meta de instalador ≤335 MB; requiere build
   limpio medido. Mantener la variante Compact/Offline y sus gates existentes.

La retrospectiva técnica está en
`docs/retrospectives/retrospective-2026-08-14-proveedor-jurisdiccion-y-evaluacion.md`;
las reglas permanentes se absorbieron en `APRENDIZAJES.md`.

---

# CIERRE — 2026-08-12 (sesión 57) · Auditoría integral del harness aplicada a Mia · EMPEZAR AQUÍ

Se ejecutó el plan integral sin copiar la implementación reservada: informe público,
trazabilidad privada, catálogo y comando único de verificación, CI, enrutamiento por función,
contexto progresivo, migraciones reejecutables y poda del runtime aparente sin consumidores.

La metodología jurídica fija bajó de ~1.744 a 363 tokens y el system del borrador de ~3.255
a 1.171, conservando 66/66 invariantes. Next pasó de 14 a 16.3.0 y React a 19.2.8: build de
14 rutas, auditoría 0 vulnerabilidades, empaquetado 24/24, UX 41/41, memoria 27/27 y auth
21/21. Playwright confirmó navegación hidratada Login→Registro; el HMR del entorno dev dejó
avisos WebSocket, pero producción compila y empaqueta. El lint quedó limpio y el instalador
produjo y probó un paquete portable de 131,9 MB con su Node propio y cabeceras seguras.

La pasada completa recorrió 142 suites en 629 s y expuso seis contratos de prueba obsoletos;
se corrigieron y las seis suites quedaron verdes. La pasada posterior terminó 142/142 en 623 s.
El verificador reintenta una sola vez el cierre transitorio del pool de SAT-Graph; una segunda
falla conserva el bloqueo. Pendiente evolutivo: reducir el tiempo de la pasada completa. No
borrar `mia-cory-audit-worktree`, `tools`, `Lexia-Vault` ni los prototipos externos sin respaldo.

Commits de esta sesión: ver `git log` inmediatamente bajo este cierre.

**Continuación 2026-08-12 · instalador y onboarding listos para prueba interna:** se generó
`desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe` (447 MB,
SHA-256 `80748B644C7828577093EE2BF15E09AA5E22F2699760474556F2A33BD5BFF89E`).
Pasaron 30/30 checks de ensamblaje y 78/78 del onboarding y configuración. La guía para
Pipe está en `docs/guia-primera-instalacion-y-onboarding.md`. El ejecutable **no está
firmado**: apto solo para prueba interna; falta aceptación visual de una instalación limpia
antes de distribuirlo, y firma de código antes de entregarlo a terceros.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---
