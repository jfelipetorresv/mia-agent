# Rediseño del perfil del despacho (SOUL) — diagnóstico y diseño

**Fecha:** 2026-07-20 · **Origen:** encargo de Pipe ("más rico pero NO más largo") ·
**Estado (verificado 2026-07-21 contra el código):** **implementado** el arreglo del bug
(punto 1 del plan) y el rediseño de preguntas/SOUL (puntos 2-6 del plan) — commit
`c980704`, "feat(perfil): el perfil del despacho pregunta criterio, no datos censales".
Punto 7 (`## aprendido` poblado por el trabajo real vía `update_soul`) **también está
implementado** — `execution/test_aprendido.py`, 32/32 checks PASS (verificado en vivo
2026-07-21). **Único punto del plan que NO se hizo tal como se diseñó: el
punto 8** — la pregunta "Súbeme 2 a 4 escritos tuyos" (carga de escritos como paso del
wizard) **no existe** en `frontend/app/onboarding/page.tsx`; el onboarding sigue siendo
puramente de preguntas. La riqueza de estilo se dejó completamente a `## aprendido`
en vez de a una carga inicial de escritos.

---

## 1 · Diagnóstico

**Este diagnóstico describe el estado del código el 2026-07-20, ANTES del arreglo.
Sigue siendo útil como historia del defecto, pero desde `c980704` el bug de §1 y los
Defectos A/B de abajo YA NO EXISTEN — ver el estado real en el encabezado y en §4.**

### No es un bug de generación: es un fallo silencioso de validación

`POST /api/onboarding/complete` acepta `responses: dict` sin validar nada. `build_soul` lee por **campo**
(`identity.name`, `jurisdiction.practice_areas`…), no por id de pregunta. Si las llaves no coinciden con
ningún campo conocido, todo queda vacío, se genera un SOUL de dos líneas — y **el API devuelve 200 OK**.

Comprobado en vivo: enviando `{"p1":…,"p2":…,"p5":…,"p10":…}` el SOUL resultante fue exactamente:

```
# SOUL.md — Despacho
# Generado: 2026-07-20 · Próxima revisión: 2026-10-18
```

Las preguntas reales (`GET /api/onboarding/questions`) son **8**, no 13:

```
p1 identity.name · p2 identity.location · p3 identity.voice · p4 identity.channels
p6 jurisdiction.practice_areas · p7 jurisdiction.client_type
p18 memory.tools_that_survived · p19 triad_mode
```

`p5` y `p10` ya no existen (removidas 2026-07-06 y 2026-07-09).

**Un abogado usando la pantalla NO reproduce este caso**: el frontend siempre manda las llaves correctas
(`onboarding/page.tsx:212` usa `current.field`).

### Defecto A — el guardián existe, funciona, y no está conectado

`validate_soul` (`backend/mia/onboarding/soul_interview.py:409`) detecta exactamente este caso: devuelve
`["## identity"]` para el SOUL degenerado. Solo se invoca en `execution/test_e2e.py`, **nunca en el endpoint**.
El detector de humo está desconectado.

### Defecto B — asimetría de validación

`PUT /api/profile/full` sí valida forma (`ux.py:582`). `POST /api/onboarding/complete` no valida nada
(`ux.py:1497-1499`): solo filtra llaves con prefijo `_` (`ux.py:1579`) y llama `run_interview` a ciegas
(`ux.py:1597`). Ninguna capa nota que el 100 % de las llaves era desconocido.

### El defecto que SÍ llega a producción

Seis de las ocho preguntas dicen *"Opcional — puedes saltarla"* (`onboarding/page.tsx:84`). Quien conteste
solo lo obligatorio obtiene un perfil de **seis líneas** — y `validate_soul` lo aprueba:

```
## identity
- name: Estudio Nogales
- lawyer: Ana Ruiz
- location: Ciudad, Pais
## jurisdiction
- base: Chile
```

---

## 2 · Por qué el SOUL actual es una tarjeta de presentación, no un alma

El SOUL se inyecta al modelo como *"Esta es tu identidad y la voz del despacho. Razona y redacta conforme
a ella"* (`prompt_builder.py:318`). Contra ese estándar:

| Línea del SOUL | ¿Sirve al razonar? |
|---|---|
| `name` / `lawyer` | Sí — va en los escritos |
| `base` (jurisdicción) | Sí — enruta normas |
| `practice_areas` / `client_type` | Débil — prior de recuperación |
| `location` | Casi no |
| `channels` (sitio web) | **No. Cero.** |
| `voice` (3 adjetivos) | **No.** Tres adjetivos no cambian un borrador |
| `tools` | **No.** `toolOptions.ts:7-11` dice literalmente que no activan nada |

**Contradicción interna:** P3 pide adjetivos de estilo y el resumen le dice al abogado *"Tu estilo de
redacción no te lo pregunto"*. MIA pregunta y niega preguntar.

**Causa de fondo:** `architecture/soul_interview.md` documenta el diseño original — **19 preguntas,
9 secciones** (`mission`, `hard_nos`, `doctrinal_stance`, `memory`, `rhythm`). Se recortó a 8 preguntas y
4 secciones. Cada recorte estuvo justificado, pero **se eliminó todo el contenido de criterio y no se
repuso nada**: quedaron los datos censales y se fue el juicio. `hard_nos` todavía se renderiza
(`soul_interview.py:303`) pero **ninguna pregunta lo alimenta** — un cuarto amoblado sin puerta.

---

## 3 · Diseño propuesto: los mismos 8 pasos, otro rendimiento

