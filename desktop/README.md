# Mia — cáscara de escritorio (Tauri v2)

Esta carpeta contiene la **cáscara orquestadora**: la app de escritorio que el
abogado abre. Al abrirse enciende, en orden, la base de datos portable, el
backend y el frontend de Mia; muestra una pantalla de arranque en español llano;
y al cerrarse apaga con orden **solo lo que ella misma arrancó**.

No contiene lógica de negocio: es únicamente el arranque/apagado y la ventana.
El backend y el frontend viven en `../backend` y `../frontend` y no se tocan.

## Cómo correrlo en desarrollo

Requisitos: Rust (`cargo`), Node/npm, VS Build Tools y WebView2 (ya instalados
en la máquina de desarrollo).

```bash
cd desktop
npm install          # instala @tauri-apps/cli (una vez)
npm run tauri dev     # compila la cáscara y abre la ventana
```

En dev, la cáscara detecta si la DB / backend / frontend ya están encendidos y
los **adopta** (no los vuelve a lanzar ni los apaga al salir). Lo que sí arranca
ella, lo apaga al cerrar.

Para un binario instalable: `npm run tauri build`.

## Configuración: `orchestration.json`

El lado Rust lee `orchestration.json` al arrancar. Se busca, en este orden:

1. junto al ejecutable,
2. en el directorio de trabajo,
3. como *fallback* de desarrollo, en `desktop/` (subiendo directorios).

Campos:

- `app_dir`: carpeta de datos del usuario. Si viene no-nulo, se pasa como
  variable de entorno `MIA_APP_DIR` al backend, al **setup** y a **LiteLLM** (el
  instalador escribirá aquí la ruta empaquetada; en dev es `null`).
- `setup` (opcional): `cmd`, `cwd`. Paso de **primer arranque** (ver F2 abajo).
- `db`: `pg_bin` (carpeta de binarios de Postgres), `data_dir`, `port`.
- `litellm` (opcional): `cmd`, `cwd`, `env`, `health_url`, `port`. Motor de
  modelos, 4º servicio (ver F2 abajo). Si el bloque no está, la cáscara orquesta
  3 servicios como siempre.
- `backend`: `cmd` (programa + argumentos), `cwd`, `env`, `health_url`, `port`.
- `frontend`: `cmd`, `cwd`, `url`, `port`.

**Tokens del config (F2):** al cargar `orchestration.json`, la cáscara expande
en un **único punto** (`OrchCfg::expand_tokens`) dos tokens en TODOS los campos
string —rutas, vectores `cmd`, `cwd`, valores de `env`, URLs—:

- `${exe_dir}` → carpeta del ejecutable de la cáscara.
- `${local_app_data}` → `%LOCALAPPDATA%`.

Así el JSON del instalador es **estático** (F4/NSIS lo copia tal cual, sin
templar) y la cáscara lo aterriza a la máquina concreta al arrancar. En dev el
JSON usa rutas absolutas sin tokens, así que la expansión no cambia nada.

### Secuencia de arranque

Orden completo: **setup (si hace falta) → DB → LiteLLM → backend → frontend**.
El apagado es inverso (frontend → backend → LiteLLM → DB). El setup y LiteLLM
son opcionales: sin sus bloques en el JSON, la secuencia es la de siempre
(DB → backend → frontend).

Para cada servicio de red (DB → LiteLLM → backend → frontend): si el puerto **ya
responde Y la identidad calza** (pg_isready para la DB, `/v1/models` + Bearer
para LiteLLM, JSON de /health con claves propias para el backend, huella de
cabeceras para el frontend — ver "Blindaje" abajo), la cáscara lo adopta sin
apagarlo; si no, lo lanza y espera su salud + identidad (polling cada 2 s).
Cuando backend y frontend responden y son MIA, la ventana navega a
`frontend.url`.

Si un puerto está tomado por un proceso que **no** responde salud, o que
responde pero **no es MIA** (un extraño — caso esperado: en la máquina del
fundador hubo apps ajenas en el 8000 y el 3100), la cáscara no lanza un
competidor ni navega a la app ajena: avisa de inmediato en español llano. Durante
esperas largas la pantalla de arranque muestra los segundos transcurridos, y si
el proceso lanzado muere, el error aparece al instante (no tras el timeout).

