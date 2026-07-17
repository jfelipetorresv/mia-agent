# Retrospective: robustecimiento e integridad de MIA

**Date**: 2026-07-17
**File**: retrospective-2026-07-17-001-robustecimiento-integridad.md

## Summary

Sesión larga y multi-frente sobre la rama `feature/robustecimiento-sin-aws`:
1. Cierre de 6 de los 8 riesgos abiertos de la sesión 48 (#68–#73), con gates verdes.
2. Fix de UI (contraste del control "Apariencia") + validación visual de las 13 pantallas.
3. Validación visual/funcional completa de MIA (yo + segunda pasada de Codex).
4. Análisis del repo de referencia `claudeclaw-os` (4 subagentes + Codex) → `docs/analisis-claudeclaw-os.md`.
5. Descubrimiento y arreglo de raíz: el "caching ahorra ~75%" era una afirmación **sin respaldo y sin mecanismo cableado**. Se instrumentó la medición y se cableó el caching de verdad.
6. Auditoría de integridad de 4 frentes ("ni una promesa que no corresponda") + arreglos.
7. Handoff detallado para continuar en terminal fresca (cablear Pinecone/MCP/banco de oro + mejoras 2/3).

Cuatro commits de contenido en la rama: `8cdc7a3`, `ac7ed31`, `e8ce3b3`, `b8ec05f`.

## Errors Encountered

| Error | Cause | Resolution | Prevention |
|-------|-------|------------|------------|
| `py -c ...` exit 2 al verificar sintaxis | Se usó el launcher `py`/python global en vez del venv del proyecto | Se localizó `.venv/Scripts/python.exe` y se usó ese | Empezar toda ejecución con el intérprete del venv del repo, nunca `py`/python del PATH |
| HTTP 500 en `/asuntos/{id}/revisar` (test visual) | DOS instancias de Next peleando por el puerto 3100 (`EADDRINUSE`) corrompían el worker de compilación (`Jest worker encountered child process exceptions`) | Se mató todo lo que escuchaba en 3100 y se relanzó una sola instancia → 200 limpio | Antes de relanzar un dev server, matar por puerto y confirmar puerto libre; un 500 en dev con jest-worker suele ser entorno, no bug |
| `test_retrieval_knowledge` c3 en rojo (34/35) tras el caching | El split del system en 2 bloques de content (con `cache_control`) cambió la FORMA del mensaje para alias `claude-*`; el gate asumía "system = string byte-idéntico" | Se actualizó c3 para comparar el TEXTO reconstruido (byte-idéntico) + c3b confirma el marcado de caché; 36/36 | Un cambio que altera la forma de transporte del prompt debe traer la actualización de los gates que codifican la forma vieja |
| Extensión Chrome (claude-in-chrome) no conectada | El navegador no estaba enlazado a la sesión | Fallback a Playwright vía Node (instalado aislado en scratchpad, navegadores ya en cache) | Documentar el fallback Playwright para `/EA-visual-verify` cuando el MCP de navegador no esté disponible |

## Snags & Blockers

- **Codex encolado indefinidamente**: la tarea Codex del análisis de RFCs quedó `queued` 9+ min sin arrancar. Impacto: no llegó a tiempo para el consolidado. Resolución: no se bloqueó el entregable; los 4 subagentes cubrían todos los subsistemas y se consolidó sin Codex, dejando su task-id para recuperar después.
- **Procesos background killed entre turnos**: backend (8000) y frontend (3100) que se dejaron encendidos se detuvieron solos entre turnos; hubo que relanzarlos para el recorrido de pantallas. Impacto bajo.
- **Reporte de subagente sobre-confiado**: el agente que cableó el caching afirmó que el fallo c3 "no era suyo". Verificándolo, SÍ lo era (efecto directo del split). El escepticismo evitó propagar una conclusión falsa.

## Workarounds Applied

- **Playwright aislado en scratchpad** (`scratchpad/pw`) en vez del MCP de navegador. Es un workaround estable; no requiere revisión salvo que se estandarice para `/EA-visual-verify`.
- **Migración 042 aplicada a mano** a la DB `mia` de desarrollo para poder correr gates con las columnas nuevas (idempotente, seguro). Normal en el flujo de MIA (cada `init_*` aplica su SQL).

## Lessons Learned

1. **Verificar los hallazgos de los subagentes antes de propagarlos o descartarlos.** El c3 (el agente decía "no es mío" — sí lo era) y el hallazgo del caching (auditor dijo "no está cableado" — se confirmó con grep propio: 0 apariciones de `cache_control`). En un proyecto donde la regla es "ningún hecho sin fuente", eso aplica también a lo que reportan los agentes.
2. **Una afirmación de arquitectura sin medición es deuda invisible.** El "~75% de ahorro por caching" vivía en 4 archivos (incluida la constitución) sin que nada lo midiera NI lo activara. El arreglo correcto no fue inflar un número, sino cablear el mecanismo + medirlo + declarar el límite honesto (no cachea bajo el mínimo de Anthropic sin SOUL real).
3. **Delegar con grupos de archivos DISJUNTOS y sin git en los agentes evita la corrupción multiagente.** Cuatro agentes escribieron en paralelo sin pisarse; el coordinador integró y commiteó. La regla de reservar el número de migración al empezar (Riesgo #73, ya con guardarraíl) sostuvo el trabajo paralelo.
4. **El coordinador preserva contexto delegando ejecución, pero NUNCA la verificación de integración ni el commit.** El fallo c3 solo se detectó al integrar y correr la regresión localmente.
5. **Distinguir falso positivo de bug real exige limpiar el entorno primero.** El 500 de `/revisar` parecía un bug de la app; era doble servidor. Reportarlo como bug habría sido justo el tipo de "afirmación que no corresponde" que la sesión combatía.

## Command Improvements

- `/EA-visual-verify`: asume Playwright MCP, que no estaba disponible; convendría documentar el fallback (Node Playwright aislado + login por token en localStorage + reload para probar persistencia). Además, capturar automáticamente errores de consola/red y redirects por pantalla (como se hizo con el script `tour.js`) hace el veredicto objetivo, no solo visual.
- `/EA-retrospective`: correcto tal cual; útil que numere por día.

## Process Improvements

- Antes de declarar un bug en dev, matar por puerto y confirmar una sola instancia del servidor.
- Cuando un subagente reporte que un fallo "no es suyo", reproducirlo aislado antes de aceptarlo.
- Para features con "API/UI completa sin consumidor" (Pinecone, MCP, banco de oro), decidir explícitamente cablear-vs-retirar antes de shippear una pantalla que promete algo inexistente.

## Metrics

- Tareas completadas: 13 de 15 en el task list (2 mejoras quedan en handoff, por decisión de Pipe).
- Riesgos cerrados: 6 (#68–#73) + hallazgos de auditoría de 4 frentes.
- Commits de contenido: 4 en la rama.
- Falsos positivos descartados con verificación: 2 (500 de `/revisar`; "c3 no es mío").
- Estimado productivo vs. incidentes: ~85% productivo / ~15% en incidentes y verificación (la verificación NO es desperdicio: destapó el bug c3 y el falso 500).

## Next Session Recommendations

- [ ] Ejecutar el handoff del 2026-07-17 en terminal fresca: empezar por cablear Pinecone (meta A), luego MCP (B) y banco de oro (C).
- [ ] Mejora 2 (blindaje del instalador) antes de la prueba en vivo: preservar secretos en upgrade, smoke-test post-first-run, backup pre-migración.
- [ ] Mejora 3: atajos de despacho (comando→prompt canónico) + health-check de playbooks.
- [ ] Verificación en vivo del caching con un `SOUL.md` real (confirmar hit-rate > 0 con API de Anthropic).
- [ ] Borrar la función huérfana `cron/scheduler.py::gepa_run_all_tenants()`.
- [ ] Correr `test_ux.py` (build completo) para confirmar el panel nuevo end-to-end.
