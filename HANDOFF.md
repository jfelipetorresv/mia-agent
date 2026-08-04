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

# CIERRE — 2026-07-30 (sesión 53) · Los cuatro pendientes de la 52, cerrados · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable` (FUERA del repo, en la raíz del proyecto, **no** en `mia\tools`).
> Para correr en vivo hace falta **LiteLLM con UTF-8**: `PYTHONUTF8=1` delante, o revienta al
> pintar su banner en una consola cp1252. Para MIRAR cualquier pantalla, siembra el despacho de
> prueba: `execution\seed_despacho_demo.py` (y `--borrar` al terminar). Lo pendiente está en
> «Qué sigue».

Rama `feat/fase1-inc1-cleanup-scaffolding`. Cuatro commits, repo limpio (`c644c91` → `28819ac`).

## Qué pasó en esta sesión (2026-07-30, 53ª)

Los cuatro puntos que la sesión 52 dejó en «qué sigue», cerrados en orden.

### 1 · El aviso de crédito LLEGA A LA PANTALLA (`c644c91`)

En la 52 el texto quedaba calculado y probado, pero nadie lo emitía: un aviso que no sale de la
memoria del proceso no avisa a nadie. `turno_sse` envuelve ahora el turno —asunto, proyecto y
cierre del borrador— y emite `aviso_de_costo` al final. **También cuando el turno FALLA**: si ya
se gastó crédito, el abogado tiene que enterarse aunque la respuesta no llegara. El componente
`AvisoDeCosto` no redacta nada (una sola redacción que auditar), y la pantalla de revisión deja
el aviso en depósito porque navega al asunto a los 900 ms. Gate 41/41 (era 26/26): ahora ejerce
el cuerpo real del SSE con un grafo de mentira, sin DB ni modelo.

### 2 · El ALCANCE en expedientes voluminosos (`d481a85`) — lo de más valor, y lo más matizado

Tres piezas, todas de CÓDIGO (funcionan bajo suscripción, donde no hay herramientas) y ninguna
gasta un token de más:

- **Barrido de cobertura**: posiciones equiespaciadas de cada pieza que el ranking no trajo,
  leídas por POSICIÓN (por parecido traería más de lo mismo). Se paga con la cola de la lista.
- **Relectura dirigida**: al analizar se busca otra vez con los HECHOS y la investigación del
  propio turno, que ya nombran los ejes que la pregunta no nombraba.
- **El alcance se DICE**: bajo el 95% leído, el informe declara «leí 86 de 252 fragmentos (34%)»
  y que un dato puntual puede faltar. Es la disciplina del muro de citas aplicada a la lectura.

**MEDICIÓN HONESTA** (caso de oro voluminoso, 4 corridas en vivo): 44 de los 98 fragmentos
leídos vienen ahora de sitios que el ranking no habría traído, pero **el recall de datos
enterrados NO subió: sigue 1/3**. El límite es estructural — leer 98 de 252 ve el 39% del
expediente se reparta como se reparta, y ninguna recuperación garantiza ver un fragmento
concreto. Por eso la tercera pieza. Dos hallazgos del camino: cubrir solo las piezas HUÉRFANAS
no movió la aguja (el sesgo también está DENTRO de cada pieza), y la primera versión del barrido
ENCOGÍA la lectura de 98 a 86 (deduplicaba después de ceder la cola).

**PARA PIPE**: se probó doblar el techo de lectura (128 → 256). El turno dejó de caber en la
suscripción, saltó a crédito (**USD 1,01 de tarjeta en una sola consulta**) y acabó agotando la
cadena. Leer más no es la salida; si quiere otra vía, es decisión suya.

### 3 · Despacho de prueba: por fin se puede MIRAR (`f226bbd`)

`execution/seed_despacho_demo.py` deja, sin red y sin cuota: despacho con perfil y SOUL.md (la
app abre en el escritorio, no en la entrevista), un asunto con documentos y un borrador
esperando revisión **generado por el grafo real**, con una cita sin respaldo, dos afirmaciones
negativas y una parte de otro expediente. `--borrar` limpia base Y archivos.

Se usó de inmediato y **encontró dos defectos que ningún test veía**:

