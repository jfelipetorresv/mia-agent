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

Para cada servicio (DB → backend → frontend): si el puerto **ya responde**, la
cáscara lo adopta sin apagarlo; si no, lo lanza y espera su salud
(`health_url` para el backend, `200` para el frontend; polling cada 2 s). Cuando
backend y frontend responden, la ventana navega a `frontend.url`.

Si un puerto está tomado por un proceso que **no** responde salud (un extraño),
la cáscara no lanza un competidor: avisa de inmediato en español llano. Durante
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

## Deuda conocida (para el bloque del instalador)

- Guard de instancia única (`tauri-plugin-single-instance`): hoy dos cáscaras
  simultáneas pueden pisarse la DB.
- CSP explícita en `tauri.conf.json` y prueba empírica de que el IPC de Tauri
  NO responde desde `localhost:3100` tras `navigate()` (el gating remoto de
  Tauri v2 lo cubre por defecto, pero hay que probarlo antes de entregar).
- La adopción de la DB es solo por puerto (sin verificar que sea Postgres).
