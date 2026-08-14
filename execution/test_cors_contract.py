"""Gate estático: CORS debe admitir cada verbo mutador usado por el frontend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    api = (ROOT / "backend/mia/api/main.py").read_text(encoding="utf-8")
    frontend = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend/app").rglob("*.tsx")
    )
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        if f'method: "{method}"' in frontend or f"method: '{method}'" in frontend:
            assert f'"{method}"' in api, f"CORS no permite {method}, aunque el frontend lo usa"
    print("cors contract OK — verbos mutadores del frontend permitidos")


if __name__ == "__main__":
    main()
