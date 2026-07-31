# CIERRE — 2026-07-27/28 (4ª sesión) · SESIÓN PIPE A EJECUTADA: F2 cerrada + 4 barreras del harness

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada,
> arráncala: `tools\postgres16-portable\pgsql\bin\pg_ctl.exe -D tools\pgdata-portable -l
> tools\pg_start.log -o "-p 55432" start` (el `pg_ctl` no devuelve el prompt pero el motor
> arranca — comprobar con `pg_isready` o conectando). **La Sesión Pipe A YA SE HIZO**: las 7
> decisiones están en `memory/decisions.md` #45/#46/#47 y **F2 está CERRADA** (`memory/findings.md`
> §CIERRE DE F2). **Antes de comparar cualquier cifra con el pasado, leer los TRES CORTES DE SERIE
> de esa sección**: fuga (N-1), abstención (M-1) y `prompt_hash` (`3391f17ea61324a4` →
> `8388c516a2156de2`), más el cambio de composición del examen (los casos de RIESGO entran por
> defecto: 3 → 9). Lo que sigue está en «Qué sigue» abajo; lo único que espera a Pipe es la
> lectura de calidad de las 6 salidas y los dos trámites de terceros
> (`docs/tramites-terceros-pipe.md`).

Rama `feat/fase1-inc1-cleanup-scaffolding`. Pusheado hasta el commit de esta entrada.

## Qué pasó en esta sesión (2026-07-27/28, 4ª)

1. **La Sesión Pipe A se ejecutó completa** (salvo la lectura de calidad, que es juicio suyo).
   Siete decisiones tomadas en vivo, registradas en `memory/decisions.md` #45, #46 y #47.
2. **Las tres decisiones de medición, aplicadas y verificadas** (`656dc20`):
   - **N-1**: la regla del muro es «no afirmar una norma como aplicable sin respaldo», NO «no
     escribir jamás el número». Mención + negación explícita en la misma oración ya no es fuga.
     **Fuga real 0/63** recalculando los crudos guardados; el falso positivo de «Ley 4137»
     desaparece y ninguna cita realmente usada se escapa (checks G1-G9).
   - **M-1**: `ABSTENTION_PHRASES` recalibrado MIDIENDO los 62 borradores (11 → 46 formas).
     Cobertura 29/29 en suscripción (antes 0/30), 30/33 en nube. **Corte de serie declarado** —
     Pipe eligió declararlo en vez de pagar un re-baseline.
   - **M-2**: fuera «Éxito de tarea»; ahora «Turnos completados» + «Se negó correctamente» en los
     casos de RIESGO (10/10 nube, 9/9 suscripción sobre las sondas ya corridas).
3. **Las CUATRO barreras del harness de litigio de Pipe, portadas** (`99fb4a2`, `ba1fbde`,
   `ae42b96`). Decisión de dureza suya: **nacen como AVISO y solo suben a muro si se mide que no
   bloquean trabajo bueno**; el banco de citas quemadas es la única excepción (muro día uno).
   - **Afirmaciones negativas** verificadas contra el documento COMPLETO (no el fragmento ni el
     resumen de un extractor) + `retrieval.document_full_text` + regla y corolario en el prompt.
   - **Banco de citas quemadas** (migración **047**, tabla `burned_citations` con RLS): la cita
     que el abogado marca como falsa no vuelve a emitirse **ni con respaldo del corpus** — el muro
     va antes de toda vía de respaldo, que es como se coló el defecto original.
   - **Contaminación entre expedientes**: partes de OTRO asunto nombradas en el escrito. Catálogo
     DERIVADO de `documents.parte` del propio despacho — cero listas cableadas, agnóstico.
   - **Ninguna lección sin barrera**: regla de trabajo (reglas 55-61 de `APRENDIZAJES.md`).
4. **F2 CERRADA y alcance de la v1 ajustado** (#47): los casos de RIESGO entran al examen por
   defecto (`load_golden_cases` los incluye; el examen pasa de 3 a 9 casos y
   `test_gold_cases_influence_eval` ya deriva el número en vez de cablearlo), el «Modo A»
   (Docker/servidor) queda FUERA de la v1, y **los USD 22,6 del tope de nube quedan sin gastar**.
5. **Riesgo #81 CERRADO** con criterio + barrera (las tres partes: N-1, M-1, M-2).
6. Verificación en tres capas en cada bloque: unitaria (4 barreras nuevas: 27/27, 20/20, 17/17,
   18/18), independiente (`test_eval_harness` 67/67 con DB, panel 50/50, substance 51/51,
   sentence_report 47/47, mutación 50/50, omission 26/26, agnostic 104/104, META C 11/11) y en
   vivo (recálculo de los 63 crudos; ciclo real del muro contra la base con RLS entre dos
   despachos: `execution/test_citas_quemadas_db.py`). Gates HALT verdes: `test_rls` 19/19,
   `test_gates_no_ciegos` 9/9.

## Qué sigue (en orden)

1. **Helper de siembra para verificación visual** (`execution/seed_despacho_demo.py`, no existe):
   un despacho de prueba CON PERFIL, para poder capturar pantallas sin correr la entrevista.
   Motivo: el gate de bienvenida no se salta con `setup/steps/perfil/skip` (devuelve 200 pero
   mira si el perfil existe), así que hoy toda captura de UI cuesta 20 minutos de andamiaje y
   quedó SIN verificación visual el botón de marcar cita falsa y los dos avisos nuevos de la
   pantalla de revisión (regla 62 de `APRENDIZAJES.md`). El andamiaje que sí quedó listo: venv
   con Playwright y script de captura en el scratchpad de la sesión.
2. ~~Alta del banco de citas quemadas desde la interfaz~~ **HECHA** (`2c7ff04`): endpoint
   `/api/citas-quemadas` (POST/GET/DELETE, 18/18 con RLS por HTTP) + enlace «Esta cita no existe
   o no dice eso» en el diálogo de cada cita, y los avisos de afirmaciones negativas y
   contaminación entre expedientes ya se pintan.
2. **Caso de oro con expediente GRANDE** (cientos de fragmentos): sigue siendo el prerrequisito
   para decidir «lectura agéntica por defecto» (N-2). No requiere aprobación.
3. **Mostrar los avisos nuevos en la pantalla**: `afirmaciones_negativas` y
   `contaminacion_expediente` viajan en el informe de verificación y todavía no se pintan.
4. Producto (plan maestro): instalador y bienvenida de F3.

## Pendientes de Pipe

- **Lectura de calidad** de las 6 salidas de `docs/f1-paquete-decision-pipe.md` y del ejemplar
  `f2sond_entail_g`. Ningún agente lo sustituye.
- **Los dos trámites de terceros**, que decidió disparar: Azure Trusted Signing (firma de Windows)
  y registro de apps OAuth (Google/Microsoft). Pasos en `docs/tramites-terceros-pipe.md`.

---
