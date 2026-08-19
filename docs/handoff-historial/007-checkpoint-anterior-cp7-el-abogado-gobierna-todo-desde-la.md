## Checkpoint anterior: CP7 — El abogado gobierna todo desde la pantalla (2026-07-02)

### Qué cambió (lenguaje simple)

- Pantalla "Conocimiento": pestaña nueva **Habilidades** (qué tan bien le va a
  Mia con cada procedimiento, con % de aprobación); botón **Importar guías**
  (sube las guías de trabajo del despacho en .md/.txt/Word, con detalle en
  llano de lo que se importó/omitió); cada sugerencia ahora dice **qué
  procedimiento se modificaría**; sección nueva **"Orden del conocimiento"**
  (propuestas de Mia para unir guías repetidas o archivar las sin uso, con
  Aprobar/Rechazar).
- Panel de control: el selector de modelos técnicos se reemplazó por **"Motor
  de IA"** en español llano (Mi suscripción / Nube / Todo en mi equipo) y
  ahora SÍ guarda el cambio; sección nueva **Recordatorios** (ver y cancelar,
  con fecha Y HORA); la clave de Pinecone ya se escribe oculta (••••).
- Onboarding: se retiró la pregunta del "modo profundo" (era una función no
  implementada — no se ofrece lo que no existe).
- Pantalla del asunto: el panel Diagnóstico mostrará el resumen en 3 líneas
  (problema/normas/riesgo) cuando el backend lo emita (llega con CP6, hoy
  pendiente de aprobación de Pipe; sin él, todo se ve como antes).

### Frontend a revisar (Cursor — capa 3) — TODOS los archivos de este checkpoint

- `frontend/app/memoria/page.tsx` — pestaña Habilidades, Importar guías,
  target en sugerencias, sección Orden del conocimiento.
- `frontend/app/dashboard/page.tsx` — Motor de IA, Recordatorios, input de
  clave oculto.
- `frontend/app/onboarding/page.tsx` — pregunta p19 retirada (verificar que la
  navegación entre preguntas no se sienta rota).
- `frontend/app/asuntos/[id]/page.tsx` — resumen estructurado condicional en
  el panel Diagnóstico (los 2 pendientes de CP5 sobre este archivo y
  `frontend/app/page.tsx` siguen abiertos — puede cerrarse todo junto).
- Foco de la capa 3: diseño de interfaz, accesibilidad (labels, foco,
  contraste), consistencia de UX entre secciones nuevas y viejas, y
  superficies de seguridad visibles (ninguna clave/dato sensible en claro).

### Comportamiento esperado

- Con datos: Habilidades lista procedimientos con barra de % aprobado;
  Importar guías muestra "Se importaron N guías…" con detalle por archivo;
  el selector de Motor de IA persiste tras recargar; cancelar un recordatorio
  lo quita SOLO si el servidor confirmó (si falla, aviso en ámbar).
- Sin datos: cada sección nueva tiene su estado vacío en español llano.

### Resultado de verificación (3 capas)

- Capa 1: regresión **41/41 suites PASS** (test_rls 12/12 HALT);
  `test_second_brain_ui` extendido **26/26**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 1 mayor
  (cancelar recordatorio mostraba éxito aunque fallara) + 1 mayor
  preexistente (clave de Pinecone visible) + 5 menores: TODOS corregidos
  antes del commit. Revisión por lectura de patrones, no auditoría con
  herramientas. Deuda §G anotada fuera de alcance: textos "second brain",
  "vault", "Pinecone" del dashboard viejo.
- Capa 3 (Cursor): PENDIENTE — revisar los 4 archivos listados arriba y
  devolver hallazgos en la sección final de este documento.

---

