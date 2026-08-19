"""
Mia · test_gates_no_ciegos.py — META-GATE: prueba las pruebas.

Recorre el propio código de `execution/` y busca ASERCIONES QUE PUEDEN QUEDARSE CIEGAS
porque leen el `content` de un mensaje que, en su cadena, ya no es un string.

═══ POR QUÉ EXISTE ════════════════════════════════════════════════════════════════
El commit e8ce3b3 (17-jul) cableó el prefix caching de Anthropic. Desde entonces
`llm._messages_with_cache` reemplaza el `content` del PRIMER mensaje `system` de un
string por una LISTA DE BLOQUES:

    [{"type":"text","text":<prefijo estable>,"cache_control":{...}},
     {"type":"text","text":<resto>}]

…pero SOLO para los alias de la API directa de Anthropic (`llm._ANTHROPIC_CACHE_ALIASES`).

Las suites instalan su cliente falso en `llm._client` o `llm._call_with_retries`, o sea
POR DEBAJO de esa conversión. Lo que queda registrado es la LISTA, no el string. Y ahí:

    assert "texto esperado" in mensaje["content"]

dejó de preguntar «¿contiene este texto?» y pasó a preguntar «¿es este texto uno de los
bloques?», que da False SIEMPRE. El gate ya no medía la propiedad: medía el tipo del
contenedor. Casos reales: `test_context_recovery::b5` (rojo desde el 17-jul sin que
nadie lo notara, y encima mal atribuido) y `test_retrieval_knowledge::toks()` (medía
`str(content)` —el repr del contenedor, con llaves y metadatos— inflando 37 tokens y
escondiendo una regresión real de forma latente).

El arreglo canónico es un ayudante `content_text(msg)` que reconstruye el texto
concatenando los bloques (fb30664, 479f78f).

═══ LAS DOS CLASES, Y POR QUÉ SE TRATAN DISTINTO ══════════════════════════════════
  · NEGATIVA (`X not in content`) → al romperse se queda VERDE PARA SIEMPRE. Nadie se
    entera nunca. Ahí viven los controles de confidencialidad y de lenguaje ("esta jerga
    NO debe aparecer", "este dato NO debe filtrarse"). ⇒ ERROR. Sin excepciones, sin
    waiver: este gate se pone ROJO y hay que usar `content_text`.
  · POSITIVA (`X in content`) y OPERACIÓN DE CADENA (`.upper()`, `str(...)`, …) → al
    romperse se pone ROJA o revienta con AttributeError. Es molesto, pero SE VE.
    ⇒ AVISO inventariado, no tumba la entrega. (Si además tumbara la entrega, este gate
    nacería rojo sobre sitios hoy sanos y el primero que lo viera lo desactivaría, que es
    exactamente el fracaso que viene a impedir.)

═══ QUÉ HACE ══════════════════════════════════════════════════════════════════════
  P · comprueba contra el código REAL que la premisa del análisis sigue en pie
      (¿sigue convirtiéndose solo el system? ¿solo los alias con caché? ¿sigue rompiendo
      el `in`?). Si el motor cambia, este gate se pone rojo y pide que lo ensanchen —
      en vez de seguir tranquilizando sobre una premisa caducada.
  E · calcula qué suites están EXPUESTAS leyendo el código (no adivinando).
  A · analiza el AST buscando lecturas de `content` de un MENSAJE en posición de pajar.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_gates_no_ciegos.py
    .venv\\Scripts\\python.exe execution\\test_gates_no_ciegos.py --verbose
"""
from __future__ import annotations

import ast
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm, prompt_builder

EXEC_DIR = ROOT / "execution"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ══ 0 · vocabulario del análisis ═══════════════════════════════════════════════════

# Atributos de `llm` que, si se les asigna un falso, quedan POR DEBAJO de la conversión.
_BELOW_CONVERSION = frozenset({"_client", "_call_with_retries"})
# Atributos que quedan POR ENCIMA: quien parchea aquí es inmune por construcción.
_ABOVE_CONVERSION = frozenset({"call_llm", "call_llm_sync", "acall_llm"})

# Métodos que solo existen (o cambian de significado en silencio) sobre un str.
_STR_ONLY_METHODS = frozenset({
    "startswith", "endswith", "lower", "upper", "casefold", "title", "strip", "lstrip",
    "rstrip", "split", "rsplit", "splitlines", "replace", "format", "encode", "find",
    "rfind", "index", "rindex", "count", "partition", "rpartition", "removeprefix",
    "removesuffix", "join", "ljust", "rjust", "zfill",
})
# Envolturas que NO arreglan nada: `str(content)` es precisamente el defecto de
# test_retrieval_knowledge::toks (medía el repr del contenedor, no el prompt).
_FAKE_FIXES = frozenset({"str", "repr"})
# El arreglo de verdad: reconstruye el texto concatenando los bloques.
_REAL_FIX_HINT = "content_text"

