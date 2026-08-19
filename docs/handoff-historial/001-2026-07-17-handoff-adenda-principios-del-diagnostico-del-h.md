## 2026-07-17 — HANDOFF (adenda): principios del diagnóstico del harness jurídico (LLOS) → MIA

Fuente: diagnóstico "Del texto que se recuerda a la barrera que bloquea" (Codex + panel red-team) sobre el sistema de skills PERSONAL de Lexia (LLOS). No es MIA, pero su principio de arquitectura es universal y varios temas aplican al producto. Conecta directo con el trabajo de hoy (el "75% caching" era una garantía confiada a prosa; los datos jurídicos fabricados de `ingest_corpus` son el mismo "corpus contaminado" que el red-team describe).

### La regla que ordena todo (adoptarla como criterio de diseño de MIA)
**Si algo DEBE cumplirse, no puede ser una directriz.** Tres niveles con garantías distintas:
- **Orden** (script con código de salida, determinista) → garantía FUERTE.
- **Directriz** (prompt/prosa que sube la probabilidad) → garantía DÉBIL.
- **Restricción** (gate/supervisor que NIEGA, no que pide) → garantía FUERTE.
Las directrices solo hacen más probable pasar el gate; NUNCA son la barrera. Auditar toda "garantía dura" de MIA y clasificarla: la que sea solo prosa, convertir a orden o restricción.

### Temas a EVALUAR/implementar en MIA (con veredicto honesto)
1. **Auditar garantías prosa-vs-código (ALTO).** Recorrer las reglas duras de MIA (verificación de citas, §G, HALT de gates, política de modelo) y confirmar que cada una la hace cumplir CÓDIGO, no solo el prompt. El caching de hoy fue el caso ejemplar: afirmado, nunca ejecutado. MIA ya tiene gates reales (test_rls, especialista de citas) — falta el barrido sistemático.
2. **Gate de citas a nivel de PASAJE + cuarentena de fichas contaminadas (ALTO).** El red-team es duro: verificar que "el radicado existe" APRUEBA el error de mala atribución (el incidente real de 10 citas). La verificación debe confrontar el PASAJE textual contra el texto completo de la providencia en disco; ficha sin fuente almacenada = no apta, en cuarentena. Conecta con lo de hoy (corpus con datos fabricados ya neutralizados en `ingest_corpus`, pero el gate de MIA `agents/verification.py` marca/escanea — revisar si confronta a nivel de pasaje o solo de existencia).
3. **Veredicto de 4 estados, no binario (MEDIO-ALTO).** Hoy MIA aprueba/rechaza. Adoptar: APTO_TÉCNICO ("citas presentes y localizables; el juicio jurídico sigue siendo tuyo" — NUNCA "seguro para firmar") · REQUIERE_JUICIO · NO_APTO · EXCEPCIÓN_AUTORIZADA (override que expira, deja riesgo residual registrado y escala). Evita la falsa seguridad del semáforo verde.
4. **Gate de calidad que fuerza ESTRUCTURA, no puntaje (MEDIO-ALTO).** MIA ya mide "sustancia" (eval_substance, s48). Revisar que NO sea un juez 1-10 (premia "basura elocuente") sino que obligue la cadena completa: mejor tesis contraria → regla → hecho probado con evidencia → inferencia → objeción → respuesta → efecto pedido. Calibrar el umbral contra escritos ya radicados de la firma.
5. **Contrato de escrito con capa probatoria ANTES de redactar (MEDIO).** Estructura canónica por tipo de caso; cada argumento con ≥1 prueba mapeada como REQUISITO previo a redactar, no control posterior.
6. **Aprobación atada al HASH de sus insumos (MEDIO).** Si cambia una cita o una prueba tras aprobar, la verificación se invalida sola. Alinea con el estado transaccional; MIA tiene checkpointer LangGraph — evaluar atar la aprobación HITL al hash de documentos/citas.
7. **Meta corregida (filosofía de producto, ALTO como norte).** NO "el abogado solo aprueba" (o relee todo = cero ahorro, o firma a ciegas = riesgo disciplinario). SÍ "el socio decide derecho; el sistema verifica lo mecanizable; vista de auditoría para aprobar en minutos". El harness DETECTA los detonadores de escalamiento y FRENA — no los evita. MIA ya tiene detonadores; alinear el discurso de producto.
8. **Nombrar los modos de auto-engaño con su freno (MEDIO).** Verificador que lava el error (→ confronta el texto fuente, no la ficha); automatización complaciente (→ la vista resalta conflictos/riesgo, no un sello; registrar tiempo de aprobación); calidad como casillas (→ medir correcciones sustantivas reales); override como bypass (→ expira y escala).

### Lo que MIA YA cubre (no re-implementar, solo verificar que sigue firme)
HITL de borradores · detonadores de escalamiento · RLS fail-closed por tenant · muro de confidencialidad/anonimización · política de modelo (suscripción/nube/soberano) · medición de sustancia (parcial) · gate/especialista de citas (parcial — ver punto 2).

### Advertencia transferible del documento
"Verificado no es verdadero; verdadero no es bueno." El harness industrializa lo chequeable (citas localizables, formato) y deja intacto lo decisivo (calidad del argumento, responsabilidad profesional). El peligro real: que funcione lo bastante bien como para que el abogado deje de mirar. El diseño de MIA debe atacar esto de frente, no esconderlo tras un verde.
