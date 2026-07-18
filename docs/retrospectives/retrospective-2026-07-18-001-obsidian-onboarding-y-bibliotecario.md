# Retrospective

**Fecha:** 2026-07-18
**Sesión:** Segundo tramo del día — continuación tras el cierre de la sesión 49 (6 features inertes cableadas)

## Summary

Tras cerrar la sesión 49, este tramo hizo tres cosas: (1) reincorporar Obsidian al checklist "Configura a Mia" y corregir una atribución falsa a Pipe encontrada en el código; (2) diseñar "el Bibliotecario de Obsidian", destilando 3 repos externos (second-brain, megarag, notebooklmreimagined) en un documento, una página visual y una entrada de memoria; (3) tomar capturas del diseño y empujar 19 commits a GitHub. Todo se orquestó con workflows dinámicos (Opus coordina, Sonnet implementa, Opus verifica adversarial).

## Errors Encountered

| Error | Cause | Resolution | Prevention |
|---|---|---|---|
| El ajuste de onboarding reintrodujo la latencia MN3: `GET /api/setup/status` podía tardar ~60s | La detección de "instalado" usaba `is_installed()` completa, que cae a `winget list` con timeout de 60s cuando Obsidian no está instalado; envolver la llamada en `asyncio.to_thread` no evita que la primera carga espere la respuesta de winget | El verificador adversarial (Opus) lo atrapó como BLOQUEANTE pese a que el gate marcaba 32/32 verde; se re-implementó con `is_installed_fast()` (solo verifica el ejecutable local, sin winget) y se probó espiando winget (0.6s, `winget_calls=[]`) | Nunca meter un subprocess de timeout largo en un endpoint de latencia (status); separar detección rápida (para status) de detección completa (para acciones) |
| Atribución falsa a Pipe en el código: comentarios decían "Obsidian pospuesto por decisión de Pipe 2026-07-06" | El commit `f971264`, al resolver la latencia de winget, sacó el paso completo del onboarding y lo etiquetó como decisión de producto de Pipe sin que existiera tal decisión (Pipe confirmó que nunca la tomó) | Se corrigieron los 3 comentarios por una nota verídica que describe el motivo técnico real | No atribuir decisiones de producto a Pipe sin que consten; separar explícitamente "arreglo técnico" de "decisión de producto" en comentarios y mensajes de commit |
| Comandos de red del shell (`Test-NetConnection`, `netstat`) cuelgan (timeout ~2 min); `SendUserFile` de un PNG de ~1MB falló (400/timeout de red) | Confirma un patrón ya conocido de red frágil en este entorno Windows | Se sondearon puertos con `socket` + `settimeout` / `curl`; las capturas quedaron guardadas en la carpeta del proyecto (objetivo cumplido) aunque no pudieron enviarse por chat | Delegar arranque/captura a subagentes aislados; no depender de comandos de red del shell ni de `SendUserFile` para archivos grandes en este entorno |

## Snags & Blockers

- Comandos de red del shell (`Test-NetConnection`, `netstat`) cuelgan hasta el timeout — ya documentado en sesiones previas, se repitió.
- `SendUserFile` falló al enviar un PNG de ~1MB (timeout/400 de red). Las capturas se guardaron localmente como respaldo.

## Lessons Learned

1. Separar "detección rápida para un path de latencia" de "detección completa para una acción": ningún endpoint de status debe invocar un subprocess de timeout largo; un caché no salva la primera carga fría.
2. Un gate que mockea la función bajo prueba NO prueba la propiedad real (latencia): "32/32 verde" no significa "sin latencia". El verificador debe ejercitar/espiar el recurso real (winget), no el mock. El verificador adversarial que re-corre y espía el recurso real fue el que atrapó el bloqueante.
3. No atribuir decisiones a Pipe sin sustento; separar arreglo técnico de decisión de producto tanto en comentarios de código como en mensajes de commit.
4. El modelo "propone y aprueba" absoluto no siempre es lo que Pipe quiere: a veces prefiere autonomía (facilitarle la vida) con salvaguardas (log, deshacer, lo irreversible nunca automático). Diseñar autonomía graduada, no binaria — este fue el giro clave del diseño del Bibliotecario.
5. Este entorno (Windows de MIA) tiene red frágil de forma recurrente: delegar arranque/captura a subagentes aislados y no depender de `SendUserFile` para archivos grandes ni de comandos de red del shell.

## Command Improvements

- `/EA-visual-verify` y el envío de imágenes: en este entorno el envío de PNG por chat falla por red de forma consistente; guardar en la carpeta del proyecto es la vía confiable y debe tratarse como el flujo por defecto, no como fallback.

## Process Improvements

- El verificador adversarial que re-corre y espía el recurso real (no el mock) es indispensable y debe mantenerse en cada ola de trabajo, no solo cuando hay sospecha de problema.
- Reservar migración/numeración y archivos compartidos: solo el coordinador los toca (ya aplicado en este tramo).

## Metrics

- Tareas completadas: reincorporación de Obsidian al onboarding (gate 35/35, test_rls 19/19), diseño del Bibliotecario (documento + artifact + memoria), capturas de diseño, push de 19 commits a GitHub.
- Bloqueantes atrapados y corregidos: 1 (latencia de winget en `/api/setup/status`).
- Snags de entorno: 2 (comandos de red del shell, envío de imágenes por `SendUserFile`).

## Next Session Recommendations

- [ ] Construir Fase 1 del Bibliotecario de Obsidian (mapa + conexiones + notas, sin mover archivos).
- [ ] Capa 3 en vivo de MCP: arrancar LiteLLM y re-correr `test_mcp` stdio-live, y probar Pinecone real.
- [ ] Resolver el cupo de agentes en `list_shortcuts`.
