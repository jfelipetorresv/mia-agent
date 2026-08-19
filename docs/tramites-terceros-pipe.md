# Los dos trámites que tiene que pedir usted — 2026-07-27

> Decisión #47.3: se disparan los dos ahora. Tardan **semanas**, y si se piden tarde se
> convierten en el cuello de botella de la entrega. Ninguno lo puede hacer un agente: los dos
> exigen su identidad y sus credenciales de Lexia.
>
> Ninguno bloquea el desarrollo. Lo que bloquean es la **entrega a un despacho real**.

---

## 1 · Firma de Windows (Azure Trusted Signing)

### Por qué importa

Sin firma, cuando el abogado abre el instalador de MIA Windows le muestra la pantalla azul de
«Windows protegió su PC — aplicación no reconocida», con el botón real escondido detrás de «Más
información». Es la primera cosa que ve de un producto que le va a confiar sus expedientes. No
hay atajo técnico: la única forma de que esa pantalla no salga es que el ejecutable venga firmado
por una identidad verificada.

Es el trámite **de mayor demora** de los dos, porque incluye una verificación de identidad de la
organización que la hace Microsoft (o su validador), no un formulario automático.

### Qué se necesita antes de empezar

- Una suscripción de **Azure** activa a nombre de Lexia Abogados SAS (si no existe, crearla es
  parte del trámite; requiere una tarjeta y los datos fiscales de la firma).
- Los datos de la firma **exactamente como aparecen en el registro mercantil**: razón social,
  NIT, dirección, país. Microsoft los coteja contra fuentes públicas y una discrepancia de
  puntuación devuelve el trámite semanas atrás.
- Un correo de dominio propio (`@lexia.co`) con capacidad de recibir la verificación.
- La antigüedad de la organización: Trusted Signing pide que la entidad tenga **3 años o más** de
  existencia verificable. Lexia los tiene; conviene tenerlo a mano porque lo preguntan.

### Los pasos, en orden

1. En el portal de Azure, crear un recurso **Trusted Signing Account** (elegir la región y el
   plan; el plan básico basta para nuestro volumen).
2. Dentro de la cuenta, crear un **Identity Validation** de tipo *Organization* con los datos del
   registro mercantil. Aquí empieza la espera: Microsoft valida y puede pedir documentos
   adicionales (certificado de existencia y representación legal, típicamente).
3. Cuando la validación quede **Completed**, crear un **Certificate Profile** — es lo que firma.
4. Darle acceso al perfil a la identidad que firmará (un *service principal* o su propia cuenta
   con el rol *Trusted Signing Certificate Profile Signer*).
5. Avíseme cuando llegue a este punto: el resto (conectar la firma al empaquetado del instalador
   y verificar que el ejecutable sale firmado) es trabajo mío, y necesito del paso 4 el nombre de
   la cuenta, el perfil y el endpoint de la región.

### Qué NO haga

- No compre un certificado EV de otro proveedor sin avisarme primero. Funcionan, pero cuestan
  varias veces más al año y algunos exigen un token físico USB para cada firma, lo que
  imposibilita firmar de forma automatizada al empaquetar.

---

## 2 · Correo y archivos del despacho (apps OAuth de Google y Microsoft)

### Por qué importa

MIA lee el correo y los archivos del despacho para armar el expediente (Gmail, Outlook,
OneDrive). Hoy eso funciona en su máquina con credenciales de desarrollo. En manos de un cliente
real **no funciona** hasta que exista una aplicación registrada a nombre de Lexia, porque es esa
aplicación la que pide el permiso al abogado y la que Google y Microsoft auditan.

La demora aquí no es la creación —eso es de una tarde— sino la **verificación** de Google cuando
la app pide permisos sensibles de Gmail: revisan la política de privacidad, la propiedad del
dominio y, en algunos casos, piden una evaluación de seguridad. Semanas.

### Google (Gmail y Drive)

1. En Google Cloud Console, crear un **proyecto** a nombre de Lexia (no personal).
2. Habilitar las APIs de **Gmail** y **Drive**.
3. Configurar la **OAuth consent screen** de tipo *External*: nombre visible («MIA — Lexia»),
   correo de soporte, logo, y los enlaces a **política de privacidad** y **términos** — tienen
   que estar publicados en un dominio de Lexia y ser alcanzables públicamente, o la revisión se
   devuelve. Si no existen, dígamelo: se redactan y se publican, y es lo primero que haría.
4. Verificar la **propiedad del dominio** `lexia.co` en Search Console con la misma cuenta.
5. Crear credenciales **OAuth Client ID** de tipo *Desktop app* (MIA corre en la máquina del
   abogado, no en un servidor). Guarde el *client ID* y el *client secret*.
6. Enviar la app a **verificación** declarando los alcances. Este es el reloj largo.

### Microsoft (Outlook y OneDrive)

1. En el portal de Entra ID (antes Azure AD), **App registrations → New registration**, cuenta
   de Lexia, tipo *Accounts in any organizational directory and personal Microsoft accounts*.
2. Añadir los permisos delegados de Graph que MIA necesita para leer correo y archivos.
3. Configurar el **redirect URI** de aplicación de escritorio.
4. Guardar el *Application (client) ID* y crear un *client secret* si hace falta.

### Qué me manda cuando los tenga

Los identificadores de cliente (y los secretos, **por un canal seguro — no por correo ni por
chat**). Yo los conecto al instalador y verifico el flujo completo con una cuenta de prueba antes
de que toque una cuenta real del despacho.

### Advertencia que le debo

Estas credenciales dan acceso a correo y archivos del despacho: son material sensible. Cuando me
las pase, van al almacén de secretos de la instalación, nunca al repositorio — y no las escriba en
un archivo del proyecto «mientras tanto».

---

## Cómo sigue esto

Los dos trámites avanzan solos mientras el producto se termina. Cuando cualquiera de los dos
llegue a su paso final, avíseme y lo conecto. Si Google devuelve la verificación pidiendo algo
—suele ser la política de privacidad—, tráigame el texto de lo que piden y lo resolvemos sin que
usted tenga que interpretarlo.
