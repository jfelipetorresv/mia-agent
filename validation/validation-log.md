# Validation Log

Screenshots and validation events are logged here.

---

## [2026-07-17 14:41] Verificación visual — Riesgo #70 (el hilo sobrevive al F5)

- **Files**: `validation/screenshots/01_2026-07-17_asunto-hilo-cargado.png`, `validation/screenshots/02_2026-07-17_asunto-hilo-tras-F5.png`
- **URL**: http://localhost:3100/asuntos/{id} (asunto de prueba con 2 turnos sembrados)
- **Full Page**: yes
- **Selector**: none
- **Notes**: Flujo Playwright (login por token → asunto → captura → reload dura F5 → captura). Confirmado programáticamente: hilo_visible_antes=true, hilo_sobrevive_F5=true. Las dos capturas son idénticas — los 4 mensajes (2 turnos usuario/MIA) persisten tras el F5. Antes del fix, la 2ª habría mostrado el chat vacío. Endpoint GET /matters/{id}/historial responde 4 mensajes en orden. Backend 8000 + frontend 3100 arriba; LiteLLM no fue necesario (no se envían turnos nuevos).

## [2026-07-17 15:43] Validación visual COMPLETA de MIA (13 pantallas)

- **Files**: `validation/screenshots/03..15_2026-07-17_*.png` (login, registro, home, panel, conversar, asunto, asunto-revisar, proyectos, conocimiento, agentes-juridicos, configuracion, onboarding, activar)
- **Método**: recorrido Playwright autenticado (usuario de prueba con 1 asunto y 2 turnos) + revisión visual por agente QA + barrido funcional de 25 endpoints GET.
- **Resultado VISUAL**: 12/12 pantallas OK. Sin jerga técnica, sin errores/500/undefined, sin desbordes ni imágenes rotas; datos reales y estados vacíos bien redactados.
- **Resultado FUNCIONAL**: 0 respuestas 5xx en los endpoints de las pantallas (dashboard/stats, matters, historial, wiki/concepts, proposals, playbooks, mailbox/status, jurisdictions, onboarding/status, dreams, gold-cases, notebooklm/status… todos 200). Los 404 observados son de paths probados a ciegas, no rutas rotas.
- **Redirects esperados**: /asuntos/{id}/revisar → /asuntos/{id}?sin_borrador=true (no hay borrador que revisar); /activar → /onboarding.
- **Único hallazgo**: el item "Apariencia" del sidebar se ve semitransparente/casi ilegible sobre el degradado inferior (contraste bajo). Cosmético. Detalle menor de copy: "lista(s)".
- **Falso positivo descartado**: un HTTP 500 inicial en /revisar era ruido de DOS instancias de Next peleando por el puerto 3100 (EADDRINUSE); con una sola instancia limpia responde 200. NO es bug de la app.

## [2026-07-17 15:55] Fix del hallazgo — contraste de "Apariencia" en el sidebar

- **Cambio**: `frontend/app/_components/ThemeToggle.tsx` — el botón "Apariencia" no tenía clase de color de texto y en el scope oscuro del sidebar quedaba casi invisible; se le añadió `text-muted-foreground` para igualarlo a "Cerrar sesión" (que sí se leía).
- **Verificación**: captura `16_2026-07-17_sidebar-apariencia-fix.png` — "Apariencia" ahora se lee con el mismo contraste que "Cerrar sesión". tsc 0 errores.

## [2026-07-17 23:10] Verificación visual — atajos de despacho (chat) + salud de guías (memoria/Conocimiento)

