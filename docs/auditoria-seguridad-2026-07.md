# Auditoría de seguridad — Mia (julio 2026)

> Auditoría realizada el 2026-07-02 sobre todo el repositorio `mia/`
> (backend FastAPI + frontend Next.js + esquema PostgreSQL/RLS).
> Este documento es el registro TÉCNICO: qué se revisó, qué se corrigió
> en esta pasada y qué queda pendiente con su prioridad.
> La explicación para no técnicos está en `docs/guia-seguridad-para-pipe.md`.

---

## 0 · Aclaración de alcance: Vercel y Supabase

**Mia hoy NO usa Vercel ni Supabase.** El stack real es:

- Frontend: Next.js 14 corriendo local (`npm run dev` / `next start`), NO desplegado en Vercel.
- Base de datos: PostgreSQL 16 + pgvector instalado localmente, NO Supabase.
- Backend: FastAPI (uvicorn) local en `127.0.0.1:8000`.

Las únicas menciones a Vercel en el repo son el README por defecto de Next.js y
la línea `.vercel` del `.gitignore` (plantilla estándar). Si en el futuro se
despliega el frontend en Vercel o se migra la DB a Supabase, aplican las
recomendaciones de la sección 4.

---

## 1 · Lo que YA estaba bien (verificado en esta auditoría)

| Área | Estado |
|---|---|
| Aislamiento multi-tenant (RLS) | ENABLE+FORCE en toda tabla por-tenant, fail-closed sin GUC, rol `mia_app` NOSUPERUSER/NOBYPASSRLS, gate `test_rls.py` 12/12 con política HALT |
| SQL | 100% consultas parametrizadas (psycopg3); no se encontró concatenación de SQL |
| Contraseñas | bcrypt cost 12; nunca en claro |
| Secretos en repo | `.env` gitignored; `JWT_SECRET` validado ≥32 chars al arrancar |
| Secretos en logs | Redactor global (CP-S2) con ~40 familias de patrones, envuelve formatters de uvicorn |
| Secretos por tenant | `secret_scope` fail-closed (CP-S3); tripwire `assert_no_stray_secret` |
| Prompt injection | Cuarentena de documentos con sellos `<<<DOC n>>>` (CP-S1) |
| Path traversal | Allowlist doble capa en carpetas locales y vault Obsidian (symlinks/junctions bloqueados) |
| Subprocesos (Agent Hub) | `shell=False`, argumentos en lista, timeout 120s, opt-in por tenant default OFF |
| Uploads | Límite 50 MB, extensiones permitidas, extracción segura |
| API binding | uvicorn escucha `127.0.0.1` por defecto (no expuesto a la red) |
| Next.js | 14.2.35 — incluye el fix del bypass de middleware CVE-2025-29927 (corregido en 14.2.25) |

---

## 2 · Brechas CORREGIDAS en esta pasada (2026-07-02)

1. **Sin freno anti fuerza-bruta en `/api/auth/login` y `/register`** →
   `api/routes/auth.py`: ventana deslizante en memoria — 5 fallos por
   (IP, email) / 15 min → 429; tope agregado de 30 fallos por IP (cualquier
   email) / 15 min → 429 (frena el barrido de emails aleatorios); 10
   registros por IP / hora → 429. Las claves vencidas se eliminan (prune
   por clave + barrido oportunista cada ~256 registros): sin fuga de memoria.
   *Límites conocidos:* (a) es por proceso; en un despliegue futuro con
   varios workers (hoy no existe — "Modo A" es solo una posibilidad, sin
   Dockerfile en el repo) migrar a contador compartido (Postgres/Redis);
   (b) detrás de un reverse proxy la IP vista es la del proxy — antes de eso hay que leer
   X-Forwarded-For desde un proxy confiable o el límite frenaría a todos los
   usuarios a la vez; (c) el registro del fallo ocurre tras el await de
   DB/bcrypt: una ráfaga concurrente puede colar unos intentos extra antes
   del primer registro (acotado por la ventana; aceptado); (d) el 429 no
   trae header `Retry-After` (cosmético).