# Un `content` solo es el de un MENSAJE si su portador se nombra como tal. Sin este
# filtro el gate confundiría notas de conocimiento (`ka[0]["content"]`), documentos
# (`d["content"]`) o filas de base con mensajes, y gritaría en decenas de sitios sanos.
_MESSAGE_TOKENS = ("message", "msgs", "msg", "hist", "conversation", "convo", "turns",
                   "prompt_messages", "sent", "payload_messages", "chat")


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover — AST exótico
        return "<?>"


# ══ P · la premisa del análisis, verificada contra el código real ══════════════════
# Este gate acota deliberadamente (solo el system, solo los alias con caché). Si el motor
# deja de cumplir eso, el acotamiento se vuelve una VENDA. Se comprueba en vivo.

def premise_checks() -> None:
    print("\n-- P · premisa del análisis (medida contra llm.py, no supuesta) --")

    stable, rest = "PREFIJO ESTABLE DEL SYSTEM. ", "resto volátil del system."
    system_text = stable + rest
    prompt_builder._register_cache_boundary(system_text, stable)

    msgs = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "pregunta del abogado"},
        {"role": "assistant", "content": "respuesta previa"},
    ]
    cache_aliases = sorted(llm._ANTHROPIC_CACHE_ALIASES)
    check("p0 · existen alias con prefix caching declarados en llm", bool(cache_aliases))

    conv = llm._messages_with_cache(msgs, cache_aliases[0]) if cache_aliases else msgs

    check("p1 · con un alias con caché, el content del SYSTEM deja de ser un str "
          "(es la conversión que ciega las aserciones)",
          isinstance(conv[0].get("content"), list))
    check("p2 · la conversión NO toca user ni assistant — el acotamiento de este gate "
          "a la PRIMERA capa system sigue siendo válido",
          isinstance(conv[1].get("content"), str) and isinstance(conv[2].get("content"), str))
    check("p3 · la concatenación de los bloques reconstruye el system BYTE A BYTE "
          "(por eso content_text no relaja nada)",
          "".join(b.get("text", "") for b in conv[0]["content"]) == system_text)
    check("p4 · DEMOSTRACIÓN del defecto: `in` es True sobre el str y False sobre los "
          "bloques, sin lanzar excepción — se rompe EN SILENCIO",
          (stable in system_text) is True and (stable in conv[0]["content"]) is False)

    non_cache = next((a for ch in llm._TASK_FALLBACK_CHAINS.values() for a in ch
                      if a not in llm._ANTHROPIC_CACHE_ALIASES), "mia-local")
    intact = llm._messages_with_cache(msgs, non_cache)
    check(f"p5 · con un alias sin caché ({non_cache}) no se convierte nada — por eso una "
          "suite anclada a una política sin caché NO está expuesta",
          all(isinstance(m.get("content"), str) for m in intact))


# ══ E · exposición: qué suites pueden sufrirlo, leído del código ═══════════════════

def _policy_reaches_cache(policy: str) -> bool:
    """¿La política `policy` puede acabar llamando a un alias con prefix caching?"""
    merged = dict(llm._TASK_FALLBACK_CHAINS)
    merged.update(llm._POLICY_CHAINS.get(policy, {}))
    return any(a in llm._ANTHROPIC_CACHE_ALIASES for ch in merged.values() for a in ch)


