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
