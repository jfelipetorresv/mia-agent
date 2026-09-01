"""
Mia · test_setup_wizard.py — gate de CP-C4 (asistente de configuración guiado, Pilar C).

Verifica con DB REAL y detectores SIMULADOS (sin red, sin winget, sin instalar nada):

  (s) GET /api/setup/status — estructura completa (7 pasos con id/titulo/estado/
      detalle/accion), detección simulada de cada componente (Obsidian, vault,
      carpetas, guías, motor, Telegram) cambia el estado, textos sin jerga (§G),
      y es SOLO LECTURA: consultar el estado no escribe nada en la DB.
  (k) skip/unskip — cada paso es opcional y RETOMABLE; el estado persiste en
      tenant_settings.config['setup'] y sobrevive entre consultas; paso
      inexistente → 404; RLS: lo omitido por un despacho no afecta a otro.
  (a) El asistente (CP-B1) guía por chat: "ayúdame a conectar mi Google Drive"
      → el modelo ve el bloque de estado real; el mensaje persistido va limpio.
  (f) Frontend: página /configurar consume /api/setup/status con skip/retomar
      y guía de Telegram; el Sidebar tiene el enlace.

Limpia sus datos al final. HALT si falla (CLAUDE.md §G). Exit 0 = PASS · 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_setup_wizard.py
"""
from __future__ import annotations

import asyncio
import os
import shutil as _shutil_std
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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

import init_assistant  # noqa: E402
import init_local_folders  # noqa: E402
import init_playbooks  # noqa: E402
import init_profiles  # noqa: E402
import init_users  # noqa: E402
from mia import config  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.api.routes import setup as setup_mod  # noqa: E402
from mia.assistant.core import SETUP_BLOCK_HEADER  # noqa: E402
from mia.channels import notify  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []

# La UI jamás muestra jerga (§G) — ninguna de estas PALABRAS puede aparecer en los
# textos (por palabra completa: "cli" no debe marcar "cliente" — revisor CP-C4).
import re as _re  # noqa: E402

_FORBIDDEN_RE = _re.compile(
    r"\b(tenant|cli|api|endpoint|backend|jsonb|winget|rls)\b", _re.IGNORECASE)


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def sb() -> psycopg.Connection:
    return psycopg.connect(autocommit=True, **PG)


def cleanup(tenant_ids: list[str]) -> None:
    if not tenant_ids:
        return
    with sb() as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s::uuid[])", (tenant_ids,))


def ok_response(text: str):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class FakeCompletions:
    def __init__(self) -> None:
        self.script: dict[str, list[str]] = {}
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def create(self, **kwargs):
        model = kwargs["model"]
        with self._lock:
            self.calls.append({"model": model, "messages": kwargs["messages"]})
            outcomes = self.script.get(model)
            if not outcomes:
                raise AssertionError(f"llamada no guionada al alias {model}")
            text = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        return ok_response(text)

    def last_for(self, model: str) -> dict | None:
        for call in reversed(self.calls):
            if call["model"] == model:
                return call
        return None