class _Exposure:
    """Dos condiciones, ambas necesarias, ambas leídas del código:
       (1) la suite instala su falso POR DEBAJO de la conversión, y
       (2) su política puede resolver a un alias con prefix caching."""

    def __init__(self, tree: ast.AST) -> None:
        self.installs_below = False
        self.patches_above = False
        self.policies: set[str] = set()
        self.dynamic_policy = False
        for n in ast.walk(tree):
            if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Attribute):
                        if t.attr in _BELOW_CONVERSION:
                            self.installs_below = True
                        elif t.attr in _ABOVE_CONVERSION:
                            self.patches_above = True
            if isinstance(n, ast.Call):
                fn = n.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name == "setattr" or (isinstance(fn, ast.Name) and fn.id == "setattr"):
                    if len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                        if n.args[1].value in _BELOW_CONVERSION:
                            self.installs_below = True
                if name == "set_model_policy":
                    if n.args and isinstance(n.args[0], ast.Constant) and \
                            isinstance(n.args[0].value, str):
                        self.policies.add(n.args[0].value)
                    else:
                        self.dynamic_policy = True

    @property
    def exposed(self) -> bool:
        if not self.installs_below:
            return False                      # inmune: parchea arriba, o no toca el LLM
        if self.policies and not self.dynamic_policy:
            # Ancla explícitamente sus políticas: expuesta solo si alguna alcanza caché.
            return any(_policy_reaches_cache(p) for p in self.policies)
        return True                           # sin anclaje → política por defecto → expuesta

    @property
    def reason(self) -> str:
        if not self.installs_below:
            return ("inmune: no instala ningún falso por debajo de la conversión"
                    + (" (parchea llm.call_llm, por ENCIMA)" if self.patches_above else ""))
        if not self.exposed:
            return (f"inmune: ancla su política a {sorted(self.policies)}, cuyas cadenas "
                    "no alcanzan ningún alias con prefix caching")
        anchor = f"políticas {sorted(self.policies)}" if self.policies else "política por defecto"
        return f"instala su falso por debajo de la conversión · {anchor} alcanza un alias con caché"


# ══ A · el analizador de aserciones ════════════════════════════════════════════════

class Finding:
    def __init__(self, path: Path, lineno: int, kind: str, snippet: str, carrier: str) -> None:
        self.path, self.lineno, self.kind = path, lineno, kind
        self.snippet, self.carrier = snippet, carrier

    @property
    def silent(self) -> bool:
        return self.kind == "NEGATIVA"


class _Analyzer(ast.NodeVisitor):
    """Busca lecturas del `content` de un mensaje en posición de PAJAR.

    Se eligió `ast` y no expresiones regulares por tres razones que una regex no puede
    cubrir: (a) distinguir el pajar de la aguja — `d["content"] not in docs` es sanísimo
    y `x not in d["content"]` es el defecto, y una regex ve la misma línea; (b) seguir el
    valor a través de una variable intermedia (`sys2 = msgs[0]["content"]` … `x in sys2`),
    que es la forma EXACTA del defecto real de b5; (c) reconocer el arreglo
    (`content_text(...)`) sin castigar a quien lo aplicó.
    """

    def __init__(self) -> None:
        self.tainted: dict[str, ast.AST] = {}   # nombre → expresión del MENSAJE portador
        self.loop_iter: dict[str, str] = {}     # variable de bucle → fuente iterada
        self.findings: list[Finding] = []

    # ── reconocimiento de formas ──────────────────────────────────────────────────
    @staticmethod
    def _content_carrier(node: ast.AST) -> ast.AST | None:
        """Si `node` lee el `content` de un dict, devuelve la expresión PORTADORA."""
        if isinstance(node, ast.Subscript):
            k = node.slice
            if isinstance(k, ast.Constant) and k.value == "content":
                return node.value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "content"):
            return node.func.value
        return None

    def _is_message(self, carrier: ast.AST) -> bool:
        """¿El portador es un MENSAJE (y no una nota, un documento o una fila)?"""
        text = _src(carrier).lower()
        if isinstance(carrier, ast.Name) and carrier.id in self.loop_iter:
            text += " " + self.loop_iter[carrier.id].lower()
        return any(tok in text for tok in _MESSAGE_TOKENS)

    def _is_system_layer(self, carrier: ast.AST, varname: str | None = None) -> bool:
        """¿Puede este portador ser el PRIMER mensaje system, el único que se convierte?

        Índice literal 0 → sí (el system va siempre primero). Índice literal distinto de
        0 → no. Índice no resoluble (variable de bucle, slice, `-1` sobre una lista que
        empieza en el system…) → sí, por precaución: un recorrido de todos los mensajes
        pasa también por el system.
        """
        if varname and ("sys" in varname.lower()):
            return True
        if "sys" in _src(carrier).lower():
            return True
        if isinstance(carrier, ast.Subscript):
            k = carrier.slice
            if isinstance(k, ast.Constant) and isinstance(k.value, int):
                return k.value == 0
            if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.USub):
                return False                    # msgs[-1] es el último turno, nunca el system
        return True

    @staticmethod
    def _sanitized(node: ast.AST) -> bool:
        """¿Pasa ya por el ayudante que reconstruye el texto?"""
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "") or ""
            if _REAL_FIX_HINT in name:
                return True
        return False

    def _resolve(self, node: ast.AST) -> tuple[ast.AST, str | None] | None:
        """Devuelve (portador, nombre-de-variable) si `node` es contenido de mensaje."""
        carrier = self._content_carrier(node)
        if carrier is not None:
            return carrier, None
        if isinstance(node, ast.Name) and node.id in self.tainted:
            return self.tainted[node.id], node.id
        return None

    # ── recolección de contexto ───────────────────────────────────────────────────
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """El cuerpo del PROPIO ayudante no se analiza.

        `content_text` es el arreglo, y por dentro hace justo lo que el gate persigue
        (`c = msg.get("content")`, `str(c or "")`) — pero ahí es correcto: está
        DISTINGUIENDO el str de la lista para reconstruir el texto. Analizarlo dentro
        castigaría precisamente a quien aplicó el arreglo, que es lo contrario de lo
        que este gate quiere incentivar.
        """
        if _REAL_FIX_HINT in node.name:
            return
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_For(self, node: ast.For) -> None:
        if isinstance(node.target, ast.Name):
            self.loop_iter[node.target.id] = _src(node.iter)
        self.generic_visit(node)

    def _scan_comprehensions(self, tree: ast.AST) -> None:
        """Variables de comprensión → su fuente iterada (`for m in sent_hist`), para poder
        decidir después si `m` es un mensaje. NodeVisitor no da este mapeo por sí solo."""
        for n in ast.walk(tree):
            if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in n.generators:
                    if isinstance(gen.target, ast.Name):
                        self.loop_iter[gen.target.id] = _src(gen.iter)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self._sanitized(node.value):
            carrier = self._content_carrier(node.value)
            if carrier is None and isinstance(node.value, ast.Name):
                carrier = self.tainted.get(node.value.id)
            if carrier is None and isinstance(node.value, ast.Call) \
                    and isinstance(node.value.func, ast.Name) \
                    and node.value.func.id in _FAKE_FIXES and node.value.args:
                # `str(msg["content"])` NO desinfecta: mide el repr del contenedor.
                carrier = self._content_carrier(node.value.args[0])
            if carrier is not None:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.tainted[t.id] = carrier
        self.generic_visit(node)

    # ── sitios que se reportan ────────────────────────────────────────────────────
    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comp in zip(node.ops, node.comparators):
            if not isinstance(op, (ast.In, ast.NotIn)):
                continue
            # Solo importa el PAJAR (lado derecho). `d["content"] not in docs` es correcto.
            got = self._resolve(comp)
            if got is None:
                continue
            carrier, varname = got
            if not self._is_message(carrier) or not self._is_system_layer(carrier, varname):
                continue
            self.findings.append(Finding(
                Path("?"), node.lineno,
                "NEGATIVA" if isinstance(op, ast.NotIn) else "POSITIVA",
                _src(node)[:150], _src(carrier)))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        # `msg["content"].upper()` / `.startswith(...)` → revienta o miente sobre una lista.
        if isinstance(fn, ast.Attribute) and fn.attr in _STR_ONLY_METHODS:
            got = self._resolve(fn.value)
            if got is not None:
                carrier, varname = got
                if self._is_message(carrier) and self._is_system_layer(carrier, varname):
                    self.findings.append(Finding(
                        Path("?"), node.lineno, "OP-CADENA", _src(node)[:150], _src(carrier)))
        # `str(msg["content"])` → mide el repr del contenedor (defecto de retrieval_knowledge).
        if isinstance(fn, ast.Name) and fn.id in _FAKE_FIXES and node.args:
            got = self._resolve(node.args[0])
            if got is not None:
                carrier, varname = got
                if self._is_message(carrier) and self._is_system_layer(carrier, varname):
                    self.findings.append(Finding(
                        Path("?"), node.lineno, "OP-CADENA", _src(node)[:150], _src(carrier)))
        self.generic_visit(node)


def analyze(path: Path) -> tuple[_Exposure, list[Finding]] | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return None
    exp = _Exposure(tree)
    if not exp.exposed:
        return exp, []
    an = _Analyzer()
    an._scan_comprehensions(tree)
    an.visit(tree)
    for f in an.findings:
        f.path = path
    return exp, an.findings


# ══ informe ════════════════════════════════════════════════════════════════════════

