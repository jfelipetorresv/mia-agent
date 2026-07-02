"""
Mia · test_playbook_import.py — gate de CP4 (import de playbooks · Riesgo #20).

Verifica contra la DB real que POST /api/playbooks/import siembra las guías de trabajo
del despacho a partir de archivos .md/.txt/.docx:

  a. Un .md con 3 encabezados de nivel 1 → 3 playbooks del tenant correcto.
  b. La línea "Cuándo:" al inicio del cuerpo → applies_when (y no queda en content).
  c. Archivo sin encabezados '#' → UN playbook con el nombre del archivo como título.
  d. Duplicado por título → se reporta como omitido SIN romper el resto del batch
     (y el contenido ya guardado no se pisa).
  e. protected=true en el import → la columna `protected` queda persistida (H.6:
     el Curator/GEPA no lo podrían podar).
  f. Aislamiento: el tenant B no ve los playbooks importados por A (patrón test_rls).
  g. Archivo de tipo no soportado (.exe) → error claro en la respuesta y NADA persistido.
  §G. Las respuestas visibles no exponen jerga técnica.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_playbook_import.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_playbooks                                   # noqa: E402  (migración 005)
import init_playbooks_protected                         # noqa: E402  (migración 014)
from mia import config, embeddings                      # noqa: E402
from mia.agent import llm                               # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.1] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="CONTENIDO_MOCK"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "tool_call", "embedding")


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id",
            (f"PBIMPORT_TEST {label}",)).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'PBIMPORT_TEST%'")


def db_one(sql: str, params: tuple):
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(sql, params).fetchone()


MD_3_GUIAS = (
    "# Caducidad en reparación directa\n"
    "Cuándo: el daño es imputable al Estado y se discute la oportunidad\n"
    "Paso 1: computar el término de dos años desde el hecho dañoso.\n"
    "Paso 2: verificar suspensiones por conciliación prejudicial.\n"
    "\n"
    "# Objeción a la cuantía\n"
    "Exigir el soporte probatorio de cada pretensión económica.\n"
    "\n"
    "# Contestación de demanda ejecutiva\n"
    "Aplica: títulos valores con firma cuestionada\n"
    "Verificar los requisitos formales del título ejecutivo.\n"
)

TXT_SIN_ENCABEZADOS = (
    "Guía plana sin encabezados de nivel uno.\n"
    "Siempre revisar los poderes y anexos antes de radicar.\n"
)

MD_CON_DUPLICADO = (
    "# Objeción a la cuantía\n"
    "Versión nueva que NO debe pisar la guía ya guardada.\n"
    "\n"
    "# Guía nueva del batch\n"
    "Cuando: se necesite comprobar que el batch sigue tras un duplicado\n"
    "Contenido de la guía nueva.\n"
)

MD_SEMILLA = (
    "# Guía semilla core\n"
    "Cuándo: siempre, es la metodología base del despacho\n"
    "Cuerpo de la guía semilla, protegido frente al mantenimiento automático.\n"
)


def run_checks(client, auth_a, auth_b, tid_a, tid_b) -> None:
    visible_payloads: list[str] = []

    # === a · .md con 3 encabezados → 3 playbooks del tenant correcto ===
    r = client.post("/api/playbooks/import", headers=auth_a,
                    files=[("files", ("guias.md", MD_3_GUIAS.encode("utf-8"), "text/markdown"))])
    j = r.json()
    visible_payloads.append(r.text)
    check("a1 · POST /api/playbooks/import (.md) -> 200", r.status_code == 200)
    check("a2 · 3 encabezados -> 3 importados, sin omitidos ni errores",
          len(j.get("importados", [])) == 3 and j.get("omitidos") == [] and j.get("errores") == [])
    cnt = db_one("SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid", (tid_a,))[0]
    check("a3 · 3 playbooks persistidos bajo el tenant A", cnt == 3)

    # === b · applies_when extraído de la línea 'Cuándo:' ===
    row = db_one("SELECT applies_when, content FROM playbooks "
                 "WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "Caducidad en reparación directa"))
    check("b1 · applies_when viene de la línea 'Cuándo:'",
          row is not None and row[0] == "el daño es imputable al Estado y se discute la oportunidad")
    check("b2 · la línea 'Cuándo:' no queda dentro del content",
          row is not None and "Cuándo:" not in row[1] and "computar el término" in row[1])
    # sin marcador → applies_when derivado del título y TODO el cuerpo es content
    row = db_one("SELECT applies_when, content FROM playbooks "
                 "WHERE tenant_id=%s::uuid AND title=%s", (tid_a, "Objeción a la cuantía"))
    check("b3 · sin marcador: applies_when se deriva del título",
          row is not None and "Objeción a la cuantía" in row[0]
          and "soporte probatorio" in row[1])
    # marcador alterno 'Aplica:'
    row = db_one("SELECT applies_when FROM playbooks WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "Contestación de demanda ejecutiva"))
    check("b4 · el marcador 'Aplica:' también extrae applies_when",
          row is not None and row[0] == "títulos valores con firma cuestionada")

    # === c · archivo sin encabezados → 1 playbook con el nombre del archivo ===
    r = client.post("/api/playbooks/import", headers=auth_a,
                    files=[("files", ("protocolo-poderes.txt",
                                      TXT_SIN_ENCABEZADOS.encode("utf-8"), "text/plain"))])
    j = r.json()
    visible_payloads.append(r.text)
    check("c1 · .txt sin encabezados -> 1 importado con el nombre del archivo",
          r.status_code == 200 and j.get("importados") == ["protocolo-poderes"])
    row = db_one("SELECT content FROM playbooks WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "protocolo-poderes"))
    check("c2 · todo el texto del archivo quedó como content",
          row is not None and "revisar los poderes" in row[0])

    # === d · duplicado por título → omitido, sin romper el resto del batch ===
    r = client.post("/api/playbooks/import", headers=auth_a,
                    files=[("files", ("mas-guias.md", MD_CON_DUPLICADO.encode("utf-8"),
                                      "text/markdown"))])
    j = r.json()
    visible_payloads.append(r.text)
    check("d1 · el duplicado se reporta como omitido",
          r.status_code == 200 and j.get("omitidos") == ["Objeción a la cuantía"])
    check("d2 · el resto del batch se importa igual",
          j.get("importados") == ["Guía nueva del batch"] and j.get("errores") == [])
    row = db_one("SELECT content FROM playbooks WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "Objeción a la cuantía"))
    check("d3 · el contenido ya guardado NO se pisó por el duplicado",
          row is not None and "soporte probatorio" in row[0] and "NO debe pisar" not in row[0])

    # === e · protected=true → flag persistido (inmune al Curator/GEPA por H.6) ===
    r = client.post("/api/playbooks/import?protected=true", headers=auth_a,
                    files=[("files", ("semilla.md", MD_SEMILLA.encode("utf-8"), "text/markdown"))])
    visible_payloads.append(r.text)
    check("e1 · import con protected=true -> 200 e importado",
          r.status_code == 200 and r.json().get("importados") == ["Guía semilla core"])
    row = db_one("SELECT protected FROM playbooks WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "Guía semilla core"))
    check("e2 · la columna 'protected' quedó persistida en TRUE (H.6: el Curator no la poda)",
          row is not None and row[0] is True)
    # control: un import normal queda protected=FALSE
    row = db_one("SELECT protected FROM playbooks WHERE tenant_id=%s::uuid AND title=%s",
                 (tid_a, "Caducidad en reparación directa"))
    check("e3 · un import sin el parámetro queda protected=FALSE (control)",
          row is not None and row[0] is False)

    # === f · aislamiento A↔B (patrón test_rls) ===
    r = client.get("/api/playbooks", headers=auth_b)
    titles_b = {p["title"] for p in r.json()}
    check("f1 · el tenant B NO ve los playbooks importados por A",
          r.status_code == 200 and not titles_b & {
              "Caducidad en reparación directa", "Objeción a la cuantía",
              "Contestación de demanda ejecutiva", "protocolo-poderes", "Guía semilla core"})
    # B puede importar un título que A ya usa (la dedup es POR tenant)
    r = client.post("/api/playbooks/import", headers=auth_b,
                    files=[("files", ("guias-b.md",
                                      "# Objeción a la cuantía\nMetodología propia del despacho B.\n"
                                      .encode("utf-8"), "text/markdown"))])
    check("f2 · B importa un título que A ya tiene (la dedup es por despacho)",
          r.status_code == 200 and r.json().get("importados") == ["Objeción a la cuantía"])
    cnt_b = db_one("SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid", (tid_b,))[0]
    check("f3 · B tiene exactamente 1 playbook propio", cnt_b == 1)

    # === g · tipo no soportado (.exe) → error claro y NADA persistido ===
    before = db_one("SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid", (tid_a,))[0]
    r = client.post("/api/playbooks/import", headers=auth_a,
                    files=[("files", ("programa.exe", b"MZ\x90\x00binario",
                                      "application/octet-stream"))])
    j = r.json()
    visible_payloads.append(r.text)
    check("g1 · .exe -> nada importado y un error claro en la respuesta",
          r.status_code == 200 and j.get("importados") == [] and len(j.get("errores", [])) == 1
          and "no soportado" in j["errores"][0])
    after = db_one("SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid", (tid_a,))[0]
    check("g2 · nada quedó persistido tras el archivo rechazado", after == before)

    # === §G · sin jerga técnica en lo que ve el abogado ===
    blob = " ".join(visible_payloads).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G · respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== CP4 · import de playbooks (POST /api/playbooks/import · Riesgo #20) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_playbooks.apply()
    init_playbooks_protected.apply()

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    drop_test_tenants()
    tid_a, tid_b = make_tenant("a"), make_tenant("b")
    auth_a = {"Authorization": "Bearer " + jwt.encode(
        {"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)}
    auth_b = {"Authorization": "Bearer " + jwt.encode(
        {"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)}
    try:
        with TestClient(app) as client:
            run_checks(client, auth_a, auth_b, tid_a, tid_b)
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("playbook import OK — CP4 verificado (seeding de guías por import, Riesgo #20).")
        return 0
    print("playbook import FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
