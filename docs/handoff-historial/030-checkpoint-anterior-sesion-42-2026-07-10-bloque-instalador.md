## Checkpoint anterior: Sesión 42 (2026-07-10) — BLOQUE INSTALADOR: Fase 1 (empaquetado) COMPLETA + cáscara blindada

### Qué se hizo esta sesión (lenguaje simple)

Arrancó el **bloque del instalador** (nuevo objetivo aprobado por Pipe): que cualquier abogado
instale MIA con doble clic, sin saber de tecnología. Plan de 4 fases; esta sesión cerró la
Fase 1 y adelantó el blindaje de la Fase 2:

- **El motor de MIA ya corre empaquetado** (sin Python ni nada instalado): 459 MB verificados
  en vivo — salud OK, seguridad exige credenciales, y el lector de PDFs escaneados responde.
  La voz queda como descarga posterior (decisión de Pipe); los escaneados van incluidos.
- **La pantalla ya corre autocontenida** (sin Node instalado): 103 MB con su propio motor
  portable, probada en un puerto libre con sus protecciones de seguridad intactas.
- **La cáscara de escritorio quedó blindada** contra el mundo real: no pueden abrirse dos MIA
  a la vez, y ya NO adopta cualquier cosa que responda en sus puertos — exige que el proceso
  demuestre ser MIA. Motivo: en la máquina de Pipe pasó de verdad (la cáscara vieja adoptó
  una app ajena llamada Voicebox como "motor" y mostró el proyecto "Intelligence Sura" como
  "pantalla" — Pipe lo vio). Ahora ese caso termina en un aviso en llano.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 82/82 suites ALL PASS** (línea base sube de 79 a 82 con
  `test_packaging` 23/23, `test_frontend_packaging` 24/24, `test_shell_hardening` 42/42).
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. cargo build exit 0. `test_ux`
  recalibrado de raíz (timeout de build 300→600s: el modo autocontenido alarga la compilación;
  el check sigue validando que compile) y re-verificado 41/41.
- **Capa 2: DOS revisiones adversariales independientes** (empaquetado y cáscara): 1 BLOQUEANTE
  (la política de seguridad nueva rompía la pantalla de arranque — corregido externalizando sus
  estilos/lógica) + 4 MAYORES (el motor "llamaba a casa" por internet en cada arranque —
  violaba la promesa local-first; compresión que podía corromper el lector de escaneados en
  silencio; prueba de humo con "verde falso" si el puerto estaba ocupado; gate que validaba
  comentarios en vez de código) + 5 menores — **TODOS corregidos y re-verificados** antes del
  commit. Detalle en `memory/progress.md` sesión 42.
- **Capa 3: PENDIENTE — de Pipe** (ver abajo).

### Capa 3 para Pipe (cuando retome)

1. **NUEVO:** abrir la cáscara de escritorio y confirmar que la pantalla de arranque SE VE con
   su diseño (fondo oscuro, marca) y que, si un puerto está ocupado por otra app, el mensaje
   en llano aparece.
2. Sigue pendiente el recorrido de producto de las sesiones 39-41 (Proyectos, guías con Mia,
   agentes jurídicos, perfil, Configuración en pestañas) — nada de eso cambió hoy.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F2 (primer arranque automático):** carpeta de datos en
   `%LOCALAPPDATA%\Mia`, llaves de seguridad generadas solas, base de datos inicializada con
   sus 30 migraciones, configuración de instalador para la cáscara, y **LiteLLM como segundo
   ejecutable empaquetado** (decisión declarada de la sesión 42: sin él, dos de los tres modos
   de motor quedan rotos en la máquina del abogado). Luego F3 (wizard de bienvenida) y F4
   (instalador final + prueba en frío en máquina limpia).
2. **ACCIÓN DE PIPE (para VENDER, no para el equipo):** registrar la cuenta de firma digital
   (Azure Trusted Signing) — sin ella el instalador funciona pero Windows muestra advertencia
   de "editor desconocido". También siguen pendientes las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: verificaciones que exigen lanzar la app de verdad quedaron como pasos
   OBLIGATORIOS del E2E de F4 (Riesgo #59): splash visual bajo la política de seguridad,
   ventana de consola del motor (hoy visible — se apaga al ensamblar el instalador), prueba
   empírica del aislamiento de la página remota, y el arranque en frío completo.

### Trabajo en background sin leer

Nada — todos los ejecutores, revisores y regresiones se leyeron y quedaron reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **Pipe (2026-07-10):** instalador con lector de escaneados INCLUIDO y voz como descarga
  posterior; plan de 4 fases aprobado; instalador sin firma suficiente para el equipo Lexia.
- **Fable (declarada):** LiteLLM entra como segundo ejecutable (~150-300 MB más) porque sin él
  los modos "nube" y "soberano" quedan completamente rotos y el modo "suscripción" pierde su
  red de respaldo — se prefirió peso sobre abogados con MIA muda. La consolidación elegante
  (Riesgo #4) queda como refactor futuro.
- La colisión de puertos en máquinas reales es caso ESPERADO del producto (demostrado en vivo
  en la máquina del fundador) — toda adopción exige identidad, nunca un simple "responde".

---

