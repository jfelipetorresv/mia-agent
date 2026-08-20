"""
Mia · test_comentarios_borrador.py — gate de los COMENTARIOS ANCLADOS sobre el borrador.

El abogado marca un pasaje del borrador y escribe qué quiere cambiar ahí; Mia corrige
ese punto y deja el resto idéntico. Este gate prueba los DOS sentidos:

  (a) comentario sobre un pasaje → solo ese pasaje cambia y la resolución lo refleja;
  (b) el re-draft toca pasajes NO comentados → el aviso aparece («también cambié X»).

Más el ancla (texto exacto, texto desplazado, contexto, no ubicado), la instrucción de
corrección que va al prompt, y el cableado del grafo (comentarios → nodo de redacción,
no → cierre). Ese tramo es puro: sin DB, sin red y sin LLM.

Si además hay base de datos disponible, corre el CAMINO REAL DEL GRAFO con el modelo
mockeado (igual que test_hitl_flow): comentar reanuda hacia una corrección acotada y
devuelve a la revisión con el informe. Sin base de datos ese tramo se declara pendiente
en vez de fingirse verde.

    .venv\\Scripts\\python.exe execution\\test_comentarios_borrador.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import comentarios as C  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


BORRADOR = """Señor Juez, en nombre de mi representada contesto la demanda de la referencia.

El monto reclamado por la demandante asciende a cien millones de pesos, suma que no
corresponde a la liquidación del contrato.

La cláusula quinta del contrato regula la forma de pago y su incumplimiento.

