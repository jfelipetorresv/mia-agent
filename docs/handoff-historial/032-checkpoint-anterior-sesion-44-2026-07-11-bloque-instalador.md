## Checkpoint anterior: Sesión 44 (2026-07-11) — BLOQUE INSTALADOR: Fase 3 (bienvenida cinematográfica + activación de llaves) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Pipe fijó como meta cerrar la **Fase 3 del instalador** y, al ver el onboarding actual, pidió algo
más grande: que **toda la primera vez que un abogado abre MIA se sienta premium** ("cinematográfico,
con wow factor, más amigable"). Se rediseñó la experiencia completa de bienvenida como un solo viaje:

- **Crear despacho → Activar → Conocer tu despacho → Entrar**, todo con el mismo diseño: fondo negro
  con una aurora teal que se mueve sola, la marca MIA que respira, una pregunta a la vez con
  transiciones suaves, una barra de progreso tipo constelación y una celebración al final. (Se
  estrenó la librería de animaciones que ya estaba instalada sin usar.)
- **Paso nuevo "Activar":** el abogado confirma el motor de Mia (su suscripción, ya viene elegida)
  y pega la **clave de búsqueda en sus documentos**, que se comprueba en vivo con un ✓. Todo en
  lenguaje llano, sin una sola palabra técnica, y siempre con la opción de "hacerlo después".
- **La clave de búsqueda queda activa al instante** (Mia ya puede leer y buscar en documentos sin
  reiniciar). La clave de respaldo del motor, si la pega, se activa la próxima vez que abra Mia —
  y ahora se lo decimos claramente.

### Frontend a revisar (Cursor — capa 3): TODO NUEVO

Esta sesión es sobre todo frontend. Pantallas rediseñadas/nuevas: `frontend/app/register/page.tsx`
("Crear tu despacho"), `login/page.tsx`, `activar/page.tsx` (NUEVA), `onboarding/page.tsx`
(rediseño preservando el guardado automático y el resumen final), e infraestructura visual nueva en
`frontend/app/_welcome/`. El Sidebar se oculta en `/activar` y `/onboarding` (pantalla completa).

### Resultado de verificación (3 capas)

- **Capa 1: línea base sube de 84 a 85 suites** con `test_welcome_keys` 39/39. Verdes (por tramos):
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT), `test_first_run` 68/68 (con la migración 031 nueva),
  `test_setup_wizard` 28/28, `test_onboarding_draft` 15/15, `test_hitl_flow` 21/21. `npm run build`
  verde (15 páginas; `/activar` nueva). La migración 031 entra sola al bundle del instalador.
- **Capa 2: CUATRO revisiones adversariales independientes** (seguridad, corrección backend,
  corrección frontend, §G/visual/accesibilidad). 0 BLOQUEANTES. Seguridad SIN mayores explotables
  (el ataque de inyección al `.env` para pisar secretos de instalación está bloqueado). §G LIMPIO
  (cero jerga visible al abogado). Se corrigieron y re-verificaron: el caso "motor en la nube"
  (ahora exige la clave y avisa fuerte de reabrir), dos claves opcionales tratadas de forma
  inconsistente, una doble llamada de validación al pulsar Enter, dos hallazgos de accesibilidad
  (campos y etiquetas sin nombre accesible), y varios menores de robustez de la escritura del `.env`.
  Detalle en `memory/progress.md` sesión 44.
- **Capa 3: PENDIENTE — de Pipe:** recorrer en vivo el nuevo viaje de bienvenida (crear despacho →
  activar → conocer el despacho → celebración) y confirmar que se siente premium.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F4 (la ÚLTIMA fase):** instalador NSIS/MSI + prueba en frío en máquina limpia,
   con los 7 puntos acumulados del Riesgo #59 (recompilar los dos ejecutables ahora incluye
   `welcome.py` + migración 031 + `env_writer.py`) y el nuevo Riesgo #60.
2. **Riesgo #60 (nuevo):** el motor que depende del motor de modelos (opción "nube", o el respaldo
   de la suscripción cuando el abogado NO tiene el CLI de Claude Code) no queda activo hasta cerrar
   y reabrir MIA una vez. La pantalla de activación ya lo advierte con fuerza; el reinicio automático
   es trabajo de F4. Para el equipo de Pipe (suscripción con su CLI) no aplica.
3. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para vender
   sin la advertencia de Windows, y las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).

### Trabajo en background sin leer

Nada — 4 recon, 4 ejecutores, 4 revisores adversariales, 2 correctores y 2 verificaciones: todo
leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **La clave de búsqueda (Voyage) se activa en caliente** porque el backend la usa directamente;
  la de respaldo del motor (Anthropic) la lee el motor de modelos solo al arrancar → se difiere
  con aviso claro. No se abrió ningún puente nuevo hacia la cáscara de escritorio (se respeta el
  blindaje de F2 y el Riesgo #59).
- **Se pide la clave con opción de diferir.** De dónde sale la llave (Pipe la provee vs. cada
  despacho la suya) es una decisión de negocio futura, fuera de F3.
- **Confianza mono-despacho:** cualquier usuario ya autenticado puede configurar las llaves de su
  instalación; si MIA pasa a multi-despacho hará falta un rol de "administrador de la instalación".
- La política de motor "suscripción" ya era la de fábrica: el wizard solo la confirma en llano.

---

