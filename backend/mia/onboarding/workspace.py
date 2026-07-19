"""Mia · onboarding.workspace — andamiaje en disco del espacio de trabajo por despacho
(Fase 1, incremento 1).

SEPARA dos cosas que NO deben mezclarse:
  · El ESTADO DE MIA sobre el caso (lo que Mia sabe, decidió y aprendió) — editable, vive
    en `.mia/` y en `expedientes/<alias>/` (ficha, bitácora, fichas…).
  · El EXPEDIENTE FUENTE (los documentos tal como llegaron) — VERBATIM e INMUTABLE, vive en
    `expedientes/<alias>/fuente/`. Nada de Mia reescribe ahí; es la fuente de verdad citable.

Layout (bajo $MIA_HOME, junto a los `soul_{tenant}.md` — mismo criterio de aislamiento por
`_safe_tenant`, sin tocar el layout plano del SOUL ya instalado):

    $MIA_HOME/despachos/<tenant>/
        .mia/
            despacho.md              perfil operativo del despacho (quién es, cómo trabaja)
            baseline-<fecha>.md      foto inicial del despacho al instalar (una por corrida)
            aprendizajes.md          PINNED — se lee SIEMPRE al retomar (reglas destiladas)
            memoria/
                INDICE.md            índice de la memoria (un hecho = un archivo)
                (un-hecho-por-archivo.md …)
        expedientes/<alias-caso>/
            ficha.md                 ficha viva del caso (estado de Mia)
            HANDOFF.md               traspaso entre turnos/sesiones del caso
            bitacora/                diario de obra del caso (append-only por Mia)
            inbox/                   entrada sin clasificar (lo que llega y aún no se archiva)
            fuente/                  VERBATIM INMUTABLE — documentos del expediente tal cual
            fichas/                  fichas derivadas (resúmenes, líneas de tiempo, extractos)
            _archivo/                lo retirado/superado (no se borra, se archiva)

AGNÓSTICO DE JURISDICCIÓN (regla dura): la estructura anterior es NEUTRA — no asume
Colombia ni ningún país. Las carpetas jurídicas propias de cada despacho (categorías
documentales de su jurisdicción) se inyectan POR DESPACHO vía `extra_carpetas` (que el
onboarding puede derivar del pack de jurisdicción instalado). Por defecto: ninguna.

IDEMPOTENTE y NO DESTRUCTIVO: crear carpetas usa `exist_ok=True`; los archivos semilla se
escriben SOLO si no existen — jamás se pisa contenido que Mia o el abogado ya evolucionaron.
Volver a llamar es seguro (devuelve qué se creó y qué ya estaba).

Puro: solo `config` + stdlib (sin DB, sin LLM), para poder invocarlo desde el onboarding o
desde un test sin arrastrar el pool ni el cliente LLM.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .. import config
from .soul_interview import _safe_tenant

# ── carpetas neutras (agnósticas de jurisdicción) ────────────────────────────
_MATTER_DIRS = ("bitacora", "inbox", "fuente", "fichas", "_archivo")


def _safe_alias(alias: str) -> str:
    """Sanea un alias de caso para usarlo como nombre de carpeta (mismo criterio que
    `_safe_tenant`): solo [A-Za-z0-9_-], el resto a '_'. Nunca vacío ni con separadores
    de ruta — así un alias no puede escapar del árbol del despacho."""
    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(alias or "").strip())
    return s or "caso"


# ── raíces por despacho / por expediente ─────────────────────────────────────
def despacho_workspace_dir(tenant_id: str) -> Path:
    """Raíz del espacio de trabajo del despacho: $MIA_HOME/despachos/<tenant>.

    Lee `config.MIA_HOME` en cada llamada (no se captura al importar) para que los tests
    puedan apuntarlo a un tempdir reasignando `config.MIA_HOME`."""
    return Path(config.MIA_HOME) / "despachos" / _safe_tenant(tenant_id)


def mia_state_dir(tenant_id: str) -> Path:
    """Carpeta `.mia/` (estado de Mia sobre el despacho)."""
    return despacho_workspace_dir(tenant_id) / ".mia"


def expedientes_dir(tenant_id: str) -> Path:
    """Carpeta `expedientes/` del despacho."""
    return despacho_workspace_dir(tenant_id) / "expedientes"


def matter_workspace_dir(tenant_id: str, alias: str) -> Path:
    """Raíz del expediente `<alias-caso>/` dentro del despacho."""
    return expedientes_dir(tenant_id) / _safe_alias(alias)


# ── helpers de escritura no destructiva ──────────────────────────────────────
def _seed_file(path: Path, content: str) -> bool:
    """Escribe `content` SOLO si el archivo no existe. Devuelve True si lo creó."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


