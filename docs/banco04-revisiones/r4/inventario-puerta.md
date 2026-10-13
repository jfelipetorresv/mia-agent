# Inventario de la puerta del veredicto · banco04 · HEAD f5d678b (feat/mia-04-hermes-legal)

Trabajo de solo lectura. Rutas relativas a `D:\Inteligencia Artificial\Mia-Super Agent\mia`.
Abreviaturas: `M` = `backend/mia/eval/banco04/metricas.py` · `J` = `backend/mia/eval/banco04/jueces.py` ·
`R` = `execution/run_banco04.py` · `VJ` = `execution/banco04_validar_jueces.py` ·
`SG` = `backend/mia/eval/spend_guard.py` · `H` = `backend/mia/eval/harness.py` ·
`PR` = `backend/mia/eval/banco04/protocolo.py` · `DOC` = `docs/banco-calidad-04-protocolo.md`.

Marcas: **[V]** verificado leyendo el código citado · **[I]** inferido del código (no ejecutado).
Tipo de entrada: **CRUDO** = dato observado (salida de corrida, voto de juez por unidad, registro
de llamada con tokens) · **CONCL** = conclusión o agregado (cumple, resultado, etiqueta, conteo,
suma, media, R decidido) · **PARÁM** = parámetro declarado por el llamador.

---

## 1 · ENTRADAS DE LA PUERTA

### 1.0 Hechos transversales

- `veredicto_global` (M:1147-1256) no recibe manifiesto, `sha`, `manifiesto_sha256` ni
  `hash_evaluador`: ninguna de sus entradas está ligada a I10 ni al evaluador congelado. [V]
- Nadie fuera de los tests llama a `veredicto_global`, `evaluar_absolutos`, `agregar_casos`,
  `agregar_estratos`, `techo_cuota`, `filas_comparativas_obligatorias`, `metricas_corrida`,
  `hechos_y_puntos_desde_clave` ni `adjudicar_negativas_falsas` (grep en `backend/` y
  `execution/` excluidos `test_*`). [V]
- La «recomputación» de comparativas y pérdidas (M:1185-1230) parte de `casos`/`casos_base`, que ya
  son AGREGADOS de `agregar_casos` (M:397-430), no corridas. [V]
- Precedencia: cualquier motivo ⇒ `no_certificable`; si no, cualquier roja ⇒ `reprueba` (M:1254). [V]

### 1.1 Parámetros de `veredicto_global` (M:1147-1151)

| Parámetro | Dónde se lee | Tipo | Ausente / vacío ⇒ | Se recalcularía desde |
|---|---|---|---|---|
| `inventario.parametros.ids_custodiados` | M:961-965 (vía `validar_inventario`, M:1163) | PARÁM | `inventario_sin_parametros` / `inventario_invalido` ⇒ NC (M:962, 969) | ids de `custodia.casos()` (R:1716-1718); no se persisten en ningún registro del runner [V] |
| `inventario.parametros.contingencia` | M:966 | PARÁM | default `False` (M:966) | `decision_r.json` campo `decision` (R:1105-1119) [I: la relación R reducida ↔ contingencia es inferida] |
| `inventario.parametros.extension` | M:967; M:1110; M:1216 | PARÁM | `{}` (M:939) ⇒ sin extensión exigida | no hay registro del runner que la produzca (ver §3 B9) |
| `inventario.{casos, filas_absolutas, comparativas, filas_extra}` | M:970-973 | CONCL (pero se exige igualdad con lo reconstruido) | distinto ⇒ NC | reconstruido desde `PR` (M:918-954) [V] |
| `casos` (0.4) y `casos_base` (0.3.3) | ver 1.2 | CONCL/AGREGADO | no Mapping ⇒ `sin_casos` (M:1123-1124); `casos_base` no Mapping se sustituye por `{}` (M:1170) | por caso: `agregar_casos` sobre las salidas de `metricas_corrida` de cada (caso, rep); éstas, desde los crudos de 1.6 |
| `semilla` | M:1189 (→ `bootstrap_casos`, M:556-567) | PARÁM | — (obligatorio) | `rep-NN.json` campo `semilla` (R:1035; valor `args.semilla`, default `"banco04"`, R:1969). NO está en el manifiesto (R:739-743) [V] |
| `absolutos` | ver 1.3 | CONCL | fila faltante ⇒ `falta_fila` (M:1173-1174) | `evaluar_absolutos` (M:472-538) sobre agregados + kappa + circuito |
| `comparativas` | ver 1.4 | CONCL (cotejada) + recibo de extensión CONCL (no recalculado) | faltante ⇒ `falta_comparativa` (M:1191-1193) | recálculo propio M:1188-1189 desde `casos`/`casos_base` |
| `techo` | ver 1.5 | CONCL | `resultado` ∉ {cumple, no_cumple, no_certificable} ⇒ `techo_ausente` (M:1241-1242) | `techo_cuota` (M:772-873) desde consumo por corrida y aprobación |
| `filas_extra` | ver 1.4 | CONCL (perdidas recalculadas; decisivos y atribución, no) | fila faltante ⇒ `falta_fila` (M:1219-1221) | ver 1.4 |
| `suspendido` | M:1250-1251 | CONCL (bool del llamador) | default `False` | existencia de `<salida>/<ver>/SUSPENDIDO.json` (R:652-653, 939-951) [I] |
| `salidas_sin_juzgar` | M:1252-1253 | CONCL (conteo del llamador) | default `0` | conteo de corridas `estado=completo` sin registro de juicio; no existen registros de juicio en disco (§3 B1) |
| `otros_motivos_no_certificable` | M:1162 | CONCL (textos del llamador) | default `()` | `estado_banco.json.motivos` (R:1146-1153) y `aprobaciones_estado.json.motivos` (R:1494-1504): cota no calculable, muestra incompleta, identidad (R:746-754); no cableado [V] |

### 1.2 Campos de cada fila de `casos` / `casos_base` que lee la puerta

Todos son AGREGADOS producidos por `agregar_casos` (M:397-430); ninguno es crudo. [V]

| Campo | Dónde lo lee la puerta | Producido en | Ausente ⇒ | Se recalcularía desde |
|---|---|---|---|---|
| claves (case_id) | M:1126-1129 | M:400-402 | falta_caso ⇒ NC | rep-NN.json existentes por versión (R:263-264) |
| `estrato` | M:1135 | M:403-406 | distinto ⇒ NC | `PR.estrato_de` (PR:89) |
| `R` | M:1138 | M:406 (`len(ms)`) | `int(… or 0)` (M:1138) | número de `rep-NN.json` del caso |
| `repeticiones` | M:1137-1138 | M:410-411 | `or []` (M:1137) | nombres `rep-NN.json` / campo `rep` (R:1035) |
| `repeticiones_invalidas` | M:1139 | M:412 | `or 0` (M:1139) ⇒ 0 | ídem |
| `n_evaluadas` | M:1141 | M:424 (cuenta `evaluada is True`) | `or 0` | por corrida, `evaluada` (M:333) = bool del llamador; se derivaría de `pasada1.estado=="evaluada"` (J:1863) y `pasada2.estado` (J:1895), que no se persisten (§3 B1) |
| `repeticiones_evaluadas` | M:1142 | M:413-415 | `or []` | ídem |
| métrica `m` ∈ `PR.METRICAS_COMPARATIVAS` (PR:384-395: turnos_completados, cobertura_hechos_materiales, cobertura_hechos_decisivos, omisiones_materiales, definitivo_con_hecho_decisivo_omitido, aprobacion_sin_edicion_proxy, utilidad_resultado_limitado, falsos_bloqueos, abstencion_injustificada, tasa_cambio_de_motor) | M:617 (vía `comparar_metrica`, M:1188) | medias M:416-417 sobre `METRICAS_MEDIA` (M:374-380) | `None` donde aplica ⇒ par faltante ⇒ NC (M:622-624, 648-653) | `metricas_corrida` por corrida (M:329-368) |
| `n_decisivos_clave`, `n_limitadas`, `n_hechos_clave` (aplicabilidad, M:597-598; PR:399-402) | M:618, M:641 | M:425-428 | `or 0` ⇒ «no aplica» si los dos lados son None (M:619-621) | clave custodiada (`hechos_materiales[].decisivo`) y conducta por corrida |
| `cobertura_hechos_materiales`, `cobertura_hechos_decisivos` (pérdida por caso) | M:701 (vía M:1225) | M:416-417 | par faltante ⇒ NC | ídem |

