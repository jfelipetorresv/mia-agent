# Opus5.5 high: preflight de entrega

Modelo confirmado: claude-opus-5-5. Solo lectura.

# Diagnóstico del smoke frontend fallido (core/Compact, 2d08474)

**Veredicto corto:** con la evidencia que hay no se puede decir si es un blocker real o un coldstart/timeout. El script se tragó la causa. Recuperar la entrega sin recompilar es posible, pero solo como artefacto verificado con `reused_payloads=true`, y **no como release final**: lo prohíbe el propio repo (`packaging/build_installer.ps1:361-363`). Solo he leído código y logs; no he ejecutado nada.

## 1. Qué está probado

- **El proceso siguió vivo los 20 s.** No se entró en la rama `HasExited` (`build_frontend.ps1:250-257`), así que no hubo crash ni EADDRINUSE.
- **No había squatter en 3100 al arrancar.** Falta el aviso "posible squatter".
- **Next llegó a escuchar.** El stdout dice `Local: http://localhost:3100`, `Network: 0.0.0.0:3100`, `✓ Ready in 0ms` y **después** `✓ Running next.config took 172ms`. En Next 16.3, "Ready" sale antes de que termine la inicialización del handler, y el config lleva `preloadEntriesOnStart: true`. **Ready no significa que ya sirva HTTP.**
- **No sabemos qué recibió cada petición.** El `catch {}` vacío (`:262-264`) oculta si hubo conexión rechazada, si cada petición pasó de `TimeoutSec 2`, si hubo un 500 o si falló la redirección. `finally` borró `smoke-stderr.log` (ya no existe). `smoke-stdout.log` **sigue en `dist/mia-frontend`**: su borrado falló, seguramente porque node aún tenía el handle abierto.
- **`/` es la única raíz dinámica (ƒ) y solo hace `redirect()`**: 307 hacia `/casos`, que es estática (`frontend/app/page.tsx:12`). Invoke-WebRequest de PowerShell 5.1 sigue redirecciones por defecto, así que esto es un candidato, no la causa.
- **No hay `proxy.ts`, `middleware.ts` ni `instrumentation.ts`**, así que no hay un fetch al backend en el camino de `/`.

## 2. Hipótesis, de más a menos probable

1. **Coldstart por encima del harness.** Tras 2 h de build con 11 workers, el preload de todas las rutas lee unos 2 270 archivos recién copiados, y Defender los escanea al acceder. Si cada GET pasa de 2 s mientras tanto, los 20 s se agotan sin ningún 200. Encaja con lo observado, pero no está probado.
2. **Defecto del harness con la redirección o la lectura de la respuesta en IWR 5.1.** Poco probable, pero no está descartado.
3. **Blocker real en el payload**: un 500 de render, un módulo que falta en el trazado del standalone o un error en `/casos`. No se puede descartar porque stderr se perdió.

Sobre el producto: la cáscara espera hasta **180 s**, sondea cada 2 s con timeout de 4 s y exige la huella de cabeceras (`lib.rs:1380`, `identity.rs:134`). Un coldstart de 20–60 s no rompe el producto. Si el primer 200 en frío tarda más de 180 s, entonces sí es blocker de producto aunque el payload esté sano.

## 3. Método mínimo para root (sin rebuild)

1. **Estado previo.** Comprobar que no hay ningún `node.exe` cuyo `Path` esté bajo `dist\mia-frontend` ni nada escuchando en 3100. Si queda un huérfano del smoke, sería un squatter.
2. **Hash previo.** Hashear el árbol `dist\mia-frontend` (SHA-256 por archivo más un agregado).
3. **Copia en TEMP.** Arrancar sobre una copia en TEMP, **nunca in situ**: el server escribe `.next/cache` y contaminaría el payload. Entorno: `HOSTNAME` eliminado, `PORT` libre, el node.exe de la propia copia, PID registrado, stdout y stderr en TEMP.
4. **Mediciones:**
   - tiempo hasta el primer TCP connect a `127.0.0.1:PORT`;
   - `curl.exe -sS -o NUL -D - -w "%{http_code} %{time_starttransfer} %{redirect_url}" --max-time 60` sobre `/` **sin** `-L`, después sobre `/casos`, después sobre `/` con `-L`;
   - registrar el código o error de cada intento.
