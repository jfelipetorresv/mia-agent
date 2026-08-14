# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

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

# CIERRE — 2026-08-08 (sesión 56) · Circuit-breaker de la suscripción + el approve medido de verdad · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para el E2E: los 4 servicios arriba y
> `node e2e\recorrido_primera_vez.mjs --corrida N`. Detalle en `architecture/e2e_runbook.md`
> §0-bis y bitácora en `validation/validation-log.md`.

Rama `feat/fase1-inc1-cleanup-scaffolding`, repo limpio tras este cierre.

## Qué pasó en esta sesión (2026-08-08, 56ª)

Los dos frentes que dejó la 55, cerrados — uno con código y otro con medición honesta:

1. **Circuit-breaker por TURNO del motor de suscripción** (`backend/mia/agent/llm.py`). El
   salto rápido de la s52 evitaba reintentos dentro de UNA llamada, pero cada nodo del grafo
   volvía a intentar la suscripción y volvía a pagar hasta 300 s — 2-3 nodos ≈ los ~13 min
   medidos. Ahora el primer timeout de un alias `cli-*` lo marca AGOTADO por el resto del
   turno (ContextVar atado a `recolectar_cambios_de_motor`, la frontera del turno): los nodos
   siguientes saltan directo al respaldo. Por ALIAS (que `cli-claude` no aguante el expediente
   no condena a `cli-claude-haiku`), muere con el turno, y cada salto queda contado en el
   aviso de costo. Si el alias agotado es el ÚLTIMO de la cadena se intenta igual (mejor tarde
   que sin respuesta). Gate: `test_cambio_de_motor_aviso.py` §3-bis (46/46) — ejerce `call_llm`
   completo con la cadena real: 3 nodos, un solo timeout pagado, turno nuevo reintenta.

2. **El approve de ~90 s NO era lo que el plan creía — y no se movió código a ciegas.** El plan
   decía «mover sellos + index_trace a background». Medido: con el despacho demo el approve
   entero tarda 0,7 s; en la corrida 5 REAL, 1,8 s de punta a punta (servidor: grafo 0,2 s;
   capture 0,1 + index 0,1 + sellos 0,0). Los 91,5 s de la corrida 4 fueron circunstancia del
   entorno (ese día TODO estuvo lento: turno 20,7 min vs 8 min hoy con el mismo expediente).
   Lo que queda es la BARRERA: instrumentación permanente de tiempos por etapa en
   `hitl._resume` (`resume(...): abrir/estado/grafo`) y `finalize_node`
   (`finalize(...): capture/index/sellos`) — la próxima regresión se LEE en el log del
   backend, no se investiga. Descartados en el camino: nodo HITL re-ejecutando trabajo al
   reanudar (interrupt es la primera línea), tareas de fondo bloqueando el loop (usan
   to_thread), y el path de edición disfrazado (el E2E aprueba sin editar).

## Corrida 5 del E2E — VERDE (la más rápida de la serie)

| corrida | total | turno | aprobar | ## aprendido |
|---|---|---|---|---|
| 4 (s55) | 22,8 min | 20,7 min | 91,5 s | poblado |
| **5 (s56)** | **8,7 min** | **8,1 min** | **1,8 s** | poblado |

El turno entero corrió EN LA SUSCRIPCIÓN sin un timeout ni un salto de motor. Ojo: n=1, el
motor estuvo notablemente más rápido hoy — no se afirma mejora de p50 con una corrida.

## Gates del cierre

test_rls 19/19 · test_gates_no_ciegos 9/9 · check_env_pins 12/12 · test_cambio_de_motor_aviso
46/46 · test_llm_fallback 25/25 · test_model_policy 43/43 · test_citation_seals 14/14 ·
test_aprendido 34/34 · test_seed_despacho_demo 17/17 (despacho demo RE-SEMBRADO después) ·
test_e2e 58/58. `test_hitl_flow` 20/21: FAIL PREEXISTENTE (idéntico en `f2266ad` limpio,
verificado con stash) — riesgo #86 en bugs-and-risks, parece check desactualizado frente al
grafo post-F0-F2.

## Pendientes que siguen

