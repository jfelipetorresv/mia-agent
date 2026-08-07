# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---

# CIERRE — 2026-08-04 (sesión 54) · El recorrido de primera vez, automatizado: 3 corridas verdes

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para el E2E del recorrido: los 4 servicios arriba, luego
> `.venv\Scripts\python.exe e2e\generar_expediente.py` (una vez) y
> `node e2e\recorrido_primera_vez.mjs --corrida N` (~25-30 min por corrida). Detalle en
> `architecture/e2e_runbook.md` §0-bis y bitácora en `validation/validation-log.md`.

Rama `feat/fase1-inc1-cleanup-scaffolding`. Repo limpio tras `af49c19` + este cierre.

## Tres commits de PIPE entre la 53 y esta (confirmado por él, 2026-08-04)

`f264b1e` (principios Lexia en el grafo), `e7ff81b` (gobierno de vaults) y `f52c945` (rediseño
«Neumorfismo Pro») los hizo Pipe desde otra herramienta y LOS QUIERE — no revertir. Esta sesión
trabajó sobre ese estado y el recorrido completo pasó en verde encima del rediseño. Queda solo
una revisión técnica ligera de lo que tocaron en `graph.py`/`prompt_builder.py` (calidad, no
permanencia).

## Qué pasó en esta sesión (2026-08-04, 54ª)

**El punto 1 de «Qué sigue» de la 53, cerrado**: el E2E automatizado de la primera vez existe,
corrió 3 veces consecutivas en verde sin intervención manual, y quedó medido y archivado.

- **`e2e/recorrido_primera_vez.mjs`** (Playwright) recorre register → activar (auto-salto en
  dev) → onboarding (7 pasos, ficha de país incluida) → asunto → expediente → pregunta →
  borrador → gate de citas → aprobar → sonda del `## aprendido`. Screenshot por paso +
  `tiempos.json` en `validation/screenshots/corrida-N/`.
- **`e2e/generar_expediente.py`**: el expediente sintético FIJO que exige la spec, derivado del
  caso de oro voluminoso (3 .txt, 252 fragmentos) — versionado como código, no como binarios.
- **Medición (política suscripción)**: 30,1 / 28,6 / 23,3 min → **p50 28,6 · p95 ≈ 30,0**. El
  95 % es el turno del grafo. `tsc` 0 errores; test_rls, test_gates_no_ciegos y check_env_pins
  PASAN. El `## aprendido` se pobló en las 3 corridas. El muro se vio funcionar de punta a
  punta (el borrador declara sus citas pendientes y el gate exige la decisión del abogado).

## Defectos y hallazgos destapados (los tests no los veían; la pantalla sí)

1. **DEFECTO UI-A (abierto, reproducible 5/5)**: a 1440×900 el aside derecho del asunto tapa el
   botón «Revisar borrador» y le intercepta el clic. Un abogado con esa pantalla no puede
   pulsarlo. El E2E lo rodea (navega directo a `/revisar`) y lo avisa en su salida. **Es el
   candidato #1 a primera tarea de la próxima sesión.**
2. **Lentitud señalable**: el motor de la suscripción agota su timeout (~13 min) con el caso
   voluminoso y salta a claude-sonnet — turnos de 20-28 min. Y `POST /draft/approve` corre el
   cierre del grafo sincrónico: 81-100 s de espera tras el clic en Aprobar.

## Qué sigue (en orden, sin necesitar a Pipe)

1. **Arreglar el DEFECTO UI-A** (el aside sobre «Revisar borrador») y re-correr el E2E.
2. **Revisión técnica ligera de los 3 commits de Pipe** (`f264b1e`, `e7ff81b`, `f52c945`):
   son deseados y se quedan; solo verificar calidad de lo que tocaron en grafo y prompt.
3. Checklist de honestidad de UI por paso (la otra mitad de la salida medible de F3).
4. Producto (plan maestro): lo que quede de F3.

## Pendientes de Pipe (sin cambios desde la 53)

- Prueba del instalador en máquina limpia (el instalador NO se ha re-ensamblado desde la 52).
- Lectura de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- Azure Trusted Signing y registro de apps OAuth (`docs/tramites-terceros-pipe.md`).
- Decidir sobre el alcance (leer más cuesta crédito de tarjeta).

---

# CIERRE — 2026-08-07 (sesión 55) · Los 4 puntos de la 54 cerrados: UI-A, revisión de commits, honestidad, corrida 4 verde · EMPEZAR AQUÍ

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

