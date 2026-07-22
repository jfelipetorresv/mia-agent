## Checkpoint MÁS RECIENTE: sesión 48 (2026-07-16) — backlog de las tres auditorías CERRADO

**Rama:** `feature/robustecimiento-sin-aws`, repo limpio, sin push. Commits: `ca7cd74`
(ruta del motor), `960553b` (frontend), `902bd90` (agnosticismo backend), `c4b57f5`
(ejemplos del onboarding), `16e9eec` + `9a93341` (dos gates en rojo), `09d00c7`
(defaults del grafo).

**LA DB PORTABLE YA ARRANCA** (llevaba sesiones caída, lo que mantenía gates diferidos).
Cómo: `tools/postgres16-portable/pgsql/bin/pg_ctl.exe -D tools/pgdata-portable -o "-p 55432"`.
Trampas: el clúster es `tools/pgdata-portable`; a la copia mínima le faltaba `share/*` (se
copió del `-full` SIN machacar `share/extension/`, que es donde vive **pgvector 0.8.2**, que
el `-full` no trae); arrancar el clúster con los binarios del `-full` levanta el postmaster
pero **sus backends mueren con `0xC0000142`** (parece vivo y da ConnectionTimeout). El 5432
lo ocupa un PostgreSQL de sistema SIN pgvector — no confundirlos.

**Gates que estaban diferidos y hoy están VERDES:** `test_rls` 19/19 (HALT), `test_welcome_keys`
41/41, `test_setup_wizard` 28/28, `test_second_brain_ui` 27/27.

### A · Frontend (`960553b`) — confianza, agnosticismo, legibilidad
Cerrado TODO el backlog de Cursor + los 6 arreglos que Antigravity nunca llegó a implementar.
Deep-link al borrador (`/asuntos/{id}/revisar`) desde panel y lista; se consumen
`?sin_borrador`/`?confirmed` (antes se escribían y nadie los leía); fin de los fallos
silenciosos en `memoria` (drift por `status===409`, no por buscar "409" en el texto);
`AuthGate` con loader; fechas con el locale del abogado (cero `es-CO`); placeholders y
ejemplos sin sesgo de país; detonador de cuantía con UVT/UIT/UMA/IPREM/SMI/€ conservando
SMLMV; "Notas del despacho" ya no miente con "Próximamente"; Telegram avisa de sus pasos
guiados; token `--cta-strong` medido sobre el fondo REAL (`bg-cta/15`, no blanco): 5.10:1
reposo / 4.91:1 hover. Verificado: `tsc` limpio + `next build` completo (14 rutas).
**Revisión adversarial: 6 hallazgos, todos corregidos** — dos invalidaban objetivos que se
daban por cerrados (el botón "Revisar borrador" no funcionaba con TECLADO; el contraste se
había medido contra blanco y daba 4.46).

### B · Agnosticismo de jurisdicción (`902bd90`, `c4b57f5`, `09d00c7`) — REGLA DURA aplicada
La raíz estaba bien diagnosticada: el pack tenía `id_formats`/`doc_markers` **sin cablear**.
Movido al pack: formatos de ID (cédula/NIT/radicado/+57), pistas de dirección y stop-words
(`pii_hints.json`), léxico del buzón (`mail_signals.json`), seed de corpus como opt-in
(`baseline_corpus_seed`). Los 7 patrones CO se movieron a JSON **sin alterar un carácter**
(verificado contra HEAD): cero regresión para el fundador.

**DECISIÓN DE PIPE — anonimizador: "enmascarar todo, siempre".** Aplica TODOS los packs
instalados + base universal + respaldos por rol, **sin mirar la jurisdicción del despacho**;
por eso `jurisdictions` **desapareció de su API pública** (un llamador viejo revienta con
TypeError, no se le ignora en silencio). Sobre-enmascarar es aceptable; filtrar un dato por
ser de otro país, no. **Efecto conocido y aceptado:** `artículos 1494-1495` se enmascara como
teléfono y las cuantías las muerde el patrón de cédula (preexistente). Si el ruido pesa, ese
es el hilo — NO reintroducir una perilla por jurisdicción.

