# Revisión final independiente Claude Code

Modelo confirmado: claude-opus-5-5. Esfuerzo solicitado: high. Solo lectura.

## Dictamen: APTO (solo por revisión estática)

Leí el código y las pruebas actuales. No ejecuté pruebas, compilación ni navegador. Los ocho hallazgos pendientes quedan cerrados en el código y no encontré regresiones que bloqueen. Lo único que no puedo confirmar es la evidencia de navegador del caso prefetch (punto 6).

## Estado de cada hallazgo

1. **Sello documental con el índice de un turno anterior: cerrado.**
   - Una cita `sellada` del expediente ahora hace que el auditor reciba todos los documentos del turno (`gate_evidence.py:44-48`), en lugar de elegir el `[doc n]` viejo.
   - Los números de los sellos antiguos ya no cuentan como dependencia (`gate_evidence.py:88`). Un `[doc n]` literal del turno actual sí cuenta.
   - Hay prueba: `test_gate_evidence.py:104-120`.
2. **Dependencias explícitas que el auditor omitía: cerrado.**
   - Las citas explícitas del texto se suman siempre a las dependencias declaradas por el auditor, y todas deben tener original disponible (`graph.py:2414-2416`).
   - Los localizadores salen de la misma lista en `build`, en `explicit_dependencies` y en `kept_sources`, así que coinciden.
   - Prueba integrada: `test_legal_context.py:134-162`. El auditor declara solo `[doc 1]` y aun así el contexto final incluye la norma.
   - Si una cita ambigua coincide con varias fuentes, no se exige ninguna como dependencia; eso respeta la política.
3. **Inventario derivado excluido sin motivo: cerrado.**
   - Los derivados siguen en la selección aunque haya citas inequívocas (`gate_evidence.py:68-69`). Así pasan a ser candidatos a exclusión y el auditor tiene que dar motivo.
   - Pruebas: `test_gate_evidence.py:68-73` y `:92-102`.
4. **Avisos sobrescritos: cerrado.** Los dos avisos ahora se concatenan (`graph.py:2441-2442`). En pantalla el salto de línea se ve como espacio (`CitationReview.tsx:438`), pero ya no se pierde texto.
5. **Bloqueo perpetuo por falta de selección previa u `origin_hash`: cerrado.**
   - Si la selección previa falta o no es válida, `plan` recibe `None` y se repite la revisión completa (`graph.py:2356-2364`).
   - Como consecuencia, el mensaje «selección auditada previa no tiene huella vigente» (`:2374-2377`) ya no se puede alcanzar. Es inocuo.
   - `origin_hash` ya entra en el manifiesto (`gate_evidence.py:104`). Las fuentes lo traen (`research.py:265`, `retrieval.py:570`), así que un cambio de metadatos fuerza una revisión completa.
   - Prueba: `test_gate_evidence.py:122-140`.
6. **Pendiente falso si el token cambia antes del envío: cerrado por lectura.**
   - `onRejected` se ejecuta antes del 401 (`api.ts:246-248`).
   - `removeMarker` usa la clave de almacenamiento de la identidad que hizo el envío y solo borra si coincide el `request_id` (`chat/page.tsx:76-89` y `463`).
   - **La evidencia de navegador no está en disco:**
     - `output/playwright/chat-recovery-prefetch-results.json` registra `passed: 0`, ningún resultado y un timeout de `page.goto` en `e2e/chat-recovery.mjs:101`. Por el orden de los archivos parece la ejecución más reciente.
     - `sol-final-validation.json:189` marca `ui_delta` como pendiente.
     - El resumen final tiene 21 casos, pero ninguno es de prefetch.
     - No encontré ningún artefacto que muestre los 2 casos prefetch aprobados.
7. **Precheck de entorno: cerrado.**
   - En modo `quick`, `verify.ps1:34-51` aplica la misma regla que `isolated_test_env.select` y, si falla, sale con código 2 y el mensaje `PRECHECK` sin ejecutar suites. Si falta `dotenv`, también termina así, en dirección segura.
   - `HANDOFF.md:19-21` documenta `MIA_TEST_ENV_FILE`.
   - Prueba: `test_gate_evidence.py:20-34`.
8. **Dobles de SAT incorrectos: cerrado.**
   - Los dobles usan `radicado` y `ratio_decidendi`, que es lo que lee `research.py:273-281`.
   - Ya hay pruebas para los hallazgos 1, 2 y 3.

## Se mantiene la política pedida

- **Al menos un original:** el final exige al menos un original, porque las dependencias no pueden estar vacías y deben tener original disponible (`graph.py:2415-2416`).
- **Derivados necesarios:** si un derivado citado no tiene original, cuenta como faltante y el auditor no llega a ser llamado.
- **Derivados ajenos:** solo se excluyen con un motivo por candidato.
- **Material ambiguo:** no se exige como dependencia.

## Observaciones que no son defectos

- Cuando hay candidatos a exclusión, se desactiva la reutilización de unidades ya auditadas (`graph.py:2362`). Solo cuesta más revisión y falla en dirección segura.
- El modo `full` no tiene el precheck de `MIA_TEST_ENV_FILE`. Ya pasaba antes y queda fuera del hallazgo 7, que era del modo `quick`.

## Lo que ejecutaron otros y yo no verifiqué

- `sol-delta-validation.json`:
  - `test_gate_evidence`: 18/18;
  - `test_gate_units`: 6/6;
  - `test_legal_context`: 4/4;
  - `tsc` y `eslint` sin errores.
- Los 21 casos de `chat-recovery-final-summary.json`.

## Límites de esta lectura

- No leí la migración 067 ni `test_gate_units.py` en esta pasada.
- No medí el presupuesto real con `full_text` completo.
- El APTO afirma que el código actual cierra los ocho defectos. No afirma que las suites pasen, ni cubre la evidencia de navegador del caso prefetch.
