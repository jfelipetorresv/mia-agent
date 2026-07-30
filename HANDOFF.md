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

# CIERRE — 2026-07-29 (sesión 52) · Instalador re-ensamblado + caso de oro GRANDE + PRIMER PILOTO CON EXPEDIENTE REAL · EMPEZAR AQUÍ

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

# CIERRE — 2026-07-27/28 (4ª sesión) · SESIÓN PIPE A EJECUTADA: F2 cerrada + 4 barreras del harness

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada,
> arráncala: `tools\postgres16-portable\pgsql\bin\pg_ctl.exe -D tools\pgdata-portable -l
> tools\pg_start.log -o "-p 55432" start` (el `pg_ctl` no devuelve el prompt pero el motor
> arranca — comprobar con `pg_isready` o conectando). **La Sesión Pipe A YA SE HIZO**: las 7
> decisiones están en `memory/decisions.md` #45/#46/#47 y **F2 está CERRADA** (`memory/findings.md`
> §CIERRE DE F2). **Antes de comparar cualquier cifra con el pasado, leer los TRES CORTES DE SERIE
> de esa sección**: fuga (N-1), abstención (M-1) y `prompt_hash` (`3391f17ea61324a4` →
> `8388c516a2156de2`), más el cambio de composición del examen (los casos de RIESGO entran por
> defecto: 3 → 9). Lo que sigue está en «Qué sigue» abajo; lo único que espera a Pipe es la
> lectura de calidad de las 6 salidas y los dos trámites de terceros
> (`docs/tramites-terceros-pipe.md`).

Rama `feat/fase1-inc1-cleanup-scaffolding`. Pusheado hasta el commit de esta entrada.

## Qué pasó en esta sesión (2026-07-27/28, 4ª)

1. **La Sesión Pipe A se ejecutó completa** (salvo la lectura de calidad, que es juicio suyo).
   Siete decisiones tomadas en vivo, registradas en `memory/decisions.md` #45, #46 y #47.
2. **Las tres decisiones de medición, aplicadas y verificadas** (`656dc20`):
   - **N-1**: la regla del muro es «no afirmar una norma como aplicable sin respaldo», NO «no
     escribir jamás el número». Mención + negación explícita en la misma oración ya no es fuga.
     **Fuga real 0/63** recalculando los crudos guardados; el falso positivo de «Ley 4137»
     desaparece y ninguna cita realmente usada se escapa (checks G1-G9).
   - **M-1**: `ABSTENTION_PHRASES` recalibrado MIDIENDO los 62 borradores (11 → 46 formas).
     Cobertura 29/29 en suscripción (antes 0/30), 30/33 en nube. **Corte de serie declarado** —
     Pipe eligió declararlo en vez de pagar un re-baseline.
   - **M-2**: fuera «Éxito de tarea»; ahora «Turnos completados» + «Se negó correctamente» en los
     casos de RIESGO (10/10 nube, 9/9 suscripción sobre las sondas ya corridas).
3. **Las CUATRO barreras del harness de litigio de Pipe, portadas** (`99fb4a2`, `ba1fbde`,
   `ae42b96`). Decisión de dureza suya: **nacen como AVISO y solo suben a muro si se mide que no
   bloquean trabajo bueno**; el banco de citas quemadas es la única excepción (muro día uno).
   - **Afirmaciones negativas** verificadas contra el documento COMPLETO (no el fragmento ni el
     resumen de un extractor) + `retrieval.document_full_text` + regla y corolario en el prompt.
   - **Banco de citas quemadas** (migración **047**, tabla `burned_citations` con RLS): la cita
     que el abogado marca como falsa no vuelve a emitirse **ni con respaldo del corpus** — el muro
     va antes de toda vía de respaldo, que es como se coló el defecto original.
   - **Contaminación entre expedientes**: partes de OTRO asunto nombradas en el escrito. Catálogo
     DERIVADO de `documents.parte` del propio despacho — cero listas cableadas, agnóstico.
   - **Ninguna lección sin barrera**: regla de trabajo (reglas 55-61 de `APRENDIZAJES.md`).
4. **F2 CERRADA y alcance de la v1 ajustado** (#47): los casos de RIESGO entran al examen por
   defecto (`load_golden_cases` los incluye; el examen pasa de 3 a 9 casos y
   `test_gold_cases_influence_eval` ya deriva el número en vez de cablearlo), el «Modo A»
   (Docker/servidor) queda FUERA de la v1, y **los USD 22,6 del tope de nube quedan sin gastar**.
5. **Riesgo #81 CERRADO** con criterio + barrera (las tres partes: N-1, M-1, M-2).
6. Verificación en tres capas en cada bloque: unitaria (4 barreras nuevas: 27/27, 20/20, 17/17,
   18/18), independiente (`test_eval_harness` 67/67 con DB, panel 50/50, substance 51/51,
   sentence_report 47/47, mutación 50/50, omission 26/26, agnostic 104/104, META C 11/11) y en
   vivo (recálculo de los 63 crudos; ciclo real del muro contra la base con RLS entre dos
   despachos: `execution/test_citas_quemadas_db.py`). Gates HALT verdes: `test_rls` 19/19,
   `test_gates_no_ciegos` 9/9.

## Qué sigue (en orden)

1. **Helper de siembra para verificación visual** (`execution/seed_despacho_demo.py`, no existe):
   un despacho de prueba CON PERFIL, para poder capturar pantallas sin correr la entrevista.
   Motivo: el gate de bienvenida no se salta con `setup/steps/perfil/skip` (devuelve 200 pero
   mira si el perfil existe), así que hoy toda captura de UI cuesta 20 minutos de andamiaje y
   quedó SIN verificación visual el botón de marcar cita falsa y los dos avisos nuevos de la
   pantalla de revisión (regla 62 de `APRENDIZAJES.md`). El andamiaje que sí quedó listo: venv
   con Playwright y script de captura en el scratchpad de la sesión.
2. ~~Alta del banco de citas quemadas desde la interfaz~~ **HECHA** (`2c7ff04`): endpoint
   `/api/citas-quemadas` (POST/GET/DELETE, 18/18 con RLS por HTTP) + enlace «Esta cita no existe
   o no dice eso» en el diálogo de cada cita, y los avisos de afirmaciones negativas y
   contaminación entre expedientes ya se pintan.
2. **Caso de oro con expediente GRANDE** (cientos de fragmentos): sigue siendo el prerrequisito
   para decidir «lectura agéntica por defecto» (N-2). No requiere aprobación.
3. **Mostrar los avisos nuevos en la pantalla**: `afirmaciones_negativas` y
   `contaminacion_expediente` viajan en el informe de verificación y todavía no se pintan.
4. Producto (plan maestro): instalador y bienvenida de F3.

## Pendientes de Pipe

- **Lectura de calidad** de las 6 salidas de `docs/f1-paquete-decision-pipe.md` y del ejemplar
  `f2sond_entail_g`. Ningún agente lo sustituye.
- **Los dos trámites de terceros**, que decidió disparar: Azure Trusted Signing (firma de Windows)
  y registro de apps OAuth (Google/Microsoft). Pasos en `docs/tramites-terceros-pipe.md`.

---