_WHY = {
    "NEGATIVA": (
        "PELIGRO SILENCIOSO. El `content` del system llega como LISTA de bloques, así que\n"
        "     `not in` da True SIEMPRE y la aserción PASA PARA SIEMPRE aunque el texto que\n"
        "     prohíbe esté ahí. Un control de confidencialidad escrito así no protege nada."),
    "POSITIVA": (
        "Visible al romperse: `in` da False sobre la lista de bloques y el check se pone\n"
        "     rojo. Molesto y desorientador (parecerá un fallo de producto), no silencioso."),
    "OP-CADENA": (
        "Visible al romperse: sobre una lista de bloques revienta con AttributeError, o\n"
        "     —si es `str(...)`— mide el REPR del contenedor (llaves, comillas, cache_control)\n"
        "     en vez del prompt. Fue el defecto de test_retrieval_knowledge::toks()."),
}

_FIX = (
    "ARREGLO: leer el mensaje con el ayudante que reconstruye el texto a partir de los\n"
    "     bloques, en vez de tocar `content` directamente:\n\n"
    "         def content_text(msg: dict) -> str:\n"
    "             c = msg.get(\"content\")\n"
    "             if isinstance(c, str):\n"
    "                 return c\n"
    "             if isinstance(c, list):\n"
    "                 return \"\".join(str(b.get(\"text\") or \"\") for b in c if isinstance(b, dict))\n"
    "             return str(c or \"\")\n\n"
    "     y luego `assert \"x\" not in content_text(msg)`.\n"
    "     Referencia: commits fb30664 y 479f78f. NO sirve `str(msg[\"content\"])`: eso mide\n"
    "     el repr del contenedor, que es el otro defecto que este gate persigue.")


def report(f: Finding) -> str:
    rel = f.path.relative_to(ROOT).as_posix()
    return (f"\n  ── {rel}:{f.lineno}  [{f.kind}]\n"
            f"     {f.snippet}\n"
            f"     portador del mensaje: {f.carrier}\n"
            f"     {_WHY[f.kind]}\n"
            f"     {_FIX}\n")


def run() -> None:
    premise_checks()

    print("\n-- E · exposición de las suites (leída del código) --")
    t0 = time.perf_counter()
    files = sorted(EXEC_DIR.glob("test_*.py"))
    exposed: list[tuple[Path, _Exposure]] = []
    immune_below = 0
    all_findings: list[Finding] = []
    parsed = 0

    for p in files:
        got = analyze(p)
        if got is None:
            continue
        parsed += 1
        exp, findings = got
        if exp.exposed:
            exposed.append((p, exp))
            all_findings.extend(findings)
        elif exp.installs_below:
            immune_below += 1
            if VERBOSE:
                print(f"     · {p.name}: {exp.reason}")
    elapsed = time.perf_counter() - t0

    check(f"e1 · el barrido analiza las {parsed} suites de execution/ (patrón, no lista fija)",
          parsed >= 100)
    print(f"     suites EXPUESTAS: {len(exposed)} · inmunes por política anclada: "
          f"{immune_below} · resto inmune por parchear arriba o no tocar el LLM: "
          f"{parsed - len(exposed) - immune_below}")
    if VERBOSE:
        for p, exp in exposed:
            print(f"     · {p.name}: {exp.reason}")

    print("\n-- A · aserciones que pueden quedarse ciegas --")
    silent = [f for f in all_findings if f.silent]
    visible = [f for f in all_findings if not f.silent]

    if silent:
        print("\n  ################  CLASE SILENCIOSA — ESTO TUMBA LA ENTREGA  ################")
        for f in silent:
            print(report(f))
    check("a1 · CERO aserciones NEGATIVAS (`not in`) sobre el content de un mensaje en "
          "suites expuestas — la clase que se queda VERDE PARA SIEMPRE al romperse",
          not silent)

    print(f"\n  AVISOS (clase visible, no tumban la entrega): {len(visible)}")
    for f in visible:
        rel = f.path.relative_to(ROOT).as_posix()
        print(f"     · {rel}:{f.lineno} [{f.kind}] {f.snippet[:100]}")
    if visible and not VERBOSE:
        print("       (--verbose para el detalle, la causa y el arreglo de cada uno)")
    elif visible and VERBOSE:
        for f in visible:
            print(report(f))

    check("a2 · el inventario de la clase visible se produjo sin errores de análisis",
          all_findings is not None)
    print(f"\n     coste del barrido: {elapsed:.2f}s")


def main() -> int:
    print("== META-GATE · aserciones ciegas por el prefix caching (content str → bloques) ==")
    run()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("gates no ciegos OK — ninguna aserción negativa puede quedarse verde para siempre.")
        return 0
    print("gates no ciegos FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
