"""Gates de la INFRAESTRUCTURA DE PRODUCCIÓN del banco 0.4 (§10.2 ítem 13: P6, P10, P11, runner).

Sin DB, sin modelo real, sin tocar 55432 ni el clúster sintético: todo corre con dobles y con
directorios temporales FUERA del repo. Exit 0 = PASS · 1 = FAIL.

Qué cubre (cada check se puede poner rojo; la mutación está documentada en su bloque):
  A · ítem 5  — intento fallido: `consumo_conocido=False`, entrada estimada, cota de salida,
                tokens CONOCIDOS intactos; cota incalculable → None (P10).
  B · ítem 4  — `run_case` persiste material del turno, SOUL, versión del CLI, intentos fallidos,
                y una instrumentación rota NO tumba la corrida.
  C · runner  — rechaza 55432 y el `.env` del repo (incluida la salida por CI), `MIA_HOME` de la
                instalación, política fija, clasificación de fallos, idempotencia, reintento
                de infraestructura, R de la piloto solo con consumo, submuestra de aprobaciones.
  D · P10/P11 — sin cota el techo es no certificable; el contador alcanza el techo, suspende y
                publica «incompleto — no certificable»; la reserva del juicio no se invade.
  E · P6      — custodia fail-closed y nada de custodia bajo el repo (ver `custodia.py`).

    .venv\\Scripts\\python.exe execution\\test_banco04_produccion.py
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
import logging  # noqa: E402

logging.disable(logging.CRITICAL)   # los avisos de gasto no gobernado del guardián no son el resultado

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _tmp(prefix: str) -> Path:
    """Directorio desechable en el temporal del SISTEMA (nunca dentro del repo)."""
    from _tmp_desechable import tmpdir_desechable
    return tmpdir_desechable(prefix, repo_root=ROOT)


import run_banco04 as rb  # noqa: E402  (no importa `mia`: solo isolated_test_env)


# ═════════════════════════════════════════════════════════════════════════════
# A · ÍTEM 5 — intentos fallidos en spend_guard
# ═════════════════════════════════════════════════════════════════════════════
def bloque_a(tmp: Path) -> None:
    print("\n-- A · ítem 5: intento fallido = consumo desconocido con cota superior --")
    from mia.eval import spend_guard
    from mia.memory.tokens import estimate_tokens

    spend_guard.ensure_installed()

    def guard(nombre: str):
        return spend_guard.EvalSpendGuard(
            run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0,
            closeout_reserve_usd=0.0, session_id="s-banco04", ledger_path=tmp / f"{nombre}.json")

    class Boom(RuntimeError):
        pass

    def invocar(g, kwargs, *, exc=None):
        prev = spend_guard._original_invoke

        def falso(client, alias, kw, task=None, *a):
            raise (exc or Boom("el CLI murió por timeout"))

        spend_guard._original_invoke = falso
        try:
            with g.activate(), g.case("caso-a"):
                try:
                    spend_guard._guarded_invoke(None, "claude-sonnet", kwargs)
                except BaseException as e:  # noqa: BLE001
                    return e
        finally:
            spend_guard._original_invoke = prev
        return None

    texto = "x" * 4000
    g = guard("a1")
    err = invocar(g, {"messages": [{"role": "user", "content": texto}], "max_tokens": 1000})
    reg = (getattr(g, "intentos_fallidos", None) or [{}])[0]
    # MUTACIÓN: borrar el bloque de registro del `except` de `_guarded_invoke` → cae a-1.
    check("a-1 · la excepción original SIGUE saliendo y el fallo queda registrado en el guardián",
          isinstance(err, Boom) and len(getattr(g, "intentos_fallidos", []) or []) == 1)
    check("a-2 · consumo_conocido=False, no 0 (§5.5)", reg.get("consumo_conocido") is False)
    # MUTACIÓN: poner `entrada_est = 0` → cae a-3.
    check("a-3 · entrada estimada con memory.tokens.estimate_tokens sobre el texto",
          reg.get("tokens_entrada_estimados") == estimate_tokens(texto))
    # MUTACIÓN: usar `kwargs.get('max_tokens', 0)` o quitar la cota → cae a-4.
    check("a-4 · cota de salida = el max_tokens acotado de la llamada",
          reg.get("cota_salida") == 1000
          and reg.get("tokens_cota_superior") == estimate_tokens(texto) + 1000)
    uc = g.cases[0].as_dict()
    # MUTACIÓN: meter lo estimado en `note_call` (prompt_tokens) → cae a-5 (se mezclaría conocido
    # con estimado y las ~160 aserciones de test_eval_spend_guard).
    check("a-5 · los tokens CONOCIDOS siguen en 0: lo estimado NO se mezcla con lo medido",
          uc["total_tokens"] == 0 and uc["prompt_tokens"] == 0)
    check("a-6 · también queda en el CaseUsage del caso (lo que lee run_case)",
          len(getattr(g.cases[0], "intentos_fallidos", []) or []) == 1)

    # Sin max_tokens el guardián pone el techo del banco: la cota nunca queda vacía.
    g = guard("a2")
    invocar(g, {"messages": [{"role": "user", "content": "hola"}]})
    reg = (g.intentos_fallidos or [{}])[0]
    check("a-7 · sin max_tokens, la cota es el techo del banco (EVAL_MAX_OUTPUT_TOKENS)",
          reg.get("cota_salida") == spend_guard.EVAL_MAX_OUTPUT_TOKENS)

    # Contenido en BLOQUES (conversión de caché): se cuenta el texto, no el repr del contenedor.
    g = guard("a3")
    bloques = [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]
    invocar(g, {"messages": [{"role": "system", "content": bloques}], "max_tokens": 10})
    reg = (g.intentos_fallidos or [{}])[0]
    # MUTACIÓN: usar `str(content)` → la cifra sube con llaves y metadatos y cae a-8.
    check("a-8 · el contenido en bloques se cuenta por su texto (nunca str(content))",
          reg.get("tokens_entrada_estimados") == estimate_tokens(texto))

    # Estimación imposible → cota None (NO cero): materia prima de P10.
    g = guard("a4")
    invocar(g, {"messages": ["no soy un dict"], "max_tokens": 10})
    reg = (g.intentos_fallidos or [{}])[0]
    # MUTACIÓN: en el `except` interno poner `entrada_est, cota_salida = 0, 0` → cae a-9 y a-10.
    check("a-9 · si la cota no se puede calcular queda None, no un cero tranquilizador",
          reg.get("tokens_cota_superior") is None and reg.get("consumo_conocido") is False)
    tot, calculable = rb.cota_de_fallidos(g.intentos_fallidos)
    check("a-10 · y el techo con ese intento es NO calculable (P10)", calculable is False)

    # Una excepción que NO es del proveedor tampoco se traga ni se enmascara.
    g = guard("a5")
    err = invocar(g, {"messages": [{"role": "user", "content": "x"}], "max_tokens": 5},
                  exc=KeyboardInterrupt())
    check("a-11 · una BaseException del intento se relanza intacta y también se registra",
          isinstance(err, KeyboardInterrupt) and len(g.intentos_fallidos or []) == 1)

    # No-alcanzado: se distingue, pero SIGUE siendo consumo_conocido=False (§5.5 literal).
    class SinConexion(ConnectionRefusedError):
        pass

    g = guard("a6")
    invocar(g, {"messages": [{"role": "user", "content": "x"}], "max_tokens": 5}, exc=SinConexion())
    reg = (g.intentos_fallidos or [{}])[0]
    check("a-12 · `proveedor_no_alcanzado` es un dato aparte; consumo_conocido sigue en False",
          reg.get("consumo_conocido") is False and "proveedor_no_alcanzado" in reg)


# ═════════════════════════════════════════════════════════════════════════════
# B · ÍTEM 4 — instrumentación de run_case (con grafo falso, sin DB)
# ═════════════════════════════════════════════════════════════════════════════
def bloque_b(tmp: Path) -> None:
    print("\n-- B · ítem 4: run_case persiste el material del turno --")
    from mia import config
    from mia.eval import cases as cases_mod
    from mia.eval import harness, spend_guard
    from mia.onboarding import soul_interview

    spend_guard.ensure_installed()
    docs = [{"id": "c1", "content": "Cláusula 7: el plazo es de 30 días.", "filename": "contrato.txt",
             "document_id": "d1", "ord": 3, "folio_ancla": "f. 4"},
            {"id": "c2", "content": "Adenda: el plazo pasa a 45 días.", "filename": "adenda.txt",
             "document_id": "d2", "ord": 0, "folio_ancla": None}]
    caso = cases_mod.GoldenCase(id="t-b", title="t", message="hola", synthetic=True)

    class FakeGraph:
        def __init__(self, values, falla_llamada=False):
            self.values, self.falla = values, falla_llamada

        async def astream(self, inp, cfg, stream_mode=None):
            if self.falla:
                try:
                    spend_guard._guarded_invoke(
                        None, "claude-sonnet", {"messages": [{"role": "user", "content": "z" * 400}],
                                                "max_tokens": 50})
                except Exception:  # noqa: BLE001
                    pass
            yield {}

        async def aget_state(self, cfg):
            return SimpleNamespace(values=self.values)

    @asynccontextmanager
    async def cp():
        yield object()

    async def sembrar(tenant, c):
        return "m-1"

    def valores(**extra):
        md = {"research_sources": [{"fuente": "ley 1", "obj": {1, 2}}], "retrieved": 2,
              "alcance_lectura": {"leidos": 2, "total": 40}, "diagnosis": "Diagnóstico breve."}
        v = {"documents": docs, "draft": "Borrador breve.", "metadata": md}
        v.update(extra)
        return v

    guard = spend_guard.EvalSpendGuard(
        run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0, closeout_reserve_usd=0.0,
        session_id="s-banco04-b", ledger_path=tmp / "b.json")
    orig = (harness._seed_case_matter, harness.open_checkpointer, harness.build_matter_graph,
            config.MIA_HOME, spend_guard._original_invoke)
    entorno = {k: os.environ.get(k) for k in ("MIA_EVAL_PERSIST_FULL", "MIA_EVAL_CLI_VERSION")}

    async def correr(graph, *, completo: bool, cli: str | None, soul: bytes | None):
        harness._seed_case_matter, harness.open_checkpointer = sembrar, cp
        harness.build_matter_graph = lambda checkpointer: graph
        config.MIA_HOME = tmp / "home-b"
        ruta_soul = soul_interview.soul_path("t-1")
        ruta_soul.parent.mkdir(parents=True, exist_ok=True)
        if ruta_soul.exists():
            ruta_soul.unlink()
        if soul is not None:
            ruta_soul.write_bytes(soul)
        for k, v in (("MIA_EVAL_PERSIST_FULL", "1" if completo else None),
                     ("MIA_EVAL_CLI_VERSION", cli)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        spend_guard._original_invoke = lambda c, a, kw, t=None, *x: (_ for _ in ()).throw(
            RuntimeError("timeout del CLI"))
        with guard.activate():
            return await harness.run_case("t-1", caso, tenant_allow_real=False)

    try:
        soul_bytes = "SOUL de plantilla\n".encode("utf-8")
        r = asyncio.run(correr(FakeGraph(valores(), falla_llamada=True), completo=True,
                               cli="claude 2.1.99", soul=soul_bytes))
        mt = r.get("material_turno") or {}
        mapa = mt.get("documents_map") or []
        # MUTACIÓN: dejar `mapa` vacío en run_case → caen b-1 y b-2.
        check("b-1 · el mapa [doc n] sale en orden de sellado con pieza, fragmento y ancla",
              [m.get("n") for m in mapa] == [1, 2]
              and [m.get("document_id") for m in mapa] == ["d1", "d2"]
              and [m.get("ord") for m in mapa] == [3, 0] and mapa[0].get("folio_ancla") == "f. 4")
        check("b-2 · cada fragmento lleva el sha256 de su contenido",
              mapa and mapa[0]["sha256"] == hashlib.sha256(docs[0]["content"].encode()).hexdigest())
        # MUTACIÓN: persistir `content` siempre (o nunca) → cae b-3 o b-4.
        check("b-3 · con MIA_EVAL_PERSIST_FULL=1 viaja el contenido completo",
              mapa and mapa[0].get("content") == docs[0]["content"])
        check("b-4 · el mapa NO se rotula 'lo que entró al prompt': declara que es la lista de "
              "intake y que pudo recortarse",
              mt.get("recorte_posible_por_contexto") is True and "intake" in mt.get("documents_origen", ""))
        check("b-5 · research_sources y alcance_lectura (del metadata) viajan en el resultado",
              mt.get("alcance_lectura") == {"leidos": 2, "total": 40}
              and (mt.get("research_sources") or [{}])[0].get("fuente") == "ley 1")
        # MUTACIÓN: hashear el texto en vez de los BYTES, o devolver None → cae b-6.
        check("b-6 · soul_sha256 = sha256 de los bytes del SOUL del despacho",
              mt.get("soul_sha256") == hashlib.sha256(soul_bytes).hexdigest())
        check("b-7 · la versión del CLI se registra (la fija el runner por entorno)",
              mt.get("cli_version") == "claude 2.1.99")
        # MUTACIÓN: no copiar `intentos_fallidos` del CaseUsage → cae b-8.
        fall = r.get("intentos_fallidos") or []
        check("b-8 · los intentos fallidos del turno salen con su cota y consumo_conocido=False",
              len(fall) == 1 and fall[0]["consumo_conocido"] is False
              and fall[0]["tokens_cota_superior"] is not None)
        # Persistencia real: el resultado debe poder ir a disco sin romper.
        try:
            d = harness.persist_report({"run_id": "b", "cases": [r]}, base_dir=str(tmp / "evr"))
            leido = json.loads((d / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0])
            ok_disco = leido["material_turno"]["documents_map"][1]["n"] == 2
        except Exception:  # noqa: BLE001
            ok_disco = False
        check("b-9 · el resultado con las claves nuevas se persiste y se relee", ok_disco)
        check("b-10 · conducta existente intacta: sigue saliendo `score`, `usage` y el preview",
              "score" in r and "usage" in r and r.get("draft_preview") == "Borrador breve.")

        # Sin FULL ni CLI ni SOUL: queda el sha256 pero NO el contenido; SOUL ausente = None.
        r2 = asyncio.run(correr(FakeGraph(valores()), completo=False, cli=None, soul=None))
        mt2 = r2["material_turno"]
        check("b-11 · sin PERSIST_FULL no engorda los crudos: hay sha256, no hay content",
              "content" not in mt2["documents_map"][0] and mt2["documents_map"][0]["sha256"])
        check("b-12 · sin SOUL → soul_sha256 None; sin CLI → cli_version None",
              mt2["soul_sha256"] is None and mt2["cli_version"] is None)
        check("b-13 · sin fallos no inventa intentos fallidos", r2.get("intentos_fallidos") == [])

        # Instrumentación rota: el turno SIGUE y el fallo queda DECLARADO.
        r3 = asyncio.run(correr(FakeGraph(valores(documents=12345)), completo=True, cli="v",
                                soul=soul_bytes))
        # MUTACIÓN: quitar el try/except del bloque → run_case revienta y cae b-14.
        check("b-14 · una instrumentación que falla NO tumba la corrida y se declara",
              r3.get("score") is not None
              and any("material" in e for e in r3["material_turno"]["errores_instrumentacion"]))
    finally:
        (harness._seed_case_matter, harness.open_checkpointer, harness.build_matter_graph,
         config.MIA_HOME, spend_guard._original_invoke) = orig
        for k, v in entorno.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═════════════════════════════════════════════════════════════════════════════
# C · RUNNER — aislamiento, política, clasificación, idempotencia, piloto
# ═════════════════════════════════════════════════════════════════════════════
def _entorno_aislado(tmp: Path, nombre: str, **cambios) -> tuple[dict, Path]:
    """Un `MIA_TEST_ENV_FILE` válido (fuera del repo) y el `environ` que lo apunta."""
    valores = {"PG_HOST": "127.0.0.1", "PG_PORT": "55448", "PG_DB": "mia_banco04",
               "PG_PASSWORD": "x", "PG_APP_PASSWORD": "y", "MIA_HOME": str(tmp / f"home-{nombre}"),
               "DATABASE_URL": "postgresql://mia_app:y@127.0.0.1:55448/mia_banco04"}
    valores.update(cambios)
    ruta = tmp / f"{nombre}.env"
    ruta.write_text("\n".join(f"{k}={v}" for k, v in valores.items() if v is not None) + "\n",
                    encoding="utf-8")
    return valores, ruta


def _rechaza(fn) -> bool:
    try:
        fn()
    except rb.AislamientoError:
        return True
    return False


def bloque_c_aislamiento(tmp: Path) -> None:
    print("\n-- C1 · el runner rechaza 55432, el .env del repo y la instalación --")
    repo = tmp / "repo"
    repo.mkdir()
    (repo / ".env").write_text("PG_PORT=55432\nMIA_HOME=.\\mia-data\n", encoding="utf-8")
    _, ok_env = _entorno_aislado(tmp, "ok")
    amb = {"MIA_TEST_ENV_FILE": str(ok_env)}

    def verif(env, **kw):
        return rb.verificar_aislamiento(env, repo_root=repo, **kw)

    v = verif(amb)
    check("c-1 · un entorno aislado válido (puerto ≠ 55432, host local, MIA_HOME ajeno) pasa",
          str(v["PG_PORT"]) == "55448" and Path(v["MIA_HOME"]).name == "home-ok")
    # MUTACIÓN: quitar el `if not ruta: raise` → cae c-2.
    check("c-2 · sin MIA_TEST_ENV_FILE no arranca", _rechaza(lambda: verif({})))
    check("c-3 · un MIA_TEST_ENV_FILE inexistente no arranca",
          _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(tmp / "no-existe.env")})))
    # MUTACIÓN: quitar la comparación con `<repo>/.env` → cae c-4. El .env del repo de este check
    # trae un contenido que, por sí solo, PASARÍA todas las demás guardas (puerto ajeno, host
    # local, MIA_HOME ajeno): lo único que lo para es que ES el archivo de la instalación.
    repo_b = tmp / "repo-b"
    repo_b.mkdir()
    (repo_b / ".env").write_text("\n".join(["PG_HOST=127.0.0.1", "PG_PORT=55448",
                                            "DATABASE_URL=postgresql://u:p@127.0.0.1:55448/m", ""]),
                                 encoding="utf-8")
    check("c-4 · rechaza el .env DEL REPOSITORIO como entorno aislado (aunque su contenido parezca válido)",
          _rechaza(lambda: rb.verificar_aislamiento(
              {"MIA_TEST_ENV_FILE": str(repo_b / ".env"), "MIA_HOME": str(tmp / "h-ajeno")},
              repo_root=repo_b)))
    _, e55 = _entorno_aislado(tmp, "p55432", PG_PORT="55432",
                              DATABASE_URL="postgresql://u:p@127.0.0.1:55432/m")
    # MUTACIÓN: quitar el chequeo explícito del puerto Y la limpieza de CI → cae c-5/c-6.
    check("c-5 · rechaza el puerto 55432", _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(e55)})))
    check("c-6 · rechaza 55432 aunque venga CI=true (la salida de `select` por CI no existe aquí)",
          _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(e55), "CI": "true",
                                  "GITHUB_ACTIONS": "true", "PG_HOST": "x", "PG_PORT": "5432",
                                  "PG_DB": "d", "PG_PASSWORD": "p", "PG_APP_PASSWORD": "q"})))

    # La comprobación PROPIA del puerto, aislada de `select` (si `select` fuese permisiva, la
    # guarda del runner debe seguir en pie).
    original = rb.isolated_test_env.select
    rb.isolated_test_env.select = lambda environ, read_file=None: {
        "PG_HOST": "127.0.0.1", "PG_PORT": "55432", "MIA_HOME": str(tmp / "h-x"),
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:55432/m"}
    try:
        # MUTACIÓN: borrar `if puerto == PUERTO_INSTALADO: raise` → cae c-7.
        check("c-7 · el chequeo del puerto es PROPIO: aun con un `select` permisivo se rechaza 55432",
              _rechaza(lambda: verif(amb)))
    finally:
        rb.isolated_test_env.select = original
    _, ehost = _entorno_aislado(tmp, "host", PG_HOST="db.ejemplo.com")
    check("c-8 · rechaza un host que no sea local", _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(ehost)})))
    _, esinhome = _entorno_aislado(tmp, "sinhome", MIA_HOME=None)
    check("c-9 · sin MIA_HOME declarado no arranca",
          _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(esinhome)})))
    repo_c = tmp / "repo-c"            # sin .env: lo único que define la instalación es mia-data
    repo_c.mkdir()
    _, einst = _entorno_aislado(tmp, "inst", MIA_HOME=str(repo_c / "mia-data"))
    # MUTACIÓN: no comparar con `repo/mia-data` → cae c-10.
    check("c-10 · rechaza un MIA_HOME que sea el de la instalación (default <repo>/mia-data)",
          _rechaza(lambda: rb.verificar_aislamiento({"MIA_TEST_ENV_FILE": str(einst)}, repo_root=repo_c)))
    (repo / ".env").write_text("MIA_HOME=D:\\datos\\instalada\n", encoding="utf-8")
    _, einst2 = _entorno_aislado(tmp, "inst2", MIA_HOME="D:\\datos\\instalada")
    check("c-11 · rechaza el MIA_HOME que declara el .env del repo",
          _rechaza(lambda: verif({"MIA_TEST_ENV_FILE": str(einst2)})))
    check("c-12 · la salida cruda no puede ir bajo el repo",
          _rechaza(lambda: rb.verificar_salida_fuera_del_repo(repo / "runs", repo))
          and rb.verificar_salida_fuera_del_repo(tmp / "fuera", repo))

    # Fin a fin por `main`: el rechazo sale con código 3 y NO llega a tocar nada.
    guardado = {k: os.environ.get(k) for k in ("MIA_TEST_ENV_FILE", "CI")}
    root_real, rb.ROOT = rb.ROOT, repo       # el .env REAL del repo no se abre ni en el rechazo
    try:
        os.environ.pop("MIA_TEST_ENV_FILE", None)
        base = ["--plan", "--version", "0.4", "--sha", "abc", "--salida", str(tmp / "out-main")]
        check("c-13 · main sin MIA_TEST_ENV_FILE → código 3", rb.main(base) == rb.EXIT_RECHAZADO)
        os.environ["MIA_TEST_ENV_FILE"] = str(repo / ".env")
        check("c-14 · main con el .env del repo → código 3", rb.main(base) == rb.EXIT_RECHAZADO)
        os.environ["MIA_TEST_ENV_FILE"] = str(e55)
        os.environ["CI"] = "true"
        check("c-15 · main con 55432 y CI=true → código 3", rb.main(base) == rb.EXIT_RECHAZADO)
    finally:
        rb.ROOT = root_real
        for k, v in guardado.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    URL = "postgresql://mia_app:y@127.0.0.1:55448/mia_banco04"
    val = {"PG_PORT": "55448", "MIA_HOME": str(tmp / "h"), "DATABASE_URL": URL}
    ok, bad = {"PG_PORT": "55448", "MIA_HOME": str(tmp / "h")}, {"PG_PORT": "55432", "MIA_HOME": str(tmp / "h")}
    try:
        rb.verificar_entorno_cargado(val, bad, tmp / "h", URL)
        post = False
    except rb.AislamientoError:
        post = True
    check("c-16 · tras importar mia, si el puerto vivo cambió (o es 55432) se aborta", post)
    rb.verificar_entorno_cargado(val, ok, tmp / "h", URL)
    # MUTACIÓN: quitar la comparación de config_url en `verificar_entorno_cargado` → cae c-16b.
    check("c-16b · tras importar mia, si config.DATABASE_URL no es la del entorno aislado (la trajo el "
          ".env del repo) se aborta",
          _rechaza(lambda: rb.verificar_entorno_cargado(
              val, ok, tmp / "h", "postgresql://mia_app:y@127.0.0.1:55432/mia"))
          and _rechaza(lambda: rb.verificar_entorno_cargado(val, ok, tmp / "h", None)))
    # DATABASE_URL en el archivo aislado: lo que de verdad abre el pool de `mia`.
    for nom, cambio in (("sinurl", {"DATABASE_URL": None}),
                        ("url55432", {"DATABASE_URL": "postgresql://u:p@127.0.0.1:55432/mia"}),
                        ("urlotro", {"DATABASE_URL": "postgresql://u:p@127.0.0.1:5999/mia"}),
                        ("urlremota", {"DATABASE_URL": "postgresql://u:p@db.ejemplo.com:55448/mia"})):
        _, e = _entorno_aislado(tmp, nom, **cambio)
        # MUTACIÓN: quitar el bloque de DATABASE_URL de `verificar_aislamiento` → caen c-16c..f.
        check(f"c-16{'cdef'[('sinurl','url55432','urlotro','urlremota').index(nom)]} · DATABASE_URL del "
              f"entorno aislado ({nom}) ausente, en 55432, con otro puerto o remota → se rechaza",
              _rechaza(lambda e=e: rb.verificar_aislamiento({"MIA_TEST_ENV_FILE": str(e)},
                                                            repo_root=tmp / "repo")))


class LlmFalso:
    def __init__(self, efectiva="quality_adaptive"):
        self.efectiva, self.actual, self.reseteado = efectiva, "suscripcion", False

    def set_model_policy(self, p):
        prev, self.actual = self.actual, p
        return prev

    def get_model_policy(self):
        return self.efectiva

    def reset_model_policy(self, token):
        self.actual, self.reseteado = token, True


def bloque_c_politica_y_fallos(tmp: Path) -> None:
    print("\n-- C2 · política fija y clasificación de fallos --")
    llm = LlmFalso()
    with rb.politica_fija(llm) as efectiva:
        dentro = (efectiva, llm.actual)
    # MUTACIÓN: fijar otro valor en `politica_fija` (p. ej. "suscripcion") → cae c-17.
    check("c-17 · fija quality_adaptive para la corrida y restaura al salir",
          dentro == ("quality_adaptive", "quality_adaptive") and llm.actual == "suscripcion"
          and llm.reseteado)
    try:
        with rb.politica_fija(LlmFalso(efectiva="suscripcion")):
            ok = False
    except rb.BancoAbortado:
        ok = True
    # MUTACIÓN: quitar la comparación `efectiva != politica` → cae c-18.
    check("c-18 · si la política EFECTIVA no es quality_adaptive, aborta (no se supone)", ok)

    class E(Exception):
        pass

    c = rb.clasificar_fallo
    # MUTACIÓN: invertir `llamadas_modelo + intentos == 0` → caen c-19 y c-20.
    check("c-19 · murió antes de la primera llamada al modelo → infraestructura",
          c(E("boom"), llamadas_modelo=0, intentos_fallidos=0) == "infraestructura")
    check("c-20 · falló DESPUÉS de llamar al modelo → producto (no se reintenta)",
          c(E("boom"), llamadas_modelo=3) == "producto"
          and c(E("boom"), llamadas_modelo=0, intentos_fallidos=1) == "producto")
    check("c-21 · la sesión del CLI expirada → infraestructura aunque hubiera llamadas",
          c(E("Claude session expired, please log in"), llamadas_modelo=2) == "infraestructura")
    # MUTACIÓN: sacar `limite_de_uso` del primer `if` → cae c-22 (se confundiría con infra).
    check("c-22 · un límite de uso del plan NO es infraestructura: es suspensión",
          c(E("usage limit reached"), llamadas_modelo=0) == "limite_de_uso"
          and c(type("X", (Exception,), {"status_code": 429})("x"), llamadas_modelo=1)
          == "limite_de_uso")


class Mundo:
    """Doble del guardián + del modelo: lleva el consumo y decide qué falla."""

    def __init__(self, consumo=1000, *, fallos=None, soul="H"):
        self.tokens, self.calls, self.fallidos, self.sin_registro = 0, 0, [], 0
        self.consumo, self.fallos, self.soul = consumo, dict(fallos or {}), soul
        self.llamadas_a_producir: list[tuple[str, int]] = []
        self.t = 0.0

    def consumo_de(self, caso_id):
        return self.consumo(caso_id) if callable(self.consumo) else self.consumo

    async def producir(self, caso, rep):
        self.llamadas_a_producir.append((caso.id, rep))
        clave = (caso.id, rep, sum(1 for c, r in self.llamadas_a_producir if (c, r) == (caso.id, rep)))
        accion = self.fallos.get(clave) or self.fallos.get((caso.id, rep))
        if accion == "infra":                         # murió ANTES de la primera llamada
            raise RuntimeError("proceso muerto antes de llamar al modelo")
        self.calls += 1
        self.tokens += self.consumo_de(caso.id)
        if accion == "producto":
            self.fallidos.append({"alias": "x", "tokens_entrada_estimados": 10, "cota_salida": 90,
                                  "tokens_cota_superior": 100, "consumo_conocido": False,
                                  "tipo_error": "Boom", "proveedor_no_alcanzado": False})
            raise RuntimeError("el turno falló tras llamar al modelo")
        if accion == "limite":
            raise RuntimeError("usage limit reached")
        if accion == "sin_cota":
            self.fallidos.append({"alias": "x", "tokens_entrada_estimados": None, "cota_salida": None,
                                  "tokens_cota_superior": None, "consumo_conocido": False,
                                  "tipo_error": "Boom", "proveedor_no_alcanzado": False})
        return {"case_id": caso.id, "matter_id": f"m-{caso.id}-{rep}", "draft_full": "texto"}

    def deps(self):
        def marca():
            return {"calls": self.calls, "tokens": self.tokens, "fallidos": len(self.fallidos),
                    "sin_registro": self.sin_registro}

        def desde(m):
            return {"claude_conocido": self.tokens - m["tokens"], "llamadas": self.calls - m["calls"],
                    "fallidos": list(self.fallidos[m["fallidos"]:]),
                    "sin_registro": self.sin_registro - m["sin_registro"]}

        def reloj():
            self.t += 1.0
            return self.t

        return rb.Deps(producir=self.producir, marca=marca, consumo_desde=desde,
                       hash_soul=lambda: self.soul, paradas=(), reloj=reloj)


def _ctx(tmp: Path, nombre: str, *, plan=None, techo=10_000_000, reserva=1_000_000,
         max_segundos=None, aprobada=None, r_reducido=3, **kw) -> rb.Contexto:
    ids = ["fuga-1", "peq-1", "peq-2", "volu-1"]
    plan = plan or rb.construir_plan(ids, ids_fuga=["fuga-1"], ids_voluminosos=["volu-1"],
                                     r_fuga=4, r_base=3)
    return rb.Contexto(
        salida=tmp / f"salida-{nombre}", version="0.4", sha="deadbeef", semilla="s", plan=plan,
        casos={c.id: SimpleNamespace(id=c.id, synthetic=True) for c in plan},
        contador=rb.ContadorCuota(techo_claude=techo, techo_codex=techo // 2,
                                  reserva_juicio_claude=reserva, reserva_juicio_codex=techo // 4),
        soul_esperado="H", r_reducido=r_reducido, max_segundos=max_segundos,
        reanudacion_aprobada=aprobada, **kw)


def bloque_c_ejecucion(tmp: Path) -> None:
    print("\n-- C3 · producción idempotente, reintento de infraestructura y piloto --")
    plan = rb.construir_plan(["fuga-1", "peq-1", "volu-1"], ids_fuga=["fuga-1"],
                             ids_voluminosos=["volu-1"], r_fuga=4, r_base=3)
    check("c-23 · R por clase viene por parámetro: fuga 4, pequeño 3, voluminoso 3 (sin constantes "
          "duplicadas en el runner)",
          [(c.id, c.clase, c.r) for c in plan] == [("fuga-1", "fuga", 4), ("peq-1", "pequeno", 3),
                                                  ("volu-1", "voluminoso", 3)])

    # ── idempotencia ────────────────────────────────────────────────────────────────
    m = Mundo(consumo=100)
    ctx = _ctx(tmp, "idem", plan=plan)
    r1 = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    esperadas = 4 + 3 + 3
    archivos = sorted((ctx.salida / "0.4").glob("*/rep-??.json"))
    check("c-24 · produce todas las repeticiones (4+3+3) y deja UN archivo por versión·caso·repetición",
          r1["salida"] == rb.EXIT_OK and len(m.llamadas_a_producir) == esperadas
          and len(archivos) == esperadas)
    check("c-25 · escritura atómica: no queda ningún .tmp ni .en_curso",
          not list((ctx.salida).rglob("*.tmp")) and not list((ctx.salida).rglob("*en_curso*")))
    n_antes = len(m.llamadas_a_producir)
    ctx2 = _ctx(tmp, "idem", plan=plan)          # MISMA salida: relanzamiento
    r2 = asyncio.run(rb.ejecutar_banco(ctx2, m.deps()))
    # MUTACIÓN: quitar el `if previo ... return previo` de `_ejecutar_una` → cae c-26.
    check("c-26 · relanzar NO repite nada de lo ya completo (idempotente)",
          len(m.llamadas_a_producir) == n_antes and r2["salida"] == rb.EXIT_OK)
    # El contador se reconstruye desde los crudos (no se pierde ni se duplica al relanzar).
    check("c-27 · el contador del relanzamiento es el mismo que el de la corrida original",
          ctx2.contador.claude_total == ctx.contador.claude_total == 100 * esperadas)

    # ── reintento de infraestructura: UNO, con los dos intentos listados ────────────
    m = Mundo(consumo=100, fallos={("peq-1", 1, 1): "infra"})
    ctx = _ctx(tmp, "infra", plan=plan)
    asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    # MUTACIÓN: `MAX_INTENTOS_INFRA = 1` → cae c-28; `= 3` → cae c-29.
    check("c-28 · un fallo de infraestructura se reintenta UNA vez y se listan los dos intentos",
          reg["estado"] == "completo" and [i["estado"] for i in reg["intentos"]]
          == ["fallo_infraestructura", "completo"])
    m = Mundo(consumo=100, fallos={("peq-1", 1, 1): "infra", ("peq-1", 1, 2): "infra",
                                   ("peq-1", 1, 3): "infra"})
    ctx = _ctx(tmp, "infra2", plan=plan)
    asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    check("c-29 · si el reintento también falla, NO hay un tercero: queda fallo_infraestructura "
          "con sus dos intentos",
          reg["estado"] == "fallo_infraestructura" and len(reg["intentos"]) == 2
          and sum(1 for c, r in m.llamadas_a_producir if (c, r) == ("peq-1", 1)) == 2)
    m = Mundo(consumo=100, fallos={("peq-1", 1): "producto"})
    ctx = _ctx(tmp, "prod", plan=plan)
    asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    # MUTACIÓN: tratar `producto` como reintentable → cae c-30.
    check("c-30 · un fallo del PRODUCTO (tras llamar al modelo) no se reintenta y cuenta",
          reg["estado"] == "fallo_producto" and len(reg["intentos"]) == 1)
    # El consumo del fallo de producto incluye la COTA de su intento fallido (100 + 100).
    check("c-31 · el consumo de un fallo incluye la cota conservadora del intento fallido",
          rb._resumen_consumo(reg["intentos"][0]["consumo"]) == 100 + 100)

    # ── guardas de producción ──────────────────────────────────────────────────────
    ctx = _ctx(tmp, "noSint", plan=plan)
    ctx.casos["peq-1"] = SimpleNamespace(id="peq-1", synthetic=False)
    try:
        asyncio.run(rb.ejecutar_banco(ctx, Mundo().deps()))
        ok = False
    except rb.BancoAbortado:
        ok = True
    check("c-32 · un caso no sintético aborta el banco (§9.3)", ok)
    ctx = _ctx(tmp, "soul", plan=plan)
    try:
        asyncio.run(rb.ejecutar_banco(ctx, Mundo(soul="OTRO").deps()))
        ok = False
    except rb.BancoAbortado:
        ok = True
    # MUTACIÓN: quitar la comparación del hash del SOUL → cae c-33.
    check("c-33 · el SOUL alterado detiene el banco ANTES de la corrida", ok)

    # ── tramos de menos de 10 min ──────────────────────────────────────────────────
    m = Mundo(consumo=100)
    ctx = _ctx(tmp, "tramo", plan=plan, max_segundos=5.0)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    hechas = len(m.llamadas_a_producir)
    ctx_b = _ctx(tmp, "tramo", plan=plan, max_segundos=None)
    r_b = asyncio.run(rb.ejecutar_banco(ctx_b, m.deps()))
    check("c-34 · el tramo se corta al agotar el reloj (código 10) y el siguiente SOLO completa lo que falta",
          r["salida"] == rb.EXIT_TRAMO and 0 < hechas < esperadas and r_b["salida"] == rb.EXIT_OK
          and len(m.llamadas_a_producir) == esperadas)

    # ── tanda piloto: R baja solo con consumo y solo en los pequeños sin fuga ──────
    plan9 = rb.construir_plan(["fuga-1", "peq-1", "peq-2", "volu-1"], ids_fuga=["fuga-1"],
                              ids_voluminosos=["volu-1"], r_fuga=10, r_base=5)
    piloto = {"fuga-1": 100, "peq-1": 100, "peq-2": 100, "volu-1": 1000}
    plena = 100 * 10 + 100 * 5 * 2 + 1000 * 5
    d = rb.decidir_r(plan9, piloto, tope_produccion=plena, r_reducido=3)
    check("c-35 · con la proyección dentro del tope se mantiene R plena",
          d["decision"] == "r_plena" and d["proyeccion_r_plena"] == plena and d["cifra_disparadora"] is None)
    d = rb.decidir_r(plan9, piloto, tope_produccion=plena - 1, r_reducido=3)
    # MUTACIÓN: reducir TODOS los casos (sin filtrar `clase == 'pequeno'`) → cae c-36.
    check("c-36 · si la proyección supera el tope, R baja de 5 a 3 SOLO en los pequeños sin fuga",
          d["decision"] == "r_reducida" and d["r_por_caso"] == {"fuga-1": 10, "peq-1": 3, "peq-2": 3,
                                                               "volu-1": 5}
          and d["cifra_disparadora"] == plena)
    d = rb.decidir_r(plan9, piloto, tope_produccion=1000, r_reducido=3)
    check("c-37 · si aun así supera el tope, el banco se SUSPENDE antes de seguir produciendo",
          d["decision"] == "suspender" and d["proyeccion_r_reducida"] > 1000)
    firma = set(inspect.signature(rb.decidir_r).parameters) | set(inspect.signature(
        rb.proyectar_consumo).parameters)
    # MUTACIÓN: añadir un parámetro de calidad (p. ej. `metricas`) a `decidir_r` → cae c-38.
    check("c-38 · la decisión de R recibe SOLO cifras de consumo: su firma no admite ningún dato "
          "de calidad",
          firma <= {"plan", "consumo_piloto", "tope_produccion", "r_reducido", "consumo_aprobaciones",
                    "r_por_caso"})
    # De punta a punta: la piloto dispara la decisión, QUEDA ESCRITA con su cifra y se ACATA.
    m = Mundo(consumo=100)
    ctx = _ctx(tmp, "dec", plan=plan9, techo=2_000, reserva=0)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    dec = rb.leer_json(ctx.salida / "0.4" / "decision_r.json")
    # MUTACIÓN: ignorar `decision == "suspender"` en `ejecutar_banco` → cae c-39.
    check("c-39 · proyección 2500/2100 sobre un tope de 2000: la decisión queda escrita con la cifra "
          "que la disparó y el banco SE SUSPENDE tras la piloto (no sigue produciendo)",
          dec is not None and dec["decision"] == "suspender" and dec["cifra_disparadora"] == 2100
          and r["salida"] == rb.EXIT_SUSPENDIDO and len(m.llamadas_a_producir) == 4
          and "proyección" in r["motivo"])
    m = Mundo(consumo=100)
    ctx = _ctx(tmp, "dec2", plan=plan9, techo=2_300, reserva=0)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    dec = rb.leer_json(ctx.salida / "0.4" / "decision_r.json")
    n_por_caso = {c: sum(1 for x, _ in m.llamadas_a_producir if x == c)
                  for c in ("fuga-1", "peq-1", "peq-2", "volu-1")}
    check("c-39b · con R reducida la proyección cabe: el banco corre con R=3 en los pequeños y "
          "R plena en fuga y voluminosos",
          dec["decision"] == "r_reducida" and r["salida"] == rb.EXIT_OK
          and n_por_caso == {"fuga-1": 10, "peq-1": 3, "peq-2": 3, "volu-1": 5})

    # ── submuestra de aprobaciones ────────────────────────────────────────────────
    comp = {"a": [1, 2, 3], "b": [2], "c": [], "d": [1, 4]}
    s1 = rb.elegir_aprobaciones(comp, "semilla")
    s2 = rb.elegir_aprobaciones({k: list(reversed(v)) for k, v in comp.items()}, "semilla")
    check("c-40 · una repetición COMPLETADA por caso, determinista y sin casos vacíos",
          s1 == s2 and [e["caso"] for e in s1] == ["a", "b", "d"]
          and all(e["rep"] in comp[e["caso"]] for e in s1))
    check("c-41 · otra semilla puede elegir otras repeticiones (no es un valor fijo)",
          any(rb.elegir_aprobaciones(comp, f"x{i}") != s1 for i in range(20)))
    ctx = _ctx(tmp, "aprob", plan=plan)
    asyncio.run(rb.ejecutar_banco(ctx, Mundo(consumo=10).deps()))
    ap = rb.leer_json(ctx.salida / "0.4" / "aprobaciones_plan.json")
    check("c-42 · al terminar escribe el plan de aprobaciones: una por caso, aparte",
          ap is not None and len(ap["elegidas"]) == 3)


def bloque_c_protocolo(tmp: Path) -> None:
    print("\n-- C4 · el runner toma R, techos y reserva de protocolo.py (no los duplica) --")
    from mia.eval.banco04 import protocolo as pr

    visibles = (list(pr.CASOS_A_CANONICOS) + list(pr.CASOS_A_RIESGO) + list(pr.CASOS_A_VOLUMINOSO)
                + list(pr.CASOS_C_PEQUENOS))
    cust = [f"V{i}-custodiado" for i in range(1, 5)]
    plan = rb.plan_desde_protocolo(pr, visibles + cust, cust)
    check("p-1 · el plan de producción son los 17 casos y 100 corridas (fuga 3×10, resto 14×5)",
          len(plan) == pr.N_CASOS_TOTAL == 17 and sum(c.r for c in plan) == pr.CORRIDAS_POR_VERSION == 100
          and sorted(c.id for c in plan if c.clase == "fuga") == sorted(pr.CASOS_FUGA_INTERMITENTE)
          and sum(1 for c in plan if c.clase == "voluminoso") == 5
          and sum(1 for c in plan if c.clase == "pequeno") == 9)
    # MUTACIÓN: `decidir_r` con `c.clase == "pequeno"` mal calculada → 82 deja de salir (c-36 también).
    piloto = {c.id: 100 for c in plan}
    d = rb.decidir_r(plan, piloto, tope_produccion=100 * 100 - 1, r_reducido=pr.R_CONTINGENCIA_PEQUENOS_SIN_FUGA)
    check("p-2 · la contingencia de §3.4 da las 82 corridas del protocolo (R=3 solo en 9 pequeños sin fuga)",
          d["decision"] == "r_reducida" and sum(d["r_por_caso"].values()) == pr.CORRIDAS_CON_CONTINGENCIA == 82)
    try:
        rb.plan_desde_protocolo(pr, visibles + ["caso-ajeno"], cust)
        ok = False
    except KeyError:
        ok = True
    check("p-3 · un caso fuera de la muestra del protocolo es un error (no se adivina su R)", ok)
    k = rb.constantes_de_protocolo(pr, 0)
    check("p-4 · Bloque 0: techos 18 M / 5 M, reserva del juicio 7 M Claude y TODA la de Codex",
          (k["techo_claude"], k["techo_codex"]) == (18_000_000, 5_000_000)
          and k["reserva_claude"] == 7_000_000 and k["reserva_codex"] == 5_000_000)
    check("p-5 · el rótulo de suspensión del runner es el del protocolo (literal)",
          rb.TEXTO_INCOMPLETO == pr.ROTULO_SUSPENSION and k["rotulo_suspension"] == rb.TEXTO_INCOMPLETO)
    c = rb.ContadorCuota(techo_claude=k["techo_claude"], techo_codex=k["techo_codex"],
                         reserva_juicio_claude=k["reserva_claude"], reserva_juicio_codex=k["reserva_codex"])
    check("p-6 · la producción del Bloque 0 tiene tope 11 M (18 − 7): no puede tocar la reserva",
          c.tope_produccion_claude == 11_000_000)
    check("p-7 · Bloque 7: la reserva sale de protocolo.py (13 M / 6 M)",
          rb.constantes_de_protocolo(pr, 7)["reserva_claude"] == 13_000_000)
    try:
        rb.constantes_de_protocolo(SimpleNamespace(), 0)
        ok = False
    except rb.BancoAbortado:
        ok = True
    check("p-8 · si falta cualquier constante del protocolo, no arranca", ok)


# ═════════════════════════════════════════════════════════════════════════════
# D · P10 y P11 — techo no certificable y suspensión
# ═════════════════════════════════════════════════════════════════════════════
def bloque_d(tmp: Path) -> None:
    print("\n-- D · P10 (techo sin cota = no certificable) y P11 (techo alcanzado = suspende) --")
    plan = rb.construir_plan(["peq-1", "peq-2", "volu-1"], ids_fuga=[], ids_voluminosos=["volu-1"],
                             r_fuga=4, r_base=2)
    # P10 — un intento fallido SIN cota (entrada/salida None) deja el banco no certificable.
    m = Mundo(consumo=100, fallos={("peq-2", 1): "sin_cota"})
    ctx = _ctx(tmp, "p10", plan=plan)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    # MUTACIÓN: en `cota_de_fallidos`, tratar `None` como 0 → cae d-1, d-2 y d-3.
    check("d-1 · P10: un fallo sin cota calculable hace el techo NO certificable",
          ctx.contador.cota_calculable is False and ctx.contador.claves_sin_cota())
    check("d-2 · P10: el estado final del banco es «no certificable», no «terminado»",
          r["estado"] == "no certificable"
          and rb.leer_json(ctx.salida / "0.4" / "estado_banco.json")["estado"] == "no certificable")
    tot, ok = rb.cota_de_fallidos([{"tokens_cota_superior": 100}, {"tokens_cota_superior": None}])
    check("d-3 · P10: la suma de cotas con UN None es incalculable (no cuenta como 0)",
          ok is False)
    tot, ok = rb.cota_de_fallidos([{"tokens_cota_superior": 100}, {"tokens_cota_superior": 50}])
    check("d-4 · con todas las cotas, la suma es calculable (100 + 50)", ok and tot == 150)
    tot, ok = rb.cota_de_fallidos([], sin_registro=1)
    check("d-5 · P10: un intento que ni se pudo registrar también deja la cota incalculable", not ok)
    # Una corrida que murió a mitad (marcador en_curso huérfano): consumo desconocido.
    ctx = _ctx(tmp, "huerfana", plan=plan)
    rb.escribir_atomico(rb.ruta_en_curso(ctx.salida, "0.4", "peq-1", 1),
                        {"caso_id": "peq-1", "rep": 1, "intento": 1})
    asyncio.run(rb.ejecutar_banco(ctx, Mundo(consumo=10).deps()))
    check("d-6 · P10: una corrida que murió a medias (consumo desconocido, sin cota) deja el banco "
          "no certificable",
          ctx.contador.cota_calculable is False)

    # P11 — el contador alcanza el techo, suspende y publica «incompleto — no certificable».
    # El piloto consume poco (la proyección cabe) y DESPUÉS el consumo real se dispara: lo que
    # suspende aquí es el ACUMULADO alcanzando el techo, no la proyección de la piloto.
    m = Mundo()
    m.consumo = lambda cid, m=m: 100 if len(m.llamadas_a_producir) <= 3 else 1000
    ctx = _ctx(tmp, "p11", plan=plan, techo=2000, reserva=0)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    marca = rb.leer_json(ctx.salida / "0.4" / "SUSPENDIDO.json")
    hechas = len(m.llamadas_a_producir)
    # MUTACIÓN: en `motivo_suspension`, `>=` → `>` (techo exacto no suspende) o quitar el
    # `suspender(...)` de `paso` → caen d-7 y d-8.
    check("d-7 · P11: al alcanzar el techo se SUSPENDE y no produce más (código 2)",
          r["salida"] == rb.EXIT_SUSPENDIDO and ctx.contador.claude_total >= 2000 and hechas < 6
          and marca is not None)
    check("d-8 · P11: se publica literalmente «incompleto — no certificable» con la cifra de consumo",
          marca["estado"] == "incompleto — no certificable"
          and marca["consumo"]["claude_total"] == ctx.contador.claude_total
          and marca["motivo"].startswith("el acumulado de cuota Claude"))
    r = asyncio.run(rb.ejecutar_banco(_ctx(tmp, "p11", plan=plan, techo=2000, reserva=0), m.deps()))
    check("d-9 · P11: no se reanuda sin una aprobación expresa de Pipe",
          r["salida"] == rb.EXIT_SUSPENDIDO and len(m.llamadas_a_producir) == hechas)
    r = asyncio.run(rb.ejecutar_banco(
        _ctx(tmp, "p11", plan=plan, techo=100_000, reserva=0, aprobada="Pipe 2026-10-12 #1"), m.deps()))
    check("d-10 · con la referencia de la aprobación de Pipe SÍ se reanuda y queda constancia",
          r["salida"] == rb.EXIT_OK
          and (tmp / "salida-p11" / "0.4" / "SUSPENDIDO.reanudado.json").is_file())

    # La RESERVA del juicio: la producción no puede consumirla.
    c = rb.ContadorCuota(techo_claude=1000, techo_codex=100, reserva_juicio_claude=300,
                         reserva_juicio_codex=100)
    c.registrar("p1", rubro="produccion", claude_conocido=650)
    check("d-11 · producción 650 con reserva 300 sobre techo 1000: aún cabe una corrida de 50",
          c.motivo_suspension(proximo_estimado=50) is None)
    # MUTACIÓN: `tope_produccion_claude` = techo (sin restar la reserva) → cae d-12.
    check("d-12 · una corrida de 60 invadiría la reserva del juicio: se suspende ANTES de hacerla",
          "reserva" in (c.motivo_suspension(proximo_estimado=60) or ""))
    c.registrar("j1", rubro="juicio", claude_conocido=299)
    check("d-13 · el juicio SÍ puede usar su reserva (cuenta para el techo, no para el tope de producción)",
          c.motivo_suspension(proximo_estimado=0) is None and c.claude_total == 949)
    c.registrar("j2", rubro="juicio", claude_conocido=51)
    check("d-14 · producción + juicio alcanzan el techo del circuito → suspende",
          "techo" in (c.motivo_suspension() or ""))
    c2 = rb.ContadorCuota(techo_claude=1000, techo_codex=100, reserva_juicio_claude=0,
                          reserva_juicio_codex=0)
    c2.registrar("x", rubro="juicio", codex_conocido=100)
    check("d-15 · el techo de Codex también suspende", "Codex" in (c2.motivo_suspension() or ""))
    c3 = rb.ContadorCuota(techo_claude=1000, techo_codex=100, reserva_juicio_claude=0,
                          reserva_juicio_codex=0)
    c3.registrar("k", rubro="produccion", claude_conocido=10)
    c3.registrar("k", rubro="produccion", claude_conocido=10)
    check("d-16 · registrar dos veces la misma clave no duplica (idempotente)", c3.claude_total == 10)

    # Límite de uso del plan → suspensión (no se reintenta ni cuenta como infraestructura).
    m = Mundo(consumo=10, fallos={("peq-2", 1): "limite"})
    ctx = _ctx(tmp, "limite", plan=plan)
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    check("d-17 · un límite de uso del plan SUSPENDE el banco («incompleto — no certificable»)",
          r["salida"] == rb.EXIT_SUSPENDIDO and r["estado"] == "incompleto — no certificable"
          and sum(1 for c_, r_ in m.llamadas_a_producir if (c_, r_) == ("peq-2", 1)) == 1)
    # El contador está MUY por debajo del techo: solo la falta de aprobación impide reanudar.
    antes = len(m.llamadas_a_producir)
    m.fallos = {}
    r = asyncio.run(rb.ejecutar_banco(_ctx(tmp, "limite", plan=plan), m.deps()))
    # MUTACIÓN: quitar el `return` de suspensión sin aprobación en `ejecutar_banco` → cae d-18.
    check("d-18 · suspendido por límite de uso: relanzar SIN aprobación de Pipe no produce nada, "
          "aunque el contador esté lejos del techo",
          r["salida"] == rb.EXIT_SUSPENDIDO and len(m.llamadas_a_producir) == antes)
    r = asyncio.run(rb.ejecutar_banco(_ctx(tmp, "limite", plan=plan, aprobada="Pipe #2"), m.deps()))
    check("d-19 · con la aprobación expresa de Pipe, el banco continúa y termina",
          r["salida"] == rb.EXIT_OK and len(m.llamadas_a_producir) > antes)

    # La reserva del juicio se respeta ANTES de producir (no solo se descubre después de invadirla).
    m = Mundo()
    m.consumo = lambda cid, m=m: 100 if len(m.llamadas_a_producir) <= 3 else 200
    ctx = _ctx(tmp, "reserva", plan=plan, techo=1000, reserva=300)       # tope de producción: 700
    r = asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    # MUTACIÓN: no consultar `motivo_suspension(proximo_estimado=...)` antes de cada corrida → cae d-20.
    check("d-20 · la producción se detiene ANTES de invadir la reserva del juicio (≤ 700 de 1000)",
          r["salida"] == rb.EXIT_SUSPENDIDO and ctx.contador.claude_produccion <= 700
          and "reserva" in r["motivo"])


# ═════════════════════════════════════════════════════════════════════════════
# E · P6 — custodia fail-closed y nada de custodia bajo el repo
# ═════════════════════════════════════════════════════════════════════════════
def _dpapi_proteger(datos: bytes) -> bytes:
    """`CryptProtectData` (ámbito de usuario, sin entropía, sin UI): solo para fabricar la llave
    de la custodia FALSA de estos gates. El cargador, a propósito, solo sabe DESPROTEGER."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(datos, len(datos))
    entrada = Blob(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    salida = Blob()
    if not crypt32.CryptProtectData(ctypes.byref(entrada), "banco04-test", None, None, None, 0x1,
                                    ctypes.byref(salida)):
        raise OSError("CryptProtectData falló")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


class CustodiaFalsa:
    """Una custodia SINTÉTICA, generada en un directorio temporal FUERA del repo, con el mismo
    formato que documenta `docs/banco04-custodia-formato.md`. Nunca se abre la custodia real."""

    MARCA = "relleno-sintetico-unico-7f3a"      # texto que NUNCA debe aparecer en disco en claro

    def __init__(self, tmp: Path, nombre: str, *, esquemas: dict) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self.AESGCM = AESGCM
        self.carpeta = tmp / f"custodia-{nombre}"
        self.carpeta.mkdir()
        self.llave = os.urandom(32)
        self.manifest: dict = {
            "schema": "banco04-custodia-manifest/v1", "protocolo": "banco04-v1.2",
            "cifrado": {"algoritmo": "AES-256-GCM", "aad": "banco04-v1.2|<id>",
                        "llave": {"archivo": "llave.dpapi", "longitud_bytes": 32,
                                  "proteccion": "Windows DPAPI ámbito usuario CRYPTPROTECT_UI_FORBIDDEN",
                                  "sha256_blob_dpapi": ""}},
            "artefactos": [], "esquemas": esquemas, "invariantes_semanticas": []}
        self.poner_llave(self.llave)
        for i in range(1, 5):
            self.escribir(f"V{i}", "caso", self.caso(f"V{i}", ["co"] if i == 4 else []),
                          "banco04-caso/v1")
        self.escribir("clave-V1", "clave", self.clave("V1"), "banco04-clave/v1")
        self.escribir("mut-ajuste", "mutaciones_ajuste", self.mutaciones(), "banco04-mutaciones/v1")
        self.escribir("semilla", "semilla", {
            "schema": "banco04-semilla/v1", "protocolo": "banco04-v1.2", "algoritmo": "HMAC-SHA256",
            "hmac_key_hex": "ab" * 32, "usos": [], "creada": "2026-10-11"}, "banco04-semilla/v1")

    # -- fabricación ---------------------------------------------------------------
    @staticmethod
    def canonico(obj) -> bytes:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def caso(self, id_: str, jur: list) -> dict:
        docs = [{"filename": f"{id_}-doc{d}.txt",
                 "chunks": [f"{self.MARCA} {id_} doc{d} fragmento {i}" for i in range(70)]}
                for d in range(3)]
        return {"schema": "banco04-caso/v1", "protocolo": "banco04-v1.2", "id": id_, "title": "t",
                "message": "mensaje", "jurisdicciones": jur, "profile": {}, "synthetic": True,
                "expect_reaches_draft": True, "recall_markers": [], "rubric": {}, "documents": docs,
                "n_fragmentos": 210, "semilla_relleno": 1}

    def clave(self, id_: str) -> dict:
        f0 = f"{id_}-doc0.txt"
        return {"schema": "banco04-clave/v1", "protocolo": "banco04-v1.2", "case_id": id_,
                "base_indice_fragmento": 0, "n_fragmentos": 210,
                "orden_documentos": [f"{id_}-doc{d}.txt" for d in range(3)],
                "hechos_materiales": [{
                    "id": "H1", "enunciado": "e", "documento": f0, "documento_orden": 0,
                    "fragmentos": [5], "fragmento_principal": 5,
                    "posicion_relativa_en_documento": 0.07, "posicion_global": 5,
                    "posicion_global_relativa": 0.02, "enterrado": True, "marcador_auxiliar": "mk",
                    "literales_exclusivos": [], "decisivo": True, "rol": "r"}],
                "puntos_materiales": [{"id": "P1", "enunciado": "e", "tipo": "conclusion",
                                       "depende_de_hechos": ["H1"],
                                       "fragmentos": [{"documento": f0, "fragmento": 5}]}],
                "conclusion_correcta": "c", "conclusiones_erroneas_previsibles": [],
                "conducta_bajo_cobertura_parcial": {
                    "alcance_esperado": "x", "conducta_exigida": "x", "descripcion": "x",
                    "debe_nombrar": [], "no_debe": []},
                "distractores": [], "normas_ficticias": [], "propiedades_construccion": {},
                "marcadores_auxiliares": ["mk"], "notas": {}}

    def item(self, id_: str = "MA-01") -> dict:
        diag = "El plazo vence el cinco de mayo."
        return {"id": id_, "jurisdicciones": [],
                "material": {"mensaje_abogado": "m", "documentos": [
                    {"filename": "a.txt", "chunks": [f"{id_} uno", f"{id_} dos"]}],
                    "mapa_doc": {"1": {"documento": "a.txt", "fragmento": 0}},
                    "piezas_fuera_del_mapa": [], "fuentes_corpus": [
                        {"ref": "corpus:x", "texto": "t", "ficticia": True}], "aviso_alcance": None},
                "salida": {"diagnostico": diag, "borrador": "b"},
                "verdad": [{"id": "v1", "clase": "defecto", "categoria": "C01", "campo": "diagnostico",
                            "inicio": 3, "fin": 8, "literal": diag[3:8], "estado_esperado": "sin_respaldo",
                            "estados_aceptables": ["sin_respaldo"], "subtipo_esperado": "hecho",
                            "nota": None}]}

    def mutaciones(self) -> dict:
        return {"schema": "banco04-mutaciones/v1", "protocolo": "banco04-v1.2", "conjunto": "ajuste",
                "uso": "depuracion_de_prompts", "base": "sintetica", "regla_de_deteccion": "x",
                "categorias": {"C01": "x"}, "items": [self.item()],
                "resumen": {"salidas": 1, "defectos": 1, "controles": 0,
                            "clausulas_falsas_breves": 0, "por_categoria": {"C01": 1}}}

    def poner_llave(self, llave: bytes, *, blob: bytes | None = None, actualizar: bool = True) -> None:
        blob = _dpapi_proteger(llave) if blob is None else blob
        (self.carpeta / "llave.dpapi").write_bytes(blob)
        if actualizar:
            self.manifest["cifrado"]["llave"]["sha256_blob_dpapi"] = hashlib.sha256(blob).hexdigest()

    def entrada(self, id_: str) -> dict:
        return next(a for a in self.manifest["artefactos"] if a["id"] == id_)

    def escribir(self, id_: str, tipo: str, obj_o_bytes, esquema: str | None, *,
                 aad_id: str | None = None, llave: bytes | None = None,
                 sha_claro: str | None = None, existente: bool = False) -> None:
        claro = obj_o_bytes if isinstance(obj_o_bytes, bytes) else self.canonico(obj_o_bytes)
        nonce = os.urandom(12)
        raw = nonce + self.AESGCM(llave or self.llave).encrypt(
            nonce, claro, f"banco04-v1.2|{aad_id or id_}".encode())
        archivo = f"{id_}.bin"
        (self.carpeta / archivo).write_bytes(raw)
        fila = {"id": id_, "tipo": tipo, "archivo": archivo,
                "sha256_claro": sha_claro or hashlib.sha256(claro).hexdigest(),
                "sha256_cifrado": hashlib.sha256(raw).hexdigest(), "bytes_claro": len(claro),
                "formato_claro": "json-canonico-utf8", "esquema": esquema}
        if existente:
            self.manifest["artefactos"][[a["id"] for a in self.manifest["artefactos"]].index(id_)] = fila
        else:
            self.manifest["artefactos"].append(fila)

    def manifiesto(self) -> Path:
        ruta = self.carpeta.parent / f"manifest-{self.carpeta.name}.json"
        ruta.write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")
        return ruta

    def abrir(self, **kw):
        from mia.eval.banco04 import custodia
        kw.setdefault("environ", {custodia.ENV_CUSTODIA: str(self.carpeta)})
        kw.setdefault("manifest_path", self.manifiesto())
        kw.setdefault("repo_root", ROOT)
        return custodia.abrir(custodia.PROPOSITO_MEDICION, **kw)


def _falla(fn, tipo=None) -> bool:
    from mia.eval.banco04 import custodia
    try:
        fn()
    except (tipo or custodia.CustodiaError):
        return True
    return False


def bloque_e(tmp: Path) -> None:
    print("\n-- E · P6: custodia fail-closed, llave DPAPI y nada bajo el repositorio --")
    from mia.eval.banco04 import custodia

    real = json.loads((ROOT / "backend/mia/eval/banco04/custodia_manifest.json").read_text(encoding="utf-8"))
    esquemas = real["esquemas"]

    # ── camino feliz ───────────────────────────────────────────────────────────────
    f = CustodiaFalsa(tmp, "ok", esquemas=esquemas)
    with f.abrir() as c:
        casos = c.casos()
        jur = c.jurisdicciones()
        ok_clave = c.clave("V1")["case_id"] == "V1"
        ok_mut = c.mutaciones("ajuste")["conjunto"] == "ajuste"
        ok_sem = c.semilla_hmac() == bytes.fromhex("ab" * 32)
    check("e-1 · una custodia íntegra abre y entrega casos, jurisdicciones, clave, mutaciones y semilla",
          [x.id for x in casos] == ["V1", "V2", "V3", "V4"] and all(x.synthetic for x in casos)
          and all(not x.recall_markers and x.rubric == {} for x in casos)
          and len(casos[0].documents) == 3 and sum(len(d.chunks) for d in casos[0].documents) == 210
          and jur == {"V1": [], "V2": [], "V3": [], "V4": ["co"]} and ok_clave and ok_mut and ok_sem)
    # MUTACIÓN: en `jurisdicciones`, devolver `[]` siempre → cae e-1 (V4 pierde su pack `co`).
    check("e-2 · cerrar() suelta lo descifrado: una custodia cerrada ya no entrega nada",
          c.cerrada and _falla(lambda: c.artefacto("V1")) and _falla(lambda: c.objeto("V1")))
    # MUTACIÓN: `cerrar()` sin `self._llave = None` → cae e-2.

    # ── propósito ──────────────────────────────────────────────────────────────────
    # MUTACIÓN: en `abrir`, quitar la comparación con PROPOSITO_MEDICION → cae e-3.
    ok = True
    for prop in ("arreglo", "calibrar", "depurar", "", "medicion"):
        ok = ok and _falla(lambda p=prop: custodia.abrir(p, environ={}), custodia.CustodiaPropositoInvalido)
    check("e-3 · otro propósito (arreglo, calibrar, depurar, vacío…) se rechaza ANTES de mirar el entorno",
          ok)

    # ── ubicación ──────────────────────────────────────────────────────────────────
    check("e-4 · sin MIA_BANCO04_CUSTODIA no hay ruta por defecto: se detiene",
          _falla(lambda: custodia.abrir(custodia.PROPOSITO_MEDICION, environ={}, repo_root=ROOT))
          and _falla(lambda: custodia.abrir(custodia.PROPOSITO_MEDICION,
                                            environ={custodia.ENV_CUSTODIA: "  "}, repo_root=ROOT)))
    check("e-5 · una carpeta de custodia ausente se detiene",
          _falla(lambda: custodia.abrir(custodia.PROPOSITO_MEDICION, repo_root=ROOT,
                                        environ={custodia.ENV_CUSTODIA: str(tmp / "no-existe")})))
    # MUTACIÓN: quitar `if carpeta == repo or _dentro_de(carpeta, repo)` → cae e-6.
    check("e-6 · una carpeta de custodia DENTRO del repositorio se rechaza (P6)",
          _falla(lambda: f.abrir(repo_root=tmp)))

    # ── hashes: cualquier alteración falla cerrado ─────────────────────────────────
    f = CustodiaFalsa(tmp, "bytes", esquemas=esquemas)
    raw = bytearray((f.carpeta / "semilla.bin").read_bytes())
    raw[20] ^= 0x01
    (f.carpeta / "semilla.bin").write_bytes(bytes(raw))
    # MUTACIÓN: quitar la comprobación de sha256_cifrado del bucle de `abrir` → cae e-7 (el
    # artefacto alterado NO se usa en este gate: solo el chequeo de apertura lo puede ver).
    check("e-7 · un archivo cifrado alterado se detecta al ABRIR, aunque no se vaya a usar",
          _falla(lambda: f.abrir()))
    f = CustodiaFalsa(tmp, "tarde", esquemas=esquemas)
    c = f.abrir()
    raw = bytearray((f.carpeta / "V2.bin").read_bytes())
    raw[-1] ^= 0x01
    (f.carpeta / "V2.bin").write_bytes(bytes(raw))
    # MUTACIÓN: quitar el sha256_cifrado de `artefacto` → cae e-8.
    check("e-8 · un archivo alterado DESPUÉS de abrir también se detecta al entregarlo",
          _falla(lambda: c.artefacto("V2")))
    f = CustodiaFalsa(tmp, "tag", esquemas=esquemas)
    raw = bytearray((f.carpeta / "V1.bin").read_bytes())
    raw[-1] ^= 0x01                                           # el tag GCM, con el manifiesto al día
    (f.carpeta / "V1.bin").write_bytes(bytes(raw))
    f.entrada("V1")["sha256_cifrado"] = hashlib.sha256(bytes(raw)).hexdigest()
    c = f.abrir()
    check("e-9 · aun con el manifiesto actualizado, el tag GCM alterado no autentica",
          _falla(lambda: c.artefacto("V1")))
    f = CustodiaFalsa(tmp, "aad", esquemas=esquemas)
    f.escribir("V1", "caso", f.caso("V1", []), "banco04-caso/v1", aad_id="V2", existente=True)
    c = f.abrir()
    # MUTACIÓN: AAD constante (no el id del artefacto) → cae e-10.
    check("e-10 · el artefacto cifrado con el id de otro (AAD distinto) no autentica",
          _falla(lambda: c.artefacto("V1")))
    f = CustodiaFalsa(tmp, "claro", esquemas=esquemas)
    f.entrada("V3")["sha256_claro"] = "0" * 64
    c = f.abrir()
    # MUTACIÓN: quitar la comparación de sha256_claro → cae e-11.
    check("e-11 · si el sha256 en claro no coincide con el manifiesto, se detiene",
          _falla(lambda: c.artefacto("V3")))
    f = CustodiaFalsa(tmp, "canon", esquemas=esquemas)
    f.escribir("V1", "caso", json.dumps(f.caso("V1", []), indent=2, ensure_ascii=False).encode("utf-8"),
               "banco04-caso/v1", existente=True)
    c = f.abrir()
    # MUTACIÓN: quitar la comparación `_canonico(obj) != claro` → cae e-12.
    check("e-12 · un JSON que no es la serialización canónica se rechaza (aunque los hashes cuadren)",
          _falla(lambda: c.objeto("V1")))
    f = CustodiaFalsa(tmp, "esquema", esquemas=esquemas)
    malo = f.caso("V1", [])
    malo["id"] = "V9"
    f.escribir("V1", "caso", malo, "banco04-caso/v1", existente=True)
    c = f.abrir()
    # MUTACIÓN: quitar la llamada a `_validar_esquema` → cae e-13.
    check("e-13 · un artefacto que viola su esquema se rechaza", _falla(lambda: c.objeto("V1")))
    f = CustodiaFalsa(tmp, "invariante", esquemas=esquemas)
    malo = f.caso("V2", [])
    malo["n_fragmentos"] = 211
    f.escribir("V2", "caso", malo, "banco04-caso/v1", existente=True)
    c = f.abrir()
    # MUTACIÓN: quitar la llamada a `_invariantes` → cae e-14.
    check("e-14 · una invariante semántica rota (n_fragmentos ≠ suma de fragmentos) se rechaza",
          _falla(lambda: c.objeto("V2")))
    f = CustodiaFalsa(tmp, "cruce", esquemas=esquemas)
    mala = f.clave("V1")
    mala["hechos_materiales"][0]["fragmentos"] = [999]
    f.escribir("clave-V1", "clave", mala, "banco04-clave/v1", existente=True)
    c = f.abrir()
    check("e-15 · una clave que apunta a un fragmento inexistente de su caso se rechaza",
          _falla(lambda: c.clave("V1")))
    f = CustodiaFalsa(tmp, "falta", esquemas=esquemas)
    (f.carpeta / "V3.bin").unlink()
    check("e-16 · un archivo de custodia que falta detiene la apertura", _falla(lambda: f.abrir()))
    f = CustodiaFalsa(tmp, "viaje", esquemas=esquemas)
    # Un artefacto VÁLIDO (hashes y GCM correctos) pero FUERA de la carpeta de custodia, al que el
    # manifiesto apunta con `..\`: solo la validación del nombre lo detiene (si el archivo no
    # existiera, el fallo de lectura taparía la mutación).
    f.escribir("V1", "caso", f.caso("V1", []), "banco04-caso/v1", existente=True)
    (tmp / "fuera-custodia.bin").write_bytes((f.carpeta / "V1.bin").read_bytes())
    f.entrada("V1")["archivo"] = "..\\fuera-custodia.bin"
    # MUTACIÓN: quitar la validación del nombre de archivo del manifiesto → cae e-17.
    check("e-17 · un nombre de archivo con ruta relativa en el manifiesto (que SÍ apunta a un archivo "
          "válido fuera de la custodia) se rechaza",
          _falla(lambda: f.abrir()))
    f = CustodiaFalsa(tmp, "manif", esquemas=esquemas)
    f.manifest["protocolo"] = "banco04-v1.1"
    ok1 = _falla(lambda: f.abrir())
    f.manifest["protocolo"] = "banco04-v1.2"
    f.manifest["schema"] = "otro/v1"
    # MUTACIÓN: quitar la validación schema/protocolo de `cargar_manifiesto` → cae e-17b.
    check("e-17b · un manifiesto de otro protocolo o de otro esquema se rechaza",
          ok1 and _falla(lambda: f.abrir()))

    # ── la llave: DPAPI ────────────────────────────────────────────────────────────
    f = CustodiaFalsa(tmp, "llave", esquemas=esquemas)
    blob = (f.carpeta / "llave.dpapi").read_bytes()
    check("e-18 · la llave de la custodia está protegida con DPAPI: el blob no contiene la llave y "
          "solo DPAPI la devuelve",
          f.llave not in blob and blob != f.llave and custodia.desproteger_dpapi(blob) == f.llave
          and "DPAPI" in real["cifrado"]["llave"]["proteccion"])
    check("e-19 · un blob DPAPI alterado no se puede desproteger",
          _falla(lambda: custodia.desproteger_dpapi(blob[:-4] + b"\x00\x00\x00\x00")))
    f.manifest["cifrado"]["llave"]["sha256_blob_dpapi"] = "0" * 64
    # MUTACIÓN: quitar la comparación de sha256_blob_dpapi → cae e-20 (el blob SÍ es DPAPI válido,
    # así que solo el hash del manifiesto lo delata).
    check("e-20 · el blob DPAPI que no coincide con el hash del manifiesto se rechaza",
          _falla(lambda: f.abrir()))
    f = CustodiaFalsa(tmp, "otra", esquemas=esquemas)
    f.poner_llave(os.urandom(32))                              # llave DPAPI válida pero OTRA
    c = f.abrir()
    check("e-21 · una llave distinta a la que cifró no autentica ningún artefacto",
          _falla(lambda: c.artefacto("V1")))
    f = CustodiaFalsa(tmp, "corta", esquemas=esquemas)
    f.poner_llave(os.urandom(16))
    # MUTACIÓN: quitar la comprobación de 32 bytes → cae e-22.
    check("e-22 · una llave que no mide 32 bytes (AES-256) se rechaza", _falla(lambda: f.abrir()))
    f = CustodiaFalsa(tmp, "nodpapi", esquemas=esquemas)
    f.poner_llave(f.llave, blob=f.llave)                       # la llave en claro, sin DPAPI
    check("e-23 · la llave en claro (sin DPAPI) en la carpeta NO se acepta como llave",
          _falla(lambda: f.abrir()))

    # ── versión propia de la custodia (protocolo.PROTOCOLO_CUSTODIA) ─────────────────────────────
    from mia.eval.banco04 import protocolo as _pr
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AES
    f = CustodiaFalsa(tmp, "protocolo", esquemas=esquemas)
    with f.abrir() as c:
        raw_reg = c.cifrar_registro("0.4/V1/1", b"hola")
    # MUTACIÓN: cambiar la AAD de `cifrar_registro` (p. ej. otro literal) → cae e-34.
    check("e-34 · la AAD NO cambió: los registros se cifran con `banco04-v1.2|registro|<id>` y descifran "
          "con AES-GCM directo",
          _AES(f.llave).decrypt(raw_reg[:12], raw_reg[12:], b"banco04-v1.2|registro|0.4/V1/1") == b"hola"
          and _pr.PROTOCOLO_CUSTODIA == "banco04-v1.2")
    original = _pr.PROTOCOLO_CUSTODIA
    try:
        del _pr.PROTOCOLO_CUSTODIA
        # MUTACIÓN: volver a una constante PROPIA de custodia.py (sin leer protocolo.py) → cae e-35.
        check("e-35 · sin `protocolo.PROTOCOLO_CUSTODIA` la custodia NO abre (fail-closed)",
              _falla(lambda: f.abrir()))
        _pr.PROTOCOLO_CUSTODIA = "banco04-v9"
        check("e-36 · la versión sale de protocolo.py: con otra versión, un manifiesto v1.2 se rechaza",
              _falla(lambda: f.abrir()))
    finally:
        _pr.PROTOCOLO_CUSTODIA = original

    # ── mutaciones: invariantes puras ──────────────────────────────────────────────
    base = CustodiaFalsa.mutaciones(CustodiaFalsa.__new__(CustodiaFalsa))
    custodia.invariantes_mutaciones_obj(base, reservado=False)
    mal = json.loads(json.dumps(base))
    mal["items"][0]["verdad"][0]["literal"] = "otra cosa"
    check("e-24 · mutaciones: salida[campo][inicio:fin] ≠ literal se rechaza",
          _falla(lambda: custodia.invariantes_mutaciones_obj(mal, reservado=False)))
    sol = json.loads(json.dumps(base))
    v2 = dict(sol["items"][0]["verdad"][0], id="v2", inicio=5, fin=10)
    v2["literal"] = sol["items"][0]["salida"]["diagnostico"][5:10]
    sol["items"][0]["verdad"].append(v2)
    check("e-25 · mutaciones: dos spans solapados en el mismo campo se rechazan",
          _falla(lambda: custodia.invariantes_mutaciones_obj(sol, reservado=False)))
    c08 = json.loads(json.dumps(base))
    c08["items"][0]["verdad"][0]["categoria"] = "C08"
    c08["items"][0]["jurisdicciones"] = ["co"]
    check("e-26 · mutaciones: C08 solo en items sin ordenamiento", _falla(
        lambda: custodia.invariantes_mutaciones_obj(c08, reservado=False)))
    check("e-27 · el reservado exige ≥30 defectos, ≥30 controles y ≥10 C12 con proporción < 0,20",
          _falla(lambda: custodia.invariantes_mutaciones_obj(base, reservado=True)))
    f = CustodiaFalsa(tmp, "disjunto", esquemas=esquemas)
    res = f.mutaciones()
    res["conjunto"], res["uso"] = "reservado", "un_solo_uso_con_prompts_congelados"
    f.escribir("mut-reservado", "mutaciones_reservadas", res, "banco04-mutaciones/v1")
    c = f.abrir()
    # (el reservado falsa no llega a 30 defectos: lo que se prueba aquí es que ajuste y reservado
    #  con material COMPARTIDO nunca pasan, ni por la vía del ajuste)
    check("e-28 · ajuste y reservado con el mismo material (o el reservado bajo mínimos) no se entregan",
          _falla(lambda: c.mutaciones("ajuste")) and _falla(lambda: c.mutaciones("reservado")))

    # ── nada de custodia bajo el repo + el manifiesto solo trae hashes ─────────────
    nombres = {a["archivo"] for a in real["artefactos"]} | {real["cifrado"]["llave"]["archivo"]}
    encontrados = []
    for raiz, dirs, archivos in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".venv", "node_modules", ".git", ".next", "__pycache__",
                                                "target", "dist")]
        encontrados += [str(Path(raiz) / n) for n in archivos if n in nombres]
    # MUTACIÓN: dejar caer en el repo un archivo con el nombre de un artefacto (p. ej. `llave.dpapi`)
    # → cae e-29.
    check("e-29 · ningún archivo de custodia (llave.dpapi, *.bin del manifiesto) aparece bajo el repo",
          not encontrados)
    local = Path(os.environ.get("LOCALAPPDATA", str(tmp))) / "MIA-banco04-custodia"
    declarada = os.environ.get(custodia.ENV_CUSTODIA, "")
    rutas = [local] + ([Path(declarada)] if declarada else [])
    check("e-30 · la ubicación de la custodia (la usual y la declarada por entorno) está FUERA del repo",
          all(not (p.resolve() == ROOT.resolve() or custodia._dentro_de(p.resolve(), ROOT.resolve()))
              for p in rutas))
    campos = {"id", "tipo", "archivo", "sha256_claro", "sha256_cifrado", "bytes_claro",
              "formato_claro", "esquema"}
    check("e-31 · el manifiesto del repo trae SOLO hashes y descriptores (ningún contenido ni llave)",
          all(set(a) <= campos for a in real["artefactos"]) and len(real["artefactos"]) == 13
          and set(real["cifrado"]["llave"]) <= {"archivo", "longitud_bytes", "proteccion",
                                                "sha256_blob_dpapi"})
    # Disco: lo descifrado nunca se escribe (el texto en claro no aparece en ningún archivo).
    f = CustodiaFalsa(tmp, "disco", esquemas=esquemas)
    with f.abrir() as c:
        c.casos()
        c.clave("V1")
    hay_claro = False
    for raiz, _d, archivos in os.walk(f.carpeta.parent):
        for n in archivos:
            try:
                if CustodiaFalsa.MARCA.encode() in (Path(raiz) / n).read_bytes():
                    hay_claro = True
            except OSError:
                pass
    check("e-32 · tras cargar y cerrar, el contenido en claro no existe en ningún archivo (solo en memoria)",
          not hay_claro)
    check("e-33 · el manifiesto REAL del repo se lee y es el de este protocolo (sin abrir la custodia real)",
          custodia.cargar_manifiesto()["protocolo"] == "banco04-v1.2"
          and _falla(lambda: custodia.abrir(custodia.PROPOSITO_MEDICION, environ={}, repo_root=ROOT)))