- **De Pipe (de la s55, sigue abierto)**: ¿muro + gate LLM (como está) o solo muro? El gate
  gasta un turno de modelo por borrador.
- **Sesión 57**: riesgo #86 (check desactualizado de test_hitl_flow, barato); F3 del plan de
  eficiencia (función→nivel) y F4 (memoria progresiva); residuos F0-F2 (KPI sellos en panel,
  extractos por rol, caché ficha).

---

# CIERRE — 2026-08-07 (sesión 55) · Los 4 puntos de la 54 + plan de eficiencia F0-F2 ejecutado

> **CONTINUACIÓN MISMA SESIÓN (tarde/noche)**: Pipe aprobó el plan de eficiencia
> (`specs/todo/PLAN-principios-harness-llos-eficiencia.md`, principios destilados de su
> harness LLOS — solo principios, nada de código/marca) y se ejecutaron F0+F1+F2:
> medición por nodo (migración 048, gate test_uso_por_nodo), gate de citas en UNA pasada
> sin reescritura + cosecha en background como propuesta (migración 049) + caches
> (test_embed_cache), y el SELLO de verificación incremental (migración 050,
> test_citation_seals 14/14; quemada gana, quemar revoca). **Medido contra baseline:
> −47 % tokens y −55 % latencia (20 → 8,9 min) con 0-sin-respaldo intacto** —
> `validation/baseline-f0-por-nodo.md` tiene las 4 tablas y los residuos anotados
> (KPI de sellos en panel, F1.2b extractos por rol, caché de ficha, F3-F4 del plan).
> Commits `74067ec` → `9d077e7`+cierre, pusheados. El backend corriendo en la máquina
> quedó ANTERIOR a estos cambios: reiniciarlo antes de mirar pantallas.

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para MIRAR pantallas: `execution\seed_despacho_demo.py`
> (`--borrar` al terminar; OJO: `test_seed_despacho_demo.py` BORRA el despacho demo al
> limpiar — re-sembrar después). Para el E2E: 4 servicios arriba y
> `node e2e\recorrido_primera_vez.mjs --corrida N` (~23-30 min).

Rama `feat/fase1-inc1-cleanup-scaffolding`. Repo limpio tras este cierre
(`585f332` → este commit). Entre la 54 y esta sesión, Pipe hizo además 8 commits de diseño
(`d297b2a` → `1be4af5`: sistema neumórfico, logotipo octaedro 3D) — SON DE PIPE y se quedan;
entraron a la revisión técnica de abajo.

## Qué pasó en esta sesión (2026-08-07, 55ª) — los 4 puntos de «Qué sigue» de la 54

1. **DEFECTO UI-A CERRADO (`585f332`)**: la fila de acciones del asunto no envolvía
   (`flex` sin wrap) y con 5 botones desbordaba bajo el aside de 300px, que interceptaba el
   clic. `flex-wrap + min-w-0`: los botones pasan a segunda línea. Verificado por mutación
   (con el código viejo la fila invade el aside: 1183px > 1140px) y EN VIVO a 1440×900 y
   1280×800. En la corrida 4 el clic real tomó 1,0 s sin aviso.
2. **Revisión técnica de los commits de Pipe — encontró 2 BLOQUEANTES en `f264b1e` y los
   cerró (`2e899bf`)**: el commit de principios Lexia renombró el nodo de verificación a un
   gate LLM (`verificador_citas`) y con ello DESCONECTÓ el muro determinista (`_verify_draft`:
   citas quemadas, [VERIFICAR], afirmaciones negativas, contaminación, alcance) — el borrador
   llegaba a revisión sin `md["verification"]` — y dejó el SSE `draft_ready` buscando el nodo
   viejo. El gate LLM SE QUEDA (decisión de Pipe); el muro corre ahora sobre su salida.
   Evidencia: test_seed 12/17→17/17, test_e2e 57/58→58/58. Los menores quedaron anotados en
   `memory/bugs-and-risks.md` (BrandMark con props muertas, contraste WCAG sin re-medir,
   harvest sin frase de progreso) + un watch-out de producto: el gate LLM gasta un turno de
   modelo extra por borrador — decisión de Pipe si lo quiere además del muro.