- **Contexto**: commit `c0df832` (feat(despacho): atajos de un clic en el chat + salud de las guias del despacho). Backend nuevo `GET /api/atajos`, `GET /api/playbooks` (con `health_status`), `POST /api/playbooks/{id}/health`.
- **Arranque**: DB portable 55432 YA arriba. Backend (uvicorn, puerto 8000) y frontend (next dev, puerto 3100) NO estaban corriendo — se arrancaron ambos con `scripts/start_api.ps1` / `scripts/start_frontend.ps1` (run_in_background), listos en <10s. LiteLLM (4000) NO se arrancó (no hace falta para estas 2 pantallas).
- **Seed**: tenant de prueba `VISUAL_VERIFY Lexia Demo` (`ad85a672-3523-4493-8487-5ab70e3f1bda`) creado directo por psycopg (molde de `execution/test_despacho_atajos.py` / `test_playbook_health.py`): 2 guías activas ("Contestacion de demanda ordinaria" con contenido limpio, "Recurso de reposicion" con 2 citas sin marcar) + 1 persona habilitada ("Estratega", summon_phrases). Se llamó `POST /api/playbooks/{id}/health` por curl para fijar `sano`/`revisar` antes de la captura, y se creó `mia-data/soul_ad85a672-....md` para saltar el `OnboardingGate`. Token JWT minteado con `config.JWT_SECRET` (mismo patrón que los gates), inyectado en `localStorage.mia_token` vía Playwright headless (Chromium cacheado, sin pelear con el formulario de login).
- **Ruta 1 — `/chat` (chat vacío, chips de atajos)**: URL final `http://localhost:3100/chat`, HTTP 200, 0 errores de consola, 0 requests fallidos. Aparecen los 3 chips esperados ("Contestacion de demanda ordinaria", "Recurso de reposicion", "Estrategia" → icono de persona para "Estratega"). Clic en el primer chip: el texto canónico se PRE-LLENA en el cuadro de mensaje ("Aplica la guía del despacho \"Contestacion de demanda ordinaria\": cuando el despacho contesta una demanda civil...") y NO se envía (el chat sigue vacío, sin turnos nuevos).
- **Ruta 2 — `/memoria` pestaña "Guías y habilidades" (badges de salud)**: URL final `http://localhost:3100/memoria`, HTTP 200, 0 errores de consola. Badge verde "Sana" en la guía sin citas pendientes, badge naranja "Revisar" en la guía con citas sin marcar — coincide 1:1 con lo que devolvió la API. Clic en "Revisar salud" de la guía ya sana: re-chequea sin error y el badge se mantiene "Sana" (idempotente, sin romper nada). 2 requests con `net::ERR_ABORTED` en `_next/static/chunks/...` durante la navegación inicial (recompilación normal de `next dev`, no afectan el render ni aparecen en la 2ª captura).
- **Files**: `validation/screenshots/17_2026-07-17_chat-atajos-vacio.png`, `18_2026-07-17_chat-atajo-clic-prellenado.png`, `21_2026-07-17_memoria-salud-guias.png`, `22_2026-07-17_memoria-revisar-salud-clic.png`.
- **Veredicto**: PASA. Ambas pantallas funcionan como se cableó: chips de un clic pre-llenan sin auto-enviar, badges de salud reflejan el estado real de cada guía y el botón "Revisar salud" funciona en vivo. Sin jerga técnica visible, sin errores de consola/red relevantes, sin datos fabricados en pantalla (todo viene del backend real).

## [2026-07-18 11:12] Captura de la propuesta de diseño — El Bibliotecario de Obsidian

- **Fuente**: HTML self-contained (sin fuentes/CDN externos) renderizado directo desde disco vía `file://` con Playwright headless (Chromium reusado del proyecto `iakids`, sin reinstalar). Página estática de diseño (`El Bibliotecario de Obsidian` — propuesta de cómo MIA lee todo el vault pero solo escribe en su propia carpeta, con los "dos planos" de riesgo, las tres salvaguardas del modo autónomo y las cuatro barreras duras).
- **Files**: `validation/screenshots/01_2026-07-18_bibliotecario-claro.png` (1280px, tema claro, fullPage), `validation/screenshots/02_2026-07-18_bibliotecario-oscuro.png` (1280px, tema oscuro, fullPage), `validation/screenshots/03_2026-07-18_bibliotecario-movil.png` (420px, tema oscuro, fullPage).
- **Viewport/DPI**: desktop 1280×900 lógico, deviceScaleFactor 2 (nitidez); móvil 420×800, deviceScaleFactor 2.
- **Resultado VISUAL**: 3/3 capturas OK. Sin texto cortado, sin overflow horizontal, tipografía y jerarquía consistentes en ambos temas, buen contraste en modo oscuro (fondo casi negro, acentos teal/verde legibles). El layout de "Dos planos" (grid 2 columnas) colapsa correctamente a una columna en móvil. Sección de código (árbol del vault) se lee sin recortes en las tres capturas.
- **Nota**: no se requirió `npm install` — se reusó el paquete `playwright@1.61.1` ya presente en `D:\Inteligencia Artificial\iakids\node_modules` vía `NODE_PATH`, y los binarios de Chromium cacheados en `~/AppData/Local/ms-playwright`. Sin cambios de código; sin git.

## [2026-08-04] E2E automatizado del recorrido de primera vez — 3 corridas VERDES (F3)

- **Qué**: `e2e/recorrido_primera_vez.mjs` (Playwright, navegador real, headless) automatiza el
  recorrido COMPLETO de primera vez: `/register` → `/activar` (auto-salto en dev) → `/onboarding`
  (7 pasos, incluida la ficha de país) → crear asunto → subir expediente fijo → pregunta →
  borrador → gate de citas → aprobar → sonda del `## aprendido`. Screenshot por paso +
  `tiempos.json` en `validation/screenshots/corrida-{1,2,3}/`.
- **Expediente fijo y versionado**: `e2e/generar_expediente.py` deriva 3 `.txt` (252 fragmentos,
  ~50 KB) del caso de oro `expediente-voluminoso-cruce-disperso` de `backend/mia/eval/cases.py` —
  determinista, versionado como código, con los 3 datos decisivos enterrados.
- **Condiciones de medición** (spec 03): máquina del proyecto (Windows 11, 47 GB RAM), política
  `suscripcion`, servicios ya arriba al arrancar el reloj; la medición INCLUYE subir e indexar;
  termina cuando el borrador aprobado es visible (`?confirmed=true`).
