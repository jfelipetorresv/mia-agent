# Checklist de honestidad de UI — recorrido de primera vez (F3)

Auditoría independiente de código (grep + lectura), sin ejecutar la app. Repo: `D:\Inteligencia Artificial\Mia-Super Agent\mia\frontend`.
Fecha: 2026-08-07. Firma: Auditor independiente (agente Sonnet, sesión 55).

## Defectos a corregir

1. **FALLA** — `frontend/app/_components/MailboxSection.tsx:71-83` (botón "Conectar" de Microsoft/Google). El botón se muestra siempre como disponible; el aviso honesto de "la conexión aún no está habilitada en este equipo" (backend `backend/mia/api/routes/mailbox.py:160-168`, HTTP 503) solo aparece DESPUÉS de que el abogado hace clic e inicia el intento de conexión. No cumple "ocultas o marcadas indisponibles" mientras no haya apps OAuth registradas.
   - Arreglo propuesto: que `GET /api/mailbox/status` incluya `oauth_configurado` por proveedor y que `MailboxSection.tsx` desactive/etiquete el botón como "Pídele a tu administrador que lo habilite" antes del clic, no después.
   - **CORREGIDO (commit `c6173e5`, 2026-08-07)**: `/api/mailbox/status` expone `disponible` por proveedor (mismo criterio que el 503 de `POST /connect`); la UI reemplaza el botón por el aviso honesto y condiciona también el permiso de OneDrive. Verificado EN VIVO en `/configurar` → Conexiones: el aviso aparece y "Conectar" no se ofrece (dev sin apps OAuth). Cubre también el AVISO de OneDrive (misma causa raíz).

## Tabla por paso

| Paso | Veredicto | Evidencia | Notas |
|---|---|---|---|
| /register | PASA | `frontend/app/register/page.tsx:6,18,32,38` (`token`, `tenant_id` solo en identificadores TS, nunca renderizados al usuario) | Sin jerga visible; copy no revisado en detalle pero sin banderas en grep de HITL/LangGraph/pgvector/embedding/SSE/endpoint/checkpoint/RLS |
| /activar | PASA | `frontend/app/activar/page.tsx:3-7` (comentario explícito: "NUNCA se muestra 'API key', 'Voyage', 'Anthropic', 'token', 'endpoint', 'modelo' ni 'LLM'") | Autoimpuesto y consistente con grep — cero coincidencias de jerga en el archivo |
| /onboarding (7 pasos) | AVISO | `frontend/app/onboarding/page.tsx` (archivo único, no fragmentado en 7 sub-rutas) | No se auditó línea por línea cada uno de los 7 pasos por presupuesto de la auditoría; grep global de jerga técnica sobre todo `app/` no arrojó coincidencias en este archivo |
| Escritorio (/) | PASA | `frontend/app/page.tsx:171` ("Un asunto es un caso de tu despacho: conectas carpetas, subes el expediente...") | Lenguaje llano, sin promesas de capacidad no construida |
| Crear asunto | AVISO | no localizado un archivo dedicado "crear asunto" distinto de `page.tsx`/`asuntos/[id]/page.tsx` | Flujo probablemente inline en el escritorio; no se verificó el modal de creación en detalle |
| Subir documentos | AVISO | `frontend/app/_components/FuentesPanel.tsx`, `FolderPicker.tsx` | Copy revisado parcialmente (ver Fuentes/Carpetas abajo); sin banderas de jerga |
| Pregunta/turno | PASA | `frontend/app/chat/page.tsx:408` (comentario "token de texto" es interno, no UI) | Sin jerga visible al usuario en el grep |
| /asuntos/[id]/revisar — gate de citas | PASA | `frontend/app/_components/CitationReview.tsx:100-101` (`if (v.respaldadas === v.citas) return "...todas con respaldo..."`) | El mensaje "todas con respaldo" SOLO se emite cuando `respaldadas === citas`; el conteo de "por verificar" en `revisar/page.tsx` usa `marcadas + anotadas` (comentario CP9 en el archivo), no solo `marcadas` — el defecto de s53 sigue corregido |
| Aprobar borrador | PASA | `frontend/app/asuntos/[id]/page.tsx:269,278` (`hitl_outcome` es clave interna del payload, nunca literal "HITL" en el DOM) | No se detectó texto "HITL" renderizado al usuario |
| Alcance de lectura (<95%) | PASA | Backend: `backend/mia/config.py:154-156` (`MIA_ALCANCE_AVISO_UMBRAL = 0.95`); Frontend: `frontend/app/_components/CitationReview.tsx:245-255` ("Leí {alcance.porcentaje}% de este expediente...") | El backend (`backend/mia/agents/graph.py:1917-1922`, función `_aviso_de_alcance`) solo puebla `alcance_lectura` por debajo del umbral; el frontend renderiza el aviso siempre que el backend lo entregue — declaración correcta y no permanente |
| Conexiones Gmail/Outlook/OneDrive | **FALLA** | `frontend/app/_components/MailboxSection.tsx:71-83` vs `backend/mia/api/routes/mailbox.py:157-168` | Ver "Defectos a corregir" #1 |
| OneDrive (Carpetas en la nube) | AVISO | `frontend/app/_components/OneDriveSourcesSection.tsx:143`, `MailboxSection.tsx:187-236` | Funcionalidad completa y aparentemente construida (a diferencia de Gmail/Outlook genérico); mismo patrón de "aviso solo tras el clic" aplica si el permiso de archivos tampoco está habilitado — mismo arreglo del defecto #1 lo cubre |
| /proyectos — carpetas exclusivas | PASA | `frontend/app/proyectos/page.tsx:147-149` ("Un proyecto se parece a un asunto en todo — conectas carpetas...") | No insinúa carpetas exclusivas por proyecto; el texto iguala el mecanismo al de un asunto |
| /configurar | PASA | `frontend/app/configurar/page.tsx:9-17` (comentario de arquitectura de pestañas) | Ninguna mención de "Modo A" ni Docker en copy visible; solo aparecen como referencia arquitectónica en CLAUDE.md, no en frontend |
| "Modo A"/Docker en UI | PASA | grep sin resultados en `frontend/app/**/*.tsx` para "docker"/"modo a" | No se ofrece en ningún punto del frontend |
| Control de vencimientos/términos procesales | PASA | `frontend/app/dashboard/page.tsx:681` ("· plazo procesal: confirma tú la fecha") | El copy traslada explícitamente la confirmación del plazo al abogado; no se insinúa control automático |

## Conteo

- PASA: 11
- FALLA: 1 (aparece dos veces en la tabla — Gmail/Outlook y OneDrive comparten la misma causa raíz, un solo defecto)
- AVISO: 3

---
Auditor independiente (agente Sonnet, sesión 55) — 2026-08-07
