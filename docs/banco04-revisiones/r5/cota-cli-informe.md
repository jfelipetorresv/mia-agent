# Cota superior de tokens por invocación del CLI sin JSON (timeout/error)
Fecha de consulta: 2026-10-12. Versiones locales: `claude --version` = 2.1.296 (Claude Code); `codex --version` = codex-cli 0.156.0.

## 1. Claude Code
### 1.1 Reintentos de la llamada a la API
- Fuente: https://code.claude.com/docs/en/env-vars (consultada 2026-10-12).
- Cita: "Override the number of times to retry failed API requests (default: 10)." (`CLAUDE_CODE_MAX_RETRIES`).
- Misma página: tope de 15 desde v2.1.186; `CLAUDE_CODE_RETRY_WATCHDOG=1` sube el default a 300 para errores transitorios y quita el tope; con 429/529 reintenta sin límite. Cita: "Retries `429` and `529` capacity errors indefinitely".
- `API_TIMEOUT_MS`: "default: 600000, or 10 minutes" (misma URL).
- Changelog https://code.claude.com/docs/en/changelog (solo se leyeron los primeros 100000 de ~1,05 M caracteres): 2.1.296 añade CLAUDE_CODE_OVERLOADED_RETRY_MAX_DELAY_MS; 2.1.288 "Fixed mid-response API timeouts failing the turn".
- NO encontrado: texto oficial que diga que `CLAUDE_CODE_MAX_RETRIES` (default 10) aplica en modo `-p`; la página no distingue modos. Tampoco si un reintento tras corte a mitad de respuesta se factura de nuevo.

### 1.2 Otras peticiones a la API además del turno
- Fuente: https://code.claude.com/docs/en/costs, sección "Background token usage" (2026-10-12). Cita: "Background jobs that summarize previous conversations for the `claude --resume` feature". También: "typically under $0.04 per session".
- Fuente: https://code.claude.com/docs/en/env-vars. `ANTHROPIC_DEFAULT_HAIKU_MODEL`: "Model ID that the `haiku` alias resolves to, also used for background functionality." Confirma llamadas de fondo con Haiku; no las enumera.
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`: "Set to any non-empty value, such as `1`, to disable nonessential network traffic." Cubre auto-actualizaciones, telemetría, reporte de errores, /feedback, notas de versión, chequeo de PR, feature flags. La página NO dice que cubra llamadas a modelo (título, resumen).
- `DISABLE_TELEMETRY`: solo opt-out de telemetría y feature flags.
- `DISABLE_NON_ESSENTIAL_MODEL_CALLS`: NO aparece en la página oficial de env-vars (búsqueda textual en el texto descargado), ni en model-config ni en las primeras 100000 del changelog. Solo fuentes comunitarias/issues de GitHub (no oficiales) que la describen como apagar "flavor text"/llamadas no críticas, con bugs reportados. Estado: sin fuente oficial.
- Título de sesión en `-p`: sin fuente oficial.
- `--bare`/`CLAUDE_CODE_SIMPLE=1` (env-vars) desactiva hooks, auto-memoria y prefetches, pero exige ANTHROPIC_API_KEY (no OAuth): incompatible con el modo suscripción de MIA.

### 1.3 Techo de salida por petición
- https://code.claude.com/docs/en/env-vars. `CLAUDE_CODE_MAX_OUTPUT_TOKENS`: "Set the maximum number of output tokens for most requests." Modelo no resoluble: default 32000, tope 128000; el resto varía por modelo (tabla no consultada). Costos: los tokens de pensamiento se facturan como salida.

## 2. Codex CLI
- `codex exec --help` (local): sin opción de reintentos ni de máximo de tokens de salida; solo `-c key=value`.
- Reintentos (`request_max_retries`, `stream_max_retries`, por proveedor en config.toml): la página oficial https://developers.openai.com/codex/config-reference no se pudo leer (`getaddrinfo ENOTFOUND`). Solo copias espejo no oficiales con valores contradictorios. Estado: sin fuente oficial leída.
- Máximo documentado de salida del modelo por defecto (repo: `gpt-5.6-sol`, effort high): sin fuente.

## 3. Cómo lanza MIA los CLI (solo lectura)
- `backend/mia/agent/subscription_llm.py`: flags fijos `-p --output-format json --max-turns 1 --tools "" --strict-mcp-config --setting-sources project --system-prompt <persona> --no-session-persistence`, más `--model <alias>` (default MIA_CLI_MODEL="sonnet") y `--effort`. Prompt por stdin; `subprocess.run(timeout=300 s)`; cwd=MIA_HOME. Entorno: `os.environ` menos variables con API_KEY/SECRET/PASSWORD/TOKEN, DATABASE_URL, PG_*. MIA NO fija CLAUDE_CODE_MAX_RETRIES, CLAUDE_CODE_MAX_OUTPUT_TOKENS, API_TIMEOUT_MS ni DISABLE_*: heredan lo que haya en el entorno del usuario.
- `backend/mia/agent/codex_subscription_llm.py`: `codex exec --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check --sandbox read-only --output-schema ... --json --strict-config --model gpt-5.6-sol -c <overrides: sin shell/web/apps/hooks/multi-agent, analytics/feedback/update-check/memories off, model_reasoning_effort> -`. Entorno por allowlist + NO_COLOR, CI=1. Timeout 180 s; payload máx. 512000 bytes. No fija reintentos ni tope de salida.

## 4. Veredicto: NO ACREDITABLE (hoy, con fuente oficial)
Fórmula deseada: cota = (1+R) x (I + O_max) + fondo (R reintentos, I entrada, O_max techo de salida incluido pensamiento, fondo = peticiones laterales). Falta:
1. R en `-p`: default 10 (tope 15) para el CLI, sin fuente de que aplique en `-p`; con RETRY_WATCHDOG sería 300/ilimitado. Sin fuente de que un reintento fallido consuma tokens facturables (el producto da un techo conservador, no exacto).
2. Fondo: la doc solo menciona resumen de conversaciones (para `--resume`; probablemente inactivo con `--no-session-persistence`, sin fuente) y llamadas Haiku de fondo sin enumerar. `DISABLE_NON_ESSENTIAL_MODEL_CALLS` sin fuente oficial; NONESSENTIAL_TRAFFIC oficialmente no cubre llamadas a modelo.
3. O_max: depende del modelo al que resuelva el alias y del pensamiento; MIA no fija CLAUDE_CODE_MAX_OUTPUT_TOKENS.
4. Un timeout (subprocess.run mata el proceso) no deja registro de uso: lo gastado solo se acota, no se observa.
5. Codex: reintentos y tope de salida sin fuente oficial leída.

Lo que lo haría ACREDITABLE (a verificar en comando y entorno reales del banco): `CLAUDE_CODE_MAX_RETRIES=<n>` y `CLAUDE_CODE_MAX_OUTPUT_TOKENS=<m>` fijados explícitamente en el env del subproceso, ausencia de `CLAUDE_CODE_RETRY_WATCHDOG`, y fuente oficial (o medición con `--debug-file`/proxy, que implica llamar al modelo, fuera de este alcance) del conjunto de peticiones laterales en `-p --max-turns 1`.

## 5. No encontrado (declarado)
- Doc oficial sobre reintentos y peticiones laterales específicas de `-p`.
- `DISABLE_NON_ESSENTIAL_MODEL_CALLS` en doc oficial.
- Tabla oficial de tope de salida por modelo (no consultada) y del modelo por defecto de Codex.
- developers.openai.com (host no resolvió) y ~90 % del changelog.
