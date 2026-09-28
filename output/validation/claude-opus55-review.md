# Revisión independiente Claude Code

Modelo confirmado: claude-opus-5-5. Esfuerzo solicitado: high. Solo lectura; sin ejecución de pruebas.

# Dictamen: NO APTO

No encontré ninguna aprobación falsa ni fuga entre despachos o usuarios. El NO APTO tiene dos causas. En el camino normal, un turno con fuentes de investigación típicas casi nunca llega a final, y la ruta de aprobación lo rechaza de entrada. Además, una prueba del catálogo de verificación queda en rojo por el cambio de contrato.

Todo lo que sigue lo obtuve leyendo el código. No ejecuté ninguna prueba ni ninguna reproducción. `test_legal_context.py` cambió mientras lo revisaba, así que evalúo su versión más reciente.

## Hallazgos

### ALTA 1: un turno normal casi nunca llega a final, y el botón de aprobar devuelve 409
*Comprobable por lectura. Falla en dirección segura: no aprueba de más, bloquea.*

Varias piezas se combinan:
- **Sin citas se toman todas las fuentes.** `gate_evidence.py:46` hace `return chosen if citations and chosen else sources, ...`. Pasa lo mismo si alguna cita no corresponde a exactamente una fuente de investigación (`:34-35`). Eso incluye las citas respaldadas por `[doc n]`, las selladas, las del mensaje del abogado y las ambiguas.
- **Las providencias nunca cuentan como cubiertas.** `research.py:279` las marca `evidence_kind: "derived_ratio"`, y `gate_evidence.py:66-68` las pone en `missing`. Con eso `complete=False` y el auditor queda `unavailable`. Aparte de eso, `legal_ledger.py:208-210` devuelve `False` para cualquier `jurisprudence`.
- **Sin fuentes tampoco hay final.** `valid_context` exige fuentes no vacías (`legal_ledger.py:59`) y `build` exige `entries` (`gate_evidence.py:82`). Un borrador sin fuentes ni documentos no puede llegar a final; antes `sin_citas` sí pasaba.
- **La aprobación se corta en la ruta.** `hitl.py:98-104` rechaza `approved` con 409 si `verification_passes` es falso. El abogado solo puede editar o rechazar, y al editar vuelve a quedar `unavailable`.
- **Presupuesto (riesgo, sin medir).** `research.py:260` mete como evidencia el `full_text` completo de hasta 6 normas. El propio `research.py:33-34` advierte que «el full_text de una ley es enorme». Es probable que se supere el presupuesto y el resultado sea `unavailable`.

**Reproducción:** llamar a `select_used("Texto sin citas.", [fuente_providencia], [])` y pasar el resultado a `build(..., budget_tokens=10**6)` da `complete=False`. Esa fuente sale tal cual de `gather_sources`, con `evidence_kind="derived_ratio"`.

**Arreglo mínimo:**
- Si no hay citas ni referencias literales, devolver `[]` como fuentes de investigación en lugar de todas.
- Si se decide que las providencias derivadas no acreditan, decirlo como límite visible, no bloquear sin explicación.
- Aceptar un contexto sin fuentes cuando el borrador no cita nada.
- Añadir una prueba integrada con las fuentes reales de `gather_sources`.

### ALTA 2: `test_modo_barreras.py` queda en rojo dentro del catálogo
*Comprobable por lectura.*

El archivo está en `config/verification.json:32`.
- `test_modo_barreras.py:70-74` espera `verification_passes({"marcadas":0,"gate_llm":{"veredicto":"apto"}}) is True`.
- `_clave_informe_no_bloquea` (`:158-161`) hace lo mismo.
- Con `legal_ledger.py:83-85` ahora se exigen `checker_version` y `evidence_coverage.complete`, así que esas dos comprobaciones dan `False` y lanzan `AssertionError`.

**Arreglo:** añadir `checker_version: "citation-verifier-v3"` y `evidence_coverage: {"complete": True}` a `ok_gate` y al informe de `:158`.

### MEDIA 3: si el auditor envuelve el JSON en un bloque de código, siempre sale «hallazgos»
*Comprobable por lectura.*

