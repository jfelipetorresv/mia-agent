## Checkpoint anterior: CP-V2 — Auto-diagnóstico prescriptivo (2026-07-02)

### Qué cambió (lenguaje simple)

- La consolidación semanal de Mia ahora produce un DIAGNÓSTICO con hasta 4
  recomendaciones concretas para el despacho ("Ha corregido 6 veces respuestas
  del mismo tipo — suba su guía de trabajo y desaparecen"), cada una con
  evidencia real contada de la actividad (nunca inventada: con menos de 5
  eventos de señal, Mia calla), impacto en dólares según la tarifa del
  despacho, y puntaje que las ordena.
- Lo que el abogado acepta o descarta NO se le vuelve a mostrar, salvo que el
  problema siga vivo pasados 30 días (entonces vuelve marcado como recurrente).
- El reporte semanal menciona cuántas recomendaciones hay y la principal.

### Frontend a construir (Cursor — capa 3): tarjetas de diagnóstico en el panel

- **`GET /api/dreams/prescriptions`** → `{prescriptions: [...]}` ordenadas por
  impacto (máx. 4). Campos por tarjeta: `id`, `category` (retrabajo | rechazos |
  conocimiento | costo | guias | valor), `headline` (título en llano),
  `prescription` (la receta, 3-4 frases), `evidence` (lista de 3 pruebas con
  números reales), `dollar_impact` (USD/mes o null), `time_impact_mins` (o
  null), `status` (`new` | `recurring`), `age_days`.
- **`POST /api/dreams/prescriptions/{id}/decision`** con body
  `{"action": "accept"}` o `{"action": "dismiss"}` → la tarjeta desaparece.
  404 si ya fue decidida (refrescar la lista).
- Sugerencia de UI: sección "Recomendaciones de Mia" en el Panel de control
  (encima o junto a "Valor entregado"); tarjeta con headline + impacto,
  evidencia expandible, botones "Lo haré" (accept) y "Descartar" (dismiss).
  `recurring` con `age_days` alto merece un matiz visual ("lleva N días").
- Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más
  actividad para hablar con evidencia."
- OJO: las tarjetas reflejan la última consolidación semanal (no tiempo real).

### Resultado de verificación (3 capas)

- Capa 1: gate `test_dreams.py` extendido 16 → **43/43**; regresión completa
  **50/50 suites × 3 corridas** (test_rls 12/12 HALT); migración 022 aplicada
  e idempotente.
- Capa 2 (revisor adversarial independiente): APROBAR tras re-verificación —
  los 4 MAYORES corregidos antes del commit: (H1) una decisión del abogado
  tomada mientras corría el cron semanal podía perderse → el guardado ya nunca
  resetea una fila decidida (solo el resurgimiento explícito a los 30 días);
  (H2) la poda borraba la edad de problemas vivos que solo salieron del top
  por diversidad → ahora se conserva toda señal viva y el panel filtra;
  (H3/H4) la recomendación de costo v1 era imposible de ejecutar (proponía
  mover tareas que YA corren en el modelo económico, hacia una pantalla sin
  ese control) → rediseñada al gasto real pagado + el selector "Motor de IA"
  del Panel de control, verificado que existe y guarda. Menores H5-H7 y
  residuales R1/R2 también cerrados (Riesgo #44).
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-V2).

---

