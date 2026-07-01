# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP0 — Estabilidad de plataforma (2026-07-01)

### Qué cambió (lenguaje simple)

- LiteLLM (la pieza que conecta a Mia con los modelos de IA) ahora corre
  en su propio entorno separado, de modo que reinstalarlo o reiniciarlo
  nunca vuelva a romper a Mia.
- Se corrigió la documentación del proyecto: rutas viejas actualizadas a
  la ubicación real ("D:\Codex\Mia-Super Agent") y se documentó la regla
  del entorno separado de LiteLLM en las notas de arquitectura.

### Frontend a revisar

- Ninguno en este checkpoint. No hubo cambios visibles en pantalla.

### Comportamiento esperado

- Los 3 procesos (litellm / uvicorn / npm run dev) arrancan sin errores
  y el chat responde igual que antes.

### Bugs conocidos / fuera de alcance

- El frontend está 16 días rezagado respecto al backend — se sincroniza
  en CP5/CP7. No es parte de este checkpoint.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): VERDE — regresión completa 32/32 suites PASS
  (test_rls 12/12 HALT PASS) + gate nuevo check_env_pins.py 9/9 PASS,
  cableado a start_api.ps1 y run_tests.ps1. Prueba en vivo: LiteLLM
  arrancó desde su entorno separado, el API arrancó con el gate de
  versiones, y un turno jurídico completo funcionó de punta a punta
  (pregunta → análisis → borrador con citas correctas → aprobación →
  finalización). Nota: la prueba en vivo usó claude-sonnet temporalmente
  (la clave de Anthropic volvió a funcionar); el modelo por defecto del
  .env no se cambió — eso es CP2.
- Capa 2 (subagente revisor independiente): ejecutada. 3 hallazgos
  mayores, TODOS corregidos antes del commit: (1) start_all.ps1 fallaba
  con rutas con espacios → comillas explícitas; (2) el gate de versiones
  no estaba conectado a ningún flujo → ahora aborta arranque y regresión;
  (3) websockets había quedado degradada (13.1) → restaurada a 15.0.1,
  pineada y cubierta por el gate. Menores: Riesgo #32 cerrado en
  bugs-and-risks.md. Esta revisión es por lectura de patrones conocidos,
  no una auditoría con herramientas de escaneo.
- Capa 3 (revisión visual de Cursor): no aplica — CP0 no tocó frontend;
  Cursor confirma en la sección siguiente.

---

## Hallazgos de Cursor (capa 3)

(Vacío. Cursor: escribe aquí tus hallazgos de la revisión visual —
diseño de interfaz, accesibilidad, consistencia de UX y superficies de
seguridad visibles en frontend. Si no hay frontend que revisar en el
checkpoint, déjalo indicado explícitamente.)
