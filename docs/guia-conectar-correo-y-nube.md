# Guía: habilitar las conexiones de Microsoft y Google en Mia

*Para el administrador del despacho (en desarrollo: Pipe). Es un paso ÚNICO por
servidor de Mia. Hasta completarlo, los botones "Conectar Microsoft/Google"
responden "aún no está habilitada" (503 por diseño).*

Mia necesita que el despacho tenga registrada una "aplicación" ante Microsoft
y/o Google. Ese registro produce dos datos (un identificador y un secreto) que
se guardan en el archivo `.env` del servidor de Mia. Nada de esto sale del
equipo del despacho.

---

## Parte 1 — Microsoft (correo Outlook/365 + OneDrive)

1. Entra a **https://portal.azure.com** con la cuenta Microsoft del despacho.
2. Busca **"App registrations"** (Registros de aplicaciones) → **New registration**.
3. Llena así:
   - **Name:** `Mia - <nombre del despacho>` (ej.: `Mia - Despacho`).
   - **Supported account types:** "Accounts in any organizational directory and
     personal Microsoft accounts" (la opción más amplia, tercera).
   - **Redirect URI:** tipo **Web**, valor:
     `http://localhost:8000/api/mailbox/oauth/callback`
4. Crea la app. En la pantalla de resumen, copia el **Application (client) ID** —
   ese es tu `MS_OAUTH_CLIENT_ID`.
5. Menú izquierdo → **Certificates & secrets** → **New client secret** →
   descripción libre, vencimiento 24 meses → **copia el VALOR del secreto de
   inmediato** (solo se muestra una vez) — ese es tu `MS_OAUTH_CLIENT_SECRET`.
6. Menú izquierdo → **API permissions** → **Add a permission** → **Microsoft
   Graph** → **Delegated permissions** → marca:
   - `offline_access`, `openid`, `email`
   - `Mail.Read` (correo) y `Calendars.Read` (calendario)
   - `Files.Read` (solo si usarás carpetas de OneDrive — Mia pide el permiso
     mínimo: tus archivos, no todo el drive de la organización)
   No hace falta "grant admin consent" para cuentas personales; para tenant
   corporativo, dale **Grant admin consent**.

## Parte 2 — Google (Gmail + Calendar)

1. Entra a **https://console.cloud.google.com** con la cuenta Google del despacho.
2. Crea un proyecto nuevo: `mia-despacho`.
3. **APIs & Services → Library**: habilita **Gmail API** y **Google Calendar API**.
4. **APIs & Services → OAuth consent screen**: tipo **External**, llena nombre
   (`Mia`) y correo de soporte. En **Test users**, agrega el correo del abogado
   que va a conectar (mientras la app esté en modo "Testing", solo esos correos
   pueden conectar — suficiente para el despacho).
5. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - **Application type:** Web application.
   - **Authorized redirect URIs:**
     `http://localhost:8000/api/mailbox/oauth/callback`
6. Copia el **Client ID** (`GOOGLE_OAUTH_CLIENT_ID`) y el **Client secret**
   (`GOOGLE_OAUTH_CLIENT_SECRET`).

## Parte 3 — Poner las llaves en Mia

1. Abre el archivo `.env` en la raíz del proyecto Mia (junto a `CLAUDE.md`).
   **Este archivo nunca se sube a GitHub.**
2. Agrega (o completa) estas líneas con los valores copiados:

   ```
   MS_OAUTH_CLIENT_ID=<el Application (client) ID de Azure>
   MS_OAUTH_CLIENT_SECRET=<el valor del secreto de Azure>
   GOOGLE_OAUTH_CLIENT_ID=<el Client ID de Google>
   GOOGLE_OAUTH_CLIENT_SECRET=<el Client secret de Google>
   ```

   (Puedes configurar solo un proveedor; el otro seguirá diciendo "no habilitado".)
3. Reinicia el backend de Mia (o cierra y vuelve a abrir la app de escritorio).
4. En Mia → **Configuración → Conexiones → Calendario y correo**, pulsa
   **Conectar Microsoft** o **Conectar Google**: ahora sí abre la pantalla real
   de consentimiento. Marca "Incluir mis archivos de OneDrive" si quieres las
   carpetas en la nube.

## Si algo falla

- "Redirect URI mismatch" → el URI registrado no coincide EXACTO con
  `http://localhost:8000/api/mailbox/oauth/callback` (revisa http vs https y el
  puerto).
- Google dice "app no verificada" → normal en modo Testing; pulsa "Continuar"
  (avanzado). Solo los correos agregados como Test users pueden pasar.
- El secreto de Azure venció → crea uno nuevo en Certificates & secrets y
  reemplázalo en `.env`.
