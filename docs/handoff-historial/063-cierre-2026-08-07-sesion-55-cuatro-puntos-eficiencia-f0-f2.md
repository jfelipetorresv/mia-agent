# CIERRE — 2026-08-07 (sesión 55) · Los 4 puntos de la 54 + plan de eficiencia F0-F2 ejecutado

> **CONTINUACIÓN MISMA SESIÓN (tarde/noche)**: Pipe aprobó el plan de eficiencia
> (`specs/todo/PLAN-principios-harness-llos-eficiencia.md`, principios destilados de su
> harness LLOS — solo principios, nada de código/marca) y se ejecutaron F0+F1+F2:
> medición por nodo (migración 048, gate test_uso_por_nodo), gate de citas en UNA pasada
> sin reescritura + cosecha en background como propuesta (migración 049) + caches
> (test_embed_cache), y el SELLO de verificación incremental (migración 050,
> test_citation_seals 14/14; quemada gana, quemar revoca). **Medido contra baseline:
> −47 % tokens y −55 % latencia (20 → 8,9 min) con 0-sin-respaldo intacto** —
> `validation/baseline-f0-por-nodo.md` tiene las 4 tablas y los residuos anotados
> (KPI de sellos en panel, F1.2b extractos por rol, caché de ficha, F3-F4 del plan).
> Commits `74067ec` → `9d077e7`+cierre, pusheados. El backend corriendo en la máquina
> quedó ANTERIOR a estos cambios: reiniciarlo antes de mirar pantallas.

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para MIRAR pantallas: `execution\seed_despacho_demo.py`
> (`--borrar` al terminar; OJO: `test_seed_despacho_demo.py` BORRA el despacho demo al
> limpiar — re-sembrar después). Para el E2E: 4 servicios arriba y
> `node e2e\recorrido_primera_vez.mjs --corrida N` (~23-30 min).

Rama `feat/fase1-inc1-cleanup-scaffolding`. Repo limpio tras este cierre
(`585f332` → este commit). Entre la 54 y esta sesión, Pipe hizo además 8 commits de diseño
(`d297b2a` → `1be4af5`: sistema neumórfico, logotipo octaedro 3D) — SON DE PIPE y se quedan;
entraron a la revisión técnica de abajo.

## Qué pasó en esta sesión (2026-08-07, 55ª) — los 4 puntos de «Qué sigue» de la 54

1. **DEFECTO UI-A CERRADO (`585f332`)**: la fila de acciones del asunto no envolvía
   (`flex` sin wrap) y con 5 botones desbordaba bajo el aside de 300px, que interceptaba el
   clic. `flex-wrap + min-w-0`: los botones pasan a segunda línea. Verificado por mutación
   (con el código viejo la fila invade el aside: 1183px > 1140px) y EN VIVO a 1440×900 y
   1280×800. En la corrida 4 el clic real tomó 1,0 s sin aviso.
2. **Revisión técnica de los commits de Pipe — encontró 2 BLOQUEANTES en `f264b1e` y los
   cerró (`2e899bf`)**: el commit de principios Lexia renombró el nodo de verificación a un
   gate LLM (`verificador_citas`) y con ello DESCONECTÓ el muro determinista (`_verify_draft`:
   citas quemadas, [VERIFICAR], afirmaciones negativas, contaminación, alcance) — el borrador
   llegaba a revisión sin `md["verification"]` — y dejó el SSE `draft_ready` buscando el nodo
   viejo. El gate LLM SE QUEDA (decisión de Pipe); el muro corre ahora sobre su salida.
   Evidencia: test_seed 12/17→17/17, test_e2e 57/58→58/58. Los menores quedaron anotados en
   `memory/bugs-and-risks.md` (BrandMark con props muertas, contraste WCAG sin re-medir,
   harvest sin frase de progreso) + un watch-out de producto: el gate LLM gasta un turno de
   modelo extra por borrador — decisión de Pipe si lo quiere además del muro.
