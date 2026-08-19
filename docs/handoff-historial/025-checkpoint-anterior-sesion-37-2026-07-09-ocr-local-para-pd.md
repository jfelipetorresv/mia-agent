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

