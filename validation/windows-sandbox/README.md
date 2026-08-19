# Gate de ciclo de vida en Windows Sandbox

Valida el setup en una VM Windows desechable, sin datos reales, secretos ni red externa. El
host solo monta los instaladores y este harness como lectura; únicamente la carpeta de
evidencia es escribible.

## Cobertura

1. Instalación silenciosa del setup vigente.
2. Primer arranque, bootstrap local y health de backend/frontend.
3. Cierre, segundo arranque y health.
4. Creación y verificación criptográfica del backup.
5. Restore real: crea y verifica el backup, muta un centinela sintético, exige que una
   confirmación de base incorrecta falle sin modificar datos, ejecuta `restore --source ...
   --confirm-database mia`, comprueba el centinela anterior y el backup preventivo.
6. Upgrade real: solo corre si semver y cronología avanzan; instala 0.2.0, siembra un
   centinela sintético, instala 0.3.0 y exige versión, health y datos preservados.
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

`outcome=pass` exige todos los pasos. `blocked` y `fail` retornan código distinto de cero.
Restore y upgrade nunca se aprueban por presencia de comandos: requieren sus centinelas.

La ejecución más reciente del 14 de agosto de 2026 no abrió un guest operativo: `WindowsSandbox.exe` cerró
sin `result.json`. Aunque el ejecutable, hipervisor y servicios estaban presentes, esa VM no se
declara verde. El diagnóstico mínimo está en `diagnostic-2026-08-14.json`; los directorios
`runs/` se ignoran porque contienen WSB y logs efímeros reproducibles.

## Prueba offline del harness

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File validation\windows-sandbox\test-harness.ps1
```
