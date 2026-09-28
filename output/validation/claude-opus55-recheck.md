# Reverificación independiente Claude Code

Modelo: claude-opus-5-5; esfuerzo solicitado high.

# Reverificación de Claude Code (Opus 5.5, esfuerzo high, solo lectura)

## Dictamen: NO APTO

Ninguna aprobación esquiva al auditor ni la atestación humana. Aun así, tres de las garantías que Astra describió no se cumplen en todos los casos: dependen de que el auditor LLM se comporte bien, cuando podrían hacerse cumplir con reglas deterministas. Las tres correcciones son pequeñas. Todo lo que sigue sale de leer el código; no ejecuté nada.

## Hallazgos restantes

### MEDIA 1: una cita sellada del expediente apunta a un `[doc n]` de otro turno y la cobertura sale completa sin serlo
*Bug comprobable por lectura.*
- El sello guarda como referencia el `[doc n]` del turno en que se selló (`verification.py:1278-1283` y `citation_seals.py:143-155`).
- `list_compatible_seals` lo reutiliza si el contenido del documento sigue presente, esté en la posición que esté (`citation_seals.py:84-122`).
- Al usarlo, `annotate_draft` pone en `fuente` solo tipo, referencia y título, sin la huella (`verification.py:1263-1265`).
- `select_used` acepta ese índice viejo como si fuera del turno actual (`gate_evidence.py:44-48`).

**Reproducción:** sellar una cita respaldada por `[doc 3]`. En el turno siguiente el mismo documento se recupera en la posición 1, y en la 3 queda otro documento. El borrador repite la cita sellada sin ancla. `select_used` elige el doc 3, que es el equivocado. `build` devuelve `complete=True` y el auditor nunca ve el original de esa cita.

**Arreglo:** si una cita sellada viene del expediente, localizar el documento por su huella de pasaje, o tratarla como ambigua y mandar todos los documentos.

### MEDIA 2: el contexto final solo incluye lo que el auditor declara, así que una fuente citada puede cambiar sin invalidar el final
*La omisión la dispara el LLM, pero falta la regla en el código.*
- La selección se forma solo con `used_ids`, es decir, con las dependencias que declara el auditor (`graph.py:2406` y `2422-2426`).
- Nada obliga a incluir las fuentes y documentos que el texto cita explícitamente (el `chosen` y las referencias de `select_used`).

**Reproducción:** el texto dice «Conforme a la Ley 1 de 2020 [doc 1]…» y el auditor responde APTO con dependencias solo en `["[doc 1]"]`. `make_context` deja fuera la norma. Si después cambia `full_text` en `legal_norms`, `validated_latest_final` sigue devolviendo el final. Eso contradice la matriz: una fuente usada que cambia o se borra no debe habilitar el final.

**Arreglo:** exigir que las citas explícitas estén dentro de `used_ids` (y rechazar si no), o sumarlas a la selección de forma determinista.

### MEDIA 3: si hay una cita inequívoca, el inventario derivado se descarta sin que el auditor dé motivo
*Comprobable por lectura; no interviene el LLM.*
- `select_used` devuelve solo `chosen` cuando hay citas (`gate_evidence.py:64`). Las providencias no citadas desaparecen del inventario y `exclusion_candidates` queda vacío.
- El motivo explícito solo se exige cuando no hay citas o cuando alguna es ambigua.
- `test_gate_evidence.py:61-68` fija ese comportamiento como correcto.

**Reproducción:** texto «Conforme a la Ley 1 de 2020, procede. La jurisprudencia reiterada lo admite.», con una norma primaria y una providencia derivada, y la Ley 1 respaldada en el informe. Resultado: `([ley1], [])`, sin candidatos a exclusión. Sin la cita de la Ley, la misma providencia sí exige motivo.

**Arreglo:** mantener los derivados no citados como `exclusion_candidates` aunque haya citas. Si la política de verdad es que basta una cita inequívoca para excluir el resto, hay que escribirlo así.

### BAJA
- **4. El aviso de exclusiones sustituye al aviso de `revisar_fuentes`** (`graph.py:2434-2436`). La pantalla solo muestra `fuentes.aviso` (`CitationReview.tsx:296` y `438`), así que se pierde, por ejemplo, «N fuentes no tienen original…». Las listas `pasaje_no_coincide` y `sin_identificacion` sí se siguen viendo.
  - **Arreglo:** concatenar los dos avisos.
- **5. Un texto ya auditado puede quedar bloqueado para siempre (falla en dirección segura).**
  - El `pop` de la selección ocurre al entrar (`graph.py:2341`). Las salidas por evidencia incompleta, por presupuesto o por excepción conservan `audited_units` (`:2351-2355` y `:2441-2446`).
  - Si luego se vuelve a auditar el mismo texto con el mismo manifiesto, `pending` queda vacío y la selección previa ya no existe. Resultado: «La selección auditada previa no tiene huella vigente», sin llamar al auditor (`:2364-2370`).
  - Relacionado: el manifiesto no incluye `origin_hash`. Si cambian metadatos de una norma que no están en el manifiesto (por ejemplo `expiry_date`), las unidades se heredan, pero la huella vieja bloquea el final para siempre con ese texto.
  - **Arreglo:** si no hay selección previa, repetir la revisión completa.
