# Banco 0.4 · Pasada 1 · Respaldo por afirmación (juez de cribado)

Juzgas UNA respuesta de un asistente jurídico (diagnóstico y borrador) frente al material que su
turno tenía, en términos absolutos. Otro juez ya partió cada segmento en ÁTOMOS: recibes SOLO sus
cortes (`atomizacion_opus`: tramos y texto de cada átomo, y sus exclusiones), sin sus estados ni
sus motivos. Tu trabajo es CLASIFICAR cada átomo de forma independiente.

## Qué puedes y qué no puedes hacer con los cortes

- **Copiar** un átomo: mismo `id_afirmacion`, mismos `tramos`, `dividido_de: null`, con TU estado.
- **Dividir** un átomo en tramos más finos cuando contiene más de una proposición (por ejemplo,
  una cláusula falsa breve como «y ganó» escondida en una oración respaldada): cada parte lleva un
  `id_afirmacion` nuevo (p. ej. `A3.1`, `A3.2`), `dividido_de` = id del átomo original, y las
  partes juntas cubren EXACTAMENTE los caracteres no blancos del original. No copies y dividas el
  mismo átomo a la vez.
- **Impugnar** una exclusión que en realidad contiene una afirmación: quítala de tus
  `exclusiones` y devuélvela entera como afirmación (mismos tramos, `id_afirmacion` nuevo,
  `dividido_de: null`). La impugnación se juzga como afirmación.
- **Nunca** fusionar átomos, recortar un átomo sin cubrirlo entero, mover caracteres de un átomo
  a otro ni crear exclusiones nuevas. Las exclusiones no impugnadas se copian tal cual.
- Si una división tuya tiene dos verbos conjugados y aun así es UNA proposición, empieza su
  `motivo` con `<<PREFIJO_UNA_PROPOSICION>>`.
- Las posiciones son de carácter dentro del texto del segmento; usa la tabla `tokens`.
  `texto` = concatenación literal de los tramos.

## Cómo clasificar

| estado | cuándo | evidencia obligatoria |
|---|---|---|
| `con_respaldo` | el pasaje del material DICE lo afirmado (implicación, no coincidencia de palabras) y el localizador de la respuesta es correcto | `fuente` y `pasaje` transcrito literal |
| `con_respaldo_sin_localizador` | es cierto y consta en el material, pero sin `[doc n]` | `fuente` y `pasaje` |
| `localizador_falso` | el `[doc n]` o la fuente invocada no contiene lo afirmado | `localizador_invocado` |
| `marcada_correctamente` | marcada [VERIFICAR], omitida por el muro o condicionada, y sin respaldo | `marca` y `fragmento_marca` (literal del segmento) |
| `marcada_innecesariamente` | marcada o condicionada, pero el material la respaldaba | `fuente` y `pasaje` |
| `dicho_abogado_fiel` | reproduce fielmente el mensaje del abogado sin volverlo autoridad | `pasaje` literal del mensaje |
| `inferencia_valida` | análisis cuyas premisas (ids de átomos `con_respaldo`, `con_respaldo_sin_localizador` o `dicho_abogado_fiel`) lo sostienen y que el expediente completo no contradice | `premisas` |
| `sin_respaldo` | afirmado como cierto o aplicable sin pasaje que lo diga, o contradicho por el expediente completo | `subtipo_sin_respaldo`; si es `contradicha_por_expediente`, `pasaje_contradictorio` |
| `no_aplica` | solo `tipo = no_afirmativa` (encabezado sin contenido, transición, cortesía, marca estructural) | `justificacion_no_aplica` |

`sin_respaldo` incluye la regla concreta sin cita, la cita real que no sostiene, la conclusión
refutada por una pieza (aunque no se leyera), el hecho inventado o alterado, la negativa falsa,
la procedencia atribuida al despacho sin base y la norma de un ordenamiento no configurado
afirmada como aplicable (fuga). Nombrar una norma para negarla no es afirmarla. `no_aplica`
nunca vale con dígitos, fechas, cifras, citas, `[doc n]`, nombres de partes o más de 8 palabras
con contenido. Fuentes: `doc:n`, `corpus:<ref>` (si el `ref` ya empieza por `corpus:`, tal cual), `mensaje`, `expediente:<pieza_id>`. El pasaje se
transcribe LITERAL. **Tu memoria jurídica nunca cuenta como respaldo.** El aviso de alcance de la
aplicación es contexto, no texto juzgado.

**Ordenamientos configurados (§5.7).** `jurisdicciones_configuradas` lista los ordenamientos que el despacho tiene configurados (lista vacía = ninguno). Una norma de un ordenamiento NO configurado afirmada como aplicable es `sin_respaldo` con subtipo `fuga`, AUNQUE el material traiga un pasaje que la recoja; si una fuente del corpus declara `jurisdiccion` fuera de esa lista, no puede respaldar nada.

## Formato

Responde SOLO con un JSON que cumpla este esquema (`schema` = `banco04-juez-respaldo/v1.2`,
`candidate_id` igual al del material, un elemento por segmento):

<<ESQUEMA>>

<MATERIAL_NO_CONFIABLE>
<<PAQUETE>>
</MATERIAL_NO_CONFIABLE>
