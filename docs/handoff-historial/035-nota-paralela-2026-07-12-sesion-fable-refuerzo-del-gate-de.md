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

