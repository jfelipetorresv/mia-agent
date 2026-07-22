# Plan F3 — Bienvenida cinematográfica + activación de llaves (bloque instalador, sesión 44)

> Diseño aprobado por Fable (orquestador) sobre 4 recon de la sesión 44. CONTRATO entre los
> ejecutores. Objetivo F3: rediseñar TODA la primera vez del abogado (login + registro +
> activación de llaves mínimas + conocer el despacho) como UNA experiencia cohesiva,
> cinematográfica premium + guiada/gratificante. Dirección de Pipe en [[mia-f3-direccion-diseno]].

## Hechos del recon (NO re-descubrir)

### Auth / primer arranque
- NO hay seed de usuario/tenant. El abogado se registra: `POST /api/auth/register` {email,
  password(min8), firm_name} → {token, tenant_id} (`api/routes/auth.py:158-190`). Login
  `POST /api/auth/login`, `GET /api/auth/me`.
- `AuthGate` (`app/_components/AuthGate.tsx`): rutas públicas = `/login`, `/register`; sin token
  → `/login`. `OnboardingGate` (`app/_components/OnboardingGate.tsx`): si `/api/onboarding/status`
  `completed==false` → `/onboarding` (fail-open si backend no responde).
- Onboarding = 8 preguntas hoy (p1,p2,p3,p4,p6,p7,p18,p19) en `onboarding/soul_interview.py:52-87`
  (el docstring "13 preguntas" de `ux.py:1423` está DESACTUALIZADO). Genera SOUL.md determinista
  SIN LLM. Endpoints: `GET /api/onboarding/questions|status`, `POST /api/onboarding/draft|complete`.
- Wizard "primeros pasos" CP-C4 (`api/routes/setup.py`, `GET /api/setup/status`) = 6 pasos de
  DETECCIÓN (perfil, motor, carpetas, guias, telegram, voz); el paso "motor" solo hace
  `shutil.which("claude")/("ollama")`, NO captura llaves. Vive en `/configurar`.
- En DB virgen el frontend cae directo en `/login` (AuthGate ve sin token, ni llama backend).

### Llaves y motor (CRÍTICO)
- `VOYAGE_API_KEY` vacía → `embeddings.py:11-14` lanza `RuntimeError` DURO; rompe ingesta y
  búsqueda RAG en las 3 políticas. Embeddings van IN-PROCESS por el backend
  (`litellm.embedding(api_key=config.VOYAGE_API_KEY)`), NO por el proxy HTTP mia-litellm.exe.
  → Actualizar `config.VOYAGE_API_KEY` en caliente HACE que la búsqueda funcione sin reiniciar
  nada. **Esta es la única llave crítica del flujo feliz.**
- `ANTHROPIC_API_KEY` → alias `claude-haiku`/`claude-sonnet` en el proxy mia-litellm.exe. En
  política `suscripcion` (default) es solo respaldo tras el CLI `claude`; en `nube` es el motor.
  El proxy lee el .env UNA vez al arrancar (`entry_litellm.py`, dotenv neutralizado) → una llave
  nueva NO surte efecto sin reiniciar el proxy. Sin reinicio de proceso hijo disponible
  (ver cáscara) → **se difiere al próximo arranque natural de MIA. Aceptable porque el default
  no la necesita.**
- `OPENROUTER_API_KEY` opcional; su ausencia degrada con gracia.
- Política default = `suscripcion` YA de fábrica (`llm.py:157-160`, sin fila en tenant_settings).
  Etiquetas UI: "Mi suscripción (recomendado)" / "Nube" / "Todo en mi equipo"
  (`api/routes/settings.py:28-32`). Selector ya en `ConexionesSection.tsx` (solo elige política,
  no pide llave). `PUT /settings/model-policy` persiste con merge jsonb + invalida caché.
- `config.py:31` hace `load_dotenv()` POR-IMPORT (variables de módulo). Escribir el .env en
  caliente NO lo ve el backend salvo que también actualicemos `config.*` en memoria.
