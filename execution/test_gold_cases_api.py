"""
Mia · test_gold_cases_api.py — gate de la PANTALLA del Banco de oro (contrato HTTP).

Cubre los dos bloqueos que impedían que la pantalla funcionara de punta a punta:

  (A) CONSENTIMIENTO — `/settings/eval-consent` (el permiso que solo se LEÍA):
      - fail-closed: sin fila en tenant_settings → {"permitido": false}
      - fail-closed: fila con config pero SIN la clave 'eval' → false
      - PUT true → concede; `:draft` deja de dar 403
      - PUT false → revoca; vuelve el 403 (y NO borra los casos ya guardados)
      - el MERGE jsonb no pisa otras claves del config ('model_policy' sobrevive) ni otras
        claves de 'eval'
      - body inválido → 422

  (B) RELECTURA — `GET /api/gold-cases/{id}`:
      - shape completo idéntico al de `:draft`
      - JAMÁS devuelve `anon_map` ni `anon_map_hash`
      - refleja las ediciones del PATCH
      - 400 uuid inválido · 404 inexistente
      - AISLAMIENTO: el despacho B no ve el caso del A (404)

Requiere PostgreSQL encendido (la pantalla es HTTP+DB; sin DB no hay nada que verificar).
Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_gold_cases_api.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import jwt
import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config  # noqa: E402
from mia.security import anonymize  # noqa: E402

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


# ── NER local MOCKEADO: el gate no puede depender de que Ollama esté vivo ─────
_KNOWN = {
    "personas": ["Juan Pérez Gómez"],
    "empresas": ["Constructora Andina S.A.S."],
    "direcciones": ["Calle 100 No. 15-20"],
}


def _fake_ner_llm(messages, *, task=None, model=None, temperature=None, **kw):
    assert model == "mia-local", f"el NER debe correr LOCAL, pidió: {model!r}"
    text = messages[-1]["content"]
    data = {k: [v for v in vs if v in text] for k, vs in _KNOWN.items()}
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(data, ensure_ascii=False)))])


_MESSAGE = (
    "El demandante Juan Pérez Gómez, con C.C. 79.484.321, y Constructora Andina S.A.S. "
    "(NIT 900.123.456-7) presentaron demanda con radicado 11001310300320180012300. "
    "Correo juan.perez@example.com. Notificaciones en la Calle 100 No. 15-20."
)
_DOC = {"filename": "poder.pdf",
        "chunks": ["Poder otorgado el 3 de marzo de 2019. Cédula 52.111.222 en el documento."]}
_ANSWER = ("Con fundamento en el artículo 90 de la Constitución Política y la Ley 1437 de 2011, "
           "operó la caducidad de la acción.")

_SHAPE = {"gold_case_id", "status", "title", "message_anon", "documents_anon",
          "gold_answer_anon", "rubric_propuesta", "spans_pii_restantes", "nota_pii",
          "nota_captura", "aviso"}


def seed_turno_aprobado(tenant_id: str, matter_id: str, *, n_docs: int = 1,
                        chunks_por_doc: int = 1) -> None:
    """Siembra el material que deja un asunto REAL ya resuelto: la traza del turno aprobado
    (pregunta + borrador que el abogado aprobó) + los documentos con sus chunks."""
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO traces(tenant_id, matter_id, input, output, hitl_outcome, trace_ts) "
            "VALUES(%s::uuid, %s, %s, %s, 'approved', now())",
            (tenant_id, str(matter_id), _MESSAGE, _ANSWER))
        for i in range(n_docs):
            doc = c.execute(
                "INSERT INTO documents(tenant_id, matter_id, filename, mime) "
                "VALUES(%s::uuid, %s::uuid, %s, 'application/pdf') RETURNING id",
                (tenant_id, matter_id, f"poder_{i}.pdf")).fetchone()[0]
            for j in range(chunks_por_doc):
                c.execute(
                    "INSERT INTO chunks(tenant_id, document_id, ord, content) "
                    "VALUES(%s::uuid, %s, %s, %s)",
                    (tenant_id, doc, j, _DOC["chunks"][0]))


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def make_matter(tenant_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title) VALUES(%s::uuid, 'Asunto real') RETURNING id",
            (tenant_id,)).fetchone()[0])


def cleanup(*tenant_ids: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in tenant_ids:
            try:
                c.execute("DELETE FROM tenants WHERE id=%s::uuid", (t,))
            except Exception:
                pass


def read_config(tenant_id: str) -> dict:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute("SELECT config FROM tenant_settings WHERE tenant_id=%s::uuid",
                        (tenant_id,)).fetchone()
    return (row[0] if row else None) or {}


def auth_for(tenant_id: str) -> dict:
    token = jwt.encode({"tenant_id": tenant_id}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    try:
        with psycopg.connect(autocommit=True, connect_timeout=3, **PG):
            pass
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] DB no disponible ({type(e).__name__}): este gate es HTTP+DB, no se omite.")
        return 1

    from fastapi.testclient import TestClient
    from mia.api.main import app

    # El :draft anonimiza con el NER local; se mockea el LLM para no depender de Ollama.
    original_anon_text = anonymize.anonymize_text

    def _anon_text_mocked(text, *, session=None, run_ner=True, llm=None):
        return original_anon_text(text, session=session, run_ner=run_ner,
                                  llm=llm or _fake_ner_llm)

    a = make_tenant("GC_API_A")
    b = make_tenant("GC_API_B")
    try:
        anonymize.anonymize_text = _anon_text_mocked
        matter_a = make_matter(a)
        auth_a, auth_b = auth_for(a), auth_for(b)
        with TestClient(app) as client:
            # ── (A) consentimiento ─────────────────────────────────────────────
            print("\n-- (A) consentimiento /settings/eval-consent --")
            r = client.get("/settings/eval-consent", headers=auth_a)
            check("consent: sin fila en tenant_settings → fail-closed (permitido=false)",
                  r.status_code == 200 and r.json() == {"permitido": False})

            # Fila con config PERO sin la clave 'eval' → sigue fail-closed. De paso deja
            # 'model_policy' escrito para probar que el merge no lo pisa.
            r = client.put("/settings/model-policy", headers=auth_a, json={"politica": "soberano"})
            check("consent: (preparación) model-policy escribe 'soberano' en el config",
                  r.status_code == 200 and r.json().get("politica") == "soberano")
            r = client.get("/settings/eval-consent", headers=auth_a)
            check("consent: hay config pero sin clave 'eval' → fail-closed (false)",
                  r.status_code == 200 and r.json() == {"permitido": False})

            # El draft está cerrado: 403 en llano, sin jerga.
            draft_body = {"title": "", "message": _MESSAGE, "documents": [_DOC],
                          "gold_answer": _ANSWER, "diagnosis": ""}
            r = client.post(f"/api/matters/{matter_a}/gold-cases:draft", headers=auth_a,
                            json=draft_body)
            det = (r.json() or {}).get("detail", "")
            check("consent: sin autorización, :draft responde 403", r.status_code == 403)
            # §G: en llano. "Configuración" NO es jerga (es el nombre de la pantalla, y desde
            # esta sesión el 403 ya no miente: ahí hay un interruptor de verdad).
            check("consent: el 403 habla en llano (sin jerga técnica)",
                  isinstance(det, str) and "datos reales" in det and "Configuración" in det
                  and not any(j in det.lower() for j in
                              ("eval", "tenant", "jsonb", "allow_", "config[", "api", "403")))

            # Conceder.
            r = client.put("/settings/eval-consent", headers=auth_a, json={"permitido": True})
            check("consent: PUT {permitido:true} → {'permitido': true}",
                  r.status_code == 200 and r.json() == {"permitido": True})
            r = client.get("/settings/eval-consent", headers=auth_a)
            check("consent: el GET confirma que quedó concedido",
                  r.status_code == 200 and r.json() == {"permitido": True})

            cfg = read_config(a)
            check("merge: 'model_policy' SOBREVIVE al merge de eval (no lo pisa)",
                  cfg.get("model_policy") == "soberano")
            check("merge: la clave queda en config['eval']['allow_eval_real_data'] = true",
                  cfg.get("eval", {}).get("allow_eval_real_data") is True)

            # El merge anidado tampoco pisa OTRAS claves dentro de 'eval'.
            with psycopg.connect(autocommit=True, **PG) as c:
                c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{eval,otra}', "
                          "'\"no me borres\"'::jsonb, true) WHERE tenant_id=%s::uuid", (a,))
            r = client.put("/settings/eval-consent", headers=auth_a, json={"permitido": True})
            cfg = read_config(a)
            check("merge: otra clave DENTRO de 'eval' sobrevive (merge anidado, no reemplazo)",
                  cfg.get("eval", {}).get("otra") == "no me borres"
                  and cfg.get("eval", {}).get("allow_eval_real_data") is True)
            check("merge: 'model_policy' sigue intacto tras el segundo PUT",
                  cfg.get("model_policy") == "soberano")

            r = client.put("/settings/eval-consent", headers=auth_a, json={"permitido": "sí"})
            check("consent: body inválido ('permitido' no booleano) → 422", r.status_code == 422)
            r = client.put("/settings/eval-consent", headers=auth_a, json={})
            check("consent: body sin 'permitido' → 422", r.status_code == 422)

            # ── (B) draft ya autorizado + relectura ────────────────────────────
            print("\n-- (B) :draft autorizado + GET /api/gold-cases/{id} --")
            r = client.post(f"/api/matters/{matter_a}/gold-cases:draft", headers=auth_a,
                            json=draft_body)
            check("draft: con autorización, :draft ya NO da 403 (201/200)", r.status_code == 200)
            drafted = r.json()
            gid = drafted.get("gold_case_id", "")
            check("draft: devuelve el shape completo", set(drafted.keys()) == _SHAPE)
            check("draft: NO filtra el mapa de anonimización",
                  "anon_map" not in drafted and "anon_map_hash" not in drafted)

            r = client.get(f"/api/gold-cases/{gid}", headers=auth_a)
            got = r.json()
            check("get: 200 y shape IDÉNTICO al del draft (un solo tipo para la UI)",
                  r.status_code == 200 and set(got.keys()) == set(drafted.keys()) == _SHAPE)
            check("get: JAMÁS devuelve anon_map ni anon_map_hash",
                  "anon_map" not in got and "anon_map_hash" not in got)
            blob = json.dumps(got, ensure_ascii=False)
            crudos = ["79.484.321", "900.123.456-7", "11001310300320180012300",
                      "juan.perez@example.com", "Juan Pérez Gómez", "Constructora Andina",
                      "Calle 100 No. 15-20", "52.111.222"]
            check("get: ningún dato crudo del asunto real aparece en la respuesta",
                  not any(c in blob for c in crudos))
            check("get: el texto anonimizado coincide con el del draft",
                  got["message_anon"] == drafted["message_anon"]
                  and got["gold_answer_anon"] == drafted["gold_answer_anon"]
                  and got["documents_anon"] == drafted["documents_anon"])
            check("get: nota_pii y aviso son los mismos del draft (mismos helpers)",
                  got["nota_pii"] == drafted["nota_pii"] and got["aviso"] == drafted["aviso"])
            check("get: spans_pii_restantes recomputados igual que en el draft",
                  got["spans_pii_restantes"] == drafted["spans_pii_restantes"])
            check("get: rúbrica con las dos listas",
                  set(got["rubric_propuesta"].keys()) == {"citas_clave", "conclusiones_clave"})
            check("get: status='draft' y título presente",
                  got["status"] == "draft" and isinstance(got["title"], str))

            # Refleja las ediciones del PATCH (no es una foto vieja).
            r = client.patch(f"/api/gold-cases/{gid}", headers=auth_a,
                             json={"gold_answer": "Operó la caducidad según la Ley 1437 de 2011."})
            check("patch: edición aceptada", r.status_code == 200)
            r = client.get(f"/api/gold-cases/{gid}", headers=auth_a)
            check("get: refleja la edición del PATCH",
                  r.status_code == 200
                  and r.json()["gold_answer_anon"] == "Operó la caducidad según la Ley 1437 de 2011.")

            # Errores en llano.
            r = client.get("/api/gold-cases/no-es-uuid", headers=auth_a)
            check("get: uuid inválido → 400", r.status_code == 400)
            r = client.get("/api/gold-cases/00000000-0000-0000-0000-000000000000", headers=auth_a)
            check("get: id inexistente → 404 'No se encontró ese caso de oro.'",
                  r.status_code == 404 and r.json()["detail"] == "No se encontró ese caso de oro.")

            # ── (E) CAPTURA SERVER-SIDE: basta el matter_id ────────────────────
            print("\n-- (E) captura server-side (el navegador nunca ve el texto crudo) --")
            m_srv = make_matter(a)
            r = client.post(f"/api/matters/{m_srv}/gold-cases:draft", headers=auth_a, json={})
            check("captura: asunto SIN turno aprobado → 409 en llano, no un caso vacío",
                  r.status_code == 409 and "aprobado" in r.json()["detail"]
                  and "trace" not in r.json()["detail"].lower())

            seed_turno_aprobado(a, m_srv, n_docs=2, chunks_por_doc=1)
            # Sin body en absoluto: el cliente solo aporta el matter_id.
            r = client.post(f"/api/matters/{m_srv}/gold-cases:draft", headers=auth_a)
            check("captura: SIN body (solo el matter_id) → 200", r.status_code == 200)
            srv = r.json()
            check("captura: shape completo", set(srv.keys()) == _SHAPE)
            check("captura: NO filtra el mapa de anonimización",
                  "anon_map" not in srv and "anon_map_hash" not in srv)
            sblob = json.dumps(srv, ensure_ascii=False)
            check("captura: ningún dato crudo del expediente sale al cliente",
                  not any(c in sblob for c in crudos))
            check("captura: la pregunta salió de la traza del turno aprobado (anonimizada)",
                  "[[PERSONA_1]]" in srv["message_anon"] and "[[CEDULA_1]]" in srv["message_anon"])
            check("captura: el borrador aprobado salió de la traza (gold_answer no vacío)",
                  "Ley 1437 de 2011" in srv["gold_answer_anon"])
            check("captura: los 2 documentos del asunto entraron con sus chunks",
                  len(srv["documents_anon"]) == 2
                  and all(d["chunks"] for d in srv["documents_anon"])
                  and {d["filename"] for d in srv["documents_anon"]} == {"poder_0.pdf", "poder_1.pdf"})
            check("captura: propone citas clave desde el borrador aprobado",
                  any("1437" in c for c in srv["rubric_propuesta"]["citas_clave"]))
            check("captura: sin diagnóstico durable, NO inventa conclusiones (lista vacía)",
                  srv["rubric_propuesta"]["conclusiones_clave"] == [])
            check("captura: asunto pequeño → nota_captura vacía (no se recortó nada)",
                  srv["nota_captura"] == "")

            # Recorte EXPLÍCITO en un asunto grande (nunca silencioso).
            m_big = make_matter(a)
            seed_turno_aprobado(a, m_big, n_docs=25, chunks_por_doc=1)
            r = client.post(f"/api/matters/{m_big}/gold-cases:draft", headers=auth_a, json={})
            big = r.json()
            check("captura: asunto grande → se acota a MAX_CAPTURE_DOCS documentos",
                  r.status_code == 200 and len(big["documents_anon"]) == 20)
            check("captura: el recorte se DICE en llano y con números (no es silencioso)",
                  "25 documentos" in big["nota_captura"] and "20" in big["nota_captura"])

            # RLS de la captura: traces.matter_id es TEXT sin FK — una traza de B con el
            # matter_id de A no debe contaminar la captura de A (la barrera es RLS por tenant).
            with psycopg.connect(autocommit=True, **PG) as c:
                c.execute(
                    "INSERT INTO traces(tenant_id, matter_id, input, output, hitl_outcome, "
                    "trace_ts) VALUES(%s::uuid, %s, %s, %s, 'approved', now() + interval '1 day')",
                    (b, str(m_srv), "PREGUNTA SECRETA DEL DESPACHO B", "BORRADOR SECRETO DE B"))
            m_srv2 = make_matter(a)
            seed_turno_aprobado(a, m_srv2)
            r = client.post(f"/api/matters/{m_srv}/gold-cases:draft", headers=auth_a, json={})
            leak = json.dumps(r.json(), ensure_ascii=False)
            check("rls: la traza de B (mismo matter_id, más reciente) NO contamina la captura de A",
                  r.status_code == 200 and "SECRETA" not in leak and "SECRETO" not in leak)
            # Y el revés: B no puede capturar desde un asunto de A.
            r = client.post(f"/api/matters/{m_srv}/gold-cases:draft", headers=auth_b, json={})
            check("rls: B no puede capturar desde el asunto de A (401)", r.status_code == 401)

            # El consentimiento sigue mandando sobre la captura server-side.
            client.put("/settings/eval-consent", headers=auth_a, json={"permitido": False})
            r = client.post(f"/api/matters/{m_srv2}/gold-cases:draft", headers=auth_a, json={})
            check("captura: sin consentimiento, la captura server-side también da 403",
                  r.status_code == 403)
            client.put("/settings/eval-consent", headers=auth_a, json={"permitido": True})

            # ── AISLAMIENTO entre despachos ────────────────────────────────────
            print("\n-- (C) aislamiento entre despachos (RLS por HTTP) --")
            r = client.get(f"/api/gold-cases/{gid}", headers=auth_b)
            check("rls: el despacho B NO puede leer el caso del A (404)", r.status_code == 404)
            r = client.get("/api/gold-cases", headers=auth_b)
            check("rls: el banco de B está vacío (no ve el caso de A)",
                  r.status_code == 200 and r.json()["total"] == 0)
            r = client.patch(f"/api/gold-cases/{gid}", headers=auth_b, json={"title": "robado"})
            check("rls: B no puede editar el caso de A (404)", r.status_code == 404)
            r = client.delete(f"/api/gold-cases/{gid}", headers=auth_b)
            check("rls: B no puede borrar el caso de A (404)", r.status_code == 404)
            r = client.get("/settings/eval-consent", headers=auth_b)
            check("rls: el consentimiento de A no se filtra a B (B sigue en false)",
                  r.status_code == 200 and r.json() == {"permitido": False})

            # ── REVOCAR ────────────────────────────────────────────────────────
            print("\n-- (D) revocar el consentimiento --")
            antes = client.get("/api/gold-cases", headers=auth_a).json()["total"]
            r = client.put("/settings/eval-consent", headers=auth_a, json={"permitido": False})
            check("revocar: PUT {permitido:false} → {'permitido': false}",
                  r.status_code == 200 and r.json() == {"permitido": False})
            r = client.get("/settings/eval-consent", headers=auth_a)
            check("revocar: el GET confirma la revocación",
                  r.status_code == 200 and r.json() == {"permitido": False})
            r = client.post(f"/api/matters/{matter_a}/gold-cases:draft", headers=auth_a,
                            json=draft_body)
            check("revocar: vuelve el 403 al intentar capturar otro asunto real",
                  r.status_code == 403)
            r = client.get("/api/gold-cases", headers=auth_a)
            check("revocar: NO borra los casos ya guardados (siguen en el banco, son anónimos)",
                  r.status_code == 200 and antes >= 1 and r.json()["total"] == antes)
            r = client.get(f"/api/gold-cases/{gid}", headers=auth_a)
            check("revocar: el caso ya guardado se sigue pudiendo releer (texto anonimizado)",
                  r.status_code == 200 and r.json()["gold_case_id"] == gid)
            cfg = read_config(a)
            check("revocar: 'model_policy' sobrevive también a la revocación",
                  cfg.get("model_policy") == "soberano"
                  and cfg.get("eval", {}).get("allow_eval_real_data") is False)
    finally:
        anonymize.anonymize_text = original_anon_text
        cleanup(a, b)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total}")
    if passed == total:
        print("Pantalla del Banco de oro OK — consentimiento escribible + relectura verificados.")
        return 0
    print("Pantalla del Banco de oro FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