`comparar_metrica` se invoca sin `base_corridas`/`nuevo_corridas` (M:1188-1189), así que la
diferencia «por corrida» de §6.2 (DOC:534-535) no se produce en la puerta. [V]

### 1.3 Filas absolutas (§6.1): qué consume la puerta y de dónde saldría cada `cumple`

La puerta lee de cada fila solo `fila`, `estrato`, `aplica`, `cumple`, `efecto_si_falla`
(M:1172-1180). `valor` no se lee. `aplica=False` hace que `cumple` sea `None` (M:463) y la fila
queda fuera del control (M:1177: solo `aplica` y `None` ⇒ sin_dato). `kappa_salidas_reales` con
`cumple None` se acepta (M:1177). Ninguna fila se recalcula en la puerta. [V]

| Fila (M:896-911) | Construida en `evaluar_absolutos` | Entrada que usa | Tipo | Ausente ⇒ | Crudo desde el que se recalcularía |
|---|---|---|---|---|---|
| `afirmaciones_sin_respaldo` | M:479-480 | `casos[].afirmaciones_sin_respaldo` (`or 0`) ← M:418-419 ← M:315 `c.get(...) or 0` | CONCL | 0 | `J.recuento` (J:1068-1084: átomos de Opus con unidad confirmada) + `adjudicar_negativas_falsas.confirmadas` (J:1127-1131); ambos sobre las decisiones y votos de `pasada1` (J:1853-1874). No persistidos |
| `fuga_jurisdiccion (casos con alguna)` | M:481-482 | `casos[].fuga_jurisdiccion` (media) ← M:363: `senal_fuga(c)` o `fuga_juez > 0` (`or 0`) | CONCL | 0 si falta `fuga_juez` | `texto_salida` = diagnóstico + borrador completos (`resultado.diagnosis_full`/`draft_full`, H:738-740, activado por R:1703; en custodiados dentro de `.enc`, R:1038) + `jurisdicciones` del caso (fijadas en R:1783, NO persistidas en rep-NN, R:1033-1040) + clasificación de los jueces (`fuga_juez`): ningún productor [V] |
| `definitivo_con_lectura_insuficiente` | M:483-484 | suma M:420-421 ← flag DLI de la celda (M:358) | CONCL | 0 | alcance (M:271-274 ← `alcance_desde_fragmentos`, M:1306-1320, sobre `material_turno.entraron_tramos`, H:876-879) + cobertura de decisivos (`cubierto` de la pasada 2, J:1215-1224; `decisivo` de la clave) + conducta (pasada 2) |
| `discordancias_sin_resolver` | M:485-486 | suma M:418-419 ← M:341 (`or 0`) + pendientes de negativa falsa (M:312-313) | CONCL | 0 | `recuento.discordancias_sin_resolver` (J:1076, 1081: es LISTA; M espera entero [V]), `adjudicar_negativas_falsas.discordancias` (J:1112, 1134-1135), `adjudicar_cobertura` resultado `discordancia` (J:1143-1159). No persistidos |
| `kappa_reservado` | M:487-488 | `kappa_reservado.kappa_float`, `.cuenta_como_minimo` | CONCL | `bool(None)` ⇒ False ⇒ NC | `pares_kappa` del reservado: `VJ` los calcula (VJ:375-378) pero los excluye de `por_item` (VJ:388) y de `resultados`; solo publica el resumen (VJ:346) ⇒ no recalculable desde disco [V] |
| `kappa_salidas_reales` | M:489-492 | `kappa_real.exigido`, `.cuenta_como_minimo`, `.kappa_float` | CONCL | `exigido` falso ⇒ `cumple None` aceptado | `J.evaluar_kappa(conjunto="real")` (J:954-983) sobre `pasada1.pares_kappa` (J:1869) de todas las corridas reales; no persistidos |
| `circuito_sobre_mutaciones_reservadas` | M:493-495 | `circuito.circuito_utilizable`, `.resumen` | CONCL | False ⇒ NC | `VJ.evaluar_exigencias` (VJ:277-347) sobre `resultados` por verdad (VJ:256-260, persistidos en el JSON de salida VJ:380, 706) |
| `evaluacion_completa_dos_jueces` | M:496-497 | bool del llamador | CONCL | — | `estado` de pasada 1 y 2 por corrida (J:1863, J:1895); no persistidos |
| `cobertura_hechos_decisivos (media)` por estrato de lectura completa | M:502-506 | `estratos[e].cobertura_hechos_decisivos`, `.n_decisivos_clave` | CONCL | `aplica=False` si `n_decisivos_clave` 0 (`or 0`, M:503) | per-run `hechos[].cubierto` (pasada 2) y clave |
| `cobertura_hechos_decisivos (ningún caso < 0,80)` | M:507-513 | `casos[].estrato`, `.n_decisivos_clave`, `.cobertura_hechos_decisivos` | CONCL | ídem | ídem |
| `aprobacion_sin_edicion_proxy` | M:514-517 | `estratos[e].aprobacion_sin_edicion_proxy` | CONCL | None ⇒ NC | M:326-327: completada, defectos, omisiones, celda, `juez_aprobaria` (pasada 2 `aprobaria_sin_editar`, M:1370) |
| `cobertura_decisivos_en_lo_leido (media)` voluminosos | M:522-525 | `estratos[e].…`, `.n_decisivos_disponibles` (`or 0`) | CONCL | `aplica=False` si 0 | `hechos[].disponible` (M:1350 ← `envio_desde_material`, M:78-101) + `cubierto` |
| `cobertura_hechos_decisivos (suelo)` voluminosos | M:526-529 | ídem | CONCL | ídem | ídem |
| `tasa_corridas_con_omision_material_leido` (todo estrato presente) | M:530-533 | `estratos[e].omisiones_materiales` | CONCL | None ⇒ NC | `puntos[].resolucion` (pasada 2, J:1233-1240) + `disponible` |
| `utilidad_resultado_limitado (media)` | M:534-537 | `.utilidad_resultado_limitado`, `.n_limitadas` | CONCL | `aplica=False` si `n_limitadas` 0 | conducta y puntos (pasada 2) |

`estratos` (agregados de `agregar_estratos`, M:433-447) no entra a `veredicto_global`: la puerta
solo ve las filas ya decididas. [V]

### 1.4 Comparativas (§6.2), filas extra y recibo de extensión

