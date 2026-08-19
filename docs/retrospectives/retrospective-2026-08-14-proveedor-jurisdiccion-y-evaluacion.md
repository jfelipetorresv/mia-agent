# Retrospectiva — 2026-08-14 — proveedor, jurisdicción y evaluación

## Resultado

Se corrigieron tres fallas de seguridad y operación antes de que llegaran a una
instalación: una cita del mensaje del abogado podía reaparecer como respaldo de
derecho bajo jurisdicción desconocida; la política adaptativa iniciaba trabajo
ordinario en el modelo más lento y luego podía cambiar de proveedor; y el modo
de membresía Codex podía confundirse con una capacidad de servidor. No se hizo
ninguna llamada real a Codex, Claude ni API durante estas correcciones.

## Qué se hizo

- Jurisdicción desconocida: el texto del abogado permanece íntegro en la traza,
  pero no respalda una cita emitida por Mia. La salida omite la cita y conserva
  evidencia de la omisión (`test_jurisdiction_omission.py`, 29/29).
- Política de proveedor: el trabajo estándar usa Sonnet; Opus/Max entra solo
  por escalada excepcional. Las rutas de membresía para trabajo principal y
  jurídico fallan claro en vez de cambiar a API o local (`test_model_policy.py`,
  55/55).
- Codex por membresía: se añadió una política explícita, sin fallback, con
  subproceso aislado, stdin para el contenido, entorno reducido y salida JSON.
  Solo se habilita cuando Tauri inyecta una marca efímera, API loopback y CORS
  local (`test_codex_production_provider.py`, 15/15).
- Custodia: se eliminó el `.env` local que contenía configuración personal.
  Ninguna clave ni sesión personal se incorporó al repo ni se utilizó para
  pruebas.

## Dónde fallamos y cómo se corrigió

1. Se inició una matriz comparativa de 180 corridas sin comprobar antes que la
   tasa observada cupiera en el límite de tiempo. La ejecución alcanzó solo una
   fracción, expuso timeouts de Opus y se detuvo por orden de Pipe. Corrección:
   artefactos preservados, certificación marcada como no concluyente y runner
   durable/fail-closed; una próxima corrida exige presupuesto, tiempo y propósito
   definidos antes de gastar cuota.
2. La primera barrera de Codex confiaba en variables de entorno y `MIA_APP_DIR`.
   La revisión adversarial demostró que un servidor podía heredarlas. Corrección:
   la marca de Tauri no se persiste en `.env`; Tauri la inyecta al proceso junto
   con host loopback, y la configuración exige CORS local. Esto evita despliegues
   remotos ordinarios; no se declara una frontera contra el administrador del
   mismo host.
3. Se contempló usar claves existentes de esta máquina para construir la ruta
   API. Pipe lo rechazó correctamente. Corrección: se eliminó el `.env` local y
   cualquier API futura se aprovisionará por instalación, nunca desde una clave
   de desarrollo heredada.

## Verificación

Pasaron los gates de proveedor (15/15 y 55/55), jurisdicción (29/29), informe
por oración (47/47), compilación Python, lint y typecheck del frontend, `cargo
check` de Tauri y `git diff --check`. La prueba de primer arranque real requiere
una ejecución posterior con su resultado capturado; no se cuenta como verde en
este cierre.

## Pendientes de continuidad

1. Diseñar y construir el alta por instalador para credenciales propias: Claude
   API y Codex/OpenAI API. Debe usar almacenamiento local ignorado, validar sin
   exponer valores, mostrar costo y dejar la ruta apagada si falta la clave.
2. Confirmar el modelo comercial de la membresía Codex/Claude para Mia antes de
   ofrecerlo a terceros. El código lo limita a la app local del titular; no debe
   anunciarse como capacidad de servidor ni como sustituto de una API empresarial.
3. Ejecutar y capturar el gate real de primer arranque y la colección rápida de
   CI desde un entorno limpio antes de generar una nueva distribución.
4. Solo si se busca una afirmación comparativa de modelos: fijar objetivo,
   presupuesto y tiempo; usar la matriz durable en carriles separados. La corrida
   interrumpida del 2026-08-14 no autoriza ganador ni métrica comercial.
