# Mia — Resúmenes de sesión

## 2026-09-02 — Sesión 63 · auditoría del trabajo de Claude Code y cierre del cableado

TL;DR: se revisó el estado que dejó Claude Code con Opus xhigh y se contrastó con Sol, Terra y
Luna xhigh. El punto de partida `a961131` ya estaba en `origin/main`; no había commits perdidos.
Se corrigieron fallos de resiliencia del frontend, una referencia ARIA colgante, contratos de
pruebas que habían quedado con rutas antiguas, portabilidad del holdout/CI, el MIME habitual de
Word y la captura de errores sin filtrar query strings. La verificación rápida quedó en **35/35**
(167,4 s);
lint, TypeScript, build de 17 rutas y `cargo check` pasaron.

Qué dejó Claude Code: bienvenida de 7→5 pasos y `/ayuda`; revisión previa de puntos abiertos y
atajos reordenables; capacidades de ayudantes medidas de forma honesta; 49 superficies Luxury
con gate del puente; purga segura de carpetas, holdout y barreras contra tests ciegos; y el nuevo
rediseño denso de `/ayuda` y `/configurar`.

Qué sigue: el instalador NSIS de disco es de 2026-08-14 y debe reensamblarse desde checkout
limpio, instalarse y probarse en frío; falta el cotejo visual humano contra el Design Pack; la
regresión con LiteLLM vivo y Telegram configurado; y el benchmark comparativo real con revisión
ciega. Los expedientes muy grandes siguen limitados por la suscripción, mitigados pero no resueltos.
Las imágenes de Antigravity siguen ausentes. No se tocó lógica jurídica ni datos reales.

