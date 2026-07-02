"""Mia · connectors.vault_writer — espejo de la memoria de Mia en el vault de Obsidian (CP-C2 · decisión #32).

El vault de Obsidian es del DESPACHO. Mia escribe SOLO bajo la subcarpeta `Mia/`
(conceptos del second brain en `Mia/conceptos/`, reportes semanales en `Mia/reportes/`)
y JAMÁS modifica las notas del abogado. La wiki interna (mia-data/wiki) sigue siendo la
fuente de verdad; el vault es el espejo visible que el abogado abre en Obsidian.

Reglas duras (fail-closed):
  - `vault_path` se valida contra OBSIDIAN_VAULT_PATH / OBSIDIAN_VAULT_ALLOWLIST — las
    MISMAS raíces permitidas que el sync de lectura (config.obsidian_vault_allowlist).
  - Cada ruta de escritura se resuelve (Path.resolve) y debe quedar DENTRO de
    `{vault}/Mia/` (is_relative_to); cualquier intento de escape lanza ValueError.
  - `{vault}/Mia` NO puede ser un symlink ni un junction de Windows (reparse point):
    si su ruta real (os.path.realpath) no coincide con la esperada bajo el vault, la
    escritura se RECHAZA con log (revisión CP-C2 — reproducido con `mklink /J`).
  - Los nombres de nota se sanean a slugs ascii; nombres con `..`, separadores de ruta
    o sin caracteres útiles se RECHAZAN (ValueError), no se "arreglan" en silencio.
    Los stems reservados de Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9) se renombran
    con sufijo ("con" → "con-nota").
  - PRIVACIDAD: el frontmatter nunca incluye el tenant ni identificadores internos —
    el vault ya es del despacho; solo lleva title / fecha / fuente: Mia y métricas
    inofensivas (confidence, case_count).

Si el vault todavía no existe, `bootstrap_vault()` crea la estructura mínima
(Mia/conceptos, Mia/reportes y un README en lenguaje llano).
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

from psycopg.types.json import Json

from .. import config
from ..db import pool

logger = logging.getLogger("mia.connectors.vault_writer")

MIA_SUBDIR = "Mia"
CONCEPTS_SUBDIR = "conceptos"
REPORTS_SUBDIR = "reportes"

# claves de metadata que SÍ pueden ir al frontmatter público (nunca el tenant).
_ALLOWED_META_KEYS = ("confidence", "case_count", "last_updated")

_SLUG_STRIP = re.compile(r"[^a-z0-9-]+")

# Stems reservados de Windows (revisión CP-C2): un archivo llamado "con.md" / "aux.md"
# apunta a un DISPOSITIVO en Windows (no a un archivo real). Se renombran con sufijo
# ("con" → "con-nota") en vez de fallar. Comparación en minúsculas (el slug ya lo es).
_WINDOWS_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


class VaultConfigError(ValueError):
    """El vault no tiene configurada su allowlist (OBSIDIAN_VAULT_PATH /
    OBSIDIAN_VAULT_ALLOWLIST). La capa API lo traduce a lenguaje llano para el
    abogado; el detalle técnico va solo al log."""

README_TEXT = (
    "# Carpeta de Mia\n\n"
    "Esta carpeta la mantiene Mia, la asistente del despacho. Aquí guarda, en notas\n"
    "normales de Obsidian, lo que va aprendiendo del trabajo aprobado por ustedes:\n\n"
    "- **conceptos/** — los conceptos y patrones que Mia ha consolidado.\n"
    "- **reportes/** — los resúmenes semanales de actividad y aprendizaje.\n\n"
    "Pueden leer, enlazar y buscar estas notas como cualquier otra del vault.\n"
    "Mia solo escribe dentro de esta carpeta: nunca modifica las demás notas del vault.\n"
    "Si editan una nota de esta carpeta, Mia puede sobreescribirla en la próxima\n"
    "actualización — su copia maestra vive en la memoria interna de Mia.\n"
)


def _slugify(value: str) -> str:
    """Nombre de archivo seguro: minúsculas ascii y guiones. Rechaza (ValueError)
    nombres con `..`, separadores de ruta, ocultos o sin caracteres útiles. Los stems
    reservados de Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9, case-insensitive) se
    renombran con sufijo (revisión CP-C2)."""
    raw = str(value or "").strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw or raw.startswith("."):
        raise ValueError("Ese nombre de nota no está permitido en el vault.")
    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_text.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        raise ValueError("Ese nombre de nota no está permitido en el vault.")
    slug = slug[:80]
    if slug in _WINDOWS_RESERVED_STEMS:
        slug += "-nota"
    return slug


def _yaml_text(value: str) -> str:
    """Valor de una línea, apto para frontmatter (sin saltos ni comillas sin escapar)."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("\\", "\\\\").replace('"', '\\"')


