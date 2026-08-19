# -*- coding: utf-8 -*-
"""Mia · test_citas_quemadas_api.py — la puerta del banco de citas quemadas (#46.2).

Esta es la pieza que convierte el MURO en algo que el abogado usa solo: marcar una cita como
falsa desde la pantalla de revisión. Sin ella el banco solo se llenaba por dentro.

Cubre:
  1. quemar una cita → queda en el banco y Mia deja de emitirla;
  2. quemarla otra vez → no duplica y actualiza el motivo (idempotente), con mensaje distinto;
  3. listar → devuelve las citas del despacho en lenguaje del abogado;
  4. desquemar → la reactiva; desquemar algo que no estaba → 404 en llano;
  5. validación: cita vacía → 400; un párrafo entero → 400 con explicación (si entrara al banco,
     el muro empezaría a retirar texto legítimo por contención);
  6. sin sesión → 401;
  7. RLS: el despacho B no ve ni puede reactivar el banco del despacho A;
  8. §G: ninguna respuesta visible trae jerga técnica.

Requiere DB. Crea dos despachos de prueba y los borra al final.
Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_citas_quemadas_api.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

import init_citas_quemadas               # noqa: E402  (migración 047)
from mia import config                   # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres",
          password=os.getenv("PG_PASSWORD", ""))

# §G: jerga que NUNCA debe llegar a una respuesta visible del abogado.
FORBIDDEN = ("burned", "citation_norm", "tenant", "rls", "normaliz", "upsert", "chunk")

CITA = "Sentencia C-832 de 2002"


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES(%s) RETURNING id",
                             (f"CQ_TEST {label}",)).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def run_checks(client, auth_a, auth_b) -> None:
    visible: list[str] = []

    # ── 1 · quemar ────────────────────────────────────────────────────────────
    r = client.post("/api/citas-quemadas", headers=auth_a,
                    json={"cita": CITA, "motivo": "el pasaje atribuido es fabricado",
                          "pasaje": "Como lo indico la Sentencia C-832 de 2002..."})
    body = r.json() if r.status_code == 200 else {}
    visible.append(str(body))
    check("1 · POST marca la cita como falsa (200)", r.status_code == 200 and body.get("ok"))
    check("1b · el mensaje le dice al abogado qué acaba de pasar, en su idioma",
          "no la volveré a usar" in (body.get("mensaje") or "").lower())
    check("1c · la primera vez NO dice «ya estaba»", body.get("ya_estaba") is False)

    # ── 2 · el MURO ya la retira (la puerta y el muro son la misma cosa) ─────
    from mia.agents import verification as V

    r_list = client.get("/api/citas-quemadas", headers=auth_a)
    lb = r_list.json() if r_list.status_code == 200 else {}
    visible.append(str(lb))
    check("2 · GET devuelve el banco del despacho", r_list.status_code == 200
          and lb.get("total") == 1)
    check("2b · con la cita y su motivo, sin campos internos",
          lb.get("citas") and set(lb["citas"][0]) == {"cita", "motivo"}
          and lb["citas"][0]["cita"] == CITA)
    # El muro, alimentado por lo que devuelve la propia puerta.
    texto, informe = V.annotate_draft(
        f"Segun la {CITA}, procede la excepcion.",
        burned=[{"citation": c["cita"]} for c in lb.get("citas") or []])
    check("2c · con el banco que devuelve la API, el muro retira la cita del borrador",
          "C-832" not in texto and informe.get("quemadas") == 1)

    # ── 3 · idempotencia ─────────────────────────────────────────────────────
    r2 = client.post("/api/citas-quemadas", headers=auth_a,
                     json={"cita": CITA.lower(), "motivo": "segundo motivo, con la fuente"})
    b2 = r2.json() if r2.status_code == 200 else {}
    visible.append(str(b2))
    check("3 · marcarla otra vez no falla y avisa que ya estaba",
          r2.status_code == 200 and b2.get("ya_estaba") is True
          and "ya estaba" in (b2.get("mensaje") or "").lower())
    r_list2 = client.get("/api/citas-quemadas", headers=auth_a)
    check("3b · y no duplica la entrada", (r_list2.json() or {}).get("total") == 1)
    check("3c · el motivo quedó actualizado (la segunda vez se marca con la fuente en la mano)",
          (r_list2.json() or {})["citas"][0]["motivo"] == "segundo motivo, con la fuente")

    # ── 4 · validación ───────────────────────────────────────────────────────
    r_vacia = client.post("/api/citas-quemadas", headers=auth_a, json={"cita": "   "})
    d_vacia = (r_vacia.json() or {}).get("detail", "")
    visible.append(str(d_vacia))
    check("4 · cita vacía → 400 en llano", r_vacia.status_code == 400 and "cita" in d_vacia.lower())

    r_larga = client.post("/api/citas-quemadas", headers=auth_a, json={"cita": "x" * 400})
    d_larga = (r_larga.json() or {}).get("detail", "")
    visible.append(str(d_larga))
    check("4b · un párrafo entero → 400 y le explica qué marcar "
          "(si entrara, el muro retiraría texto legítimo por contención)",
          r_larga.status_code == 400 and "referencia" in d_larga.lower())

    # ── 5 · sin sesión ───────────────────────────────────────────────────────
    r_sin = client.post("/api/citas-quemadas", json={"cita": CITA})
    check("5 · sin sesión → 401", r_sin.status_code == 401)

    # ── 6 · RLS entre despachos ──────────────────────────────────────────────
    r_b = client.get("/api/citas-quemadas", headers=auth_b)
    check("6 · el despacho B NO ve el banco del despacho A",
          r_b.status_code == 200 and (r_b.json() or {}).get("total") == 0)
    r_b_del = client.request("DELETE", "/api/citas-quemadas", headers=auth_b,
                             json={"cita": CITA})
    check("6b · el despacho B NO puede reactivar una cita del despacho A (404)",
          r_b_del.status_code == 404)

    # ── 7 · desquemar ────────────────────────────────────────────────────────
    r_del = client.request("DELETE", "/api/citas-quemadas", headers=auth_a,
                           json={"cita": CITA})
    b_del = r_del.json() if r_del.status_code == 200 else {}
    visible.append(str(b_del))
    check("7 · DELETE reactiva la cita (el muro es reversible por quien lo puso)",
          r_del.status_code == 200 and b_del.get("ok"))
    check("7b · y el banco queda vacío",
          (client.get("/api/citas-quemadas", headers=auth_a).json() or {}).get("total") == 0)
    r_del2 = client.request("DELETE", "/api/citas-quemadas", headers=auth_a,
                            json={"cita": CITA})
    d2 = (r_del2.json() or {}).get("detail", "")
    visible.append(str(d2))
    check("7c · reactivar algo que no estaba marcado → 404 en llano",
          r_del2.status_code == 404 and "no estaba" in d2.lower())

    # ── 8 · §G ───────────────────────────────────────────────────────────────
    todo = " ".join(visible).lower()
    sucias = [w for w in FORBIDDEN if w in todo]
    check(f"8 · §G: ninguna respuesta visible trae jerga técnica (encontradas: {sucias})",
          not sucias)


_TENANT_A = ""


def main() -> int:
    global _TENANT_A
    init_citas_quemadas.apply()   # 047, idempotente
    init_citas_quemadas.apply()

    import jwt
    from fastapi.testclient import TestClient

    from mia.api.main import app

    tid_a = make_tenant("A")
    tid_b = make_tenant("B")
    _TENANT_A = tid_a
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    try:
        with TestClient(app) as client:
            run_checks(client, {"Authorization": f"Bearer {tok_a}"},
                       {"Authorization": f"Bearer {tok_b}"})
    finally:
        cleanup([tid_a, tid_b])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Puerta del banco de citas quemadas OK — el abogado puede marcar una cita falsa "
              "y el muro la retira.")
        return 0
    print("FALLA — la puerta del banco dejó de funcionar o filtró jerga.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