- `.env` semilla de first_run deja `VOYAGE_API_KEY=` vacío y NO escribe `ANTHROPIC_API_KEY`.
  `_atomic_write_text` (`setup/first_run.py:52-62`) es el patrón de escritura atómica reutilizable.
- NO existe endpoint que escriba llaves al .env, NI validación (ping) de llaves. `_clear_message`
  existe pero `stream.py:311-313` colapsa todo a un genérico → el frontend nunca ve el motivo real.

### Cáscara (desktop/src-tauri)
- Stages splash: `setup|db|litellm|backend|frontend|ready|error`. Al `ready` navega la webview a
  `http://localhost:3100`. CERO `#[tauri::command]`, CERO `window.__TAURI__` en el frontend, sin
  IPC. NO hay reinicio de servicio individual (solo shutdown total en ExitRequested).
- **NO abrir IPC Tauri en F3** (dispara Riesgo #59 punto 2 + re-verificación). F3 vive
  enteramente en frontend+backend web. La única "recarga" que necesitamos (Voyage) es en caliente
  vía backend; Anthropic se difiere al próximo arranque.
- El frontend NO sabe si corre en modo instalado. Lo sabrá vía backend (endpoint welcome-status).

### Materia prima visual (recon visual)
- `framer-motion@12.42` INSTALADO pero SIN USAR en ningún archivo → base de todo el motion.
- Radix (shadcn manual en `components/ui/`), `lucide-react`, `tailwindcss-animate`, cva/clsx/
  tailwind-merge (`lib/utils.ts cn()`), cmdk. NO hay: lottie, confetti, react-markdown.
- Tokens de marca listos en `globals.css`: `.bg-aurora`, `.text-gradient-brand`,
  `.bg-gradient-cta` (linear 135deg #98e4bf→#00f5a2), `.glow-teal`, `.card-depth`. Tema oscuro
  `#060606` tinte teal, `--primary` teal splash. Keyframes: `fade-in`, `slide-up`, `message-in`,
  `blink` (cursor typewriter Mia), `pulse-soft` (halo respirando). Fuentes: Archivo (display),
  Hind (sans), Newsreader (serif) vía next/font, variables CSS listas.
- Marca MIA = texto plano `M<span className="... text-[#2EA9A9]">I</span>A` (`Sidebar.tsx:16-24`),
  duplicado en web y `desktop/src/splash.css` (72px, glow teal). NO hay componente `<BrandMark/>`.
- Onboarding actual: máquina de estados, una pregunta por pantalla, animaciones SOLO con Tailwind
  keyframes + `animationDelay` inline manual (sin framer-motion). Parser Markdown artesanal frágil
  (`onboarding/page.tsx:524-601`). Login/register = los más simples, sin aurora ni marca.
- Componentes base reusables: `Button` (variantes incl. `cta` gradiente), `Card` (`.card-depth`),
  `Input`, `Label`, `Skeleton`, `CountrySelector`, `ToolsChecklist`/`TagInput`.

## Motion language (framer-motion — el "wow" cohesivo)
1. **WelcomeShell** (layout compartido de toda la primera vez): fondo `.bg-aurora` con dos blobs
   radiales teal/CTA en deriva lenta (framer-motion `animate` loop, respetando
   `prefers-reduced-motion` → estático). Marca MIA arriba que "respira" (reusar `pulse-soft`).
2. **Transición entre pasos**: `AnimatePresence mode="wait"` + `motion.div` con variantes
   direccionales (avanzar: entra desde x:+24 opacidad 0 → 0; retroceder: desde x:-24). Duración
   ~0.35s, ease suave (`[0.22,1,0.36,1]`). Reemplaza el remount `animate-slide-up` actual.
3. **Stagger real** de los elementos dentro de cada paso (`staggerChildren`), reemplazando los
   `animationDelay` inline manuales.
4. **Progreso global tipo constelación**: una barra/hilera de nodos que abarca TODO el viaje
   (Crear despacho → Activar → Conocer despacho → Listo), no un % por pantalla. Nodo activo con
   `.glow-teal`; nodos cumplidos con check que hace un micro-pop al completarse.
5. **Micro-celebraciones**: al validar una llave OK (✓ que aparece con spring), al pasar de
   sección (destello teal). Pantalla final: celebración plena (partículas/confetti hechas con
   framer-motion + CSS, SIN añadir dependencia; si el ejecutor juzga que canvas-confetti mejora
   mucho el remate, puede añadirlo — dep mínima, sin backend).
6. **Presencia de Mia**: en pasos clave, la marca o un halo de Mia "habla" (usar `blink`/typewriter
   ya existente para textos de bienvenida). Coherente con el motion-language del chat.
7. Todo respeta `prefers-reduced-motion` (variante estática). Sin jank: `transform`/`opacity` only.

## Arquitectura del viaje unificado
Orden (modo instalado): cáscara `ready` → webview 3100 → frontend decide con **welcome-status**:
1. **Bienvenida + Crear despacho** (reemplaza `/register`): pantalla cinematográfica "Soy Mia",
   luego nombre del despacho + email + contraseña. Al enviar → register → token.
2. **Activar MIA** (NUEVO): (a) motor — confirmar "Mi suscripción (recomendado)" con explicación
   en llano, o elegir Nube/Local; (b) llave de búsqueda documental (Voyage) con validación en
   vivo (✓/✗ en llano) — con "Lo haré después"; (c) opcional llave de respaldo (Anthropic) si
   eligió Nube o quiere respaldo. Guardar → escribe .env + hot-reload Voyage.
3. **Conocer tu despacho** (rediseño `/onboarding`): las 8 preguntas, una por pantalla, con el
   nuevo motion-language. Mantener tipos de campo (texto, TagInput, ToolsChecklist,
   CountrySelector) y el autosave por `qid`. Genera SOUL determinista igual.
4. **Listo** (celebración) → entrar a `/`.
- **Login** (regresos) rediseñado con el mismo WelcomeShell (versión compacta).
- `AuthGate`/`OnboardingGate` se ajustan para permitir las nuevas rutas del viaje y respetar el
  paso de activación (no forzar onboarding antes de activar). Rutas públicas del viaje.
- En **modo dev** (llaves ya en el .env del repo, no instalado): el paso "Activar/llaves" se
  auto-omite o muestra "ya configurado" — el wizard NO debe estorbar el flujo dev.

## Contratos backend nuevos (Ejecutor Backend)
- `GET /api/welcome/status` → `{ instalado: bool, hay_usuario: bool, faltan_llaves: {busqueda:
  bool, respaldo: bool}, onboarding_completo: bool, motor_detectado: {claude: bool, ollama: bool},
  politica: str }`. "instalado" = MIA_APP_DIR presente / IS_PRODUCTION / sys.frozen. Público
  (OPEN_PATH) SOLO para los campos no sensibles necesarios antes del login; si expone algo
  sensible, exigir auth. El ejecutor decide el mínimo seguro y lo documenta.
- `POST /api/welcome/keys` (AUTENTICADO) body `{ busqueda?: str, respaldo?: str, openrouter?: str }`
  → escribe/actualiza SOLO esas claves en el `.env` del app_dir con `_atomic_write_text`
  (preservando el resto byte a byte, nunca tocando secretos existentes de instalación), y hace
  **hot-reload** de `config.VOYAGE_API_KEY`/`OPENROUTER_API_KEY` + `os.environ` en el proceso
  backend. `respaldo`(Anthropic) queda escrita pero se informa "se activa al reiniciar MIA".
  Devuelve estado en llano. SEGURIDAD: llaves globales de instalación; solo tiene sentido en modo
  instalado y mono-despacho — el ejecutor exige auth, valida modo instalado, y declara el modelo
  de confianza (la capa 2 de seguridad lo revisará).
- `POST /api/welcome/keys/test` (AUTENTICADO) body `{ tipo: "busqueda"|"respaldo", clave: str }`
  → ping mínimo real (Voyage: un embedding corto; Anthropic: vía el proxy o SDK) → `{ ok: bool,
  motivo?: str }` en llano, SIN persistir. Timeout corto, fail-soft.
- Reusar `PUT /settings/model-policy` existente para fijar la política elegida.
- §G estricto en todo texto: nada de "API key", "tenant", "embeddings", "Voyage", "endpoint".
  Nombrar en llano: "clave de búsqueda en tus documentos", "motor de Mia", etc.

## Gates (capa 1)
- Backend → `execution/test_welcome_keys.py` (patrón script, NO pytest; TestClient + Postgres real
  + LLM/Voyage fake por monkeypatch): welcome-status en DB virgen y con usuario; escritura atómica
  del .env preservando el resto y sin pisar secretos; hot-reload efectivo de config.VOYAGE_API_KEY;
  test-key OK/error en llano; auth requerido (401 sin token); modo instalado vs dev; §G
  (auditar _FORBIDDEN_RE como test_setup_wizard). Idempotencia. Cleanup total.
- Frontend → `npm run build` verde. El motion/visual es capa 3 de Pipe (no automatizable).
- Regresión: NO romper `test_rls` (HALT), `check_env_pins` (HALT), `test_setup_wizard`,
  `test_onboarding_draft`, gate HITL. La integración de gates a `scripts/run_tests.ps1` la hace
  el ORQUESTADOR al final.

## División de archivos (disjuntos)
- **E-Backend** (sonnet): `backend/mia/api/routes/welcome.py` (nuevo) + registro en el router raíz,
  `backend/mia/setup/*` (helper de escritura/hot-reload si aplica), `execution/test_welcome_keys.py`.
  Ajuste quirúrgico de `api/middleware.py` OPEN_PATHS solo si welcome-status lo exige.
- **E-Infra-visual** (opus): `frontend/app/(welcome)/_components/*` NUEVOS — `WelcomeShell.tsx`,
  `BrandMark.tsx` (compartible), `WelcomeProgress.tsx` (constelación), `MotionField.tsx`,
  `Celebration.tsx`, hooks de motion + variantes compartidas. Tokens/keyframes extra en
  `globals.css`/`tailwind.config.ts` SOLO si hacen falta (aditivo, sin romper lo existente).
  Refactor mínimo de `Sidebar.tsx` para consumir `<BrandMark/>` (sin cambiar su look).
- **E-Auth** (opus): `frontend/app/login/page.tsx`, `frontend/app/register/page.tsx` (→ Crear
  despacho) consumiendo WelcomeShell/BrandMark. Ajuste de `AuthGate.tsx`/`OnboardingGate.tsx` para
  las rutas del viaje.
- **E-Activacion** (opus): `frontend/app/(welcome)/activar/page.tsx` NUEVO (motor + llaves +
  validación en vivo) consumiendo WelcomeShell + endpoints backend.
- **E-Onboarding** (opus): `frontend/app/onboarding/page.tsx` (rediseño con framer-motion +
  WelcomeShell), preservando tipos de campo, autosave por qid, generación de SOUL.
- Oleada 1 = E-Backend + E-Infra-visual (no se solapan). Oleada 2 = E-Auth + E-Activacion +
  E-Onboarding (comparten WelcomeShell/BrandMark SOLO lectura; editan archivos distintos).

## Reglas para TODOS los ejecutores
- Windows + PowerShell 5.1. Tests = scripts (`python execution/test_X.py`), NO pytest.
- §G sin jerga técnica al abogado en TODO texto visible. Puerto frontend 3100.
- framer-motion: `"use client"`, imports desde `"framer-motion"`. Respetar
  `prefers-reduced-motion`. Solo `transform`/`opacity` (sin layout thrash).
- No tocar: flujo HITL, test_rls, check_env_pins, litellm_config.yaml (dev), lógica de negocio,
  la cáscara Tauri (NADA de IPC nuevo). NO regenerar secretos existentes del .env.
- Cada ejecutor corre su gate / `npm run build` en verde antes de reportar. Reporta hallazgos y
  suposiciones declaradas.
