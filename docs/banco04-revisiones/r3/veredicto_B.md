**Veredicto del área B: NO APTO.** Revisado HEAD `f5d678b`. Hay correcciones efectivas, pero persisten controles incompletos de cuota y vías reproducibles de aprobación sin evidencia suficiente.

**Seguimiento de cada ítem de la ronda 2**

- **I4 — RESUELTA para el defecto señalado.** Todos los alias CLI quedan sin cota; los jueces ya no fabrican una genérica. Evidencia: [spend_guard.py:1107](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/spend_guard.py:1107>) y [jueces.py:1354](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1354>). Cobertura: **R2-B-I4**, producción `i-1`, `i-3` y juicio `gate_r2_b`. Sondas propias confirmaron `None` para Claude y Codex. Esto no acredita como cota la entrada estimada de otras rutas.

- **I5 — PARCIAL.** Se bloquean nuevos jueces tras consumo desconocido, se impide Codex de producción en Bloque 0 y se proyecta Codex al decidir R. Cobertura: **R2-B-I5** de ambas suites. Persisten:
  1. **C19 incumplida:** [run_banco04.py:436](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:436>) permite Codex de producción con `cota_calculable=False`. Reproduje ambos permisos: llamada y siguiente corrida. El guardián tampoco consulta fallidos en curso (`:1590`). **Cambio:** bloquear ante consumo desconocido, incluido el pendiente de trasladar al contador.
  2. [banco04_validar_jueces.py:625](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:625>) acepta `versiones=("0.4","INEXISTENTE")`: exige dos nombres, no las dos versiones reales. Puede excluir el consumo de 0.3.3. **Cambio:** exigir el conjunto exacto y acreditar sus registros.
  3. El montaje deja vacía la estimación Codex de piloto ([run_banco04.py:1799](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:1799>)); `:1095` la convierte en cero. **Cambio:** proporcionar una estimación acreditada antes de lanzar. El check R2-B-I5 sobre piloto prueba una configuración inyectada, no este montaje.

- **I8 — RESUELTA.** Los mensajes de excepción reservados se cifran mediante [run_banco04.py:824](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:824>), invocado en producción (`:1013`) y aprobaciones (`:1409`). Cobertura: **R2-B-I8**. La sonda con un hecho reservado sintético dejó fuera del registro claro el texto del error; el cifrador fue un doble, no se probó criptografía real.

- **I10 — RESUELTA en las rutas revisadas.** [run_banco04.py:769](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:769>) incorpora los ocho tipos reutilizables; se cotejan al arrancar y en las rutas individuales de intentos, aprobaciones y decisión R. Cobertura: **R2-B-I10**. La sonda rechazó una huella antigua bajo contexto nuevo.

- **N1 — RESUELTA en jueces.** [jueces.py:1377](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1377>) exige entrada y salida válidas. Ejecuté los cuatro checks puros **R2-B-N1** sobre telemetría parcial, valores inválidos y controles completos. Subsiste un defecto equivalente en producción: R3-N2.

- **N2 — RESUELTA.** [run_banco04.py:746](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:746>) genera la causa de no certificabilidad para árbol sucio, incorporada en producción y aprobaciones; `:701` distingue modificaciones locales mediante huella. Cobertura: **R2-B-N2**. Sondas positiva y negativa satisfactorias.

**Objeciones nuevas y efectos de las correcciones**

**R3-N1 — BLOQUEANTE. El límite declarado admite aprobación con filas inconsistentes.** En [metricas.py:1172](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:1172>) los absolutos se aceptan sin recalcular; `:1234` confía igualmente en la atribución. Un segundo contexto reprodujo:

- Introducir una afirmación sin respaldo conservando absolutos anteriores → **`aprueba`**; recalcularlos → `reprueba`.
- Consumo 100→120 sin atribución → `reprueba`; cambiar únicamente `cumple=True` en esa fila → **`aprueba`**.

Cotejé las puertas originales. Los checks R2-A-I1/I2 no cubren esta desincronización. **Cambio:** recalcular absolutos, decisivos y atribución dentro del veredicto; rechazar evidencia ausente o contradictoria.

**R3-N2 — BLOQUEANTE. Producción sigue convirtiendo telemetría parcial en cero conocido.** [spend_guard.py:961](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/spend_guard.py:961>) rellena componentes ausentes con cero; `:1268–1274` registra éxito sin marcar consumo desconocido. Sonda del recorrido con respuesta sintética parcial: **una llamada, cero tokens conocidos, ningún fallido y `cota_calculable=True`**. Contradice C18. **Cambio:** aplicar también aquí validación de completitud y propagar incertidumbre. R2-B-N1 solo protege jueces.

**R3-N3 — MAYOR. La nueva puerta confunde consumo calculable con presupuesto cumplido.** [banco04_validar_jueces.py:329](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:329>) solo exige `cota_calculable=True`. Reproduje **`circuito_utilizable=True` con 33 M Claude/8,1 M Codex**, frente a techos 32 M/8 M. La última llamada puede superar la reserva estimada sin otra llamada que active el bloqueo. **Cambio:** comprobar acumulados y suspensión al cerrar; añadir check R2-B-I5 negativo.

**C18–C26 y límites:** C18 endurece correctamente los CLI, pero producción incumple su regla de telemetría; C19/C20 tienen los huecos descritos. C24/C25 no quedan garantizadas por la puerta. El primer límite final de [§12.6:1357](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md:1357>) permite hoy `aprueba` sin acreditar y contradice §6.4: **declararlo no autoriza la excepción**.

Verificación: cuatro checks existentes y siete controles propios satisfactorios, más sondas adversariales; revisión independiente de límites e I5. Sin suites completas, proveedores, bases, escrituras ni acceso a datos prohibidos.