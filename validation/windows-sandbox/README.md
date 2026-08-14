# Gate de ciclo de vida en Windows Sandbox

Valida el setup en una VM Windows desechable, sin datos reales, secretos ni red externa. El
host solo monta los instaladores y este harness como lectura; únicamente la carpeta de
evidencia es escribible.

## Cobertura

1. Instalación silenciosa del setup vigente.
2. Primer arranque, bootstrap local y health de backend/frontend.
3. Cierre, segundo arranque y health.
4. Creación y verificación criptográfica del backup.
5. Restore: fail-closed. La versión actual no expone una acción `restore` en
   `mia-backend --maintenance`; el gate lo registra como bloqueo y nunca convierte `verify`
   en una restauración ficticia.
6. Upgrade: solo corre si semver y cronología del artefacto avanzan. Hoy se bloquea porque el
   setup vigente es 0.1.0 (14 de agosto) y el setup rotulado 0.2.0 es más viejo (12 de agosto).
   0.1.0 sobre 0.2.0 sería downgrade; 0.2.0 sobre 0.1.0 falsificaría la cronología del build.
7. Reinstalación silenciosa de la misma versión, que sí es semánticamente válida.
8. Desinstalación silenciosa y auditoría separada de binarios/registro, listeners y datos de
   usuario preservados.

## Ejecución

Preflight sin abrir la VM:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File validation\windows-sandbox\run-host.ps1 -PreflightOnly
```

Ciclo real en Sandbox:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File validation\windows-sandbox\run-host.ps1
```

El host crea `validation/windows-sandbox/runs/sandbox-AAAAMMDD-HHMMSS/` con:

- `host-manifest.json`: hashes, tamaños, versiones, capacidad de Sandbox y decisión semántica;
- `mia-lifecycle.wsb`: configuración exacta de la VM;
- `guest-transcript.log`: bitácora del guest sin cuerpos de health ni valores de `.env`;
- `result.json`: pasos, duraciones, bloqueos, fallas y outcome;
- `host-failure.json`: solo si la VM cierra o vence el tiempo sin resultado.

`outcome=pass` exige todos los pasos. `blocked` y `fail` retornan código distinto de cero. Con
el producto actual se espera `blocked` hasta que exista un restore real y un par de artefactos
de upgrade cuya versión coincida con su cronología; esto es evidencia honesta, no un defecto
del gate.

La ejecución del 14 de agosto de 2026 no abrió un guest operativo: `WindowsSandbox.exe` cerró
sin `result.json`. Aunque el ejecutable, hipervisor y servicios estaban presentes, esa VM no se
declara verde. El diagnóstico mínimo está en `diagnostic-2026-08-14.json`; los directorios
`runs/` se ignoran porque contienen WSB y logs efímeros reproducibles.

## Prueba offline del harness

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File validation\windows-sandbox\test-harness.ps1
```
