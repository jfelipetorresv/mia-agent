"""Gate F1: conversión transaccional de credenciales legacy a cifrado en reposo."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import psycopg
from dotenv import dotenv_values

from mia.security.at_rest import PREFIX, decrypt_secret
from mia.setup.maintenance import has_unprotected_secrets, protect_existing_secrets

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".env")
settings = {
    "host": str(env.get("PG_HOST") or "127.0.0.1"),
    "port": int(env.get("PG_PORT") or 55432),
    "db": str(env.get("PG_DB") or "mia"),
    "password": str(env.get("PG_PASSWORD") or ""),
}
kw = dict(host=settings["host"], port=settings["port"], dbname=settings["db"],
          user="postgres", password=settings["password"])
tenant = str(uuid.uuid4())

print("\n=== F1 · migración de secretos legacy ===")
try:
    # Gate de primera instalación: aún no existen tablas de Mia.
    empty_db = "mia_empty_gate_" + uuid.uuid4().hex
    admin_kw = dict(
        host=settings["host"], port=settings["port"], dbname="postgres",
        user="postgres", password=settings["password"], autocommit=True,
    )
    with psycopg.connect(**admin_kw) as admin:
        admin.execute(f'CREATE DATABASE "{empty_db}"')
    try:
        assert not has_unprotected_secrets({**settings, "db": empty_db})
    finally:
        with psycopg.connect(**admin_kw) as admin:
            admin.execute(f'DROP DATABASE "{empty_db}" WITH (FORCE)')

    with psycopg.connect(**kw) as conn:
        conn.execute("INSERT INTO tenants(id, name) VALUES(%s::uuid, 'Secret migration gate')", (tenant,))
        conn.execute(
            "INSERT INTO tenant_settings(tenant_id, config) VALUES(%s::uuid, %s::jsonb)",
            (tenant, json.dumps({
                "pinecone": {"api_key": "pine-legacy", "index_name": "idx"},
                "mcp": {"servers": {"dms": {"secrets": {"token": "mcp-legacy"}}}},
            })),
        )
        conn.execute(
            "INSERT INTO tenant_oauth_tokens(tenant_id, provider, access_token, refresh_token) "
            "VALUES(%s::uuid, 'google', 'access-legacy', 'refresh-legacy')", (tenant,)
        )
        conn.commit()

    with tempfile.TemporaryDirectory(prefix="mia-secret-migrate-") as td:
        app_dir = Path(td)
        assert has_unprotected_secrets(settings, tenant)
        changed = protect_existing_secrets(app_dir, settings, tenant)
        assert changed == 4, changed
        assert not has_unprotected_secrets(settings, tenant)
        with psycopg.connect(**kw) as conn:
            access, refresh = conn.execute(
                "SELECT access_token, refresh_token FROM tenant_oauth_tokens "
                "WHERE tenant_id=%s AND provider='google'",
                (tenant,),
            ).fetchone()
            cfg = conn.execute(
                "SELECT config FROM tenant_settings WHERE tenant_id=%s", (tenant,)
            ).fetchone()[0]
        values = [access, refresh, cfg["pinecone"]["api_key"],
                  cfg["mcp"]["servers"]["dms"]["secrets"]["token"]]
        assert all(str(value).startswith(PREFIX) for value in values)
        assert decrypt_secret(access, tenant_id=tenant, purpose="oauth:google:access",
                              app_dir=app_dir) == "access-legacy"
        second = protect_existing_secrets(app_dir, settings, tenant)
        assert second == 0
    print("  [OK] cuatro secretos legacy quedaron cifrados y recuperables")
    print("  [OK] la segunda corrida es idempotente")
    print("  [OK] una instalación vacía no se bloquea antes de crear sus tablas")
finally:
    with psycopg.connect(**kw) as conn:
        conn.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant,))
        conn.commit()

print("\nPASS: migración de secretos legacy segura e idempotente")
