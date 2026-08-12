# Mia · SOP — SOUL.md + entrevista de onboarding (Módulo 5)
# Última actualización: 2026-07-20 (rediseño "más rico, no más largo")

## Qué es
El SOUL.md es la **identidad del agente** por despacho: la Capa 1 del prompt de 10
capas (1b) y el `soul_snapshot` que el grafo carga al iniciar cada turno. La
entrevista de onboarding lo construye a partir de 6 preguntas (+1 paso de jurisdicción
que pone el frontend).

NO confundir con las otras "memorias":
- `/memory/` raíz = memoria de construcción (Claude Code).
- `backend/mia/memory/` = memoria en ejecución 2a-2d (perfil, playbooks, trazas).
- **SOUL.md = persona/identidad** del agente (este módulo) — el que menciona
  CLAUDE.md §A como `$MIA_HOME/SOUL.md`.

## Dónde vive
`$MIA_HOME/soul_{tenant_id}.md` (+ `soul_{tenant_id}.responses.json` con las
respuestas crudas para "Revisar mi perfil"). `$MIA_HOME` = `config.MIA_HOME`
(default `mia-data/`, gitignored; el `.env` trae `MIA_HOME=.\mia-data`). Una ruta
relativa se ancla a `PROJECT_ROOT`. Es estado de INSTANCIA por despacho, como las API
keys: el producto se entrega sin SOUL.md y cada despacho lo crea en el onboarding.

## Las preguntas (contrato 2026-07-20)
3 bloques: `identity` (p1 nombre+firma, p2 ciudad+país) · `jurisdiction` (p6: a quién
defiende y en qué asuntos — fusiona las antiguas p6+p7 en un paso con dos campos) ·
`criterio` (p20 autonomía, p21 líneas rojas, p22 estándar de cierre). Cada pregunta:
`{id, block, field, question, example}`. Las respuestas llegan como `{field: valor}` —
**por campo, nunca por id de pregunta**. El frontend inserta encima su paso local de
jurisdicción (selector de países) que auto-llena `jurisdiction.base`.

**Historia del recorte y por qué importa.** El diseño original tenía 19 preguntas y 9
secciones. Se recortó a 8 preguntas y 4 secciones y cada recorte estuvo justificado,
pero se eliminó todo el contenido de CRITERIO sin reponer nada: quedaron los datos
censales y se fue el juicio. El perfil era una tarjeta de presentación — se pedía el
estilo en 3 adjetivos mientras el resumen decía "tu estilo no te lo pregunto", y
`hard_nos` se renderizaba sin que ninguna pregunta lo alimentara (un cuarto amoblado
sin puerta). El rediseño 2026-07-20 quita lo que Mia puede INFERIR del trabajo real o
que no cambia un borrador (estilo en adjetivos, canales, herramientas, modo profundo)
y mete lo que hace COMPUTABLE el criterio: autonomía, prohibiciones y cierre.

**Regla de diseño:** lo que Mia puede inferir del trabajo real no se pregunta. Cada
pregunta tiene que ganarse su sitio. Y todo agnóstico de jurisdicción: sin país, rama
del derecho ni tipo de cliente precargado; los chips son genéricos y editables.

## Las secciones del SOUL.md
`## identity · ## jurisdiction · ## autonomia · ## nunca · ## terminado ·
## aprendido`, más las **legacy** que solo aparecen si un `responses.json` anterior al
rediseño todavía las trae (`## legal_voice · ## hard_nos · ## rhythm · ## tools ·
## triad_mode`). `SOUL_SECTIONS` en `soul_interview.py` es la fuente.

La generación es **DETERMINISTA (sin LLM)** y **OMITE lo vacío**: jamás imprime
placeholders entre corchetes ni plantilla a medio llenar. De ahí que un perfil viejo
degrade limpio — conserva todo lo suyo y no gana secciones nuevas vacías.

`## aprendido` es la idea central del rediseño: la riqueza crece con el USO, no con más
preguntas. Ninguna pregunta la alimenta; la escribe Mia desde el trabajo real vía
`update_soul`, con cada línea marcada `[inferido]`, fechada y con su fuente.
**AVISO — ese escritor todavía NO existe** (incremento aparte): hoy la sección solo se
RENDERIZA si alguien pone el campo. No afirmar que se llena sola.

## El guardián del endpoint (arreglo 2026-07-20)
`build_soul` lee por CAMPO. Una llave desconocida no explota: simplemente no se lee, y
el perfil sale vacío **con un 200 OK encima**. Ese era un fallo silencioso real —
mandar `{"p1":…,"p2":…}` producía un SOUL de dos líneas y el API lo daba por bueno.
`validate_soul` YA detectaba el caso pero solo se invocaba desde un test: el detector de
humo estaba desconectado del endpoint.

