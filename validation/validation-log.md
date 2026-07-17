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
