# Opus5.5 high: preflight de entrega

Modelo confirmado: claude-opus-5-5. Solo lectura.

Dictamen: **APTO en preflight estático**, con una condición que bloquea si se cumple: que aparezca un `.env*` dentro de los payloads (detalle en el hallazgo 1). Revisé solo con Read/Grep/Glob. No ejecuté ni edité nada, no leí `.env` ni credenciales y el Harness sigue intacto.

## Resultado por riesgo

**Mezcla de commit o payload: no hay.**
- `packaging/build_installer.ps1:76-86` falla si las 4 versiones no coinciden o si el checkout está sucio (incluye archivos sin seguimiento), y fija HEAD.
- Sin `-SkipPayloads`, los tres payloads se recompilan en la misma corrida (`:131-141`).
- `:149-156` exige que el manifiesto del backend tenga el perfil pedido, `source_dirty=false` y el mismo commit.
- `:309-313` falla si el instalador tiene otro nombre o es anterior a la corrida.
- Versiones: 0.3.3 en `tauri.conf.json:4`, `desktop/package.json:4`, `Cargo.toml:3`, `Cargo.lock:1988`, `frontend/package.json:3` y los dos `package-lock.json`.

**Migraciones: consistentes.**
- La especificación de PyInstaller copia todos los `.sql` del checkout (`packaging/mia-backend.spec:80-84`). Hay 64 archivos, del 003 al 067, sin el 061 y sin prefijos repetidos.
- El primer arranque aplica el esquema, las migraciones y el checkpointer, y solo al final escribe el marcador (`backend/mia/setup/first_run.py:377-392`). Si no hay marcador o el código de salida no es 0, el build falla (`build_installer.ps1:264`).
- La 067 es segura sobre datos existentes. El índice de no finales usa las mismas columnas que el de la 051, y el de finales añade una columna. Las dos restricciones son más débiles que la anterior, así que no pueden chocar con filas que ya existen.

**Destrucción fuera del workspace: no encontré.**
- Todos los borrados apuntan a `packaging/dist/<payload>`, a `packaging/build/<payload>` o a carpetas temporales con GUID (`build_backend.ps1:130-131`, `build_litellm.ps1:126-127`, `build_frontend.ps1:135`, `build_installer.ps1:278`).
- `robocopy /MIR` solo escribe en `dist/pgsql` (`:174`).

**Secretos:**
- El `.env` del primer arranque se genera en una carpeta temporal y se borra.
- El humo de LiteLLM usa una clave de prueba, un directorio sin `.env` y limpia las variables `PG_*` (`build_litellm.ps1:175-214`).

**Saltos de checks (no bloquean, pero los declaro):**
- `check_env_pins.py` solo corre si faltaba pyinstaller o hooks-contrib (`build_backend.ps1:76-100`).
- El chequeo de checkout limpio corre una sola vez, al inicio (`build_installer.ps1:80`). El `source_dirty` del backend se calcula antes de compilar el frontend (`build_backend.ps1:220`).
- El filtro de contenido privado se ejecuta antes del primer arranque (`build_installer.ps1:225` frente a `:237`).

## Hallazgos

1. **Condicionalmente bloqueante: el filtro solo mira nombres de carpetas, no archivos.**
   - `build_installer.ps1:220-227` y `build_backend.ps1:174-179` no detectan un `.env`.
   - Next 16 en modo standalone puede copiar `frontend/.env` o `.env.production` a `.next/standalone`. `build_frontend.ps1:141` lo pasaría a `dist/mia-frontend` y `tauri.conf.json:42` lo metería en el instalador.
   - El `.gitignore` raíz (línea 1) ignora `.env` en cualquier nivel, así que el chequeo de checkout limpio no lo ve. No pude comprobar si ese archivo existe (Glob agotó el tiempo y no leo `.env`).
   - Si aparece `.env*` en cualquier `dist/*`, el artefacto es NO APTO.
