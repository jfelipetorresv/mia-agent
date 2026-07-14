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
assert 'listen("mia://progress"' in banner
assert 'startsWith("runtime-")' in banner

print("PASS: supervisor arranca después de Mia y solo repara hijos propios")
print("PASS: crash-loop acotado, cierre coordinado y aviso visible")