Al cerrar: `taskkill /T /F` por PID de los procesos que la cáscara arrancó
(mata el árbol de npm/node) y `pg_ctl stop -m fast` **solo** si la cáscara
encendió la DB.

Red de seguridad: backend y frontend se asignan a un **Job Object de Windows
con `KILL_ON_JOB_CLOSE`** — si la cáscara muere de forma anormal (crash,
taskkill, apagado de Windows), el SO mata esos procesos igual. La DB queda
fuera del job a propósito: dejarla viva es benigno y el siguiente arranque la
adopta.

## Logs

`desktop/logs/mia-shell.log` — qué encendió, PIDs y tiempos. Los `*.out.log` de
esa carpeta capturan la salida de los procesos hijos para diagnóstico (en modo
append: conservan arranques anteriores). La carpeta `logs/` está en
`.gitignore` del repo.

## Blindaje de la cáscara (bloque del instalador · frente C)

Las 3 deudas que tenía esta sección quedaron saldadas, más una cuarta pieza
(validación de identidad) nacida de una lección real. Gate en frío que las
verifica: `execution/test_shell_hardening.py`.

> **Lección real (2026-07-10, máquina del fundador):** los puertos 3100 y
> 8000 estaban ocupados por apps AJENAS — el Next.js de otro proyecto
> ("Intelligence Sura") en el 3100 y voicebox-server.exe en el 8000, ambos
> respondiendo 200 — y la cáscara los adoptó y le mostró al usuario la app
> equivocada. La colisión de puertos es un caso **esperado**, no
> excepcional: la adopción debe validar IDENTIDAD, no solo respuesta.
> Ver sección 4.

### 1 · Guard de instancia única

`tauri-plugin-single-instance` (v2.x, `desktop/src-tauri/Cargo.toml`) se
registra como el **primer** `.plugin(...)` del builder en `lib.rs` — antes de
`.setup()`, que es donde arranca la orquestación DB → backend → frontend.
Los plugins de Tauri corren en el orden en que se registran, así que si una
segunda cáscara se abre, el plugin la detecta (mutex con nombre por
`identifier` en Windows) y la mata **antes** de que su `.setup()` llegue a
ejecutarse: la segunda instancia nunca toca la DB, el backend ni el
frontend. La primera instancia recibe el callback y trae su ventana al
frente (`unminimize()` + `set_focus()`).

### 2 · CSP explícita

`tauri.conf.json` → `app.security.csp`:

```json
"csp": {
  "default-src": "'self'",
  "connect-src": "ipc: http://ipc.localhost"
}
```

Qué cubre: la pantalla local de arranque (`frontendDist: ../src`,
`desktop/src/index.html`). Esa pantalla no carga imágenes ni fuentes
externas, así que `default-src 'self'` basta; `connect-src ipc:
http://ipc.localhost` es lo que necesita el puente de Tauri
(`window.__TAURI__.event.listen(...)`) para que la pantalla reciba los
eventos `mia://progress`.

**Splash sin inline (revisión adversarial 2026-07-10):** Tauri **no**
hashea los `<style>` inline (solo scripts), así que un splash con CSS
inline bajo `default-src 'self'` se pintaba sin estilos, y el `<script>`
inline quedaba en riesgo. En vez de relajar la CSP con `'unsafe-inline'`,
el CSS y el JS del splash se externalizaron a `desktop/src/splash.css` y
`desktop/src/splash.js`, referenciados con `<link rel="stylesheet">` y
`<script src="splash.js">`. Ambos viven en la misma carpeta que
`index.html` (`frontendDist: ../src` — Tauri empaqueta y sirve **todos**
los archivos de esa carpeta por el protocolo `tauri://`, no solo
`index.html`), así que pasan la CSP como recursos de `'self'`.
`index.html` no contiene ningún bloque `<style>`, ningún `<script>` inline
ni atributos `style=` — y el gate `execution/test_shell_hardening.py` lo
verifica de por vida (checks de la sección 5).

