# Bitácora de feedback UX/diseño — 2026-08-19 (sesión 46)

> **Origen:** Pipe instaló el instalador `Mia_0.3.0_x64-setup.exe` (construido en esta
> misma sesión, cierre de F4) y lo usó por primera vez de punta a punta. Dejó 23
> observaciones sobre diseño, redundancia y funciones que no sirven. Este documento es
> la bitácora completa: **causa raíz verificada en el código** + solución propuesta +
> decisión de Pipe cuando la hubo.
>
> **Cómo usar este archivo:** es la fuente de verdad del bloque de trabajo UX que
> sigue. Leerlo junto con `HANDOFF.md` al abrir sesión nueva. Cada punto tiene su
> archivo y línea; no hace falta re-explorar.

---

## 0 · CORRECCIÓN CRÍTICA sobre el diseño canónico (leer primero)

En esta sesión **me equivoqué al caracterizar el diseño**, le presenté a Pipe una
opción mal descrita, él la eligió sobre esa premisa falsa, y luego lo detectó:
*"no, ese no es el diseño que habíamos establecido. Además era claro"*. Queda
corregido así:

- **El diseño canónico ES:** "MIA Onboarding Unificado" — **Neumorfismo Pro, paleta
  Teal / Azul Oxígeno, en tema CLARO y oscuro**, elevación `shadow-neu-raised`, inputs
  incrustados `shadow-neu-sunken`, fondo `bg-mesh-living`, elementos 3D cristalizados
  `animate-float`. Está declarado en `CLAUDE.md` §I y es lo que **ya está implementado**
  en `frontend/app/globals.css` (commit `f52c945`, hecho con Antigravity el 3 ago).
- **NO es** una paleta dorada/cristal. Yo describí `frontend_design_spec.md` como
  "dorado/lujo" y eso llevó a una decisión equivocada (la anulo abajo).
