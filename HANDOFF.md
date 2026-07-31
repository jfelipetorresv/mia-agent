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

# CIERRE — 2026-07-29 (sesión 52) · Instalador re-ensamblado + caso de oro GRANDE + PRIMER PILOTO CON EXPEDIENTE REAL

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada, arráncala
> (clúster en `tools/pgdata-portable`, FUERA del repo). **Si viene de un cierre sucio tarda ~8
> minutos sincronizando**: comprobar con `pg_isready` hasta que acepte conexiones, no darla por
> muerta. Para cualquier corrida en vivo hay que **encender LiteLLM** primero
> (`.venv-litellm\Scripts\litellm.exe --config litellm_config.yaml --port 4000`); la sonda de salud
> NO lo verifica. **El instalador está re-ensamblado y verde**: de ese bloque solo falta la prueba
> de Pipe en máquina limpia. Lo ejecutable sin Pipe está en «Qué sigue».

Rama `feat/fase1-inc1-cleanup-scaffolding`. Once commits, repo limpio (`d0ea25e` → `52a2eeb`).

## Qué pasó en esta sesión (2026-07-29, 52ª)

### 1 · Instalador RE-ENSAMBLADO (primera vez desde la sesión 45)

`Mia_0.1.0_x64-setup.exe`, **434,2 MB**, en `desktop/src-tauri/target/release/bundle/nsis/`. Lleva
dentro el reinicio en caliente del motor (riesgo #60), las barreras de F1/F2 y las **47
migraciones** (incluida `047_citas_quemadas`: el `.spec` toma la carpeta entera, las nuevas entran
solas).

Tres defectos cerrados (`d0ea25e`):

- **El ensamblaje no podía completarse.** `Remove-Item` falla en el árbol onedir de PyInstaller por
  rutas sobre MAX_PATH y, con `$ErrorActionPreference` en Stop, abortaba el build ENTERO en el primer
  paso sin rastro útil en el log (dos intentos murieron antes de dar con esto). Ahora se vacía con
  `robocopy /MIR` contra una carpeta vacía, en `build_backend.ps1` y `build_litellm.ps1`.
- **`build_backend.ps1` borraba `packaging/dist` COMPLETO**, no solo su payload: dejaba el árbol
  inservible para `build_installer -SkipPayloads` (los otros dos payloads desaparecían sin aviso).
- **Defecto de producto:** si el primer arranque fallaba, el motivo podía llegarle al abogado
  ilegible o no llegar. `first_run` no fijaba la codificación de su stdout y la cáscara lo lee con
  UTF-8 estricto. Ahora se fija UTF-8, fail-soft. **Verificado en el .exe empaquetado real.**

Gates: instalador 30/30 · cáscara 84/84 · litellm 66/66 · **bienvenida 41/41 (diferido desde s46)** ·
primer arranque **71/71** (antes 70/71) · RLS 19/19 · gates_no_ciegos 9/9.

### 2 · El instalador llevaba CÓDIGO DE DEPURACIÓN dentro (`5d6a585`)

Una sesión agéntica anterior dejó bloques `#region agent log` en `MailboxSection.tsx`,
`configurar/page.tsx` y `mailbox.py`; nadie los quitó y al recompilar **viajaron al bundle**: un
chunk de Next.js ya compilado hacía POST a `http://127.0.0.1:7610/ingest/...` desde la máquina del
abogado. Se detectó por casualidad mirando `git status`. Revertidos (parche guardado en el
scratchpad de la sesión) y barrera nueva `test_sin_instrumentacion_debug.py` 12/12, cuya capa
importante es la del **BUNDLE**: la fuente limpia no basta porque el paquete puede venir de un árbol
sucio anterior.

### 3 · Caso de oro con expediente GRANDE + el segundo eje de N-2 (`18426a9`, `00686d4`)

`expediente-voluminoso-cruce-disperso`: **252 fragmentos** en 3 documentos generados de forma
determinista, con tres datos decisivos SELLADOS y ENTERRADOS lejos del inicio, cada uno en un
documento distinto (la suspensión en el acta 87, la reclamación en la comunicación 65, la prórroga
del otrosí 3 en el anexo 58), y una pregunta que obliga a cruzarlos. **FUERA del examen por defecto
a propósito** (cuesta cientos de embeddings y metería otro corte de serie); se corre por id con
`run_eval.py --case`.

Señal nueva `scoring.recall_markers_signal` + campo `GoldenCase.recall_markers`. **NO se reutilizó
`rubric`**: habría producido una métrica con etiqueta engañosa —«cobertura sustantiva» midiendo
recuperación—, la familia del riesgo #81. Límite declarado en el propio código: que el dato aparezca
prueba que se leyó; que NO aparezca no distingue entre «no lo recuperó» y «lo recuperó y no lo usó».

`compare_agentic_reports` ahora cruza **ahorro con recuperación**: ahorrar perdiendo un dato del
expediente se reporta como PEOR, y un solo caso que pierda un dato manda el veredicto agregado.

**Corrida en vivo:** leyó 98 de 252 fragmentos y encontró **1 de 3** datos enterrados (el otrosí 3;
le faltaron las dos FECHAS). 0 citas sin respaldo, abstención 1/1, borrador de 8.195 caracteres,
532s, USD 0,0059 (embeddings; el razonamiento fue cuota).

**N-2 NO SE PUEDE DECIDIR HOY.** `--agentic-compare` informó «IGUAL» cuando el bucle agéntico **no
corrió ni una vez**: con el motor de la suscripción (aliases `cli-*`, subproceso al CLI) no hay
herramientas y `agentic_reading_available()` lo apaga. Corregido — sin ejecución del brazo B el
veredicto es **NO CONCLUYENTE**. El alcance hay que atacarlo por otra vía.

### 4 · PRIMER PILOTO CON EXPEDIENTE REAL (decisión de Pipe) y su borrado verificable

Expediente: arbitraje Banco Popular vs Zurich (352 archivos, 291 MB). Entraron los **escritos
rectores** (demanda, reforma del 29-07, póliza, condiciones particulares, prima, 3 actas del
tribunal): 174 páginas, 597.836 caracteres, **0 páginas de OCR** (el extractor de MIA los leyó
nativos), 574 fragmentos. La **contestación radicada, el concepto y los análisis forenses quedaron
FUERA** — son la respuesta con la que se coteja.

**Cotejo.** MIA llegó sola a **3 de las 8 excepciones** radicadas:

- Condición 9 · prueba de la pérdida en 6 meses ≈ la CUARTA de Lexia (carga probatoria).
- Personal de Nexa sin «supervisión o control **directo**» (numeral 14) ≈ la TERCERA, **casi con las
  mismas palabras**.
- Cuantía reformada sin soporte + objetar el juramento estimatorio ≈ el eje de cuantía.
- En el diagnóstico añadió el descubrimiento fuera de vigencia, y **detectó la prescripción pero la
  calificó de «insuficientemente desarrollada» cuando Lexia la puso PRIMERA**.
- No propuso: exclusión por otra póliza, deducible/valor asegurado, inexistencia por firmas y
  huellas, genérica.
- **Disciplina impecable:** 0 afirmaciones sin respaldo, todo anclado a su `[doc n]`, marcó
  `[NORMA – VERIFICAR]` donde no tenía ordenamiento configurado, avisó de un plazo a verificar como
  URGENTE, y detectó por su cuenta que **la Condición 22 estaba truncada en el expediente digital**.
- Leyó **128 de 574 fragmentos (22%)**. Hipótesis de por qué subestimó la prescripción: no vio el
  material con las fechas — el mismo límite de alcance del caso sintético.

**Borrado verificable** (`c9e3564`, `ba6fedd`) — `execution/purgar_piloto.py`. El hallazgo que
cambia el problema: **borrar en la base NO alcanza**. En la política suscripción MIA razona
invocando el CLI con `cwd = MIA_HOME`, y **ese CLI guarda el PROMPT COMPLETO de cada turno en
`~/.claude/projects/<slug de MIA_HOME>/*.jsonl`** — fuera de MIA (verificado: el expediente estaba
dentro). Tampoco se iban con el tenant las corridas del banco con texto completo, ni el perfil del
despacho, ni las trazas. El comando cubre los tres sitios y **DEMUESTRA** el resultado buscando los
términos del cliente: si aparece una coincidencia, exit 1. Las tablas se DESCUBREN del catálogo por
su columna `tenant_id` (45 hoy), así que una tabla nueva entra sola en la verificación.

Sus **dos defectos peores fueron los que tranquilizaban**, encontrados probándolo antes de usarlo:
el slug no contemplaba los ESPACIOS de la ruta y reportaba «0 coincidencias» (certeza falsa), y la
búsqueda por subcadena marcaba para borrado cuatro corridas ajenas porque **«Nexa» casa dentro de
«anexa»**. Ejercido: **584 filas en 4 tablas → 0 en las 45**, 10 transcripts borrados, 0
coincidencias. Los PDF/DOCX originales del abogado NUNCA se tocan.

**Lo que ningún borrado deshace, y el informe lo dice:** lo que ya salió al proveedor de embeddings
y al modelo. Para eso el expediente debe entrar ANONIMIZADO (`security/anonymize.py`).

### 5 · Dos defectos de CAPACIDAD que solo se ven con material real

- **La ingesta reventaba con expedientes grandes.** `embed_texts` mandaba TODOS los textos en UNA
  llamada y el proveedor rechaza el lote sobre su tope: *max allowed tokens per submitted batch is
  120000, your batch has 127058*. No era un caso extremo: `upload_document` pasa de golpe todos los
  fragmentos, así que **al abogado le reventaba la subida de un documento grande** (una póliza de 90
  páginas son 311.000 caracteres, ya roza el tope). Arreglado EN `embed_texts` —una docena de
  llamadores no deben saber del tope—: trocea por 90.000 tokens y 512 items. **Lo peligroso era el
  ORDEN**, no el troceo: quien llama empareja `vectors[i]` con `texts[i]`, y desordenarlos guardaría
  cada fragmento con el embedding de otro, un fallo silencioso que envenena la búsqueda. Gate 16/16.
- **La suscripción no da para un expediente real de ese tamaño:** el CLI expiró **3 veces a 300s**
  (15 minutos tirados) y saltó a la nube, que respondió a la primera → **USD 0,573 de tarjeta**, sin
  que nada en pantalla lo dijera.

### 6 · Política de motores: la suscripción se apalanca, el crédito se avisa (decisión de Pipe)

- **Salto rápido:** ante timeout de un alias `cli-*` con motor siguiente, se salta YA (un timeout por
  volumen es determinista; el reintento manda el mismo prompt gigante). Los timeouts de otros
  proveedores conservan su reintento intacto.
- **Aviso al abogado:** los cambios de motor se acumulan por turno (`recolectar_cambios_de_motor`,
  ContextVar) y `aviso_cambio_de_motor` arma el texto. Aparece **solo cuando cambia quién paga** (no
  entre motores de nube, no al local, no dentro de la propia suscripción).
- **Plan Max recomendado también en la INSTALACIÓN** (petición expresa de Pipe), en la tarjeta «Mi
  suscripción» de `frontend/app/activar/page.tsx`. Texto aprobado tras **cinco iteraciones** —
  registro profesional, indicativo sin condicionales, y Max enunciado como **REQUISITO** y no como
  consejo: *«Funciona con la suscripción que ya pagas. Requiere un plan Max: en planes inferiores un
  expediente extenso no cabe y genera cobros de crédito adicionales. Con Max no hay costo extra.»*
  Ver `feedback-copy-mia-registro-profesional` en la memoria del harness.
- Gate `test_cambio_de_motor_aviso.py` **26/26**; frontend compila (`tsc --noEmit` exit 0). El gate
  verifica el CONCEPTO y no la redacción, porque cablear la frase literal lo ponía rojo en cada
  mejora de copy.

## Qué sigue (en orden, sin necesitar a Pipe)

1. **ENGANCHAR EL AVISO A LA PANTALLA.** `aviso_cambio_de_motor` está calculado y probado pero nadie
   lo pinta: falta abrir `recolectar_cambios_de_motor` alrededor del turno en el grafo y mostrarlo.
   Es corto, y es lo único que quedó a medias de la sesión.
2. **EL ALCANCE EN EXPEDIENTES VOLUMINOSOS** — medido, no resuelto: 22% del expediente leído, y por
   eso se pierden datos de fecha. La lectura agéntica NO es la salida (está apagada bajo
   suscripción): las vías son subir la cobertura de la primera lectura o una **relectura dirigida sin
   herramientas** (código, no tool-calling del modelo). Es el trabajo de más valor pendiente.
3. **`execution/seed_despacho_demo.py`** (sigue sin existir): despacho de prueba CON PERFIL para
   poder capturar pantallas. Sin él no hay verificación visual de nada (regla 62).
4. Producto (plan maestro): bienvenida de F3.

## Pendientes de Pipe

- **Prueba del instalador en máquina limpia** (doble clic en frío). Nadie la sustituye; el checklist
  de 7 puntos es el riesgo #59.
- **Lectura de calidad** de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- **Los dos trámites de terceros:** Azure Trusted Signing y registro de apps OAuth
  (`docs/tramites-terceros-pipe.md`).
- **Decidir el alcance** (punto 2) si quiere una vía distinta a las dos propuestas.

---