`gate_units.py:48-49` hace `json.loads(raw)` sin limpiar. El propio repositorio ya tolera respuestas envueltas en ```` ```json ```` en `curator.py:809` y `classify.py:59`. Un APTO correcto así envuelto se registra como `hallazgos` y borra `audited_units`, y el detalle que ve el abogado dice «APTO». `test_positive_textual_review` es un falso verde porque usa JSON sin envoltura.

**Arreglo:** extraer el primer objeto JSON (quitando el bloque de código) antes de `json.loads`, y añadir una prueba con la respuesta envuelta.

### MEDIA 4: aviso falso de «pasaje no coincide» en normas con resumen, y exclusión en modo exigir
*Comprobable por lectura.*

- En `research.py:255-260`, `pasaje` sale de `summary` y `content` sale de `full_text`.
- `revisar_fuentes` (`barreras_harness.py:515-529`) compara esos dos campos.
- Un resumen parafraseado tiene poca similitud con el texto de la ley, así que sale el aviso «no corresponde a la norma que dice citar».
- Antes no existía `content`, así que la norma quedaba como «no verificable».
- Con `MIA_FUENTE_IDENTIFICACION_EXIGIR`, `filtrar_fuentes` retira la norma: se pierde información.

**Arreglo:** para normas, usar como `pasaje` un recorte de `full_text` y mandar el resumen a otro campo, o no cotejar un `derived_summary`.

### MEDIA 5: en el chat, un rechazo previo a la ejecución deja un pendiente falso
*Comprobable por lectura.*

Cuando el servidor rechaza antes de ejecutar (402 por presupuesto, 422 u otro 4xx previo a `_prepare_chat`), no queda ninguna reserva. Aun así, `page.tsx:415-418`:
- conserva el marcador,
- ya vació el input (`:359`),
- y muestra «no hace falta reenviar el mensaje», lo cual es falso.

Al pulsar «Comprobar envío» da 404 y el usuario tiene que descartar y volver a escribir.

**Reproducción:** agotar el presupuesto y enviar un mensaje.

**Arreglo:** en el `catch`, si es un `ApiError` con estado 401, 402 o 422, llamar a `clearPending(attempt.request_id)` y restaurar `input`. Mantener el marcador en 409, 502 y fallos de red.

### BAJA
- **6. Cobertura completa con anclas fuera de rango** (`gate_evidence.py:40-45`). Si el texto cita `[doc 5]` y solo hay 3 documentos, se toman todos y se declara la cobertura completa, aunque falta el material citado. Los adjuntos de `@expediente` también se numeran desde 1. Es un riesgo teórico.
  - **Arreglo:** si hay una referencia mayor que `len(documents)`, añadirla a `missing`.
- **7. Se pierde el motivo del límite de pasadas.** `TurnBudgetExceeded` ahora cae en el `except` genérico (`graph.py:2402`) y el mensaje dice «no disponible» en lugar del motivo real.
- **8. Pruebas que no prueban lo que dicen:**
  - `test_custom_citations_and_plural_doc_anchors_preserved` pasa aunque se devuelvan todas las fuentes, porque no incluye ninguna fuente sin usar.
  - La prueba integrada de `test_legal_context` solo recorre un fragmento (`chunk`) sin `research_sources`. Nunca ejercita normas, providencias ni la huella viva de `legal_norm`.
  - Las pruebas de chat fijan `state.user_id`, que el middleware nunca asigna; en producción el usuario se resuelve por email.
- **9. La prueba de chat puede tocar la base instalada.** Si `MIA_TEST_ENV_FILE` no está definido, `test_assistant_chat_requests.py` vuelve al `.env` del repositorio sin la guarda del puerto 55432.

## Lo que se sostiene
- **Aislamiento entre despachos y usuarios:**
  - `lookup_status` (`chat_requests.py:53-67`) filtra por despacho, usuario y dueño de la conversación, y no reserva, no toca el presupuesto ni actualiza el estado.
  - `list_messages` ahora filtra por usuario.
  - `validated_latest_final` pasa por el aislamiento por despacho de la base de datos (RLS).
  - La herencia de unidades incluye despacho y asunto.
- **Libro de registro:**
  - Los recibos se vinculan a ejecución, contexto y versión del verificador.
  - Un recibo de otra ejecución no habilita el final.
  - El contexto se valida contra el estado vivo.
  - La migración 067 es compatible con `ON CONFLICT DO NOTHING` sin destino.
  - La huella del fragmento se calcula antes del recorte (`setdefault`).
- **Incremental:** es conservador. Reordenar, borrar, encabezados, párrafos cortos, alcance global o cambios de evidencia obligan a revisión completa.

## Límites
- Solo leí el código. No ejecuté pruebas, compilación ni navegador, y no doy ningún test por aprobado.
- No leí `.env`, bases de datos ni expedientes. Tampoco medí el presupuesto real de `verificador_citas`.
- Los cambios en `barreras_harness.py` son código de Mia. No vi cambios fuera del repositorio.
- No evalúo la calidad jurídica de un modelo real.