"""Firma normalizada de un comando (§4.4) e instantáneas de acreditación DE PRUEBA.

La normalización es la literal de §4.4:
  · el ejecutable pasa a su nombre de archivo en minúsculas;
  · las rutas de `--output-schema` y `--output-last-message` (Codex) pasan a `<schema>` y `<salida>`;
  · se conservan el orden y todos los demás tokens;
  · `sha256` = sha256 del JSON canónico de `argv_normalizado` (sort_keys, sin espacios, UTF-8 sin
    escapar: la misma serialización canónica que `run_banco04.manifiesto_sha256` y la custodia).

Las instantáneas de prueba acreditan TODAS las firmas que los dobles pueden generar: todas las
combinaciones de modelo y esfuerzo de `subscription_llm._build_command` y de
`codex_subscription_llm._command`, y las de los jueces dobles. La versión del CLI es la REAL del
equipo (`run_banco04.version_cli()`), porque R1 la registra así (§9.4).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PureWindowsPath
from typing import Iterable, Optional

from . import entorno

EXE_CLAUDE = r"C:\banco04-dobles\bin\Claude.exe"
EXE_CODEX = r"C:\banco04-dobles\bin\Codex.exe"
AUTOR = "autor-independiente-de-pruebas (banco04-cadena)"
FECHA = "2026-10-12"

EVIDENCIA_CLAUDE = "execution/fixtures_banco04_cadena/evidencia/claude-cli-doble.json"
EVIDENCIA_CODEX = "execution/fixtures_banco04_cadena/evidencia/codex-cli-doble.jsonl"

# Comandos de los jueces dobles (los runners dobles los devuelven en `comando_sin_prompt`).
JUEZ_CLAUDE_ARGV = [EXE_CLAUDE, "-p", "--output-format", "json", "--max-turns", "1",
                    "--model", "opus", "--effort", "high"]
JUEZ_CODEX_ARGV = [EXE_CODEX, "exec", "--ephemeral", "--sandbox", "read-only", "--model",
                   "gpt-6-astra", "-c", 'model_reasoning_effort="high"', "--output-schema",
                   r"C:\Temp\juez-x\schema.json", "--output-last-message", r"C:\Temp\juez-x\out.json",
                   "--json", "-"]
CAMPO_IDENTIDAD_CODEX = "model"


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def normalizar(argv: Iterable) -> list[str]:
    a = [str(x) for x in argv]
    if not a:
        return a
    out = [PureWindowsPath(a[0]).name.lower()]
    i = 1
    while i < len(a):
        tok = a[i]
        out.append(tok)
        if tok == "--output-schema" and i + 1 < len(a):
            out.append("<schema>")
            i += 2
            continue
        if tok == "--output-last-message" and i + 1 < len(a):
            out.append("<salida>")
            i += 2
            continue
        i += 1
    return out


def firma(argv: Iterable) -> dict:
    n = normalizar(argv)
    return {"argv_normalizado": n, "sha256": hashlib.sha256(canon(n)).hexdigest()}


def comandos_claude() -> list[list[str]]:
    from mia.agent import subscription_llm as sl  # noqa: WPS433
    hints = [None, *sorted(sl._ACCEPTED_MODEL_HINTS)]
    esfuerzos = [None, *sorted(sl._ACCEPTED_EFFORTS)]
    vistos, out = set(), []
    for h in hints:
        for e in esfuerzos:
            cmd = sl._build_command(EXE_CLAUDE, h, e)
            k = tuple(cmd)
            if k not in vistos:
                vistos.add(k)
                out.append(list(cmd))
    return out


def comandos_codex() -> list[list[str]]:
    from mia.agent import codex_subscription_llm as cx  # noqa: WPS433
    out, vistos = [], set()
    for e in ("low", "medium", "high", "xhigh"):
        cmd = cx._command(Path(EXE_CODEX), schema=Path(r"C:\Temp\x\output.schema.json"),
                          output=Path(r"C:\Temp\x\last-message.json"), effort=e)
        k = tuple(normalizar(cmd))
        if k not in vistos:
            vistos.add(k)
            out.append(list(cmd))
    return out


def _evidencia(archivo: str, descripcion: str) -> list[dict]:
    ruta = entorno.ROOT / archivo
    return [{"archivo": archivo, "sha256": entorno.sha256_archivo(ruta), "descripcion": descripcion}]


def entrada_claude(n: int, cli_version: str, argv: list[str], *, omitido: bool = False) -> dict:
    conducta = {c: ("omitido_si_cero" if omitido else "presente_siempre")
                for c in ("cache_creation_input_tokens", "cache_read_input_tokens")}
    return {"id": f"claude-{n:04d}", "familia": "claude_cli", "cli_version": cli_version,
            "firma_comando": firma(argv), "conducta": conducta, "campo_identidad": None,
            "evidencia": _evidencia(EVIDENCIA_CLAUDE, "salida JSON del doble del CLI de Claude"),
            "autor": AUTOR, "fecha": FECHA}


def entrada_codex(n: int, cli_version: str, argv: list[str], *, eventos: str = "acumulado",
                  campo_identidad: Optional[str] = CAMPO_IDENTIDAD_CODEX) -> dict:
    return {"id": f"codex-{n:04d}", "familia": "codex_cli", "cli_version": cli_version,
            "firma_comando": firma(argv), "conducta": {"eventos_usage": eventos},
            "campo_identidad": campo_identidad,
            "evidencia": _evidencia(EVIDENCIA_CODEX, "eventos JSONL del doble del CLI de Codex"),
            "autor": AUTOR, "fecha": FECHA}


def instantanea(cli_claude: str, cli_codex: str, *, omitido_para: Optional[set] = None,
                eventos_codex: str = "acumulado", campo_identidad_codex: Optional[str] = CAMPO_IDENTIDAD_CODEX,
                solo_una: bool = False, ambigua_produccion: bool = False,
                ambigua_juez_codex: bool = False, etiqueta: str = "base") -> dict:
    """Instantánea de prueba `banco04-acreditacion-telemetria/v2`.

    `omitido_para`: shas de firma de Claude acreditados con `omitido_si_cero` (el resto,
    `presente_siempre`). `solo_una`: acredita una sola firma (para el rechazo por
    `firmas_previstas` incompletas). `ambigua_*`: duplica una firma con conducta distinta.
    `etiqueta` solo cambia el contenido para obtener instantáneas distintas (E2E-17)."""
    omitido_para = omitido_para or set()
    entradas: list[dict] = []
    n = 0
    for argv in comandos_claude() + [JUEZ_CLAUDE_ARGV]:
        n += 1
        f = firma(argv)
        entradas.append(entrada_claude(n, cli_claude, argv, omitido=f["sha256"] in omitido_para))
    for argv in comandos_codex() + [JUEZ_CODEX_ARGV]:
        n += 1
        entradas.append(entrada_codex(n, cli_codex, argv, eventos=eventos_codex,
                                      campo_identidad=campo_identidad_codex))
    if solo_una:
        entradas = entradas[:1]
    if ambigua_produccion:
        dup = json.loads(json.dumps(entradas[0]))
        dup["id"] = "claude-9998"
        dup["conducta"] = {c: "omitido_si_cero" for c in dup["conducta"]}
        entradas.append(dup)
    if ambigua_juez_codex:
        dup = entrada_codex(9999, cli_codex, JUEZ_CODEX_ARGV,
                            eventos="incremental" if eventos_codex == "acumulado" else "acumulado")
        entradas.append(dup)
    return {"schema": "banco04-acreditacion-telemetria/v2", "entradas": entradas,
            "nota": f"instantánea SINTÉTICA de pruebas ({etiqueta}); no acredita ningún CLI real"}


def sha_firma_claude(hint: Optional[str], esfuerzo: Optional[str]) -> str:
    from mia.agent import subscription_llm as sl  # noqa: WPS433
    return firma(sl._build_command(EXE_CLAUDE, hint, esfuerzo))["sha256"]