Hoy `POST /api/onboarding/complete` valida ANTES de escribir nada:
1. `_validate_responses_shape` — forma y tamaño.
2. `_known_fields_only` — se queda con lo que el generador SABE leer (`KNOWN_FIELDS`).
   Lo que sobra se **ignora y se registra en el log**, nunca se le enseña al abogado
   (§G: cero notación con puntos en pantalla). **422 solo si NO queda ninguna llave
   legible** — ese, y solo ese, es el fallo silencioso que había que cerrar.
3. `_reject_empty_profile` — exige el **nombre del despacho** (`firm_name`) y que el SOUL
   construido en memoria pase `validate_soul`; si no, 422 y no se toca el disco.

`PUT /api/profile/full` comparte (1) y (2) — escribe la misma fuente canónica, así que lo
que nadie lee no se guarda. NO comparte (3): un guardado parcial desde "Mi despacho" se
fusiona sobre lo que ya hay y no tiene por qué traer el perfil entero.

**Por qué (2) ignora en vez de rechazar (BLOQUEANTE-1, corregido el mismo día).** La
primera versión rechazaba el payload entero nombrando las llaves sobrantes. Con
`KNOWN_FIELDS` incompleto eso dejó a despachos REALES encerrados fuera de su propio
perfil: "Revisar mi perfil" reenvía las respuestas guardadas tal cual, y un campo del
cuestionario anterior (`jurisdiction.courts`) bastaba para un 422 perpetuo — comprobado
contra el perfil real de Lexia. Dos arreglos, no uno: `KNOWN_FIELDS` cubre ahora TODOS
los campos históricos (`LEGACY_STORED_FIELDS`), y la política dejó de ser un muro. Un
guardián no puede cerrarle la puerta a quien ya entró.

**Por qué (3) exige el nombre explícitamente (MAYOR-3).** `validate_soul` solo comprueba
que exista `## identity`, y esa sección aparece con cualquier dato de identidad — una
ciudad basta. El mensaje decía exigir el nombre del despacho y no lo exigía: se guardaban
perfiles sin dueño titulados "Despacho".

## Las tres familias de campos (`soul_interview.py`)
- `CURRENT_FIELDS` — los que alimenta el cuestionario de hoy, más `aprendido`.
- `LEGACY_RENDERED_FIELDS` — fuera del cuestionario, **dentro** del generador: si un
  `responses.json` viejo los trae, se imprimen (voz, canales, estructura, ritmo,
  herramientas, triad).
- `LEGACY_STORED_FIELDS` — del cuestionario original de 19 preguntas; hoy **no los
  renderiza nadie** (cortes, doctrina, misión, órbita). Se reconocen y se conservan
  igual: reconocer no es renderizar, y el dato que el abogado escribió no se destruye.

`KNOWN_FIELDS` es la unión de las tres. Añadir un campo al wizard sin añadirlo aquí hace
que se guarde y no se vea; quitarlo de aquí encierra fuera de su perfil a quien lo tenga.

## API (en `api/routes/ux.py`, prefijo /api)
- `GET  /api/onboarding/questions` → las preguntas vigentes (hoy 6; el número sale de
  `QUESTIONS`, no está cableado).
- `POST /api/onboarding/complete`  → `{responses, jurisdictions?}` → valida (ver
  "El guardián"), genera y guarda el SOUL.md → `{soul_content, summary, path}`.
  **422 en llano** si las llaves no se reconocen o el perfil quedaría degenerado.
- `GET/PUT /api/profile/full` → "Mi despacho": misma fuente canónica, editable después
  de la entrevista. Espeja los campos nuevos (`autonomia.*`, `nunca`, `terminado`).
- `GET  /api/onboarding/status`    → `{completed, last_updated, responses}`
  (derivado de la existencia/mtime del archivo — **sin tabla en DB**).

## Wiring al prompt
1. **Grafo (turno real del producto):** `agents/state.py::initial_state` carga
   `soul_snapshot` con `load_soul_snapshot(tenant_id)` si el archivo existe;
   `agents/graph.py::_system_with_soul` antepone la identidad al system de
   `analysis_node`, `draft_node` y el EDIT de `finalize_node`. Sin SOUL.md →
   `soul_snapshot=None` → system base sin cambios (gate 1d intacto). **Resuelve el
   problema que tenía el Riesgo #11**: la costura `soul_snapshot` existía pero nadie
   la llenaba.

