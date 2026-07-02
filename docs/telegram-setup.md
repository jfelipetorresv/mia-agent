# Mia en tu celular por Telegram — guía de 5 pasos

Con esta guía conectas a Mia con tu Telegram personal en unos 5 minutos.
Es un canal **privado**: solo tú puedes hablarle; cualquier otra persona que
encuentre el bot será ignorada por completo.

---

## Paso 1 · Crea tu bot con BotFather

1. Abre Telegram en tu celular o computador.
2. En el buscador escribe **@BotFather** y ábrelo (tiene un chulo azul de verificado).
3. Escríbele el mensaje `/newbot` y sigue las dos preguntas:
   - Un nombre visible, por ejemplo: `Mia Lexia`.
   - Un nombre de usuario que termine en "bot", por ejemplo: `mia_lexia_bot`.

## Paso 2 · Copia la clave secreta

Al terminar, BotFather te envía un mensaje con una clave larga (algo como
`1234567890:AAH8x...`). Esa es la llave de tu bot: **cópiala y no se la
compartas a nadie** — quien la tenga puede controlar el bot.

## Paso 3 · Averigua tu número de chat

1. En el buscador de Telegram escribe **@userinfobot** y ábrelo.
2. Escríbele cualquier cosa (por ejemplo "hola").
3. Te responde con tus datos; el que necesitas es el **Id** (un número, por
   ejemplo `123456789`). Ese número identifica tu chat personal y es lo que
   hace que **solo tú** puedas hablar con Mia.

## Paso 4 · Pega los datos en el archivo de configuración

1. En la carpeta principal de Mia (`D:\Codex\Mia-Super Agent\mia`) abre el
   archivo llamado **.env** con el Bloc de notas.
2. Busca la sección de Telegram (empieza con `--- Telegram`) y quítale el `#`
   del inicio a estas líneas, completando cada valor:

   ```
   TELEGRAM_BOT_TOKEN=aquí va la clave del paso 2
   TELEGRAM_ALLOWED_CHAT_ID=aquí va el número del paso 3
   MIA_BRIDGE_EMAIL=tu correo de inicio de sesión en Mia
   MIA_BRIDGE_PASSWORD=tu contraseña de Mia
   ```

3. Guarda el archivo.

## Paso 5 · Enciende el puente

1. Asegúrate de que Mia esté corriendo (el arranque de siempre).
2. Abre una ventana de PowerShell nueva y ejecuta:

   ```
   & "D:\Codex\Mia-Super Agent\mia\scripts\start_telegram.ps1"
   ```

   (Copia el comando completo, incluidas las comillas — la carpeta
   tiene un espacio en el nombre y sin comillas no funciona.)

3. Cuando diga "Puente de Telegram activo", abre el chat con tu bot en
   Telegram y salúdalo. Mia te responde ahí mismo.

---

## Comandos útiles dentro del chat

| Escribes  | Qué pasa                                                        |
|-----------|-----------------------------------------------------------------|
| `/nueva`  | Mia olvida el hilo actual y empieza una conversación desde cero |
| `/apagar` | El puente se detiene de inmediato (frase de emergencia)         |

## Bueno saberlo

- Las respuestas largas llegan como un archivo adjunto que puedes abrir ahí mismo.
- Si Mia tarda, es normal: algunas respuestas toman 1 a 3 minutos.
- Si ves "Mia está teniendo un problema técnico", espera un momento y vuelve a
  escribir; el puente se recupera solo.
- Para volver a encenderlo después de `/apagar`, repite el Paso 5.
