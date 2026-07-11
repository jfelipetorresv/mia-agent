"""Mia · setup.env_writer — actualiza claves puntuales del .env de instalación
sin tocar el resto del archivo (F3, bloque bienvenida/activación).

Lo usa `api/routes/welcome.py` (POST /api/welcome/keys): el abogado activa su
clave de búsqueda documental (Voyage) o de respaldo del motor (Anthropic)
desde la pantalla de bienvenida, y este módulo la escribe en el `.env` de la
instalación PRESERVANDO todo lo demás — JWT_SECRET, PG_*, LITELLM_*, etc.
(secretos generados en el primer arranque, ver `setup/first_run.py:
ensure_seed_env`) NUNCA se tocan ni se regeneran aquí: solo se reescriben las
claves que el llamador pide explícitamente.

Preservación EXACTA de finales de línea (revisión capa 2): el archivo se lee en
BINARIO y se separa SOLO en `\n`/`\r\n` (NO con `str.splitlines()`, que también
parte en fronteras Unicode — `\x0b`, `\x0c`, `\x85`, ` `… — y corromperría
un `.env`). Si el original usa CRLF, se conserva CRLF línea por línea; el BOM
UTF-8, si aparece, se tolera (se decodifica con `utf-8-sig`) sin perder claves.

Escritura atómica con `.tmp` de nombre ÚNICO (`mkstemp`) -> flush + fsync ->
`os.replace`: un corte de energía a mitad de camino deja el archivo intacto
(versión anterior) o completo, nunca a medias, y dos escrituras concurrentes no
colisionan sobre el mismo temporal. Un candado a nivel de módulo serializa el
read-modify-write completo para evitar lost-update entre dos POST simultáneos.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path

# Matchea `KEY=`, `export KEY=` y líneas con indentación/espacios iniciales, para
# hacer update-in-place y NO duplicar la clave. group(1) = prefijo (indent +
# 'export '); group(2) = nombre de la variable. `m.end()` cae justo tras el '='.
_KEY_LINE_RE = re.compile(r"^([ \t]*(?:export[ \t]+)?)([A-Za-z_][A-Za-z0-9_]*)[ \t]*=")

# Serializa el read-modify-write completo. `upsert_env_keys` corre en un
# threadpool (run_in_threadpool), así que el candado natural es un threading.Lock,
# no un asyncio.Lock (que vive en el event loop, no en el hilo trabajador).
_WRITE_LOCK = threading.Lock()


def _split_lines_keep_eol(text: str) -> list[str]:
    """Divide `text` en líneas partiendo SOLO en '\\n' y conservando el fin de
    línea (`\\r\\n` queda íntegro dentro de su línea). NO usa str.splitlines()
    (parte también en fronteras Unicode y perdería el EOL exacto)."""
    lines: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if ch == "\n":
            lines.append(text[start : i + 1])
            start = i + 1
    if start < len(text):
        lines.append(text[start:])
    return lines


def _eol_of(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _atomic_write_env(env_path: Path, text: str) -> None:
    """Escritura atómica con temporal de nombre ÚNICO en el mismo directorio.
    `newline=""` evita que Windows re-traduzca los `\\n`/`\\r\\n` ya presentes en
    `text` (los preservamos byte a byte)."""
    fd, tmp_name = tempfile.mkstemp(dir=str(env_path.parent), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, env_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def upsert_env_keys(env_path: Path, updates: dict[str, str]) -> None:
    """Actualiza SOLO las claves de `updates` dentro de `env_path`.

    - Cualquier otra línea (comentarios, blancos, otras claves) queda igual, en
      el mismo orden y con su mismo final de línea.
    - Si una clave de `updates` ya existe (aun como `export KEY=` o con
      indentación), se reemplaza su valor in-place, sin duplicarla.
    - Si no existe, se agrega al final (con el EOL dominante del archivo).
    - Si `env_path` todavía no existe, se crea con solo esas claves.

    Todo el read-modify-write está serializado por `_WRITE_LOCK` y termina en una
    escritura atómica: nunca hay un estado a medio escribir en disco.
    """
    with _WRITE_LOCK:
        # Lee en binario y decodifica con utf-8-sig: tolera BOM sin perder claves y
        # NO traduce finales de línea (los preservamos exactamente).
        raw = env_path.read_bytes() if env_path.exists() else b""
        original = raw.decode("utf-8-sig", errors="replace")

        pending = dict(updates)
        out_parts: list[str] = []
        for line in _split_lines_keep_eol(original):
            m = _KEY_LINE_RE.match(line)
            key = m.group(2) if m else None
            if key is not None and key in pending:
                prefix = line[: m.end()]  # conserva indent/'export'/espacios y el '='
                out_parts.append(f"{prefix}{pending.pop(key)}{_eol_of(line)}")
            else:
                out_parts.append(line)

        new_text = "".join(out_parts)
        if pending:
            nl = "\r\n" if "\r\n" in original else "\n"
            if new_text and not new_text.endswith(("\n", "\r")):
                new_text += nl
            for key, value in pending.items():  # claves nuevas: al final
                new_text += f"{key}={value}{nl}"

        _atomic_write_env(env_path, new_text)


def read_env_values(env_path: Path) -> dict[str, str]:
    """Lee el `.env` de disco (fuente de verdad tras guardar) y devuelve
    {KEY: valor} de las líneas `KEY=value` (tolera `export `, indentación y BOM).
    Comentarios y líneas en blanco se ignoran. NO expande comillas ni escapes:
    las claves del `.env` de Mia son valores crudos sin comillas."""
    if not env_path.exists():
        return {}
    text = env_path.read_bytes().decode("utf-8-sig", errors="replace")
    values: dict[str, str] = {}
    for line in _split_lines_keep_eol(text):
        m = _KEY_LINE_RE.match(line)
        if not m:
            continue
        values[m.group(2)] = line[m.end():].rstrip("\r\n").strip()
    return values