2. **Bug latente, sin efecto en core.**
   - PowerShell 5.1 escribe `mia-component-manifest.json` con BOM (`build_backend.ps1:233`), pero `backend/mia/config.py:55` lo lee con `utf-8` estricto.
   - El manifiesto queda marcado como inválido y todas las capacidades salen en falso. En core, OCR y voz ya eran falsos, así que no cambia nada; en los perfiles ocr/full sí ocultaría OCR.
   - `backup.py:238` sí tolera el BOM (`utf-8-sig`).
3. **Residuales.**
   - Los payloads de frontend y LiteLLM no llevan sello de commit. Su procedencia depende de una única corrida sin `-SkipPayloads`.
   - `node_modules` y los dos entornos virtuales vienen del estado local; no se reinstalan.
   - El primer arranque hereda el entorno del shell.

## Matriz para el ejecutor

| # | Qué cotejar | Esperado |
|---|---|---|
| 1 | Antes de construir: `git diff --stat 95a24d5 2d08474 -- packaging desktop/src-tauri frontend/next.config.mjs frontend/package*.json backend/pyproject.toml` | Solo versiones o cambios conocidos; así vale el precedente de 0.3.2 |
| 2 | Antes de construir: `Test-Path frontend\.env, frontend\.env.production` (sin leer el contenido) | Ambos `False` |
| 3 | Antes de construir: `.venv\Scripts\python.exe execution\check_env_pins.py` (opcional) | exit 0 |
| 4 | Shell nueva, sin `MIA_TEST_ENV_FILE`, `DATABASE_URL` ni `PG_*` | Confirmado |
| 5 | `desktop/src-tauri/target/release/bundle/nsis/mia-release-manifest.json` | `version=0.3.3`, `commit` = SHA completo de `2d08474`, `reused_payloads=false`, `backend_profile=core`, `webview_profile=compact`, `capabilities.ocr/voice=false`, `first_run_ms` presente, `installer.file=Mia_0.3.3_x64-setup.exe` |
| 6 | SHA-256 y bytes del instalador en `nsis/` y de la copia en Downloads | Idénticos a `installer.sha256` y `installer.bytes` |
| 7 | `dist/mia-backend/mia-component-manifest.json` | Mismo `source_commit`, `source_dirty=false`, `profile=core` |
| 8 | `dist/mia-backend/_internal/mia/db/` | `schema.sql` y 64 `.sql` en `migrations/`, incluida la 067 |
| 9 | Número de archivos de `mia-backend` en el manifiesto de release | `files_excluding_manifest + 1`; si no cuadra, el primer arranque escribió dentro del payload |
| 10 | Búsqueda recursiva con `-Force` en los cuatro `dist/*` | Sin `.env*`, `.mia-setup-complete`, `pgdata`, `mia-data` ni `.mia-backup-key*` |
| 11 | `dist/pgsql/mia-pg-tools.sha256.json` | 4 hashes; sin `pgAdmin 4` ni `StackBuilder` |
| 12 | Log del build | PASS en el humo de LiteLLM (salud, 200/401 y escucha solo en loopback), PASS en el humo del frontend (200, cabeceras y PID propio) y la línea «Primer arranque: N ms» |
| 13 | Después del build: `git status --porcelain` y `git rev-parse HEAD` | Limpio y HEAD igual. Si solo cambian `tsconfig` o `next-env`, es cosmético; cualquier otro archivo bloquea |

## Límites

- Esta lectura no demuestra que el build termine bien, ni que el instalador sea correcto, ni que la app instalada o el WebView real funcionen.
- El primer arranque del build solo cubre una instalación nueva. La actualización sobre la base de 0.3.2 pasa por `maintenance.py:310` y no se prueba aquí.
- Los logs del primer arranque se borran cuando termina bien, así que el conteo de migraciones aplicadas solo se puede cotejar con la fila 8.