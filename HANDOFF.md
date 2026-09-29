# CHECKPOINT DE EMPAQUETADO — 2026-09-28 · control de arranque

Continuación autorizada con Claude Code `claude-opus-5-5 --effort high`.
La implementación 0.3.3 está en `2d08474c`, subida a GitHub y con CI aprobado.
La primera reconstrucción completa Core/Compact terminó roja en el humo frontend
(20 s sin HTTP 200), tras aprobar backend, LiteLLM, Next y TypeScript.
No hubo NSIS ni primer arranque. Se conserva la historia y evidencia del fallo.

El mismo frontend pasó la repetición exacta del humo en 4,578 s y 14 escenarios
sintéticos de chat en Edge, con revisión visual independiente. Eso no demuestra
la causa del timeout inicial, ni equivale a un instalador aprobado.

Se ajusta únicamente el control de arranque: margen 180 s/sondeo 4 s acorde a la
shell, diagnóstico sin cuerpos privados, logs TEMP fuera del payload y limpieza
del proceso propio. Sol implementa; Opus emitió APTO estático focal. El director
revisó el diff final: suite conductual 3/3, focal posterior de los menores, parser PS5,
frontend 24/24 y contrato del instalador 48/48 aprobados.

Plan, matriz, evidencias y reservas: `docs/empaquetado-033-2026-09-28.md`.
Siguiente paso: reconstrucción completa Core/Compact sin SkipPayloads desde el
commit que contiene este checkpoint. Verificar primer arranque, manifiesto,
privacidad e integridad y copiar a Downloads. No instalar sobre datos del usuario.
La app instalada, WebView nativo y calidad con modelos jurídicos reales siguen
pendientes. Harness de Lexia permanece intacto.

---
# CHECKPOINT DE CÓDIGO — 2026-09-28 · evidencia y continuidad 0.3.3

Encargo autorizado: cinco mejoras de fuentes, cobertura, vigencia del final, revisión
incremental y recuperación del chat. Rama `codex/mia-evidencia-continuidad-20260928`,
base `9834c6b`. Plan y aceptación: `docs/mejoras-evidencia-continuidad-2026-09-28.md`.
Astra dirige/revisa en esfuerzo medio; Sol implementa en esfuerzo medio. Un solo
escritor de código. El director mantiene este documento y hace los commits.

**Arreglo cerrado en código; empaquetado pendiente por checkpoint solicitado por Pipe.**
Versiones y locks coherentes en 0.3.3. No se construyó ni instaló 0.3.3. Harness intacto.
El commit que contiene esta entrada conserva la implementación, pruebas y evidencias.

- Auditor recibe originales, procedencia y cobertura; derivados necesarios sin
  original no habilitan final. Derivados ajenos requieren exclusión motivada.
- Recibos y descarga validan texto, ejecución, fuentes, jurisdicción y revisor.
  Las referencias explícitas no dependen de que el LLM declare todas sus dependencias.
- Párrafos se reutilizan solo con dependencias y contexto vigentes. Selección inválida
  o procedencia cambiada exige revisión completa. Los sellos no reutilizan índices viejos.
- Chat recupera por usuario/despacho sin reenviar; protege cambios de sesión, carreras
  entre ventanas y callbacks tardíos. Solo persiste IDs, no mensajes ni tokens nuevos.

**Verificación:** Sol ejecutó fuentes 18/18, unidades 6/6, contexto real 4/4 y
focales documentados; integración 56/56, aislamiento 19/19, tipos y lint aprobados.
Astra aprobó el core con cinco pruebas y una sonda propias. Claude Code confirmó
`claude-opus-5-5 --effort high`: dos NO APTO corregidos y tercera pasada APTO estático.
Su reserva de navegador se cerró después con 23 escenarios únicos por Astra
(Chromium/Edge, APIs sintéticas), incluidas capturas finales sin estado residual.
La única línea visual posterior a Opus limpia `status`; tipos, lint y revisor de UI
la verificaron. No atribuir a Opus ejecución de pruebas ni aprobación del escritorio.

Evidencias principales:
- `docs/mejoras-evidencia-continuidad-2026-09-28.md`: matriz, decisiones y límites.
- `output/validation/claude-opus55-{review,recheck,final}.md`: dictámenes completos.
- `output/validation/sol-final-validation.json` y `sol-delta-validation.json`:
  resultados del ejecutor, incluidos estados pendientes a la hora de cada captura.
- `output/playwright/chat-recovery-final-summary.json`: cierre independiente 23/23
  y huellas. Prevalece sobre las reservas UI anteriores del ejecutor y de Opus.
- La corrida rápida inicial roja se conserva; los fallos/timeouts tienen correcciones
  focales, sin reescribir la historia como una corrida única verde. MCP real omitido
  por ausencia de gateway. Sin proveedores jurídicos reales, medición de ahorro ni
  prueba de la app instalada; las fuentes locales no acreditan vigencia normativa externa.

**Procesos:** pruebas, tres revisiones Claude y navegadores concluidos. Servidor Next
propio y depurador cerrados (3111/9229); PostgreSQL sintético detenido con salida 0
(55448). No quedan tareas propias ejecutándose. La demora del último servidor fue
compilación fría de `/chat` (166 s según traza); no se demostró su causa interna.

**Retomar:** comprobar estado Git y este checkpoint; no rehacer los gates aprobados
salvo cambios relevantes. Siguiente paso: desde checkout limpio, ejecutar el build
completo `packaging/build_installer.ps1 -BackendProfile core -WebViewProfile Compact`,
sin `-SkipPayloads`. Comprobar primer arranque sintético, manifiesto y SHA-256; copiar
el instalador a Downloads y cotejarlo. Instalación y WebView reales siguen pendientes;
no inferir estado instalado del registro histórico de 0.3.2 que sigue más abajo.

Pruebas de DB usan clúster temporal propio, nunca el puerto instalado 55432.
Entorno conservado y detenido: `C:\Users\USER\AppData\Local\Temp\mia-evidence-test-20260928-01a0e8f8`,
puerto 55448, configuración en `app\.env`, clúster en `pgdata`, 64 migraciones
(incluida 067). Si se necesita repetir un focal, verificar/reiniciar ese clúster
con `pg_ctl`, puerto 55448 y escucha 127.0.0.1; no conectar a la base instalada.

Para pruebas locales con DB, establecer explícitamente `MIA_TEST_ENV_FILE` con la
ruta absoluta del `.env` de un clúster sintético aislado ANTES de `scripts/verify.ps1`.
En esta sesión: `C:\Users\USER\AppData\Local\Temp\mia-evidence-test-20260928-01a0e8f8\app\.env`.
El helper rechaza ausencia de configuración y puerto local instalado 55432: ese
fallo es protección, no se corrige cargando `.env` del repositorio. En CI, el helper
admite exclusivamente las variables PG_* explícitas del servicio efímero.

# CAMBIO PUNTUAL — 2026-09-23 · llamadas a Claude Code sin transcript

Commit `416f9f9`. `subscription_llm.py` y el conector `claude_code` de `gateway/agent_hub.py` pasan `--no-session-persistence`: cada turno dejaba un transcript de un solo mensaje en `~/.claude/projects` del operador (408 acumulados). Verificado con `.venv\Scripts\python.exe`: `test_model_policy.py` 62/62 y rojo al quitar la opción; `test_claude_code_no_session_persistence` en verde. No corrió la parte de `test_agent_hub.py` que necesita Postgres local. Sin build ni instalador nuevos: el cambio llega a la app instalada en la próxima entrega. `execution/purgar_piloto.py` sigue sirviendo para lo ya acumulado.

