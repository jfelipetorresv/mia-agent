"""
Mia · test_casos_unificados.py — gate del bloque D3: «Casos» (fusión Asuntos+Proyectos).

Qué protege: el abogado ve UN solo concepto («caso») con un control explícito del
comportamiento de Mia (borrador con aprobación vs. respuesta directa). Internamente
sigue siendo matters.kind ('asunto'|'proyecto', migración 028) — este gate comprueba:

  1. PUT /api/matters/{id}/modo — el control del comportamiento:
     · mismo modo -> 200 {changed: false} (idempotente, sin tocar nada)
     · asunto -> proyecto y de vuelta -> 200 {changed: true} y GET lo refleja
     · modo inexistente -> 422 en llano
     · con un borrador esperando revisión (pending_review) -> 409 y el motivo
       DICE que hay un borrador — el bloqueo honesto que pide la decisión D3
     · AISLAMIENTO: el tenant B no puede cambiar el modo de un caso de A (401)
  2. La lista única: GET /api/matters?kind=todos trae ambos modos, y el default
     sin parámetro sigue siendo solo 'asunto' (contrato de compatibilidad intacto).
  3. La capa visible (estático, sin navegador):
     · existen /casos, /casos/[id] y /casos/[id]/revisar en el frontend
     · las rutas viejas /asuntos/... y /proyectos/... son alias que redirigen
       (ningún enlace guardado queda en 404)
     · la navegación tiene UN solo ítem «Casos» (no «Asuntos» ni «Proyectos»)
     · el control ModoDeTrabajo existe y no expone jerga técnica (§G)
  4. §G en las respuestas del API que este bloque toca.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_casos_unificados.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
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

from mia import config                                            # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "kind")


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def set_pending(matter_id: str, value: bool) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE matters SET pending_review=%s WHERE id=%s::uuid",
                  (value, matter_id))


def kind_of(matter_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT kind FROM matters WHERE id=%s::uuid",
                         (matter_id,)).fetchone()[0]


# ── capa visible (estático) ───────────────────────────────────────────────────
def run_frontend_checks() -> None:
    app_dir = ROOT / "frontend" / "app"

    lista = app_dir / "casos" / "page.tsx"
    ficha = app_dir / "casos" / "[id]" / "page.tsx"
    revisar = app_dir / "casos" / "[id]" / "revisar" / "page.tsx"
    modo = app_dir / "casos" / "[id]" / "_components" / "ModoDeTrabajo.tsx"
    check("frontend: existe la lista única /casos", lista.exists())
    check("frontend: existe la ficha única /casos/[id]", ficha.exists())
    check("frontend: existe /casos/[id]/revisar", revisar.exists())
    check("frontend: existe el control ModoDeTrabajo", modo.exists())

    if ficha.exists():
        t = ficha.read_text(encoding="utf-8")
        check("frontend: la ficha despacha por el modo del caso (un solo concepto)",
              "CasoConBorrador" in t and "CasoDirecto" in t)

    # Las URLs viejas no pueden quedar en 404: son alias que redirigen a /casos.
    alias = {
        app_dir / "asuntos" / "page.tsx": '"/casos"',
        app_dir / "asuntos" / "[id]" / "page.tsx": "`/casos/${id}`",
        app_dir / "asuntos" / "[id]" / "revisar" / "page.tsx": "`/casos/${id}/revisar`",
        app_dir / "proyectos" / "page.tsx": '"/casos"',
        app_dir / "proyectos" / "[id]" / "page.tsx": "`/casos/${id}`",
    }
    for path, destino in alias.items():
        rel = path.relative_to(app_dir)
        ok = path.exists()
        if ok:
            t = path.read_text(encoding="utf-8")
            ok = "redirect(" in t and destino in t
        check(f"compat: {rel} redirige a {destino}", ok)

    # La raíz también aterriza en /casos (conservando ?nuevo=1 del buscador).
    raiz = (app_dir / "page.tsx").read_text(encoding="utf-8")
    check("compat: la raíz `/` redirige a /casos conservando ?nuevo=1",
          "redirect(" in raiz and "/casos?nuevo=1" in raiz)

    # Navegación: UN ítem «Casos»; los dos viejos ya no existen como ítems.
    nav = (app_dir / "_components" / "nav.ts").read_text(encoding="utf-8")
    check("nav: existe el ítem único «Casos» hacia /casos",
          'label: "Casos"' in nav and '"/casos"' in nav)
    check("nav: ya no existen los ítems «Asuntos» ni «Proyectos»",
          'label: "Asuntos"' not in nav and 'label: "Proyectos"' not in nav)
    check("nav: las rutas viejas siguen marcando el ítem activo (enlaces guardados)",
          '"/asuntos"' in nav and '"/proyectos"' in nav)

    # §G en el copy del control: lo que el abogado LEE no lleva jerga. Se revisan
    # solo los literales de texto (líneas con comillas), no los identificadores.
    if modo.exists():
        visibles = [ln for ln in modo.read_text(encoding="utf-8").splitlines()
                    if ('"' in ln or "«" in ln) and not ln.strip().startswith(("//", "import", "*"))
                    and "kind" not in ln.split('"')[0]]
        blob = " ".join(ln for ln in visibles
                        if any(c in ln for c in "áéíóú¿«") or "Mia" in ln or "borrador" in ln).lower()
        leaked = [w for w in FORBIDDEN if w != "kind" and w in blob]
        check(f"§G: el copy de ModoDeTrabajo no expone jerga (fugas: {leaked or 'ninguna'})",
              not leaked)


# ── API ───────────────────────────────────────────────────────────────────────
def run_api_checks(client, auth_a, auth_b) -> None:
    visible: list[str] = []

    r = client.post("/api/matters", headers=auth_a, json={"name": "Caso con borrador D3"})
    check("crear caso (modo borrador) -> 201", r.status_code == 201)
    caso_a = r.json()["id"]
    visible.append(r.text)

    r = client.post("/api/matters", headers=auth_a,
                    json={"name": "Caso directo D3", "kind": "proyecto"})
    check("crear caso (respuesta directa) -> 201", r.status_code == 201)
    caso_b = r.json()["id"]
    visible.append(r.text)

    # Lista única y contrato de compatibilidad.
    r = client.get("/api/matters", headers=auth_a, params={"kind": "todos"})
    ids = {it["id"] for it in r.json()}
    check("lista única: ?kind=todos trae ambos modos", caso_a in ids and caso_b in ids)
    r = client.get("/api/matters", headers=auth_a)
    ids = {it["id"] for it in r.json()}
    check("compat: sin parámetro la lista sigue trayendo solo el modo borrador",
          caso_a in ids and caso_b not in ids)

    # 1 · modo inexistente -> 422
    r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_a, json={"kind": "turbo"})
    check("PUT /modo con modo inexistente -> 422", r.status_code == 422)
    visible.append(r.text)

    # 2 · mismo modo -> idempotente
    r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_a, json={"kind": "asunto"})
    check("PUT /modo al MISMO modo -> 200 sin cambio",
          r.status_code == 200 and r.json().get("changed") is False)
    visible.append(r.text)

    # 3 · asunto -> proyecto y de vuelta; GET lo refleja
    r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_a, json={"kind": "proyecto"})
    check("PUT /modo asunto->proyecto -> 200 con cambio",
          r.status_code == 200 and r.json().get("changed") is True)
    visible.append(r.text)
    check("la DB refleja el cambio a respuesta directa", kind_of(caso_a) == "proyecto")
    r = client.get(f"/api/matters/{caso_a}", headers=auth_a)
    check("GET del caso refleja el modo nuevo", r.json().get("kind") == "proyecto")

    r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_a, json={"kind": "asunto"})
    check("PUT /modo proyecto->asunto (de vuelta) -> 200 con cambio",
          r.status_code == 200 and r.json().get("changed") is True)
    check("la DB refleja la vuelta al modo borrador", kind_of(caso_a) == "asunto")
    visible.append(r.text)

    # 4 · con borrador esperando -> 409 con motivo honesto
    set_pending(caso_a, True)
    try:
        r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_a, json={"kind": "proyecto"})
        detalle = (r.json().get("detail") or "") if r.status_code == 409 else ""
        check("PUT /modo con borrador esperando revisión -> 409", r.status_code == 409)
        check("el 409 DICE que hay un borrador (motivo honesto, no genérico)",
              "borrador" in detalle.lower())
        check("el modo NO cambió bajo el bloqueo", kind_of(caso_a) == "asunto")
        visible.append(r.text)
    finally:
        set_pending(caso_a, False)

    # 5 · aislamiento entre despachos
    r = client.put(f"/api/matters/{caso_a}/modo", headers=auth_b, json={"kind": "proyecto"})
    check("AISLAMIENTO: B no puede cambiar el modo de un caso de A -> 401",
          r.status_code == 401)
    check("el modo del caso de A quedó intacto", kind_of(caso_a) == "asunto")

    # 6 · §G — lo visible al abogado sin jerga técnica ('kind' incluido: el nombre
    # interno de la columna jamás debe viajar en un mensaje; sí puede ir como clave
    # JSON del contrato, por eso se revisan solo los textos 'detail'/'message').
    import json as _json
    textos: list[str] = []
    for blob in visible:
        try:
            data = _json.loads(blob)
        except Exception:
            continue
        if isinstance(data, dict):
            for k in ("detail", "message"):
                if isinstance(data.get(k), str):
                    textos.append(data[k])
    joined = " ".join(textos).lower()
    leaked = [w for w in FORBIDDEN if w in joined]
    check(f"§G: los mensajes del API van sin jerga técnica (fugas: {leaked or 'ninguna'})",
          not leaked)


def main() -> int:
    print("== D3 · Casos (fusión Asuntos+Proyectos + control de modo de trabajo) ==")
    run_frontend_checks()

    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A test casos D3")
    tid_b = make_tenant("B test casos D3")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    try:
        with TestClient(app) as client:
            run_api_checks(client, {"Authorization": f"Bearer {tok_a}"},
                           {"Authorization": f"Bearer {tok_b}"})
    finally:
        cleanup([tid_a, tid_b])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("D3 · Casos OK.")
        return 0
    print("D3 · Casos FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