class Detectors:
    """Simula cada componente del equipo (el gate NO toca winget ni el disco)."""

    def __init__(self) -> None:
        self.which: dict[str, str | None] = {"claude": None, "ollama": None}
        self.telegram = False
        self.voz = False  # CP-Z1b: el gate NO depende de los pesos de la máquina
        self.detected_clouds: list[dict] = []
        # Obsidian reincorporado (2026-07-18): se simula igual que los demás —
        # nunca winget ni disco real en el gate. Se mockea is_installed_fast
        # (la que de verdad consume /status desde el fix MN3), no is_installed.
        self.obsidian_installed = False
        self.vault_path: str | None = None
        self._saved: dict[str, object] = {}

    async def _fake_vault_path(self, _tid: str) -> str | None:
        return self.vault_path

    def install(self) -> None:
        self._saved = {
            "which": setup_mod.shutil.which,
            "telegram_configured": notify.telegram_configured,
            "detect_cloud_folders": setup_mod.detect_cloud_folders,
            "get_engine": setup_mod.speech_engine.get_engine,
            "is_installed_fast": setup_mod.obsidian_install.is_installed_fast,
            "get_tenant_vault_path": setup_mod.vault_writer_mod.get_tenant_vault_path,
            "DETECT_TTL": setup_mod._DETECT_TTL_SECONDS,
        }
        setup_mod.shutil.which = lambda name: self.which.get(name)
        notify.telegram_configured = lambda env=None: self.telegram
        setup_mod.detect_cloud_folders = lambda *a, **k: list(self.detected_clouds)
        setup_mod.speech_engine.get_engine = lambda: SimpleNamespace(
            available=lambda: (self.voz, "" if self.voz else "no instalado"))
        setup_mod.obsidian_install.is_installed_fast = lambda: self.obsidian_installed
        setup_mod.vault_writer_mod.get_tenant_vault_path = self._fake_vault_path
        # El caché de detecciones (60s) se desactiva: el gate CAMBIA los detectores
        # entre consultas y debe ver el efecto de inmediato.
        setup_mod._DETECT_TTL_SECONDS = 0.0
        setup_mod._detect_cache.clear()

    def restore(self) -> None:
        setup_mod.shutil.which = self._saved["which"]
        notify.telegram_configured = self._saved["telegram_configured"]
        setup_mod.detect_cloud_folders = self._saved["detect_cloud_folders"]
        setup_mod.speech_engine.get_engine = self._saved["get_engine"]
        setup_mod.obsidian_install.is_installed_fast = self._saved["is_installed_fast"]
        setup_mod.vault_writer_mod.get_tenant_vault_path = self._saved["get_tenant_vault_path"]
        setup_mod._DETECT_TTL_SECONDS = self._saved["DETECT_TTL"]
        setup_mod._detect_cache.clear()


def table_counts(tenant: str) -> dict:
    with sb() as c:
        pb = c.execute("SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid", (tenant,)).fetchone()[0]
        ts = c.execute("SELECT count(*) FROM tenant_settings WHERE tenant_id=%s::uuid", (tenant,)).fetchone()[0]
    return {"playbooks": pb, "settings": ts}


