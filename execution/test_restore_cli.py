from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.setup import backup, maintenance  # noqa: E402


def test_restore_cli_requires_database_bound_confirmation(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "app"; app.mkdir()
    source = tmp_path / "source.mia-backup"; source.write_bytes(b"x")
    calls: list[dict] = []
    monkeypatch.setattr(maintenance, "resolve_pg_bin", lambda value: tmp_path / "pg")
    monkeypatch.setattr(maintenance, "_settings", lambda *_: {"host": "127.0.0.1", "port": 55432, "db": "mia", "password": "SECRET"})
    monkeypatch.setattr(maintenance.backup, "restore_database_backup", lambda **kw: calls.append(kw) or tmp_path / "safety.mia-backup")
    common = ["restore", "--pg-bin", str(tmp_path / "pg"), "--app-dir", str(app), "--source", str(source)]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert maintenance.main(common) == 1
        assert maintenance.main(common + ["--confirm-database", "otra"]) == 1
        assert maintenance.main(common + ["--confirm-database", "mia"]) == 0
    assert len(calls) == 1
    assert calls[0]["confirmed_database"] == calls[0]["db"] == "mia"


def test_restore_orders_verified_safety_backup_before_mutation_and_cleans_temp(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mia-backup"; source.write_bytes(b"encrypted")
    app = tmp_path / "app"; app.mkdir()
    pg_bin = tmp_path / "pg"; pg_bin.mkdir()
    restore_exe = pg_bin / "pg_restore.exe"; restore_exe.write_bytes(b"exe")
    events: list[object] = []
    monkeypatch.setattr(backup, "_validated_pg_dump", lambda _: pg_bin / "pg_dump.exe")
    monkeypatch.setattr(backup, "verify_database_backup", lambda **_: events.append("source-verified") or {"database": "mia"})
    monkeypatch.setattr(backup, "create_verified_database_backup", lambda **_: events.append("safety-verified") or tmp_path / "safety.mia-backup")

    @contextlib.contextmanager
    def decrypted(*_):
        dump = tmp_path / "plain.dump"; dump.write_bytes(b"plain")
        try: yield dump, {"database": "mia"}
        finally: dump.unlink(missing_ok=True); events.append("temp-cleaned")

    monkeypatch.setattr(backup, "decrypted_backup_temp", decrypted)

    def run(command, **kwargs):
        events.append(("mutate", command, kwargs))
        assert events[:2] == ["source-verified", "safety-verified"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup.subprocess, "run", run)
    result = backup.restore_database_backup(
        backup_path=source, pg_bin=pg_bin, app_dir=app,
        host="127.0.0.1", port=55432, db="mia", password="SECRET",
        confirmed_database="mia",
    )
    assert result.name == "safety.mia-backup"
    mutation = next(event for event in events if isinstance(event, tuple) and event[0] == "mutate")
    command, kwargs = mutation[1], mutation[2]
    for flag in ("--clean", "--if-exists", "--single-transaction", "--exit-on-error"):
        assert flag in command
    assert kwargs["shell"] is False and kwargs["env"]["PGPASSWORD"] == "SECRET"
    assert "SECRET" not in command
    assert events[-1] == "temp-cleaned"


def test_restore_failure_is_fail_closed_and_temp_is_removed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mia-backup"; source.write_bytes(b"encrypted")
    app = tmp_path / "app"; app.mkdir(); pg_bin = tmp_path / "pg"; pg_bin.mkdir()
    monkeypatch.setattr(backup, "_validated_pg_dump", lambda _: pg_bin / "pg_dump.exe")
    monkeypatch.setattr(backup, "verify_database_backup", lambda **_: {"database": "mia"})
    monkeypatch.setattr(backup, "create_verified_database_backup", lambda **_: tmp_path / "safety.mia-backup")
    dump = tmp_path / "plain.dump"

    @contextlib.contextmanager
    def decrypted(*_):
        dump.write_bytes(b"plain")
        try: yield dump, {"database": "mia"}
        finally: dump.unlink(missing_ok=True)

    monkeypatch.setattr(backup, "decrypted_backup_temp", decrypted)
    monkeypatch.setattr(backup, "_save_failure_log", lambda *_: None)
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "bad"))
    with pytest.raises(backup.BackupError, match="transacción fue revertida"):
        backup.restore_database_backup(
            backup_path=source, pg_bin=pg_bin, app_dir=app,
            host="127.0.0.1", port=55432, db="mia", password="SECRET",
            confirmed_database="mia",
        )
    assert not dump.exists()


def test_stage_restore_validates_and_startup_applies_or_fails_open(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "app"; app.mkdir()
    bdir = tmp_path / "backups"; bdir.mkdir()
    copia = bdir / "copia.mia-backup"; copia.write_bytes(b"x")
    settings = {"host": "127.0.0.1", "port": 55432, "db": "mia", "password": "S"}
    monkeypatch.setattr(maintenance, "_settings", lambda *_a, **_k: settings)
    monkeypatch.setattr(maintenance.backup, "default_backup_dir", lambda: bdir)
    monkeypatch.setattr(maintenance.backup, "verify_database_backup",
                        lambda **_: {"database": "mia"})

    # confirmación por nombre exacto, fail-closed
    with pytest.raises(RuntimeError):
        maintenance.stage_restore(app, tmp_path, "copia.mia-backup", "otra")
    assert not (app / maintenance.PENDING_RESTORE_NAME).is_file()

    # copia de OTRA base, fail-closed
    monkeypatch.setattr(maintenance.backup, "verify_database_backup",
                        lambda **_: {"database": "ajena"})
    with pytest.raises(RuntimeError):
        maintenance.stage_restore(app, tmp_path, "copia.mia-backup", "mia")

    # camino bueno: marca escrita con la ruta resuelta
    monkeypatch.setattr(maintenance.backup, "verify_database_backup",
                        lambda **_: {"database": "mia"})
    marker = maintenance.stage_restore(app, tmp_path, "copia.mia-backup", "mia")
    assert marker.is_file()

    # startup aplica: restore invocado y marca eliminada
    calls: list[dict] = []
    monkeypatch.setattr(maintenance.backup, "restore_database_backup",
                        lambda **kw: calls.append(kw) or (tmp_path / "safety.mia-backup"))
    assert maintenance._apply_pending_restore(app, tmp_path, settings) == "safety.mia-backup"
    assert len(calls) == 1 and calls[0]["confirmed_database"] == "mia"
    assert not marker.is_file()

    # fallo al aplicar: fail-open del arranque (marca pasa a .failed, no se reintenta)
    marker = maintenance.stage_restore(app, tmp_path, "copia.mia-backup", "mia")

    def _boom(**_kw):
        raise maintenance.backup.BackupError("pg dijo no")
    monkeypatch.setattr(maintenance.backup, "restore_database_backup", _boom)
    assert maintenance._apply_pending_restore(app, tmp_path, settings) is None
    assert not marker.is_file()
    assert (app / (maintenance.PENDING_RESTORE_NAME + ".failed")).is_file()


if __name__ == "__main__":  # verify.ps1 corre las suites como scripts: sin esto, "verde" sin correr nada
    raise SystemExit(pytest.main([__file__, "-q"]))
