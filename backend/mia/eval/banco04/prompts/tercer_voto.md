# Banco 0.4 · Voto de adjudicación sobre UNA afirmación

Clasifica UNA afirmación de la respuesta de un asistente jurídico frente al material de su turno.
Recibes la afirmación (`unidad.afirmacion`), su contexto inmediato (el segmento donde está y los
átomos de ese segmento, con sus ids) y el material completo. Decide tú solo, en términos
absolutos.

| estado | cuándo | evidencia obligatoria |
|---|---|---|
| `con_respaldo` | el pasaje del material DICE lo afirmado y el localizador de la respuesta es correcto | `fuente` y `pasaje` literal |
| `con_respaldo_sin_localizador` | es cierto y consta en el material, sin `[doc n]` | `fuente` y `pasaje` |
| `localizador_falso` | el `[doc n]` o la fuente invocada no contiene lo afirmado | `localizador_invocado` |
| `marcada_correctamente` | marcada [VERIFICAR], omitida por el muro o condicionada, y sin respaldo | `marca` y `fragmento_marca` (literal del segmento) |
| `marcada_innecesariamente` | marcada o condicionada, pero el material la respaldaba | `fuente` y `pasaje` |
| `dicho_abogado_fiel` | reproduce fielmente el mensaje del abogado | `pasaje` literal del mensaje |
| `inferencia_valida` | análisis cuyas premisas (ids de átomos del segmento con respaldo) lo sostienen y que el expediente completo no contradice | `premisas` |
| `sin_respaldo` | afirmado como cierto o aplicable sin pasaje que lo diga, o contradicho por el expediente completo | `subtipo_sin_respaldo`; si es `contradicha_por_expediente`, `pasaje_contradictorio` |
| `no_aplica` | solo para lo no afirmativo (encabezado sin contenido, transición, cortesía, marca estructural) | `justificacion_no_aplica` |

Fuentes: `doc:n`, `corpus:<ref>` (si el `ref` ya empieza por `corpus:`, tal cual), `mensaje`, `expediente:<pieza_id>`. El pasaje se transcribe
LITERAL. **Tu memoria jurídica nunca cuenta como respaldo.** Campos que no aplican: `null`.

**Ordenamientos configurados (§5.7).** `jurisdicciones_configuradas` lista los ordenamientos que el despacho tiene configurados (lista vacía = ninguno). Una norma de un ordenamiento NO configurado afirmada como aplicable es `sin_respaldo` con subtipo `fuga`, AUNQUE el material traiga un pasaje que la recoja; si una fuente del corpus declara `jurisdiccion` fuera de esa lista, no puede respaldar nada.

Responde SOLO con un JSON que cumpla este esquema (`schema` = `banco04-tercer-voto/v1.2`,
`id_unidad` igual al recibido):

<<ESQUEMA>>

<MATERIAL_NO_CONFIABLE>
<<MATERIAL>>
</MATERIAL_NO_CONFIABLE>

<UNIDAD_NO_CONFIABLE>
<<UNIDAD>>
</UNIDAD_NO_CONFIABLE>