def run_checks(client, fake_llm: FakeCompletions, det: Detectors, tenants: list[str]) -> None:
    stamp = int(time.time() * 1000)
    ra = client.post("/api/auth/register", json={
        "email": f"setup-{stamp}-a@example.com", "password": "Password-12345",
        "firm_name": "Setup Test A"})
    rb = client.post("/api/auth/register", json={
        "email": f"setup-{stamp}-b@example.com", "password": "Password-12345",
        "firm_name": "Setup Test B"})
    assert ra.status_code == 201 and rb.status_code == 201, "registro falló"
    tenant_a, tenant_b = ra.json()["tenant_id"], rb.json()["tenant_id"]
    tenants.extend([tenant_a, tenant_b])
    auth_a = {"Authorization": f"Bearer {ra.json()['token']}"}
    auth_b = {"Authorization": f"Bearer {rb.json()['token']}"}
    with sb() as c:  # política nube para el turno de chat (LLM falso)
        for t in (tenant_a, tenant_b):
            c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{model_policy}', '\"nube\"') "
                      "WHERE tenant_id = %s::uuid", (t,))

    # ── (s) estado inicial: todo pendiente, estructura completa, solo lectura ──
    before = table_counts(tenant_a)
    r = client.get("/api/setup/status", headers=auth_a)
    body = r.json()
    check("s1 · GET /setup/status → 200 con 7 pasos y campos completos",
          r.status_code == 200 and len(body["pasos"]) == 7
          and all({"id", "titulo", "estado", "detalle", "accion"} <= set(p) for p in body["pasos"]))
    ids = [p["id"] for p in body["pasos"]]
    check("s2 · los pasos son los del recorrido (perfil→motor→obsidian→carpetas→guías→telegram→voz)",
          ids == ["perfil", "motor", "obsidian", "carpetas", "guias", "telegram", "voz"])
    check("s2b · Obsidian aparece ENTRE motor y carpetas",
          ids.index("motor") < ids.index("obsidian") < ids.index("carpetas"))
    check("s3 · sin nada configurado: 0 listos y el siguiente es el perfil",
          body["completados"] == 0 and body["siguiente"] == "perfil")
    todo_texto = " ".join(
        f"{p['titulo']} {p['detalle']}" for p in body["pasos"]) + " " + body["mensaje"]
    check("s4 · §G: los textos no traen jerga técnica",
          not _FORBIDDEN_RE.search(todo_texto))
    check("s5 · consultar el estado NO escribe nada (solo lectura)",
          table_counts(tenant_a) == before)

    # ── (g) CP-C4b: el recorrido EXPLICA como un onboarding ──
    guias = {p["id"]: p.get("guia") for p in body["pasos"]}
    check("g1 · cada paso trae su guía completa (qué es · para qué · cómo paso a paso)",
          all(isinstance(g, dict) and g.get("que_es") and g.get("para_que")
              and isinstance(g.get("como"), list) and len(g["como"]) >= 3
              for g in guias.values()))
    check("g2 · la guía explica en clave de negocio (el 'para qué' habla del despacho)",
          all("despacho" in (g["para_que"] + g["que_es"]).lower()
              or "celular" in (g["para_que"] + g["que_es"]).lower()
              for g in guias.values()))
    check("g3 · la guía de Telegram trae el paso a paso del bot (@BotFather)",
          any("@BotFather" in paso for paso in guias["telegram"]["como"]))
    texto_guias = " ".join(
        f"{g['que_es']} {g['para_que']} " + " ".join(g["como"]) for g in guias.values())
    secciones = body.get("secciones") or []
    texto_secciones = " ".join(f"{x['titulo']} {x['que_es']} {x['para_que']}" for x in secciones)
    check("g5 · §G: las guías y el mapa de secciones tampoco traen jerga técnica",
          not _FORBIDDEN_RE.search(texto_guias + " " + texto_secciones))
    # g6 se anclaba al rótulo literal «Asuntos», que D3 renombró a «Casos» con la función
    # intacta: llevaba en rojo desde entonces sin causa escrita. Re-anclado al CONCEPTO
    # (regla sellada 2026-07-29: los gates de copy verifican el concepto, nunca la
    # redacción) — que el mapa cubra la pantalla de trabajo y la de memoria del despacho,
    # se llamen como se llamen, y que cada entrada diga cuándo sirve y cómo se usa, que es
    # lo que lo convierte en un manual y no en una lista de nombres.
    titulos = " ".join(x.get("titulo", "") for x in secciones).lower()
    check("g6 · el mapa de secciones cubre la pantalla de trabajo y la de conocimiento",
          len(secciones) >= 5
          and all(x.get("que_es") and x.get("para_que") for x in secciones)
          and ("casos" in titulos or "asuntos" in titulos)
          and "conocimiento" in titulos)
    check("g6b · y es un MANUAL: cada sección dice cuándo sirve y cómo se usa",
          all(x.get("cuando") and x.get("como") for x in secciones))
    check("g6c · cada sección lleva a dónde ir (no obliga a buscarla en el menú)",
          all(str(x.get("ruta", "")).startswith("/") for x in secciones))

    # ── (s) detección simulada: cada componente cambia su paso ──
    det.which["claude"] = "C:\\bin\\claude.exe"
    det.telegram = True
    det.voz = True
    r3 = client.get("/api/setup/status", headers=auth_a).json()
    estados = {p["id"]: p["estado"] for p in r3["pasos"]}
    check("s7 · detecciones simuladas → motor/telegram/voz quedan LISTOS",
          estados["motor"] == "listo"
          and estados["telegram"] == "listo" and estados["voz"] == "listo")
    check("s8 · guías, carpetas y obsidian siguen pendientes (aún no hay datos)",
          estados["guias"] == "pendiente" and estados["carpetas"] == "pendiente"
          and estados["obsidian"] == "pendiente")
    with sb() as c:
        c.execute("INSERT INTO playbooks (tenant_id, title, summary, applies_when, content) "
                  "VALUES (%s::uuid, 'Guía setup', 's', 'w', 'c')", (tenant_a,))
        c.execute("INSERT INTO local_folder_sources (tenant_id, path, label) "
                  "VALUES (%s::uuid, 'D:\\\\trabajo', 'Trabajo')", (tenant_a,))
    r4 = client.get("/api/setup/status", headers=auth_a).json()
    estados4 = {p["id"]: p["estado"] for p in r4["pasos"]}
    check("s9 · con guía y carpeta registradas → esos pasos quedan LISTOS",
          estados4["guias"] == "listo" and estados4["carpetas"] == "listo")
    check("s9b · obsidian sigue pendiente (aún no hay vault conectado)",
          estados4["obsidian"] == "pendiente")
    check("s10 · el progreso cuenta bien (5 de 7; falta perfil y obsidian)",
          r4["completados"] == 5 and r4["siguiente"] == "perfil")

    # ── obsidian: instalado sin vault → sigue pendiente; con vault → LISTO ──
    det.obsidian_installed = True
    r4b = client.get("/api/setup/status", headers=auth_a).json()
    obs4b = next(p for p in r4b["pasos"] if p["id"] == "obsidian")
    check("o1 · Obsidian instalado sin vault conectado → sigue pendiente",
          obs4b["estado"] == "pendiente")
    det.vault_path = "D:\\vault-prueba"
    r4c = client.get("/api/setup/status", headers=auth_a).json()
    obs4c = next(p for p in r4c["pasos"] if p["id"] == "obsidian")
    check("o2 · con vault conectado (DB) → Obsidian queda LISTO",
          obs4c["estado"] == "listo" and r4c["completados"] == 6)
    # Obsidian queda LISTO de aquí en adelante (no se revierte): así el resto del
    # recorrido (skip/unskip de 'perfil', chat) se comporta igual que antes de
    # reincorporarlo — el único pendiente restante es 'perfil'.

    # ── (w) fix del hallazgo bloqueante (MN3): /status con Obsidian NO instalado
    # y SIN exe local NUNCA debe invocar winget. Se restaura momentáneamente la
    # función REAL is_installed_fast (sin mock), se fuerza "sin exe local"
    # (_local_candidates → []) y se espía subprocess.run — no basta con mockear
    # is_installed_fast como hace 'det': aquí se ejercita el código real.
    _real_subprocess = setup_mod.obsidian_install.subprocess
    _orig_run = _real_subprocess.run
    _orig_local_candidates = setup_mod.obsidian_install._local_candidates
    winget_calls: list = []

    def _spy_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]).lower() == "winget":
            winget_calls.append(list(cmd))
        return _orig_run(cmd, *args, **kwargs)

    setup_mod.obsidian_install.is_installed_fast = det._saved["is_installed_fast"]  # función REAL
    setup_mod.obsidian_install._local_candidates = lambda: []  # sin exe local
    _real_subprocess.run = _spy_run
    try:
        t0 = time.monotonic()
        rw = client.get("/api/setup/status", headers=auth_a)
        w_elapsed = time.monotonic() - t0
    finally:
        _real_subprocess.run = _orig_run
        setup_mod.obsidian_install._local_candidates = _orig_local_candidates
        # el status vuelve a ver el mock de 'det' (obsidian_installed=True desde o2)
        setup_mod.obsidian_install.is_installed_fast = lambda: det.obsidian_installed
        setup_mod._detect_cache.clear()
    check("w1 · /status con Obsidian sin exe local NUNCA invoca winget (espía subprocess.run)",
          rw.status_code == 200 and not winget_calls)
    check("w2 · /status responde rápido, sin el fallback bloqueante de winget (<5s)",
          w_elapsed < 5.0)
    check("w3 · el status conserva sus 7 pasos tras ejercitar el código real",
          len(rw.json()["pasos"]) == 7)

    # ── (k) skip/unskip retomable + RLS ──
    rs = client.post("/api/setup/steps/perfil/skip", headers=auth_a)
    r5 = client.get("/api/setup/status", headers=auth_a).json()
    perfil5 = next(p for p in r5["pasos"] if p["id"] == "perfil")
    check("k1 · 'dejar para después' → el paso queda omitido y persiste",
          rs.status_code == 200 and perfil5["estado"] == "omitido"
          and r5["siguiente"] is None)
    with sb() as c:
        row = c.execute("SELECT config->'setup'->'skipped' FROM tenant_settings "
                        "WHERE tenant_id=%s::uuid", (tenant_a,)).fetchone()
    check("k2 · lo omitido vive en tenant_settings.config['setup']",
          row and row[0] == ["perfil"])
    ru = client.post("/api/setup/steps/perfil/unskip", headers=auth_a)
    r6 = client.get("/api/setup/status", headers=auth_a).json()
    check("k3 · 'retomar' → vuelve a pendiente (recorrido retomable)",
          ru.status_code == 200
          and next(p for p in r6["pasos"] if p["id"] == "perfil")["estado"] == "pendiente")
    check("k4 · paso inexistente → 404 (allowlist de pasos)",
          client.post("/api/setup/steps/hackear/skip", headers=auth_a).status_code == 404)
    rb_status = client.get("/api/setup/status", headers=auth_b).json()
    check("k5 · RLS: el despacho B tiene SU propio recorrido (nada de A se filtra)",
          rb_status["completados"] < r4["completados"]
          and all(p["estado"] != "omitido" for p in rb_status["pasos"]))
    check("k6 · sin sesión → 401", client.get("/api/setup/status").status_code == 401)

    # ── (a) el asistente guía por chat con el estado real ──
    fake_llm.script["claude-sonnet"] = ["Claro, conectemos tu Google Drive paso a paso."]
    rc = client.post("/api/assistant/chat", headers=auth_a,
                     json={"message": "Ayúdame a conectar mi Google Drive con Mia"})
    sent = fake_llm.last_for("claude-sonnet")
    last_user = sent["messages"][-1]["content"] if sent else ""
    check("a1 · el modelo ve el bloque con el estado real de configuración",
          rc.status_code == 200 and SETUP_BLOCK_HEADER in last_user
          and "carpetas" in last_user.lower())
    check("a3 · CP-C4b: el modelo ve la GUÍA del siguiente paso (qué es/para qué/cómo)",
          "Guía del siguiente paso pendiente:" in last_user
          and "Qué es:" in last_user and "Cómo, paso 1:" in last_user)
    # L1 (revisión capa 2): la guía llega COMPLETA al chat, no cortada a 150 chars.
    # El siguiente pendiente aquí es "perfil" (los demás quedaron listos en s7/s9); su
    # 'para_que' supera los 150 chars y debe aparecer entero en el bloque del sistema.
    status_now = client.get("/api/setup/status", headers=auth_a).json()
    guia_sig = next(p["guia"] for p in status_now["pasos"]
                    if p["id"] == status_now["siguiente"])
    para_que_full = guia_sig["para_que"]
    check("a4 · L1: la guía NO se entrega truncada a mitad de oración (llega completa)",
          len(para_que_full) > 150 and para_que_full in last_user.replace("\n", " "))
    with sb() as c:
        persisted = c.execute(
            "SELECT content FROM assistant_messages WHERE conversation_id=%s::uuid "
            "AND role='user' ORDER BY created_at DESC LIMIT 1",
            (rc.json()["conversation_id"],),
        ).fetchone()[0]
    check("a2 · el mensaje PERSISTIDO va limpio (el bloque no se guarda)",
          SETUP_BLOCK_HEADER not in persisted)