**Cuatro fugas de confidencialidad cerradas** (todas confirmadas ejecutando):
1. Un pack podía APAGAR la red pan-hispana con solo declarar un `role` → salían cédulas y DNI
   en crudo. Bastaba un typo, sin malicia. (La encontró la revisión adversarial; el test del
   agente probaba el camino que SÍ funcionaba: regex inválido.)
2. Preexistente: un despacho colombiano dejaba salir el DNI de un cliente español.
3. El respaldo de teléfono no cubría separadores: `615 55 12 34` salía crudo.
4. `resolve_jurisdictions` no distingue "eligió generic" de "nunca lo configuró" → un despacho
   sin configurar habría perdido cédula/NIT.

**El conocimiento ya no nace colombiano** (`09d00c7`): la jurisdicción al escribir se decide
en Python (explícita → pack del tenant → `'generic'`, nunca `'co'`); migración **036** deja el
DEFAULT en `'generic'` para `legal_norms`, `jurisprudence` y `firm_profiles`. Sin un solo
UPDATE: el material del fundador no se re-marca (verificado: co=26, co=13, colombia=6,
idénticos). **El peor defecto no estaba en el inventario:** `firm_profiles` tenía DEFAULT
`'colombia'` y `auth.py` inserta sin jurisdicción → **todo despacho nuevo nacía colombiano**.
También `corpus_factory` marcaba como colombiano el catálogo del pack español.

### C · DOS GATES LLEVABAN SESIONES EN ROJO sin que constara (`16e9eec`, `9a93341`)
Ambos sobre DINERO, y en ambos el código era correcto: el test se quedó con una regla anterior.
La línea base de "84 suites ALL PASS" **no era cierta**; conviene desconfiar de ella.
- `test_connector_hardening` (35/36 desde la sesión 47): exigía que 'suscripcion' NUNCA usara
  OpenRouter, pero `b582541` extendió el overflow por decisión de Pipe ("Ambas"). Se conserva
  lo que sí protege ('soberano' jamás) y se añade el caso que faltaba (sin opt-in tampoco).
- `test_value_delivered` (26/27 desde `f147fb9`): exigía costo 0 para un alias sin precio, pero
  el control atómico del gasto lo cambió a tarifa conservadora de Sonnet — correcto: con 0 el
  tope mensual no frena y el abogado cree que no gastó.

### D · Agent Hub y Banco de oro: CONSTRUIDOS (`65e521d` backend, `84a059b` UI)
Pipe pidió pantalla para ambos. **Las dos tenían API pero estaban muertas por dentro**;
montar la UI encima habría sido prometer lo que no se cumple, así que se cablearon primero
(decisión de Pipe: "cablearlo de verdad y luego la pantalla").

**Agent Hub — la delegación no existía.** `graph.py` leía `metadata['delegate']` y NADIE lo
escribía. Ahora MIA delega SOLO si el abogado nombra al ayudante en su mensaje con un verbo
de orden (`agents/delegate_intent.py`, determinista, sin LLM). **Se descartó el tool-calling
a propósito:** darle el gatillo al modelo convierte una inyección indirecta desde un
documento del propio expediente en una fuga. Candado en `gateway/hub_gate.py` (hermano de
`notebooklm/gate.py`): con `soberano` NO se delega aunque esté habilitado; la política se lee
con `model_policy_for_strict`, que LANZA si la DB falla — un error de infra jamás abre la
salida. Verificado a mano: soberano→bloquea, nube→permite, DB caída→bloquea. Sale solo el
mensaje del abogado (ni documentos, ni hechos, ni perfil, ni historial). **No pasa por
`anonymize` a propósito** (rompería el encargo — "busca el radicado RADICADO_1" no se puede
buscar — y daría falsa seguridad sobre prosa libre). Bug de raíz cerrado: `set_enabled` hacía
read-modify-write y activar un ayudante podía **revertir un cambio simultáneo de
`model_policy`, resucitando una política que el despacho acababa de endurecer**.

**Banco de oro — tenía TRES bloqueos, no uno:**
1. `allow_eval_real_data` solo se LEÍA: no había forma de concederlo y el 403 mandaba "a
   Configuración", donde no había nada → `GET|PUT /settings/eval-consent`, fail-closed. Ojo:
   el merge `||` de jsonb es superficial y habría borrado el resto de `config['eval']`.