class VaultWriter:
    """Escribe notas de Mia en el vault de Obsidian, SOLO bajo `{vault}/Mia/`."""

    def __init__(self, vault_path: str | Path) -> None:
        self.vault = self._validated_vault(vault_path)

    # ── validación de rutas (allowlist + anti-escape) ────────────────────────
    @staticmethod
    def _validated_vault(vault_path: str | Path) -> Path:
        """El vault debe estar bajo una raíz permitida (mismas reglas que el sync de
        lectura). A diferencia de resolve_obsidian_vault, NO exige que exista aún:
        bootstrap_vault() puede crearlo."""
        vault = Path(vault_path).expanduser().resolve()
        allowlist = config.obsidian_vault_allowlist()
        if not allowlist:
            raise VaultConfigError(
                "OBSIDIAN_VAULT_PATH u OBSIDIAN_VAULT_ALLOWLIST debe estar configurado en .env"
            )
        for root in allowlist:
            if vault.is_relative_to(root):
                return vault
        raise ValueError("La ruta del vault no está dentro de las carpetas permitidas.")

    def _mia_root(self) -> Path:
        """Raíz de escritura `{vault}/Mia` — anti-junction/symlink (revisión CP-C2).

        Si `{vault}/Mia` es un symlink o un junction de Windows (reparse point) que
        apunta fuera del vault, resolverlo haría que TODA escritura escape de la
        allowlist (reproducido con `mklink /J`). Fail-closed: se compara la ruta REAL
        (os.path.realpath, que sí resuelve junctions) contra la esperada bajo el
        vault real; si difieren — o Path.is_symlink() lo delata — se rechaza con log.
        """
        mia = self.vault / MIA_SUBDIR
        expected = Path(os.path.realpath(self.vault)) / MIA_SUBDIR
        real = Path(os.path.realpath(mia))
        if mia.is_symlink() or real != expected:
            logger.warning(
                "Escritura rechazada: %s es un enlace/junction que apunta a %s "
                "(fuera del vault permitido).", mia, real,
            )
            raise ValueError("Mia solo puede escribir dentro de su propia carpeta del vault.")
        return real

    def _target(self, subdir: str, filename: str) -> Path:
        """Ruta destino resuelta. REGLA ANTI-COLISIÓN dura: si al resolver queda fuera
        de `{vault}/Mia/`, se lanza ValueError (nunca se toca una nota del abogado)."""
        mia_root = self._mia_root()
        candidate = (mia_root / subdir / filename).resolve()
        if not candidate.is_relative_to(mia_root):
            raise ValueError("Mia solo puede escribir dentro de su propia carpeta del vault.")
        return candidate

    # ── bootstrap ────────────────────────────────────────────────────────────
    def bootstrap_vault(self) -> list[str]:
        """Crea la estructura mínima (idempotente): Mia/conceptos, Mia/reportes y un
        README en lenguaje llano. Devuelve las rutas relativas creadas en esta pasada."""
        created: list[str] = []
        for sub in (CONCEPTS_SUBDIR, REPORTS_SUBDIR):
            folder = self._mia_root() / sub
            if not folder.is_dir():
                folder.mkdir(parents=True, exist_ok=True)
                created.append(f"{MIA_SUBDIR}/{sub}")
        readme = self._mia_root() / "README.md"
        if not readme.exists():
            readme.write_text(README_TEXT, encoding="utf-8")
            created.append(f"{MIA_SUBDIR}/README.md")
        return created

    # ── frontmatter (sin tenant: el vault es del despacho) ───────────────────
    @staticmethod
    def _frontmatter(title: str, metadata: dict | None = None) -> str:
        lines = [
            "---",
            f'title: "{_yaml_text(title)}"',
            f"fecha: {date.today().isoformat()}",
            "fuente: Mia",
        ]
        for key in _ALLOWED_META_KEYS:                 # whitelist: jamás tenant_id
            value = (metadata or {}).get(key)
            if value is not None and str(value).strip():
                lines.append(f"{key}: {_yaml_text(value)}")
        lines.append("---")
        return "\n".join(lines) + "\n"

    # ── exportadores ─────────────────────────────────────────────────────────
    def export_concept(self, tenant_id: str, name: str, content: str,
                       metadata: dict | None = None) -> Path:
        """Escribe/actualiza `{vault}/Mia/conceptos/{slug}.md` con frontmatter YAML.
        Los backlinks [[...]] que traiga el contenido se conservan tal cual (Obsidian
        los enlaza solo). `tenant_id` es solo para trazabilidad interna: NUNCA se
        escribe en la nota."""
        target = self._target(CONCEPTS_SUBDIR, f"{_slugify(name)}.md")
        self.bootstrap_vault()
        body = (content or "").strip()
        target.write_text(self._frontmatter(name, metadata) + body + "\n", encoding="utf-8")
        return target

    def export_report(self, tenant_id: str, title: str, content: str) -> Path:
        """Escribe `{vault}/Mia/reportes/{fecha}-{slug}.md` (un archivo por día/título)."""
        filename = f"{date.today().isoformat()}-{_slugify(title)}.md"
        target = self._target(REPORTS_SUBDIR, filename)
        self.bootstrap_vault()
        body = (content or "").strip()
        target.write_text(self._frontmatter(title) + body + "\n", encoding="utf-8")
        return target


