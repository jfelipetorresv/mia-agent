"""
Mia · test_auth.py — gate de login real multi-tenant (Riesgo #23).

Verifica registro, login, JWT, /api/auth/me, RLS entre tenants y los cambios
mínimos del frontend de sesión.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import bcrypt
import jwt
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

import init_profiles  # noqa: E402
import init_users  # noqa: E402
from mia import config  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def cleanup(emails: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        rows = c.execute("SELECT tenant_id FROM users WHERE email = ANY(%s)", (emails,)).fetchall()
        for (tenant_id,) in rows:
            c.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))


def user_row(email: str):
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT tenant_id, email, password_hash FROM users WHERE email=%s",
            (email,),
        ).fetchone()


def firm_profile_exists(tenant_id: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM firm_profiles WHERE tenant_id=%s::uuid",
            (tenant_id,),
        ).fetchone()[0] == 1


def run_checks(client) -> None:
    stamp = int(time.time() * 1000)
    email_a = f"auth-{stamp}-a@example.com"
    email_b = f"auth-{stamp}-b@example.com"
    bad_email = f"auth-{stamp}-missing@example.com"
    password = "Password-12345"
    cleanup([email_a, email_b])
    try:
        r = client.post("/api/auth/register", json={
            "email": email_a,
            "password": password,
            "firm_name": "Auth Test A",
        })
        data_a = r.json()
        check("register ok -> 201", r.status_code == 201 and "token" in data_a and "tenant_id" in data_a)

        payload_a = jwt.decode(data_a["token"], config.JWT_SECRET, algorithms=[config.JWT_ALG])
        check("JWT payload tiene tenant_id correcto", payload_a.get("tenant_id") == data_a["tenant_id"])
        check("JWT payload tiene email y exp", payload_a.get("email") == email_a and isinstance(payload_a.get("exp"), int))

        row = user_row(email_a)
        check("registro guarda usuario", row is not None and str(row[0]) == data_a["tenant_id"])
        check("bcrypt hash verificable", row is not None and bcrypt.checkpw(password.encode(), row[2].encode()))
        check("password no se guarda en claro", row is not None and row[2] != password)
        check("register crea firm_profile", firm_profile_exists(data_a["tenant_id"]))

        dup = client.post("/api/auth/register", json={
            "email": email_a,
            "password": password,
            "firm_name": "Duplicado",
        })
        check("registro email duplicado -> 409", dup.status_code == 409)

        login = client.post("/api/auth/login", json={"email": email_a, "password": password})
        login_data = login.json()
        check("login ok -> 200", login.status_code == 200 and "token" in login_data)
        check("login email incorrecto -> 401",
              client.post("/api/auth/login", json={"email": bad_email, "password": password}).status_code == 401)
        check("login password incorrecto -> 401",
              client.post("/api/auth/login", json={"email": email_a, "password": "wrong"}).status_code == 401)

        auth_a = {"Authorization": f"Bearer {login_data['token']}"}
        me = client.get("/api/auth/me", headers=auth_a)
        check("/api/auth/me con token válido", me.status_code == 200 and me.json()["email"] == email_a)
        check("/api/auth/me sin token -> 401", client.get("/api/auth/me").status_code == 401)

        expired = jwt.encode(
            {"tenant_id": data_a["tenant_id"], "email": email_a, "exp": int(time.time()) - 10},
            config.JWT_SECRET,
            algorithm=config.JWT_ALG,
        )
        check("token expirado -> 401",
              client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401)

        # Riesgo #72: el tenant_id se usa aguas abajo como nombre de carpeta en disco (SOUL, wiki,
        # trazas). Un JWT bien firmado pero con un tenant_id que NO es UUID canónico se rechaza en
        # el borde, para que el aislamiento no dependa de sanear ese nombre.
        forjado = jwt.encode(
            {"tenant_id": "../otro-despacho", "email": email_a, "exp": int(time.time()) + 3600},
            config.JWT_SECRET, algorithm=config.JWT_ALG)
        check("token con tenant_id no-UUID -> 401 (Riesgo #72)",
              client.get("/api/auth/me", headers={"Authorization": f"Bearer {forjado}"}).status_code == 401)

        rb = client.post("/api/auth/register", json={
            "email": email_b,
            "password": password,
            "firm_name": "Auth Test B",
        })
        data_b = rb.json()
        auth_b = {"Authorization": f"Bearer {data_b['token']}"}
        matter_a = client.post("/api/matters", headers=auth_a, json={"name": "A", "description": ""}).json()
        matters_b = client.get("/api/matters", headers=auth_b).json()
        check("dos tenants distintos -> RLS aislados",
              rb.status_code == 201 and all(m["id"] != matter_a["id"] for m in matters_b))

        login_page = (ROOT / "frontend" / "app" / "login" / "page.tsx").read_text(encoding="utf-8")
        register_page = (ROOT / "frontend" / "app" / "register" / "page.tsx").read_text(encoding="utf-8")
        api_ts = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
        sidebar = (ROOT / "frontend" / "app" / "_components" / "Sidebar.tsx").read_text(encoding="utf-8")
        env_local = (ROOT / "frontend" / ".env.local").read_text(encoding="utf-8")
        check("register inicia el viaje de activación", 'router.replace("/activar")' in register_page)
        check("logout limpia token", "clearToken()" in sidebar and 'router.replace("/login")' in sidebar)
        check("frontend lee token desde localStorage", "localStorage.getItem(\"mia_token\")" in api_ts)
        check("login y register tienen formularios reales",
              'as="form"' in login_page and 'as="form"' in register_page)
        check("NEXT_PUBLIC_DEV_TOKEN eliminado", "NEXT_PUBLIC_DEV_TOKEN" not in env_local)
    finally:
        cleanup([email_a, email_b])


def main() -> int:
    print("== Auth real multi-tenant ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    init_profiles.apply()
    init_users.apply()

    from fastapi.testclient import TestClient
    from mia.api.main import app

    with TestClient(app) as client:
        run_checks(client)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Auth OK — login multi-tenant verificado.")
        return 0
    print("Auth FAIL — no avanzar con la siguiente tarea.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
