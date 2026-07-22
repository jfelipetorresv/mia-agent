"""Rutas de autenticacion real multi-tenant."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from psycopg import errors
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ... import config
from ...db import pool
from ...onboarding.workspace import scaffold_despacho_workspace

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Freno anti fuerza-bruta (auditoría 2026-07) ────────────────────────────────
# Sin esto, /login acepta intentos ilimitados: un atacante puede probar millones de
# contraseñas contra un email conocido. Ventana deslizante EN MEMORIA por proceso
# (suficiente para 1 worker, Modo B; si algún día hubiera un despliegue
# multi-worker, migrar a un contador compartido, p. ej. en Postgres o Redis —
# anotado en la auditoría).
_LOGIN_MAX_FAILURES = 5          # fallos permitidos por (ip, email) …
_LOGIN_WINDOW_SECONDS = 15 * 60  # … dentro de esta ventana → 429
_LOGIN_IP_MAX_FAILURES = 30      # tope agregado: fallos por ip (cualquier email)
_REGISTER_MAX = 10               # registros por ip …
_REGISTER_WINDOW_SECONDS = 3600  # … por hora → 429
_login_failures: dict[tuple[str, str], list[float]] = {}
_login_ip_failures: dict[str, list[float]] = {}
_register_hits: dict[str, list[float]] = {}

# Hash de sacrificio: cuando el email NO existe se verifica bcrypt igual, para que
# el tiempo de respuesta no delate qué correos tienen cuenta (timing attack).
_DUMMY_HASH = bcrypt.hashpw(b"mia-timing-equalizer", bcrypt.gensalt(rounds=12))


def _client_ip(request: Request) -> str:
    # Si algún día hubiera un despliegue detrás de un reverse proxy, esto sería
    # la IP del proxy, no la del cliente: habría que leer X-Forwarded-For DESDE
    # UN PROXY CONFIABLE antes de confiar en ella (anotado en la auditoría como
    # límite conocido).
    return request.client.host if request.client else "unknown"


def _prune(store: dict, key, window: float) -> int:
    """Poda el bucket y ELIMINA la clave si quedó vacío — sin esto, cada email/IP
    sondeado dejaría una entrada viva para siempre (fuga de memoria)."""
    bucket = store.get(key)
    if bucket is None:
        return 0
    now = time.monotonic()
    bucket[:] = [t for t in bucket if now - t < window]
    if not bucket:
        store.pop(key, None)
        return 0
    return len(bucket)


_sweep_countdown = 256


def _maybe_sweep() -> None:
    """Barrido oportunista cada ~256 registros: poda claves vencidas que nunca
    vuelven a consultarse (un atacante con emails aleatorios no toca dos veces
    la misma clave, así que el prune por-clave no basta para acotar memoria)."""
    global _sweep_countdown
    _sweep_countdown -= 1
    if _sweep_countdown > 0:
        return
    _sweep_countdown = 256
    for store, window in (
        (_login_failures, _LOGIN_WINDOW_SECONDS),
        (_login_ip_failures, _LOGIN_WINDOW_SECONDS),
        (_register_hits, _REGISTER_WINDOW_SECONDS),
    ):
        for key in list(store):
            _prune(store, key, window)


def _check_login_throttle(ip: str, email: str) -> None:
    # Tope agregado por IP primero: frena el barrido de emails aleatorios que el
    # límite por (ip, email) no ve, y acota cuánto bcrypt puede provocar una IP.
    if _prune(_login_ip_failures, ip, _LOGIN_WINDOW_SECONDS) >= _LOGIN_IP_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos desde esta conexión. Espera unos minutos e intenta de nuevo.",
        )
    if _prune(_login_failures, (ip, email), _LOGIN_WINDOW_SECONDS) >= _LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.",
        )


def _record_login_failure(ip: str, email: str) -> None:
    # El registro ocurre DESPUÉS del await de DB/bcrypt: una ráfaga concurrente
    # puede colar unos intentos extra antes del primer registro. Límite aceptado
    # (queda acotado por la ventana; anotado en la auditoría).
    now = time.monotonic()
    _login_failures.setdefault((ip, email), []).append(now)
    _login_ip_failures.setdefault(ip, []).append(now)
    _maybe_sweep()


def _clear_login_failures(ip: str, email: str) -> None:
    _login_failures.pop((ip, email), None)


def _check_register_throttle(ip: str) -> None:
    if _prune(_register_hits, ip, _REGISTER_WINDOW_SECONDS) >= _REGISTER_MAX:
        raise HTTPException(
            status_code=429,
            detail="Se crearon demasiadas cuentas desde esta conexión. Intenta más tarde.",
        )
    _register_hits.setdefault(ip, []).append(time.monotonic())
    _maybe_sweep()


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
    exp = datetime.now(timezone.utc) + timedelta(days=config.JWT_TTL_DAYS)
    return jwt.encode(
        {"tenant_id": tenant_id, "email": email, "exp": exp},
        config.JWT_SECRET,
        algorithm=config.JWT_ALG,
    )


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request):
    _check_register_throttle(_client_ip(request))
    email = _normalize_email(body.email)
    tenant_id = str(uuid4())
    firm_name = body.firm_name.strip()
    # bcrypt a threadpool: ver nota en login.
    password_hash = await run_in_threadpool(_hash_password, body.password)

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

    # Fase 1: andamiaje en disco del despacho (.mia/ + expedientes/). Es ACCESORIO — la
    # fuente de verdad es la fila del tenant ya creada; nunca debe tumbar el registro.
    # Idempotente y no destructivo; I/O síncrona → threadpool para no bloquear el event loop.
    try:
        await run_in_threadpool(
            scaffold_despacho_workspace, tenant_id, despacho_nombre=firm_name)
    except Exception:  # noqa: BLE001 — el andamiaje de disco jamás rompe el alta del despacho
        logging.getLogger("mia.onboarding").warning(
            "no se pudo crear el andamiaje del despacho (tenant=%s)", tenant_id, exc_info=True)

    return {"token": create_token(tenant_id, email), "tenant_id": tenant_id}


@router.post("/login")
async def login(body: LoginBody, request: Request):
    email = _normalize_email(body.email)
    ip = _client_ip(request)
    _check_login_throttle(ip, email)
    async with pool.get_pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT tenant_id, email, password_hash FROM auth_user_by_email(%s)",
            (email,),
        )).fetchone()
    # bcrypt (~250 ms con cost 12) va a threadpool: síncrono dentro del handler
    # bloquearía el event loop entero (SSE y todas las peticiones del API).
    if row:
        valid = await run_in_threadpool(_verify_password, body.password, row[2])
    else:
        # Email inexistente: se verifica bcrypt contra un hash de sacrificio para
        # que la respuesta tarde lo mismo que con un email real (anti-enumeración).
        await run_in_threadpool(bcrypt.checkpw, body.password.encode("utf-8"), _DUMMY_HASH)
        valid = False
    if not valid:
        _record_login_failure(ip, email)
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    _clear_login_failures(ip, email)
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
