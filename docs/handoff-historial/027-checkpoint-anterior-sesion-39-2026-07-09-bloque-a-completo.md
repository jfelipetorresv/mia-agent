## Checkpoint anterior: Sesión 39 (2026-07-09) — BLOQUE A COMPLETO: Proyectos + carpetas sin fricción

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque A del plan de evolución de producto (aprobado por Pipe), con
orquestación multi-agente según su autorización expresa de la sesión 38:

- **Pestaña "Proyectos" (nueva):** espacio de trabajo libre estilo Claude Cowork — el abogado
  crea un proyecto en 2 pasos, conecta carpetas, chatea con Mia sobre esas fuentes (con memoria
  de la conversación) y guarda los documentos que Mia produce, con descarga en Word. Sin
  diagnóstico ni aprobación de borrador (eso sigue siendo de los Asuntos, separados como pidió Pipe).
- **Fin de las rutas pegadas a mano:** selector visual de carpetas del equipo (navegable, seguro,
  fail-closed) en los 3 sitios donde antes se pegaba la ruta (carpetas de trabajo, carpeta del
  expediente, vault de Obsidian).
- **Varias carpetas por asunto/proyecto** — y de paso se corrigió DE RAÍZ el bug latente de poda
  cruzada (documentado en el plan): con 2 carpetas, el sync de una ya no puede borrar los
  documentos de la otra (ni en carpetas del equipo NI en OneDrive, donde también existía).
- **Panel "Fuentes" unificado** en la pantalla del asunto y del proyecto: carpetas del equipo +
  OneDrive + correos en una sola lista con estados en llano y "+ Conectar fuente".

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (74 suites)** — línea base sube de 70 a 74:
  `test_matter_folders_multi` 30/30 (el caso del bug de poda cruzada + concurrencia + backfill
  conservador), `test_folder_browse` 15/15, `test_projects` 33/33, `test_matter_sources` 26/26.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial multi-agente (contexto fresco)** — 12 hallazgos CONFIRMADOS,
  todos corregidos y re-verificados antes del commit salvo 2 notas aceptadas como deuda:
  2 BLOQUEANTES (el backfill de la migración podía fusionar procedencias y provocar borrado de
  documentos conservados; la poda de OneDrive seguía sin distinguir fuente → borrado cruzado
  con multi-carpeta), 2 MAYORES (carrera de sincronización sin candado en el motor → documentos
  duplicados; el chat de proyecto no recordaba los turnos anteriores), 6 menores (proyectos
  contados como "asuntos" en asistente/dashboard/endpoint legacy, burbuja "pensando" infinita
  en error, doble Enter creaba proyectos duplicados, mensaje con la palabra equivocada).
  Detalle completo en `memory/progress.md` sesión 39.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. **Proyectos:** crear un proyecto (nombre → conectar carpeta con el selector visual → entrar),
   chatear sobre los documentos, verificar que un segundo mensaje recuerda el anterior, guardar
   una respuesta larga con "Guardar en el proyecto" y descargarla en Word.
2. **Selector de carpetas:** en Configuración → Carpetas y en un asunto ("Conectar fuente →
   Carpeta del equipo"), navegar y elegir sin pegar rutas.
3. **Panel Fuentes del asunto:** vincular 2 carpetas al mismo asunto, "Revisar ahora" en una,
   confirmar que los documentos de la otra no se tocan; el botón de correos sigue ahí.
4. Sigue pendiente la capa 3 arrastrada de sesiones 35-38 (onboarding/panel/rebrand + los 5
   puntos de fuentes remotas) — nada de eso cambió en esta sesión.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque B** del plan (guías de trabajo asistidas — "Crear guía con Mia" con
   gate HITL por construcción + CRUD/versiones de playbooks + gobernanza de lo aprendido).
   El plan vive en `memory/plan-evolucion-producto.md` (Bloque A ya marcado completado).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el navegador de carpetas queda deshabilitable por flag para el futuro
   Modo A/Docker (Riesgo #56); documentos con procedencia ambigua pre-migración nunca se podan
   solos (protección anti-pérdida, Riesgo #57); `MatterDriveFolder.tsx` quedó sin uso (borrar
   en una limpieza futura).

### Trabajo en background sin leer

Nada — todos los workflows y la regresión final se leyeron y quedaron reflejados aquí.

### Decisiones tomadas / suposiciones declaradas

- `documents.body` (texto íntegro) para los archivos que Mia produce: los fragmentos indexados
  llevan traslape y no se pueden reconstruir para el Word. Suposición razonable no prevista en
  el plan, declarada aquí.
- `GET /api/matters` sin parámetro devuelve SOLO asuntos (compatibilidad de la lista actual);
  `?kind=proyecto` y `?kind=todos` para lo demás. Asistente, dashboard y endpoint legacy también
  filtran proyectos.
- Los endpoints singulares `/folder` quedan como wrappers deprecados (sin el 409); el frontend
  ya usa la superficie plural vía FuentesPanel.
- Memoria conversacional del proyecto: corta y presupuestada (últimos 6 turnos / 8.000
  caracteres), solo en proyectos — el flujo de asuntos quedó byte a byte intacto (gate HITL 21/21).

---