Con fundamento en lo anterior, solicito respetuosamente denegar las pretensiones."""


PARRAFO_MONTO = [p for p in BORRADOR.split("\n\n") if "cien millones" in p][0].strip()
PARRAFO_PETICION = [p for p in BORRADOR.split("\n\n") if "solicito" in p][0].strip()


def comentario_monto() -> dict:
    return {
        "id": "c1",
        "texto_citado": PARRAFO_MONTO,
        "parrafo_indice": 1,
        "contexto_antes": "contesto la demanda de la referencia.",
        "contexto_despues": "La cláusula quinta del contrato",
        "instruccion": "Este monto está mal: son ochenta millones.",
    }


# ── camino real del grafo (DB + checkpointer, LLM mockeado) ──────────────────
BORRADOR_MOCK = (
    "Señor Juez, contesto la demanda de la referencia en nombre de mi representada.\n\n"
    "El monto reclamado por la demandante asciende a cien millones de pesos.\n\n"
    "Con fundamento en lo anterior, solicito denegar las pretensiones."
)
#: Lo que el modelo "corrige" en la segunda pasada. El caso (b) cambia además un
#: párrafo que NADIE comentó: ahí es donde tiene que aparecer el aviso.
CORRECCION = {"tocar_de_mas": False}


def _draft_corregido() -> str:
    texto = BORRADOR_MOCK.replace("cien millones", "ochenta millones")
    if CORRECCION["tocar_de_mas"]:
        texto = texto.replace("solicito denegar las pretensiones.",
                              "solicito declarar probadas las excepciones y condenar en costas.")
    return texto


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if task == "legal_verification":
        content = "APTO"
    elif "Tarea de este turno — CORRECCIÓN" in sysmsg:
        content = _draft_corregido()
    elif "Tarea de este turno — BORRADOR" in sysmsg:
        content = BORRADOR_MOCK
    else:
        content = "DIAGNÓSTICO: el eje del asunto es la caducidad de la acción."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32),
    )


async def _ronda_de_comentarios(tenant, matter, tocar_de_mas: bool) -> dict:
    """Corre el grafo hasta la revisión, comenta un pasaje y devuelve el informe."""
    from langgraph.types import Command
    from mia.agents.checkpointer import open_checkpointer
    from mia.agents.graph import build_matter_graph
    from mia.agents.state import initial_state, thread_id_for
    from mia.db import pool
    from mia.memory import legal_ledger

    CORRECCION["tocar_de_mas"] = tocar_de_mas
    await pool.open_pool()
    try:
        cfg = {"configurable": {"thread_id": thread_id_for(tenant, matter)}}
        inp = initial_state(tenant, matter, "¿Caducó la acción?",
                            profile_snapshot={"despacho": "Defendemos aseguradoras."})
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp)
            _ = [c async for c in graph.astream(inp, cfg, stream_mode="updates")]
            st = await graph.aget_state(cfg)
        borrador = (st.values or {}).get("draft") or ""
        pasaje = [p for p in borrador.split("\n\n") if "cien millones" in p]
        comentario = {
            "id": "c1",
            "texto_citado": (pasaje[0] if pasaje else borrador).strip(),
            "parrafo_indice": 1,
            "contexto_antes": "", "contexto_despues": "",
            "instruccion": "Este monto está mal: son ochenta millones.",
        }
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp)
            _ = [c async for c in graph.astream(Command(resume={
                "decision": "comments",
                "draft_hash": legal_ledger.content_hash(borrador),
                "comentarios": [comentario],
            }), cfg, stream_mode="updates")]
            st2 = await graph.aget_state(cfg)
        values = st2.values or {}
        md = values.get("metadata") or {}
        return {
            "borrador_antes": borrador,
            "borrador_despues": values.get("draft") or "",
            "informe": md.get("comentarios_resueltos") or {},
            "pausado_en_revision": "hitl_checkpoint" in list(st2.next),
            "verification": md.get("verification") or {},
        }
    finally:
        await pool.close_pool()


def pruebas_con_db() -> bool:
    """El camino real del grafo. Devuelve False si no hay DB (tramo pendiente)."""
    import psycopg
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from mia import config, embeddings
    from mia.agent import llm
    from mia.agents.state import thread_id_for

    pg = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    try:
        with psycopg.connect(autocommit=True, connect_timeout=5, **pg) as c:
            a = c.execute("INSERT INTO tenants(name) VALUES('A comentarios') "
                          "RETURNING id").fetchone()[0]
            m1 = c.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Comentario acotado') "
                           "RETURNING id", (a,)).fetchone()[0]
            m2 = c.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Comentario con exceso') "
                           "RETURNING id", (a,)).fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        print(f"  [PEND] sin base de datos disponible ({type(exc).__name__}): el camino real "
              f"del grafo queda SIN verificar en esta corrida")
        return False

    embeddings.embed_texts = lambda texts: [[0.0] * config.EMBED_DIM for _ in texts]
    llm.call_llm = _fake_call_llm
    # Sin expediente sembrado, la puerta de etapas aborta el borrador antes de redactar
    # (es su trabajo). Aquí lo que se prueba es el camino de los COMENTARIOS, así que esa
    # puerta se abre a propósito: con ella cerrada no hay borrador que comentar.
    from mia.agents import stage_gate
    stage_gate.require_upstream_for_draft = lambda md: None
    a, m1, m2 = str(a), str(m1), str(m2)
    try:
        r1 = asyncio.run(_ronda_de_comentarios(a, m1, tocar_de_mas=False))
        check("grafo: tras comentar, el borrador vuelve a la revisión del abogado",
              r1["pausado_en_revision"])
        check("grafo: (a) el pasaje comentado quedó corregido",
              "ochenta millones" in r1["borrador_despues"])
        check("grafo: (a) el resto del escrito quedó idéntico",
              "solicito denegar las pretensiones." in r1["borrador_despues"])
        check("grafo: (a) el informe declara el comentario atendido",
              bool((r1["informe"].get("comentarios") or [{}])[0].get("atendido")))
        check("grafo: (a) sin cambios de más, no hay aviso",
              (r1["informe"].get("avisos") or []) == [])
        check("grafo: (a) el gate de citas volvió a pasar sobre el texto corregido",
              bool(r1["verification"]))

        r2 = asyncio.run(_ronda_de_comentarios(a, m2, tocar_de_mas=True))
        check("grafo: (b) el pasaje NO comentado que Mia tocó sale como aviso",
              any("denegar las pretensiones" in (av.get("antes") or "")
                  for av in (r2["informe"].get("avisos") or [])))
        check("grafo: (b) el aviso avisa, no bloquea: la corrección pedida también se aplicó",
              "ochenta millones" in r2["borrador_despues"])
        check("grafo: (b) el resumen se lo dice al abogado en llano",
              "no me pediste" in (r2["informe"].get("resumen") or ""))
        return True
    finally:
        with psycopg.connect(autocommit=True, **pg) as c:
            for tid in (thread_id_for(a, m1), thread_id_for(a, m2)):
                for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
            c.execute("DELETE FROM tenants WHERE id=%s", (a,))


def main() -> int:
    print("== Comentarios anclados sobre el borrador ==")

    # ── 1 · el ancla ──────────────────────────────────────────────────────────
    anclados = C.anclar([comentario_monto()], BORRADOR)
    check("el pasaje comentado se ancla por texto exacto",
          len(anclados) == 1 and anclados[0]["metodo"] == "exacto"
          and anclados[0]["parrafo_resuelto"] == 1)

    # El documento se movió (se insertó un párrafo antes): el índice miente, el texto no.
    movido = "Nuevo párrafo introductorio del escrito, agregado después.\n\n" + BORRADOR
    a_mov = C.anclar([comentario_monto()], movido)
    check("si el documento se desplaza, el ancla sigue al TEXTO y no al índice",
          a_mov[0]["ubicado"] and a_mov[0]["parrafo_resuelto"] == 2
          and a_mov[0]["metodo"] == "desplazado")

    # Reescritura menor del párrafo: el texto exacto ya no está, pero el contexto sí.
    parecido = BORRADOR.replace("asciende a cien millones de pesos",
                                "asciende a cien millones de pesos colombianos")
    a_par = C.anclar([comentario_monto()], parecido)
    check("un pasaje levemente reescrito se ancla por parecido/contexto",
          a_par[0]["ubicado"] and a_par[0]["parrafo_resuelto"] == 1)

    # Pasaje que ya no existe: se declara no ubicado, no se inventa un ancla.
    huerfano = C.anclar([{**comentario_monto(),
                          "texto_citado": "La póliza de cumplimiento número 4471 fue expedida "
                                          "por una aseguradora distinta de la demandada.",
                          "parrafo_indice": 1}], BORRADOR)
    check("un pasaje que ya no existe se declara NO ubicado (no se inventa el ancla)",
          not huerfano[0]["ubicado"] and huerfano[0]["metodo"] == "no_ubicado")

    check("un comentario sin instrucción o sin pasaje se descarta",
          C.normalizar_entrada([{"texto_citado": "algo"},
                                {"instruccion": "cámbialo"}]) == [])
    check("hay tope de comentarios por ronda",
          len(C.normalizar_entrada([comentario_monto()] * 50)) == C.MAX_COMENTARIOS)

    # ── 2 · la instrucción que llega al redactor ──────────────────────────────
    instr = C.instruccion_de_correccion(BORRADOR, anclados)
    check("la instrucción ordena modificar ÚNICAMENTE los pasajes comentados",
          "ÚNICAMENTE los pasajes comentados" in instr)
    check("la instrucción exige conservar el resto IDÉNTICO",
          "IDÉNTICO" in instr)
    check("la instrucción exige devolver el documento completo",
          "documento COMPLETO" in instr)
    check("el pasaje y la orden del abogado viajan en la instrucción",
          "cien millones" in instr and "ochenta millones" in instr)

    # ── 3 · (a) solo cambia el pasaje comentado ───────────────────────────────
    corregido = BORRADOR.replace("cien millones", "ochenta millones")
    r = C.resoluciones(BORRADOR, corregido, anclados)
    com = r["comentarios"][0]
    check("(a) la resolución marca el comentario como atendido", com["atendido"])
    check("(a) la resolución trae el pasaje NUEVO",
          "ochenta millones" in com["pasaje_despues"])
    check("(a) la resolución trae el pasaje anterior",
          "cien millones" in com["pasaje_antes"])
    check("(a) la resolución dice EN QUÉ cambió", bool(com["cambio"].strip()))
    check("(a) sin cambios fuera de lo comentado NO hay aviso", r["avisos"] == [])
    check("(a) el resumen declara que el resto quedó igual",
          "resto del documento quedó igual" in r["resumen"])
    check("(a) el resumen no muestra jerga técnica (§G)",
          not any(j in r["resumen"] for j in
                  ("diff", "párrafo_indice", "ancla", "LangGraph", "hash", "token")))

    # ── 4 · (b) Mia también tocó lo que nadie le pidió → AVISO ────────────────
    de_mas = corregido.replace(
        PARRAFO_PETICION,
        "Con fundamento en lo expuesto, solicito declarar probadas las excepciones "
        "propuestas y condenar en costas a la parte demandante.")
    r2 = C.resoluciones(BORRADOR, de_mas, anclados)
    check("(b) el pasaje NO comentado que cambió aparece como aviso",
          len(r2["avisos"]) == 1 and "denegar las pretensiones" in r2["avisos"][0]["antes"])
    check("(b) el aviso trae también el texto nuevo del pasaje",
          "costas" in r2["avisos"][0]["despues"])
    check("(b) el resumen le dice al abogado que también se cambió algo más",
          "no me pediste" in r2["resumen"])
    check("(b) el comentario sí atendido sigue reportándose como atendido",
          r2["comentarios"][0]["atendido"])
    check("(b) el aviso es AVISO, no bloqueo: la corrección igual se reporta",
          r2["comentarios"][0]["pasaje_despues"].strip() != "")

    # Un párrafo agregado de la nada también es un cambio no pedido.
    con_agregado = corregido.replace(
        PARRAFO_PETICION, "Adicionalmente, propongo la excepción de caducidad.\n\n"
        + PARRAFO_PETICION)
    r3 = C.resoluciones(BORRADOR, con_agregado, anclados)
    check("(b) un párrafo AGREGADO sin pedirlo también se avisa",
          any(a["tipo"] == "agregado" and "caducidad" in a["despues"]
              for a in r3["avisos"]))

    # ── 5 · el diff por párrafo no esconde el aviso en un bloque ──────────────
    # Cambiar el párrafo comentado Y el siguiente produce UN solo bloque en el diff
    # agrupado del harness; abierto párrafo a párrafo, el no comentado se ve.
    contiguo = corregido.replace(
        "La cláusula quinta del contrato regula la forma de pago y su incumplimiento.",
        "La cláusula sexta del contrato regula la forma de pago.")
    r4 = C.resoluciones(BORRADOR, contiguo, anclados)
    check("un cambio contiguo al comentado NO se esconde en el bloque del diff",
          any("cláusula quinta" in a["antes"] for a in r4["avisos"]))

    # ── 6 · sin cambios: se dice, no se finge ─────────────────────────────────
    r5 = C.resoluciones(BORRADOR, BORRADOR, anclados)
    check("si el borrador quedó igual, se declara con franqueza",
          r5["avisos"] == [] and "igual" in r5["resumen"]
          and not r5["comentarios"][0]["atendido"])

    # ── 7 · cableado del grafo ────────────────────────────────────────────────
    from mia.agents.graph import _route_after_hitl  # noqa: E402
    check("con comentarios pendientes el grafo vuelve a REDACCIÓN, no al cierre",
          _route_after_hitl({"metadata": {"needs_comment_redraft": True}}) == "draft")
    check("sin comentarios el grafo sigue al cierre de siempre",
          _route_after_hitl({"metadata": {}}) == "finalize")

    from mia.api.routes.hitl import ComentariosBody  # noqa: E402
    check("el endpoint exige la huella del borrador comentado",
          "draft_hash" in ComentariosBody.model_fields
          and ComentariosBody.model_fields["draft_hash"].is_required())

    # ── 8 · el camino real del grafo, si hay base de datos ────────────────────
    print("-- camino real del grafo (LLM mockeado) --")
    if not pruebas_con_db():
        print("     (tramo pendiente: vuelve a correr el gate con la base encendida)")

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
