"""
Mia · seed_despacho_demo.py — despacho de prueba COMPLETO para verificación visual.

POR QUÉ EXISTE (regla 62 de APRENDIZAJES.md): sin esto, capturar una sola pantalla de Mia
cuesta veinte minutos de andamiaje. El onboarding redirige a la entrevista mientras el
despacho no tenga SOUL.md, y varias pantallas (revisión del borrador, avisos del guardián,
aviso de costo) solo existen DESPUÉS de un turno completo. Por eso hubo trabajo que se
cerró sin verificación visual: no porque nadie quisiera mirar, sino porque mirar costaba
más que construir.

Qué deja montado, en una corrida y sin red:

  · Un despacho con usuario, contraseña conocida, perfil y SOUL.md → la app abre en el
    escritorio del abogado, no en la entrevista.
  · Un asunto CON documentos y un borrador ESPERANDO REVISIÓN, generado por el grafo real
    (no una fila cosida a mano): la pantalla de revisión se abre con su informe de citas.
  · Ese borrador trae, a propósito, las tres cosas que había que poder mirar y no se podía:
    una cita sin respaldo (botón «esta cita no existe»), una afirmación negativa sobre el
    expediente y una parte de OTRO asunto del mismo despacho (contaminación).
  · Un asunto vacío y un proyecto, para las pantallas en estado inicial.

El modelo y los embeddings van MOCKEADOS (mismo patrón que test_ux): el seed no gasta
cuota, no toca la red y sale igual todas las veces. El borrador NO es trabajo jurídico:
es material de prueba, y el texto lo dice.

    .venv\\Scripts\\python.exe execution\\seed_despacho_demo.py
    .venv\\Scripts\\python.exe execution\\seed_despacho_demo.py --json     (para Playwright)
    .venv\\Scripts\\python.exe execution\\seed_despacho_demo.py --borrar   (lo deja limpio)

Requiere la DB portable encendida y las migraciones aplicadas (init_db.py).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

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

from mia import config, embeddings          # noqa: E402
from mia.agent import llm                    # noqa: E402
from mia.agents.state import thread_id_for   # noqa: E402

# ── Identidad fija del despacho demo ──────────────────────────────────────────
# Fija a propósito: el mismo correo y la misma contraseña en toda máquina, para que las
# instrucciones de captura no dependan de lo que imprimió la última corrida.
DEMO_EMAIL = "demo@despacho-demo.test"
DEMO_PASSWORD = "DespachoDemo.2026"
DEMO_FIRM = "Despacho Demo (material de prueba)"

# La contraparte del OTRO asunto. La contaminación entre expedientes se detecta con las
# partes del propio despacho, así que el segundo asunto tiene que existir de verdad y el
# borrador tiene que nombrar a su contraparte.
OTRA_PARTE = "Constructora Belmonte S.A."

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

# Perfil del despacho. Agnóstico de jurisdicción a propósito (regla dura: Mia no es de
# ningún país): sin ordenamiento configurado, las referencias normativas salen marcadas
# para verificar — que es justamente uno de los estados que hay que poder mirar.
RESPUESTAS_PERFIL = {
    "identity.name": "Despacho Demo — Ana Restrepo, socia directora",
    "identity.location": "Ciudad de prueba",
    "identity.voice": "Sobrio, directo, sin adjetivos. Se afirma lo que se puede probar.",
    "jurisdiction.practice_areas": "Contratación privada, seguros, responsabilidad civil",
    "jurisdiction.client_type": "Empresas medianas y aseguradoras",
    "autonomia.reviso_siempre": [
        "Todo escrito que se radica",
        "Toda cifra que entre a una pretensión",
        "Toda cita normativa o jurisprudencial",
    ],
    "autonomia.decide_solo": [
        "El orden de los argumentos",
        "Qué documentos del expediente conviene leer primero",
    ],
    "nunca": [
        "Afirmar un hecho que no esté en el expediente",
        "Calcular un término procesal por su cuenta",
        "Citar una norma sin respaldo",
    ],
    "terminado": (
        "Cuando cada afirmación tiene su respaldo señalado y el escrito puede radicarse "
        "sin que yo tenga que reescribirlo."
    ),
    "legal_voice.structure": "Hechos, problema jurídico, argumentos, petición.",
    "legal_voice.banned_words": "«es claro que», «sin lugar a dudas», «grosso modo»",
}

# ── Dobles (sin red) ──────────────────────────────────────────────────────────
# El borrador que produce este doble es MATERIAL DE PRUEBA y lo dice en su primera línea.
# Cada pieza está puesta para que una pantalla concreta tenga algo que mostrar:
#   · «Ley 4137 de 2011, artículo 12» → cita sin respaldo: sale marcada y con el botón
#     «esta cita no existe o no dice eso» (banco de citas quemadas).
#   · «El expediente no contiene ninguna comunicación …» → afirmación negativa: el
#     guardián la contrasta contra el documento completo y avisa.
#   · La contraparte del otro asunto → aviso de contaminación entre expedientes.
BORRADOR_DEMO = (
    "BORRADOR DE PRUEBA (material de demostración, no es trabajo jurídico).\n\n"
    "1. El contrato de suministro obrante en el expediente fija en su cláusula 12 el "
    "plazo de entrega [doc 1].\n"
    "2. Conforme a la Ley 4137 de 2011, artículo 12, la mora se cuenta desde el "
    "requerimiento.\n"
    "3. El contrato no menciona ninguna prórroga del plazo de entrega [doc 1].\n"
    "4. El expediente no contiene ninguna comunicación de requerimiento previo [doc 2].\n"
    f"5. Lo resuelto frente a {OTRA_PARTE} confirma el criterio expuesto.\n"
)

DIAGNOSTICO_DEMO = (
    "DIAGNÓSTICO DE PRUEBA: el eje es la mora en la entrega y quién soporta la carga de "
    "probar el requerimiento previo."
)


# Términos ENTERRADOS: van en el documento pero deben quedar FUERA de lo que el turno
# recupera. Es la condición del aviso de afirmaciones negativas —una negativa escrita sobre
# lo que se tenía a la vista y contradicha por el documento completo— y no se puede dejar al
# azar: con todos los vectores iguales, qué fragmento entra lo decide un empate, y el aviso
# aparecía una corrida sí y otra no. Aquí el doble de embeddings los manda al fondo del
# ranking a propósito, y el seed sale igual todas las veces.
TERMINOS_ENTERRADOS = ("prórroga", "requerimiento previo")


def _fake_embed(texts):
    salida = []
    for t in texts:
        enterrado = any(term in (t or "").lower() for term in TERMINOS_ENTERRADOS)
        # Ortogonal al vector de todo lo demás (y de la consulta, que no los nombra):
        # distancia máxima → último en el ranking, siempre.
        v = [0.0, 1.0] if enterrado else [1.0, 0.0]
        salida.append(v + [0.0] * (config.EMBED_DIM - 2))
    return salida


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "Redacta el borrador" in sysmsg:
        content = BORRADOR_DEMO
    elif "Incorpora al borrador" in sysmsg:
        content = BORRADOR_DEMO + "\n(Versión con las indicaciones del abogado.)"
    else:
        content = DIAGNOSTICO_DEMO
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32))


def _instalar_dobles() -> None:
    embeddings.embed_texts = _fake_embed
    llm.call_llm = _fake_call_llm


# ── Documentos sintéticos ─────────────────────────────────────────────────────
def _pdf(texto: str) -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    for i, linea in enumerate(texto.split("\n")):
        page.insert_text((60, 70 + i * 16), linea)
    data = doc.tobytes()
    doc.close()
    return data


def _docx(texto: str) -> bytes:
    import docx
    d = docx.Document()
    for linea in texto.split("\n"):
        d.add_paragraph(linea)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ── Borrado ───────────────────────────────────────────────────────────────────
def _tenants_demo() -> list[str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        filas = c.execute(
            "SELECT t.id FROM tenants t JOIN users u ON u.tenant_id = t.id WHERE u.email = %s",
            (DEMO_EMAIL,)).fetchall()
    return [str(f[0]) for f in filas]


def borrar_demo(verboso: bool = True) -> int:
    """Deja la máquina como si el demo no hubiera existido. Devuelve cuántos borró.

    Borra también lo que NO vive en la base: el SOUL.md, las respuestas y la wiki del
    despacho son archivos en MIA_HOME, y un `DELETE FROM tenants` los deja huérfanos —
    con el efecto peor de todos, que la próxima corrida del demo arranque con el perfil
    de la anterior sin que nadie lo note."""
    tenants = _tenants_demo()
    for tid in tenants:
        with psycopg.connect(autocommit=True, **PG) as c:
            hilos = c.execute(
                "SELECT id FROM matters WHERE tenant_id = %s::uuid", (tid,)).fetchall()
            for (mid,) in hilos:
                th = thread_id_for(tid, str(mid))
                for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    c.execute(f"DELETE FROM {t} WHERE thread_id = %s", (th,))
            c.execute("DELETE FROM tenants WHERE id = %s::uuid", (tid,))
        home = Path(config.MIA_HOME)
        for p in home.glob(f"soul_{tid}*"):
            p.unlink(missing_ok=True)
        shutil.rmtree(home / "wiki" / tid, ignore_errors=True)
        if verboso:
            print(f"  [BORRADO] despacho demo {tid}")
    return len(tenants)


# ── Siembra ───────────────────────────────────────────────────────────────────
def sembrar() -> dict:
    _instalar_dobles()
    from fastapi.testclient import TestClient

    from mia.api.main import app
    from mia.onboarding.soul_interview import SoulInterview

    borrar_demo(verboso=False)  # el demo se rehace entero: nunca se mezcla con el anterior

    with TestClient(app) as client:   # el lifespan abre el pool de conexiones
        return _sembrar_con(client)


def _sembrar_con(client) -> dict:
    from mia.onboarding.soul_interview import SoulInterview

    r = client.post("/api/auth/register", json={
        "email": DEMO_EMAIL, "password": DEMO_PASSWORD, "firm_name": DEMO_FIRM})
    if r.status_code != 201:
        raise SystemExit(f"no se pudo crear el despacho demo: {r.status_code} {r.text}")
    token = r.json()["token"]
    tid = r.json()["tenant_id"]
    auth = {"Authorization": f"Bearer {token}"}

    # Perfil + SOUL.md: es lo que hace que la app NO redirija a la entrevista.
    asyncio.run(SoulInterview().run_interview(tid, RESPUESTAS_PERFIL))

    # Asunto 2 primero: su contraparte tiene que existir ANTES del turno del asunto 1,
    # porque la contaminación entre expedientes se detecta con las partes del despacho.
    otro = client.post("/api/matters", headers=auth, json={
        "name": f"Belmonte · incumplimiento de obra",
        "description": f"Contraparte: {OTRA_PARTE}. Asunto distinto, sirve para el aviso "
                       "de contaminación entre expedientes."}).json()["id"]
    client.post(f"/api/matters/{otro}/documents", headers=auth, files={
        "file": ("acta-belmonte.pdf",
                 _pdf(f"Acta de obra. Contratista: {OTRA_PARTE}.\n"
                      "Se deja constancia del avance de la obra."), "application/pdf")})

    principal = client.post("/api/matters", headers=auth, json={
        "name": "Suministro Andina · mora en la entrega",
        "description": "Asunto de demostración con documentos y borrador para revisar."
    }).json()["id"]
    # El contrato es largo A PROPÓSITO y la prórroga aparece SOLO al final: así el turno
    # recupera unos fragmentos y no otros, que es la condición del aviso de afirmaciones
    # negativas (una negativa escrita sobre lo que se tenía a la vista, contradicha por el
    # documento completo). Con un documento de un solo fragmento ese aviso no puede existir.
    clausulas = "\n".join(
        f"Cláusula {i}. Obligación ordinaria del suministro, sin incidencia en el plazo."
        for i in range(1, 40))
    client.post(f"/api/matters/{principal}/documents", headers=auth, files={
        "file": ("contrato-suministro.pdf",
                 _pdf("CONTRATO DE SUMINISTRO\n"
                      "Cláusula 12. El plazo de entrega es de treinta días.\n"
                      f"{clausulas}\n"
                      "Cláusula 40. Las partes acordaron una prórroga del plazo de entrega "
                      "y dejaron constancia del requerimiento previo de entrega."),
                 "application/pdf")})
    # Los dos documentos entierran LOS DOS términos: cuál de ellos queda como [doc 1] lo
    # decide el ranking del turno, y una siembra no puede depender de ese orden.
    client.post(f"/api/matters/{principal}/documents", headers=auth, files={
        "file": ("comunicaciones.docx",
                 _docx("Comunicación del 3 de marzo: se solicita informe de avance.\n"
                       + "\n".join(f"Comunicación de trámite {i}: sin novedad."
                                   for i in range(1, 40))
                       + "\nComunicación del 19 de marzo: se formula requerimiento previo "
                         "de entrega y se acepta la prórroga del plazo."),
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})

    # Ficha de las piezas: la contaminación entre expedientes se DERIVA de `documents.parte`
    # (nada cableado). En una instalación real la confirma el abogado desde la pantalla de
    # documentos; aquí se escribe directo porque esto es siembra, no un flujo de usuario.
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE documents SET parte = %s WHERE matter_id = %s::uuid",
                  (OTRA_PARTE, otro))
        c.execute("UPDATE documents SET parte = %s WHERE matter_id = %s::uuid",
                  ("Suministros Andina S.A.S.", principal))

    # El turno REAL, hasta la pausa de revisión: el borrador y su informe de citas quedan
    # en el checkpoint, que es de donde los lee la pantalla. Cosidos a mano no existirían.
    with client.stream("GET", f"/api/matters/{principal}/stream",
                       params={"message": "¿Estamos en mora frente al contrato de suministro?"},
                       headers=auth) as s:
        cuerpo = "".join(s.iter_text())
    if "awaiting_review" not in cuerpo:
        raise SystemExit("el turno no dejó borrador esperando revisión; revisa la DB y las "
                         "migraciones (init_db.py)")

    vacio = client.post("/api/matters", headers=auth, json={
        "name": "Asunto nuevo (sin documentos)"}).json()["id"]
    proyecto = client.post("/api/matters", headers=auth, json={
        "name": "Proyecto de demostración", "kind": "proyecto"}).json().get("id")

    return {
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "tenant_id": tid,
        "token": token,
        "asunto_con_borrador": principal,
        "asunto_otro": otro,
        "asunto_vacio": vacio,
        "proyecto": proyecto,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Despacho de prueba para verificación visual")
    ap.add_argument("--json", action="store_true", help="salida en JSON (para Playwright)")
    ap.add_argument("--borrar", action="store_true", help="borra el despacho demo y termina")
    args = ap.parse_args()

    if args.borrar:
        n = borrar_demo()
        print(f"DONE — {n} despacho(s) demo borrado(s)" if n else "DONE — no había demo")
        return 0

    datos = sembrar()
    if args.json:
        print(json.dumps(datos, ensure_ascii=False))
        return 0

    print("== Despacho demo listo ==")
    print(f"  correo      : {datos['email']}")
    print(f"  contraseña  : {datos['password']}")
    print(f"  despacho    : {datos['tenant_id']}")
    print()
    print("  Asunto con borrador esperando revisión:")
    print(f"    /asuntos/{datos['asunto_con_borrador']}")
    print(f"    /asuntos/{datos['asunto_con_borrador']}/revisar")
    print(f"  Asunto vacío : /asuntos/{datos['asunto_vacio']}")
    print(f"  Proyecto     : /proyectos/{datos['proyecto']}")
    print()
    print("  Entra por /login con ese correo (la app abre en el escritorio, no en la")
    print("  entrevista). Para saltarte el login en un navegador automatizado, inyecta")
    print("  el token en localStorage con la clave 'mia_token' (--json lo imprime).")
    print()
    print("  Al terminar:  .venv\\Scripts\\python.exe execution\\seed_despacho_demo.py --borrar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