# ── andamiaje del despacho (.mia/) ───────────────────────────────────────────
def scaffold_despacho_workspace(
    tenant_id: str,
    *,
    despacho_nombre: str | None = None,
    today: date | None = None,
) -> dict:
    """Crea (idempotente) el árbol `.mia/` del despacho: despacho.md, baseline-<fecha>.md,
    aprendizajes.md (PINNED) y memoria/INDICE.md. No pisa nada existente.

    Devuelve {"root": <str>, "created": [rutas relativas nuevas]}."""
    today = today or date.today()
    root = despacho_workspace_dir(tenant_id)
    mia_dir = mia_state_dir(tenant_id)
    memoria = mia_dir / "memoria"
    memoria.mkdir(parents=True, exist_ok=True)
    expedientes_dir(tenant_id).mkdir(parents=True, exist_ok=True)

    nombre = (despacho_nombre or "").strip()
    titulo = nombre or "este despacho"
    created: list[str] = []

    if _seed_file(mia_dir / "despacho.md",
                  f"# Despacho — {titulo}\n\n"
                  "Perfil operativo del despacho: quién es, cómo trabaja, qué espera de Mia.\n"
                  "Lo mantiene Mia a partir de lo que aprende; el abogado puede corregirlo.\n"):
        created.append(".mia/despacho.md")

    baseline = mia_dir / f"baseline-{today.isoformat()}.md"
    if _seed_file(baseline,
                  f"# Baseline — {today.isoformat()}\n\n"
                  "Foto inicial del despacho al momento de instalar Mia. Punto de comparación\n"
                  "para medir cómo evoluciona el conocimiento y la metodología con el tiempo.\n"):
        created.append(f".mia/{baseline.name}")

    if _seed_file(mia_dir / "aprendizajes.md",
                  "# Aprendizajes (PINNED)\n\n"
                  "Se lee SIEMPRE al retomar. Reglas destiladas del trabajo real del despacho:\n"
                  "lo que funcionó, lo que no, y las decisiones que no se vuelven a discutir.\n"
                  "Un aprendizaje se agrega cuando se prueba en un caso, no antes.\n"):
        created.append(".mia/aprendizajes.md")

    if _seed_file(memoria / "INDICE.md",
                  "# Índice de memoria\n\n"
                  "Memoria del despacho: **un hecho = un archivo** en esta carpeta. Este índice\n"
                  "lista cada hecho con un enlace, para leer solo lo que hace falta.\n\n"
                  "_(aún sin hechos registrados)_\n"):
        created.append(".mia/memoria/INDICE.md")

    return {"root": str(root), "created": created}


# ── andamiaje de un expediente (expedientes/<alias>/) ────────────────────────
def scaffold_matter_workspace(
    tenant_id: str,
    alias: str,
    *,
    titulo: str | None = None,
    extra_carpetas: list[str] | None = None,
) -> dict:
    """Crea (idempotente) el árbol de un expediente: ficha.md, HANDOFF.md y las carpetas
    neutras (bitacora, inbox, fuente [verbatim inmutable], fichas, _archivo). No pisa nada.

    `extra_carpetas` (agnóstico de jurisdicción): carpetas jurídicas propias del despacho
    que el onboarding deriva del pack instalado — se saneen y se crean junto a las neutras.
    Por defecto ninguna: NO se asume ninguna jurisdicción.

    Devuelve {"root": <str>, "alias": <safe>, "created": [rutas relativas nuevas]}."""
    root = matter_workspace_dir(tenant_id, alias)
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    for name in _MATTER_DIRS:
        d = root / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(f"{name}/")

    for raw in (extra_carpetas or []):
        safe = _safe_alias(raw)
        d = root / safe
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(f"{safe}/")

    # La carpeta fuente es la fuente de verdad: se documenta su inmutabilidad.
    if _seed_file(root / "fuente" / "LEEME.md",
                  "# fuente/ — verbatim inmutable\n\n"
                  "Aquí viven los documentos del expediente TAL COMO LLEGARON. Es la fuente de\n"
                  "verdad citable: Mia lee y cita de aquí, pero NUNCA reescribe ni edita estos\n"
                  "archivos. Todo lo derivado (resúmenes, extractos) va en `../fichas/`.\n"):
        created.append("fuente/LEEME.md")

    nombre = (titulo or "").strip() or _safe_alias(alias)
    if _seed_file(root / "ficha.md",
                  f"# Ficha — {nombre}\n\n"
                  "Ficha viva del caso: estado de Mia sobre el expediente (hechos, partes,\n"
                  "pretensiones, estado procesal, próximos pasos). Se actualiza a medida que\n"
                  "Mia ingiere la fuente y trabaja el caso.\n"):
        created.append("ficha.md")

    if _seed_file(root / "HANDOFF.md",
                  f"# HANDOFF — {nombre}\n\n"
                  "Traspaso entre turnos/sesiones de este caso: qué se hizo, qué quedó\n"
                  "pendiente y cómo retomar. Lo actualiza Mia al cerrar cada bloque de trabajo.\n"):
        created.append("HANDOFF.md")

    return {"root": str(root), "alias": _safe_alias(alias), "created": created}