- **El commit de diseño más reciente** (`ef3ed33`, 4 ago, "paleta monocromática negro/
  platino/cristal + isotipo octaedro 3D") **solo modificó `BrandMark.tsx`** — un archivo,
  el logo. Verificado con `git show --stat`. Nunca tocó ninguna pantalla. Por eso Pipe
  recuerda un diseño "último" que no ve aplicado: **nunca se aplicó más allá del logo**.
- **Las imágenes de referencia** que menciona la spec (`mia_onboarding_unified_*.jpg`)
  **no están en el repo ni en el disco** — quedaron en la sesión de Antigravity. Pipe
  las tiene en otro computador y las va a traer.

**⚠️ D1 QUEDA ANULADA.** La decisión original registrada ("implementar la spec de lujo
dorado/cristal") se tomó sobre mi descripción errónea. **No implementar nada dorado.**
El rumbo correcto es: consolidar y terminar de aplicar el neumorfismo teal claro/oscuro
que ya existe, y cotejarlo contra las imágenes de Antigravity cuando Pipe las traiga.

---

## 1 · Decisiones tomadas por Pipe

| # | Decisión | Estado |
|---|---|---|
| ~~D1~~ | ~~Diseño canónico = spec dorado/cristal~~ | **ANULADA** — ver §0. El canónico es neumorfismo teal claro/oscuro (`CLAUDE.md` §I) |
| D2 | Onboarding y sidebar deben seguir el selector de tema del abogado, no forzar oscuro | ✅ **HECHO** para la bienvenida (commit `10d447e`). Sidebar pendiente |
| D3 | Fusionar "Asuntos" + "Proyectos" en un solo concepto **"Casos"**, con control por caso de si Mia entrega borrador para aprobar o responde directo | Pendiente |
| D4 | **Un solo motor de IA activo** a la vez + respaldo automático si falla. Nunca dos en paralelo. OpenRouter = respaldo bien explicado, no "motor #7" | Pendiente. El backend ya funciona así (`agent/llm.py`, política única) — es solo simplificar la UI |
| D5 | El bug de Protección es **real** (Pipe probó con la app instalada, no en navegador) | ✅ **ARREGLADO** (commit `0a0f020`), falta verificar en app empaquetada |
| D6 | Lista de "qué no debo hacer nunca": se le propone un borrador de prohibiciones típicas de litigio/seguros y él lo edita | Pendiente |
| D7 | Atajos: solo poder **fijar/ocultar** de la lista automática. Sin constructor de atajos libres | Pendiente |
| D8 | Diseñador de agentes: agregar 3 casillas de capacidad — leer imágenes/diagramas/escaneados, investigación web/jurisprudencia en vivo, generar documentos largos formateados | Pendiente |
| D9 | Número de registro profesional: se mueve a Configuración → perfil del despacho. Fuera del onboarding | Pendiente |
| D10 | Jurisdicción: un solo selector multi-país. Se elimina la pregunta separada de "reglas de otro país" | Pendiente |
| D11 | `os-coach`: investigado, ver §3 | ✅ Investigado |

---

## 2 · Los 23 puntos, con causa raíz y solución

| # | Observación de Pipe | Causa raíz (verificada) | Solución |
|---|---|---|---|
| 1 | "El diseño claro que elegimos no lo estoy viendo… hay uno último que establecimos que no veo aplicado" | **Dos causas.** (a) `WelcomeShell.tsx:52` forzaba `dark` + `bg-[#060606]` cableado → login/registro/activar/onboarding SIEMPRE negros aunque el tema fuera claro. (b) El último commit de diseño solo cambió el logo (§0) | (a) ✅ **ARREGLADO** (`10d447e`): usa `bg-background` + tokens del tema. Viñeta negra fija → utilidad `bg-vignette-welcome` por tema. Verificado con capturas en claro y oscuro. (b) Cotejar con las imágenes de Antigravity cuando lleguen |
| 2 | Selección de motor redundante y confusa | `app/activar/page.tsx:560-663` — 6 tarjetas compitiendo en un `radiogroup`; "En la nube" y "OpenRouter" parecen motores separados cuando OpenRouter es respaldo. La autodetección (`GET /api/welcome/status` → `motor_detectado`) solo pinta una etiqueta "Ya detecté X", **no preselecciona nada** | D4: un paso único → detectar qué hay instalado (Claude Code/Codex/Ollama), preseleccionar el detectado, elegir UNO como principal. OpenRouter en su propia sección de respaldo |
| 3 | "Pega tu clave" no se entiende; lo de respaldo del motor tampoco | `activar/page.tsx:665-822`, dos pantallas separadas sin explicar qué activa cada clave. Clave de búsqueda = `VOYAGE_API_KEY` (embeddings, sin ella no hay búsqueda). Clave de respaldo = `ANTHROPIC_API_KEY` (es el motor PRINCIPAL si la política es "nube", si no es respaldo puro) | Fusionar en UNA pantalla "Claves", mostrando **solo las que apliquen** según el motor elegido, con copy explícito de qué habilita cada una y qué pasa si se omite |
| 4 | Explicar mejor OpenRouter | `activar/page.tsx:824-934`. Además al guardarla activa `allow_openrouter: true` (opt-in de confidencialidad) sin explicarlo | Copy nuevo: qué es, que solo entra si el principal falla, que el gasto lo paga el abogado, y que implica sacar datos a un tercero |
| 5 | La pregunta del despacho es redundante con el registro de cuenta | `onboarding/page.tsx:759-773` (pregunta `p1`). **Falta confirmar** si `app/register/page.tsx` ya pide el nombre de la firma | Si `/register` ya lo pide → precargar y no volver a preguntar |
| 6 | No pedir registro profesional aquí | Mismo campo; el placeholder pide "número de registro profesional 000.000" | D9: mover a Configuración → perfil del despacho |
| 7 | El ejemplo de país está mal ("ej: ais") | `onboarding/page.tsx:782-798` — los placeholders son literalmente **la plantilla sin rellenar**: `"Ej: tu país"` / `"Ej: tu ciudad"`. En el backend el ejemplo de `p2` es el genérico `"Ciudad, País"` (`soul_interview.py:77-79`) | Poner ejemplos concretos: "Ej: Colombia" / "Ej: Bogotá" |
| 8 | La pregunta de ciudad no es relevante | Mismo campo que #7 | Eliminar el campo Ciudad; dejar solo país/jurisdicción |
| 9 | Suprimir "reglas de otro país", ya se eligen varios países antes | `onboarding/page.tsx:229-238` (`_jurisdiction`, paso insertado solo en el frontend, usa `CountrySelector.tsx`) | D10: un solo selector multi-país; eliminar la pregunta separada |
| 10 | Suprimirla también porque Mia ya tiene reglas y memoria propia | Igual que #9 | D10 |
| 11 | Ampliar "qué no debo hacer nunca" con genéricos de la industria | `soul_interview.py:99-101`. Chips actuales: citar sin verificar, afirmar hechos fuera del expediente, enviar al cliente sin revisión, prometer un resultado | D6: proponer borrador (confidencialidad, conflictos de interés, plazos, no dar consejo fuera de competencia…) para que Pipe lo edite |
| 12 | Suprimir "¿cuándo das un escrito por terminado?" | `soul_interview.py:102-104` (`p22`) | Eliminar. Precedente: ya se eliminaron `p3`, `p4`, `p18`, `p19` por lo mismo (documentado en `soul_interview.py:27-44`) |
| 13 | ¿Sirve el skill `promptadvisers/os-coach` para el onboarding? | Investigado (§3) | Usar su patrón de flujo como inspiración, no el repo tal cual |
| 14 | **Los botones de Configuración no sirven** | **Bug real, causa raíz encontrada:** `lib.rs:~1400` navega la ventana a `http://localhost:3100`, que para Tauri v2 es **origen remoto**; por endurecimiento deliberado (sin capability `remote`, sin `dangerousRemoteUrlIpcAccess`) los orígenes remotos **no reciben IPC**, así que `window.__TAURI__` nunca existe ahí. Toda la pestaña Protección estaba muerta desde siempre, y `restart_litellm` de `/activar` también | ✅ **ARREGLADO** (`0a0f020`) **sin debilitar la seguridad**: puente por esquema URI propio `mia-shell` interceptado en proceso por WebView2 (sin puerto TCP, inalcanzable desde otro programa o la LAN), con allowlist de `Origin` exacta, solo POST y rutas cerradas. Nuevo `frontend/lib/shell.ts`. **Falta verificar en la app empaquetada** |
| 14b | Leftover de la misma causa | `RuntimeHealthBanner` sigue usando `__TAURI__.event.listen` → también muerto en la app empaquetada | Migrar al mismo puente. **Tarea abierta** |
| 15 | "Qué hace cada sección de MIA" debe ser su propia pestaña con manual para dummies | Hoy es un acordeón `<details>` dentro de Configuración → "Primeros pasos" (`configurar/page.tsx:424-448`). Los datos son estáticos: `MIA_SECTIONS` en `backend/mia/api/routes/setup.py:169-199` (6 entradas: titulo/que_es/para_que) | Promover a ruta propia `/ayuda` con manual completo. Los datos ya existen — reusar `MIA_SECTIONS` y enriquecerla |
| 15b | "Apariencia" y "Cerrar sesión" perdidos abajo | `Sidebar.tsx:91-97` — dos botones `variant="ghost" size="sm"` idénticos al final de la lista, sin jerarquía. **Ironía:** el panel que contiene el selector de tema está él mismo forzado a oscuro | Rediseñar con separación e iconos con peso, al quitar el `.dark` forzado del sidebar (D2, pendiente) |
| 16 | El panel del despacho no es amigable ni tiene el diseño acordado | `dashboard/page.tsx` (965 líneas) — es una **lista vertical** de secciones (Tope de gasto → Para tu decisión → Al día → Recordatorios → Guías → Este mes), no el layout de tarjetas tipo Bento que describe la spec §2 | Implementar el dashboard de tarjetas del diseño canónico (neumorfismo teal, NO dorado) |
| 17 | Configuración necesita mejor UX y ser más directo | `configurar/page.tsx` (564 líneas) + 7 secciones. Nota: `ProteccionDatosSection` además cablea `border-border bg-card shadow-sm` en vez de usar el primitivo `<Card>`, así que ni sigue el sistema | Aplicar el sistema de diseño de forma consistente; usar `<Card>` en todas partes; simplificar jerarquía |
| 18 | Los atajos deberían poder editarse/agregarse/quitarse | `chat/page.tsx` + `backend/mia/memory/atajos.py`. Se derivan solos de guías activas + `summon_phrases` de personas, `MAX_SHORTCUTS = 6` con 2 reservados para agentes. **No hay tabla, ni endpoint CRUD, ni pantalla** — para cambiarlos hay que ir a editar una guía o una persona | D7: control para fijar/ocultar, manteniendo la derivación automática |
| 19 | Hablemos de "casos"/"proyectos" en vez de "asuntos" | — | D3 |
| 20 | ¿Asuntos y Proyectos son redundantes? | **Sí, son la misma tabla.** `matters` con columna `kind CHECK (kind IN ('asunto','proyecto'))` (migración `028_projects_multifolder.sql:39-53`). Única diferencia real: en asunto hay borrador con aprobación (HITL), en proyecto Mia responde directo. Todo lo demás es idéntico. Aparecen como dos ítems separados en `nav.ts:29-30` | D3: fusionar en "Casos" con un control de comportamiento por caso |
| 21 | "Conocimiento" debe ser más amigable | `memoria/page.tsx` (1240 líneas) — 4 pestañas densas tipo wiki/markdown en un solo archivo: Mi despacho, Criterios aprendidos, Guías y habilidades, Sugerencias | Aplicar el diseño canónico + navegación más guiada y visual, menos "wiki plano" |
| 22 | Todo debe ser más intuitivo y con más diseño | — | Paraguas de los puntos anteriores |
| 23 | El diseñador de agentes debe permitir nombre + qué hace + cómo funciona + capacidades especiales. "Revisa GROK BOT, haz reverse engineer" | `personas/page.tsx:38-49`. Campos hoy: nombre, título, `role_prompt`, tono, áreas de énfasis, frases de invocación, `model_tier` (estándar/local), guías vinculadas, descripción, activo. **No existe ningún campo de capacidades** — el único control parecido es `model_tier`, que solo cambia privacidad del modelo, no capacidad. Todo se mete a la fuerza en el texto libre | D8: agregar las 3 casillas de capacidad. Pendiente: mirar Grok Bot como referencia de UX antes de cerrar el formulario |

---

## 3 · Hallazgo: `os-coach` (punto 13)

El repo `promptadvisers/os-coach` es un skill que guía a alguien **no técnico** a construir
un "OS agéntico" en 6 capas: **Identidad → Sustrato (conocimiento) → Reglas/Hooks →
Skills → Agentes → Herramientas/Conexiones**. Patrón por sesión: preguntar 2-3 cosas en
lenguaje llano → construir los archivos reales → guardar avance en `memory.md` → avanzar
o retroceder → auditar contra objetivos en `OS-AUDIT.md`. Protege datos sensibles guardando
referencias en vez de valores.

**Ya existe un skill interno equivalente** con la misma arquitectura. Lo aprovechable no es
el repo, es **el patrón**: sus 6 capas mapean casi 1:1 a secciones que MIA ya tiene —
Identidad → perfil del despacho · Sustrato → Conocimiento · Reglas → "qué no debo hacer
nunca" · Skills → Guías · Agentes → Personas · Herramientas → Conexiones.

**Recomendación:** rediseñar el onboarding de identidad con ese ritmo ("pregunto poco →
construyo algo real → te muestro el avance → puedes volver") en vez de las 7 preguntas
lineales de hoy, que es donde se acumuló la fatiga y la redundancia que Pipe reportó.

---

## 4 · Lección de proceso (para no repetirla)

**Qué pasó:** describí `frontend_design_spec.md` como "dorado/cristal de lujo" y le
presenté a Pipe una decisión binaria sobre esa base. Él eligió confiando en mi
descripción, y la decisión resultante era inversa a lo que realmente quería. Lo detectó
él, no yo.

**Por qué pasó:** presenté una decisión de rumbo apoyada en mi lectura de un documento,
sin haber verificado esa lectura contra `CLAUDE.md` §I (que decía explícitamente
"Teal/Azul Oxígeno… Tema Claro/Oscuro") ni contra lo implementado en `globals.css`.

**Barrera:** antes de pedirle a Pipe una decisión sobre diseño visual, **mostrarle el
estado real renderizado** (capturas de la app corriendo), no una descripción textual de un
`.md`. Una captura habría hecho evidente en 5 segundos que el problema era el negro
forzado, no la paleta. Cuando la decisión es visual, el insumo tiene que ser visual.
