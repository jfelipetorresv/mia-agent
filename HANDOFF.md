# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint: robustecimiento local sin AWS (2026-07-14) — supervisor autorreparable

- La cáscara Tauri vigila cada 5 segundos backend, frontend y LiteLLM después del arranque.
  Exige 3 fallos consecutivos, reinicia únicamente hijos propios y se detiene tras 3 recaídas
  por hora. Los servicios adoptados se observan y avisan, pero nunca se matan ni reemplazan.
- El reinicio automático del motor comparte exclusión con el reinicio manual y revalida salud
  después de tomarla; así no actúa sobre un PID nuevo usando un sondeo viejo. `shutdown()` sigue
  gobernando el cierre y `register_child()` mata cualquier hijo creado después de cerrar.
- `RuntimeHealthBanner` muestra recuperación/error en lenguaje llano dentro de la app; en navegador
  normal no aparece. Gates: `cargo check` PASS, tests Rust 3/3, gate estático PASS, `tsc` PASS y
  build Next 15/15. Claude Code re-auditó la carrera y dio **PASS sin bloqueantes**.

---

## Checkpoint: robustecimiento local sin AWS (2026-07-14) — control atómico de gasto

- Rama local `feature/robustecimiento-sin-aws`; todavía no se ha hecho push. Esta fase añade
  `035_atomic_ai_budget.sql`: cada llamada pagada reserva saldo en PostgreSQL antes de salir y
  liquida el costo real al terminar. Dos trabajos simultáneos ya no pueden atravesar juntos el tope.
- `turn_usage` conserva el detalle; `ai_budget_months` es el saldo mensual autoritativo desde la
  primera reserva, para no depender del buffer. Motores de suscripción/local no reservan; si un
  motor pagado no cabe y existe respaldo gratuito, Mia degrada a este sin detener el trabajo.
- Un corte incierto conserva la estimación por prudencia; una liberación con fallo transitorio de
  DB reintenta tres veces. RLS forzado mantiene las reservas aisladas por despacho.
- Gates: `test_atomic_ai_budget` 11/11, `test_observability` 22/22,
  `test_llm_fallback` 25/25 y `test_migration_ledger` PASS. Claude Code encontró el riesgo de
  liberación transitoria, se corrigió, y su segunda auditoría dio **PASS sin bloqueantes**.

---

## Checkpoint más reciente: Sesión 47 (2026-07-13/14) — Sala de estrategia (War Room) + OpenRouter como motor propio/respaldo

> Sesión que RETOMÓ tras un "error del computador". Diagnóstico: NO se dañó el repo de MIA
> (`mia/.git` intacto y sincronizado); lo dañado fue un `.git` fantasma y vacío en la carpeta
> contenedora `Mia-Super Agent/` (un `git init` viejo, sin remoto), que se limpió. Regla para el
> futuro: el repo de trabajo es `mia/`, no la raíz — usar `git -C mia`.

### Qué se hizo esta sesión (lenguaje simple)

Dos features nuevas, en paralelo, con orquestación multi-agente (recon → ejecución → auditoría
adversarial → corrección), ambas pusheadas a `main`:

- **Sala de estrategia (commit `e8bcc51`)** — pivote de la apuesta #2 de NotebookLM (era un
  podcast de audio; Pipe lo giró a un **debate ESCRITO** tipo "War Room"). En un ASUNTO con
  expediente, el abogado convoca un panel de 3-4 counsel con posturas OPUESTAS (defiende tu tesis
  / contraparte / juez escéptico / especialista); cada uno analiza el caso citando el expediente
  `[doc n]`, se contrastan en una ronda de réplicas, y un moderador sintetiza un dictamen
  (fortalezas / riesgos / puntos ciegos / estrategia / próximo paso). **Decisiones de Pipe:** MIA
  propone el panel y el abogado lo ajusta; salida = conclusiones arriba + debate desplegable
  abajo; cierre = dictamen + botón "convertir en borrador" (pasa por el gate de citas y HITL
  normales); solo ASUNTOS; nombre de cara al abogado = "Sala de estrategia" (§G, nunca "agente").
  Reutiliza personas.Persona, delegation.run_parallel (patrón research_swarm),
  untrusted.render_documents y verification.annotate_draft en CADA intervención y la síntesis.
- **OpenRouter como motor propio + respaldo (commit `b582541`)** — el abogado conecta su propia
  cuenta de OpenRouter (y la carga de crédito) para usar MIA (1) como MOTOR PRINCIPAL (política
  nueva "openrouter", para despachos sin la suscripción del equipo) y (2) como RESPALDO/overflow
  (en "suscripción"/"nube", con opt-in `allow_openrouter`). Validación en vivo de la clave en
  `/activar` (4ª opción de motor) + activación en caliente.

### Frontend a revisar (Cursor/Pipe — capa 3)