- **Resultado: 3 corridas consecutivas VERDES, sin intervención manual.**
  | corrida | total | turno (pregunta→borrador) | aprobar (POST sincrónico) | ## aprendido |
  |---|---|---|---|---|
  | 1 | 1803,4 s (30,1 min) | 1671,4 s | 81,0 s | poblado |
  | 2 | 1715,0 s (28,6 min) | 1516,6 s | 100,5 s | poblado |
  | 3 | 1396,4 s (23,3 min) | 1221,7 s | 95,7 s | poblado |
  **p50 = 28,6 min · p95 ≈ 30,0 min** (3 muestras). El tiempo se reporta, NO es umbral
  (decisión de Pipe 2026-07-21). Todo lo previo al turno (registro+onboarding+asunto+subida)
  cabe en <80 s; el turno del grafo es el 95 % del tiempo.
- **Gates del cierre**: `tsc` frontend 0 errores; test_rls PASA; test_gates_no_ciegos PASA;
  check_env_pins PASA.
- **DEFECTO UI-A (reproducible 5/5, PENDIENTE de arreglo)**: a 1440×900 (breakpoint `xl`) el
  aside derecho del asunto (tarjetas Diagnóstico/Normas/Riesgo) se monta sobre el botón
  «Revisar borrador» e intercepta el clic — un abogado con esa pantalla no puede pulsarlo.
  Evidencia: `corrida-1/15-FALLO.png` de la tanda (intento 5, conservada en el historial del
  monitor) y el AVISO en la salida de cada corrida. El E2E lo rodea navegando directo a
  `/revisar` y lo anuncia con «AVISO: aside tapa "Revisar borrador"».
- **HALLAZGO DE LENTITUD (señalable, no bloqueante)**: bajo `suscripcion` el caso voluminoso
  agota el timeout del motor primario (~13 min, `call_llm: timeout de la suscripción`) y salta
  a `claude-sonnet`; eso explica turnos de 20-28 min. Además `POST /draft/approve` corre el
  cierre del grafo SINCRÓNICO antes de responder: 81-100 s con la pantalla en «aprobando».
- **HALLAZGO POSITIVO**: el muro funcionó de punta a punta en las 3 corridas — el borrador
  declara honestamente qué citas quedan pendientes de verificación literal, el gate de citas
  exige el checkbox y el `## aprendido` se pobló las 3 veces tras aprobar.
- **Residuo**: cada corrida deja un despacho `e2e-<ts>@mia.test` (material 100 % sintético).
  Purga opcional por tenant: `execution/purgar_piloto.py --purgar --tenant <uuid>`.
- **Veredicto**: PASA la salida medible de F3-recorrido (3/3 verdes, evidencia visual archivada,
  `## aprendido` poblado), con el DEFECTO UI-A abierto y los dos hallazgos de lentitud anotados.

## 2026-08-07 — Sesión 55 · Corrida 4 (regresión tras los arreglos) — VERDE

- **Qué cambió antes de esta corrida**: DEFECTO UI-A corregido (`585f332`); muro determinista
  reconectado tras el gate LLM de `f264b1e` (`2e899bf`); honestidad de conexiones (`c6173e5`);
  migración 047 aplicada y en el ledger (health 45/45); el E2E ya NO rodea el defecto — el clic
  real en «Revisar borrador» ES la aserción (`f7316ad`).
- **Resultado: CORRIDA 4 VERDE, sin intervención manual.**
  | corrida | total | turno (pregunta→borrador) | aprobar (POST sincrónico) | ## aprendido |
  |---|---|---|---|---|
  | 4 | 1369,1 s (22,8 min) | 1239,7 s | 91,5 s | poblado |
  El paso «revisar-borrador» tomó 1,0 s con el CLIC REAL en el botón (sin `AVISO: aside tapa…`):
  el DEFECTO UI-A queda verificado como corregido en el recorrido completo, no solo en unidad.
- **Gates del cierre (re-corridos hoy)**: test_rls 19/19 · test_gates_no_ciegos 9/9 ·
  check_env_pins 12/12 · test_e2e 58/58 · test_seed_despacho_demo 17/17 ·
  test_sentence_report 47/47 · test_citas_quemadas 20/20 · `tsc` frontend 0 errores.
- **Los dos hallazgos de lentitud de la s54 siguen abiertos** (timeout del motor de suscripción
  ~13 min con salto a claude-sonnet; approve sincrónico de ~90 s). Sin cambios de esta sesión.
- **Veredicto**: PASA — el recorrido de primera vez queda verde CON el clic real y con el muro
  determinista de vuelta en el flujo del asunto.
- **Nota de evidencia**: las capturas (`validation/screenshots/corrida-{1..4}/`) se conservan en
  disco fuera de git (PNGs pesados; misma práctica de la s54); esta bitácora y `tiempos.json`
  son el registro citable.