| Entrada | Dónde | Tipo | Qué hace la puerta | Crudo / recálculo posible |
|---|---|---|---|---|
| `comparativas[].metrica/unidad` | M:1182 | CONCL | indexa | — |
| `comparativas[].veredicto`, `.diferencia_por_caso` | M:1195-1197 | CONCL | se coteja con el recálculo; distinto ⇒ NC | recálculo M:1188-1189 desde agregados |
| `comparativas[].extension` | M:1194, 1206, 1211 | CONCL | activa `_motivos_recibo` | — |
| `extension.comparativa_previa.{veredicto, metrica, unidad, diferencia_por_caso}` | M:1098-1103 | CONCL | solo comprueba etiqueta `no_concluyente`, (métrica, unidad) y que las claves de `diferencia_por_caso` ⊆ casos de la unidad; NO recalcula la previa [V] | agregados de las repeticiones 1..R_original de las dos versiones (sin las de extensión) |
| `extension.casos` | M:1099, 1105-1106, 1111 | CONCL | debe igualar `casos_para_extension(previa)` (M:677-681), calculado sobre la `diferencia_por_caso` APORTADA [V] | ídem |
| `extension.corridas_por_caso` | M:1108 | PARÁM | `== 5` | número de rep > R_original por caso |
| `extension.veredicto_final` | M:1114 | CONCL | igual al recálculo | recálculo |
| fila `perdida_por_caso:<m>` | M:1224-1230 | — | recalculada con `perdidas_por_caso(casos_base, casos, …)`; `cumple` aportado se ignora [V] | agregados |
| fila `decisivos_estables_perdidos` | M:1231-1237 | CONCL | solo exige `casos_cubiertos == casos_esp` y confía en `cumple` [V] | ver abajo |
| fila `atribucion_de_subidas_de_cuota` | M:1234-1237 | CONCL | confía en `cumple` [V] | ver abajo |

Productor previsto de las filas extra: `filas_comparativas_obligatorias` (M:1041-1077), sin llamador
fuera de tests [V]. Sus entradas:

| Entrada | Dónde | Tipo | Ausente / vacío ⇒ | Crudo |
|---|---|---|---|---|
| `decisivos_base`, `decisivos_nuevo`: caso → hecho → fracción de corridas cubierto | M:1060-1061 → M:708-732 | CONCL (fracción) | `None` ⇒ `sin_datos`; un caso como `{}` en las dos versiones se acepta sin control (bucles M:723 y M:730 vacíos) [V] | `cubierto` por hecho de la pasada 2 en cada corrida + `decisivo` de la clave; ninguna función de M construye la fracción desde corridas [V] |
| `techo.subidas_que_exigen_mejora_atribuible` | M:1066 | CONCL | `None` ⇒ cumple None | `techo_cuota` M:832-837 |
| `techo.resultado` | M:1067 | CONCL | ∉ {cumple, no_cumple} ⇒ cumple None | `techo_cuota` |
| `techo.consumo_por_ambito[ámbito].{base,nuevo}` | M:1020, 1027-1028 | CONCL (suma) | no Mapping ⇒ `usage_by_node_no_suma_el_consumo_medido` | `techo_cuota` M:866-870 |
| `comparativas[].veredicto == "mejora"` | M:1007-1008 | CONCL | ⇒ `sin_mejora_en_la_metrica` | recálculo |
| `atribuciones[].{subida, metrica, unidad, nodo}` | M:1071, 1003-1005 | PARÁM | ⇒ `sin_atribucion` / `atribucion_incompleta` | — |
| `atribuciones[].usage_by_node.{base,nuevo}: {nodo: tokens}` | M:1021-1037 | CONCL (suma por nodo aportada) | ⇒ `sin_usage_by_node` | filas de `turn_usage` del ámbito (caso / corrida / total) de las dos versiones; hoy solo existe el volcado por tenant y tramo (R:1937-1939, ver §2 y §3 B7) |
| `inventario.casos[cid].estrato` | M:1015-1019 | reconstruido | — | `PR` |

### 1.5 Techo de cuota (§6.3)

La puerta lee de `techo` solo `resultado` (M:1239-1249) y `R_por_caso.{base,nuevo}`
(M:1245-1247). No lee `condiciones`, `motivos`, `descriptivo` ni `consumo_por_ambito`. [V]
`R_por_caso` lo produce `techo_cuota` como `len(corridas)` de su propia entrada (M:788-789): no
está ligado a ningún `rep-NN.json`. [V]

Entradas de `techo_cuota` (M:772-873) y su origen en disco:

| Campo esperado (docstring M:773-774) | Dónde se lee | Ausente ⇒ | Campo que el runner escribe | Correspondencia |
|---|---|---|---|---|
| `corridas[].tokens` | M:743-745 (`consumo`) | no entero ≥ 0 ⇒ None ⇒ NC (M:766-767) | `intentos[].consumo.claude_conocido` (R:1544) | no declarada [V] |
| `corridas[].intentos_fallidos` | M:746 `registro.get(campo_fallidos, [])` | **clave ausente ⇒ «sin fallidos»** [V] | `consumo.fallidos` (R:1547) | no declarada |
| fallido `.consumo_conocido`/`.tokens` | M:752-754 | — | `consumo_conocido: False` siempre (SG:1245) | — |
| fallido `.tokens_entrada_estimados`, `.cota_salida` | M:755-758 | no enteros ⇒ None ⇒ NC | mismos nombres (SG:1239-1240); `None` en `cli-*` (SG:1224-1231) | coincide |
| `corridas[].inferencias` | M:798-799, 840-841 | no entero ⇒ NC (M:798-799) | ninguno; existe `consumo.llamadas` = Claude + Codex, e incluye intentos fallidos (SG:867 vía SG:1169; R:1546) | no declarada; no se infiere equivalencia |
| `corridas[].tokens_codex` | M:802 | None ⇒ NC | `consumo.codex_conocido` (R:1545) | no declarada |
| `corridas[].intentos_fallidos_codex` | M:802 | ausente ⇒ «sin fallidos» (M:746) | `consumo.codex_fallidos` (R:1547) | no declarada |
| `aprobacion.{tokens, intentos_fallidos, tokens_codex, intentos_fallidos_codex}` | M:765, 794-796 | no Mapping ⇒ `sin_aprobacion` | `aprobacion.json.consumo_aprobacion` (R:1436: SOLO el último intento válido) y cada `aprob.intento-K.json.consumo_aprobacion` (R:1396) | no declarada |
| (no leídos por `consumo`) `desconocido`, `sin_registro` | — | — | `consumo.desconocido` (huérfanos R:869, R:1522), `consumo.sin_registro` (R:1547) | `consumo` no los lee [V]: un huérfano `{desconocido: True, claude_conocido: 0}` llevado tal cual sería 0 [I] |
| varios intentos por (caso, rep) | — | — | `rep-NN.json.intentos[]` (R:1036), uno por intento | `techo_cuota` espera UN registro por corrida; la regla de suma de intentos no está declarada [V] |

### 1.6 Entradas por corrida de `metricas_corrida` (M:266-368), base de todo lo anterior

