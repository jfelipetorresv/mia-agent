## Checkpoint anterior: CP-C4b — "Configura a Mia" como onboarding explicativo (2026-07-02)

### Qué cambió (lenguaje simple)

- El recorrido "Configura a Mia" ya no solo detecta qué falta: ahora EXPLICA cada
  paso como un onboarding. Cada tarjeta tiene un botón "¿Qué es esto?" que despliega
  qué es la herramienta, para qué le sirve al despacho y cómo se hace paso a paso.
- Se agregó al final el mapa "¿Qué hace cada sección de Mia?" (Asuntos, Revisión de
  borradores, Conocimiento, Panel de control, este recorrido y Telegram).
- Mia también explica el siguiente paso completo cuando se le pregunta por la
  configuración (por Telegram): antes solo enumeraba, ahora acompaña.

### Frontend a revisar (Cursor — capa 3) + UI PENDIENTE de construir

- `frontend/app/configurar/page.tsx` — guía expandible por paso (contenido del
  servidor, `GET /api/setup/status` → `pasos[].guia` y `secciones`), sección del
  mapa de secciones, accesibilidad de la barra de progreso (`role="progressbar"`
  + aria) y del botón (`aria-expanded`). Foco de capa 3: legibilidad del texto
  largo, jerarquía visual del acordeón, contraste.
- **UI que el backend ya soporta pero el frontend AÚN NO tiene** (hallazgos del
  revisor de capa 2 — las guías se redactaron para no mentir mientras tanto, pero
  la experiencia queda a medias hasta que existan):
  1. **Panel de control · sección "Carpetas de trabajo"** — no existe. Backend
     listo: `GET /api/folders/detected`, `POST /api/folders`, `DELETE
     /api/folders/{id}`, `POST /api/folders/sync`. Debe listar carpetas
     registradas + nubes detectadas, permitir registrar por ruta y quitar.
  2. **Panel de control · tarjeta Obsidian: botón "Instalar Obsidian"** — hoy solo
     hay "Sincronizar" + input "Ruta del vault" (con jerga "vault"). Backend listo:
     `GET /api/obsidian/status`, `POST /api/obsidian/install` (body
     `{"confirmar": true}`), `POST /api/obsidian/bootstrap`. Falta el botón de
     instalar (con confirmación) y suavizar el texto "Ruta del vault" → "espacio de
     notas".
  3. **Pantalla de revisión de borrador · botón "Descargar en Word" + informe de
     verificación de citas** (pendiente de CP9, ver ese checkpoint abajo). Las
     guías de CP-C4b se escribieron asumiendo que ESTO existirá pronto.

### Resultado de verificación (3 capas)

- Capa 1: `test_setup_wizard` extendido **30/30**; regresión completa **43 suites
  verdes** (test_rls 12/12 HALT); `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — CORREGIDAS antes del
  commit: (L1) la guía llegaba cortada a 150 caracteres en el chat → ahora completa
  (check a4); (U1/U2/U4/U5/U8) las guías describían pantallas o un chat web que no
  existen → reescritas para decir la verdad del producto HOY y sin referencias
  circulares; (U3) la promesa de Word/verificación se suavizó hasta que Cursor la
  entregue. La UI faltante (carpetas, instalar Obsidian) quedó documentada arriba
  como trabajo pendiente en vez de fingir que existe. Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — revisar la página y, sobre todo, construir la UI
  pendiente de los 3 puntos de arriba.

---

