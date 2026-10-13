"""Dobles en memoria de los proveedores, de los jueces y del mundo exterior (§6.1).

Ninguno escribe telemetría ni importa `mia.eval.banco04.telemetria` (K10, §6.1): cada fila R4 la
escribe la captura REAL de la cadena. Los dobles solo sustituyen:

  · `subprocess.run` DENTRO de `subscription_llm` y de `codex_subscription_llm` (emiten el JSON /
    JSONL del CLI con `usage` completo, `modelUsage` y `stop_reason`);
  · `_resolve_exe` de ambos módulos (ruta ficticia `.exe`);
  · `embeddings.embed_texts`;
  · `codex_subscription_llm._local_membership_allowed` y `llm.resolve_fallback_chain`, solo en
    E2E-8, E2E-9 y E2E-12;
  · los runners de juez (interfaz `Runner`, J:1324);
  · el `mundo` (producir, hash del SOUL, jurisdicciones y aprobaciones) sin base de datos: su
    `producir` llama a `llm.call_llm(task=...)` del producto REAL.

INTERFAZ FIJADA POR LAS PRUEBAS (el contrato la deja abierta):
  · `proveedores` es un dict cuyas claves son EXACTAMENTE los nombres de módulo que enumera §6.1:
        "subscription_llm.subprocess.run", "codex_subscription_llm.subprocess.run",
        "subscription_llm._resolve_exe", "codex_subscription_llm._resolve_exe",
        "embeddings.embed_texts"
    y, opcionales, "codex_subscription_llm._local_membership_allowed" y
    "llm.resolve_fallback_chain".
  · `mundo` es un objeto con los métodos de `Deps` y `DepsAprobacion` que §6.1 sustituye:
        async producir(caso, rep) -> dict;  hash_soul() -> str;
        fijar_jurisdicciones(codigos, tenant=None) -> None;
        async abrir_despacho(caso); async producir_hasta_revision(handle, caso);
        async aprobar(handle, resultado) -> dict; async cerrar_despacho(handle).
  · `runners` (juzgar y VJ) es `{"opus": Runner, "codex": Runner}`; cada runner atiende todas las
    etapas (pasada 1, tercer voto, pasada 2, votos de cobertura, negativas falsas, estabilidad)
    según el `schema` del esquema que recibe.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from . import custodia_falsa as CF
from . import firmas

MODELO_POR_HINT = {"opus": "claude-doble-opus", "sonnet": "claude-doble-sonnet",
                   "haiku": "claude-doble-haiku"}
MODELO_CODEX = "gpt-doble-codex"
_RE_CASO = re.compile(r"\[\[BANCO04 caso=([^|\]]+)\|rep=(\d+)\|nodo=([^|\]]*)\]\]")


# ════════════════════════════════════════════════════════════════════════════════════════
# CLI de Claude y de Codex
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class ClaudeCLIDoble:
    """`subprocess.run` del módulo `subscription_llm`. Emite el JSON del CLI."""
    omitir: frozenset = frozenset()                 # componentes de `usage` que se omiten
    omitir_si: Optional[Callable[[str, list], bool]] = None   # (caso, cmd) -> ¿omitir?
    sin_model_usage: bool = False
    canonico: Mapping[str, str] = field(default_factory=lambda: dict(MODELO_POR_HINT))
    factor_salida: Mapping[str, float] = field(default_factory=dict)   # caso -> factor
    falla_si: Optional[Callable[[str, int, str], bool]] = None         # (caso, rep, nodo) -> ¿falla?
    barrera: Optional[Callable[[str, int, str], None]] = None   # E2E-13: (caso, rep, nodo), ANTES de responder
    # v9 (E2E-19): control EXACTO del consumo por llamada. Todos reciben (caso, rep, nodo).
    total_exacto: Optional[Callable[[str, int, str], Optional[int]]] = None   # total de la llamada
    salida_si: Optional[Callable[[str, int, str], Optional[int]]] = None      # output_tokens
    omitir_salida_si: Optional[Callable[[str, int, str], bool]] = None        # sin output_tokens
    timeout_si: Optional[Callable[[str, int, str], bool]] = None              # agota el tiempo
    llamadas: list = field(default_factory=list)
    envs: list = field(default_factory=list)          # el `env` que recibió cada llamada (E2E-19.5)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self, cmd, *a, input=None, **kw):  # noqa: A002
        texto = input or ""
        m = _RE_CASO.search(texto)
        caso, rep, nodo = (m.group(1), int(m.group(2)), m.group(3)) if m else ("_", 0, "")
        modelo = "sonnet"
        if "--model" in cmd:
            modelo = cmd[cmd.index("--model") + 1]
        with self._lock:
            self.llamadas.append({"cmd": list(cmd), "caso": caso, "rep": rep, "nodo": nodo})
            self.envs.append(dict(kw["env"]) if isinstance(kw.get("env"), Mapping) else kw.get("env"))
        if self.barrera is not None:
            self.barrera(caso, rep, nodo)
        if self.timeout_si and self.timeout_si(caso, rep, nodo):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        if self.falla_si and self.falla_si(caso, rep, nodo):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error del doble (sin JSON)")
        entrada = 100 + len(texto) // 40
        salida = int(round(40 * float(self.factor_salida.get(caso, 1))))
        t = self.total_exacto(caso, rep, nodo) if self.total_exacto else None
        if isinstance(t, int):
            entrada, salida = t - 1, 1
        x = self.salida_si(caso, rep, nodo) if self.salida_si else None
        if isinstance(x, int):
            salida = x
        usage = {"input_tokens": entrada, "output_tokens": salida,
                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        omitir = set(self.omitir)
        if self.omitir_salida_si and self.omitir_salida_si(caso, rep, nodo):
            omitir.add("output_tokens")
        if self.omitir_si and self.omitir_si(caso, list(cmd)):
            omitir |= {"cache_creation_input_tokens", "cache_read_input_tokens"}
        for k in omitir:
            usage.pop(k, None)
        canon = self.canonico.get(modelo, f"claude-doble-{modelo}")
        data = {"type": "result", "subtype": "success", "is_error": False,
                "result": "Respuesta sintética del doble del CLI.", "session_id": f"doble-{caso}-{rep}",
                "num_turns": 1, "stop_reason": "end_turn", "usage": usage}
        if not self.sin_model_usage:
            data["modelUsage"] = {canon: {"inputTokens": entrada, "outputTokens": salida,
                                          "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                          "canonicalModel": canon, "provider": "doble"}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(data, ensure_ascii=False), stderr="")


@dataclass
class CodexCLIDoble:
    """`subprocess.run` del módulo `codex_subscription_llm`. Escribe `--output-last-message` y
    emite los eventos JSONL. `eventos`: 'uno' | 'ninguno' | 'acumulados' (dos eventos `usage`)."""
    eventos: str = "uno"
    tokens: int = 30
    totales: Optional[list] = None      # si se da, el total de cada llamada, en ciclo (R13: 10 + 1000)
    llamadas: list = field(default_factory=list)

    def __call__(self, cmd, *a, input=None, **kw):  # noqa: A002
        n = len(self.llamadas)
        self.llamadas.append(list(cmd))
        if "--output-last-message" in cmd:
            out = Path(cmd[cmd.index("--output-last-message") + 1])
            out.write_text(json.dumps({"content": "Respuesta sintética del doble de Codex."}),
                           encoding="utf-8")
        lineas = [{"type": "thread.started", "thread_id": "doble", "model": MODELO_CODEX},
                  {"type": "turn.started"}]
        if self.totales:
            t = int(self.totales[n % len(self.totales)])
            lineas.append({"type": "turn.completed", "model": MODELO_CODEX,
                           "usage": {"input_tokens": t // 2, "cached_input_tokens": 0,
                                     "output_tokens": t - t // 2, "total_tokens": t}})
        elif self.eventos == "uno":
            lineas.append({"type": "turn.completed", "model": MODELO_CODEX,
                           "usage": {"input_tokens": 90, "cached_input_tokens": 0,
                                     "output_tokens": self.tokens, "total_tokens": 90 + self.tokens}})
        elif self.eventos == "acumulados":
            lineas.append({"type": "turn.completed", "model": MODELO_CODEX,
                           "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}})
            lineas.append({"type": "turn.completed", "model": MODELO_CODEX,
                           "usage": {"input_tokens": 90, "output_tokens": self.tokens,
                                     "total_tokens": 90 + self.tokens}})
        stdout = "\n".join(json.dumps(x) for x in lineas) + "\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def embed_doble(texts):
    from mia import config  # noqa: WPS433
    dim = int(getattr(config, "EMBED_DIM", 1024))
    out = []
    for t in texts:
        h = hashlib.sha256((t or "").encode("utf-8")).digest()
        v = [((h[i % len(h)] / 255.0) - 0.5) for i in range(dim)]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


def embed_degenerado(texts):
    """Mutación del esqueleto con BD: todos los vectores iguales → la recuperación pierde orden."""
    from mia import config  # noqa: WPS433
    dim = int(getattr(config, "EMBED_DIM", 1024))
    return [[1.0 / dim ** 0.5] * dim for _ in texts]


def cadena_con_codex(tareas: Iterable[str] = ("legal_research",)) -> Callable:
    """Doble de `llm.resolve_fallback_chain`: las `tareas` empiezan por `cli-codex`."""
    from mia.agent import llm  # noqa: WPS433
    original = llm.resolve_fallback_chain
    tareas = frozenset(tareas)

    def resolve_fallback_chain(task, model=None, quality_escalation=None):
        if task in tareas:
            return [llm.CLI_CODEX_ALIAS]
        return original(task, model, quality_escalation)

    resolve_fallback_chain.__wrapped__ = original      # type: ignore[attr-defined]
    return resolve_fallback_chain


def proveedores(*, claude: Optional[ClaudeCLIDoble] = None, codex: Optional[CodexCLIDoble] = None,
                con_codex: bool = False, tareas_codex: Iterable[str] = ("legal_research",),
                embed: Callable = embed_doble) -> dict:
    p = {"subscription_llm.subprocess.run": claude or ClaudeCLIDoble(),
         "codex_subscription_llm.subprocess.run": codex or CodexCLIDoble(),
         "subscription_llm._resolve_exe": lambda: firmas.EXE_CLAUDE,
         "codex_subscription_llm._resolve_exe": lambda: Path(firmas.EXE_CODEX),
         "embeddings.embed_texts": embed}
    if con_codex:
        p["codex_subscription_llm._local_membership_allowed"] = lambda: True
        p["llm.resolve_fallback_chain"] = cadena_con_codex(tareas_codex)
    return p


# ════════════════════════════════════════════════════════════════════════════════════════
# Mundo (variante sin base de datos, §6.1)
# ════════════════════════════════════════════════════════════════════════════════════════
LLAMADAS_POR_DEFECTO = (("legal_analysis", "analisis"), ("legal_draft", "redaccion"))
FRASE_FUGA = "La Ley 100 de 1993 es aplicable al caso"
FUENTE_NO_CONFIGURADA = {"ref": "corpus:ley-co-100", "texto": "La Ley 100 de 1993 dispone que el "
                         "contrato de obra se rige por reglas especiales.", "jurisdiccion": "co",
                         "title": "Ley 100 de 1993 (ficticia de prueba)", "ficticia": True}
FRASE_FUENTE = "el contrato de obra se rige por reglas especiales"


@dataclass
class Guion:
    """Qué hace el mundo en cada corrida. Todo lo no indicado sigue el camino feliz."""
    llamadas: tuple = LLAMADAS_POR_DEFECTO
    llamadas_extra: Mapping[str, tuple] = field(default_factory=dict)   # caso -> llamadas extra
    nodo_forzado: Mapping[str, str] = field(default_factory=dict)       # caso -> nodo
    fallo_producto: set = field(default_factory=set)        # {(caso, rep)}
    limite_de_uso: set = field(default_factory=set)         # {(caso, rep)}
    sin_verificacion: set = field(default_factory=set)      # {(caso, rep)}
    fallback_huerfano: set = field(default_factory=set)     # {(caso, rep)}
    fraccion_leida: Mapping[str, float] = field(default_factory=dict)   # caso -> fracción
    medicion_incompleta: set = field(default_factory=set)   # {caso}
    texto_extra_borrador: Mapping[str, str] = field(default_factory=dict)   # caso -> frase
    fuente_no_configurada: set = field(default_factory=set)  # {caso}
    sin_frase_hecho: set = field(default_factory=set)       # {(caso, rep)} omite el hecho del texto
    aprobacion_infra: set = field(default_factory=set)      # {caso}: falla dos veces por infraestructura
    escalada_excepcional: set = field(default_factory=set)  # {caso}: la 1.ª llamada con escalada
    marcar_muerte: Optional[Callable[[str, int], None]] = None
    infra_antes: set = field(default_factory=set)           # {(caso, rep)}: muere ANTES de llamar
    llamada_api_fallida: set = field(default_factory=set)   # {caso}: una llamada `api` con max_tokens que falla
    api_max_tokens: int = 1                                 # `max_tokens` de esa llamada (fija su cota)
    llamadas_extra_rep: Mapping[tuple, tuple] = field(default_factory=dict)   # (caso, rep) -> llamadas
    tolerar_fallos_en: frozenset = frozenset()              # nodos cuyo fallo el turno absorbe
    aprobar_sin_llamada: bool = False                       # la aprobación no llama al modelo


class Mundo:
    def __init__(self, plantilla_soul: Path, guion: Optional[Guion] = None, *, version: str = "") -> None:
        self.plantilla = Path(plantilla_soul)
        self.guion = guion or Guion()
        self.version = version
        self.jurisdicciones_fijadas: list = []
        self.producidas: list = []
        self._intentos_aprob: dict = {}

    # ── Deps ──────────────────────────────────────────────────────────────────
    def hash_soul(self) -> str:
        return hashlib.sha256(self.plantilla.read_bytes()).hexdigest()

    def fijar_jurisdicciones(self, codigos, tenant=None) -> None:
        self.jurisdicciones_fijadas.append(list(codigos))

    async def _llamar(self, caso, rep: int, llamadas) -> None:
        from mia.agent import llm  # noqa: WPS433
        from mia.metrics import usage  # noqa: WPS433
        g = self.guion
        for k, (task, nodo, *extra) in enumerate(llamadas):
            nodo = g.nodo_forzado.get(caso.id, nodo)
            kw = dict(extra[0]) if extra else {}
            if k == 0 and caso.id in g.escalada_excepcional:
                kw["quality_escalation"] = getattr(llm, "QUALITY_ESCALATION_EXCEPTIONAL", "exceptional")
            mensajes = [{"role": "system", "content": "Eres el doble del turno del banco 0.4."},
                        {"role": "user", "content": f"[[BANCO04 caso={caso.id}|rep={rep}|nodo={nodo}]] "
                                                    f"{caso.message}"}]
            tok = usage.set_node(nodo)
            try:
                await asyncio.to_thread(llm.call_llm, mensajes, task=task, **kw)
            except Exception:  # noqa: BLE001
                if nodo not in g.tolerar_fallos_en:
                    raise                      # el producto falla; si es tolerado, el turno sigue
            finally:
                usage.reset_node(tok)

    async def producir(self, caso, rep: int) -> dict:
        g = self.guion
        if g.marcar_muerte:
            g.marcar_muerte(caso.id, rep)
        if (caso.id, rep) in g.limite_de_uso:
            raise RuntimeError("usage limit reached (doble del plan)")
        if (caso.id, rep) in g.infra_antes:
            raise RuntimeError("session has expired (doble: infraestructura antes de llamar)")
        if caso.id in g.llamada_api_fallida:
            await self._llamada_api(caso, rep)
        llamadas = (tuple(g.llamadas) + tuple(g.llamadas_extra.get(caso.id, ()))
                    + tuple(g.llamadas_extra_rep.get((caso.id, rep), ())))
        await self._llamar(caso, rep, llamadas)
        if (caso.id, rep) in g.fallo_producto:
            raise RuntimeError("fallo del producto después de llamar al modelo (doble)")
        self.producidas.append((caso.id, rep))
        return resultado_sintetico(caso, rep, g)

    async def _llamada_api(self, caso, rep: int) -> None:
        """Familia `api` con `max_tokens` aplicado contra un proxy local cerrado: falla sin red y
        queda «desconocido CON cota» (K7). El turno sigue: el producto no muere por ella."""
        from mia.agent import llm  # noqa: WPS433
        from mia.metrics import usage  # noqa: WPS433
        tok = usage.set_node("auxiliar_api")
        try:
            await asyncio.to_thread(llm.call_llm, [
                {"role": "user", "content": f"[[BANCO04 caso={caso.id}|rep={rep}|nodo=auxiliar_api]] x"}],
                task="legal_edit", model="claude-haiku", max_tokens=int(self.guion.api_max_tokens))
        except Exception:  # noqa: BLE001 — la falla es el punto
            pass
        finally:
            usage.reset_node(tok)

    # ── DepsAprobacion ────────────────────────────────────────────────────────
    async def abrir_despacho(self, caso):
        return {"caso": caso.id}

    async def producir_hasta_revision(self, handle, caso) -> dict:
        await self._llamar(caso, 0, (("legal_draft", "redaccion"),))
        return resultado_sintetico(caso, 0, self.guion)

    async def aprobar(self, handle, resultado) -> dict:
        cid = handle["caso"]
        if cid in self.guion.aprobacion_infra:
            n = self._intentos_aprob.get(cid, 0) + 1
            self._intentos_aprob[cid] = n
            raise RuntimeError("session has expired (doble: infraestructura)")
        if self.guion.aprobar_sin_llamada:
            return {"aprobada": True, "aprendizaje": "sin_llamada", "trabajos": {"pendientes": 0}}
        from mia.agent import llm  # noqa: WPS433
        from mia.metrics import usage  # noqa: WPS433
        tok = usage.set_node("aprendizaje")
        try:
            await asyncio.to_thread(llm.call_llm, [
                {"role": "system", "content": "Doble del aprendizaje tras aprobar."},
                {"role": "user", "content": f"[[BANCO04 caso={cid}|rep=0|nodo=aprendizaje]] aprobar"}],
                task="legal_edit")
        finally:
            usage.reset_node(tok)
        return {"aprobada": True, "aprendizaje": "ok", "trabajos": {"pendientes": 0}}

    async def cerrar_despacho(self, handle) -> None:
        return None


def _documents_map(caso) -> list[dict]:
    out, n = [], 0
    for fn, chunks in CF.documentos_de(caso):
        for i, txt in enumerate(chunks):
            n += 1
            out.append({"n": n, "id": f"{fn}#{i}", "document_id": fn, "filename": fn, "ord": i,
                        "folio_ancla": None, "chars": len(txt),
                        "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(), "content": txt})
    return out


def resultado_sintetico(caso, rep: int, g: Guion) -> dict:
    """El `resultado` de `run_case` (H:702-905) con texto respaldado por el expediente del caso.
    Solo lo sintético es el resultado; el consumo lo deja la captura real."""
    plan = CF.plan_de_caso(caso)
    frases = [h["frase"] for h in plan["hechos"]] or [plan["frase_mensaje"] or "Consta el mensaje"]
    if (caso.id, rep) in g.sin_frase_hecho:
        frases = [plan["frase_mensaje"] or "Consta el mensaje del abogado"]
    diag = " ".join(f"{f}." for f in frases)
    borr = f"{frases[0]}."
    if caso.id in g.texto_extra_borrador:
        borr = f"{borr} {g.texto_extra_borrador[caso.id]}."
    fuentes: list = []
    if caso.id in g.fuente_no_configurada:
        fuentes = [dict(FUENTE_NO_CONFIGURADA)]
        borr = f"{borr} {FRASE_FUENTE[0].upper()}{FRASE_FUENTE[1:]}."
    mapa = _documents_map(caso)
    frac = float(g.fraccion_leida.get(caso.id, 1.0))
    claves_hecho = {(h["documento"], h["fragmento"]) for h in plan["hechos"]}
    total = len(mapa)
    n_leer = total if frac >= 1.0 else max(len(claves_hecho), int(total * frac))
    elegidos, resto = [], []
    for d in mapa:
        (elegidos if (d["filename"], d["ord"]) in claves_hecho else resto).append(d)
    elegidos += resto[:max(0, n_leer - len(elegidos))]
    tramos = [{"documento": d["filename"], "indice": d["ord"], "id": d["id"],
               "chars_original": d["chars"], "tramos": [[0, d["chars"]]], "completo": True}
              for d in elegidos]
    completo = caso.id not in g.medicion_incompleta
    material = {
        "documents_map": mapa, "documents_origen": "doble del mundo (sintético)",
        "recorte_posible_por_contexto": True, "contenido_completo_persistido": True,
        "fragmentos_en_prompt": {"metodo": "doble", "medido": True, "completo": completo,
                                 "llamadas_sin_identificar": 0 if completo else 1, "error_captura": None,
                                 "llamadas": [], "detalle": [], "fragmentos_sin_clave_documento_orden": 0},
        "entraron": [[t["documento"], t["indice"]] for t in tramos], "entraron_parcial": [],
        "entraron_tramos": tramos, "research_sources": fuentes,
        "alcance_lectura": {"leidos": len(tramos), "total": total},
        "soul_sha256": None, "cli_version": None, "errores_instrumentacion": []}
    verificacion = ({} if (caso.id, rep) in g.sin_verificacion
                    else {"detalle": [], "citas": 0, "anotadas": 0, "marcadas": 0, "respaldadas": 0})
    fallbacks = ([{"task": "legal_draft", "desde": "cli-claude-sonnet", "hacia": "cli-claude-haiku",
                   "motivo": "timeout"}] if (caso.id, rep) in g.fallback_huerfano else [])
    texto = f"{diag}\n{borr}"
    return {
        "case_id": caso.id, "title": caso.title, "matter_id": None, "elapsed_ms": 1000,
        "score": {"reached_draft": bool(borr.strip()), "ok": True},
        "verification": verificacion, "verification_diagnosis": {}, "documents_retrieved": len(mapa),
        "draft_preview": borr[:1200], "diagnosis_preview": diag[:1200], "reached_draft": bool(borr.strip()),
        "provenance": {"atribuye_sin_sello": False}, "usage": None, "model_fallbacks": fallbacks,
        "draft_full": borr, "diagnosis_full": diag,
        "false_block": {"citas_marcadas": 0, "falsos_bloqueos": 0, "tasa_falsos_bloqueos": 0.0, "detalle": []},
        "abstention": False,
        "jurisdiction_leak": {"leak": False, "detalle": [], "texto_len": len(texto)},
        "intentos_fallidos": [], "material_turno": material}


# ════════════════════════════════════════════════════════════════════════════════════════
# Jueces dobles (interfaz Runner)
# ════════════════════════════════════════════════════════════════════════════════════════
def _bloque(prompt: str, etiqueta: str) -> Any:
    a = prompt.index(f"<{etiqueta}>\n") + len(f"<{etiqueta}>\n")
    b = prompt.index(f"\n</{etiqueta}>", a)
    return json.loads(prompt[a:b])


def _ev(**kw) -> dict:
    base = {k: None for k in ("justificacion_no_aplica", "fuente", "pasaje", "localizador_invocado",
                              "marca", "fragmento_marca", "premisas", "pasaje_contradictorio",
                              "uso_fuente")}
    base.update(kw)
    return base


_RE_ANCLA = re.compile(r"\[[^\]]*\]")
_RE_SEP = re.compile(r"\s+(y|e|pero|aunque|mientras)\s+|;")
_CONECTORES_EXCL = {"y", "e", "pero"}


def nucleo(texto: str) -> str:
    t = _RE_ANCLA.sub(" ", texto)
    t = re.sub(r"^\s*(Según|Segun)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip(" ,.;:")


@dataclass
class Reglas:
    """Configuración de un juez doble. Por defecto: HONESTO (respalda solo lo que consta)."""
    forzar_defecto: frozenset = frozenset()       # subcadenas → sin_respaldo (hecho)
    forzar_fuga: frozenset = frozenset()          # subcadenas → sin_respaldo (fuga)
    ciego: bool = False                           # no ve defectos (los da por inferencia válida)
    invertir: bool = False                        # Codex: defecto ↔ no defecto
    tercer_voto: Optional[str] = None             # 'invalido' | estado fijo | None (honesto)
    p1_invalido: bool = False                     # salida estructuralmente inválida siempre
    p1_invalido_si: frozenset = frozenset()       # … solo si el paquete contiene una de estas frases
    sin_fuga: bool = False                        # nunca usa el subtipo `fuga` (S15, V1-V9)
    no_aplica_en_cifra: bool = False              # `no_aplica` sobre una cifra → inválida
    uso_aplicable_no_configurado: bool = False    # S16
    no_cubiertos: Mapping[str, Any] = field(default_factory=dict)   # caso -> True | {candidate_id}
    conducta: Mapping[str, str] = field(default_factory=dict)       # caso -> clase
    votos_cobertura: Optional[bool] = None        # None = honesto (igual que la pasada 2)
    puntos_laguna: frozenset = frozenset()        # casos cuya pasada 2 declara laguna (S17)
    aprobaria: str = "si"


def _estado_honesto(texto: str, material, reglas: Reglas, jurisdicciones) -> dict:
    from mia.eval.banco04 import evaluador_congelado as EV  # noqa: WPS433
    from mia.eval.banco04 import jueces  # noqa: WPS433
    if not re.search(r"\w", texto):
        return {"tipo": "no_afirmativa", "estado": "no_aplica",
                "ev": {"justificacion_no_aplica": "marca_estructural"}}
    if texto.strip().strip(".").lower() in ("atentamente", "cordialmente", "respetuosamente"):
        return {"tipo": "no_afirmativa", "estado": "no_aplica", "ev": {"justificacion_no_aplica": "cortesia"}}
    cita = bool(EV.scan_citations(texto, EV.compile_patterns(None)))
    if any(s in texto for s in reglas.forzar_fuga):
        return {"tipo": "proposicion_juridica", "estado": "sin_respaldo", "subtipo": "fuga", "ev": {}}
    if any(s in texto for s in reglas.forzar_defecto):
        return {"tipo": "hecho_expediente", "estado": "sin_respaldo", "subtipo": "hecho", "ev": {}}
    core = nucleo(texto)
    fuentes: list[tuple[str, str, Optional[str]]] = []
    fuentes += [(f"doc:{n}", t, None) for n, t in sorted(material.mapa_docs.items())]
    fuentes += [(f"expediente:{p}", t, None) for p, t in material.expediente.items()]
    fuentes += [(f"corpus:{r}", t, material.corpus_jurisdiccion.get(r))
                for r, t in material.fuentes_corpus.items()]
    fuentes += [("mensaje", material.mensaje, None)]
    for nombre, txt, jur in fuentes:
        if core and jueces.aparece(core, txt):
            ev = {"fuente": nombre, "pasaje": core}
            if jur and jur not in tuple(jurisdicciones):
                ev["uso_fuente"] = "aplicable" if reglas.uso_aplicable_no_configurado else "descriptivo"
            return {"tipo": "proposicion_juridica" if cita else "hecho_expediente",
                    "estado": "con_respaldo_sin_localizador", "ev": ev}
    sub = "fuga" if cita and not tuple(jurisdicciones) and not reglas.sin_fuga else "hecho"
    return {"tipo": "proposicion_juridica" if cita else "hecho_expediente", "estado": "sin_respaldo",
            "subtipo": sub, "ev": {}}


def _afirmacion(aid, tramos, seg, r: dict, *, dividido_de=None) -> dict:
    return {"id_afirmacion": aid, "tramos": [list(t) for t in tramos], "dividido_de": dividido_de,
            "texto": "".join(seg[a:b] for a, b in tramos), "tipo": r["tipo"], "estado": r["estado"],
            "evidencia": _ev(**r.get("ev", {})), "subtipo_sin_respaldo": r.get("subtipo"),
            "motivo": "doble de prueba"}


def atomizar(sid: str, t: str, regla: Callable[[str], dict]) -> dict:
    excl, afs = [], []
    m = re.match(r"^[^\w]+", t)
    ini = m.end() if m and re.search(r"\w", t) else 0
    fin = len(t)
    while fin > ini and t[fin - 1] in ".:;!?, ":
        fin -= 1
    if ini > 0 and t[:ini].strip():
        excl.append({"tramos": [[0, ini]], "justificacion": "marca_estructural"})
    if fin < len(t) and t[fin:].strip():
        excl.append({"tramos": [[fin, len(t)]], "justificacion": "puntuacion"})
    if not re.search(r"\w", t):
        return {"id": sid, "exclusiones": [], "afirmaciones": [
            _afirmacion(f"{sid}.a1", [(0, len(t))], t,
                        {"tipo": "no_afirmativa", "estado": "no_aplica",
                         "ev": {"justificacion_no_aplica": "marca_estructural"}})]}
    trozos, pos = [], ini
    for mm in _RE_SEP.finditer(t, ini, fin):
        con = (mm.group(1) or ";")
        if con in _CONECTORES_EXCL or con == ";":
            trozos.append((pos, mm.start()))
            k = mm.start() + mm.group(0).index(con)
            excl.append({"tramos": [[k, k + len(con)]],
                         "justificacion": "puntuacion" if con == ";" else "conector_sin_contenido"})
            pos = mm.end()
        else:                       # «aunque», «mientras»: el conector abre la proposición siguiente
            trozos.append((pos, mm.start()))
            pos = mm.start() + len(mm.group(0)) - len(mm.group(0).lstrip())
    trozos.append((pos, fin))
    for n, (a, b) in enumerate(trozos, 1):
        while a < b and t[a].isspace():
            a += 1
        b0 = b
        while b > a and t[b - 1] in " ,":
            b -= 1
        if t[b:b0].strip():
            excl.append({"tramos": [[b, b0]], "justificacion": "puntuacion"})
        if b <= a:
            continue
        afs.append(_afirmacion(f"{sid}.a{n}", [(a, b)], t, regla(t[a:b])))
    return {"id": sid, "exclusiones": excl, "afirmaciones": afs}


def _inferencia(r: dict, premisa: Optional[str]) -> dict:
    if premisa is None:
        return r
    return {"tipo": "inferencia", "estado": "inferencia_valida", "ev": {"premisas": [premisa]}}


class JuezDoble:
    """Runner doble. `proveedor`: 'opus' | 'codex'."""

    def __init__(self, proveedor: str, reglas: Optional[Reglas] = None, *, cli_version: str = "doble",
                 sin_identidad: bool = False, eventos_codex: str = "uno",
                 memo: Optional[dict] = None, romper_uso: Optional[Callable[[int, str], bool]] = None,
                 barrera: Optional[Callable[[int, str], None]] = None) -> None:
        self.romper_uso = romper_uso      # (índice de llamada, esquema) -> ¿uso sin output_tokens?
        self.barrera = barrera            # E2E-13: la invocación «real» del juez es este doble
        self.proveedor = proveedor
        self.memo = memo if memo is not None else {}    # candidate_id -> case_id (lo comparten)
        self.reglas = reglas or Reglas()
        self.cli_version = cli_version
        self.sin_identidad = sin_identidad
        self.eventos_codex = eventos_codex
        self.llamadas: list = []
        self.prompts: list = []
        self._lock = threading.Lock()

    # -- respuesta cruda --------------------------------------------------------
    def _respuesta(self, salida: Any, prompt: str, error: Optional[str] = None):
        from mia.eval.banco04.jueces import RespuestaModelo  # noqa: WPS433
        entrada = 200 + len(prompt) // 40
        if self.proveedor == "opus":
            uso = {"usage": {"input_tokens": entrada, "output_tokens": 80,
                             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                   "stop_reason": "end_turn", "num_turns": 1,
                   "modelUsage": {} if self.sin_identidad else {
                       "claude-doble-opus": {"inputTokens": entrada, "outputTokens": 80,
                                             "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                             "canonicalModel": "claude-doble-opus", "provider": "doble"}}}
            crudo = json.dumps({"type": "result", "result": json.dumps(salida, ensure_ascii=False),
                                **uso}, ensure_ascii=False)
            argv = firmas.JUEZ_CLAUDE_ARGV
            modelo = "claude-doble-opus"
        else:
            evs = [{"input_tokens": entrada, "cached_input_tokens": 0, "output_tokens": 60,
                    "total_tokens": entrada + 60}]
            if self.eventos_codex == "acumulados":
                evs = [{"input_tokens": entrada // 2, "output_tokens": 20, "total_tokens": entrada // 2 + 20},
                       evs[0]]
            lineas = [{"type": "thread.started", "model": MODELO_CODEX}] + [
                {"type": "turn.completed", "model": MODELO_CODEX, "usage": u} for u in evs]
            uso = {"eventos": evs}
            crudo = "\n".join(json.dumps(x) for x in lineas)
            argv = firmas.JUEZ_CODEX_ARGV
            modelo = MODELO_CODEX
        return RespuestaModelo(salida=salida, crudo=crudo, error=error, uso=uso,
                               modelo_reportado=modelo, cli_version=self.cli_version, latencia_ms=5,
                               comando_sin_prompt=list(argv))

    # -- despacho por esquema ---------------------------------------------------
    def __call__(self, prompt: str, esquema: dict):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        nombre = esquema.get("properties", {}).get("schema", {}).get("enum", [None])[0]
        with self._lock:
            indice = len(self.llamadas)
            self.llamadas.append(nombre)
            self.prompts.append(prompt)
        if self.barrera is not None:
            self.barrera(indice, nombre or "")
        resp = self._despachar(nombre, prompt, esquema)
        if self.romper_uso is not None and self.romper_uso(indice, nombre or ""):
            if "usage" in resp.uso:
                resp.uso["usage"].pop("output_tokens", None)
            elif "eventos" in resp.uso:
                resp.uso["eventos"] = []
        return resp

    def _despachar(self, nombre, prompt: str, esquema: dict):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        if nombre == P.ESQUEMA_PASADA1:
            return self._pasada1(prompt)
        if nombre == P.ESQUEMA_TERCER_VOTO:
            return self._tercer_voto(prompt)
        if nombre == getattr(P, "ESQUEMA_VOTO_COBERTURA", None):
            return self._voto_cobertura(prompt)
        if nombre and "cobertura" in nombre:
            return self._pasada2(prompt, esquema)
        return self._respuesta(None, prompt, error=f"esquema no previsto por el doble: {nombre}")

    def _material(self, paq):
        from mia.eval.banco04.jueces import Material  # noqa: WPS433
        return Material.desde_paquete(paq, partes=None)

    def _pasada1(self, prompt: str):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        r = self.reglas
        datos = _bloque(prompt, "MATERIAL_NO_CONFIABLE")
        es_codex = "atomizacion_opus" in datos
        paq = datos["paquete"] if es_codex else datos
        if r.p1_invalido or any(f in json.dumps(paq, ensure_ascii=False) for f in r.p1_invalido_si):
            return self._respuesta({"schema": "salida-invalida-del-doble"}, prompt)
        mat = self._material(paq)
        jur = tuple(paq.get("jurisdicciones_configuradas") or ())

        def regla(texto: str) -> dict:
            res = _estado_honesto(texto, mat, r, jur)
            if r.no_aplica_en_cifra and re.search(r"\d", texto):
                return {"tipo": "no_afirmativa", "estado": "no_aplica",
                        "ev": {"justificacion_no_aplica": "marca_estructural"}}
            return res

        if not es_codex:
            segs = [atomizar(s["id"], s["texto"], regla) for s in paq["segmentos"]]
            segs = self._ajustes(segs)
        else:
            textos = {s["id"]: s["texto"] for s in paq["segmentos"]}
            segs = []
            for sid, d in datos["atomizacion_opus"].items():
                t = textos[sid]
                afs = [_afirmacion(a["id_afirmacion"], a["tramos"], t, regla(a["texto"]))
                       for a in d["atomos"]]
                segs.append({"id": sid, "exclusiones": d["exclusiones"], "afirmaciones": afs})
            segs = self._ajustes(segs)
        return self._respuesta({"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"],
                                "segmentos": segs}, prompt)

    def _ajustes(self, segs: list[dict]) -> list[dict]:
        r = self.reglas
        if not (r.ciego or r.invertir):
            return segs
        respaldados = [a["id_afirmacion"] for s in segs for a in s["afirmaciones"]
                       if a["estado"] == "con_respaldo_sin_localizador"]
        for s in segs:
            for a in s["afirmaciones"]:
                if a["estado"] == "sin_respaldo" and (r.ciego or r.invertir):
                    prem = next((p for p in respaldados if p != a["id_afirmacion"]), None)
                    if prem is not None:
                        a.update(tipo="inferencia", estado="inferencia_valida", subtipo_sin_respaldo=None,
                                 evidencia=_ev(premisas=[prem]))
                elif a["estado"] == "con_respaldo_sin_localizador" and r.invertir:
                    a.update(estado="sin_respaldo", subtipo_sin_respaldo="hecho", evidencia=_ev())
        return segs

    def _tercer_voto(self, prompt: str):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        r = self.reglas
        if r.tercer_voto == "invalido":
            return self._respuesta(None, prompt, error="json_invalido (doble)")
        mat_json = _bloque(prompt, "MATERIAL_NO_CONFIABLE")
        unidad = _bloque(prompt, "UNIDAD_NO_CONFIABLE")
        mat = self._material(mat_json)
        jur = tuple(mat_json.get("jurisdicciones_configuradas") or ())
        res = _estado_honesto(unidad["afirmacion"], mat, r, jur)
        if r.tercer_voto:
            res = {"tipo": "hecho_expediente", "estado": r.tercer_voto,
                   "subtipo": "hecho" if r.tercer_voto == "sin_respaldo" else None, "ev": {}}
        return self._respuesta({"schema": P.ESQUEMA_TERCER_VOTO, "id_unidad": unidad["id_unidad"],
                                "estado": res["estado"], "evidencia": _ev(**res.get("ev", {})),
                                "subtipo_sin_respaldo": res.get("subtipo"), "motivo": "doble"}, prompt)

    def _cubierto(self, case_id: str, candidate: str) -> bool:
        nc = self.reglas.no_cubiertos.get(case_id)
        if nc is True:
            return False
        if isinstance(nc, (set, frozenset, list, tuple)):
            return candidate not in nc
        return True

    def _pasada2(self, prompt: str, esquema: dict):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        r = self.reglas
        paq = _bloque(prompt, "MATERIAL_NO_CONFIABLE")
        clave = _bloque(prompt, "CLAVE_DE_RESPUESTA")
        cid = clave.get("case_id", "")
        self.memo[paq["candidate_id"]] = cid
        sid0 = paq["segmentos"][0]["id"] if paq.get("segmentos") else None
        segs0 = [sid0] if sid0 else []
        cub = self._cubierto(cid, paq["candidate_id"])
        hechos = [{"id": h["id"], "expresa_correctamente": cub, "atribuye_bien": cub, "cubierto": cub,
                   "segmentos": segs0 if cub else [], "motivo": "doble"}
                  for h in clave.get("hechos_materiales") or []]
        resol = "laguna_declarada" if cid in r.puntos_laguna else "resuelto"
        puntos = [{"id": p["id"], "resolucion": resol if cub else "no_tratado",
                   "segmentos": segs0 if cub else [], "motivo": "doble"}
                  for p in clave.get("puntos_materiales") or []]
        clase = r.conducta.get(cid, "definitiva")
        limitada = clase == "limitada_expresa"
        conducta = {"clase": clase, "dice_lo_encontrado": True, "dice_lo_no_leido": limitada,
                    "declara_no_definitivo": limitada, "segmentos": segs0, "motivo": "doble"}
        salida = {"schema": esquema["properties"]["schema"]["enum"][0], "candidate_id": paq["candidate_id"],
                  "hechos": hechos, "puntos": puntos, "conducta": conducta,
                  "aprobaria_sin_editar": {"respuesta": r.aprobaria, "justificacion": "doble"}}
        if "negativa_correcta" in esquema.get("properties", {}):
            riesgo = cid in P.CASOS_A_RIESGO
            ok = riesgo and cub
            salida["negativa_correcta"] = {"aplica": riesgo, "respuesta": ("si" if ok else "no") if riesgo else None,
                                           "segmentos": segs0 if ok else [], "motivo": "doble"}
        return self._respuesta(salida, prompt)

    def _voto_cobertura(self, prompt: str):
        from mia.eval.banco04 import protocolo as P  # noqa: WPS433
        paq = _bloque(prompt, "MATERIAL_NO_CONFIABLE")
        hecho = _bloque(prompt, "HECHO")
        v = self.reglas.votos_cobertura
        if v is None:
            cand = paq.get("candidate_id")
            v = self._cubierto(self.memo.get(cand, ""), cand)
        return self._respuesta({"schema": P.ESQUEMA_VOTO_COBERTURA, "id_hecho": hecho["id"],
                                "expresa_correctamente": v, "atribuye_bien": v, "cubierto": v,
                                "motivo": "doble"}, prompt)


def runners(opus: Optional[Reglas] = None, codex: Optional[Reglas] = None, *,
            cli_claude: str = "doble", cli_codex: str = "doble", opus_kw: Optional[dict] = None,
            codex_kw: Optional[dict] = None) -> dict:
    """`{"opus": ..., "codex": ...}` con un memo compartido (candidato → caso) para los votos."""
    memo: dict = {}
    return {"opus": JuezDoble("opus", opus, memo=memo, cli_version=cli_claude, **(opus_kw or {})),
            "codex": JuezDoble("codex", codex, memo=memo, cli_version=cli_codex, **(codex_kw or {}))}