2. No se podía releer un caso → `GET /api/gold-cases/{id}`. Nunca devuelve `anon_map`.
3. **La UI no podía armar el caso:** los documentos solo exponen metadatos y el borrador se
   borra del checkpoint al terminar el turno, justo cuando se captura. Ahora `:draft` lo arma
   **server-side** desde el `matter_id` → el material sin anonimizar NUNCA pasa por el
   navegador. Fuentes: `traces.input/output` del último turno approved|edited (rejected
   fuera); `chunks ⋈ documents`. Topes explícitos (20 docs / 60 fragmentos) avisados con
   números, nunca recorte silencioso.

**Deuda conocida de esto:** (a) **D3 sigue abierto** — los flags de los CLI nunca se han
confirmado contra un `--help` real, así que la salida del ayudante va a `metadata` y NO entra
en la cadena de razonamiento jurídico; la primera invocación real puede fallar (degrada
limpio y avisa, pero "funciona" está SIN verificar en vivo). (b) **El diagnóstico del turno
no se persiste en ninguna parte** (vive en el checkpoint y se borra): por eso las
conclusiones clave llegan vacías y las escribe el abogado. Es dato de valor que se tira cada
turno — hilo abierto si Pipe quiere conservarlo. (c) `index_trace` es best-effort: si esa
fila falla, el asunto queda incapturable y el 409 dirá "aprueba el borrador primero" a quien
sí lo aprobó.

### D2 · Moneda: CERRADO — todo en dólares (decisión de Pipe)
Pipe primero dijo "lo lógico es el peso de cada jurisdicción" y, al ver el nudo, corrigió a
**todo en dólares**. El nudo era real: con la tarifa en pesos y el gasto de IA en USD, el
"valor neto" (`ux.py:1581`, `gross - cost`) mezclaba monedas → o mentía o exigía inventar una
tasa de cambio. **No se tocó nada** (el trabajo se paró a tiempo, solo se había leído código).
Si algún día un despacho pide su moneda, hay que resolver la conversión de verdad.

### E2 · CP-HUB2 + los 8 principios (`65e521d`, `84a059b`, `aa8ac3a`, `9019ee6`, `47f5578`)
**Delegación — decisión de Pipe: "MIA decide y me pregunta".** Rechazó la invocación explícita
como única vía: *"parte del encanto de MIA es que puede determinar si necesita agentes o
subagentes"*. Tenía razón, y además **MIA ya orquesta subagentes PROPIOS sin candado y así debe
seguir** (`agents/delegation.py`: swarm interno por `call_llm` → no sale nada del equipo). El
debate era solo con los 5 ayudantes EXTERNOS. Modos: `preguntar` (default) / `autonomo` /
`solo_si_lo_pido` (`GET|PUT /settings/delegation-mode`).
- **La trampa que casi lo rompe:** LangGraph re-ejecuta el nodo al reanudar. Un nodo que
  decidiera-y-preguntara volvería a llamar al modelo al aprobar y podría sacar **otro texto**:
  la pantalla sería teatro. Por eso está partido — `intake` **planifica** y persiste el plan;
  `delegation_node` solo interrumpe y lee del estado. Hay test que cambia lo que el modelo
  respondería entre proponer y aprobar y exige que salga el texto viejo.
- **Dos pausas que no se pueden confundir:** aprobar el BORRADOR no puede reanudar la pausa del
  AYUDANTE (el texto saldría sin verse). Separadas por nodo y por payload.
- **FUGA PREEXISTENTE CERRADA:** `_maybe_delegate` leía `_last_user_message`, que con
  `@expediente` lleva **pegado el contenido de los documentos** (CP-E2): **el expediente entero
  salía al CLI de un tercero**, contra el contrato escrito en el propio módulo. Ahora
  `retrieval_query`.

**Los 8 principios** (destilados de los skills y el vault de Pipe, sin clonar nada suyo; lo
colombiano y el estilo Lexia se descartaron por diseño). El hallazgo que los ordenó: **MIA está
construida para no mentir, no para argumentar bien** — y **aprendía de Pipe sin volver a leer
jamás lo aprendido**.
- **La Sala de estrategia existía y el redactor NUNCA la consultaba.** Ahora su dictamen (ya
  pagado y persistido) se inyecta sellado en el borrador. Se descartó correrla por turno: ~9
  llamadas contra las 4 del turno → triplica la factura. Coste: 0 llamadas nuevas.
