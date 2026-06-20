"""Rutas de autenticacion real multi-tenant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from psycopg import errors
from pydantic import BaseModel, Field

from ... import config
from ...db import pool

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    firm_name: str = Field(min_length=1, max_length=200)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _normalize_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value:
        raise HTTPException(status_code=422, detail="Email invalido")
    return value


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(tenant_id: str, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode(
        {"tenant_id": tenant_id, "email": email, "exp": exp},
        config.JWT_SECRET,
        algorithm=config.JWT_ALG,
    )


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    email = _normalize_email(body.email)
    tenant_id = str(uuid4())
    firm_name = body.firm_name.strip()
    password_hash = _hash_password(body.password)

    try:
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO tenants (id, name) VALUES (%s::uuid, %s)",
                (tenant_id, firm_name),
            )
            await conn.execute(
                "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, '{}'::jsonb) "
                "ON CONFLICT (tenant_id) DO NOTHING",
                (tenant_id,),
            )
            await conn.execute(
                "INSERT INTO firm_profiles (tenant_id, name) VALUES (%s::uuid, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()",
                (tenant_id, firm_name),
            )
            await conn.execute(
                "INSERT INTO users (tenant_id, email, password_hash) VALUES (%s::uuid, %s, %s)",
                (tenant_id, email, password_hash),
            )
    except errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Email ya registrado") from exc

    return {"token": create_token(tenant_id, email), "tenant_id": tenant_id}


@router.post("/login")
async def login(body: LoginBody):
    email = _normalize_email(body.email)
    async with pool.get_pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT tenant_id, email, password_hash FROM auth_user_by_email(%s)",
            (email,),
        )).fetchone()
    if not row or not _verify_password(body.password, row[2]):
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    tenant_id = str(row[0])
    saved_email = str(row[1])
    return {"token": create_token(tenant_id, saved_email), "tenant_id": tenant_id}


@router.get("/me")
async def me(request: Request):
    tenant_id = getattr(request.state, "tenant_id", None)
    email = getattr(request.state, "email", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin sesion activa")

    async with pool.tenant_connection(tenant_id) as conn:
        tenant = await (await conn.execute(
            "SELECT name FROM tenants WHERE id = %s::uuid",
            (tenant_id,),
        )).fetchone()
        if not email:
            user = await (await conn.execute(
                "SELECT email FROM users ORDER BY created_at ASC LIMIT 1"
            )).fetchone()
            email = user[0] if user else None

    return {"tenant_id": tenant_id, "email": email, "firm_name": tenant[0] if tenant else None}
