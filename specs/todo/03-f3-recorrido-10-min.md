# F3 — El recorrido de 10 minutos, en dev

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F3". La **rama honestidad-UX corre en PARALELO a F2** (sin dependencia del guardián); la
**rama recorrido corre TRAS F2** (necesita el guardián endurecido).

## Objetivo
Demostrar de punta a punta, cronometrado y con evidencia visual, que un abogado sin background
técnico completa el recorrido prometido en ≤10 minutos, y que la UI no promete nada que el producto
no tiene.

## Rama honestidad-UX (paralela a F2, sin dependencia del guardián)
- Renombrar Asunto/Proyecto según el diagnóstico existente (renombrar, NO fusionar); corregir la
  pantalla de proyectos que insinúa carpetas exclusivas.
- Ocultar visiblemente Gmail/Outlook/OneDrive hasta que exista OAuth (hoy: construidas y muertas =
  promesa rota en la UI).
- "Explicar mejor, no abrir" en modelos por agente.
- Verificar que NADA insinúe control de vencimientos procesales (riesgo #77: festivos/plazos
  incompletos y sin cablear — el producto no lo promete; esta rama confirma que la UI tampoco).

## Rama recorrido (tras F2)
- E2E automatizado con navegador (Playwright vía `.mcp.json` de este repo; scripts previos en el
  scratchpad `visual/tour.mjs` como referencia): `/register` → `/activar` → `/onboarding` (8 pasos)
  → subir expediente de muestra → pregunta → diagnóstico con anclas `[doc n]` visibles → borrador →
  aprobar → `## aprendido` poblado. Cronometrado wall-clock, screenshot por paso en
  `validation/screenshots/`.
- **Definición EXACTA de los 10 minutos** (corrección de Codex — sin esto las corridas no son
  comparables): expediente sintético FIJO y versionado (~300 páginas, calidad mixta), máquina y red
  anotadas, el reloj arranca al abrir MIA con los servicios ya arriba, INCLUYE subir e indexar el
  expediente, y termina cuando el borrador aprobado es visible. El arranque en frío de la máquina se
  mide aparte (métrica de F5/F6, no de este recorrido).
- Checklist "¿esto lo entiende un abogado?" por paso, con el copy alineado a profundidad-primero.
- Actualizar `architecture/e2e_runbook.md` para describir ESTE recorrido (hoy describe 19
  preguntas/puerto 3000; real: 8 pasos/puerto 3100 — deuda de documentación señalada en F0).

## Archivos críticos
`frontend/app/` (proyectos/conexiones/copy), `architecture/e2e_runbook.md`,
`validation/screenshots/`.

## Salida medible (copiada del plan maestro)
Recorrido verde ≤10 min, 3 corridas consecutivas sin intervención manual (salvo DB, documentado);
evidencia visual archivada; checklist de honestidad de UI firmada por agente auditor; el borrador
aprobado escribe `## aprendido`.

## Gates
HALT completo + `tsc` frontend 0 errores + E2E Playwright verde 3 veces consecutivas + checklist de
honestidad de UI firmado.

## Modelos (matriz del plan)
Ejecución dirigida (frontend, recorridos Playwright): Sonnet (medium; high si el frente incluye
diseño de gates), verifica Opus (high).