Reglas tomadas de las skills de referencia de Pipe (`perfil-personal-lexia` es su modelo de "rico pero no
largo"): **pedir artefactos, no adjetivos** · **el espacio negativo es donde está la densidad** · **elicitar
por escenario, no por abstracción** · **una línea = un hecho** · **omitir, nunca rellenar**.

### Las 8 preguntas, tal como las vería el abogado

**Se conservan (3)**

1. **¿Cómo se llama tu despacho y cómo firmas tú?** *(obligatoria)* — va impresa en cada escrito.
2. **¿En qué ciudad y país trabajas?** *(obligatoria)* — sede y husos.
3. **¿Con las reglas jurídicas de qué país trabaja tu despacho?** *(obligatoria, selector)* — enruta normas.
   No es inferible antes del primer documento.

**Se fusionan (1)** — antes p6 + p7

4. **¿A quién defiendes y en qué asuntos?** — chips libres, sin lista precargada. Es el único prior antes de
   que exista un solo documento; después MIA lo corrige sola.

**Nuevas (4) — aquí está toda la riqueza**

5. **¿Qué quieres revisar siempre antes de que salga, y qué puedo resolver yo sin preguntarte?**
   Define la línea de autonomía. Sin esto MIA solo tiene dos modos: pedir permiso para todo, o excederse.
6. **¿Qué no debo hacer nunca?** — chips + línea libre. Alimenta `hard_nos`, que ya se renderiza.
   Una prohibición comprime más que un párrafo de estilo.
7. **¿Cuándo das un escrito por terminado?** — el estándar de cierre. Es la única forma de que MIA sepa
   cuándo entregar en vez de adivinar.
8. **Súbeme 2 a 4 escritos tuyos.** — no es pregunta, es carga. Sustituye los adjetivos de estilo por la
   fuente real, y **cumple el principio que hoy MIA enuncia pero incumple**.

**Se eliminan (3):** estilo en 3 adjetivos (contradice el principio declarado) · sitio web y canales
(cero valor al razonar) · herramientas (no activan nada; Conexiones ya sabe la verdad).

**Se infiere en vez de preguntarse:** herramientas (conectores realmente activos) · estilo y estructura
(escritos + correcciones a borradores) · áreas y tipo de cliente (partes y materias de los expedientes) ·
fuentes preferidas (lo que el abogado cita) · convenciones de entrega.

### Estructura del SOUL.md resultante

```
# SOUL.md — <despacho>
# Generado: … · Próxima revisión: …

## identity      name · lawyer · location
## jurisdiction  base · practice_areas · client_type
## autonomia     reviso_siempre · decide_solo          ← nuevo
## nunca         una línea por línea roja              ← nuevo (el render ya existe)
## terminado     estándar de cierre                    ← nuevo
## aprendido     [inferido] hechos con fecha y fuente  ← nuevo, se llena solo
```

**`## aprendido` es la idea central:** la riqueza crece con el uso, no con más preguntas. Cada línea marcada
`[inferido]`, fechada y con su fuente, escrita por `update_soul` (que ya existe y ya se usa desde
"Mi despacho"), y corregible por el abogado. **La entrevista no se alarga nunca; el perfil se enriquece solo.**

Todo agnóstico de jurisdicción: sin país, sin rama, sin tipo de cliente precargado. Chips genéricos y editables.

---

## 4 · Plan de implementación — estado real (verificado 2026-07-21)

Todo el plan se ejecutó en el commit `c980704` ("feat(perfil): el perfil del despacho
pregunta criterio, no datos censales"), salvo el punto 3b señalado abajo.

| # | Archivo | Qué | Estado |
|---|---|---|---|
| 1 | `backend/mia/api/routes/ux.py` (`_known_fields_only` en ~610, endpoint en ~1627) | Validar llaves contra el set de campos conocidos + llamar `validate_soul`; 422 nombrando las llaves desconocidas | **Hecho** |
| 2 | `backend/mia/onboarding/soul_interview.py` | `QUESTIONS` nuevas (`p1,p2,p6,p20,p21,p22`); secciones `autonomia`/`nunca`/`terminado`/`aprendido` en `build_soul` (~325) y `build_summary` (~402) | **Hecho** |
| 3a | `frontend/app/onboarding/page.tsx` | ids, `TAG_IDS`/`TEXT_IDS`, `REQUIRED_IDS`, `BLOCK_LABEL` | **Hecho** |
| 3b | `frontend/app/onboarding/page.tsx` | Paso de carga de escritos (pregunta 8 del diseño, "Súbeme 2 a 4 escritos") | **NO hecho** — no existe ese paso; se decidió no implementarlo y dejar la riqueza de estilo enteramente a `## aprendido` |
| 4 | `frontend/app/_components/MiDespachoSection.tsx` | Espejo de los campos nuevos para poder editarlos después | **Hecho** |
| 5 | `execution/test_e2e.py` | Gate actualizado: `QUESTIONS` = 6, ids removidos listados explícitamente (línea ~257-262) | **Hecho** |
| 6 | `architecture/soul_interview.md` | Reescrito: documenta el diseño de 6 preguntas + generación determinista sin LLM | **Hecho** |
| 7 | Escritura de `## aprendido` desde el trabajo real | Vía `update_soul` | **Hecho** — `execution/test_aprendido.py`, 32/32 PASS |

**Pendiente real:** si Pipe todavía quiere el punto 8 original (carga de escritos como
fuente de estilo en vez de solo `## aprendido`), es trabajo nuevo, no una corrección.