| Campo | Línea | Tipo | Ausente ⇒ | Crudo (dónde existe hoy) |
|---|---|---|---|---|
| `case_id`, `estrato` | M:330 | PARÁM | KeyError | `rep-NN.json.caso_id` (R:1034); estrato desde `PR` |
| `repeticion` | M:330 | PARÁM | None ⇒ repetición inválida (M:412) | `rep-NN.json.rep` (R:1035) |
| `evaluada` | M:333 | CONCL | `is True` estricto ⇒ False | estado de pasadas 1 y 2 (no persistido) |
| `hechos[{id, decisivo, cubierto, disponible}]` | M:267, 269-270, 345-349 | CRUDO (cubierto = juez) + calculado (disponible) | `or []` ⇒ coberturas None | `hechos_y_puntos_desde_clave` (M:1341-1370): clave custodiada + `pasada2.salida.hechos[].cubierto` (no persistido) + `envio_desde_material(material_turno)` (persistido en rep-NN) |
| `puntos[{id, tipo, disponible, resolucion}]` | M:268, 283-307 | CRUDO (resolución = juez) | `or []` | clave + `pasada2.salida.puntos[].resolucion` (no persistido) |
| `alcance{leidos,total,piezas_sin_leer,medido}` | M:271-274 | calculado | `or {}` ⇒ `sin_medicion` ⇒ insuficiente | `alcance_desde_fragmentos(fragmentos_por_pieza, envio)` (M:1306-1320); `fragmentos_por_pieza` no tiene fuente declarada ni está en rep-NN [V] |
| `subtipos_sin_respaldo` | M:275 | CRUDO (juez) | `or []` ⇒ nunca C4 | `recuento.detalle_sin_respaldo[].subtipo` (J:1073-1074) |
| `conducta` | M:277-279 | CRUDO (juez) | ValueError | `pasada2.salida.conducta.clase` (M:1368) |
| `dice_lo_no_leido` | M:293 | CRUDO (juez) | False | `pasada2.salida.conducta.dice_lo_no_leido` (M:1369) |
| `negativas_falsas_adjudicadas` | M:312 | CONCL | `or []` ⇒ todas pendientes ⇒ discordancia | `adjudicar_negativas_falsas.adjudicadas` (J:1138-1139) |
| `afirmaciones_sin_respaldo` | M:315 | CONCL (conteo) | `or 0` ⇒ 0 | ver 1.3 |
| `completada` | M:316 | CRUDO | False | `rep-NN.json.estado == "completo"` (R:1006-1007) |
| `es_riesgo`, `negativa_correcta` | M:316-317 | PARÁM / CONCL | False | `es_riesgo` desde estrato [I]; `negativa_correcta`: ningún productor [V] |
| `juez_aprobaria` | M:327 | CRUDO (juez) | False | `pasada2.salida.aprobaria_sin_editar.respuesta` (M:1370) |
| `discordancias_sin_resolver` | M:341 | CONCL (conteo) | `or 0` ⇒ 0 | ver 1.3 |
| `texto_salida`, `jurisdicciones` | M:257-263 | CRUDO | ValueError (M:258-259); `fuga_senal` precalculada prohibida (M:254-256) | texto: `resultado.diagnosis_full`/`draft_full`; jurisdicciones: no persistidas |
| `fuga_juez` | M:363 | CONCL (conteo) | `or 0` ⇒ 0 | sin productor [V] |
| `falsos_bloqueos` | M:365 | CRUDO/señal | `or 0` ⇒ 0 | `resultado.false_block` (H:743) |
| `cambio_de_motor` | M:366 | CRUDO | False | `resultado.model_fallbacks` (H:733) [I: la traducción lista→bool no está escrita] |

---

## 2 · SALIDAS DEL RUNNER

`S` = `--salida` (fuera del repo, R:1752); `SC` = `--salida-custodia`. La carpeta por caso es `SC`
para los custodiados y `S` para el resto (`_base_de`, R:634-641). Todo lo escrito por
`escribir_atomico` (R:248-253) es JSON en claro con tmp + `os.replace`.

### 2.1 `execution/run_banco04.py`

| # | Ruta relativa | Escrito en / cuándo | Esquema | Cifrado | Ligado a I10 |
|---|---|---|---|---|---|
| 1 | `S/<ver>/MANIFIESTO.json` | R:779-790, una vez, apertura exclusiva `"x"`; al arrancar `ejecutar_banco` (R:1048) y `ejecutar_aprobaciones` (R:1450) | `version, sha_arbol, arbol_limpio, modificaciones_sha256, soul_sha256, cli_version, politica, protocolo_version, protocolo_hash, runner_sha256` (R:739-743). Sin `semilla`, sin digest de casos, sin `hash_evaluador`, sin `prompt_version_hash` [V] | no | es el manifiesto; solo bajo `S`, no bajo `SC` |
| 2 | `B/<ver>/<caso>/rep-NN.en_curso.json` | R:987-989 antes de cada intento; se borra tras escribir el intento (R:1028-1031); un proceso muerto lo deja y `_recuperar_huerfanas` lo convierte en intento (R:851-874) | `caso_id, rep, intento, manifiesto_sha256` | no | sí, cotejado (patrón R:769) |
| 3 | `B/<ver>/<caso>/rep-NN.intento-K.json` | R:1027, al terminar cada intento | `n, caso_id, rep, segundos, consumo, manifiesto_sha256, estado` y en fallo `clase, error_tipo, error_status, error` o `error_cifrado`, `motivo_parada` (R:1001-1017). `consumo` = `consumo_desde_guardian` (R:1537-1547): `claude_conocido, codex_conocido, llamadas, fallidos[], codex_fallidos[], sin_registro`. Cada fallido = intento de SG:1233-1247 (`alias, cota_aplicada, cota_fuente, max_tokens_pedido, motivo_cota, tokens_entrada_estimados, cota_salida, tokens_cota_superior, tipo_error, consumo_conocido=False, proveedor_no_alcanzado`). Huérfano: `consumo = {desconocido: True, claude_conocido: 0, fallidos: [], sin_registro: 0, llamadas: 0}` (R:863-870). No hay registro por llamada exitosa (alias, tokens, nodo): solo deltas [V] | texto de error cifrado en custodiados (R:824-848) | sí, cotejado |
| 4 | `B/<ver>/<caso>/rep-NN.json` | R:1033-1042 al cerrar la repetición; NO se escribe si `limite_de_uso` (R:1041) | `version, sha, caso_id, clase, rep, estado, politica, semilla, cli_version, soul_sha256_previo, intentos[], manifiesto_sha256, resultado`. `resultado` = dict de `harness.run_case` (H:703-903): `case_id, title, matter_id, elapsed_ms, score, verification, verification_diagnosis, documents_retrieved, draft_preview, diagnosis_preview, reached_draft, provenance, usage` (CaseUsage SG:643-653: `calls, prompt_tokens, completion_tokens, total_tokens, cost_usd, llm_seconds, models{alias: n}`), `model_fallbacks, draft_full, diagnosis_full` (con `MIA_EVAL_PERSIST_FULL=1`, R:1703), `false_block, abstention, jurisdiction_leak` (señal del producto, H:753), opcionales `agentic_reading, recall_enterrado, substantive`, `material_turno{documents_map, documents_origen, recorte_posible_por_contexto, contenido_completo_persistido, fragmentos_en_prompt, entraron, entraron_parcial, entraron_tramos, research_sources, alcance_lectura, soul_sha256, cli_version, errores_instrumentacion}`, `intentos_fallidos`. No contiene: jurisdicciones configuradas del caso (R:1783), digest del caso, `prompt_version_hash` (DOC:983-985) [V] | en custodiados `resultado` se sustituye por la ficha `cifrado, archivo, id_registro, algoritmo, bytes_claro, sha256_claro, sha256_cifrado` (R:818-821) | sí, cotejado (R:769, R:965) |
| 5 | `B/<ver>/<caso>/rep-NN.resultado.enc` | R:816-817 | blob AES-256-GCM, id `<ver>/<caso>/<rep>` (R:814) | sí | indirecto: por el `sha256_cifrado` de la ficha en el rep-NN cotejado |
| 6 | `B/<ver>/<caso>/rep-NN.<etapa>-intento-K.error.enc` | R:841-844 (etapa `produccion` o `aprob`) | blob cifrado del texto de la excepción | sí | indirecto, por el intento |
| 7 | `S/<ver>/decision_r.json` | R:1105-1119, una vez tras la piloto | salida de `decidir_r` (R:543-548): `tope_produccion, proyeccion_r_plena, consumo_piloto_por_caso, r_por_caso, proyeccion_r_reducida, decision, cifra_disparadora, tope_produccion_codex, proyeccion_codex_r_plena, consumo_piloto_codex_por_caso, proyeccion_codex_r_reducida, proveedor_disparador` + `manifiesto_sha256` | no | sí, cotejado |
| 8 | `S/<ver>/aprobaciones_plan.json` | R:1142-1145 al terminar la producción | `semilla, elegidas[{caso, rep}], nota, manifiesto_sha256` | no | sí, cotejado |
| 9 | `S/<ver>/estado_banco.json` | R:1149-1153 al terminar | `estado, motivos, consumo` (= `ContadorCuota.resumen`, R:454-463), `decision_r, version, sha, manifiesto_sha256, arbol_limpio` | no | lleva el campo pero NO está en `PATRONES_REUTILIZABLES` (R:769-771): no se coteja [V] |
| 10 | `S/<ver>/SUSPENDIDO.json` | R:939-951 al suspender | `estado, motivo, version, sha, consumo, regla, reanudaciones_previas` + extra | no | NO lleva `manifiesto_sha256` [V] |
| 11 | `S/<ver>/SUSPENDIDO.reanudado.json` | R:1056, R:1458-1459 | copia del marcador + `reanudado_con` | no | no |
| 12 | `B/<ver>/<caso>/aprob.en_curso.json` | R:1358-1360 | `caso_id, rep, intento, manifiesto_sha256` | no | sí, cotejado |
| 13 | `B/<ver>/<caso>/aprob.intento-K.json` | R:1424 | `n, caso_id, rep, segundos, consumo_turno, consumo_aprobacion, manifiesto_sha256, estado` y en fallo `clase, error…, motivo_parada` (R:1395-1412). Huérfano: `consumo_turno` y `consumo_aprobacion` = `{desconocido: True}` (R:1517-1522) | error cifrado en custodiados | sí, cotejado |
| 14 | `B/<ver>/<caso>/aprobacion.json` | R:1431-1439 (no en `limite_de_uso`) | `version, caso_id, rep, estado, intentos, manifiesto_sha256, aprobacion` (`{aprobada, aprendizaje, trabajos{por_estado, pendientes}}` R:1882 o `{aprobada: False, motivo}` R:1866-1867), `consumo_aprobacion` (último intento válido, R:1436), `consumo_turno_reproducido` (R:1437). La salida del turno reproducido no se guarda [V] | no | sí, cotejado |
| 15 | `S/<ver>/aprobaciones_estado.json` | R:1501-1504 | `estado, motivos, aprobaciones{caso: estado}, consumo, version, sha, manifiesto_sha256` | no | campo presente, NO cotejado (no está en R:769-771) |
| 16 | `S/<ver>/ledger/<id>.json` (escritor A) | `registrar_consumo_externo` R:1174-1196; sin llamadores [V] | `id, version, etapa, nota, consumo{claude_conocido, fallidos, codex_conocido, codex_fallidos, sin_registro, desconocido}`. No escribe `proveedor` ni `estado` [V] | no | no (excluido a propósito, R:765-768) |
| 17 | `S/<ver>/ledger/<id>.json` (escritor B) | `LedgerJuicio.iniciar` R:1273-1275 antes de lanzar; `cerrar` R:1287-1293 al volver | `id, version, etapa, proveedor, estado(en_curso\|cerrado), cota_reservada, consumo{claude_conocido, codex_conocido, fallidos, codex_fallidos, sin_registro, desconocido}, error, timeout`. Sin caso, repetición, `candidate_id` ni pasada [V] | no | no |
| 18 | `S/<ver>/usage_by_node.<epoch>.json` | R:1937-1939, en el `finally` de `correr()` (fase producción), una vez por invocación del proceso (= por tramo) | lista `{node, task, model, llamadas, prompt_tokens, completion_tokens, total_tokens, latency_ms, tool_calls}` (H:932-935), agrupada SOLO por nodo, tarea y modelo (H:922-928) sobre TODO el tenant efímero de esa invocación (creado en R:1915-1917, borrado en R:1954). No se captura en la fase de aprobaciones (R:1898-1910). Si falla, solo un aviso por stderr (R:1940-1941) [V] | no | no (sin manifiesto, versión par, caso ni repetición) |
| 19 | `<MIA_HOME>/eval-runs/spend_ledger.json` | saldo USD del guardián: `_write_ledger` en SG:828, SG:852; ruta SG:396-401 | sesiones y global en USD, `calls` | no | no; es USD, no cuota de tokens |

