## Checkpoint anterior: CP-E5 — Delegación multi-agente + tablero de misión por expediente (2026-07-04)

### Qué cambió (lenguaje simple)

- **Tablero de misión por expediente (lo que ve el abogado):** el abogado puede tomar un
  objetivo grande de un asunto —"preparar la contestación", "alistar la audiencia"— y Mia lo
  **descompone en hitos concretos y ordenados** que se ven como un tablero. Cada hito dice
  qué es, quién lo hace (**Mia lo prepara** o **lo haces tú**) y en qué estado va
  (**pendiente / en curso / hecho**). El abogado **aprueba, edita, reordena y marca avance a
  mano**: nada se ejecuta solo (consent-first).
- **Regla dura respetada:** el tablero **no maneja fechas ni plazos**. Si un hito toca un
  término procesal, queda **marcado para que el abogado lo verifique** (Mia nunca calcula
  plazos). No hay ninguna casilla de fecha en el tablero.
- **Investigación en paralelo (por dentro, no lo ve el abogado):** cuando un despacho trabaja
  en **dos o más jurisdicciones**, Mia ahora investiga cada una **por separado y a la vez**, y
  luego consolida. Para Lexia (solo Colombia) **no cambia nada** hoy: sigue el camino de
  siempre, mismo costo. Detalle en `docs/comparacion-cpe5.md`.

### Frontend a construir (Cursor — capa 3): el tablero de misión

Backend listo en `origin/main` (tras aprobación de Pipe). Falta la **pantalla del tablero**,
idealmente dentro de la vista de un asunto (una pestaña "Plan" o "Misión"). Endpoints (todos
bajo `/api`, auth como el resto; todos devuelven la **misión completa** salvo el DELETE de
misión):

- **`GET /api/missions?matter_id={id}`** → `{missions: [Mission]}`. Misiones del asunto.
- **`POST /api/missions`** body `{matter_id, title, objective, outcome?, auto_decompose?}`
  → `Mission`. Con `auto_decompose` (default true) Mia **propone los hitos** al crear.
- **`POST /api/missions/{id}/decompose`** body `{replace?}` → `Mission`. Re-propone hitos
  (`replace:true` sustituye los actuales; `false` los añade al final).
- **`PUT /api/missions/{id}`** body `{title?, objective?, outcome?, status?}` → `Mission`.
  `status` ∈ `"active"` | `"archived"`.
- **`DELETE /api/missions/{id}`** → `{ok:true}`.
- **`POST /api/missions/{id}/milestones`** body `{title, detail?, actor?, is_procedural?}`
  → `Mission`. Añade un hito manual.
- **`PUT /api/missions/{id}/milestones/{milestoneId}`** body cualquiera de
  `{title?, detail?, actor?, status?, seq?, is_procedural?}` → `Mission`. Avanzar un hito =
  `status:"done"`; reordenar = `seq`.
- **`DELETE /api/missions/{id}/milestones/{milestoneId}`** → `Mission`.

Forma de `Mission`:
```
{ id, matter_id, title, objective, outcome, status,
  progress: { done, total },
  milestones: [ { id, seq, title, detail, actor, status, is_procedural } ] }
```

- **Sin jerga (§G) — traducciones para pantalla:**
  - `actor`: `"mia"` → **"Mia lo prepara"**; `"abogado"` → **"Lo haces tú"**.
  - `status` (hito): `"queued"` → **"Pendiente"**, `"active"` → **"En curso"**, `"done"` → **"Hecho"**.
  - `is_procedural: true` → mostrar un aviso claro tipo **"Toca un plazo — confírmalo tú
    [VERIFICAR]"**. NUNCA calcular ni sugerir una fecha.
  - `progress` → barra "X de Y hitos".
  - `matter_id` es un identificador interno para ligar la misión al asunto (como el id de la
    misión); no mostrarlo como texto al abogado.
- Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual): título
  vacío, tope de misiones/hitos, misión/hito inexistente, etc. Errores de servicio **502** en
  llano. **404** si la misión no existe.

### Comportamiento esperado

- Crear misión "Preparar la contestación" con objetivo → Mia devuelve 3-8 hitos propuestos
  (pendientes), algunos marcados "Mia lo prepara". El abogado los edita/aprueba y va marcando
  "Hecho"; la barra de progreso sube.
- Si Mia no logra proponer (modelo caído) → devuelve una **lista genérica de planeación**
  editable (el tablero nunca queda vacío). Consent-first: nada se ejecuta solo.
- El objetivo con palabras de plazo ("contestar dentro del término") → el hito correspondiente
  llega **marcado como procesal** para que el abogado confirme el plazo.

### Resultado de verificación (3 capas)

- Capa 1: 3 gates nuevos — `test_delegation.py` **11/11** (concurrencia acotada, orden
  estable, fail-soft, tope duro), `test_missions.py` **40/40** (descomposición con guarda
  procesal fail-closed; CRUD y topes bajo RLS; AISLAMIENTO entre despachos; propiedad del
  expediente), `test_research_swarm.py` **21/21** (1 jurisdicción = camino simple sin costo
  extra; ≥2 = swarm con verificación por rama + síntesis; fail-soft; degradación por tope;
  dedup). Regresión **ALL PASS (59 suites)** con `test_rls` HALT.
- Capa 2 (revisor adversarial independiente): confirmó correctos RLS/aislamiento, regla de
  plazos, §G, fail-soft y concurrencia de uso. 1 MAYOR (carrera sobre el compresor compartido
  en el swarm) + 2 MENORES (dedup de jurisdicciones; degradación por tope) **corregidos y
  re-verificados ANTES del commit**; 2 residuales aceptados (orden de hitos por desempate;
  `matter_id` expuesto a propósito). Ver `memory/progress.md` sesión 33.
- Capa 3: **COMPLETADO** — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E5, commit `f47f143`).

---