# ENTREGA VERIFICADA — 2026-09-06 · Mia 0.3.2 instalada

Build completo core/Compact, exit 0, sin skips ni reutilización, desde
`95a24d5bcaad0b3a1e518694679342bc2bedc195`. Servicios e interfaz recompilados;
TypeScript aprobado, primera ejecución sintética 40.977 ms. NSIS final aprobado.

- Instalador en `C:\Users\USER\Downloads\Mia_0.3.2_x64-setup.exe`, 175.245.565 bytes.
  SHA-256 `7f99b8b6e67c989ec3dc8f5abf98bccfe9817f3d25971afc982760ceeabc81bb`.
  Copia de entrega cotejada con manifiesto. Instalación silenciosa exit 0;
  registro y ejecutable confirman 0.3.2 en AppData/Local/Mia.
- WebView REAL instalada aprobada: puentes nativos, salud, 63/63 migraciones,
  pantalla «Mis suscripciones» con Claude detectado y Codex con sesión. Captura
  final inspeccionada tras completar la animación. No se cambiaron conexiones,
  abrieron expedientes ni crearon usuarios. El primer intento del smoke llegó
  antes del frontend; se corrigió su espera y pasó con la pantalla cargada.
- Cierre ordenado verificado, servicios y puertos cerrados; reabierta normalmente,
  salud correcta y puerto de depuración 9231 cerrado. Se deja Mia abierta.
  Observación menor de accesibilidad cerrada y revisada por Sol antes del build:
  ambos estados persistentes anuncian errores mediante role=status/aria-live.
- Evidencia adicional en output/validation/entry-0.3.2.json y
  output/playwright/mia-installed-0.3.2.{json,png}. Sin pruebas de calidad jurídica
  con proveedores reales. Límites funcionales y pruebas en el checkpoint siguiente.

---
# CIERRE DE CÓDIGO — 2026-09-06 · entrada, chat y fuentes 0.3.2

Solicitud de Pipe sobre siete capturas de 0.3.1. Implementación y revisión independiente
completadas; build completo e instalación 0.3.2 pendientes en este checkpoint.

- Activación reúne Claude/Codex en «Mis suscripciones», detecta disponibilidad y separa
  cuentas API. Reutiliza claves; Voyage queda opcional. Guardar política falla visible.
  Suscripción no consume API por conservar un respaldo histórico; auxiliares CLI/local.
- Se eliminan entrevista de clientes, prohibiciones y aprobación. La firma procede solo
  del registro; perfiles existentes no se sobrescriben. Caso nuevo sin selector de modo;
  rechaza nombre vacío y normaliza espacios. Documentos conservan aprobación obligatoria.
- Chat muestra respuesta SSE o error HTTP/SSE comprensible, incluido borrador pendiente.
  No cambia ese bloqueo previo ni promete continuar mientras está pendiente aprobación.
- Carpetas locales YA vinculadas: lectura automática por referencia, sin importar al índice.
  Importación explícita aparte. Sin Voyage hay texto/FTS. Límites por turno: 12 archivos,
  8 MiB y 500 explorados; avisos de recorte/fallo/raíz alterada. Extractos en registros normales.
  No descubre todas las cuentas externas ni hereda conexiones privadas de CLI.
- Verificación sintética: fuentes 15/15, recuperación adaptativa 59/59, conocimiento 37/37,
  referencias 43/43, resiliencia 7/7, entrada 11/11, onboarding 8/8, aprendido 34/34,
  políticas 61/61, OpenRouter 17/17, aviso 44/44, RLS 19/19, metagate 9/9, instalador 48/48.
  Navegador: activación 8 escenarios, alta/casos claro y móvil oscuro, chat SSE/error visible.
  Mutaciones detectadas: exigir Voyage y permitir compresión API en suscripción.
  TypeScript/lint/build aprobados; empaquetado recompilará último ajuste de fuentes/aria-live.
- Revisión independiente Sol: fuentes/alta aprobadas, sonda cruzada tenant/caso vacía;
  Terra revisó routing de Sol. Sin proveedores reales ni prueba de calidad jurídica.
- Astra dirige esta sesión y asigna a Sol/Terra según necesidad y economía de tokens.
  No se cambia por inferencia el catálogo de modelos del producto.
- DB de pruebas 55439 apagada y conservada fuera del repo en Temp/mia-entry-test-db-20260906
  tras rechazo automático al borrado. Dev3111 apagado. Sin modificación de la DB instalada.

Evidencia: output/validation y output/playwright; contratos en
`docs/entrada-conversacion-fuentes-2026-09-06.md`. Entrega: instalador core/Compact0.3.2.

---
# HANDOFF — Mia (traspaso a Cursor)

