"""Autocontrol de los fixtures contra el código determinista que YA existe.

No prueba la cadena: prueba que los dobles y la custodia de prueba son VÁLIDOS para los validadores
congelados de hoy (custodia, `validar_pasada1`, `validar_pasada2`, tercer voto, voto de cobertura,
`validar_conjunto`, `verificar_acreditacion`, `validar_circuito`). Si esto falla, el requisito «F17
da `aprueba`» sería inalcanzable por culpa de los fixtures y no de la implementación. Es el único
bloque que puede salir verde hoy por diseño, y su verde es legítimo: no toca ninguna pieza nueva.
"""
from __future__ import annotations

import inspect
from fractions import Fraction
from typing import Callable

from . import custodia_falsa as CF
from . import dobles, entorno

LLAVE = b"llave-de-autocontrol-0123456789abcdef"


def paquete_de_resultado(caso, res: dict, jurisdicciones=()):
    from mia.eval.banco04 import ceguera
    mt = res["material_turno"]
    mapa = [{"n": d["n"], "pieza_id": d["document_id"], "fragmento_id": d["id"], "texto": d["content"]}
            for d in mt["documents_map"]]
    piezas: dict = {}
    for d in mt["documents_map"]:
        piezas.setdefault(d["document_id"], []).append(d["content"])
    expediente = [{"pieza_id": k, "nombre": k, "texto": "\n".join(v)} for k, v in piezas.items()]
    return ceguera.preparar_candidato(
        llave=LLAVE, etiqueta_version="autocontrol", case_id=caso.id, repeticion=1,
        diagnostico=res["diagnosis_full"], borrador=res["draft_full"], mensaje_abogado=caso.message,
        expediente=expediente, mapa_docs=mapa, fuentes_corpus=list(mt.get("research_sources") or []),
        aviso_alcance=None, jurisdicciones_configuradas=list(jurisdicciones))


