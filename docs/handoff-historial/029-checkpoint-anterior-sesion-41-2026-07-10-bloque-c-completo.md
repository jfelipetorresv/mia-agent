## Checkpoint anterior: Sesión 41 (2026-07-10) — BLOQUE C COMPLETO: agentes jurídicos + perfil unificado + Configuración en subtabs — PLAN A/B/C TERMINADO

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque C — el último del plan de evolución de producto aprobado por Pipe —
con la misma orquestación multi-agente autorizada desde la sesión 38:

- **Agentes jurídicos con conocimiento propio:** las "personas" pasan a llamarse **Agentes
  jurídicos** y ahora cada agente puede tener hasta 8 guías del despacho vinculadas. Cuando el
  abogado invoca un agente, Mia prioriza ESAS guías al trabajar (en el chat del asunto y en el
  asistente). Además, "Crear con Mia" también sirve para agentes: una entrevista corta arma el
  borrador del agente (con guías sugeridas ya pre-marcadas) y NADA se guarda hasta que el abogado
  pulsa Guardar en el formulario.
- **Perfil del despacho editable y unificado:** lo que el abogado respondió al conocer a Mia ya
  se puede editar en "Mi despacho" sin repetir la entrevista (identidad, países con el mismo
  selector del inicio, áreas de práctica, tarjeta profesional, herramientas). Antes había DOS
  copias desconectadas del perfil que se desincronizaban en silencio — ahora hay UNA fuente de
  verdad y la otra se deriva sola.
- **Configuración en pestañas:** la pantalla de Configuración dejó de ser un scroll largo — ahora
  son 5 pestañas (Primeros pasos con contador, Conexiones, Carpetas, Automatizaciones, Valor y
  gasto). Todos los enlaces viejos ("Ir al paso", avisos del Panel) siguen llegando a la pestaña
  correcta.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (79 suites)** — línea base sube de 76 a 79:
  `test_agent_playbooks` 55/55, `test_profile_full` 51/51, `test_config_tabs` 14/14.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial con 4 revisores independientes + refutación por hallazgo** —
  5 hallazgos MENORES confirmados (0 mayores, 0 bloqueantes; seguridad/RLS sin hallazgos), TODOS
  corregidos y re-verificados antes del commit: el presupuesto del material de guías podía
  pasarse por unos caracteres; guardar el perfil podía borrar en silencio datos guardados por la
  pantalla vieja; una guía archivada ocupaba cupo invisible en el formulario del agente; un error
  crudo del servidor podía mostrársele al abogado; código muerto. Detalle en `memory/progress.md`
  sesión 41. (De paso, el ejecutor del perfil atrapó un bug latente que habría borrado ajustes
  del despacho en cada guardado.)
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Agentes jurídicos** (antes "Personas"): abrir un agente, vincularle 2-3 guías en
   "Guías vinculadas" (ver el contador "N de 8"), guardar; luego en un asunto invocarlo
   ("actúa como litigante...") y confirmar que trabaja normal.
2. **"Crear con Mia"** en Agentes jurídicos: responder la entrevista (3-6 preguntas), ver que el
   formulario queda precargado (con guías sugeridas marcadas), CANCELAR a mitad de camino y
   verificar que NO quedó ningún agente creado; repetir y esta vez Guardar.
3. En **Conocimiento → Mi despacho**: editar el perfil (países con el selector, áreas,
   herramientas), Guardar y leer el resumen "Así entendí a tu despacho".
4. En **Configuración**: navegar las 5 pestañas; desde el Panel usar un enlace de "tope de gasto"
   (debe abrir directo la pestaña "Valor y gasto") y un "Ir al paso" del recorrido (pestaña
   correcta). Probar entrar directo a `http://localhost:3100/configurar#carpetas`.
5. Sigue pendiente la capa 3 arrastrada de los Bloques A y B (sesiones 39-40) — nada de eso
   cambió en esta sesión.

### Pendientes y próximo paso

1. **El plan A/B/C quedó COMPLETO.** La próxima sesión arranca definiendo con Pipe el siguiente
   objetivo de producto (candidatos naturales: capa 3 acumulada, activación OAuth, o el
   siguiente frente que Pipe priorice).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: carpetas vinculadas POR AGENTE pospuesto a v2; las 3 personas canónicas de
   fábrica vienen sin guías pre-vinculadas; crear un agente con guías inválidas lo crea SIN
   vínculos y avisa en llano (decisión documentada).

### Trabajo en background sin leer

Nada — los 3 workflows (recon, ejecución, capa 2) y las 2 regresiones se leyeron y quedaron
reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **"soul_responses" es un nombre lógico, no una tabla nueva:** la fuente canónica del perfil
  sigue siendo el archivo por despacho en disco (diseño local-first existente); la tabla
  `firm_profiles` pasa a ser derivada y ya no puede pisar en silencio lo canónico.
- El material de las guías de un agente entra al prompt como REFERENCIA después de las reglas
  duras (método y citación) y de la voz — nunca dentro del rol; el presupuesto es duro (≤16k)
  y la regla [VERIFICAR] manda siempre.
- "Modo profundo" (p19) NO se muestra en el perfil editable (coherente con el onboarding, que
  también la oculta — Riesgo #27).
- El renombre "Personas jurídicas" → "Agentes jurídicos" es SOLO visible: la ruta `/personas` y
  la API no cambian (cero riesgo de romper enlaces o integraciones).

---