3. **Checklist de honestidad de UI FIRMADO (`f7316ad`)**: auditor independiente, por paso del
   recorrido — `validation/checklist-honestidad-ui.md`. 11 PASA / 1 FALLA / 3 AVISO. La FALLA
   (botones «Conectar» correo visibles sin app OAuth registrada) se corrigió en `c6173e5`
   (`/api/mailbox/status` expone `disponible`; la UI muestra el aviso honesto) y se verificó
   EN VIVO en /configurar → Conexiones.
4. **Corrida 4 del E2E: VERDE en 22,8 min** (turno 20,7 min; approve 91,5 s; `## aprendido`
   poblado). El E2E ya NO rodea el UI-A: el clic real es la aserción. Bitácora en
   `validation/validation-log.md`.

**Además**: migración `047_citas_quemadas.sql` estaba aplicable pero fuera de la DB dev
(health decía 44/45) — aplicada con `init_citas_quemadas.py` y registrada en el ledger con el
MISMO sha que calcula `db_bootstrap.migration_sha256`; health 45/45.

**Gates re-corridos hoy, todos verdes**: rls 19/19 · gates_no_ciegos 9/9 · env_pins 12/12 ·
e2e 58/58 · seed 17/17 · sentence_report 47/47 · citas_quemadas 20/20 · migration_ledger PASS
· tsc 0 errores.

## Qué sigue (en orden, sin necesitar a Pipe)

1. **Lentitud señalable (abierta desde la 54)**: el motor de suscripción agota su timeout
   (~13 min) con el caso voluminoso y salta a claude-sonnet (turnos 20-28 min); y
   `POST /draft/approve` corre el cierre del grafo SINCRÓNICO (~90 s con la pantalla en
   «aprobando»). Atacar el approve asíncrono primero: es la espera que el abogado SIENTE.
2. Producto (plan maestro): lo que quede de F4 (seguridad pre-cliente) — F3 queda con su
   salida medible completa (3+1 corridas verdes, checklist firmado, `## aprendido`).
3. Los AVISO del checklist de honestidad (auditoría fina del onboarding paso a paso).

## Pendientes de Pipe (sin cambios desde la 53, + 1 nuevo)

- Prueba del instalador en máquina limpia (el instalador NO se ha re-ensamblado desde la 52;
  los arreglos de esta sesión tampoco están dentro).
- Lectura de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- Azure Trusted Signing y registro de apps OAuth (`docs/tramites-terceros-pipe.md`).
- Decidir sobre el alcance (leer más cuesta crédito de tarjeta).
- **NUEVO**: decidir sobre el gate LLM de citas de `f264b1e` (ver watch-out en
  `memory/bugs-and-risks.md`): ¿solo el muro determinista, o muro + gate LLM como hoy?

## 2026-08-14 · MIA robustecida (pendiente validación DB/VM)

- Jurisdicción por asunto con precedencia asunto → firma u organización → general; el
  asunto expone chips editables y el grafo los usa en investigación y citas.
- Ledger jurídico hash-bound: recibos históricos, verificador vigente, atestación humana,
  sellos ligados a pasaje/jurisdicción y exportación final registrada. Migraciones 051–057.
- Aprendizaje en cuatro jobs durables e idempotentes; las caídas se reintentan sin duplicar
  memoria ni repetir inferencias ya persistidas.
- Política `quality_adaptive`: Opus/xhigh para trabajo jurídico complejo y Max solo por gate
  excepcional; auxiliares ligeros. La UI reporta disponibilidad/fallback con honestidad.
- AnyDoc conserva estructura con límites de tamaño/ZIP, firma y MIME, timeout aislado. El
  benchmark sintético prueba el mecanismo (87,5 % menos contexto, recall 100 %), no la meta.
- `verify.ps1 -Suite quick`: 13 suites verdes; frontend lint/tsc/build verde. Pendientes para
  afirmar release/meta: PostgreSQL real, E2E completo, benchmark ciego con expedientes reales
  anonimizados y prueba de instalador en VM Windows limpia.