def correr(check: Callable[[str, bool], None]) -> None:
    from mia.eval.banco04 import evaluador_congelado as EV
    from mia.eval.banco04 import jueces, protocolo as P
    import banco04_validar_jueces as vj

    print("\n0 · AUTOCONTROL de los fixtures (legítimamente verde: no toca piezas nuevas)")
    visibles = CF.casos_visibles()
    check("0.1 los 13 casos visibles del protocolo se cargan",
          sorted(c.id for c in visibles) == sorted(P.CASOS_A_CANONICOS + P.CASOS_A_RIESGO
                                                     + P.CASOS_A_VOLUMINOSO + P.CASOS_C_PEQUENOS))
    carpeta = entorno.nueva_carpeta("autocontrol") / "custodia"
    cus = CF.CustodiaPrueba(carpeta, casos_visibles=visibles)
    with cus.abrir() as c:
        casos_c = c.casos()
        jur = c.jurisdicciones()
        claves = {x.id: c.clave(x.id) for x in [*casos_c, *visibles]}
        reservado = c.mutaciones("reservado")
        ajuste = c.mutaciones("ajuste")
        sem = c.semilla_hmac()
    check("0.2 la custodia de prueba abre con el cargador REAL (DPAPI real) y entrega 4 custodiados, "
          "17 claves, ajuste, reservado y semilla",
          [x.id for x in casos_c] == list(CF.IDS_CUSTODIADOS) and len(claves) == 17
          and jur == CF.JURISDICCIONES_CUSTODIADOS and sem == bytes.fromhex(CF.SEMILLA_HEX))
    todos = [*visibles, *casos_c]
    mundo = dobles.Mundo(entorno.FIXTURES / "__init__.py")
    malos_cita, malos_p1, malos_p2 = [], [], []
    for caso in todos:
        res = dobles.resultado_sintetico(caso, 1, mundo.guion)
        texto = f"{res['diagnosis_full']}\n{res['draft_full']}"
        if EV.scan_citations(texto, EV.compile_patterns(None)):
            malos_cita.append(caso.id)
        paq, _priv = paquete_de_resultado(caso, res, jur.get(caso.id, []))
        mat = jueces.Material.desde_paquete(paq, partes=None)
        rn = dobles.runners()
        r1 = jueces.pasada1(paq, mat, opus=rn["opus"], codex=rn["codex"])
        if r1.get("estado") != "evaluada" or r1.get("afirmaciones_sin_respaldo", 0):
            malos_p1.append((caso.id, r1.get("estado"), r1.get("afirmaciones_sin_respaldo")))
        r2 = jueces.pasada2(paq, claves[caso.id], runner=rn["opus"])
        if r2.get("estado") != "evaluada":
            malos_p2.append(caso.id)
    check("0.3 el texto del mundo no trae ninguna cita (no dispara la señal de fuga)", not malos_cita)
    check(f"0.4 la pasada 1 de los jueces dobles honestos es VÁLIDA y sin defectos en los 17 casos "
          f"{malos_p1[:3]}", not malos_p1)
    check(f"0.5 la pasada 2 del doble es VÁLIDA contra la clave de prueba en los 17 casos {malos_p2[:3]}",
          not malos_p2)
    # forzar un defecto en los dos jueces → la pasada 1 lo confirma (lo usa S01)
    caso = visibles[0]
    frase = CF.plan_de_caso(caso)["hechos"][0]["frase"]
    res = dobles.resultado_sintetico(caso, 1, mundo.guion)
    paq, _ = paquete_de_resultado(caso, res)
    mat = jueces.Material.desde_paquete(paq, partes=None)
    rn = dobles.runners(opus=dobles.Reglas(forzar_defecto=frozenset({frase[:20]})),
                        codex=dobles.Reglas(forzar_defecto=frozenset({frase[:20]})))
    r1 = jueces.pasada1(paq, mat, opus=rn["opus"], codex=rn["codex"])
    check("0.6 con los dos dobles forzando un defecto, la pasada 1 lo confirma (≥ 1 sin respaldo)",
          r1.get("estado") == "evaluada" and (r1.get("afirmaciones_sin_respaldo") or 0) >= 1)
    # solo Codex marca; el tercer voto decide sin_respaldo → confirmado (S02)
    rn = dobles.runners(opus=dobles.Reglas(tercer_voto="sin_respaldo"),
                        codex=dobles.Reglas(forzar_defecto=frozenset({frase[:20]})))
    r1 = jueces.pasada1(paq, mat, opus=rn["opus"], codex=rn["codex"])
    check("0.7 solo Codex marca y el tercer voto confirma → 1 sin respaldo",
          r1.get("estado") == "evaluada" and (r1.get("afirmaciones_sin_respaldo") or 0) >= 1
          and bool(r1.get("votos_tercero")))
    # tercer voto inválido dos veces → no_evaluada_tercer_voto (S03)
    rn = dobles.runners(opus=dobles.Reglas(tercer_voto="invalido"),
                        codex=dobles.Reglas(forzar_defecto=frozenset({frase[:20]})))
    r1 = jueces.pasada1(paq, mat, opus=rn["opus"], codex=rn["codex"])
    check("0.8 el tercer voto inválido dos veces deja la salida `no_evaluada_tercer_voto`",
          r1.get("estado") == "no_evaluada_tercer_voto")
    # Opus inválido → no_evaluada_opus (S14)
    rn = dobles.runners(opus=dobles.Reglas(p1_invalido=True))
    r1 = jueces.pasada1(paq, mat, opus=rn["opus"], codex=rn["codex"])
    check("0.9 Opus estructuralmente inválido dos veces → `no_evaluada_opus`",
          r1.get("estado") == "no_evaluada_opus")
    # S16 · fuente de un ordenamiento no configurado: describirla vale; usarla como aplicable, no
    g16 = dobles.Guion(fuente_no_configurada={caso.id})
    res16 = dobles.resultado_sintetico(caso, 1, g16)
    paq16, _ = paquete_de_resultado(caso, res16)
    mat16 = jueces.Material.desde_paquete(paq16, partes=None)
    r_ok = jueces.pasada1(paq16, mat16, **dobles.runners())
    r_ko = jueces.pasada1(paq16, mat16, **dobles.runners(opus=dobles.Reglas(uso_aplicable_no_configurado=True),
                                                        codex=dobles.Reglas(uso_aplicable_no_configurado=True)))
    check("0.18 con una fuente `co` en un despacho sin ordenamiento, el doble honesto la respalda como "
          "`descriptivo` (válido) y con `uso_fuente=aplicable` el validador la rechaza (base de S16)",
          r_ok.get("estado") == "evaluada" and not r_ok.get("afirmaciones_sin_respaldo")
          and r_ko.get("estado") == "no_evaluada_opus")
    # validación de los conjuntos y de la acreditación v1.3
    try:
        items_r = vj.validar_conjunto(reservado, otro=ajuste)
        ok_conj = len(items_r) == len(reservado["items"])
    except Exception as exc:  # noqa: BLE001
        ok_conj, items_r = False, []
        print("     ", type(exc).__name__, exc)
    check("0.10 el reservado y el ajuste de prueba pasan `validar_conjunto` (≥30/≥30, ≥10 C12, disjuntos)",
          ok_conj)
    acr = cus.acreditacion_v13(jueces.hash_evaluador()["combinado"])
    import json
    v = vj.verificar_acreditacion(acr, manifiesto=json.loads(cus.ruta_manifiesto.read_text(encoding="utf-8")),
                                  items=items_r, hash_evaluador=jueces.hash_evaluador())
    check(f"0.11 la acreditación v1.3 de prueba verifica ({v['motivos'][:2]})", v["ok"])
    # el circuito con los jueces honestos es utilizable; ciego y kappa invertido no lo son (S12, S13)
    def circuito(rn):
        por_item = [vj.evaluar_item(it, opus=rn["opus"], codex=rn["codex"], llave=LLAVE) for it in items_r]
        res = [x for it in por_item for x in it["verdades"]]
        pares = [p for it in por_item if it["estado"] == "evaluada" for p in it["pares_kappa"]]
        disc = sum(int(it.get("discordancias") or 0) for it in por_item)
        kw = {}
        # §8.6 bis (v8): `consumo_certificable` sale de la habilitación; si la firma conserva el
        # parámetro `consumo` (código de hoy), se le pasa un consumo certificable para aislar la calidad.
        if "consumo" in inspect.signature(vj.evaluar_exigencias).parameters:
            kw["consumo"] = {"cota_calculable": True, "resumen": {}}
        return vj.evaluar_exigencias(res, tipo="reservado", discordancias=disc, pares_kappa=pares,
                                     acreditacion=v, **kw)

    out = circuito(dobles.runners())
    fallan = {k: e for k, e in out["exigencias"].items() if not e["cumple"]}
    check(f"0.12 circuito con jueces dobles honestos sobre el reservado de prueba: utilizable {fallan}",
          bool(out.get("circuito_utilizable")))
    out_c = circuito(dobles.runners(opus=dobles.Reglas(ciego=True), codex=dobles.Reglas(ciego=True)))
    check("0.13 con jueces que no ven los defectos la sensibilidad cae < 0,95 (base de S12)",
          out_c["circuito_utilizable"] is False
          and out_c["exigencias"]["sensibilidad_final"]["cumple"] is False)
    out_k = circuito(dobles.runners(codex=dobles.Reglas(invertir=True)))
    check(f"0.14 con Codex invertido el kappa del reservado cae < 0,6 (base de S13; "
          f"kappa={out_k['exigencias']['kappa']['valor']})",
          out_k["circuito_utilizable"] is False and out_k["exigencias"]["kappa"]["cumple"] is False)

    # los dobles de los CLI son compatibles con el producto REAL (call_llm con la política fija)
    import subprocess as _sp
    import types
    from pathlib import Path
    import run_banco04 as R
    from mia.agent import codex_subscription_llm as cx, llm, subscription_llm as sl
    from mia.metrics import usage
    from . import firmas
    cl, co = dobles.ClaudeCLIDoble(), dobles.CodexCLIDoble()
    previo = (sl.subprocess, cx.subprocess, sl._resolve_exe, cx._resolve_exe,
              cx._local_membership_allowed, llm.resolve_fallback_chain)

    def proxy(run):
        return types.SimpleNamespace(run=run, TimeoutExpired=_sp.TimeoutExpired,
                                     CompletedProcess=_sp.CompletedProcess)

    resp: dict = {}
    escalada = getattr(llm, "QUALITY_ESCALATION_EXCEPTIONAL", "exceptional")
    try:
        sl.subprocess, cx.subprocess = proxy(cl), proxy(co)
        sl._resolve_exe = lambda: firmas.EXE_CLAUDE
        cx._resolve_exe = lambda: Path(firmas.EXE_CODEX)
        cx._local_membership_allowed = lambda: True
        llm.resolve_fallback_chain = dobles.cadena_con_codex()
        with R.politica_fija(llm):
            tok = usage.set_node("analisis")
            try:
                resp["claude"] = llm.call_llm([{"role": "user", "content": "[[BANCO04 caso=x|rep=1|nodo=a]] h"}],
                                              task="legal_analysis")
                resp["codex"] = llm.call_llm([{"role": "user", "content": "h"}], task="legal_research")
                resp["escalada"] = llm.call_llm([{"role": "user", "content": "h"}], task="legal_analysis",
                                                quality_escalation=escalada)
            finally:
                usage.reset_node(tok)
    except Exception as exc:  # noqa: BLE001
        print("     ", type(exc).__name__, exc)
    finally:
        (sl.subprocess, cx.subprocess, sl._resolve_exe, cx._resolve_exe,
         cx._local_membership_allowed, llm.resolve_fallback_chain) = previo
    e_normal = getattr(resp.get("claude"), "mia_effort", None)
    e_escalada = getattr(resp.get("escalada"), "mia_effort", None)
    check("0.15 el doble del CLI de Claude atraviesa el `call_llm` real (alias opus) sin red ni base",
          bool(e_normal) and getattr(getattr(resp.get("claude"), "usage", None), "completion_tokens", 0) == 40)
    check("0.16 con el doble de la cadena, `legal_research` sale por `cli-codex` y su doble responde",
          len(co.llamadas) == 1 and getattr(getattr(resp.get("codex"), "usage", None), "total_tokens", 0) == 120)
    check("0.17 la escalada excepcional produce OTRA firma de comando del mismo alias (base de E2E-16)",
          bool(e_escalada) and e_escalada != e_normal
          and len({firmas.firma(c["cmd"])["sha256"] for c in cl.llamadas}) == 2)

    # v9 · dobles de consumo exacto, de tiempo agotado y registro del `env` (E2E-19)
    cl2 = dobles.ClaudeCLIDoble(total_exacto=lambda c, r, n: 60 if n == "exacto" else None,
                                timeout_si=lambda c, r, n: n == "timeout",
                                omitir_salida_si=lambda c, r, n: n == "sin_salida")
    previo = (sl.subprocess, sl._resolve_exe)
    res2: dict = {}
    try:
        sl.subprocess = proxy(cl2)
        sl._resolve_exe = lambda: firmas.EXE_CLAUDE
        with R.politica_fija(llm):
            res2["exacto"] = llm.call_llm([{"role": "user", "content": "[[BANCO04 caso=x|rep=1|nodo=exacto]] h"}],
                                          task="legal_draft")
            try:
                llm.call_llm([{"role": "user", "content": "[[BANCO04 caso=x|rep=1|nodo=timeout]] h"}],
                             task="legal_draft")
                res2["timeout"] = None
            except Exception as exc:  # noqa: BLE001
                res2["timeout"] = type(exc).__name__
            res2["sin_salida"] = llm.call_llm([{"role": "user", "content": "[[BANCO04 caso=x|rep=1|nodo=sin_salida]] h"}],
                                              task="legal_draft")
    except Exception as exc:  # noqa: BLE001
        print("     ", type(exc).__name__, exc)
    finally:
        sl.subprocess, sl._resolve_exe = previo
    check("0.19 `total_exacto` fija el total de la llamada (60) a través del `call_llm` real",
          getattr(getattr(res2.get("exacto"), "usage", None), "total_tokens", None) == 60)
    check(f"0.20 `timeout_si` hace que el `call_llm` real falle por tiempo ({res2.get('timeout')}) y "
          "`omitir_salida_si` devuelve una respuesta sin `output_tokens` (base de E2E-19.1 y 19.7)",
          bool(res2.get("timeout")) and res2.get("sin_salida") is not None
          and getattr(res2["sin_salida"].usage, "completion_tokens", None) == 0)
    esperado = sl._sanitized_env()
    check("0.21 el doble registra el `env` que el producto pasa a `subprocess.run` (= `_sanitized_env()`)",
          len(cl2.envs) == 3 and all(e == esperado for e in cl2.envs))
