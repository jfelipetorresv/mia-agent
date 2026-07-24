# Plan Fase 4 — Instalador de Mia (runbook para Windows)

> Documento operativo. Lo corre **Pipe** en su Windows 11 (Modo B nativo, PowerShell).
> No se puede ejecutar en el contenedor Linux donde se preparó: aquí no se compilan
> `.exe` (PyInstaller) ni el instalador (NSIS). Todo lo de abajo es para tu máquina.
> Proyecto en `"D:\Codex\Mia-Super Agent\mia"` (comillas obligatorias por los espacios).

---

## Para Pipe (en 6 lineas)

1. F4 es el **último paso del bloque instalador**: convertir Mia en un programa que se
   instala con doble clic y arranca solo, sin que veas nada técnico.
2. Vas a **volver a compilar** las dos piezas del motor de Mia y **armar el instalador**,
   luego probarlo en una máquina limpia como lo haría un cliente.
3. Tú decides cuatro cosas: que **no aparezca la ventana negra** al arrancar, si firmas el
   instalador ahora o después, en qué modo se instala (para ti o para toda la máquina), y si el
   instalador debe funcionar aunque la máquina del cliente no tenga internet.
4. El riesgo si algo sale mal: que al abogado le salte una **ventana negra con texto técnico**
   (rompe la regla de "cero jerga"), o que Mia arranque a medias en una máquina sin internet.
5. Nada de esto borra datos: son binarios nuevos. Lo peor que pasa es que el instalador no
   arranque y haya que recompilar — no hay pérdida.
6. Cuando los **7 criterios de la sección "Criterio de cierre del bloque instalador"** estén
   en verde (esos 7 incluyen completar los 10 ítems del E2E), el bloque instalador queda cerrado.

---

## Decisiones que solo Pipe puede tomar

1. **Que no aparezca la ventana negra al arrancar (RECOMENDADO: sí, evitarla).**
   Hoy los dos motores de Mia arrancan abriendo una **ventana de consola negra** con texto
   técnico (uvicorn, banner de litellm). Eso viola la regla §G (el abogado no debe ver jerga).
   La cáscara ya los lanza ocultos, pero si alguien hace doble clic directo al programa, o la
   cáscara falla en ocultarlos, aparece la ventana negra. **Recomendación: activar la opción
   que las oculta al recompilar.**
   Contra: los mensajes técnicos ya no se verán en pantalla, pero de todos modos se siguen
   guardando en un archivo de registro por si hay que revisar un problema. En la práctica no
   pierdes nada útil.
   *Detalle técnico (para quien compila):* poner `console=False` en `mia-backend.spec:120` y
   `mia-litellm.spec:98` (hoy `console=True`); la ocultación en caliente es `CREATE_NO_WINDOW`
   en `lib.rs`, pero el `.spec` no la garantiza por sí solo.

2. **Firmar el instalador ahora o después (APLAZABLE; aceptable saltarla en F4).**
   Sin firma, Windows muestra una advertencia de seguridad al instalar. Para tus pruebas de
   F4 es aceptable saltarla. Antes de **distribuir a un cliente** hay que firmar. Decisión:
   ¿firmas ahora o cierras F4 sin firma y lo dejas anotado como pendiente de distribución?
   *Detalle técnico (para quien compila):* Azure Trusted Signing vía
   `bundle.windows.certificateThumbprint` / `signCommand` en `tauri.conf.json`.

3. **Modo de instalación: solo para tu usuario o para toda la máquina (recomendado: solo para
   tu usuario, suele ser más simple).**
   "Para toda la máquina" pide permiso de administrador; "solo para tu usuario" no lo pide.
   Para la laptop de un abogado, "solo para tu usuario" suele ser más simple. Decisión tuya;
   abajo el borrador viene con esa opción.
   *Detalle técnico (para quien compila):* NSIS `installMode` `perMachine` vs `currentUser`
   (el borrador trae `currentUser`).

4. **Si el instalador debe funcionar sin internet (RECOMENDADO: sí, embeber el instalador —
   offline).**
   Por defecto, al instalar, Mia descarga de internet un componente de Windows (WebView2). Si
   la máquina del cliente no tiene internet en esa primera instalación, falla.
   **Recomendación: embeber ese componente (modo offline) para que Mia se instale aunque el
   cliente no tenga internet.** Contra: el archivo de instalación pesa más (unos MB
   adicionales). Si estás seguro de que siempre habrá internet en la primera instalación,
   puedes dejar la descarga online y ahorrar peso.
   *Detalle técnico (para quien compila):* `webviewInstallMode` `embedBootstrapper` u
   `offlineInstaller` vs `downloadBootstrapper` en `tauri.conf.json`.

---

## Paso 0 — Recompilar los dos ejecutables

Los `.exe` que hoy están en `packaging/dist/` **están desactualizados**: no traen las rutas
de activación de llaves (`welcome.py`), la migración `031_welcome_bootstrap.sql`, ni
`env_writer.py` en el estado actual (Riesgo #59, ampliación sesión 44). Hay que recompilar.

**Orden OBLIGATORIO: backend PRIMERO, litellm DESPUÉS.**
Razón: `build_backend.ps1:71-78` borra `dist/` y `build/` **enteros**; `build_litellm.ps1`
solo borra su subcarpeta. Si compilas litellm primero, el build del backend borra el bundle
de litellm.

```powershell
# Ubícate en la raíz del proyecto
Set-Location "D:\Codex\Mia-Super Agent\mia"

# 1. Backend (limpia dist/ y build/ ENTEROS y compila mia-backend.spec)
powershell -File "packaging\build_backend.ps1"

# 2. (Solo si .venv-litellm no existe o litellm no está en 1.74.8) crear el venv dedicado
powershell -File "packaging\setup_venv_litellm.ps1"

# 3. LiteLLM (limpia SOLO dist\mia-litellm\, no toca el backend recién compilado)
powershell -File "packaging\build_litellm.ps1"
```

- Paso 1: corre el gate `execution\check_env_pins.py` (HALT si falla, Riesgo #32), limpia,
  compila y hace smoke OCR opcional. Salida: `packaging\dist\mia-backend\`.
- Paso 2 es **idempotente**: si `.venv-litellm` ya tiene litellm==1.74.8, sale sin hacer nada.
- Paso 3 corre un **humo REAL que sí falla el build** si algo está mal (health/liveliness 200,
  `/v1/models` con Bearer 200 con alias `claude-haiku`/`mia-local`, 401/403 sin Bearer, bind
  loopback). Salida: `packaging\dist\mia-litellm\`.

### El bundle DEBE traer welcome.py + migración 031 + env_writer.py — cómo verificar

Estos tres entran así (según recon A, confirmado contra el código):

- **`031_welcome_bootstrap.sql`** entra por el **glob de datas** del spec, no por lista
  hardcodeada. `mia-backend.spec:69-73`:
  ```python
  DB_DIR = os.path.join(BACKEND_DIR, "mia", "db")
  datas += [(os.path.join(DB_DIR, "schema.sql"), "mia/db")]
  for _mig in sorted(os.listdir(os.path.join(DB_DIR, "migrations"))):
      if _mig.endswith(".sql"):
          datas.append((os.path.join(DB_DIR, "migrations", _mig), "mia/db/migrations"))
  ```
  Es un `os.listdir()` ordenado que toma **todo** `.sql`. Cualquier `NNN_*.sql` nueva entra
  sola; no se toca el spec.
- **`welcome.py`** entra por análisis estático de imports: `entry_backend.py:45` importa
  `mia.api.main`, que en `main.py:24` importa `welcome` y en `main.py:199` hace
  `app.include_router(welcome.router, prefix="/api")`.
- **`env_writer.py`** entra porque `welcome.py:69` hace
  `from ...setup.env_writer import read_env_values, upsert_env_keys`.
  ⚠️ Acoplamiento frágil: `env_writer` sobrevive en el bundle **solo** porque `welcome.py`
  lo importa. Si en el futuro se refactoriza welcome para no importarlo, podría caerse del
  bundle en silencio (no hay `datas`/`hiddenimports` que lo ancle). Anotarlo como riesgo.

**Verificación tras compilar el backend** (PowerShell, sobre la carpeta ya generada):

```powershell
# 1. La migración 031 quedó dentro del bundle
Test-Path "packaging\dist\mia-backend\_internal\mia\db\migrations\031_welcome_bootstrap.sql"
#   -> debe imprimir True

# 2. Listar TODAS las migraciones empaquetadas (confirmar que están las 003..031)
Get-ChildItem "packaging\dist\mia-backend\_internal\mia\db\migrations\*.sql" | Select-Object Name

# 3. schema.sql también entró
Test-Path "packaging\dist\mia-backend\_internal\mia\db\schema.sql"
#   -> debe imprimir True
```

> Nota: la ruta interna de PyInstaller onedir es `_internal\` (PyInstaller 6.x). Si tu
> versión deja los datos junto al `.exe`, ajusta la ruta quitando `_internal\`. El gate
> `execution\test_packaging.py` ya protege que el spec tenga **exactamente 2** llamadas
> `collect_*` reales (litellm + rapidocr); no agregues un tercer `collect_*` o rompe ese gate.

`welcome.py` y `env_writer.py` no se verifican por archivo suelto (van embebidos en el
binario compilado de Python), sino en frío durante el E2E: al pegar las llaves en la pantalla
de activación (Paso 2, ítem correspondiente).

---

## Paso 1 — Generar el instalador NSIS/MSI

### Estado actual de la config

`desktop/src-tauri/tauri.conf.json` hoy trae el bloque `bundle` con `"targets": "all"` y
`icon` (incluye `icons/icon.ico`, que es el que NSIS necesita), pero **NO existe la clave
`bundle.windows`** — ni `nsis` ni `wix`. Con solo `"targets": "all"`, Tauri intentaría
construir NSIS **y** MSI con valores por defecto, en inglés y sin configurar.

### Por qué NSIS y no solo MSI

- **NSIS** produce un `.exe` de instalación clásico, admite **idioma español** (`languages`),
  modo `currentUser` sin admin, y permite un **template propio** e `installerHooks` — necesario
  para empaquetar las cargas laterales (`mia-backend/`, `mia-litellm/`, `mia-frontend/`,
  `pgsql/bin/`, `litellm_config.installer.yaml`, `orchestration.json`) que produce
  `packaging/build_*.ps1` y que `orchestration.installer.json` espera como hermanos del `.exe`.
- **MSI (WiX)** es más rígido para payloads grandes ensamblados fuera del flujo de Tauri y su
  UI es más difícil de mantener en español para un no-técnico. Para el objetivo (un instalador
  que el abogado ejecute) **NSIS es la vía simple**. Recomendación: fijar `"targets": ["nsis"]`.

### Bloque propuesto (BORRADOR — pegar en tauri.conf.json)

> ⚠️ **BORRADOR.** Reemplaza el `"bundle"` actual (`tauri.conf.json`, la clave `bundle`) por
> este. Es válido para **Tauri v2**. Ajusta `installMode` según tu decisión (3) y
> `webviewInstallMode` según tu decisión (4). Los payloads laterales (mia-backend/,
> mia-litellm/, mia-frontend/, pgsql/) NO se copian solos: hoy no están declarados en
> `bundle.resources`; hay que declararlos aquí o incluirlos vía el template NSIS. Verifica en
> tu Windows que las rutas relativas resuelven contra `packaging/dist/`.

```json
"bundle": {
  "active": true,
  "targets": ["nsis"],
  "icon": [
    "icons/32x32.png",
    "icons/128x128.png",
    "icons/128x128@2x.png",
    "icons/icon.icns",
    "icons/icon.ico"
  ],
  "resources": {
    "../../packaging/dist/mia-backend": "mia-backend",
    "../../packaging/dist/mia-litellm": "mia-litellm",
    "../../packaging/dist/mia-frontend": "mia-frontend",
    "../../packaging/dist/pgsql": "pgsql",
    "../../packaging/litellm_config.installer.yaml": "litellm_config.installer.yaml",
    "../../packaging/orchestration.installer.json": "orchestration.json"
  },
  "windows": {
    "webviewInstallMode": { "type": "downloadBootstrapper" },
    "nsis": {
      "installMode": "currentUser",
      "languages": ["Spanish"],
      "displayLanguageSelector": false,
      "installerIcon": "icons/icon.ico"
    }
  }
}
```

> Notas sobre el borrador:
> - `resources`: las claves son rutas relativas a `src-tauri/`; los valores son el nombre con
>   que quedan **junto al `.exe`** instalado. `orchestration.installer.json` espera esos nombres
>   como `${exe_dir}/mia-backend`, etc. Confirma los nombres exactos contra
>   `packaging/orchestration.installer.json:6-51` antes de compilar (recon A/B).
> - ⚠️ **Verificación real en Tauri v2:** `bundle.resources` se instala en el `resource_dir()`,
>   que **no** está garantizado idéntico al `exe_dir` en todos los `installMode`/targets; los
>   payloads podrían quedar bajo una subcarpeta (p.ej. `resources/`) y entonces
>   `${exe_dir}/mia-backend` **no resolvería** y el arranque rompería. Tras `npm run tauri build`
>   en Windows, **confirmar que los payloads quedan como hermanos directos del `.exe` instalado**
>   (no en un `resources/` anidado).
> - Si `resources` no copia bien las carpetas grandes, o si Tauri las anida, la alternativa es un
>   `nsis.template` propio (`installerHooks`) que empaquete los payloads junto al `.exe` — es lo
>   que sugiere el `_nota` de que "NSIS copia este JSON tal cual" —, o ajustar `orchestration`
>   para apuntar al subdir real.
> - `webviewInstallMode`: cambia a `{ "type": "embedBootstrapper" }` u `offlineInstaller` si
>   decides soportar máquinas sin internet (decisión 4).

### Comando de build

```powershell
Set-Location "D:\Codex\Mia-Super Agent\mia\desktop"

# Compila la cáscara Rust + genera el instalador NSIS
npm run tauri build
# (o, si usas el CLI directo)  cargo tauri build
```

El instalador queda en
`desktop\src-tauri\target\release\bundle\nsis\Mia_0.1.0_x64-setup.exe` (nombre según
`productName`/`version` de `tauri.conf.json`).

---

## Paso 2 — E2E en frio (maquina limpia)

Máquina Windows **sin Python ni Node**, con `LOCALAPPDATA` virgen (usuario nuevo o carpeta
`%LOCALAPPDATA%\Mia` inexistente). Cubre los **7 puntos del Riesgo #59** más la verificación
de `welcome.py`/`031`/`env_writer.py`. Marca cada casilla al pasar.

Los gates automatizados (recon D) ya prueban el **contrato en el código**; lo de abajo prueba
que **funciona al ejecutar**. Donde un gate ya cubre algo, se marca "ya cubierto por <gate>,
solo confirmar visualmente".

- [ ] **1. Instalar y primer arranque en frío.**
  Doble clic al `Mia_..._setup.exe` → se instala → abrir Mia. Debe disparar el primer arranque
  automático (`--first-run`) sin pedirte nada técnico.
  **PASA**: la app abre y avanza sola. **FALLA**: pide Python/Node, o no arranca.
  *(La lógica del gatillo triple ya está cubierta por `test_first_run.py` en caliente; aquí se
  confirma disparado por la cáscara compilada con rutas reales `${exe_dir}`/`${local_app_data}`.)*

- [ ] **2. Splash bajo la CSP nueva se pinta bien — arranque normal Y estado de error.**
  Mirar la pantalla de arranque: estilos aplicados y mensajes en español llano legibles.
  **PASA (arranque normal)**: splash con estilo, textos en llano, sin cuadros rotos.
  **FALLA**: splash sin CSS o con texto técnico.
  **Sub-paso obligatorio (estado de ERROR):** forzar una condición de error visible del
  arranque (p.ej. ocupar antes el puerto de una dependencia, o quitar temporalmente un payload
  lateral) y confirmar **visualmente** que el **mensaje de error en llano también se pinta con
  estilo** bajo la CSP nueva. Este es el caso frágil que el Riesgo #59 punto 1 exige verificar:
  texto de error inyectado dinámicamente + CSP sin `unsafe-inline`.
  **PASA (error)**: el mensaje de error se ve con estilo y en llano. **FALLA**: el error sale
  sin estilo, en crudo, o con texto técnico.
  *(La CSP sin `unsafe-inline` y el splash sin inline ya están cubiertos por
  `test_shell_hardening.py`; aquí se confirma visualmente el camino feliz Y el de error.)*

- [ ] **3. Ninguna ventana de consola negra (console=False).**
  Durante todo el arranque y uso, no debe aparecer ninguna ventana negra con texto técnico
  (uvicorn / banner de litellm). Probar también **doble clic directo** a
  `packaging\dist\mia-backend\mia-backend.exe` y `...\mia-litellm\mia-litellm.exe`.
  **PASA**: cero ventanas negras en cualquier caso. **FALLA**: aparece consola negra.
  *(Requiere haber aplicado la decisión 1 — `console=False` — en el Paso 0. Ningún gate lo
  cubre: es el punto 3 y 7 del Riesgo #59.)*

- [ ] **4. Loopback verificado en procesos vivos.**
  Con Mia corriendo, ejecutar:
  ```powershell
  Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in 55432,4000,8000,3100 } |
    Select-Object LocalAddress,LocalPort,OwningProcess
  ```
  **PASA**: los 4 puertos (Postgres 55432, LiteLLM 4000, backend 8000, frontend 3100) escuchan
  SOLO en `127.0.0.1`; un intento de conexión por la IP LAN de la máquina falla.
  **FALLA**: alguno escucha en `0.0.0.0` o responde por la IP LAN.
  *(En frío los gates solo prueban la DB via config y LiteLLM via argv, `test_litellm_packaging.py`;
  el bind vivo de backend/frontend NO lo cubre ningún gate — hay que verlo aquí.)*
  **⚠️ BLOQUEANTE de código (no lo escribe Pipe — lo hace un desarrollador o Claude Code):**
  hoy el frontend **NO** queda loopback-only, así que este ítem 4 **FALLA para el puerto 3100**
  tal cual está el código. `server.js` hace `hostname = process.env.HOSTNAME || '0.0.0.0'`
  (`build_frontend.ps1:29`) y la cáscara hace `.env_remove("HOSTNAME")` en `lib.rs:941` — al
  **quitar** la variable, el standalone de Next.js cae al default `0.0.0.0` y bindea **todas**
  las interfaces (incluida la IP LAN). El arreglo es **FIJAR** `.env("HOSTNAME", "127.0.0.1")`
  (además de `PORT`) en vez de `.env_remove("HOSTNAME")`: así se evita el bind a la IP de VPN y
  se fuerza loopback. Aplicar este cambio como paso explícito del Paso 0/refactor y **NO dar el
  ítem 4 por cubierto** hasta re-verificarlo con Mia corriendo.

- [ ] **5. IPC remoto bloqueado desde localhost:3100.**
  Con la app en la pantalla principal, abrir DevTools sobre `http://localhost:3100` y en la
  consola escribir:
  ```js
  window.__TAURI__
  ```
  **PASA (esperado, con `withGlobalTauri` en `false` — el default)**: `window.__TAURI__ === undefined`.
  Este es el criterio primario a auditar, el que fija el Riesgo #59 punto 2 (ausencia total de
  superficie Tauri en la página remota).
  **Señal a investigar (NO es PASA equivalente):** si el objeto **existe**, tratarlo como posible
  regresión de config (¿se activó `withGlobalTauri`?) y averiguar por qué apareció superficie
  Tauri en 3100. Como verificación **secundaria** puede confirmarse que cualquier `invoke()`
  rechaza con error de permisos, pero eso no sustituye al criterio primario `=== undefined`.
  **FALLA**: `window.__TAURI__` está disponible y `invoke()` funciona desde la página remota.
  *(El deny-all remoto por defecto ya está cubierto en frío por `test_shell_hardening.py`
  —capability `default` solo con `core:default`—; aquí se confirma empíricamente, según el paso
  descrito en `desktop/README.md:181-187`. Punto 2 del Riesgo #59. CRÍTICO si en el Riesgo #60
  se añade `invoke_handler`: el comando nuevo NO debe volverse alcanzable desde 3100.)*

- [ ] **6. Recompilados post-F2/F3: activación de llaves funciona.**
  En la pantalla de activación (`/activar`) pegar la clave de **búsqueda (Voyage)** y una de
  **respaldo (Anthropic u OpenRouter)**. Guardar.
  **PASA (clave de búsqueda)**: queda activa en caliente (sin reabrir); el `.env` en
  `%LOCALAPPDATA%\Mia` contiene las claves.
  **PASA (clave de respaldo) — depende de la decisión sobre el Riesgo #60:**
  - **(a) Si #60 se APLAZA** (vía por defecto con la arquitectura actual, ver Riesgo #60): la de
    respaldo escribe al `.env` y **muestra el aviso fuerte** "cierra Mia por completo y vuelve a
    abrirla".
  - **(b) Si #60 se RESUELVE** (se implementó el reinicio automático y `/activar` corre con IPC
    local): tras guardar, el motor (proxy litellm) queda **respondiendo sin reabrir** y **NO**
    aparece el aviso de reabrir. Verificación en caliente del reinicio:
    `GET http://127.0.0.1:4000/v1/models` responde 200 con la clave **nueva** sin haber cerrado Mia.
  **FALLA**: la pantalla no existe, error técnico, no se escribe el `.env`, o —en la variante
  (b)— sigue apareciendo el aviso de reabrir / el proxy no responde con la clave nueva.
  **Sub-paso (mitigación del Riesgo #60 ya aplicada — política "nube"):** con la política
  **"nube"** seleccionada, confirmar que `/activar` **NO** deja continuar sin la clave de
  respaldo. **PASA**: bloquea el avance + muestra aviso fuerte. **FALLA**: deja avanzar sin clave.
  *(Esto prueba en vivo que `welcome.py`, la migración `031` y `env_writer.py` quedaron en el
  bundle recompilado. La lógica de hot-reload vs diferida y §G en las respuestas JSON ya está
  cubierta por `test_welcome_keys.py`; aquí se confirma en la UI real.)*

- [ ] **7. Setup interrumpido a mitad → auto-repara al reabrir.**
  Durante el primer arranque, **cerrar la ventana** mientras el setup está a medias. Volver a
  abrir Mia.
  **PASA**: la reapertura detecta el estado incompleto (gatillo triple: marcador
  `.mia-setup-complete` + `PG_VERSION` + `.env`) y **completa/repara** el setup solo, sin
  intervención. **FALLA**: arranca roto, o pide reinstalar.
  *(La reparación está cubierta en caliente por `test_first_run.py` 68/68; aquí falta VERLO con
  la cáscara real. Punto 6 del Riesgo #59.)*

- [ ] **8. LiteLLM escucha solo loopback (Blindaje 6 en el exe recompilado).**
  Confirmar que `mia-litellm.exe` recompilado inyecta `--host 127.0.0.1` por defecto (no solo
  por el flag de `orchestration.installer.json`). Ya cubierto arriba en el ítem 4 para el puerto
  4000; adicionalmente intentar `http://<IP-LAN>:4000/v1/models` desde otra máquina de la red.
  **PASA**: rechazado / sin respuesta. **FALLA**: responde por la IP LAN.
  *(El humo del build `build_litellm.ps1` ya lo verifica al compilar, `test_litellm_packaging.py`
  confirma que el script contiene ese humo; aquí se confirma en el binario instalado y en frío.)*

- [ ] **9. Identidad: no adopta a un intruso.**
  (Opcional pero recomendado — reproduce la lección voicebox/Sura.) Antes de abrir Mia, levantar
  a mano un proceso que responda 200 en el puerto 8000 (o 4000/3100/55432). Abrir Mia.
  **PASA**: la cáscara NO adopta al intruso y muestra el mensaje en llano ("otro programa está
  ocupando el lugar de Mia…"). **FALLA**: adopta al proceso extraño.
  *(Toda la lógica de identidad ya está cubierta en frío por `test_shell_hardening.py` sección
  4/6; ningún gate levanta un squatter real, por eso este ítem es solo en vivo.)*

- [ ] **10. Instancia única y cierre limpio.**
  Segundo doble clic al ícono con Mia ya abierta → debe **traer la ventana al frente**, no abrir
  otra. Al cerrar Mia, verificar que Postgres/LiteLLM/backend/frontend quedan detenidos
  (`taskkill` en orden inverso; la DB solo se apaga si la encendió la cáscara).
  **PASA**: una sola ventana; al cerrar, los 4 puertos dejan de escuchar.
  **FALLA**: se abre una segunda ventana, o quedan procesos huérfanos.
  *(La lógica de single-instance y shutdown ya está cubierta como literal por
  `test_shell_hardening.py`; aquí se confirma ejecutando.)*

---

## Riesgo #60 — Reinicio automatico del motor (LiteLLM) tras activar llaves

> **Esto NO lo escribes tú, Pipe.** Es trabajo de código: lo hace un desarrollador o se lo pides
> a Claude Code. Tu única decisión aquí es: **lo hacemos ahora** (para que Mia active la clave
> sola) **o lo aplazamos** y por ahora Mia te pide cerrar y reabrir Mia a mano. Los bloques de
> código Rust/TypeScript de abajo, con números de línea, son para quien compila — no para ti.

> **Estado actual: #60 está APLAZADO por la arquitectura, no resuelto.** Con la configuración de
> hoy la cáscara navega la ventana `main` a `http://localhost:3100` (`frontend.url` en
> `orchestration.installer.json`), o sea un **origen remoto**, y la única capability es `default`
> = solo `core:default`, `windows: ["main"]`, **sin dominio `remote`** (`capabilities/default.json`).
> Por eso en `/activar` (servido desde 3100) `window.__TAURI__` es `undefined` —lo confirma el
> ítem 5 del E2E—, y el `invoke("reiniciar_litellm")` del borrador TS **siempre cae al fallback**
> ("cierra y reabre") y **nunca** reinicia el proxy. Conceder IPC remoto a `localhost:3100`
> **rompería el blindaje F2 (deny-all remoto)**, así que NO es opción. Para volver #60 realmente
> funcional habría que **reubicar `/activar` dentro del `frontendDist` local (`tauri://`)**, que
> sí tiene IPC, o exponer el reinicio por **otro canal que NO conceda `remote` a 3100** (p.ej. el
> backend local escribe una señal que la cáscara vigila). Mientras eso no se haga, el criterio de
> cierre 5 se cierra por la vía "APLAZADO con aviso 'cierra y reabre'", no por "reinicio
> automático confirmado". El código de abajo queda como **preparación** para cuando se resuelva
> ese reubicado.

**Problema.** Las claves de **respaldo** (Anthropic) y **OpenRouter** las sirve el proxy
`mia-litellm.exe`, que es un **proceso separado** y lee su `.env` **solo al arrancar**
(bugs-and-risks.md:1242; `welcome.py:247-254` documenta por qué setearlas en caliente es
"INÚTIL para el proxy y peligroso"). Hoy la pantalla `/activar` solo puede mostrar el aviso
"cierra Mia por completo y vuelve a abrirla" (`welcome.py:270-274`). Para cerrar el riesgo,
Mia debe **reiniciar sola el proxy** tras guardar la clave, sin que el abogado cierre nada.

**Por qué depende del IPC de Tauri.** El backend no controla al proxy (es un proceso hermano);
solo la **cáscara Tauri** lo supervisa. Hoy **no existe ningún `#[tauri::command]` en toda la
crate** (recon B punto 3): la comunicación cáscara→UI es unidireccional por eventos
(`mia://progress`). Hay que **añadir un comando IPC** que la UI pueda invocar.

**Dónde va (recon B punto 4).** Dos inserciones en `desktop/src-tauri/src/lib.rs`:
(a) definir el comando **después de `shutdown()` (tras `lib.rs:1062`) y antes de `pub fn run()`
(`lib.rs:1068`)**; (b) registrar el handler **entre el plugin single-instance (`lib.rs:1082`)
y `.setup(` (`lib.rs:1083`)** — después del single-instance para no romper el requisito de
"primer plugin".

Para que el comando funcione hay que **persistir la config de LiteLLM en `Shared`** (hoy
`LiteLlmCfg` solo vive como variable local `cfg` dentro de `orchestrate`). Se amplía el struct
`Shared` (`lib.rs:223-227`) y se guarda en `.setup()`. Lo ideal es **extraer el bloque de
arranque de LiteLLM (`lib.rs:704-762`) a un helper `start_litellm(...)`** y llamarlo desde
`orchestrate()` y desde el comando nuevo, para no duplicar la lógica de identidad+loopback.

**Detalles de implementación que el borrador de abajo NO puede omitir (si no, no compila o no
reinyecta bien el entorno):**
- **`MIA_APP_DIR` / `app_dir` (crítico para que #60 cumpla su propósito).** El arranque original
  inyecta `MIA_APP_DIR` desde `cfg.app_dir` (`lib.rs:720-722`), y `app_dir` **NO** forma parte de
  `LiteLlmCfg`. `entry_litellm.py` puede usar `MIA_APP_DIR` para localizar el `.env` fresco (donde
  se acaba de escribir la clave de respaldo Anthropic/OpenRouter). Si se relanza el proxy solo con
  `litellm_cfg`, arrancaría **sin** esa env y leería un `.env` viejo o ninguno — no cargaría la
  clave nueva, anulando el propósito de #60 incluso si el IPC funcionara. Por eso hay que
  **persistir también `app_dir`** (o el `MIA_APP_DIR` ya resuelto) en `Shared`/`Owned` y
  **reinyectarlo** en `start_litellm`, replicando exactamente el env del spawn original
  (`lib.rs:717-722`). Verificar en `entry_litellm.py` de qué depende para hallar el `.env`.
- **Estado y tipos (el borrador no compila tal cual).** El borrador lee
  `shared.owned.lock().unwrap().litellm_cfg`, es decir de `Owned`. `Owned` deriva `Default` y
  `LiteLlmCfg` **no** implementa `Default`, así que el campo debe ser
  `litellm_cfg: Option<LiteLlmCfg>`, seteado en `.setup()` (clonando `cfg.litellm` a `Owned`)
  **antes** de que `cfg` se mueva al `async move` (`lib.rs:1164`), y manejar el `None`. Un
  `o.litellm_cfg.clone()` no-`Option` (como aparece en el borrador) **no tipa**.
- **Cliente reqwest.** `start_litellm` necesita un cliente `reqwest .no_proxy()` que el comando
  nunca construye; hay que **reconstruirlo o persistirlo**. (Nota positiva: los locks del borrador
  están correctamente scopeados —se sueltan antes de cada `.await`—, así que el futuro del comando
  es `Send`.)

### Rust — comando nuevo en lib.rs

> **BORRADOR — compilar y verificar en Windows, NO probado en este entorno Linux.**
> Reusa `register_child` (`lib.rs:329-355`), `child_died`, el patrón `taskkill` de `shutdown()`
> (`lib.rs:1042-1045`), `identity::litellm_health` y el cliente `reqwest` `.no_proxy()`.
> Requiere que `Shared`/`Owned` ya guarden `litellm_cfg: Option<LiteLlmCfg>` **y `app_dir`**
> (para reinyectar `MIA_APP_DIR`, `lib.rs:720-722`), `job` y el `client` (o reconstruir el
> cliente `.no_proxy()`). Ver los "Detalles de implementación" de arriba: el `o.litellm_cfg.clone()`
> del borrador es ilustrativo y debe manejar el `Option`. No se debe registrar ninguna capability
> `"remote"` hacia `localhost:3100`: el comando debe quedar alcanzable SOLO desde la ventana
> `main` local (deny-all remoto vigente).

```rust
// === INSERTAR después de shutdown() (tras lib.rs:1062) y antes de pub fn run() ===
//
// Reinicia el proceso supervisado mia-litellm.exe respetando:
//  - identidad  (espera identity::litellm_health del hijo propio; nunca adopta por puerto)
//  - loopback   (cliente .no_proxy(), URLs 127.0.0.1)
//  - single-instance (corre dentro de la única cáscara viva; no lo afecta)
//  - concurrencia (serializa contra orchestrate/shutdown vía Mutex<Owned> y respeta cleaned)
#[tauri::command]
async fn reiniciar_litellm(app: tauri::AppHandle) -> Result<(), String> {
    let shared = app.state::<Shared>();

    // 1. Si la ventana ya se está cerrando, no relanzar nada.
    if closing(&shared) {
        return Err("Mia se está cerrando.".into());
    }

    // 2. Matar el proxy actual por su PID conocido (mismo patrón que shutdown()).
    let old_pid = {
        let mut o = shared.owned.lock().unwrap();
        let pid = o.litellm_pid.take();
        o.litellm_child = None; // soltamos el handle del hijo anterior
        pid
    };
    if let Some(pid) = old_pid {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        log_line(&shared.log_dir, &format!("Reinicio: apagué litellm (PID {pid})."));
    }

    // 3. Relanzar reusando el helper extraído de lib.rs:704-762.
    //    start_litellm() debe: spawn con CREATE_NO_WINDOW, job.assign(),
    //    register_child(&shared, "litellm", child), y esperar
    //    identity::litellm_health contra la health_url 127.0.0.1 (hijo propio).
    //    La LiteLlmCfg se toma de Shared (persistida en .setup()).
    let cfg = {
        let o = shared.owned.lock().unwrap();
        o.litellm_cfg.clone()  // requiere ampliar Owned/Shared con litellm_cfg
    };
    start_litellm(&app, &shared, &cfg)
        .await
        .map_err(|_| "Mia no pudo reiniciar el motor de modelos.".to_string())?;

    log_line(&shared.log_dir, "Reinicio: litellm de nuevo saludable.");
    Ok(())
}
```

```rust
// === INSERTAR en la cadena del builder, entre el plugin single-instance
//     (lib.rs:1082) y .setup( (lib.rs:1083) ===
        .invoke_handler(tauri::generate_handler![reiniciar_litellm])
```

### TypeScript — hook en /activar que lo llama tras guardar la clave

> **BORRADOR — compilar y verificar en Windows, NO probado en este entorno Linux.**
> Va en el frontend, en el handler de la pantalla `/activar`, DESPUÉS de que el backend
> confirme que escribió la clave de respaldo al `.env`. Solo debe intentar el reinicio para
> claves **diferidas** (Anthropic/OpenRouter); la de búsqueda (Voyage) ya recarga en caliente.
> Recuerda: desde `localhost:3100` `window.__TAURI__` está bloqueado por el deny-all remoto
> (ítem 5 del E2E). Este `invoke` **solo funcionará si la cáscara expone el comando a la ventana
> local** — verifícalo en el E2E; si el frontend corre como página remota en 3100 y no obtiene
> IPC, el reinicio automático NO es posible y hay que mantener el aviso "cierra y reabre Mia"
> como camino alterno.

```ts
// En el handler de guardado de /activar, tras la respuesta OK del backend.
async function trasGuardarClaveDeRespaldo(): Promise<void> {
  // El objeto global solo existe si la cáscara concede IPC a esta ventana.
  const tauri = (window as any).__TAURI__;
  if (!tauri?.core?.invoke) {
    // Sin IPC: mantener el mensaje de reabrir Mia (comportamiento actual).
    mostrarAviso("Guardé tu clave. Cierra Mia por completo y vuelve a abrirla para activarla.");
    return;
  }
  try {
    mostrarAviso("Activando el motor de Mia… (unos segundos)");
    await tauri.core.invoke("reiniciar_litellm");
    mostrarAviso("Listo. El motor de Mia ya está activo con tu nueva clave.");
  } catch (e) {
    // Fallback seguro: si el reinicio falla, pedir reabrir a mano.
    mostrarAviso("Guardé tu clave. Cierra Mia por completo y vuelve a abrirla para activarla.");
  }
}
```

**Guardas a respetar (no negociables):**
- **Identidad:** nunca matar/adoptar por puerto; al relanzar, esperar `identity::litellm_health`
  (hijo propio). Si el puerto quedara ocupado, usar `identity::litellm_identity` con la master
  key leída por `read_dotenv_value` (`lib.rs:380-395`) — nunca adoptar sin master key.
- **Loopback:** cliente `reqwest .no_proxy()` y URLs `127.0.0.1`; no exponer nada fuera de loopback.
- **Single-instance:** intacto; el comando corre dentro de la única cáscara viva.
- **Concurrencia:** serializar contra `orchestrate`/`shutdown` vía `Mutex<Owned>` y respetar
  `owned.cleaned` (como `register_child`, `lib.rs:332-339`) para no relanzar si la ventana se
  está cerrando.
- **Gating remoto:** NO añadir una capability con `"remote"` apuntando a `localhost:3100`. El
  comando debe quedar accesible solo a la ventana local. Verificar en el ítem 5 del E2E que
  `localhost:3100` sigue sin IPC salvo el comando expuesto deliberadamente.

---

## Criterio de cierre del bloque instalador

F4 se da por cerrada cuando **todo** lo siguiente está en verde:

1. **Los dos `.exe` recompilados** (Paso 0) con `console=False` aplicado (decisión 1), y el
   backend verificado incluyendo `031_welcome_bootstrap.sql`, `schema.sql` y todas las
   migraciones (comandos de verificación del Paso 0 en `True`).
2. **El instalador NSIS compila** (`npm run tauri build`) y produce
   `Mia_0.1.0_x64-setup.exe` con los payloads laterales (mia-backend/mia-litellm/mia-frontend/
   pgsql) empaquetados y en su sitio junto al `.exe` instalado.
3. **Los gates automatizados pasan** en tu Windows: `scripts\run_tests.ps1` completo en verde
   (incluye `check_env_pins.py`, los 4 gates en frío, y los 2 en caliente `test_first_run.py`
   y `test_welcome_keys.py` con Postgres real).
4. **Los 10 ítems del E2E en frío (Paso 2) marcados** — que cubren los 7 puntos del Riesgo #59
   más la activación de llaves (`welcome.py`/`031`/`env_writer.py`).
5. **Riesgo #60 resuelto O explícitamente aplazado — con la arquitectura actual, la vía por
   defecto es APLAZADO.** Hoy el frontend se sirve como **página remota** en `localhost:3100`
   sin IPC (deny-all remoto, blindaje F2), así que el reinicio automático es **inalcanzable** tal
   cual (ver "Estado actual" del Riesgo #60). Por tanto:
   - **Vía por defecto (APLAZADO):** se deja el aviso "cierra y reabre Mia" como mitigación, se
     documenta #60 como pendiente con su razón, y el **ítem 6 del E2E pasa por su variante (a)**
     (escribe `.env` + muestra el aviso fuerte).
   - **Vía resuelto (solo si se reubicó `/activar` al `frontendDist` local `tauri://` con IPC, o
     se expuso otro canal que no conceda `remote` a 3100):** el comando `reiniciar_litellm`
     compila, se registra, y el **ítem 6 pasa por su variante (b)** — tras guardar, el motor
     responde sin reabrir, sin aviso, y `/v1/models` con la clave nueva responde en caliente.
   No dar por hecho el reinicio automático mientras `/activar` siga siendo página remota en 3100.
6. **Decisiones 2, 3 y 4 tomadas y anotadas** (firma, modo de instalación, WebView2), aunque
   sea para aplazar la firma a la etapa de distribución.
7. **Ninguna ventana negra ni jerga técnica** visible para el abogado en todo el flujo (§G),
   confirmado visualmente en la máquina limpia.

Cuando 1–7 estén en verde, se registra el cierre en `memory/progress.md` y
`memory/session-summaries.md` (protocolo de cierre del CLAUDE.md, solo con trigger explícito
de Pipe), y el bloque instalador queda terminado.
