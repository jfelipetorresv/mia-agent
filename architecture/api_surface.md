# Mia · SOP — Superficie HTTP real

Última actualización: 2026-08-18.

## Qué es
El API FastAPI (`python -m mia.api.run` → `mia.api.main:app`). Auth: login JWT
(`POST /api/auth/login`); el middleware exige `Authorization: Bearer` salvo rutas
abiertas (`/health`, docs en dev). Todas las consultas de datos pasan por RLS
(`pool.tenant_connection`). **No hay JWT de desarrollo ni «5 pantallas».**

Política de modelo por defecto: `quality_adaptive` (no LiteLLM-primero).

## Arranque
`python -m mia.api.run` hasta `GET /health` → 200. El lifespan abre el pool,
arranca el scheduler, el worker durable, el flusher de uso y —si hay
`TELEGRAM_BOT_TOKEN` completo— el puente de Telegram.

## Mapa (no exhaustivo; lo que el producto usa)

| Área | Rutas |
|---|---|
| Salud | `GET /health` (público; incluye `capabilities` OCR/voz/anydoc/telegram) |
| Auth | `POST /api/auth/login` · refresh / logout |
| Asuntos | `GET/POST /api/matters` · documentos · chat SSE · historial |
| HITL | `GET /api/matters/{id}/draft` (huella `draft_hash`) · `POST .../approve` (hash + `attested`) · reject · Word borrador/final |
| Auditoría | `GET /api/exports` · `GET /api/matters/{id}/exports` |
| Ayudantes | `GET/POST /settings/agents…` (`listo`/`razon`; enable 409 si no está confirmado) |
| Política | `GET/PUT /settings/model-policy` |
| Conexiones | MCP `/api/mcp/*` (catálogo de producto vacío) · Obsidian · mailbox · speech · NotebookLM |
| Automatizaciones | `/api/automations/*` (sugerencias del cron `generate_suggestions`) |
| Misiones | `/api/missions/*` |
| Sala | `POST /api/matters/{id}/warroom` (2ª pasada exige `autorizar_pasada_cara`) |
| HITL legado | `POST /matters/{id}/approve\|reject\|edit` (mismo candado de hash) |

## HITL
Aprobar liga un **hash** del texto mostrado. Si el borrador cambió, 409 / recibo
`recibo-invalidado`. `verification_passes` no trata `unavailable` como apto:
no hay Word final.

## Relación con rutas legacy
`GET /matters`, stream y approve/reject de 1d siguen intactas (gates HITL).
La superficie `/api/*` delega en esos handlers donde aplica.

## Regla §G
Ninguna respuesta al abogado expone `hitl`, `langgraph`, `pgvector`, `tenant_id`,
`tool_call` ni `embedding`.