Contabilidad de cuota en memoria (`ContadorCuota`, R:318-463): no se persiste salvo como `resumen`
dentro de `estado_banco.json`, `aprobaciones_estado.json` y `SUSPENDIDO.json`. Se reconstruye desde
disco en cada arranque (`cargar_contador_desde_disco`, R:877-900): intentos y `rep-??.json` de cada
versión de `versiones_contador` (R:884-899; claves `caso/rep/n` o `ver/caso/rep/n`), aprobaciones
(R:1202-1212; claves `ver/caso/rep/aprobN/turno|aprobar`) y ledger (R:1213-1221; claves
`ledger/ver/id`). Los registros de las OTRAS versiones de `versiones_contador` se suman sin pasar por
`asegurar_manifiesto` (R:791-796 solo recorre `ctx.version`). [V]
Un ledger `en_curso` cuenta `cota_reservada` con `desconocido: True` (R:1215-1218); un proveedor
distinto de `"claude"` (incluido ausente) se carga como Codex (R:1216). [V]
`ruta_ledger` usa siempre `salida` (R:1170-1171, R:1213): el ledger nunca vive bajo `SC`. [V]

### 2.2 `backend/mia/eval/banco04/jueces.py`

- No escribe ningún registro persistente propio. Archivos temporales: `schema.json` y `salida.json`
  del Codex en `TemporaryDirectory` (J:1672-1697); el CLI de Claude corre en un cwd temporal
  vacío (J:1593). [V]
- Lo que escribe a disco lo escribe a través del ledger del runner: `ControlCuotaJueces.antes` →
  `ledger.iniciar` (J:1448; id `<prefijo>-<proveedor>-<seq>-<hex>`, J:1446) y `despues` →
  `ledger.cerrar` (J:1455-1470): con tokens conocidos (`tokens_conocidos`, J:1375-1404); con cota
  documentada como fallido acotado (J:1463-1467); sin cota, `timeout=True` (J:1468-1470). [V]
- `ControlCuotaJueces.intentos` (J:1430, 1471-1472) vive en memoria.
- `pasada1` (J:1818-1875), `pasada2` (J:1883-1896), `adjudicar*`, `votar_cobertura`, `acuerdo_*`
  devuelven dicts en memoria con el JSON crudo de cada intento (`llamar_validado.intentos`,
  J:1752-1755: `intento, error, salida, errores, uso, modelo_reportado, cli_version, latencia_ms`),
  decisiones, votos y `pares_kappa`. Ningún código los persiste para las corridas de producción. [V]
- `hash_evaluador` (J:1948-1962) calcula; no escribe.

### 2.3 `execution/banco04_validar_jueces.py`

