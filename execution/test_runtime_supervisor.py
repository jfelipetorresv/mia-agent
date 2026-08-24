"""Gate estático del supervisor local del escritorio. Exit 0 = PASS."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rust = (ROOT / "desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
layout = (ROOT / "frontend/app/layout.tsx").read_text(encoding="utf-8")
banner = (ROOT / "frontend/app/_components/RuntimeHealthBanner.tsx").read_text(encoding="utf-8")

assert "supervise_runtime(handle2.clone(), supervisor_cfg).await" in rust
assert rust.index("orchestrate(handle2.clone(), cfg") < rust.index("supervise_runtime(handle2.clone()")
assert 'owned_pid(&shared, "backend").is_some()' in rust
assert 'owned_pid(&shared, "frontend").is_some()' in rust
assert 'owned_pid(&shared, "litellm").is_some()' in rust
assert "SUPERVISOR_FAILURES_BEFORE_RESTART: u8 = 3" in rust
assert "SUPERVISOR_MAX_RESTARTS: u8 = 3" in rust
assert rust.count("terminate_owned(&shared") >= 3 and "if !current_died" in rust
assert "wait_port_free" in rust
assert ".compare_exchange(false, true" in rust
assert "El reinicio manual pudo completarse" in rust
assert "if closing(&shared)" in rust
assert 'emit(&app, "runtime-error"' in rust
assert "<RuntimeHealthBanner />" in layout
# 2026-08-23: el banner dejó de escuchar IPC (`__TAURI__.event.listen`) — la ventana
# de MIA es un ORIGEN REMOTO sin IPC por el hardening, así que ese camino estaba
# muerto desde siempre (HANDOFF 2026-08-19). Ahora la cáscara RETIENE el último aviso
# `runtime-*` y el banner lo lee por el puente `mia-shell` (POST /runtime/health).
assert 'shellInvoke<RuntimeHealth>("runtime/health")' in banner
assert '"runtime-ok"' in banner
assert 'stage.starts_with("runtime-")' in rust     # la retención en emit()
assert '"/runtime/health"' in rust                  # la ruta del puente
assert "runtime_notice" in rust

print("PASS: supervisor arranca después de Mia y solo repara hijos propios")
print("PASS: crash-loop acotado, cierre coordinado y aviso visible")
