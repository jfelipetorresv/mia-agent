# F5 — Congelar y empaquetar

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F5".

## Objetivo
Re-ensamblar el instalador de escritorio con el código post-F4, y arreglar el bug del minuto cero
(la DB portable no arranca sola) antes de gastar el ciclo caro de la prueba en frío (F6).

## Pasos
1. **Adelanto — sonda de instalabilidad**: YA CORRIÓ al cierre de F2 (no espera a F5); si no corrió
   ahí, correrla aquí primero: compilar solo el backend (`packaging/build_backend.ps1`) y
   `--first-run` contra una DB de scratch en dev.
2. Re-ensamblar payloads con el código post-F4:
   - `packaging/build_backend.ps1` (el `mia-backend.exe` actual NO trae `--first-run` ni las 46+
     migraciones — verificarlo de nuevo tras F4),
   - `packaging/build_frontend.ps1`,
   - `packaging/build_litellm.ps1`,
   - `packaging/build_installer.ps1` → NSIS en
     `desktop/src-tauri/target/release/bundle/nsis/`.
3. **Arreglar el bug del minuto cero** (diagnosticado y CONFIRMADO en F0, spec `00-f0-preflight.md`):
   `Abrir Mia.cmd` → `scripts/start_all.ps1` solo levanta LiteLLM/API/frontend, NUNCA la DB portable
   en 55432. Debe levantar también la DB — hoy es un prerrequisito manual y un abogado no arranca
   Postgres a mano.
4. Reactivar gates diferidos: `execution/test_welcome_keys.py`, `test_rls` post-bootstrap.
5. Smoke local del instalador antes de gastar el frío (los reintentos de ~452MB son caros).

## Archivos críticos
`packaging/build_*.ps1`, `desktop/src-tauri/`, `scripts/start_all.ps1`.

## Salida medible (copiada del plan maestro)
Instalador re-ensamblado que aplica las migraciones desde cero; "Abrir Mia" levanta
DB+LiteLLM+API+frontend sin pasos manuales, verificado con la validación de identidad de servicios de
la cáscara endurecida; gates diferidos verdes.

## Gates
HALT completo + `test_welcome_keys.py` + `test_rls` post-bootstrap + smoke local del instalador
(`--first-run` desde cero).

## Modelos (matriz del plan)
Diagnóstico de causa raíz difícil (build del instalador que falla): Codex (xhigh); ejecución
dirigida de los builds: Sonnet (medium).