5. **Cuando llegue el 200:** `Get-NetTCPConnection -LocalPort PORT -State Listen` debe dar `OwningProcess == PID`, con `X-Frame-Options: DENY` y `X-Content-Type-Options: nosniff`.
6. **Repetir con 2–3 copias frescas.** El coldstart por Defender se repite en cada copia nueva.
7. **Hash posterior** del árbol original de dist, que debe ser idéntico al previo.

**Cómo leer el resultado:**

| Resultado | Clasificación |
|---|---|
| 500, error en stderr o sin listener IPv4 | **Blocker real** del payload. Hay que recompilar el frontend (solo esa pieza). |
| Primera respuesta de más de 2 s y las siguientes rápidas, con el primer 200 por debajo de 180 s | **Defecto del harness**, payload sano |
| 307 y luego 200 en `/casos` con curl, pero IWR falla | **Defecto del harness** |
| Primer 200 en frío por encima de 180 s | **Blocker de producto** |

## 4. Admisibilidad de recuperar con `-SkipPayloads`

Se admite como **artefacto verificado, no final**, si se cumplen todos estos puntos:

- **HEAD intacto.** `git rev-parse HEAD` = `2d08474…` y `git status --porcelain --untracked-files=all` vacío. No se toca `build_frontend.ps1` en esta entrega: un commit cambia HEAD y `:155` rechazaría el manifiesto backend, lo que obliga a recompilar el backend. El arreglo del harness va en un commit posterior.
- **Manifiesto backend exacto:** `profile=core`, `source_dirty=false`, `source_commit=2d08474…`. El script ya lo valida.
- **Vínculo del frontend con esta corrida.** `SkipPayloads` solo comprueba que los archivos existan (`:206-217`). Hay que demostrar tres cosas:
  - `dist/mia-frontend/.next/BUILD_ID` igual a `frontend/.next/BUILD_ID`;
  - la fecha de ese BUILD_ID es posterior al inicio del build en el log;
  - el árbol de dist es igual al de `.next/standalone`, salvo `node.exe`, `.next/static` y `public/`.
- **Vínculo de LiteLLM:** la fecha y el hash de `mia-litellm.exe` corresponden a esta corrida, cuyo humo PASS está en el log, líneas 330-337.
- **Limpieza de dist antes del bundler.** Borrar `smoke-stdout.log` y cualquier `*.log` o `.next/cache`: `Assert-NoPrivateBuildContent` solo mira nombres de directorio, así que el log viajaría en el instalador.
- **Sin `.env*`.** `Get-ChildItem -Force -Recurse -Filter '.env*'` sobre `dist\mia-frontend` debe dar cero resultados; basta con listar nombres. El build cargó `.env.local` y el preflight de Opus puso como condición del APTO que no haya `.env*`. Mi Glob vacío **no prueba nada**, porque omite archivos ocultos e ignorados.
- **Smoke independiente PASS** según el punto 3, con PID, headers y hashes antes y después guardados en `output/validation/`.
- **Manifiesto de release** con `reused_payloads=true`, más la advertencia "NO es autorizable como release final" conservada en el informe.

## 5. Qué bloquea y qué no

- **Bloquea cualquier redacción de "release final" o "entrega autorizada".** Es la regla de `build_installer.ps1:361-363`. Solo el dueño del repo puede cambiarla, y de forma explícita.
- **Bloquea el bundling con SkipPayloads hasta tener evidencia:** el `.log` dentro de dist, el vínculo BUILD_ID/commit del frontend y la ausencia de `.env*`.
- **Queda como deuda del harness**, para un commit posterior:
  - el `catch` vacío;
  - el timeout de 20 s y 2 s por petición, muy por debajo de los 180 s del producto;
  - el `finally` que borra la evidencia y ni siquiera lo consigue con stdout.

No se exige instalación productiva en ningún punto.