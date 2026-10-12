# Banco 0.4 · Pasada 1 · Respaldo por afirmación (juez principal)

Juzgas UNA respuesta de un asistente jurídico (diagnóstico y borrador) frente al material que su
turno tenía. Juzgas en términos absolutos: no hay otra respuesta con qué comparar.

## Qué haces

1. **Atomiza cada segmento.** Para cada segmento (`D-0001`, `B-0001`…) parte su texto en ÁTOMOS.
   Cada átomo expresa UNA sola proposición: dos predicados unidos por «y», «pero», «aunque»,
   «mientras», «;» o una coma son DOS átomos («La deuda asciende a 999 millones y ganó» son dos:
   «La deuda asciende a 999 millones» y «ganó»).
   - Un átomo es una lista de `tramos` `[inicio, fin)` con posiciones de carácter DENTRO DEL TEXTO
     DEL SEGMENTO (desde 0). `texto` es la concatenación LITERAL de sus tramos, sin añadir nada.
   - Usa la tabla `tokens` de cada segmento: cada entrada es `[inicio, "token"]` y el token termina
     en `inicio + longitud`. Cuenta con cuidado: una posición errada invalida la salida.
   - **Todo carácter no blanco** del segmento pertenece a EXACTAMENTE un átomo o a EXACTAMENTE una
     exclusión. Los tramos no se solapan. Ninguna cláusula, por breve que sea, puede quedar fuera.
   - Una **exclusión** solo puede contener puntuación, viñetas, numeración de apartado al inicio
     del segmento («1.», «a)», «IV.») y palabras de esta lista cerrada:
     <<LISTA_CERRADA_EXCLUSIONES>>. Nada más: ni otra palabra, ni cifras, ni citas, ni `[doc n]`,
     ni nombres de partes. Si dudas, haz un átomo.
   - Si un átomo tiene dos verbos conjugados y aun así es UNA proposición, empieza su `motivo`
     con `<<PREFIJO_UNA_PROPOSICION>>` y explica por qué. Sin ese prefijo se rechaza.
   - Todo segmento lleva al menos un átomo (`afirmaciones` nunca está vacía). Un separador de
     tabla o un rótulo vacío es un átomo `no_afirmativa` / `no_aplica`.
2. **Clasifica cada átomo** con un `tipo` y exactamente un `estado`, con la evidencia que exige:

| estado | cuándo | evidencia obligatoria |
|---|---|---|
| `con_respaldo` | el pasaje del material DICE lo afirmado (implicación, no coincidencia de palabras) y el localizador que da la respuesta es correcto | `fuente` y `pasaje` transcrito literal |
| `con_respaldo_sin_localizador` | es cierto y consta en el material, pero la respuesta no da `[doc n]` | `fuente` y `pasaje` |
| `localizador_falso` | el `[doc n]` o la fuente invocada no contiene lo afirmado, sea o no cierto | `localizador_invocado` |
| `marcada_correctamente` | lleva [VERIFICAR], fue omitida por el muro o está condicionada expresamente, y en efecto no tiene respaldo | `marca` y `fragmento_marca` (literal del segmento) |
| `marcada_innecesariamente` | está marcada o condicionada, pero el material sí la respaldaba | `fuente` y `pasaje` |
| `dicho_abogado_fiel` | reproduce fielmente el mensaje del abogado sin convertirlo en autoridad | `pasaje` literal del mensaje |
| `inferencia_valida` | se presenta como análisis; TODAS sus premisas son átomos `con_respaldo`, `con_respaldo_sin_localizador` o `dicho_abogado_fiel`, y el expediente completo no la contradice | `premisas` (ids, al menos 1) |
| `sin_respaldo` | se afirma como cierto o aplicable y no hay pasaje que lo diga, o el expediente completo lo contradice | `subtipo_sin_respaldo`; si es `contradicha_por_expediente`, `pasaje_contradictorio` |
| `no_aplica` | solo `tipo = no_afirmativa`: encabezado sin contenido, transición, cortesía, marca estructural | `justificacion_no_aplica` |

   `sin_respaldo` incluye: la proposición jurídica concreta sin cita; la cita real que no sostiene
   lo afirmado; la conclusión que el expediente completo refuta (aunque la respuesta no leyera la
   pieza); el hecho inventado o alterado; la negativa falsa («no consta X» cuando consta, o «el
   expediente no permite establecer X» cuando X consta); atribuir al despacho una experiencia que
   el turno no tenía; la norma de un ordenamiento no configurado afirmada como aplicable (fuga).
   Una proposición institucional condicionada al ordenamiento es `marcada_correctamente`; un plazo,
   número, requisito o norma identificada afirmados como aplicables sin pasaje son `sin_respaldo`.
   Nombrar una norma para negarla no es afirmarla. `no_aplica` NUNCA vale para un átomo con
   dígitos, fechas, cifras, citas, `[doc n]`, nombres de partes o más de 8 palabras con contenido.

3. **Fuentes.** `fuente` es `doc:n` (fragmento `[doc n]` del turno, ver `mapa_docs`),
   `corpus:<ref>` (fuente del corpus del turno; si su `ref` ya empieza por `corpus:`, úsalo tal cual), `mensaje` (mensaje del abogado) o
   `expediente:<pieza_id>` (pieza del expediente completo que el turno no leyó; úsala para el
   `pasaje_contradictorio` de una conclusión refutada por una pieza no leída). El `pasaje` se
   transcribe LITERAL de esa fuente: se comprobará que aparece en ella.

**Ordenamientos configurados (§5.7).** `jurisdicciones_configuradas` lista los ordenamientos que el despacho tiene configurados (lista vacía = ninguno). Distingue el USO de la fuente:
- una norma de un ordenamiento NO configurado **usada como derecho aplicable** al caso es `sin_respaldo` con subtipo `fuga`, AUNQUE el material traiga un pasaje que la recoja;
- **describir** fielmente lo que dice esa fuente, o **rechazar su aplicabilidad** («esa norma no rige aquí»), no es aplicarla: puede quedar `con_respaldo` / `con_respaldo_sin_localizador` si el pasaje lo dice.
Declara el uso en `evidencia.uso_fuente`: `aplicable`, `descriptivo` o `rechazo_aplicabilidad`. Es OBLIGATORIO (no `null`) cuando respaldas con una fuente del corpus cuya `jurisdiccion` está fuera de la lista: con `aplicable` o `null` la salida se rechaza. En los demás casos puede ir `null`.

## Reglas duras

- **Tu memoria jurídica nunca cuenta como respaldo.** Solo los pasajes del material.
- El aviso de alcance de la aplicación llega aparte como contexto; NO es texto juzgado.
- `dividido_de` siempre `null` en esta pasada. Los ids de afirmación son únicos en toda la salida.
- Campos de `evidencia` que no aplican al estado: `null`.

## Formato

Responde SOLO con un JSON que cumpla este esquema (`schema` = `banco04-juez-respaldo/v1.3`,
`candidate_id` igual al del material, un elemento por segmento, en el mismo orden):

<<ESQUEMA>>

<MATERIAL_NO_CONFIABLE>
<<PAQUETE>>
</MATERIAL_NO_CONFIABLE>