2. **Enumeración de usuarios por timing en login** → cuando el email no
   existe ahora se verifica bcrypt contra un hash de sacrificio: la
   respuesta tarda lo mismo exista o no la cuenta. Todo bcrypt (login,
   registro y sacrificio) corre en threadpool — síncrono dentro del handler
   async bloqueaba el event loop entero (~250 ms por intento congelaba SSE
   y el resto del API). Nota: `/register` sigue confirmando con 409 si un
   email ya tiene cuenta (oráculo inevitable), desacelerado por su throttle.
3. **`/docs`, `/redoc`, `/openapi.json` abiertos sin token** → siguen
   abiertos en dev; con `MIA_ENV=production` quedan FUERA de `OPEN_PATHS`
   y además FastAPI los apaga (`docs_url=None`...).
4. **JWT sin `exp` aceptado** → con `MIA_ENV=production` el middleware exige
   el claim `exp` (`options={"require": ["exp"]}`). En dev se tolera porque
   los gates acuñan tokens sin exp. TTL ahora configurable
   (`MIA_JWT_TTL_DAYS`, default 7).
5. **CORS con `allow_methods=["*"]` y `allow_headers=["*"]` y orígenes
   hardcodeados** → orígenes desde `MIA_CORS_ORIGINS` (.env); métodos y
   headers acotados a los reales (GET/POST/PUT/DELETE/OPTIONS ·
   Authorization/Content-Type). `validate_runtime_config` rechaza `*` como
   origen en producción.
