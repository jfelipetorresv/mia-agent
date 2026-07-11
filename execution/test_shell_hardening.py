"""
Mia · test_shell_hardening.py — gate EN FRÍO del blindaje de la cáscara de escritorio
(bloque instalador · frente C).

Verifica por string-literal / parseo de JSON (sin correr cargo, sin lanzar la
cáscara) que las 3 deudas documentadas en desktop/README.md quedaron saldadas:

  1. Instancia única: desktop/src-tauri/Cargo.toml declara
     `tauri-plugin-single-instance`, y desktop/src-tauri/src/lib.rs lo
     registra como el PRIMER `.plugin(...)` del builder — ANTES de
     `.setup(...)` (donde arranca la orquestación DB → backend → frontend).
     El callback trae la ventana al frente (unminimize + set_focus) sin
     tocar procesos.
  2. CSP explícita: desktop/src-tauri/tauri.conf.json tiene
     `app.security.csp` no-nulo.
  3. Validación de que 55432 es Postgres de verdad: lib.rs (vía db_check.rs)
     usa `pg_isready` antes de adoptar un puerto ya abierto, y el mensaje al
     abogado está en español llano.
  4. Validación de IDENTIDAD de backend y frontend (lección real 2026-07-10:
     voicebox-server.exe en el 8000 y el Next.js de "Intelligence Sura" en el
     3100 fueron adoptados por responder 200): lib.rs (vía identity.rs) exige
     el JSON propio de MIA en /health (claves db/pgvector/embed_model) y la
     huella de cabeceras del frontend (X-Frame-Options DENY + frame-ancestors
     'none' + Permissions-Policy), tanto al ADOPTAR como al ESPERAR un
     proceso lanzado por la cáscara (carrera por el puerto).

  5. El splash (desktop/src/index.html) NO CONTIENE bloques inline de
     <style> ni <script> — la CSP de (2) es `default-src 'self'` SIN
     `'unsafe-inline'`, y Tauri no hashea estilos/scripts inline. El CSS y
     el JS viven externalizados en desktop/src/splash.css y
     desktop/src/splash.js, referenciados por <link>/<script src=>, que sí
     pasan la CSP al servirse desde 'self'.

  6. F2 (primer arranque automático): la cáscara aprende a preparar MIA sola
     y a supervisar LiteLLM. Verifica los structs SetupCfg/LiteLlmCfg y sus
     campos opcionales en OrchCfg, la expansión de tokens ${exe_dir}/
     ${local_app_data} en un ÚNICO punto post-parse (abortando en llano si
     alguno no se pudo resolver, en vez de sustituir por cadena vacía), el
     gatillo TRIPLE del setup (marcador `.mia-setup-complete` + PG_VERSION +
     .env) con timeout de 15 min, que LiteLLM arranca ANTES que el backend,
     que los 3 bucles de espera (litellm/backend/frontend) evalúan
     `child_died` ANTES del health-check (evita que un squatter rápido de
     puerto pase por "vivo"), la identidad de adopción de LiteLLM (/v1/models
     + Bearer + los alias claude-haiku y mia-local), la NO adopción sin
     master key, el taskkill de litellm en el apagado (orden inverso) y la
     plantilla estática packaging/orchestration.installer.json (tokens +
     --first-run).

Nota de raíz sobre el gate mismo (hallazgo del revisor adversarial,
2026-07-10): los checks de la sección 4 (identidad) buscaban los literales
de identidad (`"db"`, `x-frame-options`, `NotMia`, etc.) en el TEXTO CRUDO
de identity.rs/lib.rs — pero esos mismos literales también viven en los
doc-comments (`///`, `//!`) que documentan el diseño. Si alguien borrara la
lógica real y dejara solo el comentario, el gate seguía en PASS. Por eso
los checks de las secciones 1, 3 y 4 corren sobre el código con los
comentarios de Rust (`//...` y `/*...*/`) eliminados — se anclan al código
real, no a la prosa que lo describe.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_shell_hardening.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SRC_TAURI = ROOT / "desktop" / "src-tauri"
CARGO_TOML = SRC_TAURI / "Cargo.toml"
LIB_RS = SRC_TAURI / "src" / "lib.rs"
DB_CHECK_RS = SRC_TAURI / "src" / "db_check.rs"
IDENTITY_RS = SRC_TAURI / "src" / "identity.rs"
TAURI_CONF = SRC_TAURI / "tauri.conf.json"
DESKTOP_SRC = ROOT / "desktop" / "src"
INDEX_HTML = DESKTOP_SRC / "index.html"
SPLASH_CSS = DESKTOP_SRC / "splash.css"
SPLASH_JS = DESKTOP_SRC / "splash.js"
ORCH_INSTALLER = ROOT / "packaging" / "orchestration.installer.json"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def strip_rust_comments(src: str) -> str:
    """Elimina comentarios Rust (`//...`, `///...`, `//!...`, `/*...*/`,
    incluyendo bloque anidados) del código fuente, respetando literales de
    cadena (para no cortar strings que contengan "//", p.ej. "mia://progress").

    Así los checks que buscan literales de identidad/lógica se anclan al
    CÓDIGO REAL — un doc-comment que mencione los mismos literales ya no
    puede sostener el gate si la lógica de verdad fue borrada.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    in_string = False
    while i < n:
        c = src[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j == -1:
                break
            out.append("\n")
            i = j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            depth = 1
            i += 2
            while i < n and depth > 0:
                if src[i : i + 2] == "/*":
                    depth += 1
                    i += 2
                elif src[i : i + 2] == "*/":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def main() -> int:
    print("== Blindaje de la cáscara de escritorio: gate en frío (bloque instalador · frente C) ==")

    # --- 0 · archivos existen -------------------------------------------
    check("desktop/src-tauri/Cargo.toml existe", CARGO_TOML.is_file())
    check("desktop/src-tauri/src/lib.rs existe", LIB_RS.is_file())
    check("desktop/src-tauri/tauri.conf.json existe", TAURI_CONF.is_file())
    if not (CARGO_TOML.is_file() and LIB_RS.is_file() and TAURI_CONF.is_file()):
        print("\nRESULT: archivos base faltantes — abortando el resto de checks.")
        return 1

    cargo_toml = CARGO_TOML.read_text(encoding="utf-8")
    lib_rs = LIB_RS.read_text(encoding="utf-8")
    # Código real, sin doc-comments: los checks de lógica se anclan aquí
    # (ver strip_rust_comments — no basta con que un comentario mencione el
    # literal, la lógica tiene que seguir viva en el código).
    lib_rs_code = strip_rust_comments(lib_rs)

    # --- 1 · instancia única ---------------------------------------------
    check(
        "Cargo.toml declara tauri-plugin-single-instance",
        "tauri-plugin-single-instance" in cargo_toml,
    )

    plugin_idx = lib_rs_code.find("tauri_plugin_single_instance::init")
    setup_idx = lib_rs_code.find(".setup(|app|")
    check("lib.rs registra tauri_plugin_single_instance::init(...)", plugin_idx != -1)
    check("lib.rs tiene un bloque .setup(|app| ...)", setup_idx != -1)
    check(
        "lib.rs registra el plugin de instancia única ANTES de .setup() (orden textual del builder)",
        plugin_idx != -1 and setup_idx != -1 and plugin_idx < setup_idx,
    )
    check(
        "el callback de instancia única trae la ventana existente al frente (unminimize)",
        "unminimize" in lib_rs_code,
    )
    check(
        "el callback de instancia única trae la ventana existente al frente (set_focus)",
        "set_focus" in lib_rs_code,
    )

    # --- 2 · CSP explícita -------------------------------------------------
    tauri_conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    csp = tauri_conf.get("app", {}).get("security", {}).get("csp", "__missing__")
    check(
        "tauri.conf.json declara app.security.csp (existe la clave)",
        csp != "__missing__",
    )
    check(
        "tauri.conf.json: app.security.csp NO es null (CSP explícita, ya no deuda)",
        csp is not None and csp != "__missing__",
    )
    if isinstance(csp, dict):
        check(
            "CSP restringe default-src (no permite todo)",
            "default-src" in csp and csp["default-src"] not in ("*", None),
        )
    elif isinstance(csp, str):
        check("CSP (string) restringe default-src", "default-src" in csp)
    else:
        check("CSP tiene una forma reconocible (objeto o string)", False)

    csp_text = json.dumps(csp) if not isinstance(csp, str) else csp
    check(
        "CSP no incluye 'unsafe-inline' (el splash se sirve externalizado, no relajado)",
        "unsafe-inline" not in csp_text,
    )

    # --- 3 · validación pg_isready ------------------------------------------
    check("desktop/src-tauri/src/db_check.rs existe (módulo de validación de DB)", DB_CHECK_RS.is_file())
    db_check_rs = DB_CHECK_RS.read_text(encoding="utf-8") if DB_CHECK_RS.is_file() else ""
    db_check_rs_code = strip_rust_comments(db_check_rs)

    check(
        "lib.rs declara el módulo db_check (mod db_check;)",
        "mod db_check" in lib_rs_code,
    )
    check(
        "lib.rs invoca la validación de pg_isready antes de adoptar el puerto de la DB",
        "wait_pg_isready" in lib_rs_code,
    )
    check(
        "db_check.rs efectivamente corre pg_isready.exe",
        "pg_isready.exe" in db_check_rs_code,
    )
    check(
        "db_check.rs cubre el caso 'rejecting connections' con reintento (no falla al primer intento)",
        "reintent" in db_check_rs_code.lower(),
    )
    check(
        "el mensaje al abogado está en español llano y no adopta si pg_isready nunca confirma (puerto ocupado)",
        "otro programa está ocupando el lugar de la base de datos de Mia" in lib_rs_code
        and "reinicia el equipo" in lib_rs_code,
    )
    check(
        "db_check.rs distingue 'puerto ocupado' de 'herramienta no ejecutable' (PgReadyOutcome)",
        "PgReadyOutcome" in db_check_rs_code
        and "PortBusy" in db_check_rs_code
        and "ToolMissing" in db_check_rs_code,
    )
    check(
        "mensaje en llano cuando pg_isready.exe nunca pudo ejecutarse (instalación rota, no adopta el mensaje de 'reinicia el equipo')",
        "no encuentro las herramientas de la base de datos de Mia" in lib_rs_code,
    )
    check(
        "db_check.rs corre el Command::status() bloqueante dentro de spawn_blocking (no congela el runtime async)",
        "spawn_blocking" in db_check_rs_code,
    )

    # --- 4 · identidad de backend y frontend (voicebox/Sura, 2026-07-10) ----
    check("desktop/src-tauri/src/identity.rs existe (módulo de identidad)", IDENTITY_RS.is_file())
    identity_rs = IDENTITY_RS.read_text(encoding="utf-8") if IDENTITY_RS.is_file() else ""
    # Anclado al CÓDIGO real (sin doc-comments): un comentario que mencione
    # los mismos literales de identidad ya no puede sostener el gate si la
    # lógica de verdad fue borrada (hallazgo M1 del revisor adversarial).
    identity_rs_code = strip_rust_comments(identity_rs)

    check(
        "lib.rs declara el módulo identity (mod identity;)",
        "mod identity" in lib_rs_code,
    )
    check(
        "identity.rs valida el JSON de /health con las claves propias de MIA (db, pgvector, embed_model)",
        '"db"' in identity_rs_code and '"pgvector"' in identity_rs_code and '"embed_model"' in identity_rs_code,
    )
    check(
        "identity.rs valida la huella de cabeceras del frontend (x-frame-options DENY)",
        "x-frame-options" in identity_rs_code.lower() and "deny" in identity_rs_code.lower(),
    )
    check(
        "identity.rs valida la huella de cabeceras del frontend (frame-ancestors 'none')",
        "frame-ancestors 'none'" in identity_rs_code,
    )
    check(
        "identity.rs valida la huella de cabeceras del frontend (permissions-policy camera=())",
        "permissions-policy" in identity_rs_code.lower() and "camera=()" in identity_rs_code,
    )
    check(
        "identity.rs distingue 'responde pero NO es MIA' de 'no responde' (NotMia vs NoResponse)",
        "NotMia" in identity_rs_code and "NoResponse" in identity_rs_code,
    )
    check(
        "lib.rs exige identidad del backend en la ADOPCIÓN y en la ESPERA post-lanzamiento (2 usos)",
        lib_rs_code.count("backend_identity") >= 2,
    )
    check(
        "lib.rs exige identidad del frontend en la ADOPCIÓN y en la ESPERA post-lanzamiento (2 usos)",
        lib_rs_code.count("frontend_identity") >= 2,
    )
    check(
        "lib.rs ya NO adopta backend/frontend con un simple 200 (http_ok eliminado)",
        "http_ok" not in lib_rs_code,
    )
    check(
        "mensaje en llano cuando el 8000 responde pero no es MIA",
        "otro programa está ocupando el lugar de Mia — ciérralo o reinicia el equipo" in lib_rs_code,
    )
    check(
        "mensaje en llano cuando el 3100 responde pero no es MIA (nunca navegar a una app ajena)",
        "otro programa está ocupando el lugar de la pantalla de Mia — ciérralo o reinicia el equipo" in lib_rs_code,
    )

    # --- 5 · splash sin bloques inline (B1: CSP default-src 'self' de raíz) --
    check("desktop/src/index.html existe", INDEX_HTML.is_file())
    check("desktop/src/splash.css existe (CSS externalizado del splash)", SPLASH_CSS.is_file())
    check("desktop/src/splash.js existe (JS externalizado del splash)", SPLASH_JS.is_file())

    index_html = INDEX_HTML.read_text(encoding="utf-8") if INDEX_HTML.is_file() else ""
    check(
        "index.html NO contiene ningún bloque <style> inline",
        re.search(r"<style[\s>]", index_html, re.IGNORECASE) is None,
    )
    check(
        "index.html NO contiene ningún bloque <script> inline (solo <script src=...>)",
        re.search(r"<script(?![^>]*\bsrc=)[^>]*>", index_html, re.IGNORECASE) is None,
    )
    check(
        "index.html NO contiene atributos style= inline",
        re.search(r"\sstyle\s*=", index_html, re.IGNORECASE) is None,
    )
    check(
        "index.html referencia splash.css vía <link rel=stylesheet>",
        re.search(r'<link[^>]+href=["\']splash\.css["\']', index_html, re.IGNORECASE) is not None,
    )
    check(
        "index.html referencia splash.js vía <script src=...>",
        re.search(r'<script[^>]+src=["\']splash\.js["\']', index_html, re.IGNORECASE) is not None,
    )

    # --- 6 · F2: setup de primer arranque + LiteLLM + tokens + plantilla -----
    # La cáscara aprende a preparar MIA sola (bootstrap Python) y a supervisar
    # LiteLLM como 4º servicio. Todos los checks de lógica se anclan al CÓDIGO
    # real (sin doc-comments) igual que las secciones 1/3/4.
    identity_rs_code_f2 = identity_rs_code  # ya calculado en la sección 4

    # 6a · structs y campos opcionales en OrchCfg
    check(
        "lib.rs define struct SetupCfg (paso de primer arranque)",
        "struct SetupCfg" in lib_rs_code,
    )
    check(
        "lib.rs define struct LiteLlmCfg (motor de modelos)",
        "struct LiteLlmCfg" in lib_rs_code,
    )
    check(
        "OrchCfg tiene el campo opcional setup: Option<SetupCfg>",
        re.search(r"setup\s*:\s*Option\s*<\s*SetupCfg\s*>", lib_rs_code) is not None,
    )
    check(
        "OrchCfg tiene el campo opcional litellm: Option<LiteLlmCfg>",
        re.search(r"litellm\s*:\s*Option\s*<\s*LiteLlmCfg\s*>", lib_rs_code) is not None,
    )

    # 6b · expansión de tokens en un ÚNICO punto post-parse
    check(
        "lib.rs define fn expand_tokens (expansión de tokens del config)",
        "fn expand_tokens" in lib_rs_code,
    )
    check(
        "expand_tokens expande ${exe_dir} y ${local_app_data}",
        "${exe_dir}" in lib_rs_code and "${local_app_data}" in lib_rs_code,
    )
    check(
        "la expansión de tokens ocurre en un ÚNICO punto (una sola llamada .expand_tokens(...))",
        lib_rs_code.count(".expand_tokens(") == 1,
    )
    check(
        "si ${exe_dir} o ${local_app_data} no se pudieron resolver, lib.rs ABORTA en llano "
        "(en vez de sustituir por cadena vacía y fallar después con rutas sin sentido)",
        "exe_dir.is_empty()" in lib_rs_code
        and "local_app_data.is_empty()" in lib_rs_code
        and "MIA no pudo determinar sus carpetas de instalación" in lib_rs_code,
    )
    check(
        "el aborto por tokens vacíos ocurre ANTES de .expand_tokens(...) (guard, no sustitución silenciosa)",
        lib_rs_code.find("exe_dir.is_empty()") != -1
        and lib_rs_code.find(".expand_tokens(") != -1
        and lib_rs_code.find("exe_dir.is_empty()") < lib_rs_code.find(".expand_tokens("),
    )

    # 6c · gatillo TRIPLE del setup: marcador .mia-setup-complete, PG_VERSION o .env faltantes
    check(
        "el gatillo del setup mira el marcador <app_dir>/.mia-setup-complete "
        "(escrito por el bootstrap SOLO al terminar TODO con éxito)",
        ".mia-setup-complete" in lib_rs_code,
    )
    check(
        "el gatillo del setup mira <data_dir>/PG_VERSION",
        "PG_VERSION" in lib_rs_code,
    )
    check(
        "el gatillo del setup mira <app_dir>/.env",
        'join(".env")' in lib_rs_code,
    )
    check(
        "el gatillo del setup dispara si falta CUALQUIERA de marcador/PG_VERSION/.env "
        "(triple OR, no solo PG_VERSION/.env) — un setup interrumpido a medias se re-ejecuta",
        re.search(
            r"marker_missing\s*\|\|\s*pg_version_missing\s*\|\|\s*env_missing",
            lib_rs_code,
        )
        is not None,
    )
    check(
        "el setup tiene timeout de 15 minutos (15 * 60 s)",
        "15 * 60" in lib_rs_code,
    )
    check(
        "en fallo del setup se muestra la última línea no vacía de su stdout",
        "last_nonempty_line" in lib_rs_code,
    )

    # 6d · orden: LiteLLM arranca ANTES que el backend
    litellm_stage = lib_rs_code.find('emit(&app, "litellm"')
    backend_stage = lib_rs_code.find('emit(&app, "backend"')
    check(
        "el stage 'setup' se emite a la pantalla de arranque",
        '"setup"' in lib_rs_code,
    )
    check(
        "el stage 'litellm' se emite a la pantalla de arranque",
        litellm_stage != -1,
    )
    check(
        "LiteLLM se enciende ANTES que el backend (litellm entre DB y backend)",
        litellm_stage != -1 and backend_stage != -1 and litellm_stage < backend_stage,
    )

    # 6e · identidad de adopción de LiteLLM (/v1/models + Bearer + 2 alias)
    check(
        "identity.rs define litellm_identity (adopción con identidad) y litellm_health (liveliness)",
        "litellm_identity" in identity_rs_code_f2 and "litellm_health" in identity_rs_code_f2,
    )
    check(
        "la identidad de LiteLLM consulta /v1/models con Authorization Bearer",
        "/v1/models" in identity_rs_code_f2
        and "Authorization" in identity_rs_code_f2
        and "Bearer" in identity_rs_code_f2,
    )
    check(
        "la identidad de LiteLLM exige los dos alias propios (claude-haiku y mia-local)",
        "claude-haiku" in identity_rs_code_f2 and "mia-local" in identity_rs_code_f2,
    )
    check(
        "identity.rs distingue NotMia vs NoResponse también para LiteLLM (patrón tri-estado)",
        "NotMia" in identity_rs_code_f2 and "NoResponse" in identity_rs_code_f2,
    )

    # 6f · NO adoptar sin la master key; la key se lee del .env
    check(
        "lib.rs lee LITELLM_MASTER_KEY del .env (parser read_dotenv_value)",
        "LITELLM_MASTER_KEY" in lib_rs_code and "read_dotenv_value" in lib_rs_code,
    )
    check(
        "lib.rs llama la identidad de LiteLLM al adoptar un puerto ocupado",
        "litellm_identity" in lib_rs_code,
    )
    check(
        "mensaje en llano cuando el puerto de LiteLLM está ocupado por otra app (no se adopta a ciegas)",
        "está ocupado por otra aplicación" in lib_rs_code,
    )

    # 6i · child_died evaluado ANTES del health-check en los 3 bucles de espera
    # (hallazgo del revisor adversarial: un hijo muerto + un squatter rápido del
    # puerto podía leerse como "vivo" si el health-check corría primero).
    check(
        "lib.rs llama child_died(shared, ...) exactamente 3 veces (litellm/backend/frontend, un bucle cada uno)",
        lib_rs_code.count("child_died(shared,") == 3,
    )
    litellm_child_died_idx = lib_rs_code.find('child_died(shared, "litellm")')
    litellm_health_wait_idx = lib_rs_code.find("litellm_health(&client")
    check(
        "bucle de espera de LiteLLM: child_died se evalúa ANTES del health-check (liveliness)",
        litellm_child_died_idx != -1
        and litellm_health_wait_idx != -1
        and litellm_child_died_idx < litellm_health_wait_idx,
    )
    backend_child_died_idx = lib_rs_code.find('child_died(shared, "backend")')
    backend_identity_wait_idx = lib_rs_code.rfind("backend_identity(&client")
    check(
        "bucle de espera del backend: child_died se evalúa ANTES de re-chequear identidad "
        "(mismo orden que LiteLLM — misma clase de bug, corregida igual)",
        backend_child_died_idx != -1
        and backend_identity_wait_idx != -1
        and backend_child_died_idx < backend_identity_wait_idx,
    )
    frontend_child_died_idx = lib_rs_code.find('child_died(shared, "frontend")')
    frontend_identity_wait_idx = lib_rs_code.rfind("frontend_identity(&client")
    check(
        "bucle de espera del frontend: child_died se evalúa ANTES de re-chequear identidad "
        "(mismo orden que LiteLLM — misma clase de bug, corregida igual)",
        frontend_child_died_idx != -1
        and frontend_identity_wait_idx != -1
        and frontend_child_died_idx < frontend_identity_wait_idx,
    )

    # 6g · shutdown incluye litellm, en orden inverso
    check(
        "el apagado hace taskkill de litellm (litellm_pid en la lista de cierre)",
        "litellm_pid" in lib_rs_code
        and re.search(r'\("litellm"\s*,\s*o\.litellm_pid\)', lib_rs_code) is not None,
    )

    # 6h · plantilla del instalador estática con tokens + --first-run
    check(
        "packaging/orchestration.installer.json existe (plantilla estática del instalador)",
        ORCH_INSTALLER.is_file(),
    )
    installer_raw = ORCH_INSTALLER.read_text(encoding="utf-8") if ORCH_INSTALLER.is_file() else ""
    check(
        "la plantilla del instalador usa los tokens ${exe_dir} y ${local_app_data}",
        "${exe_dir}" in installer_raw and "${local_app_data}" in installer_raw,
    )
    check(
        "la plantilla del instalador arranca el setup con --first-run",
        "--first-run" in installer_raw,
    )
    if installer_raw:
        try:
            installer_json = json.loads(installer_raw)
        except Exception:
            installer_json = {}
        check(
            "la plantilla del instalador es JSON válido con bloques setup, litellm, db, backend y frontend",
            all(k in installer_json for k in ("app_dir", "setup", "litellm", "db", "backend", "frontend")),
        )
        litellm_blk = installer_json.get("litellm", {}) if isinstance(installer_json, dict) else {}
        check(
            "el bloque litellm de la plantilla usa health de liveliness y puerto 4000",
            isinstance(litellm_blk, dict)
            and "liveliness" in str(litellm_blk.get("health_url", ""))
            and litellm_blk.get("port") == 4000,
        )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