## 2026-07-20 — Sesión 50 · Mia lee el expediente de verdad · no puede afirmar sin respaldo · no es de ningún país
TL;DR: 18 commits en la rama (sin push) que atacan la tesis del producto —leer todo el expediente, razonar con el criterio del despacho y no poder afirmar nada sin respaldo—, con verificación adversarial que encontró seis defectos graves (dos frentes rechazados y rehechos) y la primera prueba en vivo contra un modelo real en varias sesiones.
Nota de continuidad: entre la sesión 49 (2026-07-17) y esta hubo trabajo el 18 y el 19 de julio que nunca se registró en este archivo (Fase 1, incrementos 1-3, y el primer arranque en vivo); su detalle está en `HANDOFF.md`. La numeración sigue el contador de este archivo, no el número real de sesiones.
Qué construimos:
- **Lectura adaptativa del expediente (`00c4c17`).** Con 743.600 caracteres indexados Mia leía 8 fragmentos: el **1,3 % del material**. No analizaba mal — casi no leía. Muere el literal `top_k=8`; el tamaño se deriva del material, del presupuesto real del nodo y de la exigencia de la pregunta. Trampa cerrada: `hnsw.ef_search` nunca se fijaba y con el valor de fábrica de pgvector (40) subir candidatos **degrada el recall sin avisar**. Gate `retrieval_adaptativa` 59/59 (nuevo).
- **Guardián de citas en PROYECTOS (`9516833`).** No existía: un proyecto podía afirmar normas sin una marca `[VERIFICAR]` (comprobado en vivo, cinco citas sin marcar). Se **movió el punto de emisión del SSE** para que el texto salga después de verificarse. Y el peor defecto de la sesión, PREEXISTENTE: el guardián certificaba **"Con respaldo"**, con visto verde y folio real, citas inventadas (`Decreto 108` respaldado por `Decreto 1082 de 2015`).
- **Ordenamiento aplicable y procedencia (`03d861f`).** La jurisdicción nunca llegaba al modelo: vivía en un comentario. Con el hueco abierto el modelo lo rellenaba con lo que más ha visto. `jurisdiction_agnostic` 75 → **104/104**.
- **Rediseño de interfaz por capas (`444d3a1`).** Tokens, primitivas y pantallas; el **Panel deja de ser un marcador de ceros** y consume lo que ya existía construido sin exponer. Ninguna animación respetaba "reducir movimiento" salvo la bienvenida.
- **Andamiaje de lectura agéntica, APAGADO por defecto (`513a50b` + `f791596`).** Segunda pasada tras un verificador: el techo sube de 44 a **128** (igualando el riel clásico — leía un tercio y lo llamaba ahorro) y el check de ahorro deja de ser incapaz de ponerse rojo.
- **Perfil del despacho rediseñado (`c980704`).** Pregunta criterio, no datos censales. El validador que detectaba el fallo silencioso **existía y solo se invocaba en un test**. Frente rechazado por su verificador y rehecho.
- **Carpetas + Sala (`91bd2e0`).** Causa raíz de las dos suites en rojo desde hacía sesiones (esperas que no aguardaban la convergencia, demostrado por falsificación) y **la cobertura que no existía: "carpeta vinculada a un proyecto"**, el escenario que falló en producción. La Sala gana presupuesto propio (desbordaba de verdad: 212.000 sobre un tope de 150.000).
- **El recorte por presupuesto (`3063df5`).** Partía por mitades ciegas, desperdiciaba la mitad del cupo (utilización **50 % → 99 %** medida) y tiraba primero lo que el modelo había pedido (de 12 ampliaciones sobrevivían 2; ahora 6).
- **Selector de países honesto (`6e0cacc`).** 21 casillas cableadas a mano, material real para uno. Defecto **visto en una captura**, no leyendo código.
- **Meta-gate contra las puertas que aprueban sin mirar (`f2bbec2`).** Prueba las pruebas: recorre `execution/` con análisis sintáctico (no regex), porque hay que **seguir el valor por una variable intermedia** —la forma exacta del fallo de `b5`— y reconocer el arreglo. **Verifica su propia premisa** (si mañana amplían el caching, se pone rojo pidiendo ensancharse). La aserción **negativa** tumba la entrega; la positiva solo avisa, para que el gate no nazca rojo y alguien lo desactive. Inventario: **120 suites, 11 expuestas, CERO de la clase silenciosa**.
- Menores: los agentes del despacho volvían a salir como chips (`aaa3d1a`); tres componentes que **desaparecían en tema oscuro** (`96d3449`).
Qué decidimos (detalle en decisions.md #37-#42):
- **Cuánto lee Mia se DERIVA, no se cablea.** Cobertura en **0.22** tras medir que 0.35 multiplicaba el gasto por 11-20; 0.15 rompía la promesa que custodia el gate `a1`. `MAX_TOP_K` se deja holgado a propósito: un techo que muerde siempre devuelve el producto a un número fijo.
- **Pipe sobre la lectura agéntica**, textual: *"no se puede establecer como funciona Claude code o codex? al fin y al cabo su motor será uno de ellos"*. Superior a las tres opciones que se le ofrecieron. Medido: **4,3× más barato** con un modelo que se conforma, **3,7× más caro** con uno que amplía siempre. Lo que el diseño garantiza no es ahorro universal: es que el tamaño de la lectura deje de ser una adivinanza.
- **El texto de un proyecto se emite DESPUÉS de verificarse.** Añadir el nodo sin mover la emisión lo habría dejado decorativo.
- **Marcar de más es inofensivo; respaldar de más destruye el producto.** Se aplicó al cotejo de respaldo y al recortar la promesa del selector.
- **El selector conserva los 21 países y marca solo en positivo.** Ordenar primero los preparados vuelve el producto colombiano; reducir la lista a lo instalado deja una casilla y grita lo mismo. La lista es un autocompletar, no un catálogo de capacidades.
- **La promesa se recortó a lo defendible** tras leer el paquete: solo fuentes oficiales y forma de citar. Festivos incompletos y el resolutor de plazos no está cableado a ellos; los formatos de identificación no son beneficio de elegir país porque el anonimizador aplica todos los paquetes siempre.
Verificación: HALT `test_rls` 19/19 y `check_env_pins` 10/10. Tres suites nuevas. **Prueba de mutación en todos los frentes nuevos.** Bloqueante de entorno cerrado: migraciones 044/045/046 no constaban en el ledger (la 044 nunca había corrido) — 41/44 → **44/44**. Primera prueba EN VIVO contra un modelo real: un despacho sin país pasó de recibir cinco artículos de un país concreto a cero artículos, cero códigos, cero países. **Dos matices honestos:** el guardián determinista detectó **1 de 5** citas (las otras las marcó el modelo obedeciendo, que es de lo que el guardián existe para no depender), y la fuga de jurisdicción resultó **intermitente**, no constante. **NO se corrió la regresión completa** y la línea base heredada de "84 suites" no es cierta: existen 116.
Qué sigue: ampliar el guardián a citas abreviadas (`arts. N y ss.`, siglas de código — las siglas van en el pack, nunca en el código); **banco de casos + benchmark ciego contra el modelo vivo**, que es la brecha de fondo (ningún gate corre contra un modelo real); segundo paso de la lectura agéntica (que el bucle pueda **reformular** la consulta, no solo pedir más de lo mismo); sección `## aprendido` del perfil vía `update_soul`; riesgos nuevos #75-#80. **De Pipe:** aprobar el push de los 18 commits y decidir entre profundidad en un ordenamiento o anchura verificable en varios — hoy el producto insinúa lo segundo y entrega lo primero.

## 2026-07-17 — Sesión 49
TL;DR: Se cablearon 6 features que estaban "activas por fuera, muertas por dentro" + verificación visual en vivo.
Qué construimos: (A) Banco de oro conectado al examen (run_full_suite + POST /gold-cases:evaluate, gated por allow_eval_real_data); (F) borrada gepa_run_all_tenants huérfana; (A-Pinecone) store secundario opt-in por despacho, aislado por namespace, fail-soft, nunca externaliza el expediente; (B-MCP) consumidor real stdio en sandbox por tenant, salida SELLADA [VERIFICAR], soberano bloquea antes de lanzar el subproceso; (D) blindaje del instalador: /health reporta migraciones aplicadas vs esperadas + checkpointer (migración 043), la cáscara Tauri frena si la base no terminó de actualizarse, backups rotan a 3; (E) atajos de un clic en el chat (pre-llenan, no auto-envían) + salud de guías sana/revisar (migración 044, fail-open).
Qué decidimos: Pipe eligió E completa (atajos + salud). Orquestación multi-agente: Opus coordina, Sonnet implementa grupos disjuntos, Opus verifica adversarial re-corriendo el gate; un solo escritor de git; deps y numeración de migración las prepara el coordinador (D=043, E=044).
Verificación: cada meta con su gate verde; HALT test_rls 19/19 y check_env_pins 10/10; verificación visual en vivo de chat/atajos y memoria/salud = PASA. 7 commits + retro.
Qué sigue: capa 3 en vivo de Pipe — MCP e2e (arrancar LiteLLM y re-correr test_mcp stdio-live), Pinecone real (llaves+índice dim 1024), banco de oro e2e, delegación D3 (Riesgo #66); ajuste opcional de cupo de agentes en list_shortcuts (≥6 guías).

## 2026-07-16/17 — Sesión 48 · MIA deja de ser colombiana + Agent Hub/Banco de oro cableados + criterio (los 8 principios)
TL;DR: 17 commits en tres frentes — se le quitó a MIA el sesgo colombiano que llevaba hardcodeado por dentro (4 fugas de confidencialidad cerradas), se hicieron reales dos capacidades que tenían API y estaban muertas, y se le dio criterio jurídico; de paso, la DB portable volvió a arrancar y aparecieron DOS gates que llevaban sesiones en rojo sin que constara (la línea base de "84 suites ALL PASS" NO era cierta).
Qué construimos:
- **Bug crítico (`ca7cd74`):** la bienvenida llamaba `/api/settings/model-policy` y la ruta real es `/settings/model-policy`; el 404 lo tragaba un catch vacío → elegir motor u opt-in de OpenRouter/NotebookLM **fallaba en silencio** y el abogado creía que había quedado fijado. Ahora la bienvenida se detiene con motivo en llano si no persiste.
- **Frontend (`960553b`, `32880a3`):** el borrador pendiente lleva a la pantalla de revisión; se consumen `?sin_borrador`/`?confirmed` (antes nadie los leía); el drift del curador se detecta por status 409 y no buscando "409" en el texto (**el caso normal fallaba**); locale del equipo en vez de "es-CO" (8 sitios); el detonador de cuantía suma UVT/UIT/UMA/IPREM/SMI y €; token `--cta-strong` con contraste medido sobre el fondo real (**5.10:1**; antes ~1.90:1, ilegible).
- **Agnosticismo backend (`902bd90`, `c4b57f5`, `09d00c7`, `47f5578`):** los patrones de identificación, las pistas de dirección y el léxico del buzón se movieron al pack `co/` sin alterar un carácter (cero regresión para el fundador); migración 036 deja los DEFAULT de jurisdicción en 'generic' y la decisión pasa a Python (**nunca 'co'**); `firm_profiles` hacía nacer colombiano a TODO despacho nuevo; y el prompt del anonimizador le decía al modelo "texto jurídico colombiano" — se le escapó a tres auditorías del mismo archivo el mismo día. **Cuatro fugas de confidencialidad cerradas**, todas confirmadas ejecutando.
- **Agent Hub + Banco de oro (`65e521d`, `84a059b`):** `graph.py` leía `metadata['delegate']` y nadie lo escribía nunca; el consentimiento del banco de oro solo se LEÍA y no había forma de concederlo. Cableados de verdad (candado `hub_gate` fail-closed, captura server-side para que el material sin anonimizar no pase por el navegador) + pantallas ("Ayudantes externos" en Conexiones; Banco de oro en tab propio "Calidad", no junto al dinero).
- **Criterio (`aa8ac3a`, `9019ee6`):** el examen empieza a medir sustancia (un borrador con cero argumentos desarrollados sacaba `ok:True`); los ocho principios destilados de los skills de Pipe y su vault — la Sala de estrategia existía y el redactor **nunca la consultaba**; el wiki era de **solo escritura** (`search_wiki()` no la llamaba nadie); la confianza era un trinquete que solo subía; `dreams` escribía en SOUL sin HITL ni tope (protegido por un test que hubo que invertir); el Curator fundía "siempre X" con "nunca X".
Qué decidimos:
- **Pipe — anonimizador: "enmascarar todo, siempre".** Todos los packs instalados, sin mirar el país del despacho; `jurisdictions` fuera de su API. Secreto profesional > precisión. Efecto aceptado: `artículos 1494-1495` se enmascara como teléfono.
- **Pipe — delegación: "MIA decide y me pregunta".** Rechazó que MIA no pudiera decidir ("parte del encanto de MIA es que puede determinar si necesita agentes o subagentes"). Modos: preguntar (default) / autonomo / solo_si_lo_pido.
- **Pipe — todo en dólares.** Rechazó moneda por jurisdicción: la tarifa en pesos con el gasto en USD obliga a mentir en el "valor neto" o a inventar una tasa.
- **Pipe — construir los 8 principios** de sus skills + su vault, sin clonar nada suyo (ver decisions.md #33-#36).
- Capa 1: `test_rls` 19/19 (HALT), `jurisdiction_agnostic` 75/75, `delegation_decide` 103/103, `argument_engine` 65/65, `soul_guard` 47/47, `eval_substance` 37/37 (nuevo), `gold_cases_api` 55/55, `config_tabs` 21/21, tsc/lint/build verdes. **Con la DB arriba se cerraron tres gates diferidos:** `test_rls` 19/19, `test_welcome_keys` 41/41, `test_setup_wizard` 28/28.
- Honestidad: el gate del Curator prueba el **cableado, no la puntería** del juez (corre sin red); **D3 sigue abierto** (los flags de los CLI nunca se probaron contra un `--help` real).
Qué sigue:
- Capa 3 de Pipe: E2E del instalador en máquina limpia, recorrido visual, login real de NotebookLM y —nuevo— probar en vivo la delegación (D3) y el banco de oro de punta a punta.
- Riesgos nuevos abiertos (#66-#73 en bugs-and-risks.md): diagnóstico del turno sin persistir, "Patrones rechazados" de dreams sin llegar al modelo, hilo del asunto que no sobrevive a un F5, `index_trace` best-effort, SOUL/wiki/trazas en ficheros sin RLS, y la regla nueva de reservar el número de migración al empezar.
- Backlog acotado del sesgo colombiano: FTS 'spanish' (migración de índices) y voz TTS es_MX (una voz por variante) — ambos con su razón de no tocarse hoy.

## 2026-07-13/14 — Sesión 47 · Sala de estrategia (War Room) + OpenRouter motor propio/respaldo
TL;DR: sesión que retomó tras un "error del computador" (el repo de MIA estaba intacto y sincronizado; lo dañado era un `.git` fantasma vacío en la carpeta contenedora, se limpió). Se construyeron y pushearon DOS features en paralelo con orquestación multi-agente y verificación de 3 capas (capa 3 visual queda para Pipe).
Qué construimos:
- **Sala de estrategia (`e8bcc51`):** panel de 3-4 counsel con posturas opuestas (defensor/contraparte/juez/especialista) que debaten un ASUNTO citando el expediente `[doc n]`, ronda de réplicas, y moderador que sintetiza dictamen (fortalezas/riesgos/puntos ciegos/estrategia/próximo paso). `backend/mia/agents/warroom.py` (motor, reutiliza personas.Persona + delegation.run_parallel patrón research_swarm + untrusted.render_documents + verification.annotate_draft en cada intervención y síntesis), 6 rutas en `api/routes/ux.py`, migración `033_warroom_results` (RLS), campos `panel`/`warroom_result` en state, instrucciones L8 `warroom_panelist`/`warroom_moderator` en prompt_builder, frontend `asuntos/[id]/_components/SalaEstrategia*`. Cierre = dictamen + "convertir en borrador" (gate de citas + HITL normales) + descarga Word.
- **OpenRouter motor propio + respaldo (`b582541`):** política nueva "openrouter" (motor principal para despacho sin suscripción del equipo) + overflow en suscripción/nube con opt-in `allow_openrouter`; validación en vivo de la clave en `/activar` (4ª opción de motor); helper `_openrouter_key_present()` (cache 5s lee el .env) para activar el respaldo en caliente sin reabrir; salto AUTH/402→mia-local. `llm.py`, `config.py`, `welcome.py`, `settings.py`, `activar/page.tsx`, ambos yaml, `core.py` (AgentCore.model default None).
Qué decidimos:
- Decisiones de producto de Pipe: nombre "Sala de estrategia" (§G); panel propuesto por MIA y ajustable; conclusiones + debate colapsable; cierre con "convertir en borrador"; solo ASUNTOS. OpenRouter: "Ambas" (motor principal + respaldo), en paralelo.
- Capa 1 verde (test_warroom 52/52, test_rls 19/19 HALT con +7 de warroom_results, check_env_pins 9/9, doc_citation_guard 19/19, CP9 45/45, openrouter_policy 16/16, welcome_keys 41/41, litellm_packaging 66/66, model_policy 40/40, llm_fallback 25/25, agent_core 26/26; tsc verde). Capa 2: 2 auditorías adversariales, 0 bloqueantes, 3 mayores + 8 menores corregidos y re-verificados; muralla de confidencialidad intacta (soberano nunca a la nube); aislamiento entre despachos OK.
- "War Room" de ClaudeClaw NO existe (verificado): solo delegación 1-a-1; la Sala es diseño propio.
Qué sigue:
- Capa 3 de Pipe (recorrido visual de ambas features; DB dev ya arriba en 55432). DEUDA de Pipe: confirmar los slugs exactos de OpenRouter en openrouter.ai/models (slug errado → degrada a local sin romper). Apuesta #3 NotebookLM (transformaciones al ingerir) sigue diferida. Acciones de Pipe sin cambio (firma Azure + OAuth + E2E en frío del instalador).

## 2026-07-12 — Sesión 46 · PULIDO PRE-PRUEBA — Riesgo #60 cerrado + auditoría final de seguridad/bugs
TL;DR: antes del E2E en frío de Pipe, 3 auditorías adversariales independientes (seguridad, corrección/E2E, diff) dieron 0 bloqueantes; se cerró el Riesgo #60 (reinicio en caliente del motor de modelos tras guardar la clave, sin reabrir MIA), se eliminó la única incógnita real (pre-flight del motor sin llaves) y se endureció el manejo del `.env`.
Qué construimos:
- `desktop/src-tauri/src/lib.rs`: comando Tauri `restart_litellm` (registrado en `invoke_handler`), config del proxy + `app_dir` retenidos en `Shared` para re-lanzar, flag `restarting: AtomicBool` con guard, arranque de litellm factorizado a `spawn_litellm` (reusado por arranque y reinicio; re-asigna al Job Object, taskkill viejo + espera de puerto libre antes de re-lanzar). Caminos NO-APLICA seguros (dev / adoptado / cerrando).
- `frontend/app/activar/page.tsx`: tras guardar la clave, si `window.__TAURI__` invoca `restart_litellm` y quita el aviso solo si el motor confirma "reiniciado"; en navegador (dev) conserva el aviso.
- Endurecimientos: `env_writer.upsert_env_keys` rechaza `\n`/`\r` (defensa en profundidad); `first_run.py` aplica ACL restrictiva al `.env` con `icacls` (fail-soft, solo Windows).
Qué decidimos:
- Capa 1: `cargo build` exit 0; `test_shell_hardening` 84/84 (7 checks nuevos), `test_packaging` 23/23, `test_litellm_packaging` 60/60, `test_first_run` 68/68. `test_welcome_keys` + `test_rls` NO re-corridos (DB dev apagada, puerto 55432) → diferidos al próximo arranque; el cambio de `env_writer` se micro-probó.
- Capa 2: revisor adversarial de concurrencia/ciclo de vida del diff → 0 bloqueantes, 0 mayores (sin deadlocks, ningún Mutex cruza await, flag sin fuga, Job re-asignado). Capa 3 (E2E en frío) sigue siendo de Pipe.
- Pre-flight del motor sin llaves: `mia-litellm.exe` empaquetado arranca con 0 llaves de proveedor (salud 200, 5 modelos) — el estado del arranque en frío ya no es incógnita.
- Deuda documentada (Riesgo #61, no bloquea): identidad de cáscara falsificable solo por atacante local (aceptado mono-abogado), carpeta datos=programa (aplazado), setup no re-corre migraciones en updates (deuda de "update").
Qué sigue:
- Capa 3 de Pipe (E2E en frío; para probar el #60 hay que RE-ENSAMBLAR el instalador con la cáscara de esta sesión) + correr los 2 gates diferidos con la DB arriba. Acciones de Pipe sin cambio (firma digital + OAuth).

## 2026-07-11 — Sesión 45 · BLOQUE INSTALADOR F4 — instalador de doble clic ensamblado
TL;DR: se ensambló el instalador NSIS de doble clic que un abogado instala sin Python/Node/Postgres; la incógnita crítica (dónde caen los payloads) se resolvió empíricamente a favor y la capa 2 cerró 5 hallazgos antes del sello.
Qué construimos:
- `packaging/build_installer.ps1` (contrato de ensamblaje): recompila los 3 payloads, copia el PostgreSQL 16 portable **con pgvector** a `dist/pgsql`, verifica y corre el bundler NSIS de Tauri.
- `desktop/src-tauri/tauri.conf.json`: `bundle.resources` (mapa que deja los 4 payloads + yaml + `orchestration.json` RENOMBRADO junto al exe), `targets:["nsis"]`, `windows.nsis` (installMode currentUser = sin admin, lzma), WebView2 `offlineInstaller` (instala sin internet).
- Gate nuevo `execution/test_installer_bundle.py`: invariante central = cada payload que la cáscara busca en `${exe_dir}\X` tiene destino `X` en el mapa, + el renombrado a `orchestration.json`, + console y exclusión de pgAdmin.
- Instalador real producido y probado: `Mia_0.1.0_x64-setup.exe` (~452 MB). Instalado en carpeta aislada → los motores + `orchestration.json` caen DIRECTAMENTE junto al exe (NO bajo `resources/`) → la cáscara los encuentra sin cambios.
Qué decidimos:
- Capa 1: gates del instalador verdes (test_installer_bundle 30/30, test_packaging 23/23, test_litellm_packaging 60/60, test_frontend_packaging 24/24, test_shell_hardening 77/77, test_first_run 68/68) + HALT (test_rls 12/12, check_env_pins 9/9) + test_welcome_keys 39/39. Línea base sube de 85 a 86 suites.
- Capa 2: 3 revisores independientes (seguridad, corrección/build, coherencia cáscara/§G), 0 bloqueantes, ningún secreto de Pipe en el bundle, DB endurecida. 5 correcciones aplicadas y re-verificadas: (1) REVERTIR console=False→True (la cáscara ya oculta la ventana con CREATE_NO_WINDOW; windowed vaciaba el stdout del primer arranque — regresión que introduje y corregí); (2) frontend atado a 127.0.0.1 (estaba en 0.0.0.0, expuesto a la LAN); (3) sacar pgAdmin 4 del pgsql (−736 MB: 860→124 MB); (4) WebView2 offlineInstaller (instalación sin internet); (5) endurecer el gate (backslash + pgAdmin).
- Decisión console: la ventana negra la resuelve la cáscara (CREATE_NO_WINDOW), no el spec → console=True para no perder el diagnóstico del setup (cierra Riesgo #59 pt 3/7 correctamente).
Qué sigue:
- Capa 3 de Pipe (ÚNICO pendiente de F4): E2E en máquina 100% limpia (doble clic, primer arranque en frío, ver el viaje de bienvenida). Es física, no automatizable aquí (esta máquina tiene el entorno dev + colisión de puerto 55432).
- Riesgo #60 (reinicio automático del proxy LiteLLM tras guardar clave) sigue abierto: requiere IPC de Tauri, no se hizo en F4. Acciones de Pipe sin cambio: firma digital (Azure Trusted Signing) + apps OAuth.

## 2026-07-11 — Sesión 44 · BLOQUE INSTALADOR F3 COMPLETA — primera experiencia del abogado rediseñada
TL;DR: el wizard de bienvenida creció a pedido de Pipe: login + registro + activación de llaves + onboarding ahora son UNA experiencia cinematográfica cohesiva, con activación real de la clave de búsqueda en caliente.
Qué construimos:
- Infraestructura visual `frontend/app/_welcome/` (primer uso de framer-motion en el repo): WelcomeShell, BrandMark, WelcomeProgress, transiciones/stagger con soporte reduced-motion, Celebration, MiaLine (typewriter accesible).
- Backend de activación: `GET /api/welcome/status` (público, enriquecido con token), `POST /api/welcome/keys` (escribe .env atómico, hot-reload de la clave de búsqueda VOYAGE, respaldo/OpenRouter diferidos con aviso de reabrir), `POST /api/welcome/keys/test` (ping fail-soft). `env_writer.py` (upsert robusto CRLF/BOM/lock). Migración 031 (`mia_any_tenant_exists()` SECURITY DEFINER endurecida).
- Pantallas rediseñadas: register → "Crear tu despacho", login compacto, `/activar` nueva (motor + clave de búsqueda con validación en vivo + clave de respaldo), onboarding con el mismo lenguaje visual (autosave/reanudación/SOUL intactos).
Qué decidimos:
- Regresión ALL PASS 85 suites (línea base 84→85, `test_welcome_keys` 39/39); npm build verde. Capa 2: 4 revisores independientes (seguridad, backend, frontend, §G/accesibilidad), 0 bloqueantes, varios mayores/menores TODOS corregidos y re-verificados antes del cierre (caso "nube" exige clave, Enter ya no duplica validación, accesibilidad de labels, CRLF+lock en env_writer, SECURITY DEFINER endurecida).
- Riesgo #60 nuevo: el motor que depende del proxy LiteLLM no queda activo hasta reabrir MIA (el exe solo lee .env al arrancar); mitigado con clave obligatoria + aviso fuerte para la política "nube". Modelo de confianza mono-despacho documentado (cualquier usuario autenticado escribe las llaves globales).
Qué sigue:
- Capa 3 EN VIVO de Pipe (recorrido del viaje completo registro→activar→onboarding) y luego F4: tauri bundle NSIS/MSI + E2E en frío + los puntos acumulados del Riesgo #59 (ahora incluye recompilar con welcome.py + migración 031). F4 es la ÚLTIMA fase del bloque instalador.

## 2026-07-10 — Sesión 41 · Bloque C COMPLETO — Agentes jurídicos + perfil unificado + Configuración en subtabs
TL;DR: se cerró el plan de evolución de producto (A/B/C): agentes jurídicos con guías vinculadas, perfil del despacho editable sin repetir la entrevista, y Configuración en subtabs con deep-links.
Qué construimos:
- C1: migración 030 persona_playbooks (RLS, tope 8), prioridad de guías vinculadas en el turno (tope 3 intacto), bloque ≤16k en el asistente (tras la voz, jamás en role_prompt), entrevista kind='agente' con sugerencia de guías y gate HITL por construcción, UI "Agentes jurídicos" con checklist y "Crear con Mia". Riesgo #58 cerrado.
- C2: responses de la entrevista = fuente canónica, firm_profiles derivado (derive_firm_profile), GET/PUT /api/profile/full (update_soul crítico + upsert best-effort que preserva lo sembrado por el flujo legado), MiDespachoSection + CountrySelector extraído del onboarding.
- C3: configurar/page.tsx en 5 subtabs shadcn con hash sincronizado (mount + hashchange + replaceState); todas las anclas externas intactas sin tocar backend.
Qué decidimos:
- Regresión ALL PASS 79 suites (línea base 76→79); npm build verde. Capa 2: 5 menores confirmados (0 mayores/bloqueantes, seguridad sin hallazgos), TODOS corregidos y re-verificados antes del commit `acba433`.
- "soul_responses" sigue siendo archivo por tenant en disco (nombre lógico, no tabla nueva); las canónicas de fábrica sin guías pre-vinculadas; "Modo profundo" (p19) no se muestra en el perfil.
Qué sigue:
- Capa 3 EN VIVO de Pipe (Bloques A+B+C — lista consolidada en HANDOFF.md) y registrar las apps OAuth (guía en docs/guia-conectar-correo-y-nube.md).
- El plan A/B/C quedó COMPLETO: la próxima sesión define el siguiente objetivo de producto con Pipe.

## 2026-07-10 — Sesión 40 · Bloque B COMPLETO — Guías asistidas + gobernanza de skills
TL;DR: El abogado ya puede crear guías conversando con Mia (nunca
       se guardan sin su aprobación) y gobernar lo que Mia sabe
       hacer desde una sola pantalla.
Qué construimos:
- B0: CRUD + versiones de playbooks (migración 029, RLS FORCE);
  origin ∈ {manual, importada, entrevista, asunto, aprendida};
  archivar/restaurar y restaurar versión con snapshot
- B1-B2: motor de entrevista stateless (interviewer.py, jamás
  escribe en DB) + GuideInterviewWizard.tsx (entrevista → borrador
  editable → guardar); botón "Crear con Mia" en Conocimiento
- B3: botón "Convertir en guía" en el asunto, con hitl_outcome
  expuesto al frontend y precarga de contexto del asunto
- B4: subtabs "Guías y documentos" + "Lo que Mia sabe hacer"
  fusionados en "Guías y habilidades"; sugerencias con
  "Editar antes de aplicar"; source_matters en propuestas
Qué decidimos: crear guía ya NO upsertea — si el título choca con
  un playbook existente, 409 en llano (antes sobrescribía en
  silencio); hitl_outcome se expone al frontend con 'edited'
  distinto de 'approved' para no ofrecer "Convertir en guía" sobre
  un borrador editado o rechazado; kind='agente' queda reservado al
  Bloque C (422 por ahora, wizard ya reusable).
Verificación: regresión 76/76 (línea base 74→76, test_playbook_versions
  59/59, test_guide_interview 25/25) · npm build ✓ · revisor capa 2
  con 4 agentes independientes: 10 hallazgos CONFIRMADOS (3 mayores +
  7 menores), TODOS corregidos, re-gate 76/76 · capa 3 PENDIENTE de Pipe.
Qué sigue: Bloque C (agentes jurídicos + perfil unificado +
  Configuración en subtabs) + capa 3 en vivo de Pipe sobre el
  Bloque B; acción de Pipe sin cambio (apps OAuth).

## 2026-07-02 — Sesión 23 · CP7 Frontend sincronizado
TL;DR: El abogado gobierna todo desde la pantalla. CP6 sigue
       esperando la decisión de Pipe (A/B entregado).
Qué construimos (CP7, mergeado a main):
- Pestaña Habilidades + Importar guías + target en sugerencias
- Propuestas del Curator con Aprobar/Rechazar (drift manejado)
- Selector "Motor de IA" (política CP2, persiste, sin jerga)
- Recordatorios en el panel (hora + cancelar confirmado)
- triad_mode fuera del onboarding (Riesgo #27)
- Panel Diagnóstico listo para el resumen de CP6 (condicional)
Verificación: gate 26/26 · npm build ✓ · regresión 41/41 ·
  revisor capa 2 APROBADO (2 mayores + 5 menores corregidos) ·
  capa 3 de Cursor PENDIENTE (HANDOFF con 4 archivos).
Además (misma sesión): CP-C4 mergeado — página "Configura a
  Mia" (6 pasos detectados, retomable) + guía por chat; gate
  21/21; regresión 42/42; revisor APROBADO (3 mayores + 3
  menores corregidos). PILAR C COMPLETO.
Qué sigue: SOLO quedan cosas que dependen de Pipe — decisión de
  CP6 (A/B entregado), bot de Telegram, subir guías, recorrido
  vivo de "Configura a Mia", y la capa 3 de Cursor (HANDOFF).
  CP8 y CP-B4 en pausa por decisión suya.

## 2026-07-01 — Sesión 22 · CP-B3 Proactividad
TL;DR: Mia ya avisa y recuerda por Telegram. Recordatorios en
       lenguaje natural con regla dura de plazos procesales.
Qué construimos:
- Recordatorios por chat (parser determinista, sin LLM) + cancelación
- Aviso de borradores pendientes (debounce 24h) + reporte semanal
- notify.py (canal Telegram opt-in, fail-soft, solo tenant dueño)
- Migración 017 (tabla reminders RLS + debounce en matters)
Qué decidimos: crear/cancelar recordatorios NUNCA depende del LLM;
  plazos procesales siempre [VERIFICAR]; "días hábiles" no se calculan.
Regresión: 41/41 suites (test_reminders 64/64 nuevo; test_rls 12/12).
  Revisor capa 2: 2 bloqueantes + 5 mayores corregidos pre-commit.
Además (misma sesión): CP-C3 cerrado — las sugerencias de mejora
  apuntan al procedimiento que participó en el trabajo rechazado,
  se redactan sobre su contenido real y aplicarlas es reversible.
  Gates 26/26 + 18/18 + 23/23; regresión 41/41; revisor APROBADO
  (2 mayores pre-existentes corregidos igual).
Además: CP6 IMPLEMENTADO en rama feat/cp6-una-sola-voz (una sola
  voz: fachada de 10 capas en los 3 nodos, cierre estructurado del
  diagnóstico, SOUL validado con reintento+fallback). Regresión
  41/41; revisor APROBADO (3 mayores + 3 menores corregidos).
  A/B EN VIVO entregado a Pipe — SIN MERGE hasta su aprobación.
Qué sigue: decisión de Pipe sobre CP6 → CP7 (frontend) y CP-C4.
  Pendientes de Pipe: bot de Telegram (docs/telegram-setup.md) y
  subir sus guías de trabajo (Riesgo #20).

## 2026-06-20 — Sesión 21 · Smoke test login + onboarding
TL;DR: Login real funciona. Onboarding 15 preguntas ágil.
       SOUL.md generado. Smoke test del chat pendiente.
Qué construimos:
- Fix CORS + rutas actualizadas a nueva ubicación
- Todos los task models → mia-local (Ollama)
- Timeout + fallback sin LLM para onboarding
- Onboarding reducido a 15 preguntas ágiles
- SOUL.md generado exitosamente con datos de Lexia
Qué sigue: smoke test completo — crear asunto,
  enviar mensaje en chat, verificar respuesta de Mia.

## 2026-06-20 — Pausa post-goal second brain
TL;DR: Goal completado (23/23 suites). Smoke test del
       login pendiente — Pipe no tiene acceso al computador.
Estado: 23/23 suites · 7 commits · origin/main en 2cc8a15
Qué sigue: levantar los 3 procesos, smoke test del nuevo
  login en navegador, verificar registro + onboarding
  + chat con el nuevo sistema de auth.

## 2026-06-20 — Sesión 20 · Goal Codex — Autoaprendizaje horizontal
TL;DR: Login real multi-tenant, second brain, WikiManager, GEPA, Dreams,
       conectores UI y onboarding horizontal completados.
Qué construimos:
- Auth real: register/login/me con users por tenant, bcrypt, JWT 7 días y frontend sin token dev.
- WikiManager en $MIA_HOME/wiki/{tenant_id}: conceptos, búsqueda, lint, archivo y update tras HITL.
- GEPA Loop: detecta drafts de procedimientos, propone mejoras y archiva skills sin uso.
- Dreams semanal: replay, wiki update, GEPA, lint, nudges en SOUL.md y weekly report.
- UI second brain: wiki, sugerencias, conectores Obsidian/Pinecone y salud del sistema.
- Onboarding horizontal: sin opciones hardcodeadas de país, jurisdicción, área, cortes o herramientas.
Commits: a755447, 7f443dc, 04bcde0, 2901f2c, ef0fc28, 9fda67f
Regresión: 23/23 suites verdes (17 históricas + 6 gates nuevos). `test_rls.py` 12/12 intacto.
Qué sigue: push a origin/main.

## 2026-06-20 — Sesión 19 · Goal Codex — 4 tareas
TL;DR: Issue #1 cerrado. Mia responde end-to-end con Ollama.
       Onboarding tipado + carga masiva completados.
Qué construimos:
- Issue #1 cerrado: chat responde con mia-local/qwen2.5:32b
- Onboarding con tipos mixtos (checkboxes, selects, chips, toggle)
- Carga masiva de documentos + selector de carpeta + progreso
Commits: 2fba689, b1c0960, 4390a48
Qué sigue: Issues #3 (conectores externos desde UI) y 
           pulir UX/diseño visual

## 2026-06-16 — Sesión 18 · Fix intake + Ollama
TL;DR: Issue #1 casi resuelto. Skip embeddings si chunks=0 + 
       timeout Voyage. Pendiente: verificar respuesta de Ollama.
Qué construimos:
- Fix LITELLM_LOCAL_MODEL_COST_MAP en scripts de arranque
- Skip embeddings en intake_node cuando chunks=0
- Timeout=15 + num_retries=2 en embed_texts
- mia-local (Ollama qwen2.5:32b) en litellm_config.yaml
Commits: 7b6c384, a1c47b6
Qué sigue: reiniciar Terminal 2, enviar mensaje en chat,
  verificar que Terminal 1 muestra llamada a mia-local.
  Si aparece → Issue #1 cerrado. Si Ollama responde → 
  Mia funciona end-to-end.

## 2026-06-16 — Sesión 17 · Smoke test vivo completado
TL;DR: Mia v0 operativa en navegador con LLM real. 4 issues 
       identificados en el smoke test.
Qué funciona:
- Onboarding 19 preguntas → SOUL.md generado ✅
- Crear asunto → aparece en lista ✅
- Workspace abre con avatar M + diagnóstico + área chat ✅
- Pantalla Conocimiento (3 tabs) ✅
- Panel de control con métricas reales ✅
Issues encontrados (priorizados):
1. CRÍTICO: Mia no responde en el chat — el turno del agente 
   no se dispara o no llega al frontend vía SSE.
2. UX: Preguntas del onboarding deberían tener tipos 
   (algunas abiertas, otras selección múltiple / checkboxes)
3. UX: No hay carga masiva de documentos ni conexión a 
   carpeta local
4. CONFIGURACIÓN: Conectores externos (Obsidian vault, 
   Pinecone) no configurables desde la UI todavía
Qué sigue: atacar Issue #1 primero (chat sin respuesta).
Sin ese fix, el sistema no es demostrable.

## 2026-06-15 — Handoff smoke test
TL;DR: Mia corre en el navegador. Bloqueado en CORS — fix listo, 
       pendiente de aplicar y verificar.
Estado: 3 terminales corriendo (litellm :4000, uvicorn :8000, 
        next :3000). Frontend carga. Crear asunto falla con 401 
        por CORS faltante.
Fix pendiente de verificar:
  - CORSMiddleware en main.py (causa raíz)
  - Bypass OPTIONS en middleware.py (defensa en profundidad)
  Claude Code ya tiene el diff exacto. Aplicado pero NO verificado 
  en navegador — Pipe apagó el computador antes de probar.
Qué sigue: arrancar los 3 terminales, abrir localhost:3000, 
  crear asunto "Demanda seguros HDI — prueba Mia" y verificar 
  que funciona.

## 2026-06-14 — Pausa post-v0
TL;DR: Terminal se trabó al arrancar smoke test. Proyecto intacto. Retomamos mañana.
Estado: 17/17 suites · 358 checks · commit 64bad3f
Qué sigue: decidir entre smoke test vivo o cerrar riesgo #23 (login real) antes del primer cliente.

## 2026-06-14 — Sesión 16 — 🎉 CIERRE DEL PROYECTO
TL;DR: Módulo 5 cerrado (SOUL.md + entrevista de onboarding + prueba E2E). **Mia v0 operativa.**
       Gate `test_e2e.py` 25/25; regresión **17/17 suites · 358 checks**; `test_rls` 12/12 intacto.
Qué construimos:
- Investigación previa → 4 premisas falsas del spec, presentadas como decisiones: el Doc 4 no
  estaba en el repo (el usuario lo entregó → fuente exacta), el spec decía 18 preguntas pero el
  Doc 4 trae 19 (P19 triad_mode opcional), `$MIA_HOME` no existía en config, `_TASK_MODELS` sin
  `"soul"`. Y A4: la Capa 1 no leía el SOUL.md y el grafo nunca llenaba `soul_snapshot` (Riesgo #11).
- PARTE A: `config.MIA_HOME` (ancla rutas relativas); `llm._TASK_MODELS["soul"]="claude-sonnet"`;
  `onboarding/soul_interview.py` (`SoulInterview`: get_questions/run_interview/update_soul; 19
  preguntas; template de 9 secciones; genera el SOUL.md por LLM conservando placeholders; helpers
  puros de archivo; persiste respuestas para "Revisar mi perfil"); 3 endpoints
  `/api/onboarding/*`. Wiring (decisión #21, "Grafo + prompt_builder"): `initial_state` carga
  `soul_snapshot`, `graph.py` lo antepone en analysis/draft/edit, `MiaAgent.__post_init__` lo carga
  en la Capa 1 — todo None-safe, gates intactos. NO se tocó `prompt_builder.py`.
- PARTE A5 (frontend): `app/onboarding/page.tsx` (wizard de 19 preguntas, progreso, ejemplos,
  resultado con el SOUL.md, Editar/Continuar, "Revisar mi perfil") + `OnboardingGate` (redirige a
  /onboarding la primera vez) montado en `layout.tsx`.
- PARTE B: `execution/test_e2e.py` (GATE FINAL, 25/25) — 7 pasos punta a punta con TestClient,
  `$MIA_HOME` aislado en tempdir, LLM/embeddings mockeados, PDF Ley 80/1993. SOPs
  `architecture/{e2e_runbook,soul_interview}.md`.
Qué decidimos: decisión #21 (SOUL.md como archivo en `$MIA_HOME`, sin DB; 19 preguntas; status por
mtime; wiring del soul_snapshot al grafo Y a la Capa 1, None-safe; imports diferidos para evitar
ciclos). Nuevos riesgos #26 (SOUL generado por LLM — mitigado por la revisión humana en la pantalla
de resultado) y #27 (triad_mode se almacena pero no está implementado como modo de ejecución).
Qué sigue: smoke test VIVO en navegador con LLM real (runbook). Antes del PRIMER CLIENTE, atender
riesgos abiertos: #23 (login real), #25 (diagnóstico/flags UI), #19 (Curator sin HITL ⚖️), #13 (rol
curador SAT-Graph 🔐), #3 (pgvector oficial para clientes). No quedan módulos pendientes.

Citas legales: ninguna entregada. El SOUL de Lexia (Doc 4) y el PDF Ley 80/1993 del E2E son datos
de prueba/identidad del despacho, no citas a un cliente; el corpus semilla sigue marcado [VERIFICAR]
(Riesgo #14). El SOUL.md conserva como placeholder los campos sin responder (no inventa datos).

## 2026-06-14 — Handoff pre-Sesión 16
TL;DR: Terminal cerrándose (contexto ~65%) antes de arrancar el Módulo 5.

**Estado exacto:** **Fase 3 COMPLETA y commiteada.** HEAD = `91f0884`. Commits de este terminal:
- `91f0884` feat: frontend Next.js 14 — 5 pantallas (Fase 3 UX)
- `d4f5c57` feat: superficie /api/* completa + persistencia de perfil (Fase 3 backend)
- `3d3929d` fix: arrancar scheduler en lifespan FastAPI (#22)
- `b6f6bf1` Fase 0-2 completa
Regresión **16/16 suites · 333 checks** verdes. `npm run build` ✓ (frontend compila).

**CORRECCIÓN al borrador del handoff:** NO fue "solo planificación". En este terminal SÍ se
construyó toda la Fase 3: Sesión 14 (superficie `/api/*` + persistencia de perfil `firm_profiles`
+ parser PDF/Word, gate `test_ux.py` 18/18) y Sesión 15 (scaffold Next.js 14 + las 5 pantallas +
cierre del Riesgo #24, gate `test_ux.py` 25/25). Dos commits nuevos (`d4f5c57`, `91f0884`).

**Próximo paso EXACTO:** pegar el prompt del **Módulo 5 (Fase 4): entrevista SOUL.md + prueba
E2E** — es el ÚLTIMO módulo del proyecto. Patrón de siempre: investigar premisas → presentar
decisiones (AskUserQuestion) → construir → gate → regresión → wrap → commit. Tras el gate de
Módulo 5 la regresión pasa de 16 a **17 suites** (la "17/17" del borrador es el objetivo FUTURO,
no el estado actual, que es 16/16).

**Opcional antes de Módulo 5:** smoke test VIVO de la UI (Modo B, 3 terminales: `litellm` /
`uvicorn` / `npm run dev`) — NO se hizo esta sesión; solo se verificó `npm run build` + el gate
de endpoints (TestClient). Sería el primer recorrido real en navegador.

**Riesgos abiertos (principales):** #23 (login real; hoy token de dev en frontend/.env.local),
#25 (diagnóstico de P2 y punto "borrador pendiente" de P1 sin endpoint que los alimente), #19
(Curator consolida/poda playbooks SIN revisión humana ⚖️), #13 (corpus SAT-Graph escribible por
cualquier conexión `mia_app`, sin rol curador 🔐). Lista COMPLETA en `memory/bugs-and-risks.md`.

**Arranque rápido próxima sesión:** leer `CLAUDE.md` + `memory/{progress,task_plan,decisions,
bugs-and-risks}.md` + `architecture/api_surface.md`. Entorno: PostgreSQL 16 + pgvector corriendo;
`.venv` con todas las deps; `frontend/` scaffoldeado con node_modules instalados. Tenant de dev:
`DEV_FRONTEND`. El wrap de Sesión 15 YA está commiteado (en `91f0884`); lo ÚNICO sin commitear es
esta entrada de handoff (`memory/session-summaries.md` modificado en el árbol de trabajo).

## 2026-06-14 — Sesión 15
TL;DR: Frontend Next.js 14 — las 5 pantallas. **Fase 3 (UX) COMPLETA.** Riesgo #24 cerrado.
       Gate test_ux.py 25/25 (incl. npm build); regresión 16/16 (333 checks).
Qué construimos:
- Cierre del Riesgo #24: migración `008_matters_description.sql` (+description, +status en
  matters); `ux.py` create/get/list ahora persisten/devuelven description y status. #24 🟢.
- Scaffold `frontend/` con `create-next-app@14` (TypeScript, Tailwind, App Router, no-src-dir,
  alias @/*). Next 14.2.35 + React 18. `next.config.mjs`: eslint.ignoreDuringBuilds (el build
  valida TS; ESLint no lo tumba).
- Token de dev (#23): `frontend/.env.local` (gitignored) con NEXT_PUBLIC_API_URL +
  NEXT_PUBLIC_DEV_TOKEN (JWT del tenant DEV_FRONTEND, acuñado como los gates). Documentado en
  api_surface.md §auth.
- `lib/api.ts` — cliente con Bearer; SSE sobre fetch (streamTurn) porque EventSource no admite
  headers. `app/_components/Sidebar.tsx` (nav activa). `app/layout.tsx` (Inter + sidebar 220px).
- Las 5 pantallas (Tailwind puro, §G, cada fetch con Bearer):
  P1 `app/page.tsx` (lista + modal crear), P2 `app/asuntos/[id]/page.tsx` (3 columnas: docs +
  chat con SSE en vivo + diagnóstico), P3 `app/asuntos/[id]/revisar/page.tsx` (borrador,
  [VERIFICAR] en amarillo, aprobar/editar/rechazar), P4 `app/memoria/page.tsx` (perfil +
  playbooks + sugerencias con aplicar/ignorar), P5 `app/dashboard/page.tsx` (actividad,
  procesos, modelos, costo, conectores — todo con etiquetas amigables).
- `execution/test_ux.py` — +7 checks de frontend (5 pantallas exportan default, layout con
  Sidebar, `npm run build` sin errores). Total 25/25.
Qué decidimos: sin decisión formal nueva. ESLint fuera del build (TS sí se valida). El
diagnóstico (P2) y el punto de "borrador pendiente" (P1) quedan como placeholder (sin endpoint
que los alimente) → Riesgo #25.
Qué sigue: **Fase 4 — Módulo 5 (entrevista SOUL.md + prueba E2E)**, o endurecer la UX (login
real #23, diagnóstico/flags #25). Antes de producción: arrancar backend+frontend juntos (Modo B,
3 terminales) y probar el flujo vivo end-to-end.

Citas legales: ninguna. La UI muestra contenido del backend (sintético en los tests). §G
verificado automáticamente (sin jerga técnica en respuestas ni etiquetas).

## 2026-06-14 — Sesión 14
TL;DR: Fase 3 ARRANCA, dividida en dos (decisión #20). Esta sesión: superficie /api/*
       completa + persistencia de perfil. Gate test_ux.py 18/18; regresión 16/16 (326 checks).
Qué construimos:
- Investigación previa: `frontend/` NO existe (Módulo 0 solo hizo backend); de 15 endpoints del
  gate solo ~3 existían (bajo /matters, no /api); el perfil nunca se persistió (2a in-memory).
  Se presentó y el usuario decidió (decisión #20): Fase 3 en 2 sesiones — S14 backend, S15 frontend.
- `db/migrations/007_profiles.sql` (NUEVO) — tabla `firm_profiles` (perfil estructurado del
  despacho, RLS por-tenant). `memory/profile_manager.py` — ADITIVO: __init__ +pool/+tenant_id;
  con pool=None sigue in-memory (gate 2a 19/19 intacto); +get_firm_profile/upsert_firm_profile.
- `api/routes/ux.py` (NUEVO) — router /api con ~18 endpoints: matters (list/create/get),
  documents (list/upload PDF·Word), chat (devuelve stream_url), stream (alias del SSE de 1d),
  draft (lee el checkpoint; 404 si no hay), draft/approve|reject (delegan en _resume de 1d),
  profile (get/put), playbooks (list/create), proposals (list/apply/ignore — apply cablea
  propuesta→playbook, cierra parte de #21), dashboard/stats. Montado en main.py. §G estricto.
- `ingest/extract.py` (NUEVO) — extrae texto de PDF (PyMuPDF) / Word (python-docx) / txt·md.
- Deps nuevas (pyproject + .venv): python-multipart (FastAPI lo exige para UploadFile), pymupdf,
  python-docx. Documentadas en findings.md.
- `execution/init_profiles.py` (runner 007) + `execution/test_ux.py` (18/18, TestClient + JWT,
  LLM/embeddings mockeados, PDF/Word sintéticos, check §G). `architecture/api_surface.md` (SOP).
Qué decidimos: decisión #20 (Fase 3 en 2 sesiones; /api/* nuevo + /matters legacy intacto;
perfil en firm_profiles; auth = token dev en S15).
Qué sigue: **Sesión 15 — frontend Next.js 14 (scaffold + 5 pantallas)** contra esta API verificada.

Citas legales: ninguna. Los datos del gate (documentos, perfil, playbooks, propuestas) son
sintéticos de prueba. La regla §G se verifica automáticamente (sin jerga técnica en respuestas).

## 2026-06-14 — Sesión 13
TL;DR: Módulo 3e Feedback processor cerrado. Trazas enriquecidas a v2 (decisión #19).
       **HITO: Fase 2 — Knowledge Stores COMPLETA (3a-3e).** 15/15 suites (308 checks).
Qué construimos:
- Investigación previa: las trazas reales (mia.trace.v1) NO registraban la decisión HITL, ni
  el borrador original vs final, ni los documentos citados → las 3 señales del spec no eran
  detectables. Se presentó y el usuario decidió (decisión #19): enriquecer la traza en el
  origen (Opción 1).
- `memory/trace_capture.py` — Trace gana 4 campos OPCIONALES (hitl_outcome, draft_original,
  draft_final, retrieved_doc_ids); schema sube a `mia.trace.v2` solo si traen valor (v1 sin
  ellos sigue válida). `capture()` acepta los kwargs nuevos.
- `agents/graph.py::finalize_node` — escribe los 4 campos: hitl_outcome desde final_status,
  draft_original/final, retrieved_doc_ids DERIVADO de state["documents"] (sin tocar MatterState
  ni el reducer).
- `db/migrations/006_feedback_proposals.sql` (NUEVO) — `feedback_proposals` (proposal_type
  improve_playbook|new_playbook|flag_gap, target_playbook_id, suggested_content, rationale,
  signal_count, trace_ids, status pending|approved|rejected|applied) y
  `processed_traces_watermark` (tenant_id, trace_date, last_processed_at, traces_processed).
  RLS por-tenant en ambas.
- `memory/feedback_processor.py` (NUEVO) — `FeedbackProcessor`: load_traces (v1/v2, ignora
  eventos, excluye días ya procesados por watermark, ventana since_hours), analyze (HITL_REJECTION/
  HITL_EDIT con diff>20% via difflib / NO_RESULT), propose (umbral ≥2; improve/new/flag_gap;
  call_llm task=curator), save_proposals (status pending), mark_traces_processed (watermark),
  run / run_all_tenants.
- `cron/scheduler.py` — +job `feedback_daily` (24h). `memory/__init__.py` exporta FeedbackProcessor.
- `execution/init_feedback.py` (runner 006) y `execution/test_feedback_processor.py` (21/21,
  trazas sintéticas v1+v2 en .tmp, LLM mockeado). `architecture/feedback_processor.md` (SOP).
Qué decidimos: decisión #19 (trazas v2 con señales HITL; processor PROPONE, no aplica;
idempotencia por watermark).
Qué sigue: **Fase 3 — UX (5 pantallas Next.js)**. Antes de Fase 3, ver Riesgo #22 (el scheduler
nunca se arranca: los jobs no se disparan en producción) y #21 (propuestas sin revisar/aplicar).

Citas legales: ninguna. El módulo es infraestructura de aprendizaje; el contenido de trazas y
propuestas del gate es sintético. Las propuestas que generaría en vivo son borradores para que
el ABOGADO revise (no se aplican solas).

## 2026-06-14 — Sesión 12
TL;DR: Módulo 3b Curator cerrado + persistencia de playbooks (decisión #18).
       Gate test_curator 23/23; regresión 14/14 suites (287 checks). Fase 2 COMPLETA.
Qué construimos:
- Investigación previa: el spec asumía una tabla `playbooks` que NO existía (el 2b era
  in-memory). Se presentó y el usuario decidió (decisión #18, Opción 2): crear la tabla Y
  cablear PlaybookManager a DB en la misma sesión, manteniendo su interfaz pública.
- `db/migrations/005_playbooks.sql` (NUEVO) — tabla `playbooks` (title, summary, applies_when,
  content, status active|archived|draft, usage_count, last_used_at, embedding vector(1024),
  metadata; UNIQUE(tenant_id,title); RLS por-tenant; HNSW + BTREE; GRANT mia_app).
- `memory/playbook_manager.py` — ADITIVO: `__init__(pool=None, tenant_id=None)`; con pool=None
  sigue 100% in-memory (gate 2b 14/14 intacto). +métodos async DB: register_playbook (upsert +
  embedding de summary+applies via voyage), get_index, get_playbook, mark_used, list_active.
- `memory/curator.py` (NUEVO) — `Curator`: run/load_playbooks/find_candidates (similitud coseno
  por operador `<=>` de pgvector, umbral 0.85)/consolidate (call_llm task=curator → claude-sonnet,
  archiva originales, idempotente)/prune (last_used_at > 90d, NULL no se poda)/run_all_tenants.
- `agent/llm.py` — +task `"curator": "claude-sonnet"` en _TASK_MODELS (alias que resuelve a
  claude-sonnet-4-6; auxiliary_client.TASK_MODELS es el mismo dict por referencia).
- `cron/scheduler.py` — +job `curator_weekly` (168h, domingos 2am sin timezone en v1).
- `execution/init_playbooks.py` (runner 005) y `execution/test_curator.py` (23/23, LLM+embeddings
  mockeados, embeddings de candidatos controlados con inserts directos para cosenos 0.9/0.84).
- `architecture/curator.md` (antes vacío) — SOP + Self-Annealing.
Qué decidimos: decisión #18 (playbooks persisten en DB; PlaybookManager DB-backed con interfaz
intacta; task curator → claude-sonnet).
Qué sigue: PAUSA — Módulo 3e — Feedback processor (último de Fase 2).

Citas legales: ninguna entregada. El contenido de los playbooks en el gate es filler de prueba.
NOTA jurídica: el Curator consolida/archiva playbooks con LLM SIN revisión humana → Riesgo #19
(un playbook jurídico podría degradarse; originales quedan archived/recuperables).

## 2026-06-14 — Sesión 11
TL;DR: Módulo 3d Pinecone connector cerrado. Gate 14/14; regresión 13/13 suites
       (264 checks). Store externo OPCIONAL y CONDICIONAL (noop sin API key).
Qué construimos:
- `connectors/pinecone_connector.py` (NUEVO) — `PineconeConnectorBase` (ABC: upsert/query/
  delete/describe_index), `PineconeConnector` (real; aislamiento por namespace
  `{prefix}_{tenant_id}`, batch upsert 100, SDK pinecone v3+ con import PEREZOSO),
  `NoopPineconeConnector` (misma interfaz, no-op, is_configured=False) y factory
  `get_pinecone_connector()` (real si hay PINECONE_API_KEY, si no noop).
- `.env`: +PINECONE_INDEX_NAME / PINECONE_NAMESPACE_PREFIX (comentados, defaults mia-legal/
  tenant). PINECONE_API_KEY ya estaba.
- `execution/test_pinecone_connector.py` (NUEVO, 14/14) — sin Pinecone real: noop + índice
  FALSO inyectado en `_index`. Cubre factory con/sin key, noop, interfaz completa, namespace
  por tenant, batch 250→[100,100,50], metadata intacta, top_k, normalización de matches, delete.
- `architecture/pinecone_connector.md` (antes vacío) — SOP + Self-Annealing.
Qué decidimos: sin decisión formal nueva (el módulo aplica decisión #2: pgvector primario,
Pinecone externo opcional). Aclaración de spec registrada en el SOP: el aislamiento es por el
parámetro `namespace` de Pinecone, no por un filtro de metadata (no se contamina la metadata).
Qué sigue: PAUSA — Módulo 3b — Curator cron. Pendiente Fase 2: 3e Feedback processor.

Citas legales: ninguna. El módulo es infraestructura de store vectorial; no genera ni cita
texto jurídico. El gate no toca Pinecone real ni red.

## 2026-06-14 — Sesión 10
TL;DR: Módulo 3c Obsidian indexer CERRADO. Gate test_obsidian_sync 22/22;
       regresión 12/12 suites (250 checks). 3 premisas del spec corregidas.
Qué construimos:
- Investigación previa: el spec asumía 3 cosas que no existían → se presentaron y el
  usuario decidió (decisión #17): (C1) los chunks de Obsidian van a una tabla NUEVA
  `knowledge_chunks`, NO a `documents` (documents.matter_id es NOT NULL; las notas son
  del despacho, no de un asunto); (C2) embeddings por `embeddings.embed_texts` (librería,
  no `call_llm(task="embedding")` que no existe); (C3) `cron/scheduler.py` no existía →
  se creó un scheduler propio mínimo (sin APScheduler).
- `db/migrations/004_knowledge_stores.sql` (NUEVO) — `knowledge_chunks` (source/source_path/
  chunk_index/heading_path/content/embedding(1024)/content_tsv GENERATED/metadata, UNIQUE
  por (tenant,source,source_path,chunk_index), RLS por-tenant + HNSW + GIN) y
  `obsidian_file_hashes` (sha256 por archivo, RLS). NO toca documents/chunks.
- `connectors/obsidian_sync.py` (NUEVO) — `ObsidianSync`: scan (excluye .carpetas y _archivos),
  hash sha256 incremental, chunking por encabezados H1/H2/H3 con máx 512 tok (split por
  párrafos), embed en batches de 128, upsert/borrado en knowledge_chunks y hashes, todo por
  `tenant_connection` (RLS).
- `cron/scheduler.py` (NUEVO) — registro de jobs en memoria (register/list/run/start); job
  `sync_obsidian_all_tenants` cada 6h (enumera tenants con vault configurado y sincroniza).
- `execution/init_knowledge_stores.py` (runner migración 004) y
  `execution/test_obsidian_sync.py` (gate, 22 checks, vault temporal en .tmp/, embeddings
  mockeados). `architecture/obsidian_sync.md` (SOP, antes vacío).
Qué decidimos: decisión #17 (knowledge_chunks tabla separada + correcciones C1/C2/C3).
Qué sigue: PAUSA — Módulo 3d — Pinecone connector. Pendientes Fase 2: 3b Curator, 3e Feedback.

Citas legales: ninguna. El módulo no genera ni cita texto jurídico; el vault de prueba del
gate es contenido filler temporal en .tmp/ (no es el vault real ni datos entregables).

## 2026-06-14 — Sesión 9
TL;DR: Módulo 3a SAT-Graph CERRADO. Corpus semilla cargado en DB.
       Gate test_sat_graph.py 21/21; regresión 11/11 suites (228 checks).
Qué construimos:
- Migración corrida: `init_sat_graph.py` aplicó 003_sat_graph.sql (3 tablas
  legal_norms/norm_relations/jurisprudence, RLS abierto, GRANT a mia_app).
- Corpus semilla cargado: `ingest_corpus.py` (+runner `__main__`, se corre con
  `python -m mia.rag.ingest_corpus`) → 5 normas, 3 providencias, 2 relaciones
  (todas [VERIFICAR]; datos de desarrollo, no citas entregadas).
- `execution/test_sat_graph.py` (NUEVO) — gate async contra DB real, 21 checks:
  tablas, RLS (mia_app SELECT · 2 tenants ven el mismo corpus), curaduría +
  upsert idempotente, vigencia temporal antes/durante/expirada, relaciones +
  filtro, cadena recursiva simple/hoja/ciclo, FTS español con acento, semilla.
- `architecture/sat_graph.md` (NUEVO) — SOP del módulo + Self-Annealing.
Qué decidimos:
- Decisión #16 (ya registrada en Sesión 8 previa al crash): SAT-Graph = corpus
  COMPARTIDO (sin tenant_id), RLS abierto USING(true) WITH CHECK(true), escritura
  por GRANT a mia_app, acceso vía pool.connection() (sin GUC).
- Sin decisiones nuevas esta sesión; se completó la implementación de 3a.
Qué sigue: PAUSA — no arrancar otro módulo sin el usuario. Candidato (orden del
usuario): Módulo 3c — Obsidian indexer. Pendientes Fase 2: 3b Curator, 3d Pinecone,
3e Feedback. Nuevos riesgos #13 (corpus escribible sin rol curador separado, 🔐) y
#14 (corpus semilla [VERIFICAR] sin contrastar).

Citas legales: ninguna entregada al cliente. El corpus semilla (normas y
providencias en ingest_corpus.py) es ILUSTRATIVO/de desarrollo, marcado [VERIFICAR]
en metadata; debe contrastarse contra SUIN-Juriscol / la corte respectiva antes de
cualquier uso real.

## 2026-06-14 — Sesión 8
TL;DR: Cerrada deuda del grafo (#11 reframe, #12 fix quirúrgico).
       Conteo de checks corregido a 207.
Qué construimos:
- Riesgo #11 cerrado por reframe: el ContextCompressor NO se cablea
  al grafo LangGraph hoy (nodos autocontenidos, historial no consumido).
  Decisión #14 registrada.
- Riesgo #12 cerrado con fix mínimo: role="system" → role="user"
  en el mensaje de resumen del ContextCompressor. SUMMARY_PREFIX
  actualizado a "[RESUMEN DE CONTEXTO ANTERIOR]". Decisión #15 registrada.
Qué decidimos:
- Cablear el compresor al grafo queda para cuando el grafo adopte
  historial creciente (Fase 3 o decisión de producto posterior).
- No insertar ack de assistant tras el resumen — SUMMARY_END_MARKER
  es suficiente para desambiguación semántica.
- Conteo canónico de checks: 207 (no 235 — error de tally corregido).
Qué sigue: Fase 2 — Knowledge Stores · Módulo 3a SAT-Graph.

## 2026-06-14 — Sesión 7
**TL;DR:** Módulo 2c (ContextCompressor) COMPLETO → **Fase 1 (Memoria, 2a-2d) cerrada**.
Gate `test_context_compressor.py` 22/22; regresión 10/10 suites (235 checks). PAUSA.

**Qué construimos:**
- Se leyó COMPLETO el `context_compressor.py` de Hermes (2079 líneas). Params no
  contradicen (Hermes parametriza 0.50/3/20; Mia fija 0.55/5/30). Se flaggearon 2
  mejoras → aprobadas (decisión #13).
- `agent/context_compressor.py` (NUEVO) — compress() con threshold 55%, protect 5/30,
  resumen del medio en haiku (BLOQUEO), `[RESUMEN DE CONTEXTO]` como msg system,
  `[VERIFICAR]` preservado verbatim, resumen estructurado en español jurídico,
  (A) iterativo + (B) anti-thrashing.
- `memory/trace_capture.py` +capture_event (evento context_compressed, schema event).
- `agent/core.py` run_turn comprime antes del turno (transparente). `config.py`
  +MIA_CONTEXT_WINDOW. `architecture/context_compressor.md`. Gate 22/22.

**Qué decidimos (decisión #13):** ContextCompressor adopta resumen iterativo (A) y
anti-thrashing (B) de Hermes. Params locked intactos (55%/5/30, compression→haiku).

**Qué sigue:** PAUSA — Fase 0 + Módulo 1 + Fase 1 completos. No arrancar otro módulo sin
el usuario. Candidatos: Fase 2 (3a-3e), Fase 3 (UX), Módulo 5 (SOUL.md). Nuevos Riesgos
#11 (compresor solo en run_turn, no en el grafo) y #12 (resumen role=system mid-array sin
verificar contra Anthropic). #5 ampliado (el umbral de compresión depende del estimador).

**Citas legales:** ninguna entregada al cliente. El texto jurídico en fixtures/prompts
es ilustrativo, sin `[VERIFICAR]` pendientes de fuente real.

## 2026-06-13 — Sesión 6
**TL;DR:** Módulo 1e (Agent Hub) COMPLETO → **Módulo 1 cerrado (1a-1e)**. Gate
`test_agent_hub.py` 38/38; regresión 9/9 suites verdes. PAUSA.

**Qué construimos:**
- Premisa del spec corregida: NO existía tabla `profiles` → decisión #12 (tabla nueva
  `tenant_settings` jsonb, RLS, migración por postgres). 3/5 CLIs instalados
  (hermes/claude/codex) → degradación real.
- `gateway/agent_hub.py` (AgentHub, 5 conectores, detección PATH/env, subprocess
  args-en-lista shell=False, graceful degradation), `gateway/hub_config.py` (config
  por tenant en tenant_settings, RLS), `api/routes/settings.py` (GET + enable/disable,
  §G sin marcas), seam de delegación OFF-por-defecto en `graph.py`,
  `architecture/agent_hub.md`, `execution/test_agent_hub.py` (38/38).
- `schema.sql` +tenant_settings; aplicado re-corriendo init_db.py (9 tablas, 5 policies).

**Qué decidimos:**
- #12 tenant_settings como config store por tenant (no profiles). Defaults: D2
  subprocess args-en-lista (no comillas manuales), D3 flags de CLI [VERIFICAR],
  D4 delegación OFF por defecto.

**Qué sigue:** PAUSA — Módulo 1 completo. No arrancar otro módulo sin el usuario.
Candidatos: 2c (ContextCompressor), Fase 2 (3a-3e), Fase 3 (UX). Nuevos Riesgos #9
(flags [VERIFICAR] + invocación en vivo) y #10 (subprocesos del hub NO acotados por
RLS — relevante para multi-tenant en producción).

**Citas legales:** ninguna entregada al cliente. Único [VERIFICAR] abierto: los flags
de invocación de cada CLI del Agent Hub (no jurídico).

## 2026-06-13 — Sesión 5
**TL;DR:** Módulo 1d (LangGraph StateGraph + SSE + HITL) COMPLETO — el módulo más
delicado. Gate `test_hitl_flow.py` 19/19 contra DB + checkpointer Postgres reales
(LLM/embeddings mockeados). Regresión 8/8 suites verdes (test_rls intacto). PAUSA
antes de 1e.

**Qué construimos:**
- Investigación previa → 4 decisiones presentadas y aprobadas (decisions.md #9-#11).
  Hallazgos: el schema ya soportaba RRF (content_tsv+GIN+HNSW); mia_app sin CREATE;
  Hermes NO usa LangGraph (no había patrón de grafo en los refs).
- `agents/`: `state.py` (MatterState), `retrieval.py` (RRF híbrido), `graph.py`
  (5 nodos async; interrupt() 1ª línea de hitl_checkpoint), `checkpointer.py`
  (AsyncPostgresSaver).
- `execution/init_checkpointer.py` (migración: tablas de checkpoint por postgres +
  GRANT DML a mia_app).
- `api/routes/{_common,stream,hitl}.py` (SSE + approve/reject/edit; cruzado→401;
  eventos en español §G) + `api/main.py` monta los routers.
- `architecture/hitl_flow.md`, `pyproject.toml` (+langgraph 1.2.5,
  langgraph-checkpoint-postgres 3.1.0, sse-starlette 3.4.4).

**Qué decidimos (decisions.md #9-#11):**
- #9 Checkpoint: tablas LangGraph creadas por postgres + GRANT a mia_app; aislamiento
  por thread_id+JWT; RLS de dominio sigue activo. (Subclase RLS-aware descartada.)
- #10 interrupt() = 1ª línea de hitl_checkpoint_node.
- #11 approve/reject/edit reanuda y emite finalizing→done en la misma SSE.

**Qué sigue:** PAUSA — el usuario pidió NO arrancar 1e (Agent Hub) sin él presente.
Pendientes vivos: 2c (ContextCompressor, saltado), Riesgo #4 (LiteLLM librería vs
proxy), y los nuevos Riesgos #7 (invariante de aislamiento del checkpoint) y #8
(pooling del checkpointer).

**Citas legales:** ninguna entregada al cliente. El texto jurídico en fixtures y
prompts (p. ej. "caducidad de la reparación directa, 2 años") es ILUSTRATIVO, no una
cita verificada.

## 2026-06-12 — Sesión 4
**TL;DR:** Lote autónomo 1b→2d cerrado tras "procede" del usuario. 5 módulos con gate
verde (1b 32 · 1c 16 · 2a 19 · 2b 14 · 2d 20) + regresión completa offline 6/6 suites
(116 checks). PAUSA antes de 1d/1e.

**Qué construimos:**
- 1b: `prompt_builder` refactor a tabla única `LAYERS` (10 capas; L1-6 cached TTL 1h),
  `auxiliary_client.py` (`AuxiliaryClient.complete`→texto; `TASK_MODELS` completo),
  `test_prompt_builder.py` 32/32; corregida la aserción stale de 1a (15/15).
- 1c: `plugins.py` (`PluginManager` + 6 hooks en orden de ciclo de vida, intercepción
  real) cableado en `core.py` (run_turn pre/post_llm_call + start/end_session),
  `test_plugins.py` 16/16.
- Paquete nuevo `backend/mia/memory/` (memoria en EJECUCIÓN, ≠ `/memory/` de
  construcción): `tokens.py` (estimador compartido); 2a `profile_manager.py` (perfiles
  600/900 tok, frozen al inicio del asunto) 19/19; 2b `playbook_manager.py` (índice 3k
  siempre presente + contenido on-demand) 14/14; 2d `trace_capture.py` (JSONL por
  tenant, `to_sft_example`, 8 campos) 20/20.

**Qué decidimos:**
- 2c (ContextCompressor) se salta por orden del usuario (el plan iba 2a→2b→2d).
- Estimador de tokens = heurística offline ~4 chars/token (tiktoken baja vocab por red
  → no offline; el conteo exacto lo da el gateway). → Riesgo #5.
- Memoria en ejecución en `backend/mia/memory/` (≠ `/memory/` raíz). → Riesgo #6.
- streaming/fallbacks de `call_llm` y wiring de tracing al turno → diferidos a 1d
  (no estaban en estos gates).

**Qué sigue:** PAUSA. A la vuelta de Pipe: 1d (LangGraph StateGraph + SSE + HITL) y
1e (Agent Hub). Pendiente reconciliar Riesgo #4 (LiteLLM librería vs. proxy).

**Citas legales:** ninguna entregada al cliente esta sesión. El texto jurídico en los
fixtures de test y en las capas de prompt (p. ej. "caducidad 2 años") es ILUSTRATIVO,
no una cita verificada y no se afirma como fuente (regla global de verificación).

## 2026-06-12 — Sesión 3
**TL;DR:** Módulo 0 cerrado al 100% (ingest real verificado: chunks=3, con_embedding=3,
dim=1024). Módulo 1a completo (MiaAgent + router call_llm, gate 15/15). Módulo 1b en
progreso (prompt_builder de 10 capas + cableado con caché de sesión; falta el gate).

**Qué construimos:**
- Cierre del Paso 6 del Módulo 0: vault de prueba + tenant/matter + ingest end-to-end.
- 1a: `agent/{llm,core,__init__}.py`, config (LITELLM_BASE_URL/API_KEY, MIA_MODEL),
  +openai, `test_agent_core.py` 15/15, doc `architecture/prompt_builder.md`.
- 1b (parcial): `agent/prompt_builder.py` (10 capas, 3 tiers) + `core.py` cableado
  (caché de sesión `_cached_system_prompt`, `invalidate_prompt`, 5 campos-costura).

**Qué decidimos:**
- Router LLM delgado sobre LiteLLM (LiteLLM hace lo que los ~5.800 líneas de Hermes;
  alias en `litellm_config.yaml` como fuente única).
- `compression=claude-haiku` implementado como BLOQUEO por código (`_LOCKED_TASKS`),
  no como default (decisión #7).
- Las 10 capas: L1-6 stable (prefijo cacheado), L7-8 context, L9-10 volatile;
  L4/L6/L7/L9 son costuras no-op hasta los módulos que las llenan.

**Qué sigue:** cerrar el gate de 1b (`test_prompt_builder.py`) + corregir la aserción
stale de `test_agent_core.py` (el prompt creció de identidad a 10 capas). Después seguir
el plan 1c→2a→2b→2d con PAUSA antes de 1d/1e. NOTA: el `/effort high` del usuario falló
al parsear y se llevó ese plan como argumento — pendiente de reenvío.

## 2026-06-12 — Sesión 2
**TL;DR:** Módulo 0 completo — PostgreSQL 16 + pgvector 0.8.2 + RLS multi-tenant
(gate `test_rls.py` 12/12) + API FastAPI (`/health`, middleware JWT) + scaffolding
del backend. Solo falta correr el ingest real (gated por `VOYAGE_API_KEY`).

**Qué construimos:**
- Reset de la contraseña de `postgres` (Opción 3, pg_hba trust, script elevado).
- pgvector 0.8.2 instalado en Windows nativo (binario de terceros verificado
  por SHA256) + load-test OK.
- Backend `mia/`: schema+RLS, `init_db`, pool con contexto de tenant, middleware
  JWT, `/health`, `/matters` tenant-scoped, ingest (voyage-law-2), `test_rls`,
  scripts de arranque Modo B, `pyproject` + deps en `.venv`.

**Qué decidimos:**
- Embeddings `voyage-law-2` / `vector(1024)` vía LiteLLM (decisión #8).
- App se conecta como `mia_app` (NOSUPERUSER/NOBYPASSRLS); `postgres` solo
  migraciones. RLS fail-closed por GUC `app.tenant_id`.
- pgvector de terceros es válido SOLO para desarrollo (Riesgo #3 abierto).

**Qué sigue:** llenar `VOYAGE_API_KEY` y correr el ingest real (cierra Paso 6);
luego Módulo 1 (core del agente, 1a–1e).

---

## 2026-06-21 — Replan Ruta B + Fase 0 (cimientos multi-jurisdicción)
TL;DR: replan a "Plataforma Legal Hispana + Asistente Conversacional" (ver `Plan/Plan.md`).
Construida casi toda la Fase 0; validado el modelo. Continuación detallada en
`Plan/Plan.md` → "ESTADO DE EJECUCIÓN".

**Qué construimos:**
- 0.B: revalidé el entorno — los tests son SCRIPTS (no pytest); línea base REAL 23/25 (no 17/17).
- 0.C: migración 011 (versionado temporal + `audit_logs` + `matters.pending_review`), partición
  del corpus por jurisdicción en `sat_graph.py`, abstracción de Pack en `backend/mia/jurisdiction/`,
  y onboarding backend (`GET /api/jurisdictions` + persistencia + `resolve_jurisdictions`).
  +4 gates nuevos verdes (`test_jurisdiction_pack` 19, `test_sat_graph_jurisdiction` 11,
  `test_onboarding_jurisdictions` 5; `test_sat_graph` sigue 21). Cero regresiones.
- 0.A: validación sonnet vs qwen (créditos restaurados).

**Qué decidimos:**
- #24 packs de jurisdicción instalables (refina #22); #25 corpus particionado + versionado temporal
  (modifica #16); #26 ruteo de modelo por tier (nube=sonnet para citas; mia-local=tier soberano)
  — qwen FABRICA citas legales y es 6-19× más lento.

**Qué sigue (resto Fase 0, en orden):** 0.4 política de modelo por tenant (ContextVar en
`resolve_model`; cierra `test_curator`), 0.5 PII en capa común de `call_llm`, 0.6 test HALT de
privilegio, frontend onboarding (cierra `test_onboarding_horizontal`). Luego Fase 1 (núcleo
conversacional). 0.A ya NO está bloqueado (hay créditos). Proxy LiteLLM (4000) suele estar caído.

## 2026-06-30 — Smoke test vivo (ruta Codex)
TL;DR: el flujo completo funciona en vivo; 3 bugs de plataforma invisibles a los gates quedaron
       reparados.
Qué construimos/reparamos:
- SelectorEventLoop para Windows (`api/run.py`) — el ProactorEventLoop rompía la conexión a la BD
  con uvicorn≥0.36.
- HITL fail-closed (`graph.py::confirm_node`) — decisión ausente/inválida ya no aprueba por defecto.
- Validación de ciclo de vida de turno (`stream.py`/`hitl.py` + `_common`) — 409 si hay interrupt
  pendiente o si se resume sin borrador; WikiManager awaited con log; SSE emite evento `error`
  explícito en vez de colgar.
Qué decidimos:
- claude-sonnet es el backend de calidad confirmado para producción (HTTP 200 por el proxy, sin
  bloqueo de créditos).
- LiteLLM necesita su propio venv antes de cualquier reinicio en producción (Riesgo #32).
Qué sigue: sembrar playbooks reales para observar activación (cierra #20/#31); cablear el
  `prompt_builder` (10 capas) al grafo; corregir la ruta en `CLAUDE.md`; investigar y registrar el
  trabajo no documentado (`gepa.py`, `dreams.py`, `second_brain_ui`) + auth real (Riesgo #23).

## 2026-06-30 — Hermes v0.17.0 (H.5/H.6) + correcciones Cursor (C.5/C.6) + merge a `main`
TL;DR: se cerró la rama `feat/hermes-v017-impl` (fallback de proveedor + playbooks protegidos +
       Curator legacy sellado + traces scope), 32/32 gates verdes, y se mergeó a `main`.
Qué construimos:
- **C.5** — `Curator.run()`→`_run_legacy()` (y `run_all_tenants()`→`_run_all_tenants_legacy()`)
  bloqueado por guard `MIA_ALLOW_CURATOR_LEGACY_RUN=1` (solo tests): en producción es imposible
  mutar playbooks sin el flujo HITL `propose→approve→apply`. Cierra del todo el Riesgo #19.
- **C.6** — `GET /api/traces/search` exige `matter_id` (Query obligatorio) + `assert_owns_matter`
  (401 si el asunto no es del tenant; 422 si falta el param). Evita buscar a ciegas sobre todo el
  despacho.
- **H.5** — `call_llm` recorre una CADENA de proveedores por task (`main`/`curator`:
  claude-sonnet→mia-local); reintento con backoff dentro del alias y salto al siguiente cuando el
  error lo amerita (`should_fallback`). `CONTEXT_TOO_LONG` no avanza la cadena; `AUTH`/`UNKNOWN`
  fallan rápido; cadena agotada → `ALL_PROVIDERS_EXHAUSTED`. Nuevo `TurnLLMState` + wiring de
  compresión-una-vez-por-turno en `graph.py`. Gate nuevo `test_llm_fallback` 25/25.
- **H.6** — columna `playbooks.protected` (migración 014) que inmuniza los playbooks semilla/core
  frente a Curator/GEPA/SkillImprover/UX (consolidación, poda, mejora automática y sobrescritura
  quedan bloqueadas; `apply_proposal` sobre un protegido → 409). Gate nuevo `test_playbooks_protected`
  19/19.
Qué decidimos:
- El fallback NO salta ante `AUTH` (por diseño: no gastar en un proveedor que fallará igual). En dev
  sin créditos, `main` intenta claude-sonnet primero; para forzar local, `model="mia-local"`.
- La recuperación de `CONTEXT_TOO_LONG` en el grafo quedó cableada pero es un no-op sobre prompts de
  2 mensajes → se registró como **Riesgo #33** (trabajo de la próxima sesión), no se parchó a la
  fuerza para no salir del alcance del checkpoint.
- `*.egg-info/` va a `.gitignore` (artefacto de `pip install -e`).
Qué sigue: Riesgo #33 (recuperación por nodo ante contexto largo en `graph.py`); sembrar playbooks
  reales (cierra #20/#31); separar LiteLLM en su venv (Riesgo #32); cablear `prompt_builder` al grafo.

## 2026-07-01 — Sesión 21
TL;DR: plan maestro de 3 pilares ejecutado — 10 checkpoints, 40/40 suites, todo en GitHub.
Qué construimos:
- CP0: LiteLLM en venv propio + pins + gate check_env_pins (Riesgo #32 cerrado).
- CP2: motor por suscripción (CLI claude) + 3 políticas por tenant; turno vivo 176s/19k chars sin billing API.
- CP1: shrink por nodo ante CONTEXT_TOO_LONG (Riesgo #33 cerrado).
- CP4: import de guías del despacho (POST /playbooks/import, .md/.txt/.docx).
- CP5: diagnóstico visible en pantalla + punto naranja de borrador pendiente.
- CP-B1: modo asistente — conversación libre con memoria (migración 015).
- CP-B2: puente Telegram opt-in single-chat (guía docs/telegram-setup.md).
- CP-C1: conector de carpetas disco/OneDrive/Google Drive (migración 016, allowlist 2 capas).
- CP-C2: vault de Obsidian bidireccional (Mia escribe bajo Mia/) + instalación guiada.
- CP3: el conocimiento del despacho entra al análisis (Riesgo #16 cerrado) — APROBADO por Pipe con A/B en vivo.
Regresión final 40/40 suites; capa 2 (revisor independiente) en TODOS los checkpoints con hallazgos corregidos antes de cada commit.
Qué decidimos:
- Decisiones #27-#32 (motor por suscripción · modo asistente · Telegram · carpetas · knowledge al análisis · vault bidireccional).
- "Una sola Mia": el asistente NO es un segundo agente — misma alma, memoria y política de modelo.
- Telegram primero como canal móvil (antes que app/WhatsApp); prioridad = uso diario en Lexia.
Qué sigue:
- CP7: sincronización frontend — selector de motor + UI de conectores/curator/skills.
- CP-B3: proactividad/recordatorios por Telegram. CP-C3: cierre del circuito GEPA. CP-C4: asistente de configuración guiado.
- CP6: prompt_builder→grafo (ALTO IMPACTO — requiere diff a Pipe antes de ejecutar).
- CP8: endurecimiento pre-cliente — EN PAUSA.
- Pendientes de Pipe: crear su bot de Telegram con docs/telegram-setup.md; subir sus primeras guías con /playbooks/import; decidir privacidad de conversaciones del asistente (hoy: nivel despacho) y visibilidad del diagnóstico tras aprobar.

## 2026-07-02 â€” SesiÃ³n 24 (cierre)
TL;DR: se cerraron CP6, CP9 y CP-C4b (con su UI de Cursor y una correcciÃ³n); y se trazÃ³ el
roadmap de 5 olas a partir del anÃ¡lisis de Hermes/ClaudeOS.
QuÃ© construimos:
- CP6 (una sola voz) aprobado por Pipe y mergeado a main.
- CP9 (equipo de especialistas: hechosâ†’investigaciÃ³nâ†’cruceâ†’redacciÃ³nâ†’verificaciÃ³n de citasâ†’Word)
  aprobado con A/B en vivo (docs/comparacion-cp9.md), capa 2 con M1/M2 corregidos, mergeado.
- CP-C4b (wizard "Configura a Mia" explicativo): guÃ­as por paso + mapa de secciones; capa 2 con
  L1/U1-U8 corregidos (guÃ­as reescritas a la realidad del producto), mergeado.
- Cursor construyÃ³ la UI pendiente (botÃ³n Word + informe de verificaciÃ³n, secciÃ³n Carpetas,
  botÃ³n Instalar Obsidian; arreglÃ³ lib/api.ts para mostrar los mensajes del backend). Claude Code
  verificÃ³ la entrega y corrigiÃ³ un defecto de exactitud del resumen del verificador
  (marcadas+anotadas, commit 5fca19e).
- AnÃ¡lisis a fondo de los 3 repos de referencia (3 subagentes) â†’ docs/analisis-referencias-2026-07.md
  y docs/plan-ejecucion-olas.md (roadmap de 16 checkpoints en 5 olas).
QuÃ© decidimos:
- Pipe aprobÃ³ ejecutar LAS 5 OLAS completas, orden: confidencialidad â†’ plazos â†’ valor visible â†’
  voz â†’ escala. Empezar por CP-S1.
QuÃ© sigue (TERMINAL NUEVA, contexto en 0):
- Leer docs/plan-ejecucion-olas.md y arrancar CP-S1 (cuarentena universal de contenido no confiable).
- DecisiÃ³n pendiente de Pipe antes de Ola 3 (voz): local vs nube.
- Pendientes de Pipe sin cambio: bot de Telegram, subir guÃ­as reales, corpus jurÃ­dico real,
  privacidad de conversaciones del asistente, deuda Â§G del dashboard (Pinecone/second brain).


## 2026-07-02 — Sesión 26
TL;DR: auditoría de seguridad incorporada a main (c3bdcc2) y CP-V1 "valor entregado (ROI)"
completo y mergeado (74cb2bb) — la Ola 4 quedó abierta con su primer checkpoint en verde.
Qué construimos:
- AUDITORÍA DE SEGURIDAD (pendiente de sesión 25): verificada en 3 capas (regresión 49/49 ×2,
  build ×2, revisor adversarial con 4 hallazgos corregidos: tope por IP + bcrypt a threadpool,
  poda de memoria del throttle, ApiError en frontend, docs exactos; prueba visual del freno
  anti fuerza-bruta y del error de red en llano). Aprobada por Pipe, commit c3bdcc2 en main.
- CP-V1 (Ola 4): tabla turn_usage (migración 021, RLS) con el uso REAL del LLM por llamada;
  metrics/usage (scope ContextVar api/cron, buffer acotado, precios por alias, flusher en el
  lifespan); hook en call_llm (cubre API, CLI de suscripción y local); metrics/value con la
  fórmula de horas (eventos y rechazos excluidos; borrador = escrito ≥3000 chars); endpoints
  /api/value/settings (tarifa por despacho, upsert JSONB); tarjeta "Valor entregado este mes"
  en el panel con edición de tarifa. Gate test_value_delivered.py 27/27; regresión 50/50.
- Capa 2 de CP-V1 RECHAZÓ la fórmula v1 (A1: sobre-reportaba — toda pregunta aprobada contaba
  120 min) → corregida con summarize_traces + 5 hallazgos más cerrados → re-verificado APROBAR.
  Límites declarados en Riesgo #43 (embeddings fuera del costo; heurística de borrador).
Qué decidimos:
- Defaults del ROI declarados y configurables: 100 USD/h · borrador 120 min · consulta 15 min.
- Conectores de correo/calendario siguen APLAZADOS (instrucción de Pipe, sesión 25).
Qué sigue (TERMINAL NUEVA):
- CP-V2 (Ola 4): auto-diagnóstico prescriptivo (gravedad×impacto×certeza, IDs estables,
  guardas anti-invención) — evoluciona Dreams. Detalle en docs/plan-ejecucion-olas.md.
- Frontend pendiente con Cursor (HANDOFF): pantallas de CP-P2 (automatizaciones) y CP-P3.
- Deuda menor detectada por revisor: página de memoria usa .includes("409") roto (preexistente).

## 2026-07-02 — Sesión 27
TL;DR: CP-V2 (auto-diagnóstico prescriptivo) completo, mergeado y pusheado — la Ola 4 quedó CERRADA.
Qué construimos:
- Motor determinista de recomendaciones (memory/prescriptions.py): 6 buckets con guarda
  anti-invención (<5 eventos = silencio), score gravedad×dólares×certeza, top 4 con diversidad,
  IDs estables, memoria de decisiones (tabla dream_prescriptions, migración 022, RLS FORCE).
- Integración a Dreams (sección diagnostics fail-soft + línea en el reporte semanal) y
  endpoints del panel: listar recomendaciones vigentes + decidir (aceptar/descartar).
- Capa 2 APROBÓ tras re-verificar: H1+R1 (el upsert jamás pisa una decisión del abogado),
  H2 (la poda conserva la edad de señales vivas), H3/H4 (bucket de costo rediseñado a gasto
  real + Motor de IA del Panel), H5-H7+R2. Gate test_dreams 43/43; regresión 50/50 ×3.
Qué decidimos:
- Pipe aprobó merge+push (383197b en origin/main).
- VOZ (CP-Z1): Pipe confirmó que validó Lexter con el modelo POR DEFECTO → Parakeet v3 fijado
  para v1; Whisper queda como opción futura.
- Regla de sesión: al ~65% del contexto, preparar traspaso a terminal nueva.
Qué sigue (TERMINAL NUEVA, contexto en 0):
- OLA 3 · CP-Z1: dictado local nativo (micrófono web → FastAPI → backend/mia/speech/ con
  Silero VAD + Parakeet v3 vía onnxruntime-directml, parámetros de Lexter). Leer
  docs/analisis-lexter.md y docs/plan-ejecucion-olas.md antes de tocar código.
- Frontend pendiente con Cursor (HANDOFF): tarjetas de diagnóstico CP-V2 + pantallas CP-P2/P3.

## 2026-07-02 — Sesión 28
TL;DR: TRASPASO-MODELO.md creado y verificado — cualquier modelo (Opus u otro) puede continuar
el proyecto con la misma visión, ruta y estándar de calidad; pedido explícito de Pipe.
Qué construimos:
- mia/TRASPASO-MODELO.md: orden de lectura al retomar, visión no negociable, protocolo de
  calidad por checkpoint (3 capas, test_rls HALT, A/B de alto impacto descrito completo sin
  depender del script efímero ab_run.py), cómo trabajar con Pipe, ruta por delante y trampas
  del entorno. CLAUDE.md y la memoria persistente apuntan a él.
- Consistencia de la decisión de voz: Parakeet v3 (resuelta en sesión 27) propagada a
  docs/analisis-lexter.md y docs/plan-ejecucion-olas.md (decían "confirmar con Pipe").
- Verificación: regresión completa en main ALL PASS 50/50 (una corrida previa falló por
  artefacto de DOS terminales concurrentes sobre el repo — advertencia añadida al traspaso);
  capa 2 (revisor adversarial simulando "Opus en terminal nueva"): SUFICIENTE CON
  CORRECCIONES — 3 mayores + 4 menores, TODOS corregidos antes del commit.
Qué decidimos:
- Pipe aprobó commit+merge+push de CP-V2 en este diálogo (la sesión 27 lo ejecutó en paralelo).
Qué sigue (TERMINAL NUEVA, contexto en 0):
- OLA 3 · CP-Z1 (dictado local con Parakeet v3). Leer TRASPASO-MODELO.md al arrancar.

## 2026-07-06 — Sesión 34
TL;DR: CP-E6 cierra la Ola 5; rediseño del onboarding (SOUL sin placeholders + resumen
llano); y se dejó Mia usable para Pipe (puerto 3100, lanzador, cuenta). Todo en origin/main.
Qué construimos:
- CP-E6 (más canales por relay + conectar sistemas vía MCP con seguridad): paquete
  backend/mia/mcp/ (security/catalog/service, fail-closed, entorno saneado, secretos vía
  ${VAR} bajo scope del tenant, salida sellada CP-S1, forget para borrar credenciales),
  rutas /api/mcp/*, y channels/relay.py (RelayClient reusable; telegram_bridge lo reusa).
  3 capas: gate test_mcp 38/38, regresión 60 suites, revisor APROBÓ tras corregir 1
  bloqueante (${VAR} en command/args no se interpolaba/detectaba). Merge 09330b2, pushed.
- Rediseño del onboarding (pedido de Pipe tras probarlo): soul_interview.py reescrito a
  generación DETERMINISTA que omite lo vacío y JAMÁS imprime corchetes (antes rellenaba
  template fijo de 9 secciones y conservaba placeholders); se quitaron objetivo/pilares
  (13 preguntas, sin sección mission); build_summary = resumen en lenguaje llano visible,
  SOUL técnico por debajo. Obsidian fuera del recorrido. 3 capas: e2e+setup_wizard verdes,
  regresión 60 suites, revisor APROBÓ tras corregir 1 bloqueante (validate_soul marcaba un
  corchete legítimo del abogado como defecto). Merge de6c797. Frontend de Cursor (resumen,
  7 días, herramientas con descripción, de-jerga Conocimiento) verificado y pushed (1487ba6).
- Operación: Mia movida al puerto 3100 (el 3000 lo usa otro proyecto de Pipe,
  lexia-intelligence-hub); lanzador de un clic "Abrir Mia.cmd" en OneDrive\Escritorio +
  scripts/start_all.ps1 (enciende litellm/API/frontend y abre el navegador); cuenta de Pipe
  creada (jfelipetorresv@lexia.co / tenant bc740c10 / "Lexia Abogados"), perfil regenerado limpio.
Qué decidimos (Pipe):
- SOUL: resumen llano visible, archivo técnico por debajo. Quitar objetivo/pilares. Obsidian pospuesto.
- Aprobó merge+push a main de CP-E6 y del rediseño del onboarding en el diálogo.
Qué sigue (TERMINAL NUEVA, contexto en 0):
- OLA 5 CERRADA (CP-E1..E6). Roadmap de 5 olas COMPLETO. Próximo trabajo NO es un checkpoint
  del roadmap; opciones abiertas (decidir con Pipe): (a) capa 3 EN VIVO que solo Pipe puede
  hacer — recorrer el onboarding de punta a punta en 3100 y confirmar; (b) más "wizard de
  Hermes" en el onboarding (opciones-con-descripción para preguntas de texto libre, defaults,
  follow-ups condicionales) — se hizo solo parte; (c) producto: subir corpus jurídico real y
  guías del despacho (activa citas "respaldadas"), crear bot de Telegram, activar conectores/MCP
  reales cuando Pipe dé las llaves. Frontend de la pantalla "Sistemas conectados" (CP-E6) DIFERIDO
  por decisión de Pipe hasta activar un sistema real.
- Al arrancar: leer CLAUDE.md, TRASPASO-MODELO.md, esta entrada, HANDOFF.md, la memoria
  persistente del repo. OJO: Mia corre en 3100; Cursor trabaja en paralelo sobre main (verificar
  git antes de commitear).

## 2026-07-09 — Sesión 36
TL;DR: Fuentes remotas del expediente completas — el abogado ya puede traer correos (Gmail/Microsoft)
y carpetas de OneDrive al asunto, con OAuth multi-proveedor de base.
Qué construimos:
- Fase 1: cimientos OAuth multi-proveedor (`tenant_oauth_tokens` con un despacho pudiendo tener
  Microsoft Y Google a la vez; migración `027_remote_sources.sql`).
- Fase 2: buscar y vincular correos del caso al expediente (`api/routes/matter_mail.py`), cuerpo y
  adjuntos se vuelven documentos con dedupe por sha256.
- Fase 3: OneDrive remoto SELECTIVO de solo lectura (`connectors/graph_drive.py` +
  `api/routes/remote_drive.py`), sync incremental con tope de tamaño y fail-soft por archivo.
- Fase 4: UI completa (navegador de carpetas, diálogo de búsqueda de correos, tarjetas del Panel).
- 5 commits en `main` (`7ccab33`..`c9f2a32`), sin push.
Qué decidimos:
- Dos revisores adversariales independientes: seguridad APROBADO sin bloqueantes/mayores;
  corrección con 3 mayores + 6 menores, TODOS corregidos antes del commit (renombrar en OneDrive ya
  no borra el archivo del expediente; botón para agregar permiso de archivos a una cuenta ya
  conectada; fallo por-correo no tumba el lote; entre otros — detalle en `progress.md` y
  `bugs-and-risks.md` Riesgo #54).
- Regresión 69/69 suites ALL PASS ×2 (`test_rls`/`check_env_pins` HALT intactos); línea base sube
  de 66 a 69.
Qué sigue:
- Capa 3 EN VIVO de Pipe/Cursor (conectar cuenta real, navegar carpetas, vincular correos,
  responsive) — sigue pendiente también la del botón "Revisar ahora" de la sesión 35.
- ACCIÓN DE PIPE: registrar las apps OAuth (Azure AD + Google Cloud) y poner las llaves en `.env` —
  hasta entonces todo responde 503 en llano (activación diferida, por diseño).
- Quick win #5 (checklist de pre-entrega en el gate de aprobación) sigue esperando aprobación de Pipe.
- Deuda consciente: sincronización PROGRAMADA de fuentes OneDrive (hoy solo botón manual).

## 2026-07-09 — Sesión 37
TL;DR: OCR local para PDFs escaneados (bloque 3a) + sincronización programada de OneDrive (bloque
3b); sesión interrumpida por corte de luz tras el último commit y cerrada en la retoma del mismo día.
Qué construimos:
- `ingest/ocr.py` + fallback página a página en `ingest/extract.py`: Mia ya lee PDFs escaneados
  100% en local, con honestidad por segmento y fail-soft (tope 150 págs / 10 min anotado).
- Job del scheduler cada 6h que sincroniza solo las carpetas de OneDrive remoto (cierra la deuda
  #1 del Riesgo #54); lock compartido con el botón manual, throttle 1h, fail-soft por fuente.
- Capa 2 adversarial: 3 mayores + 4 menores, TODOS corregidos (`ea28423`) + guarda `has_body`
  replicada en carpetas locales (`315dbd1`).
- 4 commits en `main` (`ad16a64`..`315dbd1`), sin push.
Qué decidimos:
- Regresión completa 70/70 ALL PASS (corrida en la retoma post-apagón); línea base sube de 69 a 70.
- `rapidocr-onnxruntime~=1.4` va en el grupo `~=` (fuera de los pins críticos del Riesgo #32).
Qué sigue:
- Capa 3 EN VIVO de Pipe/Cursor (fuentes remotas + botón "Revisar ahora") — sin cambios.
- ACCIÓN DE PIPE: llaves OAuth (Azure AD + Google Cloud) en `.env`.
- Decidir push de los 4 commits de esta sesión.

## 2026-07-09 — Sesión 39
TL;DR: Bloque A del plan de evolución de producto COMPLETO — Proyectos + carpetas sin fricción,
orquestación multi-agente autorizada por Pipe.
Qué construimos:
- A0: migración `028_projects_multifolder.sql` (`matters.kind`, `documents.source_id`,
  `documents.body`, `ck_documents_origin` gana `'mia'`) con backfill conservador
  (`HAVING count(*)=1`, huérfanos `NULL` nunca se podan) espejado a `origin='drive'`.
- A2: fix del bug latente de poda cruzada en `local_folders.py` (scoping por `source_id`) +
  superficie plural de carpetas por expediente (tope 10).
- A1: navegador seguro de carpetas (`safe_browse_roots`/`browse_folder`, fail-closed,
  `MIA_DISABLE_FOLDER_BROWSE`) + `FolderPicker.tsx` reemplazando los 3 inputs de ruta manual.
- A3: `matter_sources.py` + `FuentesPanel.tsx` — vista unificada de carpetas/OneDrive/correo con
  "+ Conectar fuente", absorbe el bloque de carpeta suelto de `asuntos/[id]/page.tsx`.
- A4: pestaña "Proyectos" completa — `kind` en matters, outputs `origin='mia'` con descarga
  `.docx`, `build_project_graph()` sin HITL (intake→work→END), nav + `proyectos/page.tsx` +
  `proyectos/[id]/page.tsx` (3 columnas).
Qué decidimos:
- Regresión completa ALL PASS 74/74 (línea base sube de 70 a 74); `npm run build` verde (14
  páginas). `test_rls`/`check_env_pins` (HALT) intactos.
- Capa 2 (5 revisores Opus por dimensión + verificador escéptico, contexto fresco): 12 hallazgos
  CONFIRMADOS, 0 descartados, TODOS corregidos salvo 2 notas de deuda aceptadas — incluye 2
  bloqueantes de pérdida de datos (backfill `DISTINCT ON` colapsaba historial multi-carpeta;
  poda de OneDrive sin `source_id` con el `FuentesPanel` nuevo permitiendo varias carpetas
  drive), 2 mayores (carrera en `sync_tenant` sin candado; chat de proyecto sin memoria
  conversacional) y 5 menores. Detalle completo en `progress.md` sesión 39.
- Riesgo #57 (`min(uuid)` en el backfill LOCAL de la migración) RESUELTO en esta sesión —
  `(array_agg(id))[1]`, confirmado por la regresión. Riesgo #56 (navegador de carpetas fail-open
  en Modo A) sigue abierto como deuda documentada.
Qué sigue:
- Bloque B del plan de evolución de producto: guías de trabajo asistidas + gobernanza de skills
  (`memory/plan-evolucion-producto.md`).
- Capa 3 EN VIVO de Pipe (Proyectos, FolderPicker, FuentesPanel) — pendiente, junto con la deuda
  de capa 3 acumulada de sesiones anteriores (OAuth de correo/OneDrive en `.env`).

## 2026-07-10 — Sesión 42
TL;DR: Arrancó el BLOQUE INSTALADOR (Fase 4 distribución): Fase 1 de empaquetado COMPLETA
(backend PyInstaller 459 MB + frontend standalone con Node portable 103 MB) + cáscara blindada
(instancia única, CSP, identidad de procesos), regresión 82/82.
Qué construimos:
- packaging/ completo (entry + spec + builds reproducibles) con gates 23/23 y 24/24; bundle
  verificado en vivo sin Python (/health + 401) y humo del frontend con node.exe portable.
- Blindaje de desktop/: single-instance, CSP con splash externalizado, pg_isready, identidad
  backend/frontend en los 4 caminos (gate 42/42) — motivado por incidente real: la cáscara
  adoptó a voicebox (8000) y al Next de Intelligence Sura (3100) en la máquina de Pipe.
- 2 revisiones adversariales (empaquetado y cáscara): 1B+4M+5m, todos corregidos de raíz.
Qué decidimos:
- Pipe: OCR dentro del instalador, voz como descarga posterior; instalador sin firma para el
  equipo (Azure Trusted Signing pendiente de registro para venta).
- Fable: LiteLLM va como 2º exe empaquetado (F2) — sin él, políticas nube/soberano rotas.
- test_ux timeout 300→600s (recalibración post-standalone, no debilitamiento).
Qué sigue:
- F2: primer arranque automático (%LOCALAPPDATA%\Mia, .env semilla + JWT, initdb + migraciones
  003→030 + checkpointer, orchestration.json de instalador, LiteLLM 2º exe).
- F3 wizard de bienvenida · F4 instalador NSIS + E2E en frío.
- Capa 3 de Pipe acumulada: splash bajo CSP (visual), recorrido de producto sesiones 39-41.

## 2026-07-11 — Sesión 43
TL;DR: Fase 2 del instalador COMPLETA — MIA se prepara sola en el primer arranque y LiteLLM
es el 4º servicio supervisado; 84/84 suites, 11 hallazgos de capa 2 corregidos.
Qué construimos:
- `mia.setup.first_run` (`--first-run` del exe): app_dir + .env semilla atómico + initdb
  loopback/scram + migraciones 003→030 + checkpointer + marcador `.mia-setup-complete`;
  idempotente y auto-reparable. Gate test_first_run 68/68 (initdb y login reales).
- mia-litellm.exe (108 MB) desde `.venv-litellm` con blindajes portados (cost-map, allowlist,
  scrub anti-Prisma, dotenv neutralizado, --host 127.0.0.1); humo vivo 200/200/401 + bind
  loopback verificado. Gate test_litellm_packaging 60/60.
- Cáscara: gatillo triple del setup (marcador+PG_VERSION+.env), tokens ${exe_dir}/
  ${local_app_data}, LiteLLM con identidad de adopción, child_died antes del health (bug en
  los 3 bucles), plantilla `orchestration.installer.json`. Gate shell_hardening 77/77.
Qué decidimos:
- Bootstrap en Python (no Rust); la cáscara solo decide cuándo y muestra progreso.
- Marcador de finalización como fuente de verdad de "setup completo" (PG_VERSION/.env no
  bastan — hallazgo M1 de capa 2).
- Loopback para TODO servicio empaquetado (litellm bindeaba 0.0.0.0 — M5, corregido y
  verificado en vivo).
- Dev sigue con LiteLLM manual (3 terminales); el 4º servicio es solo del modo instalado.
Qué sigue:
- F3 wizard de bienvenida (llaves mínimas, política suscripción-first, §G).
- F4: recompilar ambos exes + NSIS + E2E en frío (Riesgo #59 con 7 puntos acumulados).
- Capa 3 de Pipe acumulada (sin cambios de esta sesión: fue backend/cáscara/packaging).

## 2026-07-24 — Sesión 49 (3ª del día) · Las 27 sondas adversariales de F2

TL;DR: MIA aguantó los 3 ataques 30/30, y leer los crudos —no el panel— destapó dos métricas
cuyo nombre induce una lectura falsa.

Qué construimos:
- Las 27 corridas en vivo que faltaban (30/30 acumuladas) en trozos foreground bajo
  `suscripcion`; 3 agregados con el mismo `prompt_hash 3391f17ea61324a4` del RE-BASELINE.
  Coste de tarjeta USD 0,00081 (solo embeddings).
- `harness.evidence_audit` + flag `--exige-evidencia` en `aggregate_eval_runs.py`: un agregado
  avisa (y puede reprobar) cuando alguna parte se guardó sin texto releíble. 6 checks nuevos
  en `test_eval_harness.py` → 67/67.
- Reglas 52-54 en APRENDIZAJES.md; riesgo #81 en bugs-and-risks.md; §SONDAS en findings.md;
  paquete de la Sesión A ampliado con las decisiones 5 y 6 y un ejemplar completo de revisión
  humana.

Qué decidimos:
- NO corregir M-1 (métrica de abstención) ni M-2 (etiqueta de éxito): las dos mueven cifras del
  baseline publicado, así que son decisión de Pipe en la Sesión A.
- El agregado de `entailment` se conserva en N=10 con su límite DECLARADO (la parte `_smoke` no
  es releíble); los números son válidos, la auditabilidad de esa corrida no.
- No paralelizar corridas: competir por CPU distorsiona la latencia, que es un dato que se
  publica.

Qué sigue:
- Sesión Pipe A (6 salidas + 4 decisiones + M-1 y M-2).
- Referencia en nube (tope USD 30 aprobado): RISK_CASES ×10 bajo `nube` + `--agentic-compare`
  — único frente ejecutable sin Pipe; destraba la decisión sobre lectura agéntica.
- Cierre de F2: ítem 2 de la spec (fuga al 100% de ocurrencias con falsos positivos medidos).

---

## 2026-07-27/28 — Sesión 51 · La Sesión Pipe A, ejecutada: F2 cerrada y las 4 barreras del harness

TL;DR: Pipe tomó las 7 decisiones pendientes en vivo, se aplicaron las tres de medición (la fuga
real del baseline queda en 0/63), se cerró F2 y entraron las cuatro barreras de su propio harness
de litigio, graduadas: tres avisan, una es muro. Commits `656dc20` → `cdc0f7c`, todos pusheados.

Qué construimos:
- **N-1** (`656dc20`): `jurisdiction_leak_signal` deja de contar como fuga la mención de una norma
  acompañada de negación explícita en su misma oración; `harness.leak_signal_vigente` resuelve las
  señales persistidas con la regla vieja (recalcula si el texto es releíble, o las marca
  `revision_pendiente`). Verificado recalculando los 63 crudos guardados: 1 → 0.
- **M-1**: `ABSTENTION_PHRASES` recalibrado MIDIENDO los 62 borradores completos (11 → 46 formas)
  con criterio de admisión declarado; barrera nueva `test_abstention_recalibrada.py` (18/18) que
  impide que vuelva a caer a cero en silencio.
- **M-2**: el panel dice «Turnos completados» y, en casos de RIESGO, «Se negó correctamente».
- **Barrera de afirmaciones negativas** (`99fb4a2`): `scan_negative_claims` +
  `retrieval.document_full_text` + confrontación en el grafo + regla y corolario en el prompt.
- **MURO del banco de citas quemadas** (`ba1fbde`): migración 047 con RLS, `memory/burned_citations`,
  cotejo en `annotate_draft` ANTES de toda vía de respaldo.
- **Barrera de contaminación entre expedientes** (`ae42b96`): catálogo derivado de
  `documents.parte` del propio despacho — sin listas cableadas.
- **Cierre de F2** (`6aaef70`): casos de RIESGO en el examen por defecto (3 → 9 casos),
  `docs/tramites-terceros-pipe.md`, riesgo #81 cerrado, reglas 55-63 en APRENDIZAJES.
- **La puerta del banco** (`2c7ff04`): `/api/citas-quemadas` (POST/GET/DELETE) + enlace «Esta cita
  no existe o no dice eso» en el diálogo de cada cita + los dos avisos nuevos pintados en la
  pantalla de revisión.

Qué decidimos (las 7 de Pipe, en `decisions.md` #45-#47):
- La regla del muro es «no afirmar sin respaldo», no «no escribir el número» (N-1).
- Recalibrar la abstención YA y declarar el corte de serie, en vez de pagar un re-baseline (M-1).
- Dos líneas separadas en el panel: funcionó ≠ acertó (M-2).
- Los casos de RIESGO entran al examen por defecto; F2 se cierra sin endurecer más ni gastar los
  USD 22,6 restantes de nube; se disparan los dos trámites de terceros; el «Modo A» (Docker) sale
  del alcance de la v1.
- **Dureza transversal**: toda barrera nueva nace como AVISO y solo sube a muro cuando se mida que
  no bloquea trabajo bueno. Única excepción: el banco de citas quemadas.

Qué sigue:
- **Helper de siembra de un despacho de prueba CON PERFIL** (`execution/seed_despacho_demo.py`):
  sin él no hay verificación visual posible — el gate de bienvenida no se salta omitiendo pasos
  (regla 62). Es lo que bloqueó las capturas del botón nuevo.
- Caso de oro con expediente GRANDE (sigue siendo el prerrequisito de N-2).
- Producto: instalador y bienvenida de F3.
- De Pipe: la lectura de calidad de las 6 salidas y los dos trámites (Azure + OAuth).

## 2026-07-29 — Sesión 52
TL;DR: instalador re-ensamblado y verde, caso de oro GRANDE construido, y el primer piloto con un
expediente REAL destapó tres defectos de capacidad que el banco sintético no podía ver.

Qué construimos:
- Instalador `Mia_0.1.0_x64-setup.exe` 434,2 MB con F1/F2 y las 47 migraciones dentro. Tres
  defectos cerrados: el borrado de rutas largas que abortaba el build entero, el compilador del
  backend que borraba los payloads vecinos, y el mensaje de error del primer arranque que podía
  llegarle ilegible al abogado (verificado en el .exe real).
- Barrera `test_sin_instrumentacion_debug.py`: el instalador anterior llevaba dentro código de
  depuración de otra sesión que hacía POST a 127.0.0.1:7610 desde la máquina del abogado.
- Caso de oro `expediente-voluminoso-cruce-disperso` (252 fragmentos, tres datos enterrados en
  documentos distintos) + señal `recall_markers_signal` + el segundo eje del comparador agéntico
  (ahorrar perdiendo un dato del expediente = PEOR).
- `execution/purgar_piloto.py`: borrado verificable en tres sitios, incluidos los transcripts del
  CLI de la suscripción, que están FUERA de MIA y nadie esperaba.
- Embeddings por lotes: la ingesta de un expediente grande fallaba entera contra el tope del
  proveedor, y le pasaba igual al abogado al subir un documento grande.
- Política de motores: salto rápido ante timeout de la suscripción + aviso de crédito al abogado +
  plan Max como REQUISITO en la instalación.

Qué decidimos:
- El caso de oro grande queda FUERA del examen por defecto (coste y comparabilidad de las series).
- La rúbrica jurídica NO se reutiliza para medir recuperación: sería una etiqueta engañosa (#81).
- Sin ejecución del brazo agéntico no hay veredicto de N-2, sino NO CONCLUYENTE.
- Piloto con expediente real autorizado por Pipe, con borrado demostrado; lo anonimizado queda como
  la única vía para lo que ya salió de la máquina.
- Max se enuncia como requisito, no como consejo (copy aprobado tras cinco iteraciones).

Qué sigue:
1. Enganchar el aviso de cambio de motor a la pantalla (lo único a medias).
2. El ALCANCE en expedientes voluminosos: 22% leído, medido y sin resolver. La lectura agéntica no
   sirve (apagada bajo suscripción): subir cobertura de la primera lectura o relectura dirigida.
3. `seed_despacho_demo.py` y con él la verificación visual.
4. Bienvenida de F3.

## 2026-07-30 — Sesión 53

TL;DR: los cuatro pendientes de la 52, cerrados; el alcance quedó medido, repartido y DECLARADO
(el recall de datos enterrados no subió: el límite es estructural y ahora se dice en pantalla).

Qué construimos:
- El aviso de crédito llega a la pantalla (`turno_sse` en asunto, proyecto y cierre del borrador;
  también cuando el turno falla, porque el crédito ya se gastó). Gate 41/41.
- `execution/seed_despacho_demo.py` + su gate: despacho con perfil, expediente y borrador esperando
  revisión generado por el grafo real. Con él se ve por fin la interfaz sin veinte minutos de
  andamiaje — y encontró dos defectos de pantalla el primer día.
- Alcance: barrido de cobertura por zonas + relectura dirigida por los hechos/investigación del
  turno + aviso de alcance en el informe («leí 86 de 252 fragmentos»). Gate nuevo 40/40.
- Bienvenida F3: la pregunta de jurisdicción pasa de 21 filas con scroll a fichas con buscador.

Qué decidimos:
- La corrección del alcance es de CÓDIGO, no de modelo: bajo suscripción no hay herramientas.
- Cubrir solo piezas huérfanas no basta (medido): el sesgo también está dentro de cada pieza.
- Ninguna recuperación garantiza ver un fragmento concreto → el alcance se declara, no se promete.
- Subir el techo de lectura queda DESCARTADO con dato: 128→256 sacó el turno de la suscripción y
  costó USD 1,01 de tarjeta en una sola consulta.

Qué sigue:
1. E2E automatizado de la primera vez (salida medible de F3), cronometrado y con capturas.
2. El alcance, si Pipe quiere una vía distinta a las tres implementadas.
3. Lo que quede de F3 tras el E2E.