| Ruta | Cuándo | Esquema | Cifrado | Ligado a I10 |
|---|---|---|---|---|
| `--salida` (cualquier ruta; para el reservado, fuera del repo, VJ:682-683) | VJ:705-706, al final, `write_text` NO atómico | `tipo, exigencias{k: {valor, cumple}}, circuito_utilizable, nota, resumen, kappa` (resumen con Fractions como str, VJ:346), `cegado, resultados[]` por verdad (`item, id, categoria, es_defecto, proporcion_en_oracion, estado, detectado_final, detectado_opus, detectado_codex, solo_codex, estado_opus_aceptable`, VJ:233-260), `rechazos_por_codigo, por_item[{item, estado, rechazos, discordancias}]` (sin `verdades` ni `pares_kappa`, VJ:388-389), `consumo_jueces` (= `control.intentos`, VJ:701), `hash_evaluador, protocolo, acreditacion_v13` | no (claro) | no: lleva `hash_evaluador`, no el manifiesto del runner ni la versión medida [V] |
| `%LOCALAPPDATA%/MIA-banco04-registro-uso/reservado-<identidad>.usado` | VJ:490-491, antes de juzgar el reservado (VJ:695-696), exclusivo | `identidad_sellada, protocolo, protocolo_custodia, huellas_material[], marcado` (VJ:486-488) | no | no |
| `<MIA_BANCO04_CUSTODIA>/registro-uso/reservado-<identidad>.usado` | VJ:495-498 | ídem | no | no |
| `<--salida-banco>/<--version>/ledger/validacion-<tipo>-<prov>-…json` | vía `control_de_cuota` → `LedgerJuicio(salida_banco, version)` (VJ:632-635), etapa `validacion` | ver §2.1 fila 17 | no | no |

No persiste: JSON crudo de los jueces, `unidades`, `decisiones`, `pares_kappa` del reservado. [V]

### 2.4 `usage_by_node`: cómo se registra hoy

1. Cada llamada EXITOSA del grafo pasa por `llm._record_usage` (llamado en `agent/llm.py:905-913`
   solo después de que `_call_with_retries` devuelve) → `metrics.usage.record`
   (`backend/mia/metrics/usage.py:201-260`), que añade una fila con `tenant_id, matter_id, task,
   model, prompt_tokens, completion_tokens, total_tokens, node, latency_ms, tool_calls, …` a un
   búfer. Sin scope o sin `usage` no hay fila (usage.py:208-209). Con 10 000 filas en el búfer se
   descarta el 10 % más viejo (usage.py:253-257). Los intentos fallidos no generan fila. [V]
2. El scope del turno lo fija `harness.run_case` por (tenant, matter) (H:600).
3. `harness.usage_by_node(tenant)` agrega `turn_usage` del tenant por (nodo, tarea, modelo)
   (H:909-936), sin `matter_id` y sin repetición. [V]
4. El runner lo llama una vez por invocación de la fase de producción y lo escribe como
   `S/<ver>/usage_by_node.<epoch>.json` (R:1933-1941); después borra el tenant (R:1946-1954), y con
   él las filas de `turn_usage`. [V]
5. La puerta (`atribucion_valida`) no lee ese archivo: recibe `usage_by_node` dentro de cada
   atribución aportada por el llamador (M:1021). [V]

---

## 3 · BRECHAS

Formato: qué cálculo de §6 no puede hacerse con lo que el runner escribe, y por qué falta el dato.

- **B1 · No hay juicio de las corridas de producción en disco.** El único llamador de
  `jueces.pasada1` es la validación con mutaciones (VJ:229); `pasada2`, `adjudicar_cobertura`,
  `adjudicar_negativas_falsas`, `votar_cobertura`, `acuerdo_pasada2(_agregado)`,
  `acuerdo_estabilidad`, `seleccionar_con_semilla` y `evaluar_kappa(conjunto="real")` no tienen
  llamador fuera de tests. [V] Falta el dato crudo para: `afirmaciones_sin_respaldo`,
  `subtipos_sin_respaldo` (C4), `discordancias_sin_resolver`, `kappa_salidas_reales`, `hechos[].cubierto`,
  `puntos[].resolucion`, conducta, `dice_lo_no_leido`, `juez_aprobaria`, `evaluada`,
  `evaluacion_completa_dos_jueces`, `fuga_juez`, negativas falsas, adjudicación marcador ↔ juez
  (§5.2, M:1283-1300), estabilidad (§8.6), acuerdo de la pasada 2 de Codex sobre el 15 % (§8.2) y
  consumo de jueces por salida. §9.4 lo exige (DOC:1001-1007).
- **B2 · El runner no llama a la medición.** Declarado en §12.6 (DOC:1359-1360) y verificado:
  `run_banco04.py` solo importa del banco `protocolo` (R:1641) y `custodia` (R:1712); no importa
  `metricas` ni `jueces`. Tampoco llama a `senal_fuga`,
  `envio_desde_material`, `alcance_desde_fragmentos`, `hechos_y_puntos_desde_clave`,
  `discrepancias_marcador`, `agregar_casos`, `agregar_estratos`, `evaluar_absolutos`,
  `techo_cuota`, `perdidas_por_caso`, `decisivos_estables_perdidos`,
  `filas_comparativas_obligatorias`, `veredicto_global` ni `resumen_publicable`. [V] No existe un
  agregador banco04: `execution/aggregate_eval_runs.py` (citado en DOC:1011-1012) no trata
  `banco04`/`rep-NN` [V por grep]; `execution/banco04_calibracion.py` espera un `--corridas` que
  «lo produce el agregador del banco» (calibracion:17-22) y nadie lo produce. [V]
- **B3 · Entradas de `metricas_corrida` que no están en `rep-NN.json`:** `jurisdicciones` del caso
  (fijadas en R:1769-1783, no persistidas) ⇒ `senal_fuga` no se puede recalcular desde disco;
  `negativa_correcta` (sin productor); `fragmentos_por_pieza` para `alcance_desde_fragmentos`
  (sin fuente declarada; `documents_map` es la lista de intake, anterior a `_shrink`, H:816-818);
  clave custodiada (vive en la custodia, no en el registro). [V] El alcance C8 acepta una medición
  parcial: `medido` (H:858) no exige `llamadas_sin_identificar == 0` (eso solo entra en
  `fragmentos_en_prompt.completo`, H:861), y `envio_desde_material` solo comprueba que
  `entraron_tramos` no sea `None` (M:83): un turno con bloques `<<<DOC` sin identificar (H:652-653)
  cuenta como medido. [V]
- **B4 · Repeticiones y evaluación se aceptan agregadas.** `R`, `repeticiones`, `n_evaluadas`,
  `repeticiones_evaluadas` llegan en la fila del caso (M:1137-1143); `evaluada` es un booleano del
  llamador (M:333) que no se deriva de ningún registro de juicio (B1). [V]
- **B5 · Techo (§6.3) sin correspondencia declarada de esquema.** `techo_cuota` espera `tokens,
  intentos_fallidos, inferencias, tokens_codex, intentos_fallidos_codex` por corrida y por
  aprobación (M:773-774); el runner escribe `claude_conocido, codex_conocido, llamadas, fallidos,
  codex_fallidos, sin_registro, desconocido` (R:1544-1547, R:869). [V] `consumo` (M:738-759) no lee
  `desconocido` ni `sin_registro`, y toma la clave de fallidos ausente como «sin fallidos» (M:746).
  [V] No hay campo `inferencias`; `llamadas` mezcla Claude y Codex e incluye intentos fallidos
  (R:1546; SG:867 vía SG:1169). [V] Una (caso, rep) puede tener varios intentos (R:1036) y la regla
  para sumarlos en `corridas[]` no está declarada. [V] Para la aprobación, `aprobacion.json` guarda
  solo el `consumo_aprobacion` del último intento válido (R:1436); los anteriores están solo en
  `aprob.intento-*.json`. [V]
- **B6 · `R_por_caso` no ligado a disco.** Lo produce `techo_cuota` con `len(corridas)` de su
  entrada (M:789) y la puerta lo compara con el inventario (M:1245-1247); ningún paso lo cruza con
  los `rep-NN.json` existentes. [V]
