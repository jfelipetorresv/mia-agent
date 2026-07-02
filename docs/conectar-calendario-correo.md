# Conectar el calendario y el correo a Mia (CP-P3)

> Guía para Pipe. Sin jerga. El objetivo: que Mia avise sola de audiencias/plazos
> próximos de tu agenda y de correos que parecen urgentes — sin que preguntes.
> **Mia solo mira fechas, remitente y asunto. Nunca el contenido de un correo**
> (eso es opt-in aparte, y llega en el siguiente checkpoint).

## Qué hace esto por ti
- **Calendario:** Mia revisa tu agenda cada 6 horas. Si tienes un evento en las
  próximas 48 horas que parece una audiencia o un plazo, te avisa por Telegram con
  el sello **[VERIFICAR]** (Mia nunca calcula términos: solo te recuerda lo que TÚ
  ya pusiste en tu calendario).
- **Correo:** cada 30 minutos Mia mira los correos no leídos. Si alguno viene de un
  juzgado/procuraduría, tiene bandera de importancia alta, o el asunto suena urgente
  ("vence", "traslado", "requerimiento"…), te avisa. Solo te dice **quién y de qué**,
  para que abras tu bandeja — nunca lee el cuerpo.

Cada evento/correo se avisa **una sola vez** (no te repite lo mismo cada ciclo). Si no
hay nada urgente, Mia calla.

## Lo único que necesito de ti (5–10 min, una vez)
Mia necesita permiso para *leer* (nunca escribir) tu calendario y tu correo. Eso se
autoriza registrando una "aplicación" en el panel de tu proveedor. Es como cuando
autorizas a una app de terceros a ver tu calendario: tú das el permiso, y lo puedes
revocar cuando quieras.

### Si Lexia usa **Microsoft 365** (tu caso)
1. Entra a **portal.azure.com** → busca **"Registros de aplicaciones"** (App registrations)
   → **Nuevo registro**.
2. Nombre: `Mia`. Tipo de cuenta: *cuentas de este directorio organizativo*.
   URI de redirección (tipo *Web*): pega exactamente
   `http://localhost:8000/api/mailbox/oauth/callback`
   (cuando Mia esté en un servidor real, aquí va el dominio real).
3. Al crearla, copia el **"Id. de aplicación (cliente)"**.
4. En **"Certificados y secretos"** → **Nuevo secreto de cliente** → copia el **Valor**
   (solo se muestra una vez).
5. En **"Permisos de API"** → agrega, de *Microsoft Graph → Delegados*:
   `Calendars.Read`, `Mail.Read`, `offline_access`, `openid`, `email`.
   (Con Lectura basta; no pidas escritura.)
6. Mándame esas dos cosas de forma segura (el Id. de cliente y el Valor del secreto)
   y yo las pego en la configuración del servidor. **No las mandes por correo normal.**

### Si un despacho usa **Google Workspace** (para clientes futuros)
Mismo espíritu en **console.cloud.google.com**: crear proyecto → *Pantalla de
consentimiento OAuth* → *Credenciales* → *ID de cliente de OAuth (aplicación web)* con
la misma URI de redirección; habilitar las APIs de **Google Calendar** y **Gmail**;
scopes de solo lectura (`calendar.readonly`, `gmail.metadata`). Copiar el *Client ID*
y el *Client Secret*.

## Después de que me pases las llaves
1. Yo las pego en el archivo de configuración del servidor (`.env`) — nunca van al
   código ni a GitHub.
2. Tú entras a Mia → **Configura a Mia** → botón **"Conectar Microsoft 365"**, das
   clic, apruebas en la pantalla de Microsoft, y listo. (Ese botón lo arma Cursor en
   el frontend — es lo único que queda pendiente de UI.)
3. Desde ese momento Mia empieza a avisarte. Puedes **desconectar** cuando quieras
   desde la misma pantalla.

## Riesgo de negocio y confianza
- **Bajo en calendario** (solo fechas y títulos). **Medio en correo**: aunque Mia solo
  mira remitente y asunto, esa metadata ya es sensible — por eso los permisos son de
  *solo lectura* y los tokens de acceso quedan cifrables y aislados por despacho.
- El **contenido** de los correos (leerlo/resumirlo con IA) es una decisión aparte que
  **tú** activas explícitamente más adelante (CP-P4), con las salvaguardas de nube que
  definimos. Hoy está **apagado**.

## Nota técnica (para el que configure el servidor)
Variables en `.env` (ver `config.py`):
`MS_OAUTH_CLIENT_ID`, `MS_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`,
`GOOGLE_OAUTH_CLIENT_SECRET`, `MAILBOX_OAUTH_REDIRECT_URI`.
Antes: aplicar la migración con `python execution/init_mailbox.py`.