# ── vault por tenant (mismo mecanismo que el sync de lectura: tenant_settings) ──
async def get_tenant_vault_path(tenant_id: str) -> str | None:
    """Ruta del vault configurada por el tenant (`tenant_settings.config->>
    'obsidian_vault_path'`, el mismo campo que usa el sync de lectura y el scheduler)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config->>'obsidian_vault_path' FROM tenant_settings WHERE tenant_id=%s::uuid",
            (tenant_id,),
        )).fetchone()
    path = row[0] if row else None
    return path or None


async def tenant_vault_writer(tenant_id: str) -> VaultWriter | None:
    """VaultWriter del tenant si tiene vault configurado y permitido; None si no.
    Si la configuración no se puede consultar (p. ej. sin conexión a la base en
    contextos offline/tests), se trata como "sin vault" — silencioso, nivel debug."""
    try:
        path = await get_tenant_vault_path(tenant_id)
    except Exception:  # noqa: BLE001 — sin config legible no hay espejo, no es un error del vault
        logger.debug("No pude consultar el vault configurado del tenant.", exc_info=True)
        return None
    if not path:
        return None
    return VaultWriter(path)


async def register_tenant_vault(tenant_id: str, vault_path: str) -> None:
    """Registra el vault del tenant (mismo upsert que usa el conector de lectura)."""
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(tenant_settings.config, '{obsidian_vault_path}', to_jsonb(%s::text), true), "
            "updated_at = now()",
            (tenant_id, Json({"obsidian_vault_path": vault_path}), vault_path),
        )
