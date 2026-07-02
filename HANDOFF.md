# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP2 — Motor de modelos por suscripción (2026-07-01)

### Qué cambió (lenguaje simple)

- Mia ahora puede pensar usando la suscripción de Claude del abogado,
  sin costo por consumo: cada respuesta se carga a la suscripción que
  el despacho ya paga, no a una cuenta de API por token.
- Cada despacho elige su modo de trabajo entre tres opciones:
  "Mi suscripción" (recomendado), "Nube" o "Todo en mi equipo".
- El respaldo local quedó restaurado con un modelo pequeño: si la
  suscripción y la nube fallan, Mia sigue respondiendo desde el propio
  equipo del abogado.
- Tras la revisión independiente se blindó la conexión con la
  suscripción: Mia ya no comparte sus claves ni secretos con el
  programa externo, y solo ejecuta el programa auténtico (nunca un
  sustituto que pudiera manipularse).

### Frontend a revisar

- Ninguno aún — el selector visual del modo de modelo llega en CP7.

### Comportamiento esperado

- Con "Mi suscripción" activo, Mia responde igual que siempre pero el
  consumo va contra la suscripción de Claude del abogado. Si la
  suscripción no está disponible, Mia pasa sola a la nube y luego al
  respaldo local, sin que el abogado note el cambio ni pierda el turno.

### Bugs conocidos / fuera de alcance

- El alias "haiku" (modelo pequeño para tareas auxiliares) puede ser
  atendido por otro modelo pequeño de la suscripción — el proveedor
  decide cuál responde; no afecta el resultado visible.
- Riesgo #34 anotado: con varios procesos del servidor, un cambio de
  modo puede tardar hasta ~60 segundos en aplicar en todos (hoy, con un
  solo proceso, aplica de inmediato); y si el programa de la
  suscripción se cuelga, un turno puede quedar retenido unos minutos
  antes de saltar al siguiente proveedor.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): VERDE — regresión completa 33/33 suites PASS
  (incluye test_rls 12/12 HALT PASS, el gate nuevo test_model_policy.py
  40/40, test_llm_fallback 25/25 y test_curator 24/24; las 4 suites que
  esperaban el contrato viejo de modelos fueron actualizadas al nuevo).
  Gate en vivo del turno completo por suscripción: 176 segundos de
  pregunta a borrador, borrador de 19.098 caracteres con citas correctas
  (fuero de maternidad, art. 239 CST) y 47 marcadores [VERIFICAR]; el
  proxy no registró ninguna llamada por API — todo fue por suscripción.
  Se corrigieron en vivo dos problemas de calidad: la personalidad
  concisa del programa de la suscripción producía borradores diminutos
  (148 caracteres) y su modelo por defecto tardaba más de 5 minutos —
  ahora Mia le impone su propia personalidad jurídica y usa el modelo
  rápido de alta calidad (configurable).
- Capa 2 (subagente revisor independiente): revisor independiente
  ejecutado: 2 mayores corregidos (aislamiento de credenciales del
  subproceso, blindaje de ejecutable), 5 menores corregidos/anotados;
  revisión por lectura de patrones, no auditoría con herramientas.
- Capa 3 (revisión visual de Cursor): no aplica — CP2 no tocó frontend;
  Cursor confirma en la sección siguiente.

---

## Hallazgos de Cursor (capa 3)

(Vacío. Cursor: escribe aquí tus hallazgos de la revisión visual —
diseño de interfaz, accesibilidad, consistencia de UX y superficies de
seguridad visibles en frontend. Si no hay frontend que revisar en el
checkpoint, déjalo indicado explícitamente.)
