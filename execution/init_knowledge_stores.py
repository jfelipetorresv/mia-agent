"""
Mia · init_knowledge_stores.py — migración de los knowledge stores (Módulo 3c · decisión #17).

Aplica backend/mia/db/migrations/004_knowledge_stores.sql como `postgres` (mia_app NO tiene
CREATE) y verifica que las 2 tablas (`knowledge_chunks`, `obsidian_file_hashes`) existan con
RLS habilitado y mia_app con INSERT.

Idempotente: re-ejecutable. `apply()` se puede importar desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_knowledge_stores.py

Paso adicional — scaffold del vault (opcional, --skip-vault para omitir):
    Si OBSIDIAN_VAULT_PATH está en .env y la carpeta no tiene AGENTS.md, crea el scaffold
    completo del vault usando scripts/create_vault_scaffold.py. Idempotente: nunca sobreescribe
    archivos existentes. Si OBSIDIAN_VAULT_NAME / OBSIDIAN_VAULT_MATERIAS están en .env los usa;
    si no, crea el scaffold con valores por defecto que el abogado puede editar después.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "004_knowledge_stores.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_TABLES = ("knowledge_chunks", "obsidian_file_hashes")


def apply() -> None:
    """Aplica 004_knowledge_stores.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def scaffold_vault() -> None:
    """
    Crea el scaffold del vault si OBSIDIAN_VAULT_PATH está configurado y la carpeta
    no tiene AGENTS.md todavía. Idempotente: nunca sobreescribe archivos existentes.
    """
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH", "")
    if not vault_path_str:
        print("[INFO] OBSIDIAN_VAULT_PATH no configurado — scaffold omitido.")
        print("       Configura OBSIDIAN_VAULT_PATH en .env y vuelve a correr para crear el vault.")
        return

    vault_path = Path(vault_path_str)
    agents_file = vault_path / "AGENTS.md"

    if agents_file.exists():
        print(f"[OK] Vault en {vault_path} ya tiene AGENTS.md — scaffold omitido (idempotente).")
        return

    # Importar el creador del scaffold
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    try:
        from create_vault_scaffold import create_vault  # type: ignore
    except ImportError as e:
        print(f"[WARN] No se pudo importar create_vault_scaffold: {e}")
        print("       Crea el vault manualmente con: python scripts/create_vault_scaffold.py --help")
        return

    nombre = os.getenv("OBSIDIAN_VAULT_NAME", vault_path.name)
    materias = os.getenv("OBSIDIAN_VAULT_MATERIAS", "derecho civil,derecho comercial,derecho administrativo")
    organizacion = os.getenv("OBSIDIAN_VAULT_ORGANIZACION", "")
    tipo = os.getenv("OBSIDIAN_VAULT_TIPO", "despacho")  # "despacho" o "abogado"

    print(f"\n[INFO] Creando scaffold del vault '{nombre}' en {vault_path}...")
    try:
        create_vault(
            tipo=tipo,  # type: ignore[arg-type]
            nombre=nombre,
            ruta=vault_path_str,
            materias=materias,
            organizacion=organizacion,
            force=False,  # nunca sobreescribir en onboarding automático
        )
        print("[OK] Scaffold del vault creado correctamente.")
        print(f"     Edita {vault_path / '00-perfil-despacho' / 'identidad.md'} con los datos del despacho.")
    except Exception as e:
        print(f"[WARN] Error al crear scaffold del vault: {e}")
        print("       Puedes crearlo manualmente: python scripts/create_vault_scaffold.py --help")


def main(skip_vault: bool = False) -> None:
    apply()
    print("[OK] 004_knowledge_stores.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        tabs = c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name = ANY(%s) ORDER BY table_name",
            (list(_TABLES),),
        ).fetchall()
        print(f"[INFO] tablas knowledge stores: {', '.join(r[0] for r in tabs)}")
        for t in _TABLES:
            ins = c.execute(
                "SELECT has_table_privilege('mia_app', %s, 'INSERT') AS ok", (f"public.{t}",)
            ).fetchone()[0]
            rls = c.execute(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE relname=%s AND relnamespace='public'::regnamespace", (t,)
            ).fetchone()[0]
            print(f"[INFO] {t}: mia_app INSERT={ins}  RLS={rls}")

    if not skip_vault:
        print("\n--- Scaffold del vault ---")
        scaffold_vault()

    print("\nDONE init_knowledge_stores")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicializa knowledge stores de Mia")
    parser.add_argument(
        "--skip-vault",
        action="store_true",
        help="Omite la creación del scaffold del vault (solo aplica migración SQL)",
    )
    args = parser.parse_args()
    main(skip_vault=args.skip_vault)
