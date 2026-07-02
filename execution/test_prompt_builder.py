"""
Mia · test_prompt_builder.py — gate del Módulo 1b (10 capas + AuxiliaryClient).

Verifica OFFLINE (sin red ni proxy LiteLLM):
  1. Las 10 capas en el ORDEN correcto (índices 1..10, nombres y tiers).
  2. Las capas 1-6 marcadas como CACHED (prefijo estable, TTL 1h); 7-10 no.
  3. compression forzado a mia-local bajo política 'soberano' (CP2, decisión #27)
     AUNQUE se pase otro `model` — tanto en resolve_model como atravesando
     AuxiliaryClient.complete() de punta a punta (con un cliente OpenAI falso, sin
     red). El gate fija la política explícitamente; el bloqueo bajo las 3 políticas
     lo cubre execution/test_model_policy.py.
  4. El mapa TASK_MODELS está completo (router + tareas auxiliares).
  5. El prompt ensamblado respeta el orden de las capas y las costuras vacías no
     aportan texto.

El LLM se simula con un cliente falso inyectado en llm._client (no se llama a
ningún proveedor real). Salida: exit 0 = PASS.

Se ejecuta con el python de mia/.venv:
    .venv\\Scripts\\python.exe execution\\test_prompt_builder.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia import config
from mia.agent import auxiliary_client as ac
from mia.agent import core, llm, prompt_builder as pb

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# Contrato esperado de las 10 capas: (index, name, tier, cached)
_EXPECTED = [
    (1, "identity", "stable", True),
    (2, "methodology", "stable", True),
    (3, "citation", "stable", True),
    (4, "tools", "stable", True),
    (5, "user_comms", "stable", True),
    (6, "skills", "stable", True),
    (7, "matter", "context", False),
    (8, "session_instructions", "context", False),
    (9, "memory", "volatile", False),
    (10, "metadata", "volatile", False),
]


# --- 1 + 3 · las 10 capas en orden y el marcado de cacheo ----------------------
def test_layers_order_and_cache() -> None:
    agent = core.MiaAgent(tenant_id="t-1")
    layers = pb.build_layers(agent)

    check("hay exactamente 10 capas", len(layers) == 10)

    order_ok = all(
        layers[i]["index"] == exp[0] and layers[i]["name"] == exp[1] and layers[i]["tier"] == exp[2]
        for i, exp in enumerate(_EXPECTED)
    )
    check("las 10 capas en orden correcto (index/name/tier)", order_ok)

    # Índices estrictamente 1..10 en secuencia.
    check("índices son 1..10 en secuencia", [l["index"] for l in layers] == list(range(1, 11)))

    # Capas 1-6 cached; 7-10 no.
    cached_ok = all(layers[i]["cached"] == exp[3] for i, exp in enumerate(_EXPECTED))
    check("capas 1-6 marcadas cached, 7-10 no", cached_ok)

    # Doble check vía el tier: cached <=> tier == stable.
    check("cached <=> tier=='stable'", all(l["cached"] == (l["tier"] == "stable") for l in layers))

    # Exactamente 6 capas cacheadas y son las 1..6.
    cached_idx = [l["index"] for l in layers if l["cached"]]
    check("exactamente las capas {1..6} son cached", cached_idx == [1, 2, 3, 4, 5, 6])

    check("TTL del prefijo STABLE = 3600s (1h)", pb.STABLE_CACHE_TTL_SECONDS == 3600)


# --- 5 · ensamblaje y costuras vacías ------------------------------------------
def test_assembly() -> None:
    agent = core.MiaAgent(tenant_id="t-1")
    layers = {l["name"]: l for l in pb.build_layers(agent)}

    # Costuras (tools/skills/matter/memory) vacías por defecto.
    for seam in ("tools", "skills", "matter", "memory"):
        check(f"costura '{seam}' vacía por defecto", layers[seam]["content"] == "")
    # session_instructions vacía si no hay system_message.
    check("session_instructions vacía sin system_message", layers["session_instructions"]["content"] == "")
    # Capas activas con contenido.
    for active in ("identity", "methodology", "citation", "user_comms", "metadata"):
        check(f"capa '{active}' tiene contenido", bool(layers[active]["content"]))

    prompt = pb.build_system_prompt(agent)
    check("el prompt empieza con la identidad (L1)", prompt.startswith(core.DEFAULT_IDENTITY))
    # Orden en el texto ensamblado: identidad < metodología < citación < comms < fecha.
    pos = lambda s: prompt.find(s)
    ordered = (
        pos(core.DEFAULT_IDENTITY[:30])
        < pos(pb.METHODOLOGY[:30])
        < pos(pb.CITATION_POLICY[:30])
        < pos(pb.USER_COMMS[:30])
        < pos("Fecha de la sesión")
    )
    check("orden de capas preservado en el texto", ordered)

    # Las costuras vacías NO aportan texto: con todas vacías, el prompt no trae los
    # encabezados de matter. Al llenar una costura, sí aparece.
    agent.matter_context = "Demanda de responsabilidad civil, cuantía media."
    agent.invalidate_prompt()  # no cachea en build directo, pero deja claro el patrón
    prompt2 = pb.build_system_prompt(agent)
    check("al llenar la costura 'matter' aparece en el prompt", "## Asunto en curso" in prompt2)
    check("la costura 'matter' (L7) va tras las stable y antes de la metadata",
          prompt2.find("## Asunto en curso") > prompt2.find(pb.USER_COMMS[:30])
          and prompt2.find("## Asunto en curso") < prompt2.find("Fecha de la sesión"))


# --- 4 · TASK_MODELS completo --------------------------------------------------
def test_task_models() -> None:
    expected_tasks = {
        "main", "compression", "verification",
        "title_generation", "session_search", "web_extract", "vision",
    }
    check("TASK_MODELS contiene todas las tareas esperadas",
          expected_tasks.issubset(set(ac.TASK_MODELS)))
    check("compression -> mia-local en el mapa (decisión #23)", ac.TASK_MODELS["compression"] == "mia-local")
    # H.5: TASK_MODELS = primer eslabón (proveedor preferido) de cada cadena de fallback.
    # main prefiere claude-sonnet (cae a mia-local en call_llm).
    check("main -> claude-sonnet en el mapa (1er eslabón de la cadena H.5)",
          ac.TASK_MODELS["main"] == "claude-sonnet")
    # Ningún alias inexistente: solo claude-haiku, claude-sonnet o MIA_MODEL.
    valid = {"claude-haiku", "claude-sonnet", config.MIA_MODEL}
    check("todos los alias de TASK_MODELS existen (haiku/sonnet/MIA_MODEL)",
          all(v in valid for v in ac.TASK_MODELS.values()))


# --- 2 · compression bloqueado a haiku, incl. atravesando AuxiliaryClient -------
class _FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        msg = SimpleNamespace(content="[texto auxiliar]")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def test_compression_lock() -> None:
    # CP2: el ruteo depende de la política de modelo activa (decisión #27). Este gate
    # fija 'soberano' explícitamente (patrón de test_model_policy.py): bajo esa política
    # compression→mia-local, que es lo que el cliente falso de abajo espera; el bloqueo
    # bajo 'suscripcion'/'nube' lo cubre test_model_policy.py.
    tok = llm.set_model_policy("soberano")
    try:
        # Nivel resolve_model / model_for (sin red).
        check("model_for(compression) -> mia-local (soberano)",
              ac.AuxiliaryClient.model_for("compression") == "mia-local")
        check("model_for(compression, model=sonnet) IGNORA el override",
              ac.AuxiliaryClient.model_for("compression", "claude-sonnet") == "mia-local")
        check("model_for(compression, model=opus) IGNORA el override",
              ac.AuxiliaryClient.model_for("compression", "claude-opus") == "mia-local")

        # Punta a punta a través de AuxiliaryClient.complete() con cliente falso.
        fake = _FakeClient()
        original = llm._client
        llm._client = fake  # _get_client() devuelve este si no es None
        try:
            out = ac.aux.complete("Comprime este expediente.", task="compression", model="claude-sonnet")
            check("aux.complete devuelve texto", out == "[texto auxiliar]")
            check("compression: el gateway recibe mia-local (no sonnet)",
                  fake.chat.completions.last_kwargs["model"] == "mia-local")

            # Tarea NO bloqueada: el override de model SÍ pasa.
            ac.aux.complete("Verifica esta cita.", task="verification", model="claude-haiku")
            check("verification: el override de model SÍ pasa al gateway",
                  fake.chat.completions.last_kwargs["model"] == "claude-haiku")

            # Sin model: la verification usa su default mia-local ('soberano').
            ac.aux.complete("Verifica esta otra.", task="verification")
            check("verification sin override -> mia-local (soberano)",
                  fake.chat.completions.last_kwargs["model"] == "mia-local")
        finally:
            llm._client = original
    finally:
        llm.reset_model_policy(tok)


def main() -> int:
    print("== Módulo 1b · prompt_builder (10 capas) + AuxiliaryClient ==")
    test_layers_order_and_cache()
    test_assembly()
    test_task_models()
    test_compression_lock()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
