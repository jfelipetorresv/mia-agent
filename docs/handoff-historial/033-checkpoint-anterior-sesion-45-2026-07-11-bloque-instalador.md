## Checkpoint anterior: Sesión 45 (2026-07-11) — BLOQUE INSTALADOR: Fase 4 (instalador de doble clic) ENSAMBLADA — falta SOLO el E2E en frío de Pipe

### Qué se hizo esta sesión (lenguaje simple)

Se armó el **instalador de doble clic** que un abogado usa para instalar MIA sin tener Python,
Node ni base de datos en su computador. La cáscara de escritorio no empaqueta sola los motores,
así que se cableó cómo se colocan todos junto al programa y se incluyó una **base de datos
portable con el buscador vectorial adentro**. Resultado real y probado: `Mia_0.1.0_x64-setup.exe`
(~452 MB), que instala sin pedir permisos de administrador y **funciona sin internet**.

- **Ensamblaje (`packaging/build_installer.ps1` + `tauri.conf.json`):** recompila los tres motores,
  copia el PostgreSQL portable (con pgvector) y arma el instalador NSIS. Cada motor + el archivo
  de arranque quedan **directamente junto al programa** (verificado instalando en una carpeta
  aislada: nada queda mal ubicado — era la duda central de esta fase).
- **La incógnita crítica se resolvió a favor:** la cáscara busca los motores en rutas fijas junto
  a su exe, y ahí quedan exactamente. Instalación de prueba: 804 MB en disco, todo en su sitio.

### Frontend a revisar (Cursor — capa 3): NO APLICA
Esta sesión fue empaquetado + cáscara (Rust) + scripts. No hay UI nueva. La capa 3 pendiente es
de **Pipe**, no de Cursor (ver abajo).

### Resultado de verificación (3 capas)

- **Capa 1:** gates del instalador verdes — `test_installer_bundle` 30/30 (NUEVO), `test_packaging`
  23/23, `test_litellm_packaging` 60/60, `test_frontend_packaging` 24/24, `test_shell_hardening`
  77/77, `test_first_run` 68/68 — + HALT `test_rls` 12/12 y `check_env_pins` 9/9 + `test_welcome_keys`
  39/39. Línea base sube de 85 a 86 suites. Instalador producido y verificado por instalación
  aislada (payloads junto al exe, sin subcarpeta `resources/`, pgvector presente, pgAdmin ausente).
- **Capa 2:** TRES revisores adversariales independientes (seguridad, corrección/build, coherencia
  cáscara/§G). **0 BLOQUEANTES**, ningún secreto de Pipe viaja en el instalador, DB bien endurecida.
  **5 correcciones aplicadas y re-verificadas:** (1) **console REVERTIDO a True** — la cáscara ya
  oculta la ventana con CREATE_NO_WINDOW; el `console=False` que se había puesto vaciaba el stdout
  con el que el primer arranque le dice al abogado *por qué* falló (regresión introducida y
  corregida en la misma sesión); (2) **frontend atado a 127.0.0.1** — estaba en 0.0.0.0, visible
  para toda la red del despacho; (3) **pgAdmin fuera** del paquete de base de datos (−736 MB:
  860→124 MB, y menos superficie de ataque); (4) **WebView2 `offlineInstaller`** para instalar sin
  internet; (5) gate endurecido. Detalle en `memory/session-summaries.md` sesión 45 y Riesgo #59.
- **Capa 3: PENDIENTE — de Pipe (ÚNICO pendiente de F4):** instalar el `.exe` en una **máquina
  100% limpia** (sin Python/Node/Postgres, estado virgen) con doble clic y confirmar el primer
  arranque en frío + el viaje de bienvenida. Es física: no se puede hacer en la máquina de dev
  (tiene el entorno + colisión de puerto 55432). El instalador está en
  `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`.

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** el E2E en frío en máquina limpia (arriba) — cierra el bloque instalador.
2. **Riesgo #60 (ola futura):** el reinicio automático del motor de modelos tras guardar la clave
   en el wizard NO se hizo en F4 (requiere IPC de Tauri); la mitigación de F3 (clave obligatoria +
   aviso de reabrir) sigue vigente.
3. **ACCIÓN DE PIPE (sin cambio):** firma digital (Azure Trusted Signing) para vender sin la
   advertencia de "editor desconocido" de Windows, y registrar las apps OAuth.

### Trabajo en background sin leer
Nada — 1 recon, 2 builds delegados y 3 revisores de capa 2: todo leído y reflejado aquí. La
instalación de prueba del build corregido la corrió y verificó la propia terminal (804 MB, layout
correcto) y se limpió (carpeta + clave de registro).

### Decisiones tomadas y suposiciones declaradas

- **console=True (no False):** la ventana negra la elimina la cáscara con CREATE_NO_WINDOW, no el
  spec; windowed rompía el diagnóstico del primer arranque. Cierra Riesgo #59 pt 3/7 por diseño.
- **installMode currentUser:** instala sin pedir administrador (más fácil para el abogado, §B);
  si algún día se quisiera "para todos los usuarios" cambia a perMachine (implica UAC).
- **WebView2 offlineInstaller** (+~130 MB al instalador) elegido sobre el descargador para que el
  E2E en frío/offline no falle — coherente con local-first. Reversible en `tauri.conf.json`.
- **pgAdmin/StackBuilder excluidos** del pgsql: MIA nunca los usa (conecta por psycopg + initdb).
- El Postgres portable se toma de `..\tools\postgres16-portable-full\pgsql` (fuera del repo);
  `build_installer.ps1` lo autodetecta y exige pgvector antes de empaquetar.

---

