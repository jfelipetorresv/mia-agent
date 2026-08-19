## Checkpoint actual: CP-E6 — Más canales (relay) + conectar sistemas vía MCP (2026-07-04)

### Qué cambió (lenguaje simple)

- **Conectar sistemas del despacho (lo nuevo para el abogado):** Mia ahora puede conectarse
  a sistemas externos —**gestión documental** del despacho y **consulta de estados de
  procesos judiciales**— para trabajar con esa información. Todo nace **apagado**: el
  despacho lo enciende con sus credenciales cuando quiere, y lo apaga (o borra las
  credenciales) cuando quiere.
- **Seguridad primero:** las credenciales viven **fuera** del cerebro de Mia; se piden
  tokens de **solo lectura**; y al conectar, ningún secreto interno de Mia se filtra.
- **Más canales:** se preparó el patrón "relay" para que sumar canales (WhatsApp, correo…)
  sea un adaptador delgado, con las llaves del canal fuera del núcleo. El puente de
  Telegram ya usa ese patrón común.

### Frontend PENDIENTE para Cursor — pantalla "Sistemas conectados"

**COMPLETADO** (Cursor capa 3 · 2026-07-12). Detalle en "Hallazgos de Cursor (capa 3)" al final.

En Configuración → Conexiones, sección "Sistemas conectados". Endpoints (`/api/mcp/*`):

- `GET /api/mcp/status` → lista de sistemas. Cada uno trae: `slug`, `display_name`
  (mostrar ESTE, en llano), `description`, `permissions_note` (nota de permisos mínimos —
  mostrarla para tranquilidad del abogado), `fields` (cada uno: `env_var`, `label`,
  `is_secret`, `required`), `enabled`, `configured`, `missing` (etiquetas de lo que falta).
- `POST /api/mcp/{slug}/enable` con body `{ "env": {…}, "secrets": {…} }` → guarda las
  credenciales y habilita. `env` = campos NO secretos (URLs), `secrets` = tokens. Las
  claves van por `env_var`/`secret_key` que da `fields`. Devuelve el status actualizado.
- `POST /api/mcp/{slug}/disable` → apaga sin borrar credenciales. Devuelve status.
- `POST /api/mcp/{slug}/forget` → borra la conexión y sus credenciales. Devuelve status.

Comportamiento esperado en la UI:
- Por cada sistema: nombre + descripción + nota de permisos; un formulario con los
  `fields` (los `is_secret:true` como campo tipo contraseña). Botón "Conectar" (enable),
  y si `enabled`: "Desconectar" (disable) y "Borrar credenciales" (forget).
- El backend **nunca** devuelve el valor de un secreto — no intentes precargarlo; usa
  `configured`/`missing` para mostrar si ya está puesto.
- Errores del backend llegan en llano (§G) — mostrarlos tal cual. Nada de "MCP",
  "servidor", "tenant": el abogado ve "Gestión documental del despacho".
- **No urgente / activación diferida:** igual que "Conectar Microsoft 365", la conexión
  EN VIVO con estos sistemas depende de registrar el servidor real; la UI puede quedar
  lista sin que haya un sistema conectado todavía.

Detalle técnico completo en `docs/canales-y-mcp.md`.

---