- con una única cita OMITIDA, el resumen decía «todas con respaldo en sus fuentes» — lo
  contrario de lo ocurrido, en la primera línea que se lee;
- en un PROYECTO, `normalizarInforme` descartaba los avisos nuevos: el componente sabía
  pintarlos y nunca los recibía.

El gate del seed salía intermitente (el aviso de afirmaciones negativas dependía de un empate
entre vectores). Ahora el doble de embeddings entierra esos términos a propósito: 3 corridas
seguidas, 17/17.

### 4 · Bienvenida F3: verificada entera y arreglado su punto flojo (`28819ac`)

El rediseño cinematográfico ya estaba (aurora, wordmark, una pregunta a la vez, progreso de
cuatro etapas). Lo que no encajaba era la única pregunta de contexto: 21 países en filas con
casilla y scroll, en medio de un wizard de una pregunta a la vez. Ahora son fichas en flujo con
buscador; la pregunta pasa de 1290 a 1010 px y se marca un país con un clic (comprobado en el
recorrido real, no de vista).

## Qué sigue (en orden, sin necesitar a Pipe)

1. **E2E automatizado de la primera vez** (salida medible de F3 en el plan maestro): el
   recorrido `/register → /activar → /onboarding (7 preguntas) → expediente → borrador →
   aprobar`, cronometrado y con captura por paso. Esta sesión lo recorrió a mano hasta la
   pregunta 4 y verificó cada pantalla; falta automatizarlo entero y correrlo 3 veces.
   Aviso del camino: el alta tiene freno anti fuerza-bruta (10 registros por hora y por IP) —
   un E2E que registre en bucle se topa con un 429 legítimo.
2. **El alcance, si se quiere otra vía**: hoy está medido, repartido y declarado. Subir el techo
   está probado y descartado (punto 2 de arriba).
3. Producto (plan maestro): lo que quede de F3 tras el E2E.

## Pendientes de Pipe

- **Prueba del instalador en máquina limpia** (doble clic en frío), checklist de 7 puntos,
  riesgo #59. Nada lo sustituye. **El instalador NO se ha re-ensamblado con los cambios de esta
  sesión.**
- **Lectura de calidad** de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- **Los dos trámites de terceros**: Azure Trusted Signing y registro de apps OAuth
  (`docs/tramites-terceros-pipe.md`).
- **Decidir sobre el alcance** con el dato nuevo: leer más cuesta crédito de tarjeta.

---

---

# CIERRE — 2026-08-04 (sesión 54) · El recorrido de primera vez, automatizado: 3 corridas verdes · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para el E2E del recorrido: los 4 servicios arriba, luego
> `.venv\Scripts\python.exe e2e\generar_expediente.py` (una vez) y
> `node e2e\recorrido_primera_vez.mjs --corrida N` (~25-30 min por corrida). Detalle en
> `architecture/e2e_runbook.md` §0-bis y bitácora en `validation/validation-log.md`.

Rama `feat/fase1-inc1-cleanup-scaffolding`. Repo limpio tras `af49c19` + este cierre.

## OJO: tres commits ajenos sin documentar

Entre la sesión 53 y esta aparecieron `f264b1e` (principios Lexia en el grafo), `e7ff81b`
(gobierno de vaults) y `f52c945` (rediseño «Neumorfismo Pro») — de otra herramienta, sin entrada
de HANDOFF. Esta sesión trabajó SOBRE ese estado y el recorrido pasó, así que no rompen el flujo
principal, pero nadie ha auditado qué más tocaron (`graph.py`, `prompt_builder.py`).

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
2. **Auditar los 3 commits ajenos** (`f264b1e`, `e7ff81b`, `f52c945`): qué cambiaron en el
   grafo y el prompt, y si merecen su entrada de traspaso o revertirse.
3. Checklist de honestidad de UI por paso (la otra mitad de la salida medible de F3).
4. Producto (plan maestro): lo que quede de F3.

## Pendientes de Pipe (sin cambios desde la 53)

- Prueba del instalador en máquina limpia (el instalador NO se ha re-ensamblado desde la 52).
- Lectura de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- Azure Trusted Signing y registro de apps OAuth (`docs/tramites-terceros-pipe.md`).
- Decidir sobre el alcance (leer más cuesta crédito de tarjeta).