**Pendiente — verificación VISUAL del splash bajo CSP (capa 3 / E2E de
Fase 4):** lo anterior es verificación estática (compilación + gates). La
confirmación empírica de que el splash SE VE con estilos y pinta los
errores en llano bajo esta CSP queda declarada para la capa 3 en vivo /
E2E de Fase 4. Paso concreto: lanzar la cáscara con un puerto ocupado por
una app ajena (p. ej. algo escuchando en 55432 que no sea Postgres) y
confirmar visualmente que el mensaje de error en español llano se muestra
CON los estilos del splash (fondo negro, marca MIA, texto legible).

Qué NO cubre: la CSP de `tauri.conf.json` solo aplica a contenido servido
desde `frontendDist` (la pantalla de arranque). Una vez `orchestrate()`
llama a `window.navigate("http://localhost:3100")`, la página remota del
frontend Next.js queda gobernada por sus **propias** cabeceras HTTP (ver
`frontend/next.config.mjs` — CSP `frame-ancestors 'none'`, etc., verificadas
en `execution/test_frontend_packaging.py`), no por esta CSP de Tauri.

Gating de IPC remoto (que `localhost:3100` NO pueda invocar comandos de
Tauri): revisado en `tauri.conf.json` y en `desktop/src-tauri/capabilities/
default.json` — no hay ninguna entrada `security.capabilities`/`remote` ni
`dangerousRemoteUrlIpcAccess` que otorgue capacidades a orígenes remotos; el
gating remoto de Tauri v2 por defecto (deny-all para ventanas sin capability
remota explícita) queda vigente. Lo que falta es la **verificación
empírica** — queda para el E2E de Fase 4:

> Con la cáscara corriendo y ya navegada a `http://localhost:3100`, abrir
> las DevTools de esa ventana (o inyectar vía `mcp__claude-in-chrome`) y
> evaluar `window.__TAURI__ === undefined` (o, si `withGlobalTauri` inyectara
> el objeto, que `window.__TAURI__.core.invoke(...)` rechace con un error de
> permisos) — debe ser `true`/rechazar. Si alguna vez se agrega
> `withGlobalTauri` a nivel de ventana remota o una capability con `remote`
> apuntando a `localhost:3100`, este paso debe volver a correr.

### 3 · Validación de que 55432 es Postgres de verdad

Antes: la adopción de la DB era solo "¿hay algo escuchando en el puerto?".
Ahora (`desktop/src-tauri/src/db_check.rs`, llamado desde `orchestrate()` en
`lib.rs`): si el puerto ya está abierto, se corre `pg_isready.exe` — vive en
el mismo `pg_bin` que `pg_ctl.exe` en `orchestration.json`, sin dependencia
nueva — contra `127.0.0.1:<port>`:

- exit 0 ("accepting connections") → confirmado Postgres, se adopta.
- exit 1 ("rejecting connections", típico de Postgres arrancando) → se
  reintenta cada 1.5 s dentro del mismo deadline de 60 s que ya usaba el
  arranque en frío.
- cualquier otro exit (exit 2 "no response", etc.) → se reintenta hasta el
  deadline; si nunca confirma, se declara ocupado por un extraño y **no se
  adopta ni se lanza pg_ctl encima**. El abogado ve: *"otro programa está
  ocupando el lugar de la base de datos de Mia — reinicia el equipo"*.
- el binario `pg_isready.exe` **no se pudo ejecutar en NINGÚN intento** del
  deadline (instalación rota, ruta de `pg_bin` incorrecta) → caso separado
  (`PgReadyOutcome::ToolMissing`, revisión adversarial 2026-07-10): antes
  se colapsaba con "puerto ocupado" y el abogado recibía "reinicia el
  equipo" cuando reiniciar no arregla nada. Ahora ve: *"no encuentro las
  herramientas de la base de datos de Mia — reinstala Mia o avísale a
  soporte"*.

Nota técnica: cada intento de `pg_isready` (bloqueante, hasta 3 s) corre
dentro de `tauri::async_runtime::spawn_blocking` para no congelar el
runtime async de la cáscara mientras espera.

### 4 · Validación de IDENTIDAD del backend y del frontend

La misma lógica que la DB, aplicada a los otros dos puertos
(`desktop/src-tauri/src/identity.rs`, llamado desde `orchestrate()`):
"responde en el puerto" no es "es MIA".

