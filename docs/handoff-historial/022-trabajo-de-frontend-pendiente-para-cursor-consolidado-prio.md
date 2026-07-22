## ⭐ Trabajo de frontend PENDIENTE para Cursor (consolidado · priorizado · 2026-07-03)

El backend de estos puntos ya está en `origin/main`; falta SOLO la UI. Cada uno tiene su
sección detallada más abajo con endpoints y comportamiento. Orden sugerido:

1. **Control del tope de gasto de IA (CP-E1)** — `GET/PUT /api/policy/budget`. **COMPLETADO** (commit `7030e5e`). Detalle en la sección "CP-E1 · control del tope en el Panel".
2. **Pantalla de gestión de Personas jurídicas (CP-E3, lo más nuevo)** — CRUD
   `GET/POST/PUT/DELETE /api/personas`. **COMPLETADO** (commit `557478c`). Detalle en la sección "CP-E3" arriba de todo.
3. **Tarjetas de "Recomendaciones de Mia" (CP-V2)** — `GET /api/dreams/prescriptions` +
   `POST .../{id}/decision`. **COMPLETADO** (commit `c61912f`). Detalle en la sección "CP-V2".
4. **Automatizaciones (CP-P2)** — plantillas + sugerencias consent-first (`/api/automations/*`). **COMPLETADO** (commit `5642a73`).
5. **Conectar Microsoft 365 / Google (CP-P3)** — botón "Conectar" (`/api/mailbox/*`). **COMPLETADO** (commit `70ac8e7`). OJO:
   la ACTIVACIÓN real (llaves OAuth en `.env`) sigue APLAZADA por decisión de Pipe hasta el producto
   final; la UI está lista y muestra el aviso 503 si el servidor aún no tiene las llaves.

**Reglas para Cursor (recordatorio):** §G sin jerga técnica al abogado (nada de "tenant",
"LangGraph", "modelo", "pgvector"); errores del backend llegan en llano — mostrarlos tal cual;
tras `npm run build` reinicia el dev server (pisa la caché `.next`). Escribe tus hallazgos de
capa 3 al final del archivo.

---

