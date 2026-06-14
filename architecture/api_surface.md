# Mia · SOP — Superficie /api/* (backend de las 5 pantallas)
# Última actualización: 2026-06-14 (Fase 3 backend · decisión #20)

## Qué es
Endpoints HTTP que consumen las 5 pantallas del abogado (Next.js, Sesión 15). Viven en
`backend/mia/api/routes/ux.py` (router con prefijo `/api`), montado en `api/main.py`. Auth: el
JWT middleware (`api/middleware.py`) exige `Authorization: Bearer <jwt>` con `tenant_id`; todas
las consultas pasan por RLS (`pool.tenant_connection`). El frontend usará un token de desarrollo
(deuda técnica S15; no hay login todavía).

## Relación con las rutas legacy (no romper)
Las rutas del Módulo 1d/1e siguen INTACTAS y NO se renombran (el gate `test_hitl_flow` las usa):
`GET /matters`, `GET /matters/{id}/stream`, `POST /matters/{id}/approve|reject|edit`,
`GET/POST /settings/agents…`, `GET /health`. La superficie `/api/*` es nueva y, donde aplica,
**delega** en esos handlers (stream y approve/reject) para no duplicar la lógica del grafo.

## Mapa de endpoints (todos bajo /api, requieren JWT salvo nota)

| Pantalla | Método · ruta | Request | Response (campos visibles) |
|---|---|---|---|
| 1 Lista | `GET /api/matters` | — | `[{id, name, created_at}]` |
| 1 Lista | `POST /api/matters` (201) | `{name, description?}` | `{id, name, description, created_at}` |
| 2 Workspace | `GET /api/matters/{id}` | — | `{id, name, created_at}` |
| 2 Workspace | `GET /api/matters/{id}/documents` | — | `[{id, name, type, created_at}]` |
| 2 Workspace | `POST /api/matters/{id}/documents` (201) | multipart `file` (PDF/Word/txt/md) | `{id, name, fragments}` |
| 2 Workspace | `POST /api/matters/{id}/chat` | `{message}` | `{stream_url}` |
| 2 Workspace | `GET /api/matters/{id}/stream?message=` | — (SSE) | eventos `thinking/draft_ready/awaiting_review` (§G) |
| 3 Revisión | `GET /api/matters/{id}/draft` | — | `{draft, awaiting_review}` · **404** si no hay borrador |
| 3 Revisión | `POST /api/matters/{id}/draft/approve` | `{edited_text?}` | SSE `finalizing→done` |
| 3 Revisión | `POST /api/matters/{id}/draft/reject` | `{reason?}` | SSE `finalizing→done` |
| 4 Memoria | `GET /api/profile` · `PUT /api/profile` | perfil estructurado | el perfil del despacho |
| 4 Memoria | `GET /api/playbooks` · `POST /api/playbooks` (201) | `{title, summary, applies_when, content}` | `[{id, title, summary, applies_when}]` |
| 4 Memoria | `GET /api/proposals` | — | `[{id, type, suggestion, reason, times_seen}]` |
| 4 Memoria | `POST /api/proposals/{id}/apply` · `/ignore` | — | `{status}` |
| 5 Dashboard | `GET /api/dashboard/stats` | — | métricas + conectores + jobs (etiquetas amigables) |

## Detalles que importan
- **Borrador (Pantalla 3):** `GET …/draft` lee el `draft` del checkpoint del grafo
  (`AsyncPostgresSaver` vía `graph.aget_state`); 404 si el asunto no tiene un turno pausado.
  `approve` con `edited_text` se trata como edición; sin él, como aprobación. Reusan `_resume`.
- **Subida de documentos:** `ingest/extract.py` extrae texto (PyMuPDF para PDF, python-docx para
  Word, utf-8 para txt/md) → `chunk_text` → embeddings (voyage-law-2) → `documents` + `chunks`
  bajo RLS. Requiere `python-multipart` (FastAPI lo exige para `UploadFile`).
- **Perfil:** persistido en `firm_profiles` (migración 007, decisión #20) vía
  `ProfileManager(pool=…).get_firm_profile / upsert_firm_profile`. Es el perfil ESTRUCTURADO
  (distinto de los perfiles de texto in-memory de 2a que alimentan la costura L9 del prompt).
- **Aplicar propuesta:** `apply` actualiza (improve) o crea (new) un playbook y marca la
  propuesta `applied`; `flag_gap` solo se marca atendida. Cierra parte del Riesgo #21.

## Regla §G en las respuestas (cero jerga técnica)
Ninguna respuesta `/api/*` expone `hitl`, `langgraph`, `pgvector`, `tenant_id`, `tool_call` ni
`embedding` (verificado por `test_ux.py::§G`). Traducciones aplicadas:
- Jobs cron → "Sincronización del conocimiento" / "Depuración del conocimiento" / "Aprendizaje
  de Mia" (nunca `curator_weekly`, etc.).
- Conectores → `knowledge_base` (Obsidian) · `external_store` (Pinecone) · `models` con
  etiquetas ("Razonamiento principal" / "Respuestas rápidas"), nunca ids `claude-…-4-6`.
- Tipos de propuesta → "Mejorar conocimiento" / "Conocimiento nuevo" / "Brecha detectada".

## Decisiones de diseño tomadas
- `/api/*` nuevo + legacy `/matters/*` intacto (no romper 1d). Delegación en stream/approve.
- Perfil persistido en tabla nueva `firm_profiles` (no reusar tenant_settings; el perfil tiene
  forma propia y rica).
- `chat` no corre el turno: devuelve `stream_url` y el cliente abre el SSE (un POST no puede
  hacer streaming idiomático; mantiene el patrón GET-SSE de 1d).
- `matters` no tiene columna `description` (Módulo 0); el POST la acepta y la ECHO-ea pero no la
  persiste todavía (deuda menor; añadir columna si la Pantalla 2 la necesita).

## Self-Annealing
1. **`RuntimeError: Form data requires python-multipart`** al arrancar → falta la dep; está en
   `pyproject.toml`, instalar en `.venv`.
2. **`/draft` siempre 404** → el asunto no corrió un turno (no hay checkpoint con `draft`), o el
   `thread_id` no coincide (`{tenant}:{matter}`).
3. **§G falla** → revisar que ningún campo de respuesta traiga jerga; usar las etiquetas amigables.
4. **Upload 415** → tipo no soportado (solo PDF/Word/txt/md).
