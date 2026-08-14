"""Contrato de capacidades opcionales del bundle de Mia."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.config import optional_capabilities  # noqa: E402


def main() -> int:
    previous = os.environ.get("MIA_BUNDLE_MANIFEST")
    try:
        with patch("mia.config.importlib.util.find_spec", return_value=object()):
            os.environ.pop("MIA_BUNDLE_MANIFEST", None)
            development = optional_capabilities()
            assert development["ocr"]["available"] is True
            assert development["voice"]["available"] is True

            with tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "components.json"
                manifest.write_text(
                    json.dumps({"capabilities": {"ocr": False, "voice": True}}),
                    encoding="utf-8",
                )
                os.environ["MIA_BUNDLE_MANIFEST"] = str(manifest)
                bundled = optional_capabilities()
                assert bundled["ocr"]["available"] is False
                assert bundled["ocr"]["included"] is False
                assert "PDF con texto" in str(bundled["ocr"]["reason"])
                assert bundled["voice"]["available"] is True

                manifest.write_text("{invalido", encoding="utf-8")
                fail_closed = optional_capabilities()
                assert fail_closed["ocr"]["available"] is False
                assert fail_closed["voice"]["available"] is False
    finally:
        if previous is None:
            os.environ.pop("MIA_BUNDLE_MANIFEST", None)
        else:
            os.environ["MIA_BUNDLE_MANIFEST"] = previous

    print("optional capabilities: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
