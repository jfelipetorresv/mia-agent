# Canales y sistemas conectados (CP-E6)

_Ola 5 · escala. Cómo Mia llega por más canales y se conecta a más sistemas — sin que
ninguna credencial entre al núcleo del agente._

Este documento tiene dos partes: **canales** (por dónde te habla Mia) y **sistemas**
(a qué se conecta Mia para trabajar). Las dos comparten un principio: **las credenciales
viven FUERA del núcleo** y con los permisos mínimos.

---

## Parte 1 · Canales (patrón "relay")

Un **canal** es una vía para hablar con Mia: hoy el chat de la web y **Telegram**;
mañana WhatsApp, correo, u otro. Todos siguen el mismo patrón **relay**:

- El canal corre **opt-in** con el API si hay `TELEGRAM_BOT_TOKEN` (hilo
  daemon en el lifespan). También puede correrse a mano
  (`python -m mia.channels.telegram_bridge`).
- Guarda **sus** credenciales en **su propio entorno** (el token del bot de Telegram,
  por ejemplo) — el núcleo nunca las ve.
- Habla con Mia **solo por el API HTTP**, autenticándose con usuario/clave para obtener
  un **JWT** (POST `/api/auth/login`). Así el aislamiento por despacho (RLS) y la
  política de modelo aplican **igual que en la web**.

La pieza reusable es `backend/mia/channels/relay.py`:

- `RelayClient` — login con JWT, **re-login automático ante 401**, y los tres verbos que
  cualquier canal necesita: `chat` (texto), `transcribe` (voz→texto) y `synthesize`
  (texto→voz). El STT y el TTS corren **100% local** en el servidor del despacho.
- `RelayConfig` / `load_relay_config` — lee la identidad del despacho desde el entorno
  del proceso de canal.

El puente de Telegram (`channels/telegram_bridge.py`) es el **primer adaptador y el
molde a copiar**: su `MiaClient` es solo `RelayClient` con el nombre local.

### Cómo añadir un canal nuevo (checklist)

1. Crea `channels/<canal>_bridge.py`. La lógica de transporte (recibir/enviar del
   canal) va ahí; **no** toques el motor ni la DB.
2. Instancia un `RelayClient(api_url, email, password, http=...)`. Las credenciales del
   despacho llegan por el entorno del proceso (usa `load_relay_config` con los nombres
   de **tus** variables). El secreto del canal (token del bot, etc.) también vive en el
   entorno del proceso, nunca en el núcleo.
3. Por cada mensaje entrante: valida el remitente autorizado → llama a `client.chat(...)`
   (o `transcribe`/`synthesize` si es voz) → devuelve la respuesta por el transporte.
4. **Regla de modalidad** (de CP-Z2): voz entra → voz sale; texto entra → texto sale.
5. Resiliencia: un turno que falla **no** debe tumbar el loop; degradación con gracia y
   mensaje en llano al usuario (sin jerga). Copia el contrato de `TelegramBridge`.
6. **Nunca loguees el contenido** de los mensajes ni las respuestas — solo ids y
   longitudes (§G / confidencialidad).
7. Gate de pruebas con el transporte y el HTTP **doblados** (mira
   `execution/test_telegram_bridge.py`).

---

## Parte 2 · Sistemas conectados (MCP)

Un **sistema** es algo a lo que Mia se conecta para trabajar: la **gestión documental**
del despacho, la **consulta de estados de procesos**, etc. Mia habla con ellos por el
protocolo **MCP** (Model Context Protocol). El código vive en `backend/mia/mcp/`.

### Principios de seguridad (todos elevan una costura ya probada)

| Principio | Cómo | Costura elevada |
|---|---|---|
| Credenciales fuera del núcleo | El config de cada servidor referencia sus secretos con placeholders `${clave}`, resueltos en el borde bajo el **scope del despacho** | CP-S2 (secret_scope) |
| Entorno saneado del subproceso | Al lanzar un servidor local hereda **solo** la allowlist mínima del SO + lo declarado; ninguna clave de la instalación cruza | CP-S3 (`sanitize_subprocess_env`) |
| Salida sellada | Lo que devuelve un servidor externo entra como **"datos, no órdenes"** | CP-S1 (cuarentena universal) |
| Permisos mínimos | Cada entrada del catálogo recomienda el token de **solo lectura/consulta** | — |
| Consent-first + fail-closed | Cada servidor nace **deshabilitado**; un secreto sin resolver o una forma sospechosa **aborta** el lanzamiento | patrón del proyecto |

### El catálogo

`mcp/catalog.py` es un **catálogo curado**: presencia en el catálogo = aprobación. No
hay servidores arbitrarios definidos por el usuario en v1 (reduce la superficie de una
config hostil que ejecute comandos locales). Cada entrada nace apagada y declara:

- nombre en español (sin marca, §G) y para qué le sirve al despacho;
- las variables que necesita, separando **secretas** (tokens) de **no secretas** (URLs);
- la nota de **permisos mínimos** del token.

Entradas actuales de producto: **ninguna**. Se retiraron «gestión documental»
(`server-filesystem` + token DMS que no se usaba) y «consulta de procesos»
(`python -m mia_mcp_procesos`, módulo inexistente). No se inventa un scraper
judicial ni un DMS. La pantalla de Conexiones lo dice en llano.

### El flujo seguro (`mcp/service.py::resolve_server`)

1. El servidor debe estar en el catálogo y **habilitado** para el despacho.
2. Los `${clave}` se resuelven **bajo el scope de secretos del tenant** (CP-S2): cada
   valor sale de la clave que **ese** despacho configuró, jamás del entorno global.
3. Un placeholder requerido sin resolver **aborta** (`MCPConfigError`) — no se lanza un
   servidor con un secreto colgando.
4. La forma del comando se valida contra **exfiltración** (`MCPSecurityError`).
5. El entorno se **sanea** (CP-S3): allowlist del SO + solo lo declarado, ya resuelto.

El resultado es un `ResolvedMCPServer` (comando + args + entorno saneado) **listo para
lanzar**, sin secretos de la instalación ni placeholders colgando.

### Endpoints (consent-first)

- `GET  /api/mcp/catalog` — el catálogo (sin datos del despacho).
- `GET  /api/mcp/status` — por despacho: habilitado, configurado, qué falta. **Nunca**
  devuelve el valor de un secreto.
- `POST /api/mcp/{slug}/enable` — habilita con las credenciales del despacho (acto
  humano explícito). Valida claves declaradas y secretos requeridos.
- `POST /api/mcp/{slug}/disable` — deshabilita (conserva las credenciales guardadas).

### Alcance / lo que falta para ACTIVAR en vivo

Igual que los conectores de correo (CP-P3): la **maquinaria de seguridad** es real y
está probada; lo que queda para hablar en vivo con un servidor MCP es el **cliente
JSON-RPC** (instalar el SDK `mcp` y registrar el servidor real del despacho). Hasta
entonces todo queda **listo y apagado** — sin superficie de ataque nueva encendida.

---

## Frontend (capa 3 · Cursor)

Pantalla "Sistemas conectados" en Configurar a Mia: lista `GET /api/mcp/status`, con un
formulario por servidor (los `fields`, marcando secretos) que hace `POST .../enable`, y
un interruptor que hace `.../disable`. Todo en llano — el abogado ve "Gestión documental
del despacho", no "servidor MCP". Ver HANDOFF.md §CP-E6.