3. **Checklist de honestidad de UI FIRMADO (`f7316ad`)**: auditor independiente, por paso del
   recorrido — `validation/checklist-honestidad-ui.md`. 11 PASA / 1 FALLA / 3 AVISO. La FALLA
   (botones «Conectar» correo visibles sin app OAuth registrada) se corrigió en `c6173e5`
   (`/api/mailbox/status` expone `disponible`; la UI muestra el aviso honesto) y se verificó
   EN VIVO en /configurar → Conexiones.
4. **Corrida 4 del E2E: VERDE en 22,8 min** (turno 20,7 min; approve 91,5 s; `## aprendido`
   poblado). El E2E ya NO rodea el UI-A: el clic real es la aserción. Bitácora en
   `validation/validation-log.md`.

**Además**: migración `047_citas_quemadas.sql` estaba aplicable pero fuera de la DB dev
(health decía 44/45) — aplicada con `init_citas_quemadas.py` y registrada en el ledger con el
MISMO sha que calcula `db_bootstrap.migration_sha256`; health 45/45.

**Gates re-corridos hoy, todos verdes**: rls 19/19 · gates_no_ciegos 9/9 · env_pins 12/12 ·
e2e 58/58 · seed 17/17 · sentence_report 47/47 · citas_quemadas 20/20 · migration_ledger PASS
· tsc 0 errores.

## Qué sigue (en orden, sin necesitar a Pipe)

1. **Lentitud señalable (abierta desde la 54)**: el motor de suscripción agota su timeout
   (~13 min) con el caso voluminoso y salta a claude-sonnet (turnos 20-28 min); y
   `POST /draft/approve` corre el cierre del grafo SINCRÓNICO (~90 s con la pantalla en
   «aprobando»). Atacar el approve asíncrono primero: es la espera que el abogado SIENTE.
2. Producto (plan maestro): lo que quede de F4 (seguridad pre-cliente) — F3 queda con su
   salida medible completa (3+1 corridas verdes, checklist firmado, `## aprendido`).
3. Los AVISO del checklist de honestidad (auditoría fina del onboarding paso a paso).

## Pendientes de Pipe (sin cambios desde la 53, + 1 nuevo)

- Prueba del instalador en máquina limpia (el instalador NO se ha re-ensamblado desde la 52;
  los arreglos de esta sesión tampoco están dentro).
- Lectura de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- Azure Trusted Signing y registro de apps OAuth (`docs/tramites-terceros-pipe.md`).
- Decidir sobre el alcance (leer más cuesta crédito de tarjeta).
- **NUEVO**: decidir sobre el gate LLM de citas de `f264b1e` (ver watch-out en
  `memory/bugs-and-risks.md`): ¿solo el muro determinista, o muro + gate LLM como hoy?

## 2026-08-14 · MIA robustecida (pendiente validación DB/VM)

- Jurisdicción por asunto con precedencia asunto → firma u organización → general; el
  asunto expone chips editables y el grafo los usa en investigación y citas.
- Ledger jurídico hash-bound: recibos históricos, verificador vigente, atestación humana,
  sellos ligados a pasaje/jurisdicción y exportación final registrada. Migraciones 051–057.
- Aprendizaje en cuatro jobs durables e idempotentes; las caídas se reintentan sin duplicar
  memoria ni repetir inferencias ya persistidas.
- Política `quality_adaptive`: Opus/xhigh para trabajo jurídico complejo y Max solo por gate
  excepcional; auxiliares ligeros. La UI reporta disponibilidad/fallback con honestidad.
- AnyDoc conserva estructura con límites de tamaño/ZIP, firma y MIME, timeout aislado. El
  benchmark sintético prueba el mecanismo (87,5 % menos contexto, recall 100 %), no la meta.
- `verify.ps1 -Suite quick`: 13 suites verdes; frontend lint/tsc/build verde. Pendientes para
  afirmar release/meta: PostgreSQL real, E2E completo, benchmark ciego con expedientes reales
  anonimizados y prueba de instalador en VM Windows limpia.