def run_frontend_checks() -> None:
    page = (ROOT / "frontend" / "app" / "configurar" / "page.tsx").read_text(encoding="utf-8")
    sidebar = (ROOT / "frontend" / "app" / "_components" / "Sidebar.tsx").read_text(encoding="utf-8")
    check("f1 · página /configurar consume /api/setup/status con skip y retomar",
          "/api/setup/status" in page and "Dejar para después" in page and "Retomar" in page)
    check("f2 · CP-C4b: la página pinta la guía del servidor (qué es/para qué/cómo) y "
          "el mapa de secciones — sin rutas técnicas (§G)",
          "¿Qué es esto?" in page and "guia.como" in page
          and "¿Qué hace cada sección de Mia?" in page
          and "telegram-setup.md" not in page)
    # El pase wow (2026-07) extrajo los items de navegación a nav.ts; el Sidebar
    # los consume desde ahí. El check exige el MISMO comportamiento (el menú
    # lateral enlaza 'Configuración' — reestructuración 2026-07-09), mirando
    # ambos archivos.
    nav_src = (ROOT / "frontend" / "app" / "_components" / "nav.ts").read_text(encoding="utf-8")
    check("f3 · el Sidebar enlaza 'Configuración'",
          "/configurar" in (sidebar + nav_src) and "Configuración" in (sidebar + nav_src))
    check("f4 · accesibilidad: barra de progreso con role y valores (hallazgo capa 3 diferido)",
          'role="progressbar"' in page and "aria-valuenow" in page
          and "aria-expanded" in page)


def main() -> int:
    print("== CP-C4 · asistente de configuración guiado (setup wizard) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    init_profiles.apply()
    init_users.apply()
    init_assistant.apply()
    init_playbooks.apply()
    init_local_folders.apply()

    fake_llm = FakeCompletions()
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake_llm))
    llm.time.sleep = lambda *_a, **_k: None

    det = Detectors()
    det.install()
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tenants: list[str] = []
    try:
        with TestClient(app) as client:
            run_checks(client, fake_llm, det, tenants)
        run_frontend_checks()
    finally:
        det.restore()
        llm._client = None
        cleanup(tenants)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Setup guiado OK — CP-C4 verificado (detección simulada + retomable + chat + UI).")
        return 0
    print("Setup guiado FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
