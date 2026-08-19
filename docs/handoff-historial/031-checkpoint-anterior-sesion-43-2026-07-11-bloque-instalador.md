## Checkpoint anterior: Sesión 43 (2026-07-11) — BLOQUE INSTALADOR: Fase 2 (primer arranque automático) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Se completó la **Fase 2 del instalador** (meta que Pipe fijó para la sesión): en una máquina
limpia, MIA ahora **se prepara sola la primera vez que se abre**:

- **Primer arranque automático:** la cáscara detecta que MIA no está preparada y dispara un
  paso de preparación que crea la carpeta de datos del abogado, genera las llaves de seguridad
  solas (una sola vez, jamás se pisan), crea la base de datos desde cero —cerrada al mundo:
  solo escucha dentro del computador— aplica las 28 migraciones y deja la memoria conversacional
  lista. Si el abogado cierra la ventana a mitad de la preparación, la próxima apertura **se
  auto-repara** (esto salió de la revisión adversarial: antes quedaba rota para siempre).
- **El motor de modelos (LiteLLM) ya es un ejecutable propio** (108 MB, sin Python): la cáscara
  lo enciende y lo vigila como 4º servicio, con la misma regla de identidad de siempre (nada
  se adopta por solo responder — exige la llave y los nombres de modelos de MIA).
- **Hallazgo de seguridad corregido y verificado en vivo:** el motor de modelos quedaba
  escuchando hacia toda la red del despacho (cualquier equipo de la oficina podía usar las
  llaves de la firma); ahora solo escucha dentro del computador — se probó con un intento real
  desde la red, rechazado.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 84/84 suites ALL PASS** (línea base sube de 82 a 84 con
  `test_first_run` 68/68 —initdb y login reales— y `test_litellm_packaging` 60/60;
  `test_shell_hardening` sube de 69 a 77 checks). `test_rls` 12/12 y `check_env_pins` 9/9
  (HALT) intactos. cargo build exit 0. Cero reintentos.
- **Capa 2: TRES revisiones adversariales independientes** (bootstrap, cáscara, LiteLLM):
  **6 MAYORES + 5 menores, TODOS corregidos y re-verificados** antes del commit. Los más
  importantes: preparación interrumpida quedaba rota para siempre (ahora marcador de
  finalización + gatillo triple); archivo de llaves podía quedar a medias (ahora escritura
  atómica); el motor de modelos expuesto a la red local (ahora solo loopback, verificado
  en vivo); el gate no probaba un login real (ahora sí). Detalle en `memory/progress.md`
  sesión 43.
- **Capa 3: PENDIENTE — de Pipe** (sin UI nueva esta sesión; sigue la lista acumulada abajo).

### Capa 3 para Pipe (cuando retome)

1. Sin cambios visuales nuevos esta sesión (todo fue motor, cáscara y empaquetado). Sigue
   pendiente lo acumulado: abrir la cáscara y ver el splash (sesión 42) + recorrido de
   producto de las sesiones 39-41.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F3 (wizard de bienvenida):** la primera pantalla que ve el abogado al
   abrir MIA instalada — pedirle solo las llaves mínimas y dejar la política de motor
   "suscripción" lista, todo en llano (§G). Luego F4 (instalador NSIS + E2E en frío en máquina
   limpia, con los 7 puntos acumulados del Riesgo #59 — incluye recompilar los dos ejecutables
   con lo de esta sesión).
2. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para
   vender sin la advertencia de Windows, y las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente (Riesgo #59): los ejecutables ya compilados en dist/ se recompilan en F4
   (el del backend aún no trae el paso de preparación; el del motor de modelos no trae la
   inyección default de loopback — la protección vigente es la configuración del instalador,
   verificada en vivo).

### Trabajo en background sin leer

Nada — 3 recon, 3 ejecutores, 3 revisores, 3 correctores y la regresión: todo leído y
reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **Bootstrap en Python, no en Rust:** la cáscara solo decide CUÁNDO prepararse y muestra el
  progreso; toda la lógica vive en `mia.setup.first_run` (testeable con initdb real).
- **Marcador `.mia-setup-complete` como fuente de verdad** de "preparación completa" — existir
  la base y las llaves NO basta (pueden ser de una preparación interrumpida).
- **Loopback para todo servicio empaquetado** (la base ya lo hacía; el motor de modelos
  bindeaba 0.0.0.0 por default del CLI — corregido en instalador, dev y entry).
- **El modo desarrollo no cambia:** LiteLLM sigue manual (3 terminales); el 4º servicio es
  exclusivo del modo instalado. `litellm_config.yaml` de dev intacto.
- MIA_ENV=prod en el `.env` semilla (verificado contra los 5 usos reales de IS_PRODUCTION —
  no rompe login ni CORS).

---

