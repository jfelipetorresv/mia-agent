# Retrospective: Inc. 3 de Fase 1 + auditoría de usabilidad y RAG

**Date**: 2026-07-19
**File**: retrospective-2026-07-19-001-inc3-y-auditoria-usabilidad.md

## Summary

Sesión larga en tres actos. **(1)** Se cerró el **incremento 3 de la Fase 1**: limpieza de los 8 archivos sucios pre-existentes y las cuatro piezas (procedencia, `folio_ancla` real, ficha-loader + `/daily`·`/cierre`, clasificador de metadata con "Documentos por confirmar"). **(2)** Primer arranque en vivo con Pipe: se aplicaron las migraciones 045/046 a la DB real, `test_rls` 19/19, y se destrabaron varios problemas de entorno (no de producto). **(3)** Pipe reportó 10 problemas de usabilidad; se auditó todo con workflows multi-agente + Codex y se arreglaron cuatro bugs de fondo que explicaban el síntoma central: *"MIA no revisa bien la información"*.

Todo en la rama `feat/fase1-inc1-cleanup-scaffolding`, **sin push** (12 commits).

## Errors Encountered

| Error | Cause | Resolution | Prevention |
|-------|-------|------------|------------|
| `Token '-l' inesperado en la expresión` (PowerShell) | Comando de arranque de la DB entregado en 3 líneas unidas con backtick de continuación; al pegarlo, PowerShell lo partió y ejecutó cada trozo suelto | Reescrito a **una sola línea** en `docs/prueba-en-vivo-inc3.md` | Nunca entregar a un no-técnico comandos multilínea con `` ` ``. Una línea, siempre |
| Terminal lentísima ("perfiles tardaron 2650ms") | **2.060 procesos `node` de `statusline.js`** huérfanos desde el día anterior, saturando la máquina | Se mataron solo los `statusline.js` (2086 → 24 procesos); terminal de 5736ms → 1917ms | Ante "todo va lento", **contar procesos primero**; no culpar al síntoma visible (el perfil era mínimo, no tenía nada que optimizar) |
| `ChunkLoadError: Loading chunk app/layout failed` (×3, con **tres causas distintas**) | (a) saturación por los zombis; (b) recompilación de 50s tras borrar `.next`; (c) caché del navegador con la página vieja | (a) limpieza; (b) esperar el `✓ Compiled`; (c) abrir por `127.0.0.1:3100` (otro origen ⇒ caché limpio) | Antes de concluir, **pedir el recurso por HTTP**: si el servidor devuelve 200 en los 6 chunks, el problema es del cliente |
| MIA "se cierra sola" (3 veces) | Los servicios lanzados desde la sesión del asistente **mueren al terminar el comando** (el sandbox se lleva el árbol), incluso vía `Win32_Process.Create` | Se creó `Abrir Mia.cmd` para que **Pipe** la lance desde su sesión | Los servicios de desarrollo los arranca el **usuario**. No reintentar la misma vía tres veces |
| `Remove-Item on system path '/c' is blocked` | Un guard de seguridad interpretó mal el `cmd.exe /c` presente en la misma línea | Se quitó el `Remove-Item` (los `>` sobrescriben el log igual) | Separar borrados de rutas de comandos que contengan flags tipo `/c` |
| `psycopg.errors.UndefinedColumn: column m.name does not exist` | Se asumió que `matters` tenía columna `name`; es `title` | Script que descubre columnas vía `information_schema` y se adapta | Consultar el esquema real antes de escribir SQL exploratorio |
| `test_retrieval_knowledge` a10 pasó a 35/36 | La assertion esperaba el sello literal `<<<DOC 1>>>`; el fix legítimo lo cambió a `<<<DOC 1 · archivo.pdf>>>` | Assertion comparada por **prefijo** (`<<<DOC 1`); 36/36 PASS | Al cambiar un formato sellado, buscar las aserciones que lo comparan literal |
| Falsa alarma de `dangerouslySetInnerHTML` en `MiaMarkdown.tsx` | `grep -c` contó una mención **dentro de un comentario** que documentaba justamente que NO se usa | Se leyó con contexto (`-B8 -A8`) y se descartó | Nunca alarmar por un `grep -c`: confirmar con contexto antes de bloquear un commit |

## Snags & Blockers

- **Sin ojos en la aplicación**: la extensión de Chrome no está conectada a esta cuenta (`OAuth token belongs to a different claude.ai account`), y MIA no se mantiene viva desde la sesión del asistente. Resultado: **toda la auditoría fue de código**, sin verificación visual. Es la limitación más seria de la sesión.
- **Resultados de workflow truncados**: los retornos grandes se cortan (99.963 caracteres perdidos en una auditoría de 8 agentes). Se resolvió **editando el `return` del script y re-invocando con `resumeFromRunId`**: los agentes replican desde caché (23 ms, 0 tokens) y se recupera exactamente el campo que falta. Técnica muy valiosa, documentar y reutilizar.
- **`find` y `Glob` se cuelgan** en este repo (timeout de 120 s y 20 s respectivamente). `git ls-files | grep` resolvió en un segundo.
- **Cuenta duplicada**: el correo de Pipe ya estaba registrado desde el 20 de junio (despacho "lexia", vacío). Se verificó que no tuviera datos (0 asuntos, 0 documentos) **antes** de borrarlo.

## Workarounds Applied

- **`Abrir Mia.cmd`** (nuevo, commiteado): lanzador de doble-clic. No es un parche sino la vía correcta — evita que los servicios dependan de una sesión efímera.
- **Migraciones aplicadas fuera de `setup_db.ps1`**: el script tiene un *landmine* real — su chequeo previo de pgvector apunta al PostgreSQL **del sistema** (`C:\Program Files\PostgreSQL\16\bin\psql.exe`, puerto 5432) y no al portable (55432), y aborta con `exit 1` antes de migrar. Se aplicaron 045/046 directo al 55432. **Pendiente de arreglar en el script.**
- **Verificación por prefijo** en la assertion del sello: correcto, no un parche.

## Lessons Learned

1. **Medir antes de culpar.** Dos síntomas distintos (terminal lenta y `ChunkLoadError`) tenían **la misma causa invisible**: 2.060 procesos zombis. El perfil de PowerShell —el sospechoso obvio— no tenía nada que optimizar.
2. **Los datos del usuario ganan a las hipótesis elegantes.** La hipótesis "las sentencias eran PDF escaneados" era plausible y habría cerrado el caso. La consulta a la base la refutó: **622 fragmentos, 743.600 caracteres bien indexados**. El bug real era otro y solo apareció al medir.
3. **Cuantificar convierte una queja en un diagnóstico.** "No revisa bien la información" era irrefutable e inaccionable. `9.600 / 743.600 = 1,3 % del material` es un número que dice exactamente qué arreglar.
4. **Auditar antes de construir.** Gran parte de lo que Pipe pedía **ya existía y solo estaba mal expuesto** (`/api/setup/status` devuelve los 7 estados en lenguaje llano y solo lo consume Configuración). Construirlo de nuevo habría sido duplicar trabajo hecho.
5. **Tres intentos iguales = cambiar de estrategia.** Se intentó mantener MIA viva tres veces por la misma vía. Lo correcto era, al segundo fallo, devolver el control al usuario con un lanzador.
6. **El código guarda las decisiones.** El Panel "vacío" no era descuido: había una decisión escrita del 2026-07-09 de dejar ahí solo lo accionable. Leer el porqué antes de revertir evita romper un criterio deliberado.
7. **Una decisión de producto puede resolver un dilema técnico.** Ante "¿cuánto debe leer MIA?", Pipe no eligió un número: *"lo que se requiera para dar respuesta completa y suficiente"*. Eso cambia el diseño (recuperación adaptativa) en vez de mover una constante.

## Command Improvements

- `/EA-retrospective`: en repos grandes, `find` y `Glob` se cuelgan buscando la carpeta de retrospectivas. **Sugerencia: usar `git ls-files | grep -i retro`** para detectar la convención existente.

## Process Improvements

- **Higiene de procesos**: revisar periódicamente los `node` huérfanos de `statusline.js`. La causa raíz sigue **sin diagnosticar** (por qué el statusline no cierra sus procesos) — solo se limpió el efecto.
- **Arreglar `scripts/setup_db.ps1`**: que el chequeo de pgvector apunte al Postgres configurado en `.env` (`PG_PORT`), no a una ruta fija del sistema.
- **Cobertura ausente**: no existe **ni un solo test** de "carpeta vinculada a un PROYECTO", que es justo el escenario que falló en producción. Los 5 fallos de carpetas conocidos son todos de *asuntos*.
- **Un escritor por archivo**: los workflows funcionaron bien con frentes de archivos disjuntos; un agente reportó ver cambios ajenos en `git diff` (eran de sus hermanos del mismo workflow). Mantener la disciplina y verificar el `status` antes de cada commit.

## Metrics

- **Commits**: 12 (ninguno pusheado)
- **Bugs de fondo arreglados y verificados**: 4 (conocimiento tirado en proyectos, fragmentos anónimos, wiki en bruto, markdown sin renderizar)
- **Suites verificadas**: `test_rls` 19/19 · `retrieval_knowledge` 36/36 · `untrusted` 28/28 · `projects` 33/33 · `document_pipeline` 45/45 · `citation_guard` 19/19 · `context_references` 43/43
- **Problemas de entorno vs. de producto**: ~60 % del tiempo se fue en entorno (zombis, arranque, caché, cuenta duplicada), no en código
- **Procesos zombis eliminados**: 2.060

## Next Session Recommendations

- [ ] **Ola 2 (decidida por Pipe)**: lectura suficiente —recuperación adaptativa, no un tope fijo—; **guardián de citas también en proyectos**; **Panel primero** por la vía rápida
- [ ] Cerrar los **5 fallos reales de carpetas** (conteo, throttle, conservación tras `unlink`) — causa raíz aún sin identificar
- [ ] **Crear cobertura de "carpeta vinculada a un proyecto"** (hoy inexistente)
- [ ] Investigar el **error de Hook** en `frontend/app/chat/page.tsx` (`useAtajo` dentro de un callback): ¿afecta el chat en runtime?
- [ ] Arreglar el chequeo de pgvector de `scripts/setup_db.ps1`
- [ ] Diagnosticar la **causa raíz de los `statusline.js` huérfanos**
- [ ] Preparar el **encargo acotado para Cursor** (rediseño visual de panel y conocimiento)
- [ ] Rediseñar la **creación del SOUL** con las skills de referencia de Pipe (más rico, no más largo)
- [ ] Pendiente de Pipe (trámite, no código): **registrar las apps OAuth** de Gmail/Outlook/OneDrive — el código está construido y muerto sin eso
- [ ] Verificar **en vivo** todo el inc. 3 (nunca se probó con MIA corriendo)
