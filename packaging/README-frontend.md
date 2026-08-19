# Empaquetado del frontend (Fase 1 · bloque instalador · frente B)

Este documento cubre SOLO el frontend Next.js 16.3. El backend (PyInstaller) tiene
su propio `build_backend.ps1` / `entry_backend.py` / `mia-backend.spec`, a cargo
de otro frente — no tocar esos archivos desde aquí.

## Qué resuelve

El instalador de Mia no puede exigirle al abogado que instale Node.js ni que
corra `npm install` en su máquina. La solución es `output: "standalone"` de
Next.js (`frontend/next.config.mjs`): el build genera
`frontend/.next/standalone/server.js` con el subconjunto MÍNIMO de
`node_modules` que el server necesita para correr — no el `node_modules`
completo del repo (que incluye devDependencies, tipos, herramientas de build,
etc.).

`output: "standalone"` NO cambia `next dev` — solo cambia qué genera
`next build`. El modo desarrollo del equipo sigue igual.

## Qué falta ensamblar a mano (standalone no lo hace solo)

Next.js documenta que `standalone` deliberadamente NO copia dos cosas, para
mantener el standalone chico y determinista:

1. **`.next/static/`** — los assets estáticos del cliente (JS/CSS con hash,
   cargados por el navegador). Sin esto la página carga pero se ve rota (sin
   estilos, sin JS del cliente).
2. **`public/`** — archivos servidos tal cual desde la raíz (imágenes,
   favicon, etc.). Hoy `frontend/public/` no existe en el repo, pero el
   ensamblaje lo soporta si aparece más adelante.

`packaging/build_frontend.ps1` copia ambos a
`.next/standalone/.next/static` y `.next/standalone/public` respectivamente
como parte del ensamblaje.

## Node portable

El instalador no debe depender del Node del PATH del abogado (puede no
existir, o ser otra versión). Se empaqueta **solo `node.exe`** (el binario del
runtime) — no se necesita `npm` ni `npx` para correr un `server.js` ya
compilado.

- Versión usada: **Node.js v22.23.1** (línea LTS 22, "Jod" — la LTS activa de
  la 22.x al momento de este empaquetado; el repo no fija versión vía
  `.nvmrc` ni `engines` en `package.json`, así que se tomó la LTS 22 más
  reciente de `nodejs.org/dist`).
- `node.exe` solo: **~83 MB**. ZIP oficial completo descomprimido (con npm,
  corepack, `node_modules` de npm, docs): **~92 MB**. Para el instalador basta
  con `node.exe` — el ensamblaje NO copia el resto del ZIP.

### Cómo volver a descargar el Node portable

`tools/node-portable/` vive en `D:\Inteligencia Artificial\Mia-Super
Agent\tools\node-portable\` — **fuera** del repo git de `mia/` (es una carpeta
hermana, igual que `tools/postgres16-portable/`). No se versiona: los
binarios de Node no van a git.

```powershell
$ver = "v22.23.1"
$dest = "D:\Inteligencia Artificial\Mia-Super Agent\tools\node-portable"
$zip = Join-Path $dest "node-$ver-win-x64.zip"
Invoke-WebRequest -Uri "https://nodejs.org/dist/$ver/node-$ver-win-x64.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $dest -Force
& (Join-Path $dest "node-$ver-win-x64\node.exe") --version   # debe imprimir v22.23.1
```

`packaging/build_frontend.ps1` busca automáticamente cualquier carpeta
`node-v*-win-x64` dentro de `tools/node-portable/` (no hace falta editar el
script si se actualiza la versión de Node).

## Ensamblaje (`packaging/build_frontend.ps1`)

```powershell
powershell -File packaging\build_frontend.ps1
```

Pasos que ejecuta:

1. `npm run build` en `frontend/` (se puede saltar con `-SkipBuild` para
   iterar rápido sobre el ensamblado sin recompilar).
2. Ensambla `packaging/dist/mia-frontend/` con:
   - `server.js` + `node_modules` mínimos + `package.json` (de
     `.next/standalone/`)
   - `.next/static/` (assets del cliente)
   - `public/` (si existe)
   - `node.exe` (Node portable)
3. Prueba de humo: arranca el ensamblado con **su propio `node.exe`**
   (nunca el del PATH), espera un `GET /` con código 200, verifica las
   cabeceras de seguridad, y apaga el proceso.

`packaging/dist/` está en `.gitignore` (ver raíz del repo) — solo se versiona
el script, no su salida.

## Gotcha verificado: `HOSTNAME` y bind de red

`server.js` (generado por Next) hace:

```js
const hostname = process.env.HOSTNAME || '0.0.0.0'
```

En Windows, `$env:HOSTNAME` puede venir ya seteado por el sistema (nombre del
equipo), y ese nombre puede resolver a una IP de red/VPN en vez de loopback.
Si no se limpia esa variable antes de lanzar `node server.js`, el server
escucha SOLO en esa IP y **ni `localhost` ni `127.0.0.1` conectan** —
parece "no arrancó" cuando en realidad está sirviendo en la interfaz
equivocada. `build_frontend.ps1` limpia `$env:HOSTNAME` antes de lanzar el
proceso. El instalador final debe replicar esto (no heredar el entorno del
usuario tal cual).

## Gotcha verificado: `localhost` vs `127.0.0.1` en pruebas de humo

En pruebas manuales con `Invoke-WebRequest`, pedir `http://localhost:<puerto>/`
puede colgarse hasta agotar el timeout: `localhost` resuelve primero a `::1`
(IPv6) en la resolución de nombres de esta máquina, y como Node solo escucha
en la interfaz IPv4 (`0.0.0.0`), la conexión a `::1` nunca conecta ni cae en
fallback rápido a IPv4 dentro del mismo intento. `Test-NetConnection` lo
confirma: conectar a `::1:<puerto>` falla, conectar a `127.0.0.1:<puerto>`
funciona. Todas las pruebas de humo (manuales y en `build_frontend.ps1`) usan
`127.0.0.1` explícito, nunca `localhost`.

## Verificación

- Gate en frío (no requiere build ni red):
  `.venv\Scripts\python.exe execution\test_frontend_packaging.py`
- Regresión de desarrollo: `npm run dev` en `frontend/` debe seguir
  compilando igual que antes (standalone no toca el modo dev).
