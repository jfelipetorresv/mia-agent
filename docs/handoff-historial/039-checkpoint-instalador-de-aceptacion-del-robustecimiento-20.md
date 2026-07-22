## Checkpoint: instalador de aceptación del robustecimiento (2026-07-14)

- Se reconstruyó desde cero el instalador NSIS de la rama
  `feature/robustecimiento-sin-aws`: backend, LiteLLM, frontend, PostgreSQL
  portátil y la cáscara Tauri. Artefacto local:
  `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`
  (452.488.052 bytes; SHA-256
  `A9E80ACEE007D5A2407107F101F751D4160964C665305749416CEC8535F4FF33`).
- Gates posteriores al build: installer 30/30, backend packaging 23/23,
  LiteLLM packaging 66/66, frontend packaging 24/24, shell hardening 84/84,
  first run real 68/68 y supervisor PASS. Se actualizó el gate antiguo que
  contaba exactamente tres usos de `child_died`: ahora protege los tres
  bucles de arranque sin rechazar los usos adicionales del supervisor.
- Claude Code repitió controles y verificó el hash. Veredicto: **PASS
  condicionado para prueba de aceptación local; no producción**. El siguiente
  gate es instalar y arrancar el NSIS real, recorrer visualmente la app y
  comprobar LiteLLM/backend/frontend de punta a punta.
- El instalador no tiene firma de código. Es válido para prueba local, pero la
  firma y la aceptación visual son requisitos antes de distribuirlo a terceros.

---