- **Sala de estrategia (TODO NUEVO):** `frontend/app/asuntos/[id]/page.tsx` (botón "Convocar Sala
  de estrategia" en la barra de acciones + estado del stream) y `frontend/app/asuntos/[id]/
  _components/SalaEstrategia{Dialog,Result}.tsx` + `warroom-types.ts`. Recorrido: en un asunto CON
  expediente, convocar la sala → ajustar el panel → ver el debate en vivo (rondas) → dictamen con
  conclusiones + debate colapsable → "Descargar en Word" y "Convertir en borrador". Sin expediente
  debe mostrar aviso en llano (no error mudo).
- **OpenRouter:** `frontend/app/activar/page.tsx` — la 4ª tarjeta de motor "Tu cuenta de
  OpenRouter" con su campo de clave (✓ en vivo) y, en otras políticas, el campo opcional "más uso".

### Resultado de verificación (3 capas)

- **Capa 1 (regresión, DB dev en 55432):** test_warroom **52/52**, `test_rls` **19/19** (HALT,
  +7 checks nuevos de `warroom_results` con RLS fail-closed), `check_env_pins` **9/9** (HALT),
  test_doc_citation_guard **19/19**, CP9 test_document_pipeline **45/45**, test_openrouter_policy
  **16/16**, test_welcome_keys **41/41**, test_litellm_packaging **66/66**, test_model_policy
  **40/40**, test_llm_fallback **25/25**, test_agent_core **26/26**. `tsc --noEmit` verde; `npm run
  build` compila 15/15 páginas (queda un flake ambiental de Windows al generar `500.html`, ajeno
  al código — se reproduce en árbol pristine).
- **Capa 2 (DOS auditorías adversariales independientes):** 0 BLOQUEANTES. **Sala:** aislamiento
  entre despachos y gate de citas OK; 2 mayores + 5 menores corregidos (réplicas desalineadas ante
  fallo parcial de un panelista; error invisible sin expediente; inyección de 2º orden entre
  intervenciones ahora SELLADA con `untrusted.fence_block`; degradación por presupuesto funcional
  a 0.85 del tope; clamp del tamaño de panel en el SSE; agentes reales sin clonar "defensor";
  cobertura RLS de la tabla nueva). **OpenRouter:** la **muralla de confidencialidad SE SOSTIENE**
  ("soberano" jamás enruta a la nube por ningún fallback; la clave nunca se filtra); 1 mayor + 3
  menores corregidos (overflow inerte tras reinicio en caliente → helper `_openrouter_key_present`
  con cache 5s lee el `.env`; auto-omisión del wizard sin la clave del motor; landmine de
  `AgentCore.model` → default None).
- **Capa 3: PENDIENTE — de Pipe** (recorrido visual en vivo de ambas features).

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** recorrer la Sala de estrategia y la nueva opción de OpenRouter en vivo
   (encender MIA Modo B; la DB dev ya quedó arriba en 55432).
2. **ACCIÓN DE PIPE (deuda de OpenRouter):** confirmar los slugs EXACTOS de los modelos en
   openrouter.ai/models (`anthropic/claude-sonnet-4.6`, `anthropic/claude-haiku-4.5`). Un slug
   errado degrada a `mia-local` sin romper, pero pierde el motor OpenRouter en silencio.
3. Acciones de Pipe sin cambio: firma digital (Azure Trusted Signing) + apps OAuth; capa 3 en
   frío del instalador (bloque instalador). Apuesta #3 de NotebookLM (transformaciones al ingerir)
   sigue diferida.

### Trabajo en background sin leer

Nada — 2 recon iniciales (ClaudeClaw, sistema de motor), 3 recon de MIA, 5 ejecutores, 2 auditores
adversariales y 2 correctores: todo leído y reflejado aquí. La regresión la corrió esta terminal.

### Decisiones tomadas y suposiciones declaradas

- **El "War Room" de ClaudeClaw NO existe** (se verificó el zip): ClaudeClaw solo tiene delegación
  1-a-1 + hive mind, no un panel que debate. La Sala de estrategia es diseño propio de MIA.
- **Panelistas sintéticos de código** (`WARROOM_STANCES`, 4 posturas) reemplazables por Agentes
  del despacho — no depende de que el despacho haya creado personas.
- **Política "openrouter" = consentimiento por selección** (no depende de `allow_openrouter`); el
  overflow en "suscripción"/"nube" SÍ exige el opt-in (gate de confidencialidad CP-S3).
- Las dos features tocan archivos DISJUNTOS (Sala: warroom/ux/asuntos/033; OpenRouter:
  llm/config/welcome/settings/activar/yaml) → paralelo seguro sin colisión ni migración compartida.

---

## Nota paralela (2026-07-12, sesión Fable) — Refuerzo del gate de citas: guardián de referencias [doc n] fantasma

> Vía SEPARADA del bloque instalador (no lo toca). Registrada aquí a pedido de Pipe porque él estaba
> corriendo otra sesión al mismo tiempo. Backend Python puro, sin dependencias nuevas, sin cambios en
> `packaging/`/`desktop/` → no afecta el instalador ni el build en caliente.

### Qué se hizo (lenguaje simple)
Punto de partida: se analizó el repo externo `earlyaidopters/notebooklmreimagined` para sacar ideas
para MIA. De ahí salieron 3 apuestas; se implementó la #1 (la de mayor impacto y menor riesgo).

**El hueco que cierra:** cuando MIA redacta y "cita" un documento del expediente (ej. "según el poder
[doc 9]"), nadie comprobaba que ese documento existiera. Si solo se recuperaron 5 documentos y el
modelo inventaba un `[doc 9]`, esa cita pasaba **como si estuviera respaldada**. Ahora un guardián
determinista detecta toda referencia `[doc n]` fuera del rango real y le añade `[VERIFICAR]` — igual
que cualquier cita sin respaldo (nunca borra ni bloquea; solo avisa). Es el análogo de la técnica de
"lista blanca de IDs" de NotebookLM/open-notebook, aplicada al diferenciador #1 de MIA.

### Archivos (commit `ec1aa15` en `main`, ya pusheado a GitHub)
- `backend/mia/agents/verification.py`: `flag_phantom_doc_citations()` + `highest_sealed_doc_index()`
  (el rango válido sube al mayor `<<<DOC n>>>` que vio el modelo, incluyendo adjuntos por `@expediente`,
  para no marcar como fantasma una cita legítima a un adjunto). `annotate_draft` gana el parámetro
  opcional `num_documents` (retrocompatible; corre el guardián DESPUÉS del escáner legal).
- `backend/mia/agents/graph.py` (`_verify_draft`): cablea el rango = max(docs RRF, adjuntos sellados).
- `execution/test_doc_citation_guard.py`: gate nuevo, **19/19**, sin DB/red.

### Verificación (3 capas)
- **Capa 1:** test 19/19; AST OK; firma retrocompatible (el nodo research y `eval/scoring.py` no cambian).
- **Capa 2:** revisor independiente con contexto fresco → halló 1 falso positivo real (cita legítima a
  adjunto `@expediente`) → **corregido + test**. Demás hallazgos van en dirección segura (documentados).
- **Capa 3 (visual):** N/A — no se tocó frontend. El informe de verificación solo gana una clave
  aditiva `docs_fantasma` (no rompe render). *Opcional a futuro:* la Pantalla 2/3 podría mostrar el
  conteo de referencias fantasma detectadas.

### Alcance y pendientes
- **Cubre el flujo de ASUNTO** (verification_node). **El flujo de PROYECTO (work_node) NO pasa por
  verificación** — hoy su respuesta llega sin red de `[VERIFICAR]`. Decisión de diseño a **confirmar
  con Pipe** si quiere extenderlo.
- **Apuestas #2 y #3 DIFERIDAS** (en memoria `mia-notebooklm-apuestas`): #2 audio del expediente en
  modo debate/crítica (necesita voz multi-locutor = pesos nuevos, zona sensible del instalador →
  retomar al cerrar el instalador); #3 transformaciones al ingerir (extraer pretensiones/hechos/
  cronología al subir; toca la ruta de upload, riesgo medio).

### ⚠️ Incidente de sesiones concurrentes (resuelto, sin pérdida)
Había otra sesión corriendo sobre el mismo repo; las operaciones de git chocaron. **Desenlace limpio:**
el commit del banco de oro quedó en `bfa7d07`, este trabajo en `ec1aa15`, historia lineal, nada perdido.
La carrera dejó un conflicto de `git stash pop` (autostash) en `memory/session-summaries.md` que se
resolvió conservando TODO el contenido (lo stasheado era una entrada vieja ya presente en el archivo);
el autostash ya se descartó tras confirmar que no aportaba nada. **Recomendación: no correr dos sesiones
que hagan git sobre el mismo repo a la vez.** (Confirmado en vivo por la sesión de Claude que desenredó
el choque; guardián verificado a fondo en capa 2 — sin falsos positivos, CP9 45/45 sin regresión.)

---

## Checkpoint más reciente: Sesión 46 (2026-07-12) — PULIDO PRE-PRUEBA: Riesgo #60 cerrado + auditoría final de seguridad/bugs + pre-flight del motor sin llaves

### Qué se hizo esta sesión (lenguaje simple)

Pipe pidió, antes de instalar en frío, "dejarlo listo para pruebas": mejorar lo que quedaba, revisar
seguridad y bugs, y solucionar lo que saliera. Se corrieron **tres auditorías adversariales
independientes** (seguridad, corrección/E2E en frío, y revisión del diff) — **0 bloqueantes en todo**.

- **Se cerró el Riesgo #60 (mejora que Pipe pidió expresamente):** el motor de modelos ahora se
  **reinicia solo, en caliente**, cuando el abogado guarda su clave en la pantalla de bienvenida —
  ya NO hay que cerrar y reabrir MIA. Se implementó vía un comando interno de la cáscara Tauri
  (`restart_litellm`): el frontend, que corre dentro de la cáscara, lo invoca tras guardar la clave;
  la cáscara mata el motor viejo, espera a que libere el puerto y lo re-lanza leyendo la clave nueva,
  re-asignándolo al Job Object anti-huérfanos. En modo desarrollo (navegador) degrada solo al aviso
  de "reabre Mia", sin romper nada.
- **Se eliminó la única incógnita real de tu prueba (pre-flight del motor sin llaves):** nadie había
  encendido `mia-litellm.exe` con CERO llaves de proveedor, que es exactamente el estado del arranque
  en frío cuando el abogado difiere las claves. Se probó: arranca en ~1 s, responde salud y lista los
  5 modelos. Ya no es un riesgo.
- **Dos endurecimientos de seguridad baratos:** validación anti-inyección extra al escribir el `.env`
  y permisos restrictivos (solo el dueño) sobre el archivo de claves.

### Frontend a revisar (Cursor — capa 3): un cambio mínimo
`frontend/app/activar/page.tsx` (`finish()`): tras guardar la clave, si corre dentro de la cáscara,
invoca `restart_litellm` y, solo si el motor se reinició, quita el aviso "cierra y reabre". En
navegador (dev) el aviso se conserva. Cubierto por gate + revisión; falta el recorrido visual en vivo.

### Resultado de verificación (3 capas)
- **Capa 1:** `cargo build` exit 0; `test_shell_hardening` **84/84** (sube de 77 con 7 checks nuevos
  del reinicio), `test_packaging` 23/23, `test_litellm_packaging` 60/60, `test_first_run` 68/68.
  **NO se re-corrieron `test_welcome_keys` ni `test_rls`** porque la DB dev de mia no estaba encendida
  (puerto 55432); el único cambio en esa ruta (validación `\n`/`\r` en `env_writer`) se micro-probó
  aparte. **Pendiente: correrlos en el próximo arranque con la DB arriba.**
- **Capa 2:** revisor adversarial independiente de concurrencia/ciclo de vida sobre el diff de la
  cáscara — **0 bloqueantes, 0 mayores** (sin deadlocks, ningún Mutex cruza `await`, el flag de
  reinicio no se fuga, el proceso re-lanzado se re-asigna al Job, caminos "no-aplica" seguros para
  dev/adoptado/cerrando). 3 menores cosméticos/pre-existentes, ninguno rompe la prueba.
- **Capa 3: PENDIENTE — de Pipe (sin cambio respecto a F4):** el E2E en frío en máquina 100% limpia
  sigue siendo el único pendiente para cerrar el bloque instalador. Ahora, al guardar la clave de
  respaldo en `/activar`, el motor debe quedar activo SIN reabrir (antes obligaba a reabrir).

### Pendientes y próximo paso
1. **Capa 3 de Pipe:** E2E en frío (doble clic → primer arranque → viaje de bienvenida → guardar clave
   y ver que el motor queda activo sin reabrir). En `desktop/src-tauri/target/release/bundle/nsis/`.
   Nota: el `.exe` en el bundle es de la sesión 45; si se quiere probar el reinicio en caliente del
   #60 hay que RE-ENSAMBLAR el instalador (`packaging/build_installer.ps1`) para incluir la cáscara
   recompilada de esta sesión.
2. **Correr `test_welcome_keys` + `test_rls`** con la DB dev encendida (verificación diferida de capa 1).
3. **Deuda consciente nueva (Riesgo #61), NO bloquea la prueba:** identidad de cáscara falsificable
   solo por un atacante local (aceptado en modelo mono-abogado); carpeta de datos = carpeta de
   programa (aplazado); el setup no re-corre migraciones en una actualización futura (deuda de
   "update").
4. **Acciones de Pipe sin cambio:** firma digital (Azure Trusted Signing) + registrar apps OAuth.

### Trabajo en background sin leer
Nada — 3 auditores (seguridad/bugs/diff), 1 ejecutor y 1 recon de diseño: todo leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas
- **El reinicio del motor lo dispara el frontend, no el backend:** el frontend ya vive dentro de la
  cáscara Tauri (`withGlobalTauri`), así que invoca el comando directo; el backend Python no tiene
  canal hacia la cáscara. Más limpio y sin dependencias nuevas.
- **El aviso "cierra y reabre" solo se borra si el motor confirma que se reinició** (no incondicional):
  si el motor fue adoptado o hay un reinicio en curso, se conserva el aviso — más honesto.
- **Se corrigió lo barato y se DOCUMENTÓ lo riesgoso** (Riesgo #61): cambiar el layout de carpetas o
  la firma de identidad justo antes del E2E en frío es más peligroso que el problema que resuelven;
  mejor con la prueba de Pipe como red.
- Los comandos de app de Tauri v2 no requieren ACL de capabilities (la CSP ya permite `ipc:`).

---

## Checkpoint anterior: Sesión 45 (2026-07-11) — BLOQUE INSTALADOR: Fase 4 (instalador de doble clic) ENSAMBLADA — falta SOLO el E2E en frío de Pipe

### Qué se hizo esta sesión (lenguaje simple)

Se armó el **instalador de doble clic** que un abogado usa para instalar MIA sin tener Python,
Node ni base de datos en su computador. La cáscara de escritorio no empaqueta sola los motores,
así que se cableó cómo se colocan todos junto al programa y se incluyó una **base de datos
portable con el buscador vectorial adentro**. Resultado real y probado: `Mia_0.1.0_x64-setup.exe`
(~452 MB), que instala sin pedir permisos de administrador y **funciona sin internet**.

- **Ensamblaje (`packaging/build_installer.ps1` + `tauri.conf.json`):** recompila los tres motores,
  copia el PostgreSQL portable (con pgvector) y arma el instalador NSIS. Cada motor + el archivo
  de arranque quedan **directamente junto al programa** (verificado instalando en una carpeta
  aislada: nada queda mal ubicado — era la duda central de esta fase).
- **La incógnita crítica se resolvió a favor:** la cáscara busca los motores en rutas fijas junto
  a su exe, y ahí quedan exactamente. Instalación de prueba: 804 MB en disco, todo en su sitio.

### Frontend a revisar (Cursor — capa 3): NO APLICA
Esta sesión fue empaquetado + cáscara (Rust) + scripts. No hay UI nueva. La capa 3 pendiente es
de **Pipe**, no de Cursor (ver abajo).

### Resultado de verificación (3 capas)

- **Capa 1:** gates del instalador verdes — `test_installer_bundle` 30/30 (NUEVO), `test_packaging`
  23/23, `test_litellm_packaging` 60/60, `test_frontend_packaging` 24/24, `test_shell_hardening`
  77/77, `test_first_run` 68/68 — + HALT `test_rls` 12/12 y `check_env_pins` 9/9 + `test_welcome_keys`
  39/39. Línea base sube de 85 a 86 suites. Instalador producido y verificado por instalación
  aislada (payloads junto al exe, sin subcarpeta `resources/`, pgvector presente, pgAdmin ausente).
- **Capa 2:** TRES revisores adversariales independientes (seguridad, corrección/build, coherencia
  cáscara/§G). **0 BLOQUEANTES**, ningún secreto de Pipe viaja en el instalador, DB bien endurecida.
  **5 correcciones aplicadas y re-verificadas:** (1) **console REVERTIDO a True** — la cáscara ya
  oculta la ventana con CREATE_NO_WINDOW; el `console=False` que se había puesto vaciaba el stdout
  con el que el primer arranque le dice al abogado *por qué* falló (regresión introducida y
  corregida en la misma sesión); (2) **frontend atado a 127.0.0.1** — estaba en 0.0.0.0, visible
  para toda la red del despacho; (3) **pgAdmin fuera** del paquete de base de datos (−736 MB:
  860→124 MB, y menos superficie de ataque); (4) **WebView2 `offlineInstaller`** para instalar sin
  internet; (5) gate endurecido. Detalle en `memory/session-summaries.md` sesión 45 y Riesgo #59.
- **Capa 3: PENDIENTE — de Pipe (ÚNICO pendiente de F4):** instalar el `.exe` en una **máquina
  100% limpia** (sin Python/Node/Postgres, estado virgen) con doble clic y confirmar el primer
  arranque en frío + el viaje de bienvenida. Es física: no se puede hacer en la máquina de dev
  (tiene el entorno + colisión de puerto 55432). El instalador está en
  `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`.

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** el E2E en frío en máquina limpia (arriba) — cierra el bloque instalador.
2. **Riesgo #60 (ola futura):** el reinicio automático del motor de modelos tras guardar la clave
   en el wizard NO se hizo en F4 (requiere IPC de Tauri); la mitigación de F3 (clave obligatoria +
   aviso de reabrir) sigue vigente.
3. **ACCIÓN DE PIPE (sin cambio):** firma digital (Azure Trusted Signing) para vender sin la
   advertencia de "editor desconocido" de Windows, y registrar las apps OAuth.

### Trabajo en background sin leer
Nada — 1 recon, 2 builds delegados y 3 revisores de capa 2: todo leído y reflejado aquí. La
instalación de prueba del build corregido la corrió y verificó la propia terminal (804 MB, layout
correcto) y se limpió (carpeta + clave de registro).

### Decisiones tomadas y suposiciones declaradas

- **console=True (no False):** la ventana negra la elimina la cáscara con CREATE_NO_WINDOW, no el
  spec; windowed rompía el diagnóstico del primer arranque. Cierra Riesgo #59 pt 3/7 por diseño.
- **installMode currentUser:** instala sin pedir administrador (más fácil para el abogado, §B);
  si algún día se quisiera "para todos los usuarios" cambia a perMachine (implica UAC).
- **WebView2 offlineInstaller** (+~130 MB al instalador) elegido sobre el descargador para que el
  E2E en frío/offline no falle — coherente con local-first. Reversible en `tauri.conf.json`.
- **pgAdmin/StackBuilder excluidos** del pgsql: MIA nunca los usa (conecta por psycopg + initdb).
- El Postgres portable se toma de `..\tools\postgres16-portable-full\pgsql` (fuera del repo);
  `build_installer.ps1` lo autodetecta y exige pgvector antes de empaquetar.

---

## Checkpoint anterior: Sesión 44 (2026-07-11) — BLOQUE INSTALADOR: Fase 3 (bienvenida cinematográfica + activación de llaves) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Pipe fijó como meta cerrar la **Fase 3 del instalador** y, al ver el onboarding actual, pidió algo
más grande: que **toda la primera vez que un abogado abre MIA se sienta premium** ("cinematográfico,
con wow factor, más amigable"). Se rediseñó la experiencia completa de bienvenida como un solo viaje:

- **Crear despacho → Activar → Conocer tu despacho → Entrar**, todo con el mismo diseño: fondo negro
  con una aurora teal que se mueve sola, la marca MIA que respira, una pregunta a la vez con
  transiciones suaves, una barra de progreso tipo constelación y una celebración al final. (Se
  estrenó la librería de animaciones que ya estaba instalada sin usar.)
- **Paso nuevo "Activar":** el abogado confirma el motor de Mia (su suscripción, ya viene elegida)
  y pega la **clave de búsqueda en sus documentos**, que se comprueba en vivo con un ✓. Todo en
  lenguaje llano, sin una sola palabra técnica, y siempre con la opción de "hacerlo después".
- **La clave de búsqueda queda activa al instante** (Mia ya puede leer y buscar en documentos sin
  reiniciar). La clave de respaldo del motor, si la pega, se activa la próxima vez que abra Mia —
  y ahora se lo decimos claramente.

### Frontend a revisar (Cursor — capa 3): TODO NUEVO

Esta sesión es sobre todo frontend. Pantallas rediseñadas/nuevas: `frontend/app/register/page.tsx`
("Crear tu despacho"), `login/page.tsx`, `activar/page.tsx` (NUEVA), `onboarding/page.tsx`
(rediseño preservando el guardado automático y el resumen final), e infraestructura visual nueva en
`frontend/app/_welcome/`. El Sidebar se oculta en `/activar` y `/onboarding` (pantalla completa).

### Resultado de verificación (3 capas)

- **Capa 1: línea base sube de 84 a 85 suites** con `test_welcome_keys` 39/39. Verdes (por tramos):
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT), `test_first_run` 68/68 (con la migración 031 nueva),
  `test_setup_wizard` 28/28, `test_onboarding_draft` 15/15, `test_hitl_flow` 21/21. `npm run build`
  verde (15 páginas; `/activar` nueva). La migración 031 entra sola al bundle del instalador.
- **Capa 2: CUATRO revisiones adversariales independientes** (seguridad, corrección backend,
  corrección frontend, §G/visual/accesibilidad). 0 BLOQUEANTES. Seguridad SIN mayores explotables
  (el ataque de inyección al `.env` para pisar secretos de instalación está bloqueado). §G LIMPIO
  (cero jerga visible al abogado). Se corrigieron y re-verificaron: el caso "motor en la nube"
  (ahora exige la clave y avisa fuerte de reabrir), dos claves opcionales tratadas de forma
  inconsistente, una doble llamada de validación al pulsar Enter, dos hallazgos de accesibilidad
  (campos y etiquetas sin nombre accesible), y varios menores de robustez de la escritura del `.env`.
  Detalle en `memory/progress.md` sesión 44.
- **Capa 3: PENDIENTE — de Pipe:** recorrer en vivo el nuevo viaje de bienvenida (crear despacho →
  activar → conocer el despacho → celebración) y confirmar que se siente premium.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F4 (la ÚLTIMA fase):** instalador NSIS/MSI + prueba en frío en máquina limpia,
   con los 7 puntos acumulados del Riesgo #59 (recompilar los dos ejecutables ahora incluye
   `welcome.py` + migración 031 + `env_writer.py`) y el nuevo Riesgo #60.
2. **Riesgo #60 (nuevo):** el motor que depende del motor de modelos (opción "nube", o el respaldo
   de la suscripción cuando el abogado NO tiene el CLI de Claude Code) no queda activo hasta cerrar
   y reabrir MIA una vez. La pantalla de activación ya lo advierte con fuerza; el reinicio automático
   es trabajo de F4. Para el equipo de Pipe (suscripción con su CLI) no aplica.
3. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para vender
   sin la advertencia de Windows, y las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).

### Trabajo en background sin leer

Nada — 4 recon, 4 ejecutores, 4 revisores adversariales, 2 correctores y 2 verificaciones: todo
leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **La clave de búsqueda (Voyage) se activa en caliente** porque el backend la usa directamente;
  la de respaldo del motor (Anthropic) la lee el motor de modelos solo al arrancar → se difiere
  con aviso claro. No se abrió ningún puente nuevo hacia la cáscara de escritorio (se respeta el
  blindaje de F2 y el Riesgo #59).
- **Se pide la clave con opción de diferir.** De dónde sale la llave (Pipe la provee vs. cada
  despacho la suya) es una decisión de negocio futura, fuera de F3.
- **Confianza mono-despacho:** cualquier usuario ya autenticado puede configurar las llaves de su
  instalación; si MIA pasa a multi-despacho hará falta un rol de "administrador de la instalación".
- La política de motor "suscripción" ya era la de fábrica: el wizard solo la confirma en llano.

---

## Checkpoint anterior: Sesión 43 (2026-07-11) — BLOQUE INSTALADOR: Fase 2 (primer arranque automático) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Se completó la **Fase 2 del instalador** (meta que Pipe fijó para la sesión): en una máquina
limpia, MIA ahora **se prepara sola la primera vez que se abre**:

- **Primer arranque automático:** la cáscara detecta que MIA no está preparada y dispara un
  paso de preparación que crea la carpeta de datos del abogado, genera las llaves de seguridad
  solas (una sola vez, jamás se pisan), crea la base de datos desde cero —cerrada al mundo:
  solo escucha dentro del computador— aplica las 28 migraciones y deja la memoria conversacional
  lista. Si el abogado cierra la ventana a mitad de la preparación, la próxima apertura **se
  auto-repara** (esto salió de la revisión adversarial: antes quedaba rota para siempre).
- **El motor de modelos (LiteLLM) ya es un ejecutable propio** (108 MB, sin Python): la cáscara
  lo enciende y lo vigila como 4º servicio, con la misma regla de identidad de siempre (nada
  se adopta por solo responder — exige la llave y los nombres de modelos de MIA).
- **Hallazgo de seguridad corregido y verificado en vivo:** el motor de modelos quedaba
  escuchando hacia toda la red del despacho (cualquier equipo de la oficina podía usar las
  llaves de la firma); ahora solo escucha dentro del computador — se probó con un intento real
  desde la red, rechazado.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 84/84 suites ALL PASS** (línea base sube de 82 a 84 con
  `test_first_run` 68/68 —initdb y login reales— y `test_litellm_packaging` 60/60;
  `test_shell_hardening` sube de 69 a 77 checks). `test_rls` 12/12 y `check_env_pins` 9/9
  (HALT) intactos. cargo build exit 0. Cero reintentos.
- **Capa 2: TRES revisiones adversariales independientes** (bootstrap, cáscara, LiteLLM):
  **6 MAYORES + 5 menores, TODOS corregidos y re-verificados** antes del commit. Los más
  importantes: preparación interrumpida quedaba rota para siempre (ahora marcador de
  finalización + gatillo triple); archivo de llaves podía quedar a medias (ahora escritura
  atómica); el motor de modelos expuesto a la red local (ahora solo loopback, verificado
  en vivo); el gate no probaba un login real (ahora sí). Detalle en `memory/progress.md`
  sesión 43.
- **Capa 3: PENDIENTE — de Pipe** (sin UI nueva esta sesión; sigue la lista acumulada abajo).

### Capa 3 para Pipe (cuando retome)

1. Sin cambios visuales nuevos esta sesión (todo fue motor, cáscara y empaquetado). Sigue
   pendiente lo acumulado: abrir la cáscara y ver el splash (sesión 42) + recorrido de
   producto de las sesiones 39-41.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F3 (wizard de bienvenida):** la primera pantalla que ve el abogado al
   abrir MIA instalada — pedirle solo las llaves mínimas y dejar la política de motor
   "suscripción" lista, todo en llano (§G). Luego F4 (instalador NSIS + E2E en frío en máquina
   limpia, con los 7 puntos acumulados del Riesgo #59 — incluye recompilar los dos ejecutables
   con lo de esta sesión).
2. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para
   vender sin la advertencia de Windows, y las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente (Riesgo #59): los ejecutables ya compilados en dist/ se recompilan en F4
   (el del backend aún no trae el paso de preparación; el del motor de modelos no trae la
   inyección default de loopback — la protección vigente es la configuración del instalador,
   verificada en vivo).

### Trabajo en background sin leer

Nada — 3 recon, 3 ejecutores, 3 revisores, 3 correctores y la regresión: todo leído y
reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **Bootstrap en Python, no en Rust:** la cáscara solo decide CUÁNDO prepararse y muestra el
  progreso; toda la lógica vive en `mia.setup.first_run` (testeable con initdb real).
- **Marcador `.mia-setup-complete` como fuente de verdad** de "preparación completa" — existir
  la base y las llaves NO basta (pueden ser de una preparación interrumpida).
- **Loopback para todo servicio empaquetado** (la base ya lo hacía; el motor de modelos
  bindeaba 0.0.0.0 por default del CLI — corregido en instalador, dev y entry).
- **El modo desarrollo no cambia:** LiteLLM sigue manual (3 terminales); el 4º servicio es
  exclusivo del modo instalado. `litellm_config.yaml` de dev intacto.
- MIA_ENV=prod en el `.env` semilla (verificado contra los 5 usos reales de IS_PRODUCTION —
  no rompe login ni CORS).

---

## Checkpoint anterior: Sesión 42 (2026-07-10) — BLOQUE INSTALADOR: Fase 1 (empaquetado) COMPLETA + cáscara blindada

### Qué se hizo esta sesión (lenguaje simple)

Arrancó el **bloque del instalador** (nuevo objetivo aprobado por Pipe): que cualquier abogado
instale MIA con doble clic, sin saber de tecnología. Plan de 4 fases; esta sesión cerró la
Fase 1 y adelantó el blindaje de la Fase 2:

- **El motor de MIA ya corre empaquetado** (sin Python ni nada instalado): 459 MB verificados
  en vivo — salud OK, seguridad exige credenciales, y el lector de PDFs escaneados responde.
  La voz queda como descarga posterior (decisión de Pipe); los escaneados van incluidos.
- **La pantalla ya corre autocontenida** (sin Node instalado): 103 MB con su propio motor
  portable, probada en un puerto libre con sus protecciones de seguridad intactas.
- **La cáscara de escritorio quedó blindada** contra el mundo real: no pueden abrirse dos MIA
  a la vez, y ya NO adopta cualquier cosa que responda en sus puertos — exige que el proceso
  demuestre ser MIA. Motivo: en la máquina de Pipe pasó de verdad (la cáscara vieja adoptó
  una app ajena llamada Voicebox como "motor" y mostró el proyecto "Intelligence Sura" como
  "pantalla" — Pipe lo vio). Ahora ese caso termina en un aviso en llano.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 82/82 suites ALL PASS** (línea base sube de 79 a 82 con
  `test_packaging` 23/23, `test_frontend_packaging` 24/24, `test_shell_hardening` 42/42).
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. cargo build exit 0. `test_ux`
  recalibrado de raíz (timeout de build 300→600s: el modo autocontenido alarga la compilación;
  el check sigue validando que compile) y re-verificado 41/41.
- **Capa 2: DOS revisiones adversariales independientes** (empaquetado y cáscara): 1 BLOQUEANTE
  (la política de seguridad nueva rompía la pantalla de arranque — corregido externalizando sus
  estilos/lógica) + 4 MAYORES (el motor "llamaba a casa" por internet en cada arranque —
  violaba la promesa local-first; compresión que podía corromper el lector de escaneados en
  silencio; prueba de humo con "verde falso" si el puerto estaba ocupado; gate que validaba
  comentarios en vez de código) + 5 menores — **TODOS corregidos y re-verificados** antes del
  commit. Detalle en `memory/progress.md` sesión 42.
- **Capa 3: PENDIENTE — de Pipe** (ver abajo).

### Capa 3 para Pipe (cuando retome)

1. **NUEVO:** abrir la cáscara de escritorio y confirmar que la pantalla de arranque SE VE con
   su diseño (fondo oscuro, marca) y que, si un puerto está ocupado por otra app, el mensaje
   en llano aparece.
2. Sigue pendiente el recorrido de producto de las sesiones 39-41 (Proyectos, guías con Mia,
   agentes jurídicos, perfil, Configuración en pestañas) — nada de eso cambió hoy.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F2 (primer arranque automático):** carpeta de datos en
   `%LOCALAPPDATA%\Mia`, llaves de seguridad generadas solas, base de datos inicializada con
   sus 30 migraciones, configuración de instalador para la cáscara, y **LiteLLM como segundo
   ejecutable empaquetado** (decisión declarada de la sesión 42: sin él, dos de los tres modos
   de motor quedan rotos en la máquina del abogado). Luego F3 (wizard de bienvenida) y F4
   (instalador final + prueba en frío en máquina limpia).
2. **ACCIÓN DE PIPE (para VENDER, no para el equipo):** registrar la cuenta de firma digital
   (Azure Trusted Signing) — sin ella el instalador funciona pero Windows muestra advertencia
   de "editor desconocido". También siguen pendientes las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: verificaciones que exigen lanzar la app de verdad quedaron como pasos
   OBLIGATORIOS del E2E de F4 (Riesgo #59): splash visual bajo la política de seguridad,
   ventana de consola del motor (hoy visible — se apaga al ensamblar el instalador), prueba
   empírica del aislamiento de la página remota, y el arranque en frío completo.

### Trabajo en background sin leer

Nada — todos los ejecutores, revisores y regresiones se leyeron y quedaron reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **Pipe (2026-07-10):** instalador con lector de escaneados INCLUIDO y voz como descarga
  posterior; plan de 4 fases aprobado; instalador sin firma suficiente para el equipo Lexia.
- **Fable (declarada):** LiteLLM entra como segundo ejecutable (~150-300 MB más) porque sin él
  los modos "nube" y "soberano" quedan completamente rotos y el modo "suscripción" pierde su
  red de respaldo — se prefirió peso sobre abogados con MIA muda. La consolidación elegante
  (Riesgo #4) queda como refactor futuro.
- La colisión de puertos en máquinas reales es caso ESPERADO del producto (demostrado en vivo
  en la máquina del fundador) — toda adopción exige identidad, nunca un simple "responde".

---

## Checkpoint anterior: Sesión 41 (2026-07-10) — BLOQUE C COMPLETO: agentes jurídicos + perfil unificado + Configuración en subtabs — PLAN A/B/C TERMINADO

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque C — el último del plan de evolución de producto aprobado por Pipe —
con la misma orquestación multi-agente autorizada desde la sesión 38:

- **Agentes jurídicos con conocimiento propio:** las "personas" pasan a llamarse **Agentes
  jurídicos** y ahora cada agente puede tener hasta 8 guías del despacho vinculadas. Cuando el
  abogado invoca un agente, Mia prioriza ESAS guías al trabajar (en el chat del asunto y en el
  asistente). Además, "Crear con Mia" también sirve para agentes: una entrevista corta arma el
  borrador del agente (con guías sugeridas ya pre-marcadas) y NADA se guarda hasta que el abogado
  pulsa Guardar en el formulario.
- **Perfil del despacho editable y unificado:** lo que el abogado respondió al conocer a Mia ya
  se puede editar en "Mi despacho" sin repetir la entrevista (identidad, países con el mismo
  selector del inicio, áreas de práctica, tarjeta profesional, herramientas). Antes había DOS
  copias desconectadas del perfil que se desincronizaban en silencio — ahora hay UNA fuente de
  verdad y la otra se deriva sola.
- **Configuración en pestañas:** la pantalla de Configuración dejó de ser un scroll largo — ahora
  son 5 pestañas (Primeros pasos con contador, Conexiones, Carpetas, Automatizaciones, Valor y
  gasto). Todos los enlaces viejos ("Ir al paso", avisos del Panel) siguen llegando a la pestaña
  correcta.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (79 suites)** — línea base sube de 76 a 79:
  `test_agent_playbooks` 55/55, `test_profile_full` 51/51, `test_config_tabs` 14/14.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial con 4 revisores independientes + refutación por hallazgo** —
  5 hallazgos MENORES confirmados (0 mayores, 0 bloqueantes; seguridad/RLS sin hallazgos), TODOS
  corregidos y re-verificados antes del commit: el presupuesto del material de guías podía
  pasarse por unos caracteres; guardar el perfil podía borrar en silencio datos guardados por la
  pantalla vieja; una guía archivada ocupaba cupo invisible en el formulario del agente; un error
  crudo del servidor podía mostrársele al abogado; código muerto. Detalle en `memory/progress.md`
  sesión 41. (De paso, el ejecutor del perfil atrapó un bug latente que habría borrado ajustes
  del despacho en cada guardado.)
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Agentes jurídicos** (antes "Personas"): abrir un agente, vincularle 2-3 guías en
   "Guías vinculadas" (ver el contador "N de 8"), guardar; luego en un asunto invocarlo
   ("actúa como litigante...") y confirmar que trabaja normal.
2. **"Crear con Mia"** en Agentes jurídicos: responder la entrevista (3-6 preguntas), ver que el
   formulario queda precargado (con guías sugeridas marcadas), CANCELAR a mitad de camino y
   verificar que NO quedó ningún agente creado; repetir y esta vez Guardar.
3. En **Conocimiento → Mi despacho**: editar el perfil (países con el selector, áreas,
   herramientas), Guardar y leer el resumen "Así entendí a tu despacho".
4. En **Configuración**: navegar las 5 pestañas; desde el Panel usar un enlace de "tope de gasto"
   (debe abrir directo la pestaña "Valor y gasto") y un "Ir al paso" del recorrido (pestaña
   correcta). Probar entrar directo a `http://localhost:3100/configurar#carpetas`.
5. Sigue pendiente la capa 3 arrastrada de los Bloques A y B (sesiones 39-40) — nada de eso
   cambió en esta sesión.

### Pendientes y próximo paso

1. **El plan A/B/C quedó COMPLETO.** La próxima sesión arranca definiendo con Pipe el siguiente
   objetivo de producto (candidatos naturales: capa 3 acumulada, activación OAuth, o el
   siguiente frente que Pipe priorice).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: carpetas vinculadas POR AGENTE pospuesto a v2; las 3 personas canónicas de
   fábrica vienen sin guías pre-vinculadas; crear un agente con guías inválidas lo crea SIN
   vínculos y avisa en llano (decisión documentada).

### Trabajo en background sin leer

Nada — los 3 workflows (recon, ejecución, capa 2) y las 2 regresiones se leyeron y quedaron
reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **"soul_responses" es un nombre lógico, no una tabla nueva:** la fuente canónica del perfil
  sigue siendo el archivo por despacho en disco (diseño local-first existente); la tabla
  `firm_profiles` pasa a ser derivada y ya no puede pisar en silencio lo canónico.
- El material de las guías de un agente entra al prompt como REFERENCIA después de las reglas
  duras (método y citación) y de la voz — nunca dentro del rol; el presupuesto es duro (≤16k)
  y la regla [VERIFICAR] manda siempre.
- "Modo profundo" (p19) NO se muestra en el perfil editable (coherente con el onboarding, que
  también la oculta — Riesgo #27).
- El renombre "Personas jurídicas" → "Agentes jurídicos" es SOLO visible: la ruta `/personas` y
  la API no cambian (cero riesgo de romper enlaces o integraciones).

---

## Checkpoint anterior: Sesión 40 (2026-07-10) — BLOQUE B COMPLETO: guías asistidas + gobernanza de lo aprendido

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque B del plan de evolución de producto (aprobado por Pipe), con la
misma orquestación multi-agente autorizada desde la sesión 38:

- **"Crear con Mia" (nuevo):** el abogado ya no tiene que redactar una guía de trabajo desde
  cero — le abre una entrevista corta (3 a 6 preguntas), Mia arma un borrador, el abogado lo edita
  libremente y SOLO se guarda cuando él pulsa Guardar (nada toca la base de datos antes de eso).
  Disponible desde Conocimiento y también desde un asunto ya resuelto ("Convertir en guía"),
  donde precarga lo que se hizo en ese caso.
- **Gobernanza completa de guías:** historial de versiones con restaurar, archivar/reactivar,
  editar aunque la guía esté protegida (protegida solo bloquea que Mia la cambie sola), y las
  sugerencias de mejora de Mia ahora se pueden editar antes de aplicarlas (antes era solo
  aprobar o rechazar tal cual).
- **Una sola pantalla para "lo que Mia sabe hacer":** se fusionaron dos pestañas que mostraban
  la misma información partida en dos vistas (guías y habilidades) en una sola, con el origen de
  cada guía en lenguaje llano (manual, importada, con Mia, aprendida) y de dónde viene cada
  sugerencia ("Aprendí esto trabajando en...").
- **Corrección importante de comportamiento:** crear una guía con un nombre que ya existe ya NO
  la sobrescribe en silencio — avisa en llano que ya existe una guía con ese nombre.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (76 suites)** — línea base sube de 74 a 76:
  `test_playbook_versions` 59/59 (48 iniciales, sube tras la capa 2), `test_guide_interview` 25/25.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `test_ux` sube a 37/37,
  `test_second_brain_ui` 26/26. `npm run build` verde (14 páginas). Hubo 1 ciclo de corrección en
  el gate (un test buscaba el nombre viejo de una pestaña; se actualizó al nuevo copy sin
  debilitar la aserción).
- **Capa 2: revisión adversarial con 4 agentes independientes (contexto fresco)** — 10 hallazgos
  CONFIRMADOS, todos corregidos y re-verificados antes del commit:
  3 MAYORES (restaurar una versión con un título repetido daba un error técnico en vez de un
  aviso en llano; crear una guía con nombre repetido sobrescribía en silencio la existente sin
  dejar rastro; "Editar antes de aplicar" descartaba la corrección que el abogado acababa de
  escribir), 7 menores (varios casos de identificadores mal escritos que daban error técnico en
  vez de aviso en llano; una guía nueva creada por Mia no quedaba indexada para búsquedas
  futuras; el botón "Convertir en guía" aparecía en casos donde no debía). Detalle completo en
  `memory/progress.md` sesión 40.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Conocimiento → "Guías y habilidades"**: pulsar "Crear con Mia", responder la entrevista
   (mínimo 3 preguntas), revisar que el borrador es editable y que cancelar a mitad de camino NO
   deja ninguna guía creada; guardarla y verla aparecer con el sello "Creada con Mia".
2. Editar una guía existente, ver su Historial y restaurar una versión anterior.
3. Desactivar y reactivar una guía.
4. En Sugerencias: usar "Editar antes de aplicar" sobre una propuesta.
5. En un asunto con borrador APROBADO: usar el botón "Convertir en guía" (y verificar que NO
   aparece si el borrador fue rechazado o aprobado con cambios).

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque C** del plan (agentes jurídicos con conocimiento propio + perfil del
   despacho editable y unificado + Configuración reorganizada en subtabs). El plan vive en
   `memory/plan-evolucion-producto.md` (Bloques A y B ya marcados completados).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el endpoint de entrevista para crear agentes (`kind='agente'`) responde
   "próximamente" hasta el Bloque C — el componente de entrevista ya quedó reusable para ese caso
   (Riesgo #58).

### Trabajo en background sin leer

Nada.

### Decisiones tomadas y suposiciones declaradas

- Crear una guía (por el wizard o manualmente) ya NO sobrescribe en silencio una guía con el
  mismo nombre — avisa en llano y el abogado decide. Antes de esta sesión, un nombre repetido
  podía hacer "desaparecer" una guía existente sin que nadie se diera cuenta.
- El resultado de la revisión de un borrador ("aprobado" vs. "aprobado con cambios" vs.
  "rechazado") ahora es visible para la pantalla del asunto, no solo para el backend — es lo que
  decide si aparece el botón "Convertir en guía". Un borrador "aprobado con cambios" NO cuenta
  como evidencia suficiente (mismo criterio que usa la entrevista para decidir qué mostrarle a
  Mia).
- Crear agentes jurídicos con "Crear con Mia" queda para el Bloque C a propósito — el wizard de
  entrevista de esta sesión ya se construyó pensando en reusarse para ese caso.

---

## Checkpoint anterior: Sesión 39 (2026-07-09) — BLOQUE A COMPLETO: Proyectos + carpetas sin fricción

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque A del plan de evolución de producto (aprobado por Pipe), con
orquestación multi-agente según su autorización expresa de la sesión 38:

- **Pestaña "Proyectos" (nueva):** espacio de trabajo libre estilo Claude Cowork — el abogado
  crea un proyecto en 2 pasos, conecta carpetas, chatea con Mia sobre esas fuentes (con memoria
  de la conversación) y guarda los documentos que Mia produce, con descarga en Word. Sin
  diagnóstico ni aprobación de borrador (eso sigue siendo de los Asuntos, separados como pidió Pipe).
- **Fin de las rutas pegadas a mano:** selector visual de carpetas del equipo (navegable, seguro,
  fail-closed) en los 3 sitios donde antes se pegaba la ruta (carpetas de trabajo, carpeta del
  expediente, vault de Obsidian).
- **Varias carpetas por asunto/proyecto** — y de paso se corrigió DE RAÍZ el bug latente de poda
  cruzada (documentado en el plan): con 2 carpetas, el sync de una ya no puede borrar los
  documentos de la otra (ni en carpetas del equipo NI en OneDrive, donde también existía).
- **Panel "Fuentes" unificado** en la pantalla del asunto y del proyecto: carpetas del equipo +
  OneDrive + correos en una sola lista con estados en llano y "+ Conectar fuente".

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (74 suites)** — línea base sube de 70 a 74:
  `test_matter_folders_multi` 30/30 (el caso del bug de poda cruzada + concurrencia + backfill
  conservador), `test_folder_browse` 15/15, `test_projects` 33/33, `test_matter_sources` 26/26.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial multi-agente (contexto fresco)** — 12 hallazgos CONFIRMADOS,
  todos corregidos y re-verificados antes del commit salvo 2 notas aceptadas como deuda:
  2 BLOQUEANTES (el backfill de la migración podía fusionar procedencias y provocar borrado de
  documentos conservados; la poda de OneDrive seguía sin distinguir fuente → borrado cruzado
  con multi-carpeta), 2 MAYORES (carrera de sincronización sin candado en el motor → documentos
  duplicados; el chat de proyecto no recordaba los turnos anteriores), 6 menores (proyectos
  contados como "asuntos" en asistente/dashboard/endpoint legacy, burbuja "pensando" infinita
  en error, doble Enter creaba proyectos duplicados, mensaje con la palabra equivocada).
  Detalle completo en `memory/progress.md` sesión 39.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. **Proyectos:** crear un proyecto (nombre → conectar carpeta con el selector visual → entrar),
   chatear sobre los documentos, verificar que un segundo mensaje recuerda el anterior, guardar
   una respuesta larga con "Guardar en el proyecto" y descargarla en Word.
2. **Selector de carpetas:** en Configuración → Carpetas y en un asunto ("Conectar fuente →
   Carpeta del equipo"), navegar y elegir sin pegar rutas.
3. **Panel Fuentes del asunto:** vincular 2 carpetas al mismo asunto, "Revisar ahora" en una,
   confirmar que los documentos de la otra no se tocan; el botón de correos sigue ahí.
4. Sigue pendiente la capa 3 arrastrada de sesiones 35-38 (onboarding/panel/rebrand + los 5
   puntos de fuentes remotas) — nada de eso cambió en esta sesión.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque B** del plan (guías de trabajo asistidas — "Crear guía con Mia" con
   gate HITL por construcción + CRUD/versiones de playbooks + gobernanza de lo aprendido).
   El plan vive en `memory/plan-evolucion-producto.md` (Bloque A ya marcado completado).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el navegador de carpetas queda deshabilitable por flag para el futuro
   Modo A/Docker (Riesgo #56); documentos con procedencia ambigua pre-migración nunca se podan
   solos (protección anti-pérdida, Riesgo #57); `MatterDriveFolder.tsx` quedó sin uso (borrar
   en una limpieza futura).

### Trabajo en background sin leer

Nada — todos los workflows y la regresión final se leyeron y quedaron reflejados aquí.

### Decisiones tomadas / suposiciones declaradas

- `documents.body` (texto íntegro) para los archivos que Mia produce: los fragmentos indexados
  llevan traslape y no se pueden reconstruir para el Word. Suposición razonable no prevista en
  el plan, declarada aquí.
- `GET /api/matters` sin parámetro devuelve SOLO asuntos (compatibilidad de la lista actual);
  `?kind=proyecto` y `?kind=todos` para lo demás. Asistente, dashboard y endpoint legacy también
  filtran proyectos.
- Los endpoints singulares `/folder` quedan como wrappers deprecados (sin el 409); el frontend
  ya usa la superficie plural vía FuentesPanel.
- Memoria conversacional del proyecto: corta y presupuestada (últimos 6 turnos / 8.000
  caracteres), solo en proyectos — el flujo de asuntos quedó byte a byte intacto (gate HITL 21/21).

---

## Checkpoint anterior: Sesión 38 (2026-07-09) — Cáscara de escritorio + rediseño onboarding/panel + rebrand visual + PLAN APROBADO de evolución de producto

### Qué se hizo esta sesión (retoma post-apagón, todo en `origin/main`)

- **Cáscara de escritorio Tauri (Fase 4 · bloque 2)** — `35b3a96`: la app que el abogado abre
  y enciende/apaga todo (DB→backend→frontend). E2E de 5 ciclos + Job Object anti-huérfanos
  verificado con crash simulado. Revisión adversarial: 2 mayores + 5 menores corregidos.
- **Onboarding rediseñado** — `46db38c`: 8 preguntas (fuera estilo/límites/ritmo — el estilo
  se aprende del flywheel), UNA pregunta de país con 21 países multi-select, ejemplos sin
  Lexia. e2e 32/32, second_brain_ui 26/26.
- **Panel/Configuración reestructurados** — `0d5e826`: el Panel solo con lo accionable
  (Para tu decisión + recordatorios + recomendaciones + Este mes); Configuración absorbe
  conexiones/carpetas/automatizaciones/valor. Guía OAuth en `docs/guia-conectar-correo-y-nube.md`.
- **Rebrand visual completo** — `13f0d55`: paleta Lexia (teal/negro/degradé verde), sidebar
  negra con wordmark MIA (I en teal), Archivo+Hind, aurora teal, card-depth. Pipe lo vio en
  vivo y le gustó ("me gusta lo que estoy viendo").

### PRÓXIMA SESIÓN: ejecutar el plan de evolución de producto (APROBADO por Pipe)

> **AUTORIZACIÓN EXPRESA DE PIPE (2026-07-09, en sus palabras):** ejecutar el plan
> **usando workflows de orquestación multi-agente desde el arranque, a velocidad
> máxima**. Es decir: al retomar con /arranque, usar el tool Workflow (fan-out de
> ejecutores en paralelo sobre partes disjuntas del Bloque A + verificación
> adversarial multi-agente) sin volver a pedirle permiso. Los límites NO cambian:
> verificación de 3 capas antes del cierre, gate HITL innegociable, HALT si
> test_rls falla, y capa 3 visual sigue siendo de Pipe.

**El plan completo vive en `memory/plan-evolucion-producto.md`** (misma copia en
`C:\Users\USER\.claude\plans\chad-me-gusta-lo-memoized-token.md`). Resumen:
- **Bloque A (EMPEZAR AQUÍ):** pestaña "Proyectos" estilo Claude Cowork (reusa `matters`
  con `kind`), selector visual de carpetas del equipo (fin de rutas pegadas a mano),
  multi-carpeta por asunto (⚠️ PRIMERO `documents.source_id` — hay bug latente de poda
  cruzada documentado en el plan), panel "Fuentes" unificado.
- **Bloque B:** "Crear guía con Mia" (entrevista stateless con gate HITL por construcción),
  CRUD+versiones de playbooks, gobernanza de skills aprendidas (fusionar subtabs).
- **Bloque C:** Personas → "Agentes jurídicos" con conocimiento vinculado, perfil del
  despacho editable (SOUL como fuente canónica, `/api/profile/full`), Configuración en subtabs.
- Decisiones de Pipe: todo en orden A→B→C, un bloque por sesión; Proyectos y Asuntos como
  pestañas SEPARADAS. Verificación 3 capas por bloque; gate HITL innegociable.

**Pendientes de Pipe (sin cambio):** registrar apps OAuth (guía en docs/), capa 3 en vivo
de sesiones 35-36 y del onboarding/panel/rebrand nuevos.

---

## Checkpoint anterior: Sesión 37 (2026-07-09) — OCR local para PDFs escaneados + sincronización automática de OneDrive

### Qué se hizo esta sesión

> Nota: la sesión se interrumpió por un corte de luz tras el último commit; el cierre (regresión
> completa + esta memoria) se completó en la retoma del mismo día. No se perdió trabajo.

- **Bloque 3a — Mia ya lee PDFs escaneados (OCR local):** en litigio la mayoría de expedientes
  son escaneos sin capa de texto; antes Mia quedaba ciega SIN AVISAR. Ahora los lee con un motor
  de lectura óptica que corre 100% en el servidor del despacho (el documento nunca sale de ahí),
  página por página, marcando con honestidad qué partes vienen de lectura óptica. Fail-soft:
  tope de 150 páginas / 10 minutos con corte anotado; una página corrupta no tumba el documento;
  un archivo sin cuerpo legible NO entra como documento válido (se reporta y se reintenta luego).
- **Bloque 3b — las carpetas de OneDrive se mantienen al día solas:** job programado cada 6 horas
  (misma cadencia que Obsidian) que sincroniza las fuentes de OneDrive remoto de cada despacho;
  comparte el candado con el botón manual (nunca corren dobles) y una carpeta rota no tumba las
  demás. Cierra la deuda #1 de la sesión 36.
- **Revisión adversarial (capa 2) corrida y cerrada:** 3 mayores + 4 menores, TODOS corregidos
  antes del cierre (`ea28423` + `315dbd1`): el OCR ya no congela el servidor (async), RAM acotada
  ante PDFs con páginas descomunales, "solo nota sin cuerpo" ya no entra como documento, gate de
  no-egress que PRUEBA que el OCR no hace ninguna llamada de red, y la guarda de cuerpo legible
  replicada también en carpetas locales.

### Frontend a revisar (Cursor — capa 3): NO APLICA

Los 4 commits son backend + tests puros — no hay UI nueva. Sigue pendiente la capa 3 de la
sesión 36 (fuentes remotas) y la del botón "Revisar ahora" (sesión 35) — ver checkpoint anterior.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 70/70 suites ALL PASS** (corrida en la retoma post-apagón) —
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; línea base sube de 69 a 70 con
  `test_ocr_ingest` 26/26. Sin frontend tocado → sin `npm run build`. (Nota de tally:
  `test_speech_tts` es 24/24 en el script actual; el 26/26 histórico era de otra versión.)
- **Capa 2:** revisor adversarial independiente — 3 mayores + 4 menores, TODOS corregidos y
  re-verificados; detalle en `memory/progress.md` sesión 37 y Riesgo #55.
- **Capa 3: NO APLICA** (sin UI nueva en esta sesión).

**Commits de esta sesión en `main`, SIN PUSH todavía:** `ad16a64` (OCR bloque 3a), `10788c2`
(cron OneDrive bloque 3b), `ea28423` (correcciones capa 2), `315dbd1` (guarda has_body en
carpetas locales) + el commit de cierre de esta memoria. Los commits de la sesión 36 ya están
en `origin/main`.

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor — los 5 puntos de la sesión 36 (abajo) + botón "Revisar ahora".
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` — hasta entonces las fuentes remotas responden 503 en llano (por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) espera aprobación de Pipe.
4. Decidir push a `origin/main` de los commits de esta sesión.

---

## Checkpoint anterior: Sesión 36 (2026-07-09) — Fuentes remotas del expediente (Gmail + OneDrive vía la nube)

### Qué se hizo esta sesión

Bloque 2 de la Fase 3 (el que quedó pendiente en el HANDOFF de la sesión 35): el abogado ya puede
traer correos (Microsoft/Google) y carpetas de OneDrive al expediente, con OAuth multi-proveedor de
base (un despacho puede tener Microsoft Y Google conectados a la vez). Construido en 4 fases:

- **Fase 1 — cimientos OAuth multi-proveedor:** `tenant_oauth_tokens` con PK `(tenant_id, provider)`;
  migración `027_remote_sources.sql` (+ `remote_drive_sources`, `remote_file_hashes`, RLS FORCE);
  `documents.origin` gana `'mail'`/`'drive'`. `GET /api/mailbox/status` ahora reporta POR PROVEEDOR.
- **Fase 2 — correos del caso → expediente:** buscar y vincular correos (cuerpo + adjuntos se
  vuelven documentos, dedupe por sha256, máx 20 por lote).
- **Fase 3 — OneDrive remoto SELECTIVO de solo lectura:** navegar carpetas, registrar una fuente,
  sincronizar (incremental por eTag→sha256, tope 20MB por archivo, fail-soft por archivo, tope 20
  fuentes por despacho).
- **Fase 4 — UI:** navegador modal de carpetas, diálogo de búsqueda de correos, tarjetas del Panel
  de control por proveedor con checkbox de OneDrive.

Detalle completo (piezas de código, los 3 mayores + 6 menores corregidos en `c9f2a32`) en
`memory/progress.md` sesión 36 y `memory/bugs-and-risks.md` Riesgo #54.

### Frontend a revisar (Cursor — capa 3, PENDIENTE)

Toda la UI de esta sesión (`OneDriveFolderPicker`, `OneDriveSourcesSection`, `MatterDriveFolder`,
`MailSearchDialog`, `MailboxSection`) pasó `npm run build` verde y está cubierta por gates de API,
pero **nadie la recorrió en un navegador real todavía.** Pendiente:

1. **Conectar Microsoft con "Incluir mis archivos de OneDrive"** y verificar el flujo real de
   consentimiento OAuth (requiere que Pipe haya puesto las llaves en `.env` primero — ver más abajo).
2. **Navegador de carpetas:** entrar 2-3 niveles y elegir una carpeta para sincronizar.
3. **Probar el 503** cuando no hay conexión configurada, y el botón nuevo **"Añadir permiso de
   archivos"** sobre una cuenta Microsoft que solo tenía correo conectado.
4. **Buscar y vincular 2-3 correos reales** desde el diálogo del asunto y verlos aparecer como
   documentos del expediente.
5. **Responsive** de los dos modales nuevos (buscador de correos, navegador de carpetas).

También sigue pendiente la capa 3 del botón "Revisar ahora" (deuda arrastrada de la sesión 35).

**Contratos de los endpoints nuevos (por si Cursor los necesita):**
- `GET /api/mailbox/status` → `{conectado, conexiones:[{proveedor, proveedor_nombre, conectado,
  funciones:[...], archivos:bool}], analisis_contenido, proveedor?, proveedor_nombre?, proveedores?}`
  — `archivos` indica si esa conexión YA tiene permiso de OneDrive (para ofrecer "Añadir permiso").
- `GET /api/matters/{id}/mail/search?q=&provider=` → `{resultados:[{...,provider}]}`; sin `provider`
  busca en todas las cuentas conectadas; sin cuenta conectada → 503 en llano.
- `POST /api/matters/{id}/mail/link` con `{items:[{provider, message_id}]}` (máx 20) →
  `{added:[...], already:[...], skipped:[{name, reason}]}` — un fallo individual nunca tumba el lote.
- `GET /api/drive/browse?item_id=` → `{items:[...]}` (un nivel de OneDrive; sin `item_id` = raíz);
  503 sin cuenta/permiso, 502 si Graph falla.
- `GET /api/drive/sources` / `POST /api/drive/sources` (`{remote_item_id, label?, kind, matter_id?}`)
  / `DELETE /api/drive/sources/{id}` / `POST /api/drive/sources/{id}/sync` (throttle 60s + lock de
  corrida en vuelo, ambos con mensaje en llano).

### Resultado de verificación (3 capas)

- **Capa 1:** regresión completa **69/69 suites ALL PASS** (dos corridas, antes y después de las
  correcciones de capa 2) — `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; `npm run build`
  verde. Gates nuevos: `test_mailbox_multi.py` 21/21, `test_mail_to_matter.py` 24/24,
  `test_remote_drive.py` 35/35. (Nota de tally: `test_setup_wizard` es 28/28, no el 30/30 que quedó
  anotado en HANDOFFs anteriores — correspondía a otra versión del script.)
- **Capa 2 — dos revisores adversariales independientes (contexto fresco):** seguridad **APROBADO
  sin bloqueantes ni mayores** (RLS, OAuth state con nonce+cookie anti-CSRF, sin fuga de tokens/
  contenido, SQL parametrizado, límites verificados); corrección encontró **3 mayores + 6 menores,
  TODOS corregidos** antes del commit `c9f2a32` (renombrar en OneDrive ya no borra el archivo del
  expediente; la UI espera a que la sync termine; botón para agregar permiso de archivos a una
  cuenta ya conectada; fallo por-correo no tumba el lote; `last_synced_at` por fuente; reset del
  diálogo al cerrar; uuid malformado → 404; embeddings fuera de la conexión pooled; ids de URL
  escapados; scopes base de Microsoft siempre incluidos).
- **Capa 3: PENDIENTE** — sin navegador conectado en esta sesión; ver la lista de 5 puntos arriba.

**5 commits en `main`, SIN PUSH todavía:** `7ccab33` (Fase 1 OAuth), `8c2c28a` (Fase 2 correos),
`a84088a` (Fase 3 OneDrive), `b989e39` (Fase 4 UI), `c9f2a32` (correcciones de capa 2).

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor (los 5 puntos de arriba) + la capa 3 pendiente del botón "Revisar
   ahora" (sesión 35).
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` (`MS_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`) — hasta entonces todo
   responde 503 en llano (activación diferida, por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) sigue esperando aprobación de Pipe.
4. Deuda consciente: sincronización PROGRAMADA de fuentes OneDrive (hoy solo botón manual).
5. Decidir si se hace push a `origin/main` de estos 5 commits.

---

## Checkpoint anterior: Sesión 35 (2026-07-08) — Frentes B/C + Data Factory del corpus + bugfix FTS

### Qué se hizo esta sesión

Sesión de retoma: había ~5h de trabajo de una sesión previa sin commitear ni documentar (nunca corrió
`/cierre`). Se reconstruyó por lectura de código, se verificó y se corrigió antes de commitear:

- **Bugfix** `agents/research.py`: la consulta FTS de investigación mandaba el mensaje completo del
  abogado (0 resultados casi siempre) → ahora usa términos clave + citas exactas en OR.
- **Frente B (aprendizaje):** motivo del rechazo en la traza (B1), botón "Revisar ahora" en
  Conocimiento → `POST /api/learning/run` (B2), aprobar una corrección de wiki ya la aplica de verdad
  al archivo del concepto (B4).
- **Fase 3 · frente C + Data Factory del corpus:** `rag/corpus_factory.py` (motor único, jurisdicción
  por pack JSON — nada de Colombia hardcodeado, ver decisión de Pipe en `memory/progress.md` sesión
  35) + `connectors/vault_export.py` (backfill de playbooks y fichas del corpus al vault de Obsidian).

Detalle completo, con los 5 hallazgos de capa 2 y sus correcciones, en `memory/progress.md` (sesión 35).

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/memoria/page.tsx` (pestaña Sugerencias): botón nuevo **"Revisar ahora"** sobre la
  lista de propuestas — dispara `POST /api/learning/run`, muestra spinner mientras corre y un mensaje
  de resultado ("Mia propuso N mejoras nuevas" / "no encontró nada nuevo"). `npm run build` verde y
  cubierto por gate de API; falta el recorrido visual en vivo (clic real, estados de carga/error).
- Nada más cambió en `frontend/`; el resto de esta sesión fue backend puro (Data Factory, vault export,
  bugfix de investigación) sin superficie nueva para el abogado más allá del botón de arriba.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **66/66 suites verdes** (dos corridas — antes y después de aplicar las
  correcciones de capa 2), `test_rls`/`check_env_pins` HALT intactos. Gates nuevos: `test_research_query`
  11/11, `test_corpus_factory` 12/12, `test_vault_export` 38/38.
- Capa 2 (revisor adversarial independiente, workflow multi-agente): 5 hallazgos CONFIRMADOS, los 5
  corregidos y RE-VERIFICADOS antes del commit (colisión de slug al exportar playbooks; parseo frágil
  del concepto de una wiki_correction → columna dedicada; conexión pooled sostenida durante E/S de
  disco; lógica de identidad duplicada entre adaptadores del corpus; fetches secuenciales evitables).
- Capa 3: **PENDIENTE** — sin navegador conectado en esta sesión para el recorrido en vivo del botón.

**6 commits en `main`, YA PUSHEADOS a `origin/main`:** `9f62b4e`, `4ea4126`, `cb32ebb`, `00728c8`,
`8376726`, `c11fb71` (el último añade 3 de los 5 quick wins de
`docs/analisis-claude-for-legal.md` — detalle en `memory/progress.md`, regresión 66/66 y capa 2
con 3 hallazgos corregidos antes del commit).

**Pendiente real para la próxima sesión (ya no queda nada "chico" en la cola):**
1. Capa 3 visual en vivo (botón "Revisar ahora" en Conocimiento + los quick wins de prompt no
   tienen UI que revisar, son solo texto de sistema).
2. **Gmail/OneDrive vía Graph API** (bloque 2 de la Fase 3, `mia-decisiones-pipe-fase3` en
   memoria) — es la siguiente pieza grande. Antes de construirla a ciegas, vale la pena que Pipe
   confirme alcance: ¿Gmail primero (correos+adjuntos del caso como parte del expediente) o
   OneDrive vía Graph API primero (la sincronización LOCAL de OneDrive/Google Drive Desktop ya la
   cubre `local_folder_sources`/F3.1 para quien tenga el cliente de escritorio instalado — el
   Graph API solo aporta valor si el abogado NO usa el cliente de escritorio)? Necesita también
   que Pipe registre la app OAuth (mismo patrón "activación diferida" que Microsoft 365/Google ya
   tienen: backend/UI listos, 503 hasta que lleguen las llaves).
3. Quick win #5 (checklist de pre-entrega ejecutado en el gate de aprobación) — requiere
   aprobación previa de Pipe por tocar `hitl_checkpoint`.

---

## ⭐ Trabajo de frontend PENDIENTE para Cursor (consolidado · priorizado · 2026-07-03)

El backend de estos puntos ya está en `origin/main`; falta SOLO la UI. Cada uno tiene su
sección detallada más abajo con endpoints y comportamiento. Orden sugerido:

1. **Control del tope de gasto de IA (CP-E1)** — `GET/PUT /api/policy/budget`. **COMPLETADO** (commit `7030e5e`). Detalle en la sección "CP-E1 · control del tope en el Panel".
2. **Pantalla de gestión de Personas jurídicas (CP-E3, lo más nuevo)** — CRUD
   `GET/POST/PUT/DELETE /api/personas`. **COMPLETADO** (commit `557478c`). Detalle en la sección "CP-E3" arriba de todo.
3. **Tarjetas de "Recomendaciones de Mia" (CP-V2)** — `GET /api/dreams/prescriptions` +
   `POST .../{id}/decision`. **COMPLETADO** (commit `c61912f`). Detalle en la sección "CP-V2".
4. **Automatizaciones (CP-P2)** — plantillas + sugerencias consent-first (`/api/automations/*`). **COMPLETADO** (commit `5642a73`).
5. **Conectar Microsoft 365 / Google (CP-P3)** — botón "Conectar" (`/api/mailbox/*`). **COMPLETADO** (commit `70ac8e7`). OJO:
   la ACTIVACIÓN real (llaves OAuth en `.env`) sigue APLAZADA por decisión de Pipe hasta el producto
   final; la UI está lista y muestra el aviso 503 si el servidor aún no tiene las llaves.

**Reglas para Cursor (recordatorio):** §G sin jerga técnica al abogado (nada de "tenant",
"LangGraph", "modelo", "pgvector"); errores del backend llegan en llano — mostrarlos tal cual;
tras `npm run build` reinicia el dev server (pisa la caché `.next`). Escribe tus hallazgos de
capa 3 al final del archivo.

---

## ✅ Rediseño del onboarding — COMPLETADO (backend + frontend en `origin/main`, 2026-07-06)

**Backend** (merge `de6c797`) y **frontend de Cursor** (commit `1487ba6`) ya están en
`origin/main` y verificados (tsc limpio; 3100 sirve 200 sin ChunkError; SummaryMarkdown
calza con `build_summary`). Cursor entregó: resumen llano + detalle técnico plegable,
7 días (con fin de semana), herramientas con descripción, y "Conocimiento" de-jergada.
**Único pendiente = capa 3 EN VIVO de Pipe:** hacer el recorrido de punta a punta en
`http://localhost:3100` y confirmar que el resumen refleja sus respuestas. La spec
original se conserva abajo por trazabilidad; NO rehacer.

<details><summary>Spec original (histórica — ya implementada)</summary>

Pipe probó el onboarding real y pidió arreglos. **El backend ya cambió** (rama
`feat/onboarding-soul-claro`); falta la parte visual. Contexto: el "Configura a Mia"
debe sentirse fácil para un abogado (cero jerga de agentes), estilo wizard de Hermes.

**COMPLETADO** (Cursor capa 3 · 2026-07-06). Detalle en "Hallazgos de Cursor (capa 3)" al final.

**Ya hecho en backend (no tocar, solo consumir):**
- La entrevista ahora trae **13 preguntas** (`GET /api/onboarding/questions`); se
  QUITARON las de "objetivo del año" y "los 3 pilares" (eran confusas). Los `id`
  `p15`/`p16` ya no llegan — si el frontend tiene lógica por-id para ellos, quítala.
- El SOUL.md se genera **determinista y sin placeholders** (nunca más `[CORCHETES]`).
- `POST /api/onboarding/complete` ahora devuelve, además de `soul_content`, un campo
  **`summary`**: un resumen en **lenguaje llano** en Markdown ("### Así entendí a tu
  despacho" + viñetas). ESO es lo que debe ver el abogado al terminar.
- El recorrido "Configura a Mia" ya **no incluye Obsidian** (`GET /api/setup/status`
  devuelve 6 pasos). No lo repongas.

**Frontend a construir (`frontend/app/onboarding/page.tsx` salvo que se indique):**

1. **Pantalla final = el resumen, no el .md crudo.** Hoy se muestra `soul_content` en
   un `<pre>`. Cámbialo por render del campo **`summary`** (Markdown → texto con
   viñetas y negritas, legible). El `soul_content` técnico puede quedar oculto o en un
   "Ver detalle técnico" plegable (opcional, para power users). Encabezado tipo tarjeta.

2. **Días de la semana — agregar SÁBADO y DOMINGO.** La pregunta de ritmo (`p17`) hoy
   muestra checkboxes Lunes–Viernes; hay abogados que trabajan fin de semana. Deja los
   **7 días** (Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo).

3. **Herramientas (`p18`) — lista curada CON descripción, no texto libre.** Reemplaza
   los chips libres por una lista de opciones (checklist) donde cada una explique qué
   hace Mia con ella. Los valores seleccionados se envían igual (lista de textos) en la
   respuesta del field `memory.tools_that_survived`. Opciones sugeridas + descripción:
   - **Correo** — "Mia vigila tus correos urgentes y te avisa."
   - **Calendario** — "Mia te recuerda tus eventos y audiencias próximas."
   - **Gestor documental** — "Mia consulta los documentos del despacho para responder."
   - **Mensajería (Telegram)** — "Habla con Mia desde tu celular, por texto o por voz."
   - **Carpetas en la nube (OneDrive/Google Drive)** — "Mia conoce las carpetas donde
     guardas tu trabajo."
   - **Notas (Obsidian)** — "Mia guarda y consulta tus notas." *(marcar "próximamente"
     si se quiere, ya que Obsidian está pospuesto)*
   Deja además un campo "otra…" para añadir libremente si el abogado quiere.

4. **De-jergar la pantalla "Conocimiento"** (`frontend/app/memoria/page.tsx`, pestañas
   línea ~14-18). Nombres nuevos (confirmados con Pipe):
   - "Wiki del despacho" → **"Temas que Mia va aprendiendo"**
   - "Lo que Mia sabe" → **"Documentos y fuentes"**
   - "Habilidades" → **"Lo que Mia sabe hacer"**
   - "Sugerencias de Mia" → **"Mejoras que Mia propone"**
   - "Mi despacho" → se queda igual (ya es claro).

**Reglas:** §G sin jerga ("SOUL", "tenant", "playbook", "wiki" no van); textos cálidos
y explicativos (estilo Hermes: cada opción con su descripción, un default sensato); tras
`npm run build` reinicia el dev server. **OJO — puerto:** Mia ahora corre en **3100**
(no 3000; el 3000 es de otro proyecto del equipo). Escribe tus hallazgos abajo.

</details>

---

## Checkpoint actual: CP-E6 — Más canales (relay) + conectar sistemas vía MCP (2026-07-04)

### Qué cambió (lenguaje simple)

- **Conectar sistemas del despacho (lo nuevo para el abogado):** Mia ahora puede conectarse
  a sistemas externos —**gestión documental** del despacho y **consulta de estados de
  procesos judiciales**— para trabajar con esa información. Todo nace **apagado**: el
  despacho lo enciende con sus credenciales cuando quiere, y lo apaga (o borra las
  credenciales) cuando quiere.
- **Seguridad primero:** las credenciales viven **fuera** del cerebro de Mia; se piden
  tokens de **solo lectura**; y al conectar, ningún secreto interno de Mia se filtra.
- **Más canales:** se preparó el patrón "relay" para que sumar canales (WhatsApp, correo…)
  sea un adaptador delgado, con las llaves del canal fuera del núcleo. El puente de
  Telegram ya usa ese patrón común.

### Frontend PENDIENTE para Cursor — pantalla "Sistemas conectados"

**COMPLETADO** (Cursor capa 3 · 2026-07-12). Detalle en "Hallazgos de Cursor (capa 3)" al final.

En Configuración → Conexiones, sección "Sistemas conectados". Endpoints (`/api/mcp/*`):

- `GET /api/mcp/status` → lista de sistemas. Cada uno trae: `slug`, `display_name`
  (mostrar ESTE, en llano), `description`, `permissions_note` (nota de permisos mínimos —
  mostrarla para tranquilidad del abogado), `fields` (cada uno: `env_var`, `label`,
  `is_secret`, `required`), `enabled`, `configured`, `missing` (etiquetas de lo que falta).
- `POST /api/mcp/{slug}/enable` con body `{ "env": {…}, "secrets": {…} }` → guarda las
  credenciales y habilita. `env` = campos NO secretos (URLs), `secrets` = tokens. Las
  claves van por `env_var`/`secret_key` que da `fields`. Devuelve el status actualizado.
- `POST /api/mcp/{slug}/disable` → apaga sin borrar credenciales. Devuelve status.
- `POST /api/mcp/{slug}/forget` → borra la conexión y sus credenciales. Devuelve status.

Comportamiento esperado en la UI:
- Por cada sistema: nombre + descripción + nota de permisos; un formulario con los
  `fields` (los `is_secret:true` como campo tipo contraseña). Botón "Conectar" (enable),
  y si `enabled`: "Desconectar" (disable) y "Borrar credenciales" (forget).
- El backend **nunca** devuelve el valor de un secreto — no intentes precargarlo; usa
  `configured`/`missing` para mostrar si ya está puesto.
- Errores del backend llegan en llano (§G) — mostrarlos tal cual. Nada de "MCP",
  "servidor", "tenant": el abogado ve "Gestión documental del despacho".
- **No urgente / activación diferida:** igual que "Conectar Microsoft 365", la conexión
  EN VIVO con estos sistemas depende de registrar el servidor real; la UI puede quedar
  lista sin que haya un sistema conectado todavía.

Detalle técnico completo en `docs/canales-y-mcp.md`.

---

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

## Checkpoint reciente: CP-E4 — Banco de pruebas de calidad (eval harness) (2026-07-03)

### Qué es (lenguaje simple)

- Una herramienta INTERNA para medir si un cambio en Mia **mejora o empeora** la calidad de
  sus análisis, ANTES de confiar en él. Corre a Mia sobre un set de **casos de prueba
  sintéticos** (inventados, sin datos reales de cliente) y puntúa cada resultado con señales
  **objetivas** (sin que otra IA juzgue): cuántas citas quedaron sin respaldo, si el
  diagnóstico trae su cierre estructurado, si produjo borrador. Luego compara "antes vs
  después" y da un veredicto en llano: **mejora / sin cambio / regresión**.
- **No toca datos reales de cliente:** los casos son sintéticos por construcción; correr el
  banco sobre expedientes reales del despacho exige autorización explícita (candado
  fail-closed) — hoy no hay ni pantalla ni caso que lo haga.

### Frontend (Cursor — capa 3): NO aplica

- CP-E4 es una herramienta de **desarrollo/administración por línea de comandos**
  (`execution/run_eval.py`), no una función del producto para el abogado. **No hay UI que
  construir ni revisar.** Un panel de calidad para el despacho podría venir en un checkpoint
  futuro, pero no es parte de este.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_eval_harness.py` **25/25** (scorer determinista; comparador detecta
  regresión/mejora con veredicto fail-safe; casos todos sintéticos; candado de datos reales
  fail-closed; end-to-end por el grafo real con LLM/embeddings stubbeados, incl. que intake
  recupera el expediente sembrado); regresión **ALL PASS (56 suites)** (test_rls HALT).
- Capa 2 (revisor adversarial independiente): candado de datos reales y determinismo de las
  métricas CONFIRMADOS. 1 MAYOR corregido y re-verificado ANTES del commit: el runner sembraba
  los documentos SIN embedding → intake los ignoraba y Mia redactaba "a ciegas" (el banco no
  ejercitaba la recuperación del expediente) → ahora se siembran con embedding como en
  producción y el gate exige que intake recupere el documento. 2 MENORES aceptados (ver
  memory/bugs-and-risks.md Riesgo #51).
- Capa 3: NO APLICA (sin frontend).

---

## Checkpoint reciente: CP-E3 — Personas jurídicas especializadas y editables (2026-07-03)

### Qué cambió (lenguaje simple)

- Mia ahora tiene **personas jurídicas** que el despacho **edita a su gusto**: un
  **litigante** (estratega procesal), un **tributarista** y un **revisor de citas**
  vienen listos de fábrica, y el despacho puede cambiarlos, deshabilitarlos, borrarlos
  o crear los suyos. Cada persona tiene su **voz** (cómo razona y con qué tono), sus
  **áreas de énfasis**, un **nivel de motor** y sus **frases de invocación**.
- El abogado **invoca** una persona escribiéndola en su propio mensaje — "actúa **como
  litigante** y analiza este asunto", "dame la **perspectiva tributaria**", "**revisa las
  citas** de este borrador" — en el chat de un asunto o hablando con Mia (Telegram). Mia
  adopta esa voz solo para ese turno. **Nada se auto-activa**: sin invocación, Mia trabaja
  exactamente como hoy.
- **Privacidad blindada:** una persona NUNCA puede mandar el trabajo del despacho a un
  motor de nube que su política no permita. Solo puede elegir entre "el motor del despacho"
  (respeta la política) o "siempre el motor local" (más privado y económico) — jamás al
  revés. El revisor de citas usa el motor local de fábrica.
- **La voz no relaja las reglas:** una persona colorea el tono, pero **nunca** puede hacer
  que Mia invente una norma o una cita — la regla de marcar con [VERIFICAR] lo no
  verificable manda siempre, por encima de cualquier persona.

### Frontend a construir (Cursor — capa 3): pantalla de personas en el Panel

- CP-E3 es **backend**; el abogado hoy invoca personas por frase en el chat (que ya
  existe). Falta la pantalla para **gestionarlas**. Endpoints listos (todos bajo `/api`,
  auth como el resto):
  - **`GET /api/personas`** → `{personas: [...]}`. Cada persona: `{id, name, title,
    role_prompt, tone, focus_areas[], model_tier, summon_phrases[], description, enabled}`.
    La primera llamada **siembra** las 3 canónicas del despacho.
  - **`POST /api/personas`** body con los mismos campos (name y role_prompt obligatorios)
    → la persona creada. `model_tier` ∈ `"estandar"` | `"local"`.
  - **`PUT /api/personas/{id}`** → la persona actualizada.
  - **`DELETE /api/personas/{id}`** → `{ok: true}`.
  - Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual):
    nombre duplicado, nivel inválido, tope alcanzado, etc.
- **Sin jerga (§G):** para `model_tier`, mostrar al abogado dos opciones en llano —
  "El motor del despacho" (`estandar`) y "Siempre el motor local — más privado" (`local`).
  Nunca nombres de modelo. `role_prompt` es "cómo debe razonar y hablar esta persona";
  `summon_phrases` es "frases con las que la llamas en el chat".
- Trabajo FUTURO opcional (no de este checkpoint): autocompletar las frases de invocación
  al teclear en el chat; un selector de persona en el asunto (hoy la invocación es por frase).

### Comportamiento esperado

- En un asunto: "Analiza esto **como litigante**" → Mia razona con voz de litigante en los
  5 especialistas del turno (hechos→investigación→cruce→borrador→corrección), sin cambiar
  el método ni la verificación de citas. Sin frase de persona → turno idéntico a hoy.
- Con Mia libre (Telegram): "**revisa las citas** de este texto: …" → Mia adopta la voz del
  revisor (motor local de fábrica) y marca lo no respaldado con [VERIFICAR].
- Nombre/persona deshabilitada o inexistente → Mia trabaja sin persona (no falla el turno).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_personas.py` **52/52** (candado de motor fail-closed en las 3
  políticas incl. soberano; voz con guardrail [VERIFICAR] y sin jerga; detección por frase;
  validación; CRUD bajo RLS; AISLAMIENTO entre despachos; siembra idempotente que respeta el
  borrado); regresión **ALL PASS (55 suites)** (test_rls 12/12 HALT). Sin frontend web → sin
  npm build.
- Capa 2 (revisor adversarial independiente): los 7 invariantes SE SOSTIENEN
  (confidencialidad del motor, RLS, la voz no anula la citación, fail-open, comportamiento
  sin cambios, recursos/concurrencia, logs). Sin bloqueantes ni mayores. 2 MENORES
  (fail-open del asistente simétrico a stream; L3 citación añadida al system del asistente
  para que la regla dura preceda a la voz) + 1 NOTA (el candado 'local' devuelve el motor
  local por CONSTRUCCIÓN, no por posición de la cadena) corregidos y re-verificados ANTES
  del commit. Ver memory/progress.md sesión 32.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E3).

---

## Checkpoint anterior: CP-E2 — Adjuntar pruebas por referencia (@expediente / @carpeta) (2026-07-03)

### Qué cambió (lenguaje simple)

- El abogado ya puede **traer evidencia a la conversación escribiéndola con `@`**: en el
  chat de un asunto o con Mia (Telegram/asistente) puede escribir `@expediente` (los
  documentos del asunto en curso), `@expediente:"Banco Popular vs Zurich"` (otro asunto
  del despacho, por su nombre) o `@carpeta:"Pruebas Zurich"` (una carpeta de trabajo
  registrada). Mia **expande la mención** e incorpora esa evidencia a su análisis del
  turno, sin que el abogado copie y pegue nada.
- Es donde más sirve **hablando con Mia libremente** (por Telegram o el asistente), que
  antes no traía documentos sola: ahora `@expediente:"..."` mete el expediente a la charla.
- **Privacidad primero:** una mención SOLO resuelve a expedientes y carpetas **del propio
  despacho** (nunca de otro), y **nunca abre un archivo del disco** — lee lo que Mia ya
  tiene indexado. Si el nombre no existe, está deshabilitado, o parece una ruta de
  computador, Mia lo dice en llano y no adjunta nada. Toda la evidencia entra **sellada**
  (Mia la trata como datos del caso, no como órdenes). Si el material referenciado es muy
  grande, se adjunta **recortado con aviso honesto** (nunca finge tener la prueba completa).

### Frontend (Cursor — capa 3): NO hay UI nueva

- CP-E2 es **sintaxis de mensaje** — el abogado escribe `@expediente`/`@carpeta` en el campo
  de chat que YA existe (asunto y, sobre todo, Telegram). No toca `frontend/`. **No hay nada
  que construir ni revisar** en la interfaz para este checkpoint.
- Trabajo FUTURO opcional (no de este checkpoint): un autocompletado que sugiera nombres de
  expedientes/carpetas al teclear `@` en el chat del asunto. Los datos ya existen
  (`GET /api/matters`, `GET /api/folders`). No es necesario para que la función trabaje hoy.
- Nota: sigue pendiente de Cursor el control del tope de gasto de **CP-E1** (ver abajo);
  ese trabajo NO se mezcló con CP-E2.

### Comportamiento esperado

- En un asunto: "Analiza @expediente a fondo" → Mia trabaja con los documentos del asunto
  (igual que antes, pero ahora explícito); "compara con @expediente:\"Otro caso\"" cruza con
  otro expediente del despacho. La búsqueda interna del turno usa el texto SIN la mención
  (no se ensucia con el documento adjunto).
- Con Mia libre (Telegram): "Según @expediente:\"Zurich\" ¿qué defensa tengo?" trae ese
  expediente a la respuesta. Nombre ambiguo o inexistente → aviso en llano, sin adjuntar.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_context_references.py` **43/43** (parseo + denylist de rutas +
  resolución por título/etiqueta con RLS + AISLAMIENTO entre despachos + sellado
  anti-inyección + techo de tokens con recorte marcado + query de recuperación limpia);
  regresión **ALL PASS (54 suites)** (test_rls 12/12 HALT). Sin frontend web → sin npm build.
- Capa 2 (revisor adversarial independiente): confidencialidad/RLS, confinamiento a las
  filas del despacho (nunca disco), anti-inyección (CP-S1), escape LIKE y fail-open/closed
  CONFIRMADOS. 2 MAYORES (fetch sin LIMIT en SQL → tope de recursos; techo de tokens en el
  listado de carpeta → presupuestado por archivo) + 2 MENORES (`@expedientes` plural;
  query solo-referencia) corregidos y RE-VERIFICADOS CERRADOS antes del commit. Ver
  memory/progress.md sesión 31.
- Capa 3: NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP-E1 — Auditoría de acciones + tope de gasto de IA (2026-07-03)

### Qué cambió (lenguaje simple)

- **Registro de auditoría:** Mia ahora deja rastro de cada acción del despacho
  (quién hizo qué y cuándo) en un registro interno append-only, por despacho. Es
  invisible y no cambia nada de la experiencia; sirve para cumplimiento/confianza
  al vender a firmas grandes. Guarda solo metadatos (acción, ruta, ids, resultado)
  — NUNCA el texto de la consulta ni el contenido del expediente.
- **Tope de gasto de IA:** el despacho puede fijar un presupuesto MENSUAL en dólares.
  Al alcanzarlo, los turnos nuevos se pausan con un aviso en llano hasta que el
  abogado suba el tope o llegue el mes siguiente. Antes solo se MEDÍA el gasto
  (tarjeta "Valor entregado"); ahora se puede LIMITAR.

### Frontend a construir (Cursor — capa 3): control del tope en el Panel

- **`GET /api/policy/budget`** → `{monthly_budget_usd, spent_this_month_usd,
  remaining_usd, over_budget, unlimited}`. `monthly_budget_usd`/`remaining_usd` son
  null cuando es ilimitado (`unlimited: true`).
- **`PUT /api/policy/budget`** body `{"monthly_budget_usd": 100}` (o `null`/0 para
  quitar el tope) → devuelve el estado ya actualizado.
- Sugerencia de UI: en el Panel de control, junto a "Valor entregado este mes",
  un control "Tope de gasto de IA este mes" — input en USD + "Sin límite"; mostrar
  gasto del mes y restante; si `over_budget`, un aviso ámbar "Se alcanzó el tope;
  los turnos están en pausa". Estado vacío/ilimitado en llano.
- El REGISTRO de auditoría es backend-only por ahora (no requiere pantalla); una
  vista "Registro de actividad" es trabajo futuro opcional.

### Comportamiento esperado

- Con tope fijado y gasto por debajo: todo igual. Al superarlo, un asunto o el
  asistente responden **402** con el aviso en llano (mostrar el `detail` tal cual).
- El dictado por voz NO cuenta como "acción" en el registro (alta frecuencia).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_observability.py` **22/22** (auditoría RLS + fail-open +
  recorte de campos; tope: roundtrip incl. rama de producción, suma del mes UTC,
  bloqueo/permiso, fail-open); regresión **ALL PASS (53 suites)** (test_rls HALT).
  Sin frontend web tocado → sin npm build.
- Capa 2 (revisor adversarial): confidencialidad (sin fuga del mensaje a
  audit_logs — se guarda solo el path, no el query string), aislamiento RLS,
  fail-open y no-regresión del curador CONFIRMADOS. 1 BLOQUEANTE (el tope no
  persistía sobre la fila tenant_settings que todo tenant ya tiene → jsonb_set
  corregido) + 1 MENOR (borde de mes corrido 5h por la zona del servidor)
  corregidos ANTES del commit y re-verificados. Ver memory/progress.md sesión 30.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E1).

---

## Checkpoint anterior: CP-Z2 — Conversación por voz en Telegram (2026-07-03)

### Qué cambió (lenguaje simple)

- **Mia ya habla.** Si el abogado le manda una NOTA DE VOZ a su bot privado de
  Telegram, Mia la transcribe (en el servidor del despacho, el audio nunca sale de
  ahí), responde, y le devuelve una NOTA DE VOZ hablada. Es el "asistente personal
  en el celular": le hablas y te contesta hablando.
- Regla de modalidad: **voz entra → voz sale; texto entra → texto sale** (el chat
  de texto por Telegram no cambia). Al recibir voz, Mia primero devuelve por
  escrito lo que ENTENDIÓ (para que el abogado verifique la transcripción) y luego
  la nota de voz de la respuesta.
- Respuestas largas (un borrador) siguen yendo por escrito; solo las respuestas
  conversacionales cortas se dicen habladas.

### Frontend (Cursor — capa 3): NO hay UI web nueva

- CP-Z2 vive 100% en el **canal de Telegram** (backend). No toca `frontend/`. El
  asistente conversacional de Mia no tiene pantalla web (es Telegram), así que no
  hay nada que construir ni revisar en la interfaz. El motor de voz de salida
  (`/api/speech/synthesize`, ver abajo) queda **reutilizable** para un futuro botón
  "Escuchar" en la web, pero eso NO es parte de este checkpoint.
- **La capa 3 de este checkpoint la hace Pipe en vivo:** crear el bot de Telegram
  (guía `docs/telegram-setup.md`), instalar la voz desde el Panel (botón "Instalar
  dictado por voz", que ahora también baja el modelo de voz de salida), y **dictar
  una nota de voz real** para oír a Mia responder hablando.

### Endpoint nuevo (por si la web lo usa después)

- **`POST /api/speech/synthesize`** (auth como todo /api/*): body `{"text": "..."}`
  → responde audio **OGG/Opus** (`audio/ogg`), 100% local. Errores en llano: 400
  (texto vacío), 413 (muy largo), 429 (rate-limit), 503 (voz no instalada u
  ocupada), 403 (motor de nube sin opt-in — hoy no aplica, es local).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_tts.py` **26/26** (síntesis local, códec Opus
  round-trip, candado de privacidad, 503 al estar ocupado, rate-limit);
  `test_telegram_bridge.py` extendido **37/37** (bucle de voz completo, modalidad,
  degradación a texto si el TTS falla, reply vacío, chat no autorizado);
  `test_speech_stt.py` **60/60** (instalación ahora incluye el modelo de voz);
  regresión completa **ALL PASS (52 suites)** (test_rls HALT). Sin `npm build`
  (no hay frontend web).
- Capa 2 (revisor adversarial independiente): confidencialidad, autorización,
  modalidad, instalación y concurrencia CONFIRMADOS; 1 MAYOR (espera del semáforo
  sin tope → 503 explícito) + 2 MENORES (reply vacío, guardia de tamaño) CERRADOS
  antes del commit. Ver memory/progress.md sesión 30.
- Capa 3: PENDIENTE — Pipe dicta una nota de voz real (lo único que la
  verificación automatizada no cubre).

---

## Checkpoint anterior: CP-Z1b — La voz instalada en el producto (2026-07-03)

### Qué cambió (lenguaje simple)

- El dictado por voz ya se instala DESDE LA PANTALLA: tarjeta nueva "Dictado
  por voz" en el Panel de control (sección Conectores) con botón "Instalar
  dictado por voz", confirmación explícita en ámbar, barra de avance de la
  descarga (~700 MB) y mensajes del servidor en llano. Ya no hace falta que un
  administrador corra un script.
- El recorrido "Configura a Mia" tiene el paso 7 "Dictado por voz" (detección
  automática + guía explicativa; "Ir al paso" lleva al Panel).
- El chat del asunto ya tiene el BOTÓN DE MICRÓFONO: dictas, Mia transcribe en
  el servidor del despacho (la voz nunca sale de ahí) e inserta el texto en el
  campo sin borrar lo escrito. Este botón lo construyó Claude Code — Cursor
  hace la revisión visual (capa 3), no la construcción.

### Endpoints para la UI (ya construida — revisar, no construir)

- **`GET /api/speech/status`** → `{estado, listo, mensaje, progreso}` donde
  `estado` ∈ instalado | no_instalado | descargando | error; `progreso` (solo
  descargando) = `{fase, descargado_mb, total_mb, porcentaje}` (total/porcentaje
  pueden ser null si el servidor de descarga no anuncia el tamaño).
- **`POST /api/speech/install`** body `{"confirmar": true}` → `{status, message}`.
  Sin confirmación → 400 con `detail` en llano (mostrarlo tal cual).
- **`POST /api/speech/transcribe`** (de CP-Z1): multipart `audio` WAV PCM16 16k
  + `pulir`; responde `{text, cleaned_text, duration_seconds, message}`.

### Qué revisar visualmente (Cursor — capa 3)

1. **`frontend/app/dashboard/page.tsx` · tarjeta "Dictado por voz"**: estados
   Inactivo / Instalando… (barra `role="progressbar"` con MB) / Instalado;
   confirmación `role="alertdialog"` antes de descargar; Cancelar no descarga;
   tras un error el botón reaparece con el mensaje en ámbar; el refresco es
   automático cada 2 s SOLO mientras descarga.
2. **`frontend/app/configurar/page.tsx`**: el paso 7 "Dictado por voz" se pinta
   con su guía expandible (el contenido viene del servidor — no requirió cambios
   en esta página; verificar que el acordeón y el progreso "N de 7" se vean bien).
3. **Micrófono** (`frontend/app/_components/MicButton.tsx`,
   `frontend/lib/useDictation.ts`, `frontend/lib/wav.ts`, integrado en
   `frontend/app/asuntos/[id]/page.tsx`): estados inactivo → grabando (pulso
   rojo + "Dictando… toca para terminar") → transcribiendo (spinner "Mia está
   escribiendo tu dictado…"); `aria-pressed` alterna; el permiso de micrófono se
   pide solo al primer clic; los errores del backend (400/413/429/503) y el
   aviso "No se escuchó voz en la grabación." salen en ámbar bajo el campo;
   PROBAR CON MICRÓFONO REAL dictando en español (lo único que la verificación
   automatizada no pudo cubrir).

### Comportamiento esperado

- Instalar desde la tarjeta: confirmar → "Empecé a descargar…" → barra avanza →
  la tarjeta pasa sola a "Instalado" (verificado en vivo con descarga real).
- Dictar un clip corto → el texto aparece en el campo en ~1-3 s, agregado al
  final de lo ya escrito. Un clip en silencio → aviso honesto en ámbar.
- Ningún texto visible trae jerga técnica.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_speech_stt.py` extendido 41 → **57/57** (instalador:
  consent-first, single-flight, progreso, retry limpio, tar malicioso rechazado,
  idempotencia — sin descargar los pesos reales); `test_setup_wizard.py`
  **30/30** (7 pasos); regresión completa **ALL PASS (51 suites)**; `npm run
  build` verde ×2; verificación EN VIVO por navegador: tarjeta en sus 3 estados,
  confirmación/cancelar, instalación real (descarga del detector de voz desde
  internet), paso 7 del wizard, botón de micrófono con aria correcta, y POST
  multipart navegador→API con WAV real (CORS OK).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 29.
- Capa 3 (Cursor): PENDIENTE — revisar lo listado arriba (en especial dictar
  con micrófono real).

---

## Checkpoint anterior: CP-Z1 — Dictado local (voz a texto) (2026-07-02)

### Qué cambió (lenguaje simple)

- Mia ya puede transcribir la voz del abogado SIN que el audio salga de su
  servidor: un nuevo servicio de dictado 100% local (mismo motor y parámetros
  que Lexter, el dictado que Pipe ya usa y validó en español jurídico).
- El backend está completo y probado; falta el botón de micrófono en la web
  (este HANDOFF). Opcionalmente, Mia puede "pulir" la puntuación del dictado
  con su modelo local (si Ollama está corriendo); si no, entrega el texto crudo.
- Si el servidor no tiene el modelo de voz descargado, el botón debe explicar
  en llano lo que el backend responde (503 con instrucción para el administrador).

### Frontend a construir (Cursor — capa 3): botón de micrófono

- **`POST /api/speech/transcribe`** (multipart/form-data, requiere Authorization
  como todo /api/*):
  - campo `audio`: archivo WAV PCM16 **16 kHz mono** (el navegador debe
    re-muestrear antes de enviar — ver nota técnica), máx. 5 minutos / 32 MB.
  - campo opcional `pulir`: `"true"` para pedir la corrección de puntuación con
    el modelo local (fail-soft: puede volver null).
  - Respuesta: `{text, cleaned_text, duration_seconds, message}` — `text` es la
    transcripción cruda; `cleaned_text` la versión pulida o null; `message`
    solo viene cuando no se escuchó voz ("No se escuchó voz en la grabación.").
  - Errores en llano listos para pantalla: 400 (audio ilegible), 413 (muy
    grande), 429 (demasiados clips seguidos), 503 (dictado no instalado en el
    servidor) — mostrar el `detail` tal cual (lib/api.ts ya lo propaga).
- **Nota técnica de captura:** `MediaRecorder` produce webm/opus, que el backend
  NO acepta. Capturar con Web Audio API (`AudioContext` + `MediaStreamSource`),
  acumular Float32, re-muestrear a 16 kHz mono (p. ej. `OfflineAudioContext`) y
  empaquetar WAV PCM16 en el cliente (~30 líneas; sin librerías externas).
- **UI sugerida:** botón 🎤 junto al campo de texto del asunto y del asistente;
  estados: inactivo → grabando (pulso rojo + "Dictando… toca para terminar") →
  transcribiendo (spinner "Mia está escribiendo tu dictado…") → texto insertado
  en el campo (usar `cleaned_text ?? text`). Si `message` viene, mostrarlo en
  ámbar. Accesibilidad: `aria-pressed` en el botón, estado comunicado con texto
  además del color. Pedir permiso de micrófono solo al primer clic.
- Referencia de diseño (OpenJarvis, en disco): `jarvis-ref/OpenJarvis-main/
  frontend/hooks/useSpeech.ts` y `components/Chat/MicButton.tsx`.

### Comportamiento esperado

- Dictar un clip corto en español → el texto aparece en el campo en ~1-3 s
  (motor local, sin GPU). Clips largos (hasta 5 min) tardan más y llegan
  completos. Un clip en silencio → aviso honesto, no texto inventado.
- El audio JAMÁS sale del servidor: no hay que pedir consentimiento de nube.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_stt.py` 35/35 (incluye integración real con
  el modelo descargado: español correcto y audio de 76 s por el camino VAD);
  regresión completa en verde (test_rls HALT).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 28.
- Capa 3 (Cursor): PENDIENTE — construir el botón descrito arriba.

---

## Checkpoint anterior: CP-V2 — Auto-diagnóstico prescriptivo (2026-07-02)

### Qué cambió (lenguaje simple)

- La consolidación semanal de Mia ahora produce un DIAGNÓSTICO con hasta 4
  recomendaciones concretas para el despacho ("Ha corregido 6 veces respuestas
  del mismo tipo — suba su guía de trabajo y desaparecen"), cada una con
  evidencia real contada de la actividad (nunca inventada: con menos de 5
  eventos de señal, Mia calla), impacto en dólares según la tarifa del
  despacho, y puntaje que las ordena.
- Lo que el abogado acepta o descarta NO se le vuelve a mostrar, salvo que el
  problema siga vivo pasados 30 días (entonces vuelve marcado como recurrente).
- El reporte semanal menciona cuántas recomendaciones hay y la principal.

### Frontend a construir (Cursor — capa 3): tarjetas de diagnóstico en el panel

- **`GET /api/dreams/prescriptions`** → `{prescriptions: [...]}` ordenadas por
  impacto (máx. 4). Campos por tarjeta: `id`, `category` (retrabajo | rechazos |
  conocimiento | costo | guias | valor), `headline` (título en llano),
  `prescription` (la receta, 3-4 frases), `evidence` (lista de 3 pruebas con
  números reales), `dollar_impact` (USD/mes o null), `time_impact_mins` (o
  null), `status` (`new` | `recurring`), `age_days`.
- **`POST /api/dreams/prescriptions/{id}/decision`** con body
  `{"action": "accept"}` o `{"action": "dismiss"}` → la tarjeta desaparece.
  404 si ya fue decidida (refrescar la lista).
- Sugerencia de UI: sección "Recomendaciones de Mia" en el Panel de control
  (encima o junto a "Valor entregado"); tarjeta con headline + impacto,
  evidencia expandible, botones "Lo haré" (accept) y "Descartar" (dismiss).
  `recurring` con `age_days` alto merece un matiz visual ("lleva N días").
- Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más
  actividad para hablar con evidencia."
- OJO: las tarjetas reflejan la última consolidación semanal (no tiempo real).

### Resultado de verificación (3 capas)

- Capa 1: gate `test_dreams.py` extendido 16 → **43/43**; regresión completa
  **50/50 suites × 3 corridas** (test_rls 12/12 HALT); migración 022 aplicada
  e idempotente.
- Capa 2 (revisor adversarial independiente): APROBAR tras re-verificación —
  los 4 MAYORES corregidos antes del commit: (H1) una decisión del abogado
  tomada mientras corría el cron semanal podía perderse → el guardado ya nunca
  resetea una fila decidida (solo el resurgimiento explícito a los 30 días);
  (H2) la poda borraba la edad de problemas vivos que solo salieron del top
  por diversidad → ahora se conserva toda señal viva y el panel filtra;
  (H3/H4) la recomendación de costo v1 era imposible de ejecutar (proponía
  mover tareas que YA corren en el modelo económico, hacia una pantalla sin
  ese control) → rediseñada al gasto real pagado + el selector "Motor de IA"
  del Panel de control, verificado que existe y guarda. Menores H5-H7 y
  residuales R1/R2 también cerrados (Riesgo #44).
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-V2).

---

## Checkpoint anterior: CP-C4b — "Configura a Mia" como onboarding explicativo (2026-07-02)

### Qué cambió (lenguaje simple)

- El recorrido "Configura a Mia" ya no solo detecta qué falta: ahora EXPLICA cada
  paso como un onboarding. Cada tarjeta tiene un botón "¿Qué es esto?" que despliega
  qué es la herramienta, para qué le sirve al despacho y cómo se hace paso a paso.
- Se agregó al final el mapa "¿Qué hace cada sección de Mia?" (Asuntos, Revisión de
  borradores, Conocimiento, Panel de control, este recorrido y Telegram).
- Mia también explica el siguiente paso completo cuando se le pregunta por la
  configuración (por Telegram): antes solo enumeraba, ahora acompaña.

### Frontend a revisar (Cursor — capa 3) + UI PENDIENTE de construir

- `frontend/app/configurar/page.tsx` — guía expandible por paso (contenido del
  servidor, `GET /api/setup/status` → `pasos[].guia` y `secciones`), sección del
  mapa de secciones, accesibilidad de la barra de progreso (`role="progressbar"`
  + aria) y del botón (`aria-expanded`). Foco de capa 3: legibilidad del texto
  largo, jerarquía visual del acordeón, contraste.
- **UI que el backend ya soporta pero el frontend AÚN NO tiene** (hallazgos del
  revisor de capa 2 — las guías se redactaron para no mentir mientras tanto, pero
  la experiencia queda a medias hasta que existan):
  1. **Panel de control · sección "Carpetas de trabajo"** — no existe. Backend
     listo: `GET /api/folders/detected`, `POST /api/folders`, `DELETE
     /api/folders/{id}`, `POST /api/folders/sync`. Debe listar carpetas
     registradas + nubes detectadas, permitir registrar por ruta y quitar.
  2. **Panel de control · tarjeta Obsidian: botón "Instalar Obsidian"** — hoy solo
     hay "Sincronizar" + input "Ruta del vault" (con jerga "vault"). Backend listo:
     `GET /api/obsidian/status`, `POST /api/obsidian/install` (body
     `{"confirmar": true}`), `POST /api/obsidian/bootstrap`. Falta el botón de
     instalar (con confirmación) y suavizar el texto "Ruta del vault" → "espacio de
     notas".
  3. **Pantalla de revisión de borrador · botón "Descargar en Word" + informe de
     verificación de citas** (pendiente de CP9, ver ese checkpoint abajo). Las
     guías de CP-C4b se escribieron asumiendo que ESTO existirá pronto.

### Resultado de verificación (3 capas)

- Capa 1: `test_setup_wizard` extendido **30/30**; regresión completa **43 suites
  verdes** (test_rls 12/12 HALT); `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — CORREGIDAS antes del
  commit: (L1) la guía llegaba cortada a 150 caracteres en el chat → ahora completa
  (check a4); (U1/U2/U4/U5/U8) las guías describían pantallas o un chat web que no
  existen → reescritas para decir la verdad del producto HOY y sin referencias
  circulares; (U3) la promesa de Word/verificación se suavizó hasta que Cursor la
  entregue. La UI faltante (carpetas, instalar Obsidian) quedó documentada arriba
  como trabajo pendiente en vez de fingir que existe. Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — revisar la página y, sobre todo, construir la UI
  pendiente de los 3 puntos de arriba.

---

## Checkpoint anterior: CP9 — Equipo de especialistas para producir documentos (2026-07-02)

> Estado: APROBADO por Pipe y mergeado a `main` (2026-07-02). Falta la UI del
> frontend (botón Word + informe de verificación) — ver abajo.

### Qué cambió (lenguaje simple)

- Al preguntar en un asunto, Mia ya no trabaja "de un solo envión": ahora un
  equipo de especialistas hace el trabajo por etapas, cada uno con el estilo
  del despacho — uno establece los HECHOS del expediente, otro INVESTIGA las
  normas y sentencias aplicables según el país del despacho (usando primero el
  corpus jurídico interno del sistema), otro CRUZA hechos con derecho y emite
  el diagnóstico, otro REDACTA el borrador, y un VERIFICADOR revisa cita por
  cita: toda cita sin respaldo queda marcada [VERIFICAR] automáticamente
  (antes se nos escapaban sentencias sin marca — el riesgo detectado en la
  comparación de CP6).
- El avance se ve en vivo en el chat: "estableciendo los hechos…",
  "investigando normas…", "cruzando los hechos con el derecho…",
  "verificando las citas…".
- Botón nuevo posible: **descargar el borrador como documento Word** con
  formato de escrito judicial (el backend ya lo sirve).

### Frontend a revisar (Cursor — capa 3)

- NO se tocó ningún archivo del frontend en este checkpoint: el backend emite
  datos nuevos que la UI puede aprovechar. Trabajo sugerido para la
  Pantalla 2/3 (`frontend/app/asuntos/[id]/page.tsx`):
  1. Botón "Descargar en Word" → `GET /api/matters/{id}/draft.docx`
     (descarga directa; 404 si no hay borrador).
  2. Mostrar el informe del verificador de citas: el SSE `awaiting_review` y
     `GET /api/matters/{id}/draft` ahora traen `verification`:
     `{citas, marcadas, respaldadas, anotadas, detalle:[{cita, estado}]}`.
     Sugerencia: una línea sobria bajo el borrador ("Mia revisó N citas; M
     quedaron marcadas para tu verificación") con detalle expandible.
  3. Los mensajes nuevos del avance ya llegan por el evento `thinking`
     existente — no requiere cambio, solo verificar que se vean bien.

### Comportamiento esperado

- Al preguntar en un asunto: los mensajes de avance cambian por etapa (5
  frases distintas antes de "Borrador listo"); el turno tarda MÁS que antes
  (son 4 pasos de razonamiento en vez de 2 — calidad sobre velocidad).
- El borrador llega con TODAS las citas específicas o marcadas [VERIFICAR] o
  respaldadas en el corpus del sistema; el diagnóstico conserva el resumen en
  3 líneas (problema/normas/riesgo) de CP6.
- El Word descarga con encabezados, viñetas y el pie "no radicar sin
  verificar las citas marcadas".

### Bugs conocidos / fuera de alcance

- El detector de citas es conservador: puede marcar de más (inofensivo — el
  abogado revisa algo que estaba bien), y no detecta una marca escrita ANTES
  de la cita. Artículos con numerales intercalados ("artículo 164, numeral 2,
  literal i del CPACA") pueden escapar al detector — deuda anotada.
- El costo por turno aproximadamente se duplica (4 llamadas de razonamiento
  en vez de 2). Decisión consciente: calidad del documento sobre costo.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_document_pipeline` **41/41**; regresión completa
  del repo en verde (43 suites; test_rls 12/12 HALT); `test_hitl_flow`
  actualizado al orden nuevo del equipo (19/19).
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 2 mayores
  CORREGIDOS antes del commit: (M1) los expedientes grandes recuperaban su
  turno solo una vez por conversación y ahora cada etapa tiene su propio
  rescate; (M2) un patrón del verificador podía congelar el servidor con
  texto malicioso (confirmado con medición) — reescrito y movido fuera del
  hilo principal; ambos con checks de regresión (cp9-37..41). Menores
  corregidos: nombre de archivo Word con caracteres especiales, contexto
  impreciso al especialista de hechos, color/limpieza del Word. Revisión por
  lectura de patrones conocidos, no auditoría con herramientas de escaneo.
- Capa 3 (Cursor): NO APLICA aún (sin cambios de frontend en este
  checkpoint); queda el trabajo sugerido arriba para cuando se apruebe CP9.

---

## Checkpoint anterior: CP-C4 — "Configura a Mia": el recorrido guiado (2026-07-02)

### Qué cambió (lenguaje simple)

- Página nueva **"Configura a Mia"** (enlace en la barra lateral): un checklist
  de 6 pasos que detecta solo qué está listo y qué falta (perfil, motor de IA,
  Obsidian, carpetas de trabajo, guías, Telegram), con barra de progreso,
  "Ir al paso", guía de Telegram integrada, y "Dejar para después"/"Retomar"
  (el recorrido se recuerda entre sesiones).
- Mia también guía por chat: si le pides "ayúdame a conectar mi Google Drive",
  responde con el estado real de la configuración, no de memoria.
- Detectar NUNCA instala ni registra nada: las acciones viven en sus pantallas
  con sus propias confirmaciones.

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/configurar/page.tsx` (NUEVA) — checklist, progreso, guía de
  Telegram inline, mensajes de error en ámbar. Hallazgo del revisor de capa 2
  DIFERIDO a esta capa: la barra de progreso necesita `role="progressbar"` +
  aria; los estados del paso se comunican en parte solo por color/símbolo
  (accesibilidad).
- `frontend/app/_components/Sidebar.tsx` — enlace nuevo "Configura a Mia".
- Siguen pendientes los 4 archivos de CP7 (sección siguiente) — puede
  revisarse todo junto.

### Resultado de verificación (3 capas)

- Capa 1: regresión **42/42 suites PASS** (test_rls 12/12 HALT); gate nuevo
  `test_setup_wizard` **21/21**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 3 mayores
  (disparador del chat confundía verbos jurídicos "se configura la causal";
  detección con winget de hasta 60 s en el camino del request → caché 60 s;
  I/O de disco bloqueando el event loop → threads) y 3 menores: corregidos
  antes del commit. Residual aceptado: carrera menor en "dejar para después"
  con dos clics simultáneos (se autocorrige). Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — archivos listados arriba.

---

## Checkpoint anterior: CP7 — El abogado gobierna todo desde la pantalla (2026-07-02)

### Qué cambió (lenguaje simple)

- Pantalla "Conocimiento": pestaña nueva **Habilidades** (qué tan bien le va a
  Mia con cada procedimiento, con % de aprobación); botón **Importar guías**
  (sube las guías de trabajo del despacho en .md/.txt/Word, con detalle en
  llano de lo que se importó/omitió); cada sugerencia ahora dice **qué
  procedimiento se modificaría**; sección nueva **"Orden del conocimiento"**
  (propuestas de Mia para unir guías repetidas o archivar las sin uso, con
  Aprobar/Rechazar).
- Panel de control: el selector de modelos técnicos se reemplazó por **"Motor
  de IA"** en español llano (Mi suscripción / Nube / Todo en mi equipo) y
  ahora SÍ guarda el cambio; sección nueva **Recordatorios** (ver y cancelar,
  con fecha Y HORA); la clave de Pinecone ya se escribe oculta (••••).
- Onboarding: se retiró la pregunta del "modo profundo" (era una función no
  implementada — no se ofrece lo que no existe).
- Pantalla del asunto: el panel Diagnóstico mostrará el resumen en 3 líneas
  (problema/normas/riesgo) cuando el backend lo emita (llega con CP6, hoy
  pendiente de aprobación de Pipe; sin él, todo se ve como antes).

### Frontend a revisar (Cursor — capa 3) — TODOS los archivos de este checkpoint

- `frontend/app/memoria/page.tsx` — pestaña Habilidades, Importar guías,
  target en sugerencias, sección Orden del conocimiento.
- `frontend/app/dashboard/page.tsx` — Motor de IA, Recordatorios, input de
  clave oculto.
- `frontend/app/onboarding/page.tsx` — pregunta p19 retirada (verificar que la
  navegación entre preguntas no se sienta rota).
- `frontend/app/asuntos/[id]/page.tsx` — resumen estructurado condicional en
  el panel Diagnóstico (los 2 pendientes de CP5 sobre este archivo y
  `frontend/app/page.tsx` siguen abiertos — puede cerrarse todo junto).
- Foco de la capa 3: diseño de interfaz, accesibilidad (labels, foco,
  contraste), consistencia de UX entre secciones nuevas y viejas, y
  superficies de seguridad visibles (ninguna clave/dato sensible en claro).

### Comportamiento esperado

- Con datos: Habilidades lista procedimientos con barra de % aprobado;
  Importar guías muestra "Se importaron N guías…" con detalle por archivo;
  el selector de Motor de IA persiste tras recargar; cancelar un recordatorio
  lo quita SOLO si el servidor confirmó (si falla, aviso en ámbar).
- Sin datos: cada sección nueva tiene su estado vacío en español llano.

### Resultado de verificación (3 capas)

- Capa 1: regresión **41/41 suites PASS** (test_rls 12/12 HALT);
  `test_second_brain_ui` extendido **26/26**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 1 mayor
  (cancelar recordatorio mostraba éxito aunque fallara) + 1 mayor
  preexistente (clave de Pinecone visible) + 5 menores: TODOS corregidos
  antes del commit. Revisión por lectura de patrones, no auditoría con
  herramientas. Deuda §G anotada fuera de alcance: textos "second brain",
  "vault", "Pinecone" del dashboard viejo.
- Capa 3 (Cursor): PENDIENTE — revisar los 4 archivos listados arriba y
  devolver hallazgos en la sección final de este documento.

---

## Checkpoint anterior: CP-C3 — El circuito de aprendizaje quedó cerrado (2026-07-01)

### Qué cambió (lenguaje simple)

- Cuando el abogado rechaza o corrige un borrador, la sugerencia de mejora
  que Mia genera ahora apunta al procedimiento que DE VERDAD participó en
  ese trabajo (antes podía proponer mejorar uno cualquiera), se redacta
  viendo el contenido real de ese procedimiento, y al aplicarla queda
  guardada la versión anterior (se puede volver atrás).
- El listado de sugerencias ahora dice QUÉ procedimiento se va a modificar.
- Para ver el ciclo completo en vivo falta UN insumo de negocio: que Pipe
  suba sus primeras guías de trabajo (botón/endpoint de importar guías).

### Frontend a revisar (Cursor — capa 3)

- Sin pantalla nueva. NOTA para CP7: `GET /api/proposals` ahora devuelve un
  campo `target` (título del procedimiento a modificar) — la Pantalla 4
  (memoria) debería mostrarlo junto a cada sugerencia. Siguen PENDIENTES de
  capa 3 los 2 archivos de CP5.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gates extendidos: test_feedback_processor 26/26, test_gepa 18/18,
  test_trace_capture 23/23, test_ux 29/29.
- Capa 2 (revisor independiente): **APROBADO** sin bloqueantes; sus 2
  hallazgos mayores (del flujo pre-existente de aplicar sugerencias,
  agravados por este checkpoint) se corrigieron antes del commit.
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend; ver nota para CP7 arriba).

---

## Checkpoint anterior: CP-B3 — Mia te avisa y recuerda (2026-07-01)

### Qué cambió (lenguaje simple)

- Mia ahora es proactiva: el abogado le pide recordatorios escribiéndole
  normal ("recuérdame radicar la tutela mañana a las 9") y Mia le avisa por
  Telegram a la hora pactada; también avisa cuando un borrador queda
  esperando su revisión (máximo un aviso al día por asunto) y envía el
  reporte semanal de lo aprendido.
- Regla de negocio dura: si el recordatorio menciona un plazo o actuación
  procesal, SIEMPRE va con [VERIFICAR] — la fecha la pone el abogado y la
  confirma él; Mia no calcula términos legales, y "días hábiles" ni se
  agendan: se pide la fecha exacta.
- Todo es opt-in: sin el bot de Telegram configurado, nada suena y Mia lo
  dice honestamente al confirmar ("quedará visible en tu lista de
  recordatorios").

### Frontend a revisar (Cursor — capa 3)

- CP-B3 NO trae pantalla nueva (la UI de recordatorios llega con CP7; ya
  existen los endpoints GET /api/assistant/reminders y POST
  /api/assistant/reminders/{id}/cancel). Siguen PENDIENTES de capa 3 los 2
  archivos de CP5 listados en el checkpoint anterior.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gate nuevo `test_reminders` **64/64**.
- Capa 2 (revisor independiente, contexto fresco): APROBADO CON
  CORRECCIONES — 2 bloqueantes y 5 mayores, TODOS corregidos antes del
  commit y convertidos en checks del gate (detalle en memory/progress.md,
  sesión 22). Residuales aceptados en memory/bugs-and-risks.md (Riesgo #35).
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP3 + CP-C2 — Conocimiento del despacho y vault de Obsidian (2026-07-01)

### Qué cambió (lenguaje simple)

- CP3: Mia ya analiza con el MÉTODO DEL DESPACHO — al diagnosticar un
  asunto usa las notas y criterios internos del despacho (lo indexado
  desde Obsidian y las carpetas de trabajo), siempre como orientación
  de método, nunca en reemplazo de la norma o la sentencia. APROBADO
  por Pipe con una comparación en vivo (mismo caso, con y sin el
  conocimiento del despacho).
- CP-C2: Mia escribe su memoria donde el abogado la ve — su vault de
  Obsidian. Los conceptos que aprende y los reportes semanales quedan
  como notas normales bajo la carpeta `Mia/` del vault; Mia JAMÁS toca
  las notas del abogado. Incluye instalación guiada de Obsidian para
  quien no lo tenga (con confirmación explícita).

### Frontend a revisar (Cursor — capa 3)

- CP3 y CP-C2 no traen pantalla nueva (la UI de conectores llega en
  CP7). Siguen PENDIENTES de la capa 3 los 2 archivos de CP5:
- `frontend/app/page.tsx`: punto naranja en la lista de asuntos cuando
  hay borrador pendiente (title="Borrador esperando tu revisión").
- `frontend/app/asuntos/[id]/page.tsx`: panel "Diagnóstico" (texto con
  scroll interno; estado vacío: "Mia aún no ha analizado este asunto.").

### Comportamiento esperado

- Con notas del despacho indexadas, al preguntar en un asunto el
  análisis refleja el método interno (y sigue marcando [VERIFICAR] lo
  que corresponda). Si el despacho no tiene notas indexadas, todo se
  comporta EXACTAMENTE igual que antes.
- Al consolidarse un concepto o generarse el reporte semanal, aparece
  una nota nueva en `{vault}/Mia/conceptos/` o `{vault}/Mia/reportes/`
  visible en Obsidian; las notas del abogado quedan intactas.

### Bugs conocidos / fuera de alcance

- Menores anotados por los revisores: el presupuesto del 15% para las
  notas usa un estimador de tokens aproximado (podría quedarse corto o
  largo en casos límite); si el disco/OneDrive del vault no está
  disponible, la nota espejo no se escribe (queda solo en el registro
  interno — no se pierde nada, se reintenta en el siguiente ciclo).
- Decisiones de producto pendientes de Pipe (ver bugs-and-risks.md):
  privacidad de las conversaciones del asistente, diagnóstico visible
  tras aprobar, y deshabilitar la instalación de Obsidian en Modo A.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): regresión completa **40/40 suites PASS**
  (test_rls 12/12 HALT PASS); gates nuevos: test_retrieval_knowledge
  **35/35** y test_vault_write **34/34**.
- Capa 2 (revisores independientes con contexto fresco): CP3 aprobado
  con 1 mayor CORREGIDO (las notas del despacho entran al prompt
  delimitadas y con orden de no obedecer instrucciones embebidas —
  anti-inyección — más margen de recorte y limpieza de metadatos).
  CP-C2 aprobado con 2 mayores CORREGIDOS (escape por junction/symlink
  de Windows hacia fuera del vault BLOQUEADO fail-closed — reproducido
  con mklink /J; escritura al vault ya no congela el servidor con
  discos lentos). Revisión por lectura de patrones conocidos, no
  auditoría con herramientas de escaneo.
- Capa 3 (Cursor): PENDIENTE — revisar los 2 archivos de CP5 listados
  arriba y devolver hallazgos en la sección final.

### Checkpoint anterior: CP-B2 + CP-C1 — Telegram y carpetas del abogado (2026-07-01)

Mia atiende por Telegram (bot privado single-chat, opt-in hasta que
Pipe cree su bot — guía docs/telegram-setup.md) y conoce las carpetas
de trabajo autorizadas (disco, OneDrive, Google Drive); carpetas de
sistema excluidas SIEMPRE. Gates: test_telegram_bridge 22/22 y
test_local_folders 39/39; test_obsidian_sync 22/22 sin regresión.
Revisores: CP-B2 con 2 mayores corregidos (token del bot filtrado a
logs; instructivo roto por espacios de la ruta); CP-C1 con 2 mayores
de privacidad corregidos (subcarpetas de sistema excluidas también en
el descenso recursivo; carpetas >2000 archivos sin pérdida de
conocimiento). Sin frontend (capa 3 no aplica).

### Checkpoint anterior: CP5 + CP-B1 — Diagnóstico visible y modo asistente (2026-07-01)

CP5: panel "Diagnóstico" en la pantalla del asunto + punto naranja de
borrador pendiente en la lista (gate test_ux 29/29 con npm run build);
2 ventanas de carrera de milisegundos anotadas (se autocorrigen solas).
CP-B1: modo asistente — conversación libre con memoria por tenant y
usuario (test_assistant 32/32); el revisor encontró 1 BLOQUEANTE de
confidencialidad entre despachos (compresor compartido) + 2 mayores —
LOS 4 hallazgos corregidos y cubiertos con checks antes del commit.
Capa 3 de Cursor PENDIENTE sobre sus 2 archivos de frontend (los
mismos listados en el checkpoint actual).

---

## Hallazgos de Cursor (capa 3)

### 2026-07-02 — CP9 + CP-C4b: UI pendiente construida + revisión visual

**Qué se construyó (las 3 piezas pendientes):**

1. **Pantalla de revisión de borrador** (`frontend/app/asuntos/[id]/revisar/page.tsx`):
   - Botón "Descargar en Word" en la cabecera → `GET /api/matters/{id}/draft.docx`.
     Nota técnica: la descarga NO puede ser un enlace directo porque el endpoint
     exige el header Authorization — se añadió `apiDownload()` en `lib/api.ts`
     (fetch → Blob → descarga). El error se muestra inline en ámbar, sin jerga.
   - Informe de verificación de citas bajo el borrador: línea sobria ("Mia revisó
     N citas; M quedaron marcadas para tu verificación") con detalle expandible
     cita por cita (`aria-expanded` en el botón). Cada estado se comunica con
     texto + color (no solo color): "Verifícala tú" / "Con respaldo" / "Anotada".
     Si `verification` es null (borradores previos a CP9) no se muestra nada.

2. **Panel de control · sección "Carpetas de trabajo"** (`frontend/app/dashboard/page.tsx`):
   - Lista las nubes detectadas (OneDrive/Google Drive) con botón "Registrar"
     (o sello "Registrada"), las carpetas registradas con "Quitar", y un
     formulario para registrar por ruta (con nombre opcional).
   - "Quitar" pide confirmación explícita porque borra el conocimiento indexado
     de esa carpeta ("Mia… olvidará lo que leyó de ella") — acción destructiva.
   - Botón "Revisar carpetas ahora" → `POST /api/folders/sync`; el mensaje del
     servidor (en lenguaje llano) se muestra tal cual.
   - Texto de privacidad visible: "Mia solo lee las carpetas que tú registres
     aquí. Nunca revisa nada fuera de ellas."

3. **Panel de control · tarjeta Obsidian** (`frontend/app/dashboard/page.tsx`):
   - Botón "Instalar Obsidian" (solo aparece si `GET /api/obsidian/status`
     reporta que NO está instalado) con confirmación explícita en un panel
     ámbar (`role="alertdialog"`) antes de llamar `POST /api/obsidian/install`
     con `{"confirmar": true}`. Cancelar no instala nada.
   - Se muestra el `message` del status en lenguaje llano bajo el título.
   - Jerga corregida (§G): "Ruta del vault" → label "Ubicación de tu espacio de
     notas"; el error de sync "No se pudo sincronizar el vault." → "…tu espacio
     de notas."

**Hallazgo transversal corregido:** `lib/api.ts` descartaba el `detail` que el
backend redacta en lenguaje llano — todo error llegaba al abogado como
"Error 400". Ahora `checkResponse` lee el `detail` del cuerpo JSON y lo usa
como mensaje, así los textos cuidados del backend (p. ej. por qué una carpeta
no es segura, o la confirmación que exige instalar) por fin se ven en pantalla.

**Deuda §G que sigue abierta (ya anotada en CP7, no se tocó aquí):** la tarjeta
"Pinecone" (con "vectores", "Index") y la sección "Salud del second brain"
("Skills activos/archivados") del panel de control siguen con jerga técnica.

**Consistencia pendiente (menor):** la pantalla de revisión usa `alert()` del
navegador para errores de Aprobar/Rechazar (patrón pre-existente); el resto de
la app usa mensajes inline en ámbar. Unificar cuando se retoque esa pantalla.

**Verificación:** `npm run build` verde (11/11 páginas, sin errores de tipos).

### 2026-07-04 — CP-E1 + CP-E3 + CP-V2: UI pendiente construida (capa 3)

**Qué se construyó (3 commits separados, ya en `origin/main`):**

1. **CP-E1 · Tope de gasto de IA** (`frontend/app/dashboard/page.tsx`):
   - Tarjeta "Tope de gasto de IA este mes" junto a "Valor entregado este mes" (grid de 2 columnas en pantallas grandes).
   - `GET/PUT /api/policy/budget`: input USD + checkbox "Sin límite"; muestra gasto del mes y restante cuando hay tope.
   - Aviso ámbar con `role="alert"` cuando `over_budget`: "Se alcanzó el tope; los turnos están en pausa."
   - Errores del backend (`detail` vía `ApiError`) se muestran tal cual en ámbar.
   - Verificado en vivo: registro de usuario de prueba → PUT tope 100 USD → respuesta coherente (`unlimited=false`, `monthly_budget_usd=100`).

2. **CP-E3 · Personas jurídicas** (`frontend/app/personas/page.tsx`, enlace en `Sidebar.tsx`):
   - Pantalla CRUD completa: lista las 3 personas de fábrica en la primera carga (`GET /api/personas` siembra).
   - Crear, editar (formulario inline), eliminar (con confirmación).
   - §G: `model_tier` como selector "El motor del despacho" / "Siempre el motor local — más privado" — sin nombres de modelo.
   - Etiquetas en llano: `role_prompt` → "Cómo debe razonar y hablar esta persona"; `summon_phrases` → "Frases con las que la llamas en el chat".
   - Errores 422 del backend se propagan tal cual (`ApiError.detail`).
   - Verificado en vivo: API devuelve Litigante, Tributarista, Revisor de citas tras registro.

3. **CP-V2 · Recomendaciones de Mia** (`frontend/app/dashboard/page.tsx`):
   - Sección "Recomendaciones de Mia" en el Panel (encima de valor/tope).
   - `GET /api/dreams/prescriptions` + `POST .../{id}/decision` con botones "Lo haré" / "Descartar".
   - Evidencia expandible (`aria-expanded`); matiz ámbar para `recurring` con `age_days`.
   - Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más actividad para hablar con evidencia."
   - Verificado en vivo: tenant nuevo → lista vacía (0 recomendaciones); rutas `/dashboard` y `/personas` responden 200.

**Build:** `npm run build` verde tras cada frente (12/12 páginas al final, sin errores de tipos).

**Deuda §G sin tocar (pre-existente):** tarjeta "Pinecone" (vectores, Index) y sección "Salud del second brain" (Skills) siguen con jerga técnica — anotado en CP7.

**Pendiente de Pipe (capa 3 en vivo, no automatizable aquí):** probar aceptar/descartar una recomendación real cuando el cron semanal haya generado tarjetas; invocar una persona editada en el chat de un asunto.

### 2026-07-04 — CP-E5: tablero de misión por expediente (capa 3)

**Qué se construyó** (commit `f47f143`, ya en `origin/main`):

- **`frontend/app/_components/MissionBoard.tsx`** + pestaña **Plan** en `frontend/app/asuntos/[id]/page.tsx` (junto a Consulta).
- CRUD completo vía `/api/missions/*`: crear misión con propuesta automática de hitos, editar título/objetivo, archivar/eliminar, re-proponer hitos (añadir o reemplazar).
- Hitos: editar título, actor, estado, reordenar (↑↓), añadir manual, quitar. Barra de progreso "X de Y hitos" con `role="progressbar"`.
- §G: `mia` → "Mia lo prepara"; `abogado` → "Lo haces tú"; estados → Pendiente / En curso / Hecho; `is_procedural` → aviso "Toca un plazo — confírmalo tú [VERIFICAR]". Sin campos de fecha.
- Errores 422/502 del backend mostrados tal cual (`ApiError.detail`).
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** crear una misión real ("Preparar la contestación"), editar hitos propuestos y marcar avance en un asunto con documentos.

### 2026-07-04 — CP-P2: automatizaciones consent-first (capa 3)

**Qué se construyó** (commit `5642a73`, ya en `origin/main`):

- Sección **Automatizaciones** en el Panel (`AutomationsSection.tsx` + `dashboard/page.tsx`).
- **Sugerencias de Mia:** `GET /api/automations/suggestions` con botones Activar / Descartar; aviso ámbar en plantillas que tocan plazos procesales.
- **Automatizaciones activas:** lista con resumen en llano (p. ej. "3 días de anticipación") y Quitar (`DELETE`).
- **Crear automatización:** catálogo de plantillas (`GET /api/automations/blueprints`) con formularios expandibles por campo (`entero`/`texto`/`opcion`); `POST` con `plantilla` + `valores`. Errores 422 mostrados tal cual.
- §G: sin "blueprint", "cron" ni "job" en pantalla.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** tener un recordatorio procesal pendiente para que Mia proponga el aviso anticipado; aceptar/descartar en pantalla y verificar que queda activa.

### 2026-07-04 — CP-P3: calendario y correo (Microsoft 365 / Google) (capa 3)

**Qué se construyó** (commit `70ac8e7`, ya en `origin/main`):

- **`MailboxSection.tsx`** + **`MailboxSectionLoader.tsx`** (Suspense para query OAuth).
- **Panel de control · Conectores** y **Configura a Mia**: tarjeta "Calendario y correo".
- `GET /api/mailbox/status` — muestra conectado / proveedor o botones Conectar Microsoft 365 / Google Workspace.
- `POST /api/mailbox/connect/{provider}` → redirige a la URL de consentimiento; opción «Incluir contenido de correos» (`?content=1`).
- `DELETE /api/mailbox/disconnect`; `PUT /api/mailbox/content-analysis` — opt-in de resumen con IA (checkbox).
- Tras OAuth, el backend redirige a `/configurar?mailbox=conectado|error` — la UI muestra el mensaje.
- §G: sin "OAuth", "token" ni "Graph"; errores 503/422 del backend tal cual.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe:** registrar la app en Azure/Google, pegar llaves en `.env`, y probar el flujo completo de conexión en vivo.

### 2026-07-06 — Rediseño del onboarding + de-jerga de Conocimiento (capa 3)

**Qué se construyó:**

1. **Pantalla final del onboarding** (`frontend/app/onboarding/page.tsx`):
   - Consume `summary` de `POST /api/onboarding/complete` y lo muestra en tarjeta con Markdown legible (viñetas y negritas).
   - El `soul_content` técnico quedó en `<details>` plegable "Ver detalle técnico".
   - Eliminada lógica de preguntas `p15`/`p16` (objetivo del año y pilares) que el backend ya no envía.

2. **Días de la semana (p17):** checkboxes ahora incluyen los 7 días (añadidos Sábado y Domingo).

3. **Herramientas (p18):** reemplazados chips libres por checklist curada con descripción por opción (Correo, Calendario, Gestor documental, Mensajería, Carpetas en la nube, Notas/Obsidian marcada "Próximamente") + campo "Otra herramienta" para texto libre. Los valores se envían como lista de textos en `memory.tools_that_survived`.

4. **Conocimiento** (`frontend/app/memoria/page.tsx`): pestañas renombradas — "Temas que Mia va aprendiendo", "Documentos y fuentes", "Lo que Mia sabe hacer", "Mejoras que Mia propone" (Mi despacho sin cambio).

**Build:** `npm run build` verde (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** completar el onboarding de punta a punta y verificar que el resumen final refleja las respuestas; probar selección de herramientas y días de fin de semana.

### 2026-07-12 — CP-E6: Sistemas conectados (capa 3)

**Qué se construyó:**

- **`frontend/app/_components/ConnectedSystemsSection.tsx`** — UI consent-first sobre `/api/mcp/*`.
- Integrado en **Configuración → Conexiones** (`ConexionesSection.tsx`), alineado al design system actual (`ConnectorCard`, `Button`, `Input`, `Label`).

**Comportamiento:**

- `GET /api/mcp/status` → una tarjeta por sistema (`display_name`, descripción, nota de permisos).
- Formulario con campos `fields` (secretos como password); **Conectar** → `POST .../enable` con `{ env, secrets }`.
- Si habilitado: **Desconectar** (`disable`) y **Borrar credenciales** (`forget`, con confirmación).
- Secretos nunca se precargan; errores del backend en llano (`ApiError.detail`).
- §G: sin "MCP" / "servidor" / "tenant" en pantalla.

**Build:** `npm run build` verde (warnings preexistentes de `useReducedMotion` en `_welcome/`, no bloquean).

**Pendiente de Pipe:** conectar un sistema real cuando el cliente MCP esté activo; OAuth/correo siguen con activación diferida.

### Corrección post-Cursor (Claude Code · verificación de la entrega integrada)

- **Exactitud del resumen del verificador (corregido):** la línea sobria contaba
  solo `marcadas` para decir cuántas citas verificar, pero el abogado debe
  verificar TODA cita con la marca [VERIFICAR] en el texto final = `marcadas`
  (las que ya venían marcadas del redactor) **+ `anotadas`** (las que el
  verificador añadió por no tener respaldo). Con el conteo anterior, un caso real
  (5 citas: 3 marcadas + 2 anotadas + 0 respaldadas) mostraba "3 quedaron
  marcadas" cuando en el borrador hay 5 con marca; y peor, un caso de 0 marcadas
  + 2 anotadas decía "todas quedaron con respaldo" (falso — 2 sin respaldo). Eso
  subrepresentaba justo el riesgo que CP9 existe para evitar. Corregido en
  `revisar/page.tsx` (`porVerificar = marcadas + anotadas`). Build verde,
  regresión 43/43 tras el cambio.