- **Anatomía del argumento** en la capa 2 (cacheada, +238 tokens una vez) + jerarquía 80/20 +
  `facts` que explota las inconsistencias en vez de describirlas.
- **El examen mide sustancia** (`aa8ac3a`): 3 señales deterministas; se RECHAZARON 3 que no se
  podían medir sin mentir (confrontación → solo por léxico, gameable con una palabra;
  consecuencia → depende de fórmulas de un país; 80/20 → probado, NO discrimina). Van como
  **indicios informativos**, no en `ok`: meterlas en el contrato volvería rojos de golpe los
  casos de oro ya aprobados.
- **El wiki era de SOLO ESCRITURA:** `search_wiki()` sin un solo llamador. Cableado, fenceado
  como inferido y NO citable. Antes hubo que arreglar la confianza, que era un **trinquete**
  (solo subía; 9 toques → 1.0; nunca bajaba ante un rechazo).
- **`dreams` escribía SOUL sin permiso, sin tope y sin versión** — y estaba **PROTEGIDO POR UN
  TEST** que exigía ese comportamiento ("Nudges actualiza SOUL"): hubo que invertirlo. Ahora
  propone; el tope RECHAZA (no trunca). La instrucción directa de Pipe se aplica sin
  re-preguntar.
- **El Curator fusionaba contradicciones** (coseno >0.85): "siempre X" y "nunca X" acababan en
  un texto que no dice ninguna. Ahora juez barato + umbral 0.85 y **fail-soft a duplicado** (un
  falso positivo interroga al abogado, deja de aprobar, y la memoria deja de aprender).
- **Obsidian:** el frontmatter entraba como basura y los `[[wikilinks]]` no se parseaban — MIA
  leía el segundo cerebro del despacho como un PDF.
- **Otra fuga cerrada:** `wiki_dir()` interpolaba el `tenant_id` en la ruta **sin sanear** —
  inofensivo mientras solo se escribía; primitiva de lectura al wiki de OTRO despacho en cuanto
  se cableara la lectura.
- **Y otra:** el prompt del NER decía *"anonimizar un texto jurídico colombiano"* (`47f5578`).
  Se le escapó a TRES auditorías del mismo archivo el mismo día: todas miraban los patrones,
  ninguna leyó el prompt.

**Deuda de esto (leer antes de tocar):** (a) **D3 abierto** — los flags de los CLI nunca se han
probado contra un `--help` real; la salida del ayudante va a `metadata` y NO al razonamiento; la
primera invocación en vivo puede fallar (degrada limpio, pero "funciona" está SIN verificar).
(b) El **juez de conflictos** está probado en cableado, **no en puntería** (los gates corren sin
red). El siguiente paso honesto es un set etiquetado de pares reales contra el modelo vivo.
(c) **El diagnóstico del turno no se persiste** (checkpoint → se borra): las conclusiones clave
del banco de oro llegan vacías y se tira dato de valor cada turno. (d) El archivo **"Patrones
rechazados"** de `dreams` sigue sin llegar al modelo (confidence hardcodeada). (e) **El hilo de
mensajes del asunto no sobrevive a un F5** (no hay endpoint de historial; los turnos están en
`traces` y nadie los muestra). (f) **SOUL/wiki/trazas viven en ficheros SIN RLS**: el
aislamiento depende de sanear el nombre de fichero. (g) **El número de migración se reserva al
EMPEZAR, no al escribir**: dos agentes crearon el mismo `038` y hubo que renumerar (soul → 040).

### E · Pendiente técnico (reportado, no tocado — con su razón)
- **FTS `'spanish'`**: vive en columnas `GENERATED ALWAYS AS ... STORED` + triggers (003/004/013
  + schema.sql); cambiarlo exige migración de índices y reindexado. No es cosmético.
- **Voz TTS `es_MX`**: el asset lo eligió Pipe de oído y lo baja `install.py`; voz por despacho
  exige empaquetar una voz por variante.
- **Capa 3 de Pipe (lo que él pidió reservarse):** E2E del instalador en máquina limpia y el
  recorrido visual; login/registro reales del NotebookLM.

---

