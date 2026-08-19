"""
Mia · test_second_brain_ui.py — gate de conectores + UI del second brain.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

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

import init_dreams  # noqa: E402
import init_feedback  # noqa: E402
import init_knowledge_stores  # noqa: E402
import init_playbooks  # noqa: E402
from mia import config  # noqa: E402
from mia.api.routes import ux  # noqa: E402
from mia.memory.wiki_manager import WikiManager  # noqa: E402

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


def make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES('Second Brain UI') RETURNING id").fetchone()[0])


def cleanup(tenant_id: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant_id,))


class FakeObsidianSync:
    async def sync(self, vault_path, tenant_id: str) -> dict:
        return {"indexed": 3, "skipped": 0, "deleted": 0, "errors": 0}


class FakePineconeConnector:
    def __init__(self, api_key: str, index_name: str, namespace_prefix: str) -> None:
        self.api_key = api_key
        self.index_name = index_name
        self.namespace_prefix = namespace_prefix

    async def describe_index(self) -> dict:
        return {"total_vector_count": 42}


async def seed_wiki(tmp: str, tenant_id: str) -> None:
    mgr = WikiManager(home=tmp)
    await mgr.init_wiki(tenant_id)
    await mgr.compile_concept(tenant_id, "Concepto UI", ["Evidencia aprobada"])


def seed_db(tenant_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        pb = c.execute(
            "INSERT INTO playbooks (tenant_id,title,summary,applies_when,content,status) "
            "VALUES (%s::uuid,'Skill UI','summary','applies','content','active') RETURNING id",
            (tenant_id,),
        ).fetchone()[0]
        c.execute(
            "INSERT INTO feedback_proposals (tenant_id,proposal_type,suggested_content,rationale) "
            "VALUES (%s::uuid,'weekly_report','Reporte semanal de prueba','Generado por Dreams')",
            (tenant_id,),
        )
        return str(pb)


def run_frontend_checks() -> None:
    memoria = (ROOT / "frontend" / "app" / "memoria" / "page.tsx").read_text(encoding="utf-8")
    dashboard = (ROOT / "frontend" / "app" / "dashboard" / "page.tsx").read_text(encoding="utf-8")
    onboarding = (ROOT / "frontend" / "app" / "onboarding" / "page.tsx").read_text(encoding="utf-8")
    asunto = (ROOT / "frontend" / "app" / "asuntos" / "[id]" / "page.tsx").read_text(encoding="utf-8")
    # Reestructuración 2026-07-09 (feedback de Pipe: el Panel tenía demasiada
    # información que en realidad es configuración): Conexiones (Obsidian, Pinecone,
    # Motor de IA) y "La salud de Mia" se mudaron del Panel a Configuración —
    # Conexiones vive en el componente compartido ConexionesSection.tsx.
    configurar = (ROOT / "frontend" / "app" / "configurar" / "page.tsx").read_text(encoding="utf-8")
    conexiones_src = configurar + (
        ROOT / "frontend" / "app" / "_components" / "ConexionesSection.tsx"
    ).read_text(encoding="utf-8")
    # Pase wow 2026-07-08: el tab de la wiki se llama "Criterios aprendidos" (§G, sin jerga).
    check("frontend: tab Wiki del despacho", "Criterios aprendidos" in memoria)
    check("frontend: sugerir corrección", "Sugerir corrección" in memoria)
    check("frontend: reporte semanal destacado", "Resumen semanal" in memoria)
    # Pase wow 2026-07-08: "Conectores" → "Conexiones" y "Salud del second brain" →
    # "La salud de Mia" (lenguaje llano §G); Obsidian y Pinecone siguen presentes.
    check("frontend: sección Conectores", "Conexiones" in conexiones_src and "Obsidian" in conexiones_src and "Pinecone" in conexiones_src)
    check("frontend: salud second brain", "La salud de Mia" in configurar)
    # CP7 · el selector de motor consume la política CP2 (sin nombres de modelos, §G)
    check("frontend CP7: selector 'Motor de IA' consume /settings/model-policy (PUT al cambiar)",
          "Motor de IA" in conexiones_src and "/settings/model-policy" in conexiones_src
          and "Modelo preferido" not in conexiones_src)
    # Regresión (hallazgo de Cursor, capa 3): el router de settings se registra SIN
    # prefijo (api/main.py), así que la ruta real es "/settings/model-policy". La
    # bienvenida llamaba "/api/settings/model-policy" → 404 tragado por un catch
    # vacío: el abogado creía haber fijado su motor y Mia seguía con otro.
    activar = (ROOT / "frontend" / "app" / "activar" / "page.tsx").read_text(encoding="utf-8")
    check("frontend: la bienvenida fija el motor con la ruta REAL (sin prefijo /api)",
          "/settings/model-policy" in activar and "/api/settings/model-policy" not in activar)
    # B4: "Guías y documentos" + "Lo que Mia sabe hacer" se fusionaron en un solo
    # subtab ("Guías y habilidades", sentence case como el resto de tabs de esta
    # página: "Mi despacho", "Criterios aprendidos") que muestra la métrica GEPA.
    check("frontend CP7: tab Guías y habilidades consume /api/skills/ranked",
          "Guías y habilidades" in memoria and "/api/skills/ranked" in memoria)
    check("frontend CP7: botón Importar guías → /api/playbooks/import (multipart)",
          "Importar guías" in memoria and "/api/playbooks/import" in memoria)
    check("frontend CP7: la sugerencia muestra el procedimiento que se modificaría (target)",
          "Procedimiento que se modificaría" in memoria and "p.target" in memoria)
    check("frontend CP7: propuestas del Curator con Aprobar/Rechazar",
          "/api/curator/proposals" in memoria and "Orden del conocimiento" in memoria)
    check("frontend CP7: recordatorios en el panel (listar + cancelar, CP-B3)",
          "/api/assistant/reminders" in dashboard and "Recordatorios" in dashboard)
    check("frontend CP7 (Riesgo #27): triad_mode FUERA del onboarding (sin toggle ni "
          "etiqueta; la pregunta p19 queda filtrada)",
          'case "p19"' not in onboarding and "Modo profundo" not in onboarding
          and "HIDDEN_QUESTION_IDS" in onboarding and '"p19"' in onboarding)
    check("frontend CP7: panel Diagnóstico pinta el resumen estructurado si existe",
          "diagnosis_summary" in asunto and "Problema jurídico" in asunto)


def main() -> int:
    print("== Second brain endpoints + UI ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    init_playbooks.apply()
    init_feedback.apply()
    init_dreams.apply()
    init_knowledge_stores.apply()

    from fastapi.testclient import TestClient
    from mia.api.main import app

    original_home = config.MIA_HOME
    original_obsidian = ux.ObsidianSync
    original_pinecone = ux.PineconeConnector
    original_resolve_vault = config.resolve_obsidian_vault

    def _resolve_vault_for_test(vault_path: str) -> Path:
        p = Path(vault_path).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"La ruta del vault no existe o no es un directorio: {p}")
        return p

    tenant = make_tenant()
    seed_db(tenant)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.MIA_HOME = Path(tmp)
            config.resolve_obsidian_vault = _resolve_vault_for_test
            asyncio.run(seed_wiki(tmp, tenant))
            ux.ObsidianSync = FakeObsidianSync
            ux.PineconeConnector = FakePineconeConnector
            token = jwt.encode({"tenant_id": tenant}, config.JWT_SECRET, algorithm=config.JWT_ALG)
            auth = {"Authorization": f"Bearer {token}"}
            with TestClient(app) as client:
                r = client.get("/api/wiki/concepts", headers=auth)
                check("GET /api/wiki/concepts", r.status_code == 200 and r.json()[0]["name"] == "Concepto UI")
                r = client.get("/api/wiki/concepts/Concepto%20UI", headers=auth)
                check("GET /api/wiki/concepts/{concept}", r.status_code == 200 and "markdown" in r.json())
                r = client.post("/api/wiki/concepts/Concepto%20UI/feedback", headers=auth, json={"correction": "Ajustar definición"})
                check("POST wiki feedback", r.status_code == 201 and r.json()["status"] == "pending")
                r = client.get("/api/dreams/report", headers=auth)
                check("GET /api/dreams/report", r.status_code == 200 and r.json()["report"] == "Reporte semanal de prueba")
                r = client.get("/api/skills/ranked", headers=auth)
                check("GET /api/skills/ranked", r.status_code == 200 and isinstance(r.json(), list))
                r = client.post("/api/connectors/obsidian/sync", headers=auth, json={"vault_path": str(Path(tmp))})
                check("POST obsidian sync", r.status_code == 200 and r.json()["chunks_indexed"] == 3)
                r = client.post("/api/connectors/pinecone/configure", headers=auth, json={"api_key": "key", "index_name": "idx"})
                check("POST pinecone configure", r.status_code == 200 and r.json()["vectors_count"] == 42)
                r = client.get("/api/dashboard/stats", headers=auth)
                body = r.json()
                check("dashboard incluye second_brain", r.status_code == 200 and "second_brain" in body)
                check("dashboard incluye modelos dinámicos", bool(body.get("connectors", {}).get("models")))
                # CP7 · contratos que consume la UI nueva
                r = client.get("/api/curator/proposals", headers=auth)
                check("GET /api/curator/proposals (lista para la UI)",
                      r.status_code == 200 and isinstance(r.json(), list))
                r = client.get("/settings/model-policy", headers=auth)
                pol = r.json() if r.status_code == 200 else {}
                # El test fijaba 3 opciones; la sesión 47 sumó OpenRouter como motor
                # propio/respaldo y quedaron 4 (_POLICY_LABELS en routes/settings.py).
                # Se comprueba contra la fuente, no contra un número escrito a mano,
                # para que sumar un motor no vuelva a dar un falso rojo.
                from mia.api.routes.settings import _POLICY_LABELS
                check("GET /settings/model-policy trae política + todas las opciones con nombre",
                      r.status_code == 200 and pol.get("politica")
                      and len(pol.get("opciones", [])) == len(_POLICY_LABELS)
                      and all("nombre" in o for o in pol["opciones"]))
                r = client.put("/settings/model-policy", headers=auth, json={"politica": "soberano"})
                check("PUT /settings/model-policy persiste el cambio (el selector escribe)",
                      r.status_code == 200 and r.json().get("politica") == "soberano")
                r = client.get("/api/proposals", headers=auth)
                check("GET /api/proposals incluye el campo target (CP-C3, lo pinta la UI)",
                      r.status_code == 200
                      and all("target" in p for p in r.json()))
        run_frontend_checks()
    finally:
        ux.ObsidianSync = original_obsidian
        ux.PineconeConnector = original_pinecone
        config.resolve_obsidian_vault = original_resolve_vault
        config.MIA_HOME = original_home
        cleanup(tenant)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Second brain UI OK.")
        return 0
    print("Second brain UI FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