6. **Sin cabeceras de seguridad** →
   - Backend: middleware ASGI que añade `X-Content-Type-Options: nosniff`,
     `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
     `Cache-Control: no-store` (sin pisar las que el handler ya fijó — SSE intacto).
   - Frontend (`next.config.mjs`): `X-Frame-Options: DENY`,
     `CSP frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`,
     `Permissions-Policy` (cámara/micrófono/geo apagados).
7. **`/health` filtraba el error técnico de la DB** (podía traer host/usuario
   de la cadena de conexión) → ahora responde `"error": "db_unavailable"`
   genérico y el detalle va solo al log (ya redactado).
8. **La consulta jurídica del abogado quedaba en los access logs** — el SSE
   viaja como `GET /stream?message=<consulta confidencial>` y uvicorn loguea
   la URL completa → se añadió `message` a los parámetros de query redactados
   (`security/redact.py`). Secreto profesional, no solo secretos técnicos.
9. **Upload leía el archivo completo a RAM antes de validar el límite** →
   `file.read(MAX + 1)` acotado en `upload_document` e `import_playbooks`.
10. **Frontend descartaba el `detail` en login/register** → ahora muestra el
    mensaje en llano del backend (p. ej. el aviso del freno anti fuerza-bruta)
    sin filtrar códigos técnicos.

**Variables de entorno nuevas (todas opcionales, defaults = comportamiento actual):**
`MIA_ENV` (dev|production) · `MIA_CORS_ORIGINS` (coma-separados) · `MIA_JWT_TTL_DAYS`.

**Verificación (completada 2026-07-02, sesión 26):** regresión completa
`scripts/run_tests.ps1` en verde — **49/49 suites** (incluido `test_rls.py`,
gate HALT) — y `npm run build` del frontend sin errores, ambos CON estos
cambios aplicados. Revisor independiente adversarial (capa 2): veredicto
APROBAR CON CORRECCIONES; las correcciones exigidas (tope por IP + bcrypt a
threadpool, poda de memoria del throttle, filtro de errores de red en
login/register, y las imprecisiones de estos documentos) quedaron aplicadas
y re-verificadas en esta misma pasada.

---

## 3 · Brechas ABIERTAS priorizadas (no corregidas hoy)

### Antes de exponer a internet o del primer cliente (ALTA)
1. **Token de sesión en `localStorage`** (`frontend/lib/api.ts`): un XSS
   exitoso roba la sesión completa. Mitigado por las cabeceras nuevas y por
   React (escape por defecto), pero el fix real es migrar a cookie
   `HttpOnly+Secure+SameSite` — requiere rediseñar el flujo de auth y el SSE.
2. **Sin revocación de tokens**: un JWT robado vale hasta su `exp` (7 días).
   Opciones: TTL corto + refresh, o lista de revocación en DB.
3. **Clave de Pinecone en claro en `tenant_settings`** (Riesgo #37.1): cifrar
   en reposo (pgcrypto) o secret manager. Decisión de Pipe pendiente.
4. **TLS**: todo es HTTP local hoy. Cualquier despliegue expuesto necesita
   HTTPS terminado en un reverse proxy (Caddy/nginx/Cloudflare) y HSTS.
5. **Backups cifrados y probados** de PostgreSQL: hoy no hay rutina definida.

### Antes de multi-tenant real / Modo A (MEDIA — ya anotadas en bugs-and-risks.md)
*Nota: "Modo A" (Docker + WSL2) es una posibilidad futura, no una capacidad
existente — no hay Dockerfile ni docker-compose en el repo. Fuera de alcance
de v1. Los ítems siguientes son gates a resolver SI algún día se construye.*
6. Subprocesos del Agent Hub fuera del alcance de RLS (Riesgo #10) — sandbox por tenant.
7. Corpus SAT-Graph escribible por el mismo rol `mia_app` (Riesgo #13) — rol curador aparte.
8. Cron de Obsidian enumera tenants con conexión superusuario (Riesgo #15) — SECURITY DEFINER dedicada.
9. `POST /api/obsidian/install` ejecuta winget en el host — DESHABILITAR en Modo A (gate de despliegue).
10. Rate limiting compartido entre workers (ver corrección #1).
11. Función `auth_user_by_email` SECURITY DEFINER (Riesgo #29) — auditar si se amplía.
12. Canal de Telegram único por instalación (Riesgo #35) — token/chat por tenant.

### Higiene continua (BAJA)
13. Escaneo de dependencias automatizado (`pip-audit` / `npm audit` / Dependabot cuando haya remoto).
14. Contraseñas: solo se exige mínimo 8 chars; considerar chequeo contra listas de contraseñas filtradas.
15. Los datos semilla del corpus llevan `[VERIFICAR]` (Riesgo #14) — no citar sin contrastar.

---

## 4 · Si algún día se usa Vercel o Supabase (guía preventiva)

**Vercel (frontend):**
- Poner `NEXT_PUBLIC_API_URL` como variable de entorno del proyecto — recordar
  que TODO lo `NEXT_PUBLIC_*` es visible en el navegador: jamás claves ahí.
- Restringir `MIA_CORS_ORIGINS` del backend al dominio exacto `*.vercel.app`/custom.
- Activar el firewall/WAF del plan y los deployment protections (evitar previews públicos
  con datos reales).
- Las cabeceras de `next.config.mjs` ya viajan con el deploy.

**Supabase (base de datos):**
- Las políticas RLS de Mia son Postgres estándar y migran, PERO: Supabase
  añade roles propios (`anon`, `service_role`). La **`service_role` key
  ignora RLS** — tratarla como el superusuario `postgres` de hoy: solo
  migraciones, nunca en la app ni en el frontend.
- Mia fija el tenant con `set_config('app.tenant_id', …)` por transacción —
  con el pooler de Supabase (pgbouncer en modo transaction) esto funciona
  solo si TODO va dentro de la misma transacción (como hoy). Verificarlo con
  `test_rls.py` apuntando a Supabase antes de migrar.
- Activar en el panel: enforcement de SSL, network restrictions (IP allowlist),
  backups automáticos (PITR si el plan lo permite) y el Security Advisor.
- No usar la API REST autogenerada (PostgREST) ni exponer `anon` key: Mia ya
  tiene su propia API con JWT; deshabilitar lo que no se use.