**Backend (8000):** ya no basta un 200 en `health_url` — se parsea el JSON
de `/health` y se exigen las claves propias de MIA: `"db"`, `"pgvector"` y
`"embed_model"`, que el endpoint devuelve **siempre**, incluso en estado
degradado (ver `backend/mia/api/main.py::health`). Un health ajeno (como el
de voicebox) casi nunca traerá esa combinación.

**Frontend (3100):** ya no basta un 200 — se exige la huella de cabeceras
que `frontend/next.config.mjs` fija en TODAS las rutas de MIA
(`/:path*`): `X-Frame-Options: DENY` + `Content-Security-Policy` con
`frame-ancestors 'none'` + `Permissions-Policy` con `camera=()`. Por qué esa
señal y no otra: (a) aplica a todas las rutas, incluso redirecciones, así
que no depende de qué página responda; (b) está protegida por contrato — el
gate `execution/test_frontend_packaging.py` falla si alguien quita esas
cabeceras de next.config.mjs, de modo que la huella no se puede romper en
silencio; (c) un marcador en el HTML (p. ej. el `<title>`) puede cambiar por
página sin que ningún test lo note.

**Semántica de tres estados:** `Mia` (adoptar/navegar), `NotMia` (responde
pero es OTRO programa → fallar YA con mensaje en llano — *"otro programa
está ocupando el lugar de Mia — ciérralo o reinicia el equipo"* / *"...el
lugar de la pantalla de Mia..."* — y NO adoptar ni navegar jamás a una app
ajena), `NoResponse` (aún no responde → reintentar dentro del deadline).

**La exigencia aplica en los DOS caminos:** al adoptar un puerto ya abierto
y también en la espera después de que la cáscara lanza el proceso — si un
tercero gana la carrera por el puerto y responde 200 sin ser MIA, se falla
de inmediato en vez de navegar a lo que sea que haya contestado.

## Fase 2 · Primer arranque automático

En una máquina limpia, la cáscara detecta que no hay datos y deja MIA
funcionando sola: crea la carpeta de datos, el `.env` semilla, el cluster de
Postgres, las migraciones, y enciende el motor de modelos. Todo esto se activa
por dos bloques **opcionales** de `orchestration.json` (`setup` y `litellm`) más
la expansión de tokens; si esos bloques faltan (como en el JSON de dev), el
comportamiento es idéntico al de siempre. Gate en frío: sección 6 de
`execution/test_shell_hardening.py`.

### Paso de setup (primer arranque)

El bloque `setup` (`{ "cmd": [...], "cwd": "..." }`) apunta al bootstrap Python
(`mia-backend.exe --first-run --pg-bin ... --pg-data ... --pg-port 55432`). La
cáscara lo corre **antes que todo** si falta CUALQUIERA de:

- el marcador `<app_dir>/.mia-setup-complete` (con `app_dir` configurado) — el
  bootstrap lo escribe **solo** al terminar TODO con éxito;
- `<db.data_dir>/PG_VERSION` (no hay cluster de Postgres);
- —con `app_dir` configurado— `<app_dir>/.env` (no hay semilla).

Sin `app_dir` configurado, el marcador y el `.env` no se pueden mirar: el
gatillo se reduce a `PG_VERSION` (comportamiento de siempre en dev). Este
triple gatillo existe porque un setup interrumpido justo después de escribir
`.env`+`PG_VERSION` (p. ej. una falla a media migración) antes NUNCA se
volvía a ejecutar y dejaba la instalación rota para siempre; el bootstrap es
idempotente y resiliente a estados a medias (repara un `initdb` interrumpido,
falla en llano si hay cluster sin `.env`), así que basta con volver a
llamarlo.

Mientras corre, el splash muestra `"Preparando Mia por primera vez, puede tardar
unos minutos…"` (stage `setup`). Timeout: **15 minutos**. El proceso entra al
Job Object (red anti-huérfanos) y recibe `MIA_APP_DIR` cuando hay `app_dir`. Su
stdout/stderr van a `logs/setup.out.log`; si sale con código ≠0, la cáscara
muestra la **última línea no vacía** de ese stdout (el bootstrap garantiza que
es un mensaje en español llano). Al terminar bien, la cáscara sigue con su flujo
normal y enciende la DB ella misma (el bootstrap deja el Postgres temporal
apagado).

