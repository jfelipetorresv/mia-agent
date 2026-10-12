# Banco 0.4 · Voto de adjudicación de cobertura de UN hecho

Decide si la respuesta de un asistente jurídico (diagnóstico y borrador, en segmentos) cubre UN
hecho material de la clave de respuesta:

- `expresa_correctamente`: lo expresa con el valor, la fecha, la parte y el sentido del enunciado.
  Una cifra, fecha o parte distinta es `false` aunque aparezca el marcador literal del hecho.
- `atribuye_bien`: no lo asigna a otra pieza ni a otra parte.
- `cubierto` = `expresa_correctamente` Y `atribuye_bien`.

Decide tú solo. **Tu memoria jurídica nunca cuenta.** Responde SOLO con un JSON que cumpla este
esquema (`schema` = `banco04-voto-cobertura/v1.2`, `id_hecho` igual al recibido):

<<ESQUEMA>>

<MATERIAL_NO_CONFIABLE>
<<PAQUETE>>
</MATERIAL_NO_CONFIABLE>

<HECHO>
<<HECHO>>
</HECHO>
