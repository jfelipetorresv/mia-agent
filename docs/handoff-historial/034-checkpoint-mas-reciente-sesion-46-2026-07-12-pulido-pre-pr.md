## Checkpoint más reciente: Sesión 46 (2026-07-12) — PULIDO PRE-PRUEBA: Riesgo #60 cerrado + auditoría final de seguridad/bugs + pre-flight del motor sin llaves

### Qué se hizo esta sesión (lenguaje simple)

Pipe pidió, antes de instalar en frío, "dejarlo listo para pruebas": mejorar lo que quedaba, revisar
seguridad y bugs, y solucionar lo que saliera. Se corrieron **tres auditorías adversariales
independientes** (seguridad, corrección/E2E en frío, y revisión del diff) — **0 bloqueantes en todo**.

- **Se cerró el Riesgo #60 (mejora que Pipe pidió expresamente):** el motor de modelos ahora se
  **reinicia solo, en caliente**, cuando el abogado guarda su clave en la pantalla de bienvenida —
  ya NO hay que cerrar y reabrir MIA. Se implementó vía un comando interno de la cáscara Tauri
  (`restart_litellm`): el frontend, que corre dentro de la cáscara, lo invoca tras guardar la clave;
  la cáscara mata el motor viejo, espera a que libere el puerto y lo re-lanza leyendo la clave nueva,
  re-asignándolo al Job Object anti-huérfanos. En modo desarrollo (navegador) degrada solo al aviso
  de "reabre Mia", sin romper nada.
- **Se eliminó la única incógnita real de tu prueba (pre-flight del motor sin llaves):** nadie había
  encendido `mia-litellm.exe` con CERO llaves de proveedor, que es exactamente el estado del arranque
  en frío cuando el abogado difiere las claves. Se probó: arranca en ~1 s, responde salud y lista los
  5 modelos. Ya no es un riesgo.
- **Dos endurecimientos de seguridad baratos:** validación anti-inyección extra al escribir el `.env`
  y permisos restrictivos (solo el dueño) sobre el archivo de claves.

### Frontend a revisar (Cursor — capa 3): un cambio mínimo
`frontend/app/activar/page.tsx` (`finish()`): tras guardar la clave, si corre dentro de la cáscara,
invoca `restart_litellm` y, solo si el motor se reinició, quita el aviso "cierra y reabre". En
navegador (dev) el aviso se conserva. Cubierto por gate + revisión; falta el recorrido visual en vivo.

### Resultado de verificación (3 capas)
- **Capa 1:** `cargo build` exit 0; `test_shell_hardening` **84/84** (sube de 77 con 7 checks nuevos
  del reinicio), `test_packaging` 23/23, `test_litellm_packaging` 60/60, `test_first_run` 68/68.
  **NO se re-corrieron `test_welcome_keys` ni `test_rls`** porque la DB dev de mia no estaba encendida
  (puerto 55432); el único cambio en esa ruta (validación `\n`/`\r` en `env_writer`) se micro-probó
  aparte. **Pendiente: correrlos en el próximo arranque con la DB arriba.**
- **Capa 2:** revisor adversarial independiente de concurrencia/ciclo de vida sobre el diff de la
  cáscara — **0 bloqueantes, 0 mayores** (sin deadlocks, ningún Mutex cruza `await`, el flag de
  reinicio no se fuga, el proceso re-lanzado se re-asigna al Job, caminos "no-aplica" seguros para
  dev/adoptado/cerrando). 3 menores cosméticos/pre-existentes, ninguno rompe la prueba.
- **Capa 3: PENDIENTE — de Pipe (sin cambio respecto a F4):** el E2E en frío en máquina 100% limpia
  sigue siendo el único pendiente para cerrar el bloque instalador. Ahora, al guardar la clave de
  respaldo en `/activar`, el motor debe quedar activo SIN reabrir (antes obligaba a reabrir).

### Pendientes y próximo paso
1. **Capa 3 de Pipe:** E2E en frío (doble clic → primer arranque → viaje de bienvenida → guardar clave
   y ver que el motor queda activo sin reabrir). En `desktop/src-tauri/target/release/bundle/nsis/`.
   Nota: el `.exe` en el bundle es de la sesión 45; si se quiere probar el reinicio en caliente del
   #60 hay que RE-ENSAMBLAR el instalador (`packaging/build_installer.ps1`) para incluir la cáscara
   recompilada de esta sesión.
2. **Correr `test_welcome_keys` + `test_rls`** con la DB dev encendida (verificación diferida de capa 1).
3. **Deuda consciente nueva (Riesgo #61), NO bloquea la prueba:** identidad de cáscara falsificable
   solo por un atacante local (aceptado en modelo mono-abogado); carpeta de datos = carpeta de
   programa (aplazado); el setup no re-corre migraciones en una actualización futura (deuda de
   "update").
4. **Acciones de Pipe sin cambio:** firma digital (Azure Trusted Signing) + registrar apps OAuth.

### Trabajo en background sin leer
Nada — 3 auditores (seguridad/bugs/diff), 1 ejecutor y 1 recon de diseño: todo leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas
- **El reinicio del motor lo dispara el frontend, no el backend:** el frontend ya vive dentro de la
  cáscara Tauri (`withGlobalTauri`), así que invoca el comando directo; el backend Python no tiene
  canal hacia la cáscara. Más limpio y sin dependencias nuevas.
- **El aviso "cierra y reabre" solo se borra si el motor confirma que se reinició** (no incondicional):
  si el motor fue adoptado o hay un reinicio en curso, se conserva el aviso — más honesto.
- **Se corrigió lo barato y se DOCUMENTÓ lo riesgoso** (Riesgo #61): cambiar el layout de carpetas o
  la firma de identidad justo antes del E2E en frío es más peligroso que el problema que resuelven;
  mejor con la prueba de Pipe como red.
- Los comandos de app de Tauri v2 no requieren ACL de capabilities (la CSP ya permite `ipc:`).

---