El runtime alterno `MiaAgent.run_turn` fue retirado en agosto de 2026 por no tener consumidor.
La única ruta vigente es el grafo productivo descrito arriba.

## Revisión trimestral
`SoulInterview.update_soul(tenant_id, updates)` fusiona las respuestas guardadas con los
cambios y **reconstruye** el SOUL.md de forma determinista (sin LLM), conservando lo
demás. El header registra "Próxima revisión: generación + 3 meses".

## Gate
`execution/test_e2e.py` (58/58) — recorrido completo del abogado: onboarding (preguntas
vigentes, el rechazo de un perfil ilegible, las secciones de criterio, wiring al turno),
asunto, documento, chat+SSE, HITL, memoria, dashboard. Es el GATE FINAL.

La **degradación de un perfil ya creado** se comprueba en `run_perfil_ya_creado_checks`,
**por el endpoint HTTP y con su propio despacho** (`LEXIA_PRE_RECORTE`, copiado de la
forma de los perfiles reales de `mia-data/`). No vale comprobarla llamando a `update_soul`:
eso se salta los tres validadores del API, que es justo donde vivía el 422 — el check
anterior estuvo verde encima de un rechazo real por exactamente ese motivo (BLOQUEANTE-2).
Regla: **si el defecto vive en el endpoint, el check pasa por el endpoint.**

`execution/test_onboarding_horizontal.py` (13/13) cubre el contrato del wizard, incluida
la salida para un país fuera de la lista (ver abajo).

## El paso de país nunca es una pared
El país es de los pocos datos que Mia no puede inferir (enruta normas), así que se pide.
Pero **Mia no es de ningún país**: la lista de casillas es una comodidad para los países
que ya traen paquete jurídico, y junto a ella va siempre un campo libre ("¿Trabajas con
las reglas de otro país?"). Cualquiera de las dos vías basta para continuar.

- Casillas marcadas → viajan como `jurisdictions` (códigos de paquete) y como nombres en
  `jurisdiction.base`.
- Países escritos a mano → **solo** como nombres en `jurisdiction.base` (no tienen código
  de paquete). Si no hay ninguna casilla marcada, `jurisdictions` viaja como `["generic"]`:
  modo general elegido a propósito, no "nunca configuró nada".
- `MiDespachoSection.tsx` espeja las dos vías. Si solo las espejara la entrevista, el
  abogado perdería su jurisdicción la primera vez que editase el perfil.

Hacer obligatorio ese paso **sobre una lista cerrada** dejaba a un despacho de Brasil,
EE. UU., Portugal o Francia sin poder terminar el alta: cierra mercados enteros y choca
de frente con la regla dura del producto. El paso sigue siendo obligatorio; la lista, no.

## Self-Annealing
1. **El SOUL.md sale con dos líneas** → llegaron llaves que el generador no lee (p. ej.
   ids de pregunta en vez de campos). Desde 2026-07-20 eso es un 422 que NOMBRA las
   llaves, no un 200 silencioso. Si vuelve a pasar en silencio, el guardián se
   desconectó: revisa que `onboarding_complete` siga llamando a `_reject_unknown_fields`
   y `_reject_empty_profile`.
2. **Un campo nuevo del wizard no aparece en el perfil** → falta en `KNOWN_FIELDS` (el
   endpoint lo IGNORA y lo deja anotado en el log — busca ahí "se ignoran llaves") o en
   `build_soul`/`build_summary` (se guarda y no se ve). Los tres sitios se tocan juntos.
2b. **Un despacho no puede volver a guardar su perfil** → alguien volvió a convertir el
   guardián en un muro, o le quitó campos a `KNOWN_FIELDS`. Los perfiles de `mia-data/`
   son el contraste real: sus llaves tienen que estar TODAS en `KNOWN_FIELDS`.
3. **El borrador no usa la voz del despacho** → no hay `$MIA_HOME/soul_{tenant}.md`
   (onboarding incompleto) → `soul_snapshot=None`. Verifica `config.MIA_HOME` y que el
   archivo exista para ese tenant.
4. **Import circular al cargar el grafo** → `state.py`/`core.py` importan los helpers
   de `onboarding.soul_interview` de forma DIFERIDA (dentro de la función) justo para
   evitarlo; no los muevas al top del módulo.
5. **triad_mode no "hace" nada** → hoy es solo una preferencia almacenada en el
   SOUL.md; no existe un modo de ejecución de tres modelos en el grafo (trabajo
   futuro — ver bugs-and-risks #27). Su pregunta (p19) salió del cuestionario en el
   rediseño 2026-07-20: no se ofrece lo que no está implementado.