- **B7 · C25 / `usage_by_node` imposible de acreditar con lo escrito.** `atribucion_valida` exige
  `{base, nuevo}: {nodo: tokens}` por ámbito (`<caso>:caso`, `<caso>:max_corrida`, `total`,
  `ponderado`) que sume exactamente `consumo_por_ambito` (M:1020-1029). Lo escrito es un volcado por
  tenant y por tramo, sin caso ni repetición, sin aprobaciones y sin par de versiones (R:1937-1939;
  H:922-928). [V] `turn_usage` solo recibe llamadas exitosas (`agent/llm.py:897-913`), mientras
  `consumo_por_ambito` incluye la cota de los intentos fallidos (M:755-758, 866-870): con intentos
  fallidos las dos sumas no pueden coincidir. [I] El ámbito `max_corrida` exige consumo por nodo de
  UNA corrida: no existe. Las filas por `matter_id` existían en `turn_usage` pero se borran con el
  tenant (R:1946-1954). [V] Además, los ámbitos `<caso>:caso`, `total` y `ponderado` incluyen el
  consumo de la aprobación (M:768, M:819-821, M:866-870), y las filas `turn_usage` de cada aprobación
  viven en un tenant propio que `cerrar_aprob` borra (R:1888-1896) sin volcarlas nunca: la igualdad
  de M:1027-1029 falla por construcción aunque no haya intentos fallidos. [V] `consumo_por_ambito`
  es solo Claude (campo `tokens`, M:800-801), mientras `turn_usage` registra cualquier alias, también
  `cli-codex` (`agent/llm.py:905`). [I]
- **B8 · Decisivos estables.** Ninguna función construye «caso → hecho → fracción de corridas
  cubierto» desde las corridas (M:708-732 la recibe hecha) y el dato por corrida (`cubierto`) no
  existe en disco (B1). La clave dice qué hechos son decisivos; el inventario de decisivos por caso
  no se coteja con ella, y `{}` en las dos versiones pasa (M:715-731). [V]
- **B9 · Extensión pre-registrada.** El runner no tiene modo extensión: `plan_desde_protocolo`
  (R:492-502) y `main` (R:1962-1991) no reciben extensión; las R salen de `decision_r.json`. [V] No
  puede producir las 5 corridas adicionales ni distinguirlas, y `comparativa_previa` no se puede
  reconstruir desde disco: exigiría métricas por corrida con identidad de repetición (B2) para
  agregar solo 1..R_original. [V]
- **B10 · Kappa del reservado y circuito.** `VJ` no persiste `pares_kappa` (VJ:388) ni las
  decisiones: `kappa_reservado` y `circuito_utilizable` solo existen como conclusión en el JSON de
  salida (VJ:320, 339, 346). [V] Ese JSON no está ligado al manifiesto de la ejecución ni a la versión
  medida. `--versiones-contador` exige lista no vacía, que incluya la propia, sin repetidos y ≥ 2
  en el Bloque 7 (VJ:625-629), pero los nombres no se cotejan con versiones que existan en disco. [V]
- **B11 · `suspendido`, `salidas_sin_juzgar`, `otros_motivos_no_certificable`.** El runner deja
  `SUSPENDIDO.json` y los motivos en `estado_banco.json`/`aprobaciones_estado.json`, pero nada los
  conecta con la puerta; `salidas_sin_juzgar` no se puede contar (B1). [V]
- **B12 · Identidad (I10) en la puerta.** Nada liga `casos`, `casos_base`, `techo` o `filas_extra` a
  `MANIFIESTO.json` de 0.4 y de 0.3.3; `estado_banco.json` y `aprobaciones_estado.json` no se
  cotejan; `SUSPENDIDO.json`, `ledger/*.json`, `usage_by_node.*.json` no llevan manifiesto. [V]
- **B13 · Ítems de §9.4 que no se registran:** digest del caso y `prompt_version_hash`
  (DOC:983-985; ausentes en R:1033-1040 y R:739-743); por llamada exitosa, alias, modelo efectivo,
  esfuerzo, tokens, nodo y motivo de parada (DOC:995): solo en `turn_usage`, borrado con el tenant;
  `rep-NN.json` lleva totales de `CaseUsage` (SG:643-653). Jueces (DOC:1001-1007): ver B1. [V]
- **B14 · Consumo de jueces sin vínculo a la salida juzgada.** El ledger del juicio no registra
  caso, repetición, `candidate_id` ni pasada (R:1273-1275, J:1446), así que el consumo de jueces no
  se atribuye por salida. [V]

---

## 4 · TELEMETRÍA: componentes ausentes convertidos en cero

Columna «Afecta»: **CUOTA** = alimenta `claude_conocido`/`codex_conocido`/`ContadorCuota`
(certificabilidad del techo §3.4/§6.3) · **PROY** = solo proyección, decisión de R o control previo ·
**ATRIB** = alimenta `turn_usage`/`usage_by_node` (C25) · **USD** = saldo en dólares del guardián ·
**CALIDAD** = métricas de §6.1/§6.2, no cuota · **NEUTRO** = el cero no oculta consumo.

### 4.1 Ruta de producción (alias `cli-*` y LiteLLM) hasta el guardián

| Archivo:línea | Patrón | Qué pasa si falta | Afecta |
|---|---|---|---|
| `backend/mia/agent/subscription_llm.py:258` | `data.get("usage") or {}` | sin `usage` ⇒ dict vacío | CUOTA + ATRIB |
| `backend/mia/agent/subscription_llm.py:260-262` | `_n(key)`: `int(v) if isinstance(v,(int,float)) else 0` | `input_tokens`, `output_tokens`, `cache_*` ausentes ⇒ 0; la respuesta sale con `usage` de ceros | CUOTA + ATRIB |
| `backend/mia/agent/subscription_llm.py:265-270` | suma de componentes rellenados | `total_tokens` = 0 si todo falta. Como `usage` sale siempre con enteros, en `cli-claude` la ausencia se pierde ANTES del guardián: SG:961-969 no puede distinguir «ausente» de «cero» [V] | CUOTA + ATRIB |
| `backend/mia/agent/codex_subscription_llm.py:244-263` | `prompt = completion = total = cached = 0`; `int(raw.get(...) or 0)` | sin evento `usage` ⇒ ceros; componente ausente ⇒ 0 o valor previo | CUOTA (Codex) + ATRIB |
| `backend/mia/eval/codex_cli_adapter.py:536-538` | `int(result.prompt_tokens or 0)` etc. | `None` del parser ⇒ 0 (ruta override eval `cli-codex-eval`) | CUOTA (Codex) + ATRIB |
| SG:955-959 | `_int`: `int(v or 0)`, excepción ⇒ 0 | | CUOTA |
| SG:961-962 | `getattr(u, "prompt_tokens", 0)`, `getattr(u, "completion_tokens", 0)` | `usage` ausente ⇒ 0 | CUOTA |
| SG:966 → `metrics/usage.py:184-198` | `_cache_tokens`: `getattr(..., 0)`, `int(value or 0)`, excepción ⇒ 0 | caché ausente ⇒ 0 | CUOTA + ATRIB |
| SG:969 | `(_int(total_tokens) or (prompt + completion)) + cache_creation` | todo ausente ⇒ total 0 | CUOTA |
| SG:1268-1274 | `if reservation is not None and total == 0: actual = estimate`; luego `note_call(total_tokens=total)` | total 0 se registra como llamada EXITOSA con 0 tokens, sin entrada en `intentos_fallidos` ni marca de desconocido. En `cli-*` la reserva es `None` (`upper_bound_call_cost` = 0, SG:991-992; `check_and_reserve` ⇒ None, SG:787-789), así que ni siquiera se cobra la estimación [V] | CUOTA |
| SG:867-878 (`note_call`) | `int(total_tokens or 0)`, `int(prompt_tokens or 0)`, `int(completion_tokens or 0)`, `float(... or 0.0)`, `usage.models.get(alias, 0)` | | CUOTA (y `CaseUsage` de rep-NN) |
| SG:1169-1172 | `note_call(..., total_tokens=0)` en el camino de excepción | tokens conocidos 0, pero el intento va aparte a `intentos_fallidos` (SG:1233-1256) con cota `None` en `cli-*` (SG:1224-1231) ⇒ no certificable | NEUTRO (cota aparte) |
| SG:1213-1214 | sin cota calculable ⇒ `None`, no 0 | | NEUTRO (correcto) |
| SG:1262-1263 | `getattr(guard, "intentos_fallidos_sin_registro", 0) or 0` | contador de intentos no registrados | NEUTRO |
| R:1609, R:1612 (`GuardBanco.note_call`) | `int(total_tokens or 0)` para embeddings y Codex | | CUOTA (Codex; y resta de Claude, R:1616-1617) |
| R:1540 | `getattr(guard, "intentos_fallidos", None) or []` | | CUOTA |
| R:1543, R:1554 | `int(getattr(guard, "intentos_fallidos_sin_registro", 0) or 0)` | atributo ausente ⇒ 0 sin registrar | CUOTA |
| R:1544-1545 | deltas de `tokens_llm`, `tokens_codex` (`m.get("codex_tokens", 0)`) | heredan los ceros de las filas anteriores | CUOTA |
| `metrics/usage.py:211-212, 218` | `int(getattr(usage, "prompt_tokens", 0) or 0)`, `completion`, `int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)` | | ATRIB |
| `metrics/usage.py:208-209` | `usage is None` ⇒ sin fila | ausencia (no cero), pero el nodo desaparece del desglose | ATRIB |
| `metrics/usage.py:253-257` | búfer lleno ⇒ descarta el 10 % más viejo | filas perdidas | ATRIB |
| H:925-926 | `coalesce(latency_ms, 0)`, `coalesce(tool_calls, 0)` | | ATRIB (no tokens) |
| H:932-935 | `int(r[4] or 0)`, `int(r[5] or 0)`, `int(r[6] or 0)`, `float(r[7] or 0.0)`, `int(r[8] or 0)` | `sum` NULL ⇒ 0 | ATRIB |