- **6. Chat: queda un pendiente falso.** Si el token cambia antes del envío, `api.ts:246-248` lanza un 401 sin llamar a `onRejected`. El marcador sigue guardado bajo la identidad anterior y, al volver esa cuenta, aparece un pendiente que da 404. Falla en dirección segura.
- **7. El tramo `quick` en local queda rojo por construcción.**
  - `test_legal_context.py:15-16` llama a `load()` al importarse, y `test_assistant_chat_requests` exige `MIA_TEST_ENV_FILE`.
  - `verify.ps1` no comprueba ni avisa de esa variable, y `HANDOFF.md` no la menciona.
  - En CI pasa, porque `ci.yml` define `GITHUB_ACTIONS` y las variables `PG_*`.
- **8. Calidad de pruebas:**
  - El doble de SAT para providencias usa los campos `case_number` y `ratio`, que no existen (`test_legal_context.py:130`, `test_gate_evidence.py:21`). La providencia llega sin contenido, así que nunca se prueba una exclusión con una ratio realista.
  - Ninguna prueba cubre MEDIA 1, 2 ni 3.

## Estado de los hallazgos anteriores

| Anterior | Estado |
|---|---|
| ALTA 1: el turno normal no llega a final | **Cerrado**, por la decisión explícita y la selección H1. Límite: el presupuesto con `full_text` completo sigue sin medirse. |
| ALTA 2: fixtures del catálogo | **Cerrado** (`test_modo_barreras`, `test_p0`, `test_hitl_resume_state`). |
| MEDIA 3: JSON envuelto | **Cerrado.** Solo acepta ```` ```json\n…\n``` ````. Con `\r\n` o un bloque sin lenguaje sale «hallazgos», que va en dirección segura. |
| MEDIA 4: pasaje frente a resumen | **Cerrado.** El pasaje sale de `full_text` y `summary` va aparte. |
| MEDIA 5: 402 y 422 dejaban un pendiente falso | **Cerrado por lectura.** Los tres estados se lanzan antes de la reserva (`chat_requests.py:75-91`). El 401 **no lo doy por probado** hasta el informe del navegador. |
| BAJA 6: anclas fuera de rango | **Cerrado**, con prueba. |
| BAJA 7: motivo del presupuesto | **Cerrado** (`graph.py:2441`). |
| BAJA 8: pruebas débiles | **Cerrado.** Hay prueba integrada con `gather_sources` y una norma real en la base, las pruebas de chat resuelven el usuario por email y la mutación del número de norma bloquea la exportación. |
| BAJA 9: la prueba podía tocar la base instalada | **Cerrado** (`isolated_test_env.py`), con la salvedad del punto 7. |

## Lo que se sostiene

- **Ningún final se construye sobre una selección obsoleta.** Es una negación, pero sostenida por lectura con cuatro guardas independientes:
  1. el `pop` al entrar en la auditoría;
  2. `text_hash` en `reviewed_selection`;
  3. `verification_passes` de esa misma auditoría;
  4. la huella viva en `finalise_if_gated` y en `validated_latest_final`.

  `verificador_citas` va directo a `hitl_checkpoint` (`graph.py:3053`), así que el borrador no se reescribe entre medias.
- **Dependencias en derivados:** se rechazan, porque solo se aceptan localizadores con `available` (`gate_units.py:82`).
- **Derivados citados explícitamente:** van a `missing` y el auditor no llega a ser llamado.
- **Exclusiones:** exigen exactamente un motivo por candidato, sin duplicados.
- **Fuente primaria:** se exige al menos una dependencia en una fuente primaria (política autorizada).
- **Huella de las normas:** SAT y la base comparten columnas y tipos, así que las huellas coinciden.
- **Chat:**
  - el token se captura en el encabezado;
  - la sesión se invalida al cambiar de cuenta;
  - las respuestas que llegan tarde se descartan;
  - el marcador se borra después del efecto de escritura;
  - el marcador corrupto solo se descarta si el usuario lo pide.

## Riesgos propios del LLM (no son bugs)

- Que el auditor dé motivos de exclusión falsos o declare menos dependencias de las reales. El punto MEDIA 2 debe cerrarse de todos modos.
- La vigencia normativa externa: la fecha de derogación no viaja en el payload.

## Límites

- No ejecuté pruebas, compilación ni navegador.
- No leí la migración 067 en esta pasada.
- No medí el presupuesto real.
- Por la restricción de solo lectura, no dejé este informe en archivo.