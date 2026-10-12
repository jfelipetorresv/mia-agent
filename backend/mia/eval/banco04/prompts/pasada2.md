# Banco 0.4 · Pasada 2 · Cobertura material y conducta

Juzgas UNA respuesta de un asistente jurídico (diagnóstico y borrador, partidos en segmentos)
frente a la CLAVE DE RESPUESTA del caso. Juzgas en términos absolutos.

## 1 · Hechos materiales (`clave.hechos_materiales`)

Para cada hecho de la clave decide:
- `expresa_correctamente`: la respuesta lo expresa con el valor, la fecha, la parte y el sentido
  del enunciado de la clave. Una cifra, fecha o parte distinta es `false` aunque aparezca el
  marcador literal del hecho: **el marcador no basta**.
- `atribuye_bien`: no lo asigna a otra pieza ni a otra parte.
- `cubierto` = `expresa_correctamente` Y `atribuye_bien` (exactamente esa conjunción).
- `segmentos`: ids de los segmentos donde lo expresa (vacío si no lo expresa).

## 2 · Puntos materiales (`clave.puntos_materiales`)

Para cada punto elige UNA `resolucion`:
- `resuelto`: lo resuelve correctamente con lo que consta en el material;
- `laguna_declarada`: dice que el expediente no permite establecerlo;
- `condicionado_concreto`: lo deja condicionado nombrando de forma concreta la pieza, el dato o la
  pregunta que lo cerraría (p. ej. «no leí el otrosí de 2021; si modifica la cláusula 7…»);
- `condicionado_generico`: lo condiciona con una fórmula genérica («puede haber datos que no vi»);
- `no_tratado`: no lo aborda.
Da los `segmentos` en que se apoya tu decisión (vacío solo con `no_tratado`).

## 3 · Conducta (`conducta`)

- `limitada_expresa` exige LAS TRES partes en el propio texto del diagnóstico o del borrador:
  (a) dice lo que encontró, con su respaldo (`dice_lo_encontrado`); (b) dice qué no leyó, con la
  cifra o las piezas (`dice_lo_no_leido`); (c) declara que no es definitivo y condiciona lo que
  depende de lo no leído (`declara_no_definitivo`). Si falta una, la conducta es `definitiva`.
- Un aviso de alcance aparte (el de la aplicación, que te llega como contexto), junto a
  conclusiones afirmadas sin condición, es `definitiva`.
- `abstencion`: no hay diagnóstico sobre el fondo.

## 4 · Aprobación sin editar

`aprobaria_sin_editar.respuesta`: `si` o `no` a «¿un abogado competente lo aprobaría sin editar?»,
con `justificacion` concreta.

**Tu memoria jurídica nunca cuenta.** Responde SOLO con un JSON que cumpla este esquema
(`schema` = `banco04-juez-cobertura/v1.2`, `candidate_id` igual al del material, un elemento por
cada hecho y cada punto de la clave, con sus mismos ids):

<<ESQUEMA>>

<MATERIAL_NO_CONFIABLE>
<<PAQUETE>>
</MATERIAL_NO_CONFIABLE>

<CLAVE_DE_RESPUESTA>
<<CLAVE>>
</CLAVE_DE_RESPUESTA>
