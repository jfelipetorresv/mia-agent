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
  variable de entorno `MIA_APP_DIR` al backend (el instalador escribirá aquí la
  ruta empaquetada; en dev es `null`).
- `db`: `pg_bin` (carpeta de binarios de Postgres), `data_dir`, `port`.
- `backend`: `cmd` (programa + argumentos), `cwd`, `env`, `health_url`, `port`.
- `frontend`: `cmd`, `cwd`, `url`, `port`.

### Secuencia de arranque

Para cada servicio (DB → backend → frontend): si el puerto **ya responde Y la
identidad calza** (pg_isready para la DB, JSON de /health con claves propias
para el backend, huella de cabeceras para el frontend — ver "Blindaje" abajo),
la cáscara lo adopta sin apagarlo; si no, lo lanza y espera su salud + identidad
(polling cada 2 s). Cuando backend y frontend responden y son MIA, la ventana
navega a `frontend.url`.

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