class Muerte(BaseException):
    """El proceso muere a mitad de una corrida (nadie la captura: queda el marcador `.en_curso`)."""


class MundoF(Mundo):
    async def producir(self, caso, rep):
        k = sum(1 for c, r in self.llamadas_a_producir if (c, r) == (caso.id, rep)) + 1
        if self.fallos.get((caso.id, rep, k)) == "muerte":
            self.llamadas_a_producir.append((caso.id, rep))
            raise Muerte()
        res = await super().producir(caso, rep)
        res["material_turno"] = {"documents_map": [{"n": 1, "sha256": "x", "content": "TEXTO-EN-CLARO"}],
                                 "contenido_completo_persistido": True}
        return res


def _corre(ctx, m):
    try:
        return asyncio.run(rb.ejecutar_banco(ctx, m.deps()))
    except Muerte:
        return None


def _cifrador(tmp: Path, nombre: str):
    """Una custodia FALSA abierta, de la que sale el cifrador de registros (misma llave/algoritmo)."""
    real = json.loads((ROOT / "backend/mia/eval/banco04/custodia_manifest.json").read_text(encoding="utf-8"))
    f = CustodiaFalsa(tmp, nombre, esquemas=real["esquemas"])
    return f.abrir()


def bloque_f(tmp: Path) -> None:
    print("\n-- F · consumo desconocido duradero, custodiados aparte, guardián sin embeddings --")
    plan = rb.construir_plan(["peq-1", "peq-2", "volu-1"], ids_fuga=[], ids_voluminosos=["volu-1"],
                             r_fuga=4, r_base=2)
    # ── F1 · un proceso que muere deja un intento de consumo DESCONOCIDO que sobrevive a relanzar ──
    m = MundoF(consumo=10, fallos={("peq-1", 1, 1): "muerte"})
    ctx = _ctx(tmp, "f-huerf", plan=plan)
    check("f-1 · la muerte del proceso deja el marcador de corrida a medias", _corre(ctx, m) is None
          and rb.ruta_en_curso(ctx.salida, "0.4", "peq-1", 1).is_file())
    ctx2 = _ctx(tmp, "f-huerf", plan=plan)
    r = _corre(ctx2, m)
    reg = rb.leer_json(rb.ruta_corrida(ctx2.salida, "0.4", "peq-1", 1))
    # MUTACIÓN: en `_recuperar_huerfanas`, `if not destino.exists()` → `if False` (no deja el intento
    # duradero) → caen f-2 y f-3.
    check("f-2 · el relanzamiento lista el intento huérfano y el nuevo: dos intentos, el 1.º de "
          "infraestructura con consumo desconocido",
          reg["estado"] == "completo" and [i["n"] for i in reg["intentos"]] == [1, 2]
          and reg["intentos"][0].get("huerfano") is True and reg["intentos"][1]["estado"] == "completo")
    ctx3 = _ctx(tmp, "f-huerf", plan=plan)
    r3 = _corre(ctx3, m)
    check("f-3 · y tras OTRO relanzamiento el banco sigue «no certificable» (la fila huérfana no "
          "desaparece al borrarse el marcador)",
          ctx3.contador.cota_calculable is False and "peq-1/1/1" in ctx3.contador.claves_sin_cota()
          and r3["estado"] == "no certificable")
    m = MundoF(consumo=10, fallos={("peq-1", 1, 1): "muerte", ("peq-1", 1, 2): "muerte"})
    ctx = _ctx(tmp, "f-dos", plan=plan)
    _corre(ctx, m)
    _corre(_ctx(tmp, "f-dos", plan=plan), m)
    ctx = _ctx(tmp, "f-dos", plan=plan)
    _corre(ctx, m)
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    # MUTACIÓN: no contar los huérfanos en `n_infra` → cae f-4 (haría un tercer intento).
    check("f-4 · dos intentos huérfanos agotan el reintento de infraestructura: no hay un tercero y "
          "se listan los dos",
          reg["estado"] == "fallo_infraestructura" and len(reg["intentos"]) == 2
          and sum(1 for c, r_ in m.llamadas_a_producir if (c, r_) == ("peq-1", 1)) == 2)

    # ── F2 · un límite de uso no pierde los tokens consumidos antes de cortar ───────────────────
    m = MundoF(consumo=10, fallos={("peq-2", 1): "limite"})
    ctx = _ctx(tmp, "f-lim", plan=plan)
    _corre(ctx, m)
    m.fallos = {}
    ctx = _ctx(tmp, "f-lim", plan=plan, aprobada="Pipe #3")
    r = _corre(ctx, m)
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-2", 1))
    total_ctx = ctx.contador.claude_total
    ctx_b = _ctx(tmp, "f-lim", plan=plan)
    _corre(ctx_b, m)
    # MUTACIÓN: reutilizar la clave `caso/rep/1` tras reanudar (empezar siempre en n=1) → cae f-5.
    check("f-5 · tras reanudar con aprobación, el intento del límite y el nuevo van listados (n=1 y 2) "
          "y el consumo del que se cortó SIGUE en el total (6 corridas + 1 intento = 70)",
          r["salida"] == rb.EXIT_OK and [i["n"] for i in reg["intentos"]] == [1, 2]
          and total_ctx == 70 and ctx_b.contador.claude_total == 70)

    # ── F3 · casos custodiados: crudos aparte y sin `content` ───────────────────────────────────
    m = MundoF(consumo=10)
    cust_f = _cifrador(tmp, "cifr-f")
    ctx = _ctx(tmp, "f-cust", plan=plan, salida_custodia=tmp / "f-cust-custodia",
               ids_custodiados=frozenset({"volu-1"}), cifrar=cust_f.cifrar_registro)
    _corre(ctx, m)
    en_cust = sorted(p.name for p in (tmp / "f-cust-custodia").rglob("rep-*.json"))
    fuera = [p for p in ctx.salida.rglob("rep-*.json") if "volu-1" in str(p)]
    rc = rb.leer_json(rb.ruta_corrida(tmp / "f-cust-custodia", "0.4", "volu-1", 1))
    rv = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    # MUTACIÓN: `_base_de` devuelve siempre `ctx.salida` → cae f-6.
    check("f-6 · los crudos de un caso custodiado van a --salida-custodia y NO a la salida común",
          len(en_cust) > 0 and not fuera and rc is not None)
    # I8 · §2.3 — la salida cruda de un caso custodiado va CIFRADA, nunca en claro.
    enc = tmp / "f-cust-custodia" / "0.4" / "volu-1" / "rep-01.resultado.enc"
    claro_dec = json.loads(cust_f.descifrar_registro("0.4/volu-1/1", enc.read_bytes()).decode("utf-8"))
    en_claro = [str(p) for p in (tmp / "f-cust-custodia").rglob("*")
                if p.is_file() and b"TEXTO-EN-CLARO" in p.read_bytes()]
    en_claro += [str(p) for p in ctx.salida.rglob("*")
                 if p.is_file() and "volu-1" in str(p) and b"TEXTO-EN-CLARO" in p.read_bytes()]
    # MUTACIÓN: guardar `resultado` en claro en el registro (sin `cifrar_resultado_custodiado`) → cae f-7.
    check("f-7 · I8: el resultado de un caso custodiado se guarda CIFRADO con la llave de la custodia: en "
          "disco no hay texto en claro, el registro trae solo la ficha con hashes, y descifrado vuelve íntegro",
          not en_claro and rc["resultado"]["cifrado"] is True
          and rc["resultado"]["sha256_cifrado"] == hashlib.sha256(enc.read_bytes()).hexdigest()
          and hashlib.sha256(json.dumps(claro_dec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
          == rc["resultado"]["sha256_claro"]
          and claro_dec["material_turno"]["documents_map"][0]["content"] == "TEXTO-EN-CLARO"
          and "TEXTO-EN-CLARO" in json.dumps(rv))
    check("f-7b · el registro cifrado solo autentica con su propio id (otro id no descifra)",
          _falla(lambda: cust_f.descifrar_registro("0.4/volu-1/2", enc.read_bytes())))
    m8 = MundoF(consumo=1)
    try:
        asyncio.run(rb.ejecutar_banco(_ctx(tmp, "f-cust2", plan=plan, salida_custodia=tmp / "f-c2",
                                           ids_custodiados=frozenset({"volu-1"})), m8.deps()))
        ok = False
    except rb.BancoAbortado:
        ok = not any(c_ == "volu-1" for c_, _r in m8.llamadas_a_producir)   # y sin gastar cuota
    # MUTACIÓN: quitar el `if ... ctx.cifrar is None: raise` de `_ejecutar_una` → cae f-8 (correría en claro).
    check("f-8 · un caso custodiado SIN cifrador no se corre (antes de llamar al modelo)", ok)
    repo = tmp / "repo-f"
    home = tmp / "home-f"
    sal = tmp / "salida-f"
    repo.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)

    def vsc(dest):
        return rb.verificar_salida_custodia(dest, repo_root=repo, mia_home=home, salida=sal)
    # MUTACIÓN: quitar la comparación con MIA_HOME → cae f-9.
    check("f-9 · la carpeta de custodia no puede estar bajo el repo, bajo MIA_HOME, ni ser (o contener) "
          "la salida común; una carpeta aparte sí",
          _rechaza(lambda: vsc(repo / "c")) and _rechaza(lambda: vsc(home / "c"))
          and _rechaza(lambda: vsc(sal)) and _rechaza(lambda: vsc(sal / "c"))
          and _rechaza(lambda: vsc(tmp)) and vsc(tmp / "aparte-ok"))
    # `main`: --incluir-custodiados exige --salida-custodia válida.
    snap = dict(os.environ)
    root_real, rb.ROOT = rb.ROOT, repo
    try:
        _, e = _entorno_aislado(tmp, "fmain", MIA_HOME=str(home))
        os.environ["MIA_TEST_ENV_FILE"] = str(e)
        os.environ.pop("CI", None)
        base = ["--plan", "--version", "0.4", "--sha", "a", "--salida", str(sal), "--incluir-custodiados"]
        c1 = rb.main(base)
        c2 = rb.main(base + ["--salida-custodia", str(home / "c")])
        c3 = rb.main(base + ["--salida-custodia", str(tmp / "aparte-main")])
    finally:
        rb.ROOT = root_real
        os.environ.clear()
        os.environ.update(snap)
    check("f-10 · main: --incluir-custodiados sin --salida-custodia o con una bajo MIA_HOME → código 3; "
          "con una válida pasa",
          (c1, c2, c3) == (rb.EXIT_RECHAZADO, rb.EXIT_RECHAZADO, rb.EXIT_OK))

    # ── F4 · el guardián del banco no cuenta los embeddings como cuota del modelo ──────────────
    from mia.eval import spend_guard
    g = rb.crear_guardian_banco(
        spend_guard, run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0,
        closeout_reserve_usd=0.0, session_id="s-banco04-f", ledger_path=tmp / "f.json")
    g.note_call(alias=spend_guard.embed_alias(), prompt_tokens=1000, completion_tokens=0,
                total_tokens=1000, cost_usd=0.0, seconds=0.1)
    g.note_call(alias="claude-sonnet", prompt_tokens=30, completion_tokens=20, total_tokens=50,
                cost_usd=0.0, seconds=0.1)
    # MUTACIÓN: no separar por alias de embeddings en `note_call` → cae f-11.
    check("f-11 · tokens_llm/llamadas_llm excluyen los embeddings de la siembra (1050 totales, 50 del modelo)",
          g.total_tokens == 1050 and g.tokens_llm == 50 and g.llamadas_llm == 1)


def bloque_b2(tmp: Path) -> None:
    print("\n-- B2 · C8: la lista REAL de fragmentos que entraron al prompt --")
    from mia import config
    from mia.agents import untrusted
    from mia.eval import cases as cases_mod
    from mia.eval import harness, spend_guard

    spend_guard.ensure_installed()
    from mia.agent import llm as llm_mod

    def frag(i, doc, ord_, texto):
        return {"id": f"c{i}", "content": texto, "filename": doc, "document_id": f"id-{doc}",
                "ord": ord_, "folio_ancla": None}

    docs = [frag(1, "a.txt", 0, "A" * 400), frag(2, "a.txt", 1, "B" * 400), frag(3, "b.txt", 0, "C" * 400)]
    extra = frag(9, "b.txt", 7, "RELECTURA " * 20)
    caso = cases_mod.GoldenCase(id="t-b2", title="t", message="hola", synthetic=True)

    class Grafo:
        def __init__(self, guion):
            self.guion = guion

        async def astream(self, inp, cfg, stream_mode=None):
            await self.guion()
            yield {}

        async def aget_state(self, cfg):
            return SimpleNamespace(values={"documents": docs, "draft": "Borrador.", "metadata": {
                "diagnosis": "Dx.", "retrieved": 3}})

    @asynccontextmanager
    async def cp():
        yield object()

    async def sembrar(tenant, c):
        return "m-1"

    guard = spend_guard.EvalSpendGuard(
        run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0, closeout_reserve_usd=0.0,
        session_id="s-b2", ledger_path=tmp / "b2.json")
    orig = (harness._seed_case_matter, harness.open_checkpointer, harness.build_matter_graph,
            config.MIA_HOME, llm_mod.call_llm)
    original_render = untrusted.render_documents

    def llamar(task, doc_list, *, falla=False, extra_texto=""):
        ctx = untrusted.render_documents(doc_list)
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": ctx + extra_texto}]
        return llm_mod.call_llm(msgs, task=task)

    async def correr(guion, fake_llm, romper=False):
        harness._seed_case_matter, harness.open_checkpointer = sembrar, cp
        harness.build_matter_graph = lambda checkpointer: Grafo(guion)
        config.MIA_HOME = tmp / "home-b2"
        llm_mod.call_llm = fake_llm
        if romper:
            del llm_mod.call_llm
        with guard.activate():
            return await harness.run_case("t-b2", caso, tenant_allow_real=False)

    try:
        # Escenario 1: el 1.º intento desborda el contexto; el nodo recorta (2 de 3, truncados) y reintenta.
        def llm1(messages, *a, **k):
            if "C" * 400 in messages[1]["content"]:
                raise RuntimeError("context_too_long")
            return "ok"

        async def guion1():
            try:
                llamar("legal_analysis", docs)
            except RuntimeError:
                pass
            from mia.agents import context_recovery as cr
            recortados = [dict(docs[0], content="A" * 100 + cr.DOC_TRUNCATED_MARKER),
                          dict(docs[1], content="B" * 100 + cr.DOC_TRUNCATED_MARKER)]
            llamar("legal_analysis", recortados)
            # relectura dirigida: un fragmento que NO está en state["documents"]
            llamar("legal_draft", recortados + [extra])

        r = asyncio.run(correr(guion1, llm1))
        mt = r["material_turno"]
        fp = mt["fragmentos_en_prompt"]
        # MUTACIÓN: contar también las llamadas que fallaron (quitar `if not llamada["ok"]: continue`)
        # → cae g-1 (entraría el fragmento c3 del intento que desbordó).
        check("g-1 · lo que entró COMPLETO es lo del intento que TERMINÓ bien: c3 (intento que desbordó) no "
              "cuenta; sí el fragmento de la relectura (no está en state['documents']); los dos recortados "
              "NO entran como leídos",
              mt["entraron"] == [["b.txt", 7]] and fp["medido"] is True
              and [c["ok"] for c in fp["llamadas"]] == [False, True, True])
        det = {(d["filename"], d["ord"]): d for d in fp["detalle"]}
        # MUTACIÓN: contar un fragmento cortado como completo (ignorar `marcador_en_el_mayor`) → cae g-2.
        check("g-2 · I3: un fragmento recortado se persiste como PARCIAL con el TRAMO enviado [0, 100) de "
              "400 y va a `entraron_parcial`, nunca a `entraron`",
              mt["entraron_parcial"] == [["a.txt", 0], ["a.txt", 1]]
              and det[("a.txt", 0)]["tramos"] == [[0, 100]] and det[("a.txt", 0)]["chars_original"] == 400
              and det[("a.txt", 0)]["parcial"] is True and det[("a.txt", 0)]["completo"] is False
              and ["a.txt", 0] not in mt["entraron"])
        tr = {(t["documento"], t["indice"]): t for t in mt["entraron_tramos"]}
        check("g-2b · `entraron_tramos` trae (documento, índice, id, chars_original, tramos, completo) de "
              "cada fragmento visto: el cotejo de disponibilidad se hace contra los TRAMOS",
              tr[("a.txt", 1)] == {"documento": "a.txt", "indice": 1, "id": "c2", "chars_original": 400,
                                   "tramos": [[0, 100]], "completo": False}
              and tr[("b.txt", 7)]["tramos"] == [[0, 200]] and tr[("b.txt", 7)]["completo"] is True)
        check("g-3 · cada fragmento lleva su id estable, su documento y su índice, y la lista de "
              "intake sigue ahí (los 3)",
              det[("a.txt", 1)]["id"] == "c2" and det[("a.txt", 1)]["document_id"] == "id-a.txt"
              and [m["n"] for m in mt["documents_map"]] == [1, 2, 3])
        check("g-4 · los parches se restauran: render_documents es el original y call_llm el que había",
              untrusted.render_documents is original_render and llm_mod.call_llm is llm1)
        check("g-5 · es JSON y pasa por persist_report",
              bool(harness.persist_report({"run_id": "b2", "cases": [r]}, base_dir=str(tmp / "evr2"))))

        # Escenario 2: expediente vacío → nada entró y es una medición válida (lista vacía, no None).
        async def guion2():
            llamar("legal_analysis", [])

        r2 = asyncio.run(correr(guion2, lambda m, *a, **k: "ok"))
        check("g-6 · sin documentos la lista es [] (medida), no None",
              r2["material_turno"]["entraron"] == [] and r2["material_turno"]["fragmentos_en_prompt"]["medido"])

        # Escenario 3: un prompt con sellos que no coincide con ningún render (p. ej. comprimido).
        async def guion3():
            untrusted.render_documents(docs)
            llm_mod.call_llm([{"role": "user", "content": "<<<DOC 1>>> resumido por el compresor"}],
                             task="legal_analysis")

        r3 = asyncio.run(correr(guion3, lambda m, *a, **k: "ok"))
        fp3 = r3["material_turno"]["fragmentos_en_prompt"]
        # MUTACIÓN: no contar `sin_identificar` → cae g-7.
        check("g-7 · un prompt con sellos que no se puede identificar se declara (no completo), sin "
              "inventar fragmentos",
              fp3["llamadas_sin_identificar"] == 1 and fp3["completo"] is False
              and r3["material_turno"]["entraron"] == [])

        # Escenario 4: si la captura no se puede instalar, el turno SIGUE y `entraron` queda None.
        async def guion4():
            return None

        r4 = asyncio.run(correr(guion4, None, romper=True))
        # MUTACIÓN: `entraron` = [] aunque no se haya medido → cae g-8.
        check("g-8 · si la captura no se instala el turno SIGUE y `entraron` es None (sin medición: "
              "no se presume lectura), con el error declarado",
              r4.get("score") is not None and r4["material_turno"]["entraron"] is None
              and "instalacion" in (r4["material_turno"]["fragmentos_en_prompt"]["error_captura"] or ""))
    finally:
        (harness._seed_case_matter, harness.open_checkpointer, harness.build_matter_graph,
         config.MIA_HOME, llm_mod.call_llm) = orig
        untrusted.render_documents = original_render


class MundoA(MundoF):
    """Doble de las APROBACIONES: despacho propio por aprobación, turno reproducido y aprobar."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.abiertos, self.cerrados, self.consumo_turno, self.consumo_aprob = [], [], 30, 20
        self.fallos_apr, self.no_aprobable, self.pendientes, self.codex_por_run = {}, False, 0, 0
        self.orden = []

    async def abrir(self, caso):
        k = sum(1 for c in self.abiertos if c == caso.id) + 1
        self.abiertos.append(caso.id)
        accion = self.fallos_apr.get((caso.id, k))
        if accion == "infra":
            raise RuntimeError("proceso muerto antes de llamar al modelo")
        if accion == "muerte":
            raise Muerte()
        return {"caso": caso.id, "k": k}

    async def producir_apr(self, h, caso):
        self.orden.append(("turno", h["caso"], h["k"]))
        self.calls += 1
        self.tokens += self.consumo_turno
        if self.fallos_apr.get((caso.id, h["k"])) == "limite":
            raise RuntimeError("usage limit reached")
        if self.fallos_apr.get((caso.id, h["k"])) == "producto":
            raise RuntimeError("el turno falló tras llamar al modelo")
        return {"matter_id": "m", "case_id": caso.id}

    async def aprobar(self, h, res):
        self.orden.append(("aprobar", h["caso"], h["k"]))
        self.calls += 1
        self.tokens += self.consumo_aprob
        if self.no_aprobable:
            return {"aprobada": False, "motivo": "verificación"}
        return {"aprobada": True, "trabajos": {"pendientes": self.pendientes}}

    async def cerrar(self, h):
        self.cerrados.append(h)

    def deps_apr(self):
        d = self.deps()
        return rb.DepsAprobacion(
            abrir_despacho=self.abrir, producir_hasta_revision=self.producir_apr, aprobar=self.aprobar,
            cerrar_despacho=self.cerrar, marca=d.marca, consumo_desde=d.consumo_desde,
            paradas=(), reloj=d.reloj)


def _corre_apr(ctx, m):
    try:
        return asyncio.run(rb.ejecutar_aprobaciones(ctx, m.deps_apr()))
    except Muerte:
        return None


def bloque_h(tmp: Path) -> None:
    print("\n-- H · aprobaciones, ledger del juicio, Codex aparte y reserva del Bloque 7 --")
    from mia.eval import spend_guard
    from mia.eval.banco04 import protocolo as pr

    # ── H1 · Bloque 7: reserva del juicio ──────────────────────────────────────────────────────
    k7 = rb.constantes_de_protocolo(pr, 7)
    check("h-1 · Bloque 7: techos 32 M / 8 M y la reserva del juicio 13 M Claude / 6 M Codex DECLARADA en "
          "protocolo.py (C17), leída de ahí",
          (k7["techo_claude"], k7["techo_codex"]) == (32_000_000, 8_000_000)
          and pr.RESERVA_JUICIO["bloque7"] == {"claude": 13_000_000, "codex": 6_000_000}
          and (k7["reserva_claude"], k7["reserva_codex"]) == (13_000_000, 6_000_000)
          and k7["reserva_fuente"] == "protocolo.py")
    # Mutación EN COPIA (no en el repo): un protocolo al que se le borra la entrada bloque7.
    sin7 = SimpleNamespace(
        TECHOS_CIRCUITO=pr.TECHOS_CIRCUITO,
        RESERVA_JUICIO={k_: v for k_, v in pr.RESERVA_JUICIO.items() if k_ != "bloque7"},
        R_CONTINGENCIA_PEQUENOS_SIN_FUGA=3, ROTULO_SUSPENSION=pr.ROTULO_SUSPENSION, N_CASOS_TOTAL=17)
    try:
        rb.constantes_de_protocolo(sin7, 7)
        ok = False
    except rb.BancoAbortado:
        ok = True
    # MUTACIÓN: reintroducir un fallback (valor por defecto) para bloque7 en el runner → cae h-2.
    check("h-2 · sin RESERVA_JUICIO['bloque7'] en protocolo.py el runner NO arranca (fail-closed, sin "
          "fallback)", ok)
    falso = SimpleNamespace(
        TECHOS_CIRCUITO=pr.TECHOS_CIRCUITO, RESERVA_JUICIO={"bloque7": {"claude": 9, "codex": 3}},
        R_CONTINGENCIA_PEQUENOS_SIN_FUGA=3, ROTULO_SUSPENSION=pr.ROTULO_SUSPENSION, N_CASOS_TOTAL=17)
    k7b = rb.constantes_de_protocolo(falso, 7)
    check("h-2b · lo que declara protocolo.py MANDA (9/3 en una copia)",
          (k7b["reserva_claude"], k7b["reserva_codex"], k7b["reserva_fuente"]) == (9, 3, "protocolo.py"))
    k0 = rb.constantes_de_protocolo(pr, 0)
    check("h-3 · el Bloque 0 sigue leyendo protocolo.py (7 M y todo Codex)",
          k0["reserva_claude"] == 7_000_000 and k0["reserva_codex"] == 5_000_000
          and k0["reserva_fuente"] == "protocolo.py")

    # ── H2 · Codex contabilizado aparte ────────────────────────────────────────────────────────
    g = rb.crear_guardian_banco(
        spend_guard, run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0,
        closeout_reserve_usd=0.0, session_id="s-banco04-h", ledger_path=tmp / "h.json")
    m0 = rb.marca_guardian(g)
    g.note_call(alias=spend_guard.embed_alias(), prompt_tokens=1000, completion_tokens=0,
                total_tokens=1000, cost_usd=0.0, seconds=0.1)
    g.note_call(alias="cli-claude-opus", prompt_tokens=30, completion_tokens=20, total_tokens=50,
                cost_usd=0.0, seconds=0.1)
    g.note_call(alias="cli-codex", prompt_tokens=500, completion_tokens=200, total_tokens=700,
                cost_usd=0.0, seconds=0.1)
    g.intentos_fallidos = [
        {"alias": "cli-claude-sonnet", "tokens_cota_superior": 100, "consumo_conocido": False},
        {"alias": "cli-codex-eval", "tokens_cota_superior": 40, "consumo_conocido": False}]
    c = rb.consumo_desde_guardian(g, m0)
    # MUTACIÓN: no separar `es_alias_codex` en `note_call` (todo a Claude) → cae h-4.
    check("h-4 · el guardián separa Claude (50), Codex (700) y embeddings (1000): Codex NO suma a Claude",
          g.tokens_llm == 50 and g.tokens_codex == 700 and c["claude_conocido"] == 50
          and c["codex_conocido"] == 700 and c["llamadas"] == 2)
    # MUTACIÓN: no repartir los intentos fallidos por alias en `consumo_desde_guardian` → cae h-5.
    check("h-5 · los intentos fallidos también se reparten por alias (cota Claude 100, cota Codex 40)",
          [f["tokens_cota_superior"] for f in c["fallidos"]] == [100]
          and [f["tokens_cota_superior"] for f in c["codex_fallidos"]] == [40])
    cont = rb.ContadorCuota(techo_claude=10_000, techo_codex=5_000, reserva_juicio_claude=2_000,
                            reserva_juicio_codex=5_000)
    rb.registrar_consumo(cont, "x/1/1", "produccion", c)
    check("h-6 · el contador lleva Claude (50 + 100) y Codex (700 + 40) por SEPARADO y avisa del Codex "
          "consumido en producción con toda su cuota reservada",
          cont.claude_total == 150 and cont.codex_total == 740 and cont.codex_produccion == 740
          and any("Codex" in a for a in cont.advertencias())
          and cont.resumen()["codex_produccion"] == 740)

    class MundoCodex(MundoF):
        def deps(self):
            d = super().deps()
            base = d.consumo_desde

            def desde(mm):
                out = base(mm)
                out["codex_conocido"] = 5 * out["llamadas"]
                return out
            d.consumo_desde = desde
            return d

    plan = rb.construir_plan(["peq-1", "peq-2", "volu-1"], ids_fuga=[], ids_voluminosos=["volu-1"],
                             r_fuga=4, r_base=2)
    m = MundoCodex(consumo=100)
    ctx = _ctx(tmp, "h-codex", plan=plan)
    _corre(ctx, m)
    ctx2 = _ctx(tmp, "h-codex", plan=plan)
    _corre(ctx2, m)
    check("h-7 · el Codex de cada corrida se persiste y SOBREVIVE al relanzamiento, separado de "
          "Claude (6 corridas: Claude 600, Codex 30)",
          ctx.contador.claude_total == 600 and ctx.contador.codex_total == 30
          and ctx2.contador.claude_total == 600 and ctx2.contador.codex_total == 30)

    # ── H3 · el ledger del juicio ──────────────────────────────────────────────────────────────
    sal = tmp / "salida-h-led"
    for etapa, i in (("juicio", "j1"), ("adjudicacion", "a1"), ("validacion", "v1"), ("estabilidad", "e1")):
        rb.registrar_consumo_externo(sal, "0.4", id_=i, etapa=etapa, claude_conocido=100,
                                     codex_conocido=10)
    rb.registrar_consumo_externo(sal, "0.4", id_="j1", etapa="juicio", claude_conocido=100,
                                 codex_conocido=10)                           # idempotente por id
    ctx = _ctx(tmp, "h-led", plan=plan, techo=10_000, reserva=2_000)
    ctx.contador.registrar("prod", rubro="produccion", claude_conocido=50)
    rb.cargar_contador_desde_disco(ctx)
    # MUTACIÓN: no llamar a `_cargar_aprobaciones_y_juicio` en el cargador → cae h-8.
    check("h-8 · el consumo del juicio, la adjudicación, la validación y la estabilidad (Claude y "
          "Codex) entra al contador desde el ledger, idempotente por id",
          ctx.contador.claude_total == 450 and ctx.contador.codex_total == 40)
    check("h-9 · el juicio cuenta para el techo pero NO para el tope de producción (reserva)",
          ctx.contador.claude_produccion == 50 and ctx.contador.tope_produccion_claude == 8_000)
    for mal in (lambda: rb.registrar_consumo_externo(sal, "0.4", id_="x", etapa="produccion"),
                lambda: rb.registrar_consumo_externo(sal, "0.4", id_="../x", etapa="juicio")):
        try:
            mal()
            ok = False
        except ValueError:
            ok = True
        if not ok:
            break
    check("h-10 · una etapa que no es de juicio o un id con ruta se rechazan", ok)
    rb.registrar_consumo_externo(sal, "0.4", id_="j2", etapa="juicio", claude_conocido=1,
                                 claude_fallidos=[{"tokens_cota_superior": None}])
    ctx = _ctx(tmp, "h-led", plan=plan)
    rb.cargar_contador_desde_disco(ctx)
    check("h-11 · un fallo del juicio sin cota deja el techo NO certificable (P10)",
          ctx.contador.cota_calculable is False)
    # Bloque 7: dos versiones suman contra UN techo
    m = MundoF(consumo=10)
    ca = _ctx(tmp, "h-v", plan=plan)
    _corre(ca, m)
    cb = _ctx(tmp, "h-v", plan=plan)
    cb.version = "0.3.3"
    _corre(cb, m)
    cc = _ctx(tmp, "h-v", plan=plan, versiones_contador=("0.4", "0.3.3"))
    rb.cargar_contador_desde_disco(cc)
    # MUTACIÓN: `_versiones` devolver solo `ctx.version` → cae h-12.
    check("h-12 · Bloque 7: 0.4 y 0.3.3 suman contra el MISMO techo (60 + 60 = 120)",
          cc.contador.claude_total == 120 and ca.contador.claude_total == 60)

    # ── H4 · ejecutor de las aprobaciones ──────────────────────────────────────────────────────
    m = MundoA(consumo=100)
    ctx = _ctx(tmp, "h-ap", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    plan_ap = rb.leer_json(ctx.salida / "0.4" / "aprobaciones_plan.json")
    ctx_a = _ctx(tmp, "h-ap", plan=plan, consumo_aprobaciones=60)
    r = _corre_apr(ctx_a, m)
    regs = {c.id: rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", c.id)) for c in plan}
    hechos = len([1 for _ in m.abiertos])
    # MUTACIÓN: no abrir un despacho por aprobación (reutilizar uno) → cae h-13.
    check("h-13 · UNA aprobación por caso (3), cada una en su PROPIO despacho (se abre y se cierra uno "
          "por aprobación)",
          r["salida"] == rb.EXIT_OK and hechos == 3 and len(m.cerrados) == 3
          and sorted(h["caso"] for h in m.cerrados) == ["peq-1", "peq-2", "volu-1"]
          and all(g["estado"] == "completo" for g in regs.values()))
    check("h-14 · cada aprobación corre sobre la repetición que eligió el plan",
          {e["caso"] for e in plan_ap["elegidas"]} == {"peq-1", "peq-2", "volu-1"}
          and all(regs[e["caso"]]["rep"] == e["rep"] for e in plan_ap["elegidas"]))
    # MUTACIÓN: `consumo_aprobacion` = todo (turno + aprobar) → cae h-15.
    check("h-15 · la cifra de §5.5/§6.3 para la aprobación es SOLO aprobar + trabajos (20), y el turno "
          "reproducido (30) queda aparte",
          all(g["consumo_aprobacion"]["claude_conocido"] == 20
              and g["consumo_turno_reproducido"]["claude_conocido"] == 30 for g in regs.values()))
    check("h-16 · el contador suma las aprobaciones a la producción (600 + 3·50 = 750) y ambas gastan cuota",
          ctx_a.contador.claude_total == 750 and ctx_a.contador.claude_produccion == 750)
    n_antes = len(m.abiertos)
    ctx_b = _ctx(tmp, "h-ap", plan=plan, consumo_aprobaciones=60)
    r2 = _corre_apr(ctx_b, m)
    check("h-17 · relanzar no repite aprobaciones hechas y el contador no cambia (idempotente)",
          len(m.abiertos) == n_antes and ctx_b.contador.claude_total == 750 and r2["salida"] == rb.EXIT_OK)
    est = rb.leer_json(ctx.salida / "0.4" / "aprobaciones_estado.json")
    check("h-18 · al terminar, estado de las aprobaciones escrito", est["estado"] == "aprobaciones_terminadas")

    # no aprobable / trabajos pendientes → no certificable
    m = MundoA(consumo=100)
    m.no_aprobable = True
    ctx = _ctx(tmp, "h-ap2", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    r = _corre_apr(_ctx(tmp, "h-ap2", plan=plan, consumo_aprobaciones=60), m)
    check("h-19 · si la revisión no permite aprobar, queda `no_aprobable` y el banco «no certificable»",
          r["estado"] == "no certificable" and any("no_aprobable" in x for x in r["detalle"]["motivos"]))
    m = MundoA(consumo=100)
    m.pendientes = 2
    ctx = _ctx(tmp, "h-ap3", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    r = _corre_apr(_ctx(tmp, "h-ap3", plan=plan, consumo_aprobaciones=60), m)
    # MUTACIÓN: no mirar `trabajos.pendientes` en el resumen → cae h-20.
    check("h-20 · trabajos de aprendizaje sin terminar al aprobar → «no certificable»",
          r["estado"] == "no certificable" and any("trabajos" in x for x in r["detalle"]["motivos"]))

    # infraestructura: UN reintento, y el despacho se cierra siempre
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-1", 1): "infra"}
    ctx = _ctx(tmp, "h-ap4", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    r = _corre_apr(_ctx(tmp, "h-ap4", plan=plan, consumo_aprobaciones=60), m)
    g1 = rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1"))
    check("h-21 · un fallo de infraestructura de la aprobación se reintenta UNA vez y se listan los dos "
          "intentos",
          g1["estado"] == "completo" and [i["n"] for i in g1["intentos"]] == [1, 2]
          and g1["intentos"][0]["clase"] == "infraestructura")
    # muerte del proceso a mitad de una aprobación: consumo desconocido y duradero
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-1", 1): "muerte"}
    ctx = _ctx(tmp, "h-ap5", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    _corre_apr(_ctx(tmp, "h-ap5", plan=plan, consumo_aprobaciones=60), m)
    ctxm = _ctx(tmp, "h-ap5", plan=plan, consumo_aprobaciones=60)
    r = _corre_apr(ctxm, m)
    gm = rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1"))
    ctxm2 = _ctx(tmp, "h-ap5", plan=plan, consumo_aprobaciones=60)
    _corre_apr(ctxm2, m)
    # MUTACIÓN: no convertir el marcador `aprob.en_curso` huérfano en intento duradero → cae h-22.
    check("h-22 · una aprobación que murió a medias deja un intento de consumo DESCONOCIDO que sobrevive "
          "a relanzar: «no certificable»",
          gm["estado"] == "completo" and gm["intentos"][0].get("huerfano") is True
          and ctxm2.contador.cota_calculable is False)
    # límite de uso: suspende; techo: no empieza otra
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-2", 1): "limite"}
    ctx = _ctx(tmp, "h-ap6", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    r = _corre_apr(_ctx(tmp, "h-ap6", plan=plan, consumo_aprobaciones=60), m)
    check("h-23 · un límite de uso durante una aprobación SUSPENDE («incompleto — no certificable»)",
          r["salida"] == rb.EXIT_SUSPENDIDO and r["estado"] == "incompleto — no certificable"
          and rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-2")) is None)
    # reanudar sin aprobación de Pipe (el contador está lejos del techo: solo la falta de aprobación frena)
    m.fallos_apr = {}
    abiertos1 = len(m.abiertos)
    r_sin = _corre_apr(_ctx(tmp, "h-ap6", plan=plan, consumo_aprobaciones=60), m)
    sin_nuevas = len(m.abiertos) == abiertos1
    r_con = _corre_apr(_ctx(tmp, "h-ap6", plan=plan, consumo_aprobaciones=60, aprobada="Pipe #9"), m)
    # MUTACIÓN: quitar el `return` de suspensión sin aprobación en `ejecutar_aprobaciones` → cae h-23b.
    check("h-23b · fase de aprobaciones suspendida: sin aprobación de Pipe no reanuda; con ella termina",
          r_sin["salida"] == rb.EXIT_SUSPENDIDO and sin_nuevas and r_con["salida"] == rb.EXIT_OK
          and len(m.abiertos) > abiertos1)
    m = MundoA(consumo=100)
    ctx = _ctx(tmp, "h-ap7", plan=plan, consumo_aprobaciones=0, techo=700, reserva=0)
    _corre(ctx, m)
    ctxt = _ctx(tmp, "h-ap7", plan=plan, consumo_aprobaciones=300, techo=700, reserva=0)
    abiertos0 = len(m.abiertos)
    r = _corre_apr(ctxt, m)
    # MUTACIÓN: no consultar `motivo_suspension` antes de cada aprobación → cae h-24.
    check("h-24 · las aprobaciones respetan el techo y la reserva del juicio ANTES de empezar cada una",
          r["salida"] == rb.EXIT_SUSPENDIDO and len(m.abiertos) == abiertos0 + 1
          and ctxt.contador.claude_produccion <= ctxt.contador.tope_produccion_claude)
    # producto: no se reintenta; dos fallos de infraestructura: no hay un tercer intento
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-1", 1): "producto"}
    ctx = _ctx(tmp, "h-ap9", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    _corre_apr(_ctx(tmp, "h-ap9", plan=plan, consumo_aprobaciones=60), m)
    g1 = rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1"))
    # MUTACIÓN: tratar `producto` como reintentable en `_ejecutar_una_aprobacion` → cae h-27.
    check("h-27 · una aprobación que falla tras llamar al modelo (producto) NO se reintenta y cuenta",
          g1["estado"] == "fallo_producto" and len(g1["intentos"]) == 1
          and sum(1 for c_ in m.abiertos if c_ == "peq-1") == 1)
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-1", 1): "infra", ("peq-1", 2): "infra", ("peq-1", 3): "infra"}
    ctx = _ctx(tmp, "h-ap10", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    _corre_apr(_ctx(tmp, "h-ap10", plan=plan, consumo_aprobaciones=60), m)
    g1 = rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1"))
    check("h-28 · dos fallos de infraestructura en la aprobación agotan el reintento: no hay tercero",
          g1["estado"] == "fallo_infraestructura" and len(g1["intentos"]) == 2
          and sum(1 for c_ in m.abiertos if c_ == "peq-1") == 2)
    ctx = _ctx(tmp, "h-ap11", plan=plan, consumo_aprobaciones=60)
    ctx.casos["peq-1"] = SimpleNamespace(id="peq-1", synthetic=False)
    m = MundoA(consumo=100)
    _ctx0 = _ctx(tmp, "h-ap11", plan=plan, consumo_aprobaciones=60)
    _corre(_ctx0, m)
    try:
        asyncio.run(rb.ejecutar_aprobaciones(ctx, m.deps_apr()))
        ok = False
    except rb.BancoAbortado:
        ok = True
    check("h-29 · una aprobación sobre un caso no sintético aborta (§9.3)", ok)
    # varias muertes seguidas en la aprobación: el intento previo no se pisa al reanudar
    m = MundoA(consumo=100)
    m.fallos_apr = {("peq-1", 1): "muerte", ("peq-1", 2): "muerte"}
    ctx = _ctx(tmp, "h-ap12", plan=plan, consumo_aprobaciones=60)
    _corre(ctx, m)
    _corre_apr(_ctx(tmp, "h-ap12", plan=plan, consumo_aprobaciones=60), m)
    _corre_apr(_ctx(tmp, "h-ap12", plan=plan, consumo_aprobaciones=60), m)
    _corre_apr(_ctx(tmp, "h-ap12", plan=plan, consumo_aprobaciones=60), m)
    g1 = rb.leer_json(rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1"))
    # MUTACIÓN: `n_infra = 0` o `n = 0` en `_ejecutar_una_aprobacion` → cae h-30.
    check("h-30 · dos aprobaciones huérfanas agotan el reintento (2 intentos listados, ninguno pisado)",
          g1 is not None and g1["estado"] == "fallo_infraestructura"
          and [i["n"] for i in g1["intentos"]] == [1, 2] and all(i.get("huerfano") for i in g1["intentos"]))
    # custodiados: aprobaciones a la carpeta aparte
    m = MundoA(consumo=100)
    ctx = _ctx(tmp, "h-ap8", plan=plan, consumo_aprobaciones=60, salida_custodia=tmp / "h-ap8-cust",
               ids_custodiados=frozenset({"volu-1"}), cifrar=_cifrador(tmp, "cifr-h").cifrar_registro)
    _corre(ctx, m)
    ctxc = _ctx(tmp, "h-ap8", plan=plan, consumo_aprobaciones=60, salida_custodia=tmp / "h-ap8-cust",
                ids_custodiados=frozenset({"volu-1"}))
    _corre_apr(ctxc, m)
    check("h-25 · la aprobación de un caso custodiado también va a la carpeta de custodia",
          rb.ruta_aprobacion(tmp / "h-ap8-cust", "0.4", "volu-1").is_file()
          and not rb.ruta_aprobacion(ctx.salida, "0.4", "volu-1").exists()
          and rb.ruta_aprobacion(ctx.salida, "0.4", "peq-1").is_file())
    try:
        asyncio.run(rb.ejecutar_aprobaciones(_ctx(tmp, "h-vacio", plan=plan), MundoA().deps_apr()))
        ok = False
    except rb.BancoAbortado:
        ok = True
    check("h-26 · sin aprobaciones_plan.json (producción sin terminar) la fase de aprobaciones no corre", ok)


def bloque_i(tmp: Path) -> None:
    print("\n-- I · cota efectiva (CLI), reserva Codex, ledger del juicio y manifiesto de ejecución --")
    from mia.eval import spend_guard

    # ── I4 · la cota de salida solo vale si el proveedor la aplica ─────────────────────────────
    spend_guard.ensure_installed()

    def guardia(nombre):
        return spend_guard.EvalSpendGuard(
            run_limit_usd=10.0, session_limit_usd=30.0, global_limit_usd=100.0, closeout_reserve_usd=0.0,
            session_id="s-banco04-i", ledger_path=tmp / f"{nombre}.json")

    def fallar(g, alias):
        prev = spend_guard._original_invoke

        def falso(client, a, kw, task=None, *x):
            raise RuntimeError("timeout del CLI")
        spend_guard._original_invoke = falso
        try:
            with g.activate(), g.case("c"):
                try:
                    spend_guard._guarded_invoke(None, alias, {"messages": [{"role": "user", "content": "x" * 400}],
                                                              "max_tokens": 500})
                except RuntimeError:
                    pass
        finally:
            spend_guard._original_invoke = prev
        return (g.intentos_fallidos or [{}])[0]

    from mia.agent import subscription_llm as sub
    from mia.agent import llm as llm_mod
    cdx = {a: fallar(guardia(f"i4{i}"), a) for i, a in enumerate(("cli-codex", "cli-codex-eval"))}
    opus = fallar(guardia("i4opus"), "cli-claude-opus")
    api = fallar(guardia("i4api"), "claude-sonnet")
    # MUTACIÓN: en `cota_salida_cli`, devolver siempre None (sin cota real para el CLI) → cae i-1.
    check("i-1 · I4: un timeout de Opus por CLI de UN turno sin herramientas queda con cota REAL = entrada "
          "estimada + máximo de salida documentado (131 072), fuente declarada, y el max_tokens pedido "
          "(que el CLI descarta) solo como dato",
          opus["cota_aplicada"] is True and opus["cota_fuente"] == "maximo_documentado_cli_un_turno"
          and opus["cota_salida"] == 131_072 and opus["max_tokens_pedido"] == 500
          and opus["tokens_cota_superior"] == opus["tokens_entrada_estimados"] + 131_072)
    # MUTACIÓN: dar a Codex el máximo de Claude (o inventar uno) en `CLI_SALIDA_MAXIMA["codex"]` → cae i-1b.
    check("i-1b · Codex (gpt-5.6-sol): SIN máximo de salida documentado → cota desconocida, con el motivo",
          all(v["cota_aplicada"] is False and v["cota_salida"] is None and v["tokens_cota_superior"] is None
              and "sin máximo" in (v["motivo_cota"] or "") for v in cdx.values()))
    check("i-1c · la tabla de máximos está VERSIONADA con fuente y fecha",
          spend_guard.CLI_SALIDA_MAXIMA["version"] == "2026-10-12"
          and "platform.claude.com" in spend_guard.CLI_SALIDA_MAXIMA["fuente"]
          and spend_guard.CLI_SALIDA_MAXIMA["codex"] == {})
    # Un bucle / herramientas: la invocación REAL cambia y la cota vuelve a ser desconocida.
    base_flags = list(sub._BASE_FLAGS)
    try:
        sub._BASE_FLAGS[:] = [f for f in base_flags if f != "--max-turns"]      # sin tope de turnos
        sin_turnos = fallar(guardia("i4t"), "cli-claude-opus")
        sub._BASE_FLAGS[:] = ["Bash" if f == "" else f for f in base_flags]      # herramientas habilitadas
        con_tools = fallar(guardia("i4h"), "cli-claude-opus")
    finally:
        sub._BASE_FLAGS[:] = base_flags
    # MUTACIÓN: no comprobar `--max-turns 1` / `--tools ""` en `cota_salida_cli` → cae i-1d.
    check("i-1d · I4: si la invocación NO es de un turno sin herramientas (sin --max-turns 1, o con "
          "herramientas) la cota sigue DESCONOCIDA",
          all(v["cota_salida"] is None and v["tokens_cota_superior"] is None and "un solo turno" in v["motivo_cota"]
              for v in (sin_turnos, con_tools)))
    hints = dict(llm_mod._CLI_MODEL_HINTS)
    try:
        llm_mod._CLI_MODEL_HINTS["cli-claude-opus"] = "modelo-sin-dato"
        sin_dato = fallar(guardia("i4s"), "cli-claude-opus")
    finally:
        llm_mod._CLI_MODEL_HINTS.clear()
        llm_mod._CLI_MODEL_HINTS.update(hints)
    check("i-1e · un modelo sin máximo documentado en la tabla → cota desconocida",
          sin_dato["cota_salida"] is None and "sin máximo" in sin_dato["motivo_cota"])
    check("i-2 · I4: bajo una API que SÍ aplica max_tokens la cota sigue siendo max_tokens (500 + entrada)",
          api["cota_aplicada"] is True and api["cota_salida"] == 500 and api["cota_fuente"] == "max_tokens_aplicado")
    ok_c = rb.ContadorCuota(techo_claude=10_000_000, techo_codex=5_000, reserva_juicio_claude=2_000,
                            reserva_juicio_codex=1_000)
    rb.registrar_consumo(ok_c, "x/1/1", "produccion", {"claude_conocido": 10, "fallidos": [opus]})
    check("i-3 · I4: el timeout de Opus con cota real deja el techo CERTIFICABLE; el de Codex (sin dato) o el "
          "de un bucle de herramientas lo dejan NO certificable (P10)",
          ok_c.cota_calculable is True
          and rb.cota_de_fallidos([opus])[0] == opus["tokens_cota_superior"]
          and rb.cota_de_fallidos([cdx["cli-codex"]])[1] is False
          and rb.cota_de_fallidos([con_tools])[1] is False)

    # ── I5 · reserva Codex efectiva y control previo del juicio ───────────────────────────────
    c = rb.ContadorCuota(techo_claude=10_000, techo_codex=8_000, reserva_juicio_claude=2_000,
                         reserva_juicio_codex=6_000)
    c.registrar("p", rubro="produccion", codex_conocido=7_000)
    # MUTACIÓN: quitar el bloque `codex_produccion + proximo_codex` de `motivo_suspension` → cae i-4.
    check("i-4 · I5: 7 000 de Codex en producción con techo 8 000 y reserva 6 000 SUSPENDE (la reserva "
          "Codex se protege igual que la de Claude)", "Codex" in (c.motivo_suspension() or ""))
    c2 = rb.ContadorCuota(techo_claude=10_000, techo_codex=8_000, reserva_juicio_claude=2_000,
                          reserva_juicio_codex=6_000)
    c2.registrar("p", rubro="produccion", codex_conocido=1_000)
    check("i-5 · I5: control PREVIO: 1 000 + 1 500 de la siguiente corrida > 2 000 → suspende antes de correr",
          c2.motivo_suspension(proximo_codex=1_500) is not None
          and c2.motivo_suspension(proximo_codex=1_000) is None)

    class MundoC(MundoF):
        def deps(self):
            d = super().deps()
            base = d.consumo_desde

            def desde(mm):
                out = base(mm)
                out["codex_conocido"] = 5 * out["llamadas"]
                return out
            d.consumo_desde = desde
            return d

    plan = rb.construir_plan(["peq-1", "peq-2", "volu-1"], ids_fuga=[], ids_voluminosos=["volu-1"],
                             r_fuga=4, r_base=2)
    m = MundoC(consumo=1)
    ctx = _ctx(tmp, "i-cdx", plan=plan, techo=100, reserva=0)        # Codex: techo 50, reserva 25 → tope 25
    r = _corre(ctx, m)
    # MUTACIÓN: no pasar `codex_piloto` a `paso` (estimado_codex=0) → cae i-6 (la reserva se invade).
    check("i-6 · I5: de punta a punta la producción se detiene ANTES de invadir la reserva Codex (≤ 25 de 50)",
          r["salida"] == rb.EXIT_SUSPENDIDO and ctx.contador.codex_produccion <= 25
          and "Codex" in r["motivo"])

    # ── I5b · el control previo del juicio mira AMBOS proveedores ──────────────────────────────
    cj = rb.ContadorCuota(techo_claude=1_000, techo_codex=500, reserva_juicio_claude=100,
                          reserva_juicio_codex=0)
    cj.registrar("g", rubro="juicio", codex_conocido=500)
    cj2 = rb.ContadorCuota(techo_claude=1_000, techo_codex=500, reserva_juicio_claude=100,
                           reserva_juicio_codex=0)
    cj2.registrar("g", rubro="juicio", claude_conocido=1_000)
    cj3 = rb.ContadorCuota(techo_claude=1_000, techo_codex=500, reserva_juicio_claude=100,
                           reserva_juicio_codex=0)
    cj3.registrar("g", rubro="juicio", claude_conocido=100, codex_conocido=100)
    # MUTACIÓN: en `motivo_juicio`, quitar el bucle sobre ambos proveedores → cae i-9b.
    check("i-9b · el control previo del juicio verifica el techo de AMBOS proveedores: con Codex agotado no "
          "se lanza un juez de Claude (y viceversa); con ambos holgados, sí",
          "Codex" in (cj.motivo_juicio("claude", 10) or "") and "Claude" in (cj2.motivo_juicio("codex", 10) or "")
          and cj3.motivo_juicio("claude", 100) is None and cj3.motivo_juicio("codex", 500) is not None)

    # ── ledger del juicio ─────────────────────────────────────────────────────────────────────
    sal = tmp / "salida-i-led"

    def led(techo=1_000, techo_cx=500):
        return rb.LedgerJuicio(sal, "0.4", nuevo_contador=lambda: rb.ContadorCuota(
            techo_claude=techo, techo_codex=techo_cx, reserva_juicio_claude=100, reserva_juicio_codex=0))
    L = led()
    ruta = L.iniciar(id_="j1", etapa="juicio", proveedor="claude", cota_tokens=300)
    fila = rb.leer_json(ruta)
    # MUTACIÓN: no escribir el intento `en_curso` antes de devolver → cae i-7.
    check("i-7 · ledger: `iniciar` deja el intento ESCRITO (en_curso, con su cota) ANTES de lanzar al juez",
          fila["estado"] == "en_curso" and fila["cota_reservada"] == 300 and fila["proveedor"] == "claude")
    ctx_l = _ctx(tmp, "i-led-ctx", plan=plan)
    ctx_l.salida = sal
    rb.cargar_contador_desde_disco(ctx_l)
    check("i-8 · y otro proceso que relee el disco ya cuenta esa reserva como consumo DESCONOCIDO",
          ctx_l.contador.claude_total == 300 and ctx_l.contador.cota_calculable is False)
    try:
        L.iniciar(id_="j2", etapa="juicio", proveedor="claude", cota_tokens=800)
        ok = False
    except rb.PresupuestoAgotado:
        ok = True
    # MUTACIÓN: quitar `motivo_juicio` de `iniciar` → cae i-9.
    check("i-9 · `iniciar` RECHAZA (PresupuestoAgotado) un intento cuya cota no cabe: 300 + 800 > 1 000, y "
          "no deja rastro", ok and not rb.ruta_ledger(sal, "0.4", "j2").exists())
    try:
        L.iniciar(id_="x1", etapa="juicio", proveedor="codex", cota_tokens=600)
        ok = False
    except rb.PresupuestoAgotado:
        ok = True
    check("i-10 · lo mismo con Codex (cota 600 > techo 500)", ok)
    for mal in (dict(id_="j1", etapa="juicio", proveedor="claude", cota_tokens=1),      # id repetido
                dict(id_="n1", etapa="juicio", proveedor="claude", cota_tokens=None),    # sin cota
                dict(id_="n2", etapa="produccion", proveedor="claude", cota_tokens=1),   # etapa
                dict(id_="n3", etapa="juicio", proveedor="gemini", cota_tokens=1)):      # proveedor
        try:
            L.iniciar(**mal)
            ok = False
            break
        except ValueError:
            ok = True
    check("i-11 · sin cota, con id repetido, etapa o proveedor inválidos, `iniciar` no lanza", ok)
    L.cerrar("j1", claude_conocido=120)
    c3 = L.contador()
    check("i-12 · `cerrar` sustituye la reserva por lo medido (120) y el techo vuelve a certificable",
          c3.claude_total == 120 and c3.cota_calculable is True)
    L.iniciar(id_="j3", etapa="adjudicacion", proveedor="codex", cota_tokens=200)
    L.cerrar("j3", timeout=True, error="timeout")
    c4 = L.contador()
    # MUTACIÓN: en `cerrar`, ignorar `timeout` (tratar como conocido) → cae i-13.
    check("i-13 · un TIMEOUT de un juez no se pierde: cuenta su cota (200 Codex) y deja el techo no certificable",
          c4.codex_total == 200 and c4.cota_calculable is False)
    # un marcador de PRODUCCIÓN en vuelo no se convierte en huérfano al consultar el ledger
    marca = rb.ruta_en_curso(sal, "0.4", "peq-1", 1)
    rb.escribir_atomico(marca, {"caso_id": "peq-1", "rep": 1, "intento": 1})
    L.contador()
    check("i-14 · consultar el ledger NO toca los marcadores `.en_curso` de la producción (podría estar viva)",
          marca.is_file() and not rb.ruta_intento(sal, "0.4", "peq-1", 1, 1).exists())
    try:
        L.cerrar("no-existe")
        ok = False
    except ValueError:
        ok = True
    check("i-15 · cerrar un intento que no está en curso se rechaza", ok)
    k0 = rb.contador_desde_protocolo(__import__("mia.eval.banco04.protocolo", fromlist=["x"]), 0)
    check("i-16 · `contador_desde_protocolo` arma el contador con techo y reserva del bloque",
          k0.techo_claude == 18_000_000 and k0.reserva_codex == 5_000_000)

    # ── I10 · manifiesto inmutable de la ejecución ─────────────────────────────────────────────
    M1 = rb.construir_manifiesto(version="0.4", sha_arbol="a" * 40, arbol_limpio=True, soul_sha256="s1",
                                 cli_version="2.1", politica="quality_adaptive",
                                 protocolo_version="banco04-v1.2", protocolo_hash="h1", runner_sha256="r1")
    M2 = dict(M1, sha_arbol="b" * 40)
    m = MundoF(consumo=10)
    ctx = _ctx(tmp, "i-man", plan=plan, manifiesto=M1)
    _corre(ctx, m)
    reg = rb.leer_json(rb.ruta_corrida(ctx.salida, "0.4", "peq-1", 1))
    man = rb.leer_json(ctx.salida / "0.4" / "MANIFIESTO.json")
    check("i-17 · I10: la ejecución escribe un MANIFIESTO.json y cada registro lleva su hash",
          man == M1 and reg["manifiesto_sha256"] == ctx.manifiesto_sha256 and ctx.manifiesto_sha256)
    n0 = len(m.llamadas_a_producir)
    _corre(_ctx(tmp, "i-man", plan=plan, manifiesto=M1), m)
    check("i-18 · relanzar con el MISMO manifiesto reutiliza lo hecho", len(m.llamadas_a_producir) == n0)

    def rechaza(ctx_):
        try:
            asyncio.run(rb.ejecutar_banco(ctx_, m.deps()))
        except rb.BancoAbortado as exc:
            return str(exc)
        return None
    msg = rechaza(_ctx(tmp, "i-man", plan=plan, manifiesto=M2))
    # MUTACIÓN: quitar la comparación de manifiestos en `asegurar_manifiesto` → cae i-19.
    check("i-19 · otro SHA de árbol (u otro SOUL, CLI, política, protocolo) → se rechaza y dice qué difiere",
          msg is not None and "sha_arbol" in msg)
    (ctx.salida / "0.4" / "MANIFIESTO.json").unlink()      # sin manifiesto registrado pero con registros previos
    msg2 = rechaza(_ctx(tmp, "i-man", plan=plan, manifiesto=M2))
    # MUTACIÓN: quitar `_exigir_mismo_manifiesto` (reutilizar el terminal sin cotejar) → cae i-20.
    check("i-20 · registros previos hechos con otro manifiesto NO se reutilizan (se rechazan)",
          msg2 is not None and "manifiesto" in msg2)
    for campo in ("soul_sha256", "cli_version", "politica", "protocolo_hash", "runner_sha256"):
        d = _ctx(tmp, "i-man2", plan=plan, manifiesto=M1)
        _corre(d, MundoF(consumo=1)) if campo == "soul_sha256" else None
        cambiado = _ctx(tmp, "i-man2", plan=plan, manifiesto=dict(M1, **{campo: "otro"}))
        if rechaza(cambiado) is None:
            ok = False
            break
        ok = True
    check("i-21 · cualquier campo del manifiesto que cambie (SOUL, CLI, política, protocolo, runner) lo rechaza", ok)
    rb.verificar_sha_declarado("abcdef1", "abcdef1234567890" + "0" * 24)
    malos = []
    for decl in ("", "abc", "deadbee", "abcdef2"):
        try:
            rb.verificar_sha_declarado(decl, "abcdef1234567890" + "0" * 24)
            malos.append(decl)
        except rb.BancoAbortado:
            pass
    # MUTACIÓN: aceptar cualquier `--sha` (quitar `startswith`) → cae i-22.
    check("i-22 · `--sha` no es una etiqueta libre: debe ser (un prefijo ≥7 de) el SHA real del árbol",
          not malos)

    class R:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out

    real_run = rb.subprocess.run
    try:
        rb.subprocess.run = lambda cmd, **k: (R(0, "c" * 40 + "\n") if "rev-parse" in cmd else R(0, " M x.py\n"))
        sucio = rb.info_arbol_git(ROOT)
        rb.subprocess.run = lambda cmd, **k: (R(0, "c" * 40 + "\n") if "rev-parse" in cmd else R(0, ""))
        limpio = rb.info_arbol_git(ROOT)
        rb.subprocess.run = lambda cmd, **k: R(128, "")
        try:
            rb.info_arbol_git(ROOT)
            ok = False
        except rb.BancoAbortado:
            ok = True
    finally:
        rb.subprocess.run = real_run
    check("i-23 · el SHA y la limpieza del árbol salen de git (solo lectura); sin SHA legible se aborta",
          sucio == {"sha": "c" * 40, "arbol_limpio": False} and limpio["arbol_limpio"] is True and ok)


def main() -> int:
    tmp = _tmp("banco04-prod-")
    bloque_a(tmp)
    bloque_b(tmp)
    bloque_b2(tmp)
    bloque_c_aislamiento(tmp)
    bloque_c_politica_y_fallos(tmp)
    bloque_c_ejecucion(tmp)
    bloque_c_protocolo(tmp)
    bloque_d(tmp)
    bloque_e(tmp)
    bloque_f(tmp)
    bloque_h(tmp)
    bloque_i(tmp)
    malos = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(malos)}/{len(results)} checks OK")
    for n in malos:
        print("  FALLA:", n)
    return 0 if not malos else 1


if __name__ == "__main__":
    raise SystemExit(main())
