## Checkpoint anterior: Sesión 38 (2026-07-09) — Cáscara de escritorio + rediseño onboarding/panel + rebrand visual + PLAN APROBADO de evolución de producto

### Qué se hizo esta sesión (retoma post-apagón, todo en `origin/main`)

- **Cáscara de escritorio Tauri (Fase 4 · bloque 2)** — `35b3a96`: la app que el abogado abre
  y enciende/apaga todo (DB→backend→frontend). E2E de 5 ciclos + Job Object anti-huérfanos
  verificado con crash simulado. Revisión adversarial: 2 mayores + 5 menores corregidos.
- **Onboarding rediseñado** — `46db38c`: 8 preguntas (fuera estilo/límites/ritmo — el estilo
  se aprende del flywheel), UNA pregunta de país con 21 países multi-select, ejemplos sin
  Lexia. e2e 32/32, second_brain_ui 26/26.
- **Panel/Configuración reestructurados** — `0d5e826`: el Panel solo con lo accionable
  (Para tu decisión + recordatorios + recomendaciones + Este mes); Configuración absorbe
  conexiones/carpetas/automatizaciones/valor. Guía OAuth en `docs/guia-conectar-correo-y-nube.md`.
- **Rebrand visual completo** — `13f0d55`: paleta Lexia (teal/negro/degradé verde), sidebar
  negra con wordmark MIA (I en teal), Archivo+Hind, aurora teal, card-depth. Pipe lo vio en
  vivo y le gustó ("me gusta lo que estoy viendo").

### PRÓXIMA SESIÓN: ejecutar el plan de evolución de producto (APROBADO por Pipe)

> **AUTORIZACIÓN EXPRESA DE PIPE (2026-07-09, en sus palabras):** ejecutar el plan
> **usando workflows de orquestación multi-agente desde el arranque, a velocidad
> máxima**. Es decir: al retomar con /arranque, usar el tool Workflow (fan-out de
> ejecutores en paralelo sobre partes disjuntas del Bloque A + verificación
> adversarial multi-agente) sin volver a pedirle permiso. Los límites NO cambian:
> verificación de 3 capas antes del cierre, gate HITL innegociable, HALT si
> test_rls falla, y capa 3 visual sigue siendo de Pipe.

**El plan completo vive en `memory/plan-evolucion-producto.md`** (misma copia en
`C:\Users\USER\.claude\plans\chad-me-gusta-lo-memoized-token.md`). Resumen:
- **Bloque A (EMPEZAR AQUÍ):** pestaña "Proyectos" estilo Claude Cowork (reusa `matters`
  con `kind`), selector visual de carpetas del equipo (fin de rutas pegadas a mano),
  multi-carpeta por asunto (⚠️ PRIMERO `documents.source_id` — hay bug latente de poda
  cruzada documentado en el plan), panel "Fuentes" unificado.
- **Bloque B:** "Crear guía con Mia" (entrevista stateless con gate HITL por construcción),
  CRUD+versiones de playbooks, gobernanza de skills aprendidas (fusionar subtabs).
- **Bloque C:** Personas → "Agentes jurídicos" con conocimiento vinculado, perfil del
  despacho editable (SOUL como fuente canónica, `/api/profile/full`), Configuración en subtabs.
- Decisiones de Pipe: todo en orden A→B→C, un bloque por sesión; Proyectos y Asuntos como
  pestañas SEPARADAS. Verificación 3 capas por bloque; gate HITL innegociable.

**Pendientes de Pipe (sin cambio):** registrar apps OAuth (guía en docs/), capa 3 en vivo
de sesiones 35-36 y del onboarding/panel/rebrand nuevos.

---

