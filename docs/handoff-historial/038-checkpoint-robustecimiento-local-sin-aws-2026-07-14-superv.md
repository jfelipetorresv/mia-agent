## Checkpoint: robustecimiento local sin AWS (2026-07-14) — supervisor autorreparable

- La cáscara Tauri vigila cada 5 segundos backend, frontend y LiteLLM después del arranque.
  Exige 3 fallos consecutivos, reinicia únicamente hijos propios y se detiene tras 3 recaídas
  por hora. Los servicios adoptados se observan y avisan, pero nunca se matan ni reemplazan.
- El reinicio automático del motor comparte exclusión con el reinicio manual y revalida salud
  después de tomarla; así no actúa sobre un PID nuevo usando un sondeo viejo. `shutdown()` sigue
  gobernando el cierre y `register_child()` mata cualquier hijo creado después de cerrar.
- `RuntimeHealthBanner` muestra recuperación/error en lenguaje llano dentro de la app; en navegador
  normal no aparece. Gates: `cargo check` PASS, tests Rust 3/3, gate estático PASS, `tsc` PASS y
  build Next 15/15. Claude Code re-auditó la carrera y dio **PASS sin bloqueantes**.

---