> **Referencia histórica del plan (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». La ruta externa ya no existe en esta máquina (comprobado
> 2026-09-06); entrar por `AGENTS.md`, `CLAUDE.md`, `TRASPASO-MODELO.md` y el cierre más reciente.

---

# CIERRE — 2026-09-06 · memoria larga e instalación 0.3.1 completadas

Meta explícita de Pipe: implementar memoria de conversaciones largas, instalar esta
versión y dejar el instalador accesible. Base `86164e5`, misma rama de auditoría.
Meta cumplida: memoria implementada y revisada, NSIS completo construido desde
`9453c4c6d4d3289df4f81c5c9c7aa0da80c02b12`, instalado y abierto en esta máquina.

- Recupera todos los originales en páginas de 200; checkpoint persistido por despacho
  y conversación con cursor, huella UTC, revisión y RLS forzado. Conserva primeros
  cinco, últimos treinta y `[VERIFICAR]` textuales; invalida ante cambios de origen.
- Reutiliza resúmenes, acepta solo ahorro, evita compresiones concurrentes del mismo
  tramo y detiene intentos poco útiles. Si los originales caben, se usan íntegros;
  si no caben, avisa sin responder como si recordara todo. No guarda contexto efímero.
- Verificación consolidada de nueve casos de memoria: última pasada amplia 8/9,
  antithrashing corregido con fechas UTC y focal 1/1; después prefijo/edición/borrado
  forzado 2/2. No presentar como una única corrida 9/9. Dos mutaciones detectadas
  (omitir cabeza; inyectar checkpoint de otro despacho). Proveedores simulados.
- Regresión final: asistente 32/32, compresor 30/30, recuperación 61/61, RLS 19/19,
  contratos SQL 7/7 y metagate 9/9. Migración 066 sellada: 63 migraciones. Su forma
  final se aplicó a desarrollo mediante el helper del test legado. Bases temporales
  de pruebas eliminadas. Revisión independiente aprobada.
- Versiones frontend/desktop/Cargo/Tauri coherentes en 0.3.1; gate instalador 48/48.
  PostgreSQL de desarrollo apagado ordenadamente; el puerto 55432 pertenece ahora
  a la instalación. No iniciar simultáneamente la base de desarrollo en ese puerto.

## Entrega e instalación verificadas

1. Build completo core/Compact, sin skips ni payloads reutilizados, exit 0 (~50 min).
   Backend, LiteLLM y frontend empaquetados y probados; TypeScript aprobado.
   Primera ejecución aislada aprobada en 88.763 ms; Tauri y NSIS aprobados.
2. Instalador: `C:\Users\USER\Downloads\Mia_0.3.1_x64-setup.exe`, 175.244.104 bytes.
   SHA-256: `a1f9d79fb312738f0a9319970d70ef69317789c16ba44f95d53ed451e5b58c8a`.
   Copia de entrega cotejada contra el artefacto y su manifiesto.
3. Instalación exit 0 en `C:\Users\USER\AppData\Local\Mia`; registro y ejecutable
   confirman 0.3.1. Se corrigió una ruta NSIS antigua recordada con `/D` explícito.
   El ejecutable NSIS difiere del release solo en el marcador normal `UNK→NSS`;
   normalizar esos tres bytes en memoria produce exactamente el hash instalado.
4. `e2e/installed_smoke.mjs` aprobado sobre la WebView real instalada: bienvenida
   visible, puentes nativos de estado/protección, DB/pgvector/checkpointer/provenance
   listos y 63/63 migraciones. Captura inspeccionada visualmente. No se crearon
   usuarios ni se eligió jurisdicción. Perfil core: OCR y voz opcionales no incluidos.
5. Cierre ordenado comprobado, incluidos servicios y PostgreSQL. Reabierta normalmente
   sin CDP (9231 cerrado), con salud correcta. Se deja Mia abierta para el ingreso inicial.

Evidencia de entrega: `validation/installed-release-0.3.1.json`; manifiesto original
en `desktop/src-tauri/target/release/bundle/nsis/mia-release-manifest.json`.
Captura local: `output/playwright/mia-installed-0.3.1.png`. No hubo push ni merge.

Diseño: `docs/chat-continuidad-idempotencia.md`. Evidencia de código:
`validation/conversation-memory-0.3.1.json`. La lectura pagina PostgreSQL pero reúne
originales en RAM. No hay medición de calidad semántica de modelos reales ni promesa
monetaria; el resumen no sustituye fuentes ni verifica citas.

---

# CIERRE — 2026-09-06 · continuación: recuperación de envíos del chat

Continúa sobre `c5281c2` en `fix/mia-audit-efficiency-20260906`. Se añadió idempotencia
propia del chat JSON/SSE: `request_id` opcional, registro por despacho/usuario/envío,
recuperación de respuesta completada antes del control de presupuesto y reserva que
no caduca ante fallos o cancelación. No se repite una inferencia de desenlace incierto.
La pantalla conserva la clave al reintentar, evita duplicar burbujas y bloquea otro
envío hasta recuperar el pendiente o abrir una conversación nueva.

- Migración aditiva `065_assistant_chat_requests.sql`, RLS forzado, sellada sin cambiar
  SQL históricos. El aplicador existente la descubre automáticamente. Aplicada dos
  veces en una base temporal propia; no aplicada a la instalación del usuario.
- Nueva suite `execution/test_assistant_chat_requests.py`: 7/7 en PostgreSQL real,
  proveedor sustituido. Seis solicitudes concurrentes ejecutan un solo turno; replay
  entre instancias, claves distintas, RLS, cancelación, fallo de recibo, JSON/SSE y
  presupuesto comprobados. Mutación que omite caché detectada en rojo. Bases limpiadas.
- Compatibilidad: asistente 32/32, contratos de migración 7/7, RLS 19/19, frontera
  jurídica JSON/SSE verde y resiliencia frontend 7/7. Evidencia consolidada en
  `validation/chat-idempotency-2026-09-06.json`. No se repitieron las 95 suites anteriores.
- Frontend: lint y build final con TypeScript verdes. Navegador real con API sintética,
  13 comprobaciones por tema en claro/oscuro, cero errores de página. Capturas y detalle
  en `output/playwright/chat-idempotency.json`; root inspeccionó reintento claro y
  recuperación oscura. Revisión independiente detectó y cerró mezcla de hilos tras fallo.
- PostgreSQL portable se encontró detenido (WAL writer, excepción Windows), se reinició
  y terminó recuperación a las 21:50:42 hora local. No se contó ese timeout como verde.
  Servidor temporal de frontend 3111 detenido; modelos y canales externos no usados.

## Límites y siguiente trabajo

- La respuesta durable sobrevive al servidor; la clave de la pantalla no sobrevive a
  recargar/cerrar navegador. Dos claves distintas entre dispositivos no serializan el
  mismo hilo. Fallar el recibo después del historial deja incertidumbre, no otro consumo.
- Memoria de conversaciones largas revisada, **no implementada**: últimos 200 mensajes
  omiten historia antes del compresor. Un resumen durable requiere cursor de cobertura,
  originales y pendientes preservados, control de carreras e información de cobertura
  parcial. Diseño y criterios en `docs/chat-continuidad-idempotencia.md`.
- Cambios locales en rama: no merge, push, despliegue ni NSIS actualizado. Mantienen los
  pendientes de instalación, puente Tauri, evaluación real de modelos y dictamen Cursor
  del cierre anterior. No se acredita producto sin bugs ni ahorro monetario real.

---

# CIERRE — 2026-09-06 · auditoría, reglas genéricas y referencias Grok

Rama `fix/mia-audit-efficiency-20260906`, base `8a5ac10`. Pipe pidió revisar propósito,
cableado y calidad de Mia e incorporar principios generales de Lexia Litigio. Añadió
`grokrouter-main.zip` y `grokky-main.zip` como referencias. Comparación y matriz completas:
`docs/auditoria-mia-2026-09-06.md`; no se copió código sujeto a sus licencias restrictivas.

## Cambios comprobados

- Compresión que aumenta tokens se rechaza; checkpoint propio no duplicado; ante contexto
  excesivo no se reintenta si el compresor no redujo el prompt. Preserva advertencias.
- Aprobación que regenera borrador devuelve estado pendiente real, texto, huella e informe
  nuevos. La pantalla exige otra revisión y bloquea ediciones concurrentes mientras espera.
- Métrica Codex de tokens leídos de caché llega al recorder, sin doble conteo ni fingir
  precio medido para cuota de suscripción.
- `AGENTS.md` incorpora principios genéricos y conecta las pruebas con sus productores;
  el catálogo rápido suma compresión y recibo de revisión.

## Verificación y estado del cierre

- Focales: compresor 30/30, recuperación 61/61, recibos HITL 4/4, Codex 31/31.
  Negativos/mutaciones detectaron las versiones anteriores. Revisión independiente aprobada;
  la observación de edición concurrente se corrigió y re-revisó.
- UI: build de producción, lint y tipos verdes. Navegador claro/oscuro con API sintética:
  nueva versión + nueva huella + nueva constancia + controles bloqueados. Cero errores de
  página; axe WCAG A/AA sin incidencias. Capturas en `output/playwright/`.
- Primer quick: 31/35, tres fallos por PostgreSQL en recuperación y timeout MCP. Los tres
  de base ya pasaron al recuperarse. Original conservado en `validation/audit-2026-09-06-quick.json`.
- Regresión ampliada cerrada: **95/95 suites seleccionadas**, 2.963 checks contabilizados
  (no total de aserciones únicas), en `validation/audit-2026-09-06-system.json`. RLS 19/19
  verificado aparte y E2E sintético 60/60 incluido. MCP offline+DB recuperado 40/40;
  parte live omitida. No se declara regresión exhaustiva; 57 omisiones justificadas.
- `cargo check --locked` **inconcluso**: se detuvo el proceso propio durante copia de
  recursos Tauri, tras observar progreso de E/S lento (más de 500 MB copiados). No falló
  una comprobación de Rust; tampoco se acredita compilación. Log local en
  `%TEMP%/mia-audit-cargo-20260906.log`. No se modificó fuente de escritorio.
- PostgreSQL portable queda encendido tras recuperarse. Servidor temporal de frontend
  cerrado; no quedan pruebas ni compilaciones corriendo. No se arrancó API de producción
  ni canales externos.

## Pendientes y límites

- No se reconstruyó ni instaló el NSIS con estos cambios. Cotejo formal de Cursor pendiente:
  el CLI encontrado devuelve ayuda del editor al pedir ayuda del agente; no hubo dictamen.
  Codex sí inspeccionó las capturas y ejecutó navegador/accesibilidad.
- Faltan prueba de instalación limpia, puente Tauri instalado y servicios opt-in; modelos
  reales no evaluados en esta auditoría. No hay ahorro monetario de producción acreditado.
- Resumen persistido por conversación e idempotencia por envío son propuestas, no funciones
  añadidas. Sus criterios y fronteras de aislamiento constan en el informe.
- No se cambiaron fuentes de clientes, precios, proveedores ni doctrina de jurisdicción.

## Hallazgos de Cursor (capa 3)

Pendiente dictamen de Cursor sobre las capturas de revisión. Comprobar que tras cambiar
selección aparece la nueva versión, queda desmarcada la constancia humana y no se permite
editar durante la espera. La lógica ya cuenta con revisión independiente y pruebas.

---

# CIERRE — 2026-09-02 · sesión 63 · auditoría de Claude Code, cableado y regresión

## TL;DR

Se auditó el último estado que dejó Claude Code y se cerraron los huecos verificables que
aparecieron al recorrerlo. El punto de partida era `a961131`, ya alineado con `origin/main`;
no había commits perdidos ni cambios sin push de la sesión 62. La revisión de esta sesión se
hizo con Claude Code (Opus, esfuerzo xhigh) y con pasadas independientes de Sol, Terra y Luna
(xhigh), cada una sobre una superficie distinta.

El desarrollo queda **verde en la verificación rápida integrada: 35 suites, 167,4 s**. También
pasaron lint, TypeScript y el build de producción del frontend (17 rutas), además de `cargo
check` del escritorio. La regresión completa inicial no fue verde por dos dependencias de
entorno (LiteLLM apagado y Telegram sin canal opt-in) y por contratos de pruebas que aún
nombraban rutas antiguas; los contratos deterministas fueron corregidos y repetidos en verde.

## Qué dejó construido Claude Code

- **Bienvenida y ayuda (`95c55ac`)**: la entrevista pasó de siete preguntas a cinco, la
  jurisdicción quedó como control único y `/ayuda` se convirtió en una pantalla propia con
  la explicación de cada sección.
- **Revisión y atajos (`12b2fc0`)**: los puntos abiertos aparecen antes de aprobar y los
  atajos del chat se pueden reordenar con arrastre o teclado, conservando el orden.
- **Capacidades de ayudantes (`89f16cb`)**: lo que la máquina no tiene no se promete al modelo;
  la pantalla y el prompt comparten la misma medición fail-closed. Incluyó la migración 064.
- **Sistema visual y escritorio (`82d659c`)**: 49 superficies adoptaron el sistema Luxury y
  nació el gate que comprueba que la pantalla solo invoque rutas existentes del puente seguro.
- **Deuda y barreras (`a2cf33a`, `85893b8`, `b00f2db`)**: retiro seguro de carpetas rotas,
  banco de citas/holdout, corrección de tests ciegos y actualización de riesgos.
- **Pantallas densas (`a961131`)**: `/ayuda` y `/configurar` dejaron de mostrarlo todo a la
  vez, con navegación por pestañas, deep-links y estado más legible.

## Qué se corrigió en esta auditoría

- Chat: una conversación que falla al cargar ya no borra el hilo visible; hay reintento,
  controles de historial/nueva conversación en móvil y anuncios accesibles de estado/respuesta.
- Memoria, ayuda y configuración: los errores de carga ya no se convierten en listas vacías
  engañosas; cada pantalla ofrece reintento claro.
- Configuración: se eliminó una referencia ARIA a paneles inexistentes y se añadió un gate
  específico de resiliencia del frontend.
- CI y pruebas: el contrato de migraciones corre en el job crítico que ya instala el backend;
  el purgador de carpetas es portable; el holdout normaliza saltos de línea de Windows y conserva su sello;
  Word acepta el MIME habitual `application/docx`; y los tests fueron alineados con las rutas
  canónicas actuales, sin cambiar la política de motores para hacerlos pasar.
- Evidencia: el cotejador de capturas conserva el detalle de errores sin query strings ni
  secretos. El puente productivo sigue usando solo POST, allowlist y loopback.

## Verificación ejecutada

- `scripts\verify.ps1 -Mode quick`: **35/35 suites verdes** (167,4 s).
- Gates focales: migraciones **7/7**, purgador **13/13**, configuración **34/34**, resiliencia
  del frontend **7/7**, holdout/mutaciones **50/50**, gasto **83/83**, benchmark de proveedores
  **20/20**, correo→expediente **24/24**, multi-carpeta de expediente **31/31**, multi-carpeta
  de proyecto **31/31**, personas **52/52**.
- Frontend: `npm run lint` **0**, TypeScript **0**, `npm run build` **0**; las **17 rutas** se
  generaron. El aviso de SWC nativo fue absorbido por el fallback WASM de Next y no impidió
  compilar. Escritorio: `cargo check` **0**.
- CI remoto sobre `55680a2`: **3/3 jobs verdes** (frontend estático, contratos legales críticos
  y cáscara de escritorio).
- Navegador: el arnés real tomó `/casos` y `/onboarding` en claro/oscuro, sin redirecciones ni
  spinners. Registró 8 mensajes por captura, todos asociados al puente esperado `mia-shell.localhost`
  ausente en navegador puro; esto no acredita el puente instalado.

## Pendientes reales

- **Instalador**: el build Compact/core ya se reensambló desde `59cfd71`: `Mia_0.3.0_x64-setup.exe`,
  167,1 MB, SHA-256 `d35b243981b9443f189e93924145b501c28d4e28d6b91b0c59dd8c663751126c`.
  El primer arranque sobre datos temporales limpios pasó en 37,8 s y los humos de frontend
  portable/LiteLLM pasaron. Sigue pendiente instalar ese NSIS en una máquina limpia, verificar
  el puente real dentro de Tauri y firmarlo si corresponde. El gate contractual del puente no sustituye
  esa prueba.
- **Cotejo visual humano**: el arnés ya produjo 4 capturas actuales de `/casos` y `/onboarding`
  en claro/oscuro, pero aún falta compararlas visualmente contra
  `docs/design/MIA-Luxury-Design-Pack/` y dar el visto bueno de diseño. El gate de tokens no puede
  declarar equivalencia visual.
- **Servicios vivos**: LiteLLM no estaba levantado en el puerto 4000 durante la regresión; el
  bloque de reintentos y el MCP-live quedan pendientes de una corrida con ese servicio. Telegram
  está correctamente opt-in, pero no hay `TELEGRAM_BOT_TOKEN` configurado en esta máquina.
- **Benchmark de calidad**: la ruta Codex productiva (`codex`/`cli-codex`) y la ruta lateral de
  evaluación (`cli-codex-eval`) ya están separadas y verificadas; todavía no existe un resultado
  comparativo de calidad con ambos brazos completos y revisión humana ciega.
- **Producto conocido**: expedientes muy grandes pueden agotar el tiempo de la suscripción y
  saltar al motor de crédito; el circuit-breaker y el aviso lo mitigan, pero no aumentan el
  límite de contexto. La lectura agéntica bajo suscripción sigue apagada y su límite está
  declarado en pantalla.
- Siguen sin entrar al repositorio las imágenes de Antigravity mencionadas en la bitácora.

La suposición de esta auditoría es que “lo otro que quiero revisar” significa salud integral
del proyecto: código, cableado, pruebas, frontend, escritorio, documentación y pendientes de
release. No se tocó lógica jurídica de negocio ni se usaron datos reales de clientes.

---

# CIERRE — 2026-09-01 · sesión 62 · los 23 puntos de UX cerrados y la deuda de la 61 en cero · EMPEZAR AQUÍ

## TL;DR

Registro histórico: esos cinco commits se incorporaron después a `origin/main`; al iniciar la
sesión 63, `HEAD` y `origin/main` estaban en `a961131`. La bitácora de feedback UX del 2026-08-19
queda **cerrada: sus 23 puntos están todos hechos**, y la deuda declarada en la sesión 61 queda
en cero salvo lo que sigue abajo con su causa. `verify.ps1 -Mode quick` VERDE: **33 suites,
36,6 s**. Los gates se corren con `.venv\Scripts\python.exe` (el Python del sistema no tiene
psycopg y da rojos falsos).

Lo que más importa de esta sesión no es lo que se construyó, sino **lo que una revisión
adversarial independiente encontró después**: siete defectos que los gates propios daban por
buenos, dos de ellos DENTRO de los gates nuevos. Está todo corregido y en el aprendizaje 93.

## Lo hecho

- **Deuda de la 61 `a2cf33a`**: las 6 carpetas rotas retiradas y con comando propio
  (`purgar_carpetas_rotas.py`, simulacro por defecto); los 2 rojos del banco de pruebas con
  causa raíz —el doble no emitía los productos de etapa de la 059, el turno abortaba y no
  había cita que omitir— **69/69**; y un tercer helper que retrocedía el vocabulario del
  CHECK (aprendizaje 86 vivo en `init_soul_versions`), con su barrera.
- **Revisión y atajos `12b2fc0`**: los puntos que la revisión deja abiertos se ven ANTES de
  aprobar, no solo en el recibo; y los atajos fijados se reordenan arrastrando, con flechas
  para quien no usa ratón. Probado en vivo: el orden cambia y sobrevive a recargar.
- **Bienvenida `95c55ac`**: la entrevista pasa de siete pasos a cinco (fuera ciudad/país,
  registro profesional y estándar de cierre; la firma se precarga); la jurisdicción es un solo
  control; doce líneas rojas del oficio como borrador. Y «Cómo funciona Mia» es pantalla propia
  (`/ayuda`) con cuándo sirve y cómo se usa cada sección.
- **Agentes `89f16cb`**: un ayudante declara qué puede hacer (leer escaneados, buscar en vivo,
  redactar largo). Lo marcado viaja a su prompt; **lo que el equipo no tiene NO se le afirma al
  modelo**, se le dice que hoy no puede. Migración `064`, aditiva y sellada.
- **Diseño `82d659c`**: 49 superficies dibujadas a mano llevadas al sistema, y la corrección
  sellada de Pipe deja de ser un hábito y pasa a ser gate (`test_sistema_de_diseno`). Más
  `test_puente_shell`, que impide que la pantalla llame a una ruta que la cáscara no sirve.

## Lo que encontró la revisión adversarial (y por qué importa para la próxima sesión)

Nueve mutaciones sobre el árbol de trabajo; **tres no pusieron rojo el gate que debían**. Ese
número es el hallazgo: quien escribe un gate tiende a mutar lo que el gate mira, no lo que el
gate debería mirar. Los dos casos que conviene tener presentes al escribir el próximo:

- Un check que buscaba **una cadena de texto** en vez de una conducta (el nombre de un archivo
  en el código del helper: un comentario bastaba para absolverlo). Ahora ejecuta y mide.
- Un check que, **sin base de datos, decía «no evaluado» y aprobaba**. Un gate que aprueba
  porque no pudo medir es peor que no tenerlo.

Y el defecto de producto más caro: la honestidad sobre las capacidades estaba resuelta en la
PANTALLA y abierta en el PROMPT. Detalle completo en el aprendizaje 93.

## Decisiones de Pipe aplicadas (todas de la bitácora 2026-08-19)

D6 (líneas rojas con borrador editable), D8 (capacidades del agente), D9 (registro profesional
a Configuración), D10 (un solo selector de jurisdicción), y los puntos 5, 7, 8, 11, 12, 15,
15b, 17 y 22. Ninguna decisión nueva: esta sesión ejecuta lo ya decidido.

## Deuda declarada (con causa)

- **Prueba en frío del instalador.** El puente quedó verificado por contrato (`test_puente_shell`
  7/7), pero el `.exe` que quedó en disco es anterior al rediseño y al puente actual. Falta
  reensamblarlo desde checkout limpio y acreditar los botones de Protección en una máquina limpia.
- **Cotejo visual contra los renders del pack.** Las capturas en claro y oscuro están tomadas y
  la tabla de veredictos está en `validation/validation-log.md`; decir que se ven *como el
  pack* exige comparar contra `docs/design/MIA-Luxury-Design-Pack/`, y eso es mirar, no medir.
  El gate de diseño lo advierte en su propia salida.
- **Sin push (superseded).** El estado histórico ya fue incorporado a `origin/main`; cualquier
  cambio pendiente de la sesión 63 se documenta y se commitea al cerrar esta auditoría.
- **Las imágenes de Antigravity** que menciona §0 de la bitácora siguen sin llegar al repo.

## Trampas del entorno que costaron tiempo (para no repetirlas)

- El build del instalador **exige checkout limpio** y lo rechaza si no lo está. Va después del
  commit, no antes.
- La verificación visual con navegador headless: **navegar por `localhost:3100`, no por
  `127.0.0.1:3100`** — con la segunda, la sesión no resuelve y toda pantalla sale en el spinner
  de carga, que leído deprisa parece que el producto está roto.
- Un `addInitScript` de Playwright corre **antes de que exista el documento**: tocar
  `document.documentElement` ahí siembra un error en cada página del recorrido.
- `git grep`/`find` recursivos sobre el repo cuelgan por el antivirus: usar `git ls-files` o la
  herramienta de búsqueda del harness.

---

# CIERRE — 2026-08-24 · sesión 61 · D3/D4/D7 + deuda vieja en cero + segunda tanda del harness

## TL;DR

Ocho commits pusheados (`4718432`…`ac447cc`). Los bloques D3 (Casos), D4 (motor único) y D7
(atajos editables) de la bitácora UX quedaron implementados y verificados; la deuda vieja quedó
en cero salvo lo declarado abajo; y entró la segunda tanda de mecanismos del harness de litigio,
todos como AVISO. `verify.ps1 -Mode quick` VERDE: 29 suites, ~35 s. Los gates se corren con
`.venv\Scripts\python.exe` (el Python del sistema no tiene psycopg y da rojos falsos).

## Lo hecho

- **D3 `4718432`**: asuntos+proyectos → un solo concepto «Casos» (misma tabla `matters`; la
  diferencia real es el modo borrador/directo, ahora un control dentro del caso con
  `PUT /api/matters/{id}/modo` y 409 honesto). URLs viejas redirigen. Sin migración (decisión
  documentada en `ux.py`). Vocabulario visible «asunto»→«caso» en toda la capa visible.
- **D4 `b13336f`**: pantalla de activación con preselección real del motor detectado, una sola
  pantalla de claves con requisitos como requisitos, y OpenRouter fuera del grupo de motores con
  consentimiento expreso (sin casilla no viaja `allow_openrouter`). **Copy pendiente de aprobación
  de Pipe.**
- **D7 `2010a8a`**: atajos del chat editables — migración `062_shortcut_prefs` (RLS patrón 047),
  CRUD `/api/atajos`, panel «Tus atajos». Lo fijado nunca se descarta; el desborde se dice con el
  número exacto. Falta reordenar arrastrando (columna `position` en 0).
- **Deuda `6355d66` + `8374572` + `c8fca73`**: gate real del lanzador (`test_api_launcher`, probado
  por mutación), `setup_db_steps.py` (PS 5.1), `RuntimeHealthBanner` por el puente `mia-shell` sin
  debilitar seguridad, `test_e2e` 59/59 de raíz (mocks con contrato viejo de packs 059), tres gates
  rojos viejos con causa raíz (aprendizajes 86-87), y las consolas negras (aprendizaje 85 — regla
  sellada de Pipe: ningún gate abre ventanas).
- **Harness tanda 2 `ac447cc`** (auditoría previa: el harness NO tiene cifra medida de mejora, solo
  diagnóstico): modo `aviso|muro` declarado en `config/catalogo-barreras.json` (15 invariantes) y
  cotejado contra conducta en ambos sentidos (`test_modo_barreras`, probado por mutación); raíces
  de datos (`test_raices_datos` — ya cazó 6 carpetas rotas en la DB, residuo de seeds); denuncia de
  ausencia de medición (`test_medicion_por_nodo`, auto-mutación integrada); latencia+`tool_calls`
  por nodo (migración `063`, `usage_by_node()` ampliado); disposición de hallazgos en el recibo
  `human_approval` del ledger (`memory/hallazgos.py`), sin fricción de UI. NO portados con razón:
  herencia de cotejo (Mia capada a 1 pasada/turno), techos por rol (solo aplicaría al Agent Hub),
  paralelismo (grafo lineal).

## Decisiones de Pipe — TOMADAS el 2026-08-24 (mismo día, en chat)

1. Barra lateral: CLARA en tema claro — anula la decisión previa «siempre oscura por identidad
   de marca». Implementada en el commit de barra+marca de esta misma sesión.
2. Ayudantes del Agent Hub: CON la marca en letra pequeña bajo el nombre funcional («Funciona
   con Claude Code…») — excepción parcial sellada a §G, documentada donde vive la regla.
3. Copy de D4 (motor / claves / consentimiento OpenRouter): APROBADO por Pipe tal como está
   en `b13336f`.

## Deuda declarada (con causa)

- Capa 3 del puente `mia-shell` (botones en la app empaquetada): exige re-ensamblar el instalador
  con checkout limpio.
- `test_eval_harness.py`: 2 rojos preexistentes (demostrado idéntico en HEAD).
- 6 carpetas rotas en la DB local (residuo de seeds/tests): reportadas por `test_raices_datos` en
  cada corrida, no borradas.
- Bloque informativo de disposición de hallazgos en la pantalla de revisión: el dato ya viaja en
  `metadata`, falta pintarlo.
- Verificación visual en navegador de D4 y D7: no corrida (D3 sí se verificó en vivo).

---

# CIERRE — 2026-08-19 · sesión 46 · F4 CERRADA (instalador existe) + 23 observaciones de UX de Pipe · EMPEZAR AQUÍ

## TL;DR

Se cerró el bloque instalador: **existe un instalador funcional** y Pipe lo instaló y usó
por primera vez. De ese uso salieron **23 observaciones de UX/diseño** que son el próximo
bloque de trabajo. Están todas, con causa raíz verificada en el código y solución
propuesta, en **`memory/bitacora-feedback-ux-2026-08-19.md` — ese archivo es la fuente de
verdad del bloque UX. Leerlo completo antes de tocar `frontend/`.**

Pipe cambia de computador en este punto: este HANDOFF + la bitácora son el traspaso.

## Lo que se logró hoy

**1 · F4 (última fase del bloque instalador) — CERRADA.**
`Mia_0.3.0_x64-setup.exe`, 156.4 MB (meta ≤335 MB cumplida y medida), NSIS vía
`tauri build`, SHA-256 `453ce456ca07279a470792c4702589e85e8a96453673f0836ade9bcaf72d777e`,
manifiesto en `bundle/nsis/mia-release-manifest.json` (commit `c94594c`, `reused_payloads:false`).
Verificado: smoke de LiteLLM (health + `/v1/models` con y sin Bearer + bind solo a
`127.0.0.1` con acceso LAN rechazado), smoke de frontend en 3100 con node portable,
**primer arranque en frío sobre datos temporales limpios: 21.852 ms, exit 0** (initdb +
migraciones con el pgsql empaquetado), pgvector presente, pgAdmin excluido. Revisor
independiente sin contexto previo lo auditó y lo declaró entregable.
Pipe lo instaló y la app arrancó.

**2 · Bug de packaging arreglado (`c94594c`).** `build_backend.ps1` instalaba PyInstaller con
`--no-deps` y omitía `pyinstaller-hooks-contrib`. Sin él no existe `hook-cryptography.py`,
PyInstaller no recoge `_cffi_backend`, el primer import de `cryptography` muere en un
try/except silencioso y el reintento de PyJWT explota con *"PyO3 modules compiled for
CPython 3.8 or older may only be initialized once per interpreter process"* — el guard de
PyO3 enmascaraba el `ModuleNotFoundError` real. `mia-backend.exe` crasheaba en `--first-run`.
Se agregó el pin `2026.6` + un gate de auto-reparación para venvs viejos. No toca pins de la app.

**3 · Protección de datos: pestaña 100% muerta → arreglada (`0a0f020`, ya en main).**
Causa raíz: `lib.rs:~1400` navega la ventana a `http://localhost:3100`, que para Tauri v2 es
**origen remoto**; por endurecimiento deliberado (sin capability `remote`, sin
`dangerousRemoteUrlIpcAccess`) los orígenes remotos no reciben IPC, así que `window.__TAURI__`
nunca existe ahí y **cada botón de Protección estaba muerto desde siempre** (`restart_litellm`
de `/activar` también). No era regresión: nunca pudo funcionar como estaba diseñado.
Arreglo **sin debilitar la seguridad**: puente por esquema URI propio `mia-shell`
(`http://mia-shell.localhost`) interceptado en proceso por WebView2 — sin puerto TCP,
inalcanzable desde otro programa o la LAN — con allowlist de `Origin` exacta, solo POST y
rutas cerradas, reusando los comandos de mantenimiento existentes. Nuevo `frontend/lib/shell.ts`.

**4 · La bienvenida ya respeta el tema del abogado (`10d447e`).**
`WelcomeShell.tsx:52` forzaba `dark` + `bg-[#060606]` cableado: login, registro, `/activar` y
`/onboarding` salían **negros aunque el abogado eligiera claro**, mientras el resto de la app
sí era clara. Era la queja #1 de Pipe. Ahora usa `bg-background` + tokens del tema, y la
viñeta negra fija pasó a la utilidad `bg-vignette-welcome` con variante por tema.
Verificado con capturas de Playwright en claro y oscuro.

## ⚠️ Estado y lo que NO está verificado (no reportar como cerrado)

| Cosa | Estado |
|---|---|
| Puente `mia-shell` de Protección | Capa 1 OK (`cargo check` + `tsc` limpios). **Capa 3 PENDIENTE**: hay que reconstruir el instalador y probar los botones en la app empaquetada. Ver «Cómo verificar» abajo |
| `RuntimeHealthBanner` | **Sigue roto** por la misma causa (usa `__TAURI__.event.listen`). Migrarlo al puente `mia-shell`. Tarea abierta |
| Prueba en frío en máquina limpia | No se hizo: no hay una máquina virgen disponible. Se hizo lo más cercano posible (primer arranque sobre `%LOCALAPPDATA%` temporal limpio) |
| Firma del instalador | Sin firmar. Windows lo marca como "publicador desconocido". Funciona igual. Pipe debe registrar Azure Trusted Signing cuando quiera quitar el aviso |
| `console=True` en los dos `.spec` | Se dejó en `True` **a propósito y está documentado**: la cáscara Tauri lanza los hijos con `CREATE_NO_WINDOW` (`lib.rs:36`, ~15 puntos de spawn), así que el abogado no ve consolas. Solo se vería si alguien hace doble clic directo en `mia-backend.exe` |
| Los 22 puntos de UX restantes | Sin empezar. Ver la bitácora |

## ⚠️ Corrección importante sobre el diseño canónico

En esta sesión **describí mal** `frontend_design_spec.md` (lo llamé "dorado/cristal de lujo"),
Pipe eligió esa opción sobre esa premisa falsa, y luego lo detectó: *"no, ese no es el diseño
que habíamos establecido. Además era claro"*.

- **El canónico es** "MIA Onboarding Unificado": **Neumorfismo Pro, paleta Teal / Azul
  Oxígeno, tema CLARO y oscuro** (`CLAUDE.md` §I), que es lo **ya implementado** en
  `globals.css` (commit `f52c945`, hecho con Antigravity). **NADA dorado.**
- El commit de diseño más reciente (`ef3ed33`, "paleta monocromática negro/platino/cristal
  + isotipo octaedro 3D") **solo modificó `BrandMark.tsx`** — el logo. Nunca tocó pantallas.
  Por eso Pipe recordaba un diseño que no veía aplicado: **no se aplicó**.
- Las imágenes de referencia de Antigravity (`mia_onboarding_unified_*.jpg`) **no están en el
  repo ni en el disco**. **Pipe las tiene en otro computador y las va a traer** — cotejar el
  diseño contra ellas antes de rediseñar pantallas a gran escala.
- **Lección de proceso:** cuando la decisión es visual, el insumo debe ser visual (capturas de
  la app corriendo), no mi lectura de un `.md`. Registrada en la bitácora §4.

## Cómo continuar (sesión siguiente)

1. **Leer `memory/bitacora-feedback-ux-2026-08-19.md` completo.** Trae los 23 puntos con
   archivo, línea y causa raíz — no hace falta re-explorar el código.
2. **Esperar/pedir las imágenes de Antigravity** antes de rediseñar pantallas. Sin ellas, el
   trabajo de diseño es adivinar (ya pasó una vez en esta sesión).
3. **Verificar el puente de Protección** (capa 3) reconstruyendo el instalador — ver abajo.
4. **Migrar `RuntimeHealthBanner`** al puente `mia-shell` (misma causa raíz, tarea abierta).
5. Atacar los puntos de la bitácora. Sugerencia de orden por dependencia: primero lo que no
   depende del diseño visual (D3 Casos, D4 motor único, D7 atajos, D8 capacidades de agente,
   D9/D10 y los arreglos de copy del onboarding #7/#8/#12), y dejar para después lo puramente
   visual (#16 dashboard, #17 Configuración, #21 Conocimiento, sidebar de D2) hasta tener las
   imágenes de referencia.

## Cómo reconstruir el instalador y verificar Protección

```powershell
cd "<ruta-del-repo>\mia"
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

El script exige **checkout limpio** (rechaza el release si hay cambios sin commitear) y
reconstruye los 3 payloads + el bundle NSIS. Tarda ~25-40 min. Con `-SkipPayloads` reusa
`packaging/dist/` existente, pero **solo funciona si esos payloads se construyeron desde un
checkout limpio** (si no, aborta: "payload construido desde fuentes sucias").

Luego, en la app instalada: **Configuración → Protección**. "Guardar llave" debe reportar la
llave escrita en `Documentos\Llave-de-recuperacion-Mia.txt`; "Ya la guardé" limpia el aviso;
"Crear copia ahora" reporta copia verificada; "Recuperar…" lista los `.mia-backup`.
**Re-chequeo de seguridad obligatorio** desde DevTools de esa ventana: `window.__TAURI__ === undefined`
debe seguir siendo `true`, y un `fetch("http://mia-shell.localhost/maintenance/status", {method:"POST"})`
desde **cualquier otro origen** (una pestaña normal de Chrome) debe fallar.

## Trampas del entorno (le costaron horas a esta sesión)

- **Ruta del proyecto:** `CLAUDE.md` §A y §G y `desktop/orchestration.json` todavía dicen
  `D:\Inteligencia Artificial\Mia-Super Agent\mia`. **Esa carpeta ya no existe.** En este equipo
  el repo estaba en `D:\Codex\Mia-Super Agent\mia`. Al clonar en el equipo nuevo, la ruta será
  otra vez distinta: **corregir esas referencias** (o mejor, hacerlas relativas).
- **Binarios portables NO están en el repo** (correctamente, por peso) y hay que
  reprovisionarlos en cada equipo antes de poder construir el instalador:
  - **Node portable** v22.23.1 (versión fijada en `packaging/node-version.txt`).
  - **PostgreSQL 16 portable** (binarios de EDB, ~300 MB comprimido) **+ pgvector 0.8.0
    compilado contra él** (`nmake /F Makefile.win` con las Build Tools de VS, `PGROOT` apuntando
    al pgsql portable). Sin `lib\vector.dll` el build del instalador **aborta en duro**.
  - Ambos vivían en `<workspace>\tools\` (fuera de `mia\`).
- **Rust/Tauri:** hace falta el toolchain de Rust (`rustup`) + VS Build Tools. `desktop/README.md`
  los daba por instalados; en este equipo no estaban. `npm install` en `desktop/` instala
  `@tauri-apps/cli`. Tauri descarga NSIS solo en el primer `tauri build`.
- **Smart App Control de Windows** bloquea los `.exe` recién compilados sin firma
  (*"bloqueado por la directiva de Device Guard"*), y el smoke post-build falla con eso. Pipe lo
  **desactivó manualmente** en este equipo (Seguridad de Windows → Control de aplicaciones y
  navegador → Smart App Control → Desactivado). **Es irreversible sin reinstalar Windows.**
  En el equipo nuevo puede volver a aparecer: la alternativa limpia es firmar los ejecutables.
- **Dependencias del frontend desactualizadas:** tras traer 252 commits, `build_frontend.ps1`
  falló con `error: unknown option '--webpack'` hasta correr `npm install` en `frontend/`.
- **`.claude/launch.json`** (para levantar el dev server desde el agente) está gitignorado —
  hay que recrearlo en el equipo nuevo. Contenido: `npm run dev` en `cwd: frontend`, puerto 3100.

---

# CIERRE — 2026-08-18 · Mapa al día + mock del swarm alineado a la firma real · EMPEZAR AQUÍ

## Resultado de esta sesión

`CLAUDE.md` ya describía el producto del 18 ago 2026; este HANDOFF no. Quedó alineado.
No se inventó servidor MCP. `Plan/Plan.md` vive en el workspace padre (fuera de
`mia-agent`) y no entra en este PR.

HEAD de trabajo: rama `feat/fase1-inc1-cleanup-scaffolding`. El mapa de abajo es el
contrato vigente — no reabrir «5 pantallas» ni «LiteLLM primero».

## Mapa vigente (18 ago 2026)

- **Packs fail-closed.** Un pack vacío o un handoff roto no finge cotejo verde: cero
  fuentes ≠ preflight OK. El recorte de drafts conserva la matriz. Migración
  `059_packs_handoff_cost_status.sql` (handoffs, fact-pack por hash, `cost_status`
  honesto: medido / estimado / no_medida). Gate: `execution/test_packs_preflight.py`.
- **HITL por hash + tesis one-shot.** Approve/edit exigen `draft_hash` del borrador
  actual (409 si cambió; 422 si falta huella o attest). Cambiar la matriz en revisión
  autoriza UNA pasada extra de redacción+verificador (`selection_redraft_used`), no
  el bucle automático draft↔gate.
- **Packet destilado.** El cruce recibe hash / pasaje / locator `[doc n]`, no el dump
  de investigación. Vive en `metadata.source_packet`.
- **MCP vacío honesto.** Sin servidores en `tenant_settings.config['mcp']['servers']`
  el despacho ve un dict vacío. Catálogo curado; `resolve_server` es fail-closed.
  No hay servidor MCP de producto que inventar para un test rojo.
- **CI verde (sin bajar gates).** SHA de migraciones sin psycopg; checkpointer en el
  job legal; JWT_SECRET ≥ 32 caracteres; stubs de Tauri; `verify.ps1` usa el Python
  de PATH (`MIA_VERIFY_PYTHON`) y no usa `WindowStyle` en Ubuntu; el catálogo quick
  corre junto a Postgres en Ubuntu; el blindaje BatBadBut del CLI se afirma solo en
  Windows. Commits 56631c8 → 7ef8709 sobre el cierre del 15.
- **Cron suggestions.** El job `generate_suggestions` alimenta
  `GET /api/automations/suggestions` (consent-first; el abogado acepta o descarta).
- **Telegram en el lifespan.** `start_bridge_if_configured()` arranca con la API si
  hay token. No es un proceso suelto obligatorio para que el producto viva.
- **Agent Hub.** Cinco conectores (investigación, documentos, automatización,
  escritorio, navegación). Solo `invocation_ready` si el binario está en PATH y
  `--help` confirma los flags. Si no, razón honesta — nunca `[VERIFICAR]` en el
  catálogo.
- **Router LLM.** `agent/llm.py` con política por defecto `quality_adaptive`.
  LiteLLM es proxy opcional de respaldo, no el camino primero del abogado.
- **Frontend.** No son «5 pantallas». Hay asunto, revisión HITL, memoria,
  configuración (conexiones, ayudantes, protección), automatizaciones, misiones y
  sala de estrategia. Login JWT. ~14 routers `/api`.

## Gate de esta sesión

`execution/test_research_swarm.py`: los mocks de `resolve_jurisdictions_for` y
`citation_patterns_for` tenían un solo argumento; el grafo llama
`(tenant_id, matter_id)` desde la sesión 58 y el fail-soft de `_turn_jurisdictions`
tragaba el `TypeError` (misma clase que el arreglo de `test_projects.py` el 15 ago,
regla 78). Firmas alineadas a las reales, incluido el stub de `resolve_jurisdictions`
del check de dedup. Suite 21/21 PASS. No se inventó servidor MCP: el gate vacío
bloquea y el turno sigue.

## Pendientes que deja esta sesión

Siguen abiertos los del 15 ago (no se tocaron):

- **P3**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev).
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o
  tramo rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- **API propia por instalación** (decisión de Pipe). Benchmark solo por decisión de
  negocio. Distribución sin prometer ≤335 MB.

PRIMERA TAREA del próximo arranque con entorno completo: la misma del 15 — E2E con
DB, `test_first_run.py` con salida capturada, y revisar en vivo las pantallas nuevas
si el entorno lo permite. No reabrir el mapa de producto.

---

# CIERRE — 2026-08-15 · E2E con DB verde, first_run capturado y pantallas revisadas en vivo

## Resultado de esta sesión (commits 12bf5e9 + cierre, pusheados)

Los tres puntos de la «primera tarea» del cierre anterior quedaron cerrados con evidencia:

1. **`test_first_run.py` VERDE 73/73 con salida capturada** (exit 0). Ya cuenta como gate.
2. **E2E con DB, todo verde**: test_rls 19/19 · test_e2e 59/59 · test_hitl_flow 21/21
   (el riesgo #86 queda re-verificado: la suite pasa con DB) · test_citation_seals 20/20 ·
   test_projects 61/61 · `verify.ps1 -Mode quick` VERDE 16 suites (14,3 s).
3. **Pantallas nuevas revisadas en vivo** (Playwright + `seed_despacho_demo.py`):
   /activar con «Calidad jurídica adaptativa» RECOMENDADO y el copy del plan Max en
   «Mi suscripción»; selector de motor en Conexiones con «Codex en este equipo (no
   disponible en este equipo)» deshabilitado con su razón; chips «Contexto jurídico
   [General]» pintando lo efectivo; tarjeta «Recuperar desde una copia» con su copy y el
   aviso de aplicación al reinicio. En dev /activar redirige a /onboarding
   (`instalado=false`, correcto); para verla se interceptó `/api/welcome/status`.

Dos defectos REALES corregidos en 12bf5e9:

- **El lanzador canónico de la API estaba roto en Windows**: en `backend/mia/api/run.py`
  una local `config = uvicorn.Config(...)` sombreaba el módulo `config` y
  `python -m mia.api.run` (el camino de `start_api.ps1`) moría con `UnboundLocalError`.
  Ningún gate lo ejecutaba. Pendiente: gate que lo arranque de verdad (regla 79).
- **8 checks rojos de test_projects que parecían regresión**: los 5 mocks de
  `resolve_jurisdictions_for` tenían la firma vieja de 1 argumento (la sesión 58 la
  amplió a `(tenant_id, matter_id)`); el fail-soft de `_turn_jurisdictions` tragaba el
  `TypeError` y degradaba a la rama restrictiva. Mocks actualizados (regla 78).

**Entorno reconstruido**: el `.env` eliminado el 2026-08-14 era la única copia de las
contraseñas del clúster portable 55432. Se resetearon (`trust` temporal en `pg_hba.conf`
con backup, restaurado a scram) las contraseñas de `postgres`/`mia_app`/`mia_curator` y
se regeneró el `.env` con las claves del semilla de `first_run.py` (regla 80). Las 56
migraciones se re-aplicaron idempotentes (3 fallos esperados: constraints viejos
superados por migraciones posteriores; los vigentes quedaron intactos).

## Pendientes que deja esta sesión

- **P3 nuevo**: aviso de hidratación en /configurar#conexiones — un `<div>` dentro de un
  `<p>` (badge «2 Issues» del overlay de Next dev). Ubicar y corregir.
- **Gate del lanzador**: ejecutar `python -m mia.api.run` hasta health 200 en CI o tramo
  rápido.
- **`scripts/setup_db.ps1`** revienta en PowerShell 5.1 (here-string con Python
  embebido); migrar ese bloque a un `.py`.
- El bloque grande sigue siendo el del cierre 2026-08-14: **API propia por instalación**
  (decisión de Pipe), benchmark solo por decisión de negocio, y distribución sin
  prometer ≤335 MB.

Retrospectivas: técnica en `docs/retrospectives/retrospective-2026-08-15-e2e-db-y-lanzador-api.md`;
de sesión en `Pipe-OS/01-operacion/retrospectivas/retrospective-2026-08-15-002-mia-e2e-db-first-run-pantallas.md`.
Reglas nuevas 78-81 en `APRENDIZAJES.md`.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---