### 4.2 Runner: traslado del consumo al contador

| Archivo:línea | Patrón | Qué pasa si falta | Afecta |
|---|---|---|---|
| R:907, R:909, R:911 | `int(consumo.get("claude_conocido") or 0)`, `codex_conocido`, `sin_registro` | un `consumo` sin esas claves y sin `desconocido: True` se registra como 0 conocido y `calculable=True` (R:340-345) [V] | CUOTA |
| R:899 | `registrar_consumo(..., it.get("consumo") or {})` | intento sin `consumo` ⇒ 0 calculable | CUOTA |
| R:1210 | `it.get("consumo_turno") or {"desconocido": bool(it.get("huerfano"))}` | sin consumo y sin `huerfano` ⇒ `{desconocido: False}` ⇒ 0 calculable | CUOTA |
| R:1212 | `it.get("consumo_aprobacion") or {}` | ⇒ 0 calculable | CUOTA |
| R:1221 | `fila.get("consumo") or {}` (ledger cerrado) | ⇒ 0 calculable | CUOTA |
| R:1218 | `int(fila.get("cota_reservada") or 0)` (ledger en curso) | 0, pero con `desconocido: True` ⇒ no certificable | CUOTA (acumulado subestimado; certificabilidad intacta) |
| R:1216 | proveedor ≠ `"claude"` ⇒ campo Codex | proveedor ausente se carga como Codex | CUOTA |
| R:1364-1365, R:1422-1423 | `c_turno = {}`, `c_aprob = {}` iniciales | fallo antes de la primera marca (p. ej. en `abrir_despacho`) ⇒ registrados como 0 calculable [V]; no hay LLM antes de esa marca [I] | CUOTA |
| R:1287-1289 (`LedgerJuicio.cerrar`) | defaults `0` de los parámetros | cierre sin tokens y sin `timeout` ⇒ 0 calculable | CUOTA |
| R:1191-1195 (`registrar_consumo_externo`) | defaults `0`, `desconocido=False` | ídem | CUOTA |
| R:863-870 | huérfano `claude_conocido: 0` con `desconocido: True` | marcado | NEUTRO |
| R:916-917, R:921-922 | `_resumen_consumo(_codex)`: `int(... or 0)` y descarta el booleano `calculable` de `cota_de_fallidos` | consumo sin cota o desconocido cuenta como su parte conocida (0 en huérfanos) | PROY (piloto R:1100-1103; aprobaciones R:931-936, R:1477-1479) |
| R:1094-1095 | `estimacion_piloto_codex.get(clase, 0)`; `_montaje_real` no la pasa (R:1799), queda `{}` (R:627) | Codex de la piloto = 0 | PROY |
| R:534 | `cx_piloto.get(k, 0)` | | PROY |
| R:1132 | `consumos_piloto.get(c.id, 0)`, `codex_piloto.get(c.id, 0)` | | PROY |
| R:1467 | `max(1, int(ctx.consumo_aprobaciones) // …)` | | PROY |
| R:1010-1011, R:1404-1406 | `int(consumo.get("llamadas") or 0)` en `clasificar_fallo` | 0 llamadas ⇒ «infraestructura» | NEUTRO para la cuota; afecta la clase del fallo |

### 4.3 Medición y jueces

| Archivo:línea | Patrón | Qué pasa si falta | Afecta |
|---|---|---|---|
| M:746 | `registro.get(campo_fallidos, [])` | clave de fallidos ausente ⇒ sin fallidos | CUOTA (techo §6.3) |
| M:840-841 | `int(r.get("inferencias") or 0)` | validado antes (M:798-799) | NEUTRO |
| M:858-859 | mediana `or [0]` | descriptivo | NEUTRO |
| M:315, 341, 363, 365, 419, 422, 425-428, 445, 479, 481, 483, 485, 503, 525, 529, 537 | `or 0` / `default=0` | conteos de calidad ausentes ⇒ 0 | CALIDAD |
| J:1375-1404 (`tokens_conocidos`) | telemetría parcial ⇒ `None`, no 0 | | NEUTRO (correcto) |
| J:1391-1395 | `cache_*` ausentes no se suman | si el CLI omitiera la caché consumida, se subcontaría [I] | CUOTA (jueces) |
| J:1403 | `int(tot) if tot is not None else 0` dentro de `max` | prompt y completion ya exigidos | NEUTRO |
| J:1592, 1599, 1606, 1679, 1686 | `RespuestaModelo(..., uso={})` en errores | ⇒ `tokens_conocidos` None ⇒ cota o `timeout` | NEUTRO |
| J:1609 | `data.get("usage") or {}` | ⇒ None conocido | NEUTRO |
| `backend/mia/eval/codex_cli_adapter.py:292-329` (`_parse_events`) | defaults `None`, no 0; por clave se queda con el último evento que la trae (J usa este parser, J:1689) | no rellena ceros [V]; con varios eventos no suma [I] | NEUTRO / posible subconteo Codex jueces [I] |
| VJ:376 | `int(x.get("discordancias") or 0)` | | CALIDAD |

### 4.4 USD (no cuota de tokens)

SG:474 (`pid` 0), SG:592, SG:612, SG:626, SG:807, SG:825, SG:827, SG:851 (`.get("spent_usd"|"calls", 0…)`),
SG:787 (`estimate or 0.0` ⇒ gratis), SG:1032-1039 (`real_call_cost`, `or 0`): afectan el tope en USD,
no la certificabilidad de la cuota.
