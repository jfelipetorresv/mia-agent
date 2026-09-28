"""Explicit test environment, never the installed database or the repository .env."""
import os
from pathlib import Path
from dotenv import dotenv_values


def select(environ, read_file=dotenv_values):
    path = environ.get("MIA_TEST_ENV_FILE")
    ci = str(environ.get("CI", "")).lower() == "true" or str(environ.get("GITHUB_ACTIONS", "")).lower() == "true"
    required = ("PG_HOST", "PG_PORT", "PG_DB", "PG_PASSWORD", "PG_APP_PASSWORD")
    if not path and ci and all(environ.get(key) for key in required):
        return {key: value for key, value in environ.items() if key.startswith("PG_")}
    if not path or not Path(path).is_file():
        raise RuntimeError("MIA_TEST_ENV_FILE must point to the isolated test environment")
    values = read_file(path)
    if not ci and str(values.get("PG_PORT")) == "55432":
        raise RuntimeError("Installed database is forbidden for these tests")
    return values


def load() -> None:
    values = select(os.environ)
    for key, value in values.items():
        if value is not None:
            os.environ[key] = value
    os.environ["MIA_ENV"] = "dev"