### LiteLLM como 4º servicio

El bloque `litellm` (`{ "cmd", "cwd", "env", "health_url", "port" }`) se enciende
**entre la DB y el backend**, con el mismo patrón tri-estado que el backend:

- **Puerto libre** → la cáscara lanza el proceso hijo y espera **liveliness**
  (un 200 en `health_url`, p. ej. `/health/liveliness`). Como es su propio hijo,
  no hay riesgo de adoptar a un extraño: basta el 200. Entra al Job Object y
  recibe su `env` + `MIA_APP_DIR` (si hay `app_dir`).
- **Puerto ocupado** → **adopción SOLO con identidad**: GET
  `http://127.0.0.1:<port>/v1/models` con `Authorization: Bearer
  <LITELLM_MASTER_KEY>`, donde la master key se lee del `<app_dir>/.env` (parser
  `.env` mínimo en Rust). Se adopta solo si responde 200 y el cuerpo contiene los
  dos alias propios de MIA (`claude-haiku` **y** `mia-local`). Sin `app_dir`, sin
  `.env` o sin la key → **no se adopta** (mensaje en llano: *"El puerto N está
  ocupado por otra aplicación — ciérrala o reinicia el equipo"*). Nunca se
  adopta por un simple 200 (misma lección que voicebox/Sura en la sección 4).

En el apagado, `litellm` se mata por PID en el orden inverso del arranque
(frontend → backend → **litellm** → DB).

### Frontend instalado (PORT + HOSTNAME)

Al lanzar el frontend, la cáscara fija la env `PORT` al puerto configurado y
**limpia `HOSTNAME`**. El `server.js` del standalone de Next (instalado) toma su
puerto de `PORT` y su host de `HOSTNAME`; si el sistema trae `HOSTNAME` seteado
(nombre de equipo que puede resolver a una IP de VPN), el server escucharía solo
en esa IP y ni `localhost` ni `127.0.0.1` conectarían (gotcha documentado en
`packaging/build_frontend.ps1`). En dev (`npm run start -- -p 3100`) ambos
coinciden en 3100, así que es inocuo.

### Dev sigue con LiteLLM manual (decisión)

El `orchestration.json` de **dev NO lleva bloque `litellm`**: sigue en 3
terminales y LiteLLM se arranca a mano (`scripts/run_litellm_clean.ps1`). Razón:
ese launcher **quita** variables de entorno (scrubbing de `DATABASE_URL`, `PG_*`
y ~15 más para que LiteLLM no intente Prisma), además de aislar el CWD y parchear
`proxy_server.py` en caliente. El campo `env` de `orchestration.json` solo
**añade** variables, no las quita, así que no puede replicar ese saneo de forma
limpia. En **instalado**, en cambio, el exe empaquetado de LiteLLM
(`entry_litellm.py`, a cargo de otro frente) hace su propio saneo por dentro, y
ahí sí la cáscara lo enciende como 4º servicio vía el bloque `litellm` de
`packaging/orchestration.installer.json`.

### Plantilla del instalador

`packaging/orchestration.installer.json` es la plantilla **estática** que el
instalador (F4) copiará junto al ejecutable, sin templar nada. Usa los tokens
`${exe_dir}` / `${local_app_data}` en todas las rutas, define el `setup` con
`--first-run`, el `litellm` con `health_url` de liveliness en el 4000, el
`backend` en el 8000 y el `frontend` con el `node.exe` portable + `server.js`.
La cáscara la expande al cargarla. Los comentarios JSON no son válidos: para
anotar se usan campos `_nota` string (serde los ignora al deserializar).

> **Verificación diferida a F4 / Riesgo #59:** la confirmación visual del stage
> `setup` (que el splash pinta "Preparando Mia por primera vez…" y, en fallo, la
> última línea en llano del bootstrap) y el E2E con los exes reales en una
> máquina limpia son de la capa 3 en vivo / Fase 4. F2 verifica en frío (gate)
> y por compilación.
