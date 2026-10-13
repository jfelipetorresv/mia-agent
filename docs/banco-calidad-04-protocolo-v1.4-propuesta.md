# Banco de calidad 0.4: propuesta de protocolo banco04-v1.4 (cambios exactos sobre v1.3)

Estado: **propuesta** para la revisión de Astra. **No** modifica `docs/banco-calidad-04-protocolo.md`;
el director integra este texto después de la revisión. Mientras tanto rige banco04-v1.3.

Fecha: 2026-10-12. Base: `docs/banco-calidad-04-protocolo.md` en banco04-v1.3, sin cambios desde
`f5d678b`. La acompaña el contrato `docs/banco04-cadena-contrato.md` (banco04-cadena/v7).

---

## 1 · Motivo

1. **Dictamen de Astra sobre el contrato v6** (scratchpad `r4/veredicto_contrato6.md`, NO APTO). La
   cota del intento fallido del CLI de Claude que proponía la v6
   (`11 × (entrada_estimada + 128000) + 2 × fondo_max`) **no es conservadora**:
   - la entrada se estima con una heurística (`memory/tokens.py`, caracteres/4; el juez,
     caracteres/3), que no acota toda la entrada que envía el CLI;
   - la salida máxima depende del modelo: 128 000 es el tope descrito para los modelos que el CLI no
     reconoce;
   - los diez reintentos documentados son de **peticiones fallidas**, no once peticiones por
     invocación;
   - una muestra del fondo, aunque se duplique, no fija un máximo.

   Además, imponer `CLAUDE_CODE_MAX_RETRIES=10` cambia la conducta medida cuando el entorno traía
   otro valor.
2. **Consecuencia en v1.3.** Por C18 ningún CLI tiene cota. Por §5.5, §6.3, §6.4 y C19, un solo
   intento fallido de CLI deja el techo **no certificable** y, con él, el veredicto global. En un
   circuito de miles de llamadas, eso hace prácticamente imposible certificar la **calidad** por una
   causa que no es de calidad.

## 2 · Decisión de Pipe (2026-10-12): «Separar calidad y cuota»

Revoca «Acotar y medir», del mismo día, que nunca se integró en el protocolo. Contenido:

- El banco emite **dos veredictos**.
  - **CALIDAD:** `aprueba` / `reprueba` / `no_certificable`, por las causas de calidad e identidad
    que ya existen. Sigue siendo certificable aunque haya intentos fallidos sin cota. Un fallo de
    consulta solo cuenta para la calidad por sus efectos propios (turno no completado, fallo sin
    texto, etc.), como hasta ahora.
  - **CUOTA:**
    - «certificada» (cumple / excede) si no hubo ningún intento sin cota;
    - «estimada» si los hubo: se publica el consumo conocido, una estimación empírica del intento
      sin cota declarada como NO garantizada, y el aviso;
    - si la parte CONOCIDA ya excede el techo, el resultado es «excede» aunque haya intentos sin
      cota.
- El techo sigue gobernando la suspensión durante la corrida. Para suspender se usa, de forma
  conservadora, el conocido + la estimación empírica (detener antes), nunca para certificar.
- La reanudación con autorización de Pipe sigue igual, y C27 se mantiene.
- Se retira el fijado de reintentos: el envoltorio no toca el entorno del CLI. Se conserva la
  medición del fondo como estimación empírica versionada, con la instantánea, la firma y la versión
  del CLI.
- Codex: los intentos sin cota caen en la misma regla (cuota estimada).

## 3 · Lo que no cambia

La muestra, las repeticiones, la rúbrica, las métricas, los umbrales de §6.1 y §6.2, las cifras de
los techos de §3.4 y §6.3, los jueces y la custodia. Todavía no se ha corrido ninguna línea base, así
que la versión nueva se fija **antes** de correr (§0 del protocolo).

---

## 4 · Cambios exactos

Cada cambio da el texto actual de v1.3 (entre comillas angulares de bloque) y el texto que lo
sustituye.

### 4.1 Cabecera

**Actual:**

> Versión del protocolo: **banco04-v1.3** · Fecha: 2026-10-11 · Plan: `como-vamos-con-la-robust-llama.md`

**Nuevo:**

> Versión del protocolo: **banco04-v1.4** · Fecha: 2026-10-12 · Plan: `como-vamos-con-la-robust-llama.md`

Al final del párrafo de cabecera se añade: «La v1.4 separa el veredicto de calidad del de cuota
(decisión de Pipe del 2026-10-12, §12.7).»

### 4.2 §3.4 · Techo efectivo, contingencia y suspensión

**Actual:**

> Se miden acumulados durante la corrida, incluida la cota conservadora de los intentos fallidos
> (§5.5).

**Nuevo:**

> Se miden acumulados durante la corrida. Cada intento fallido con cota suma su cota (§5.5). Cada
> intento sin cota suma, **solo para decidir la suspensión**, su estimación empírica (§5.5), de forma
> conservadora, para detener antes. Esa suma nunca certifica la cuota (§6.3).

**Actual** (primer punto de «Suspensión»):

> - se para, se persiste lo hecho y se publica como **«incompleto — no certificable»**, con la cifra
>   de consumo;

**Nuevo:**

> - se para, se persiste lo hecho y se publica como **«incompleto — no certificable»** en el
>   veredicto de calidad, con la cifra de consumo y el veredicto de cuota (§6.4);

### 4.3 §5.5 · Intentos fallidos

**Actual:**

> - El techo de §6 se evalúa **con esa cota superior**. Si un intento fallido no permite calcularla,
>   el techo queda **no certificable** y 0.4 no aprueba esa fila.

**Nuevo:**

> - El techo de §6.3 se evalúa con esa cota superior **cuando existe**.
> - Un intento sin cota (por C18, todo intento fallido de un CLI) no hace no certificable el techo:
>   deja el veredicto de cuota en **«estimada»** (§6.3, §6.4).
> - Cada intento sin cota se registra con una **estimación empírica no garantizada**: entrada
>   heurística + la salida máxima observada en llamadas conocidas de la misma familia, versión del
>   CLI y firma de comando + el fondo observado en la medición versionada del CLI (instantánea, firma
>   y versión), o 0 declarado «no medido».
> - La estimación se publica y sirve para suspender (§3.4). **Nunca certifica.**

**Actual:**

> - **Segundo proveedor (Codex, 5C):** se mide igual, por caso y en total, en su propia cuota.

**Nuevo:**

> - **Segundo proveedor (Codex, 5C):** se mide igual, por caso y en total, en su propia cuota. Sus
>   intentos sin cota caen en la misma regla (cuota «estimada»).

### 4.4 §6.3 · Techo de cuota

**Actual** (final del primer párrafo):

> Por eso **el techo se aplica solo a consumo real agregado (sumas) y a
> extremos**, siempre con la cota conservadora de los intentos fallidos (§5.5). Las medianas y los
> p50 son solo descriptivos.

**Nuevo:**

> Por eso **el techo se aplica solo a consumo real agregado (sumas) y a
> extremos**, con la cota de los intentos fallidos que la tienen (§5.5). Las medianas y los
> p50 son solo descriptivos.

**Se añade**, después del párrafo «Una subida de más del 10 %…»:

> **Veredicto de cuota.** El techo de esta sección y la atribución de subidas forman el **veredicto
> de CUOTA**, separado del de calidad (§6.4). Para cada condición de la tabla:
>
> 1. **Conocido ya excede.** Se calcula la cota inferior del numerador (solo consumo conocido) y la
>    cota superior del denominador (conocido + cotas; infinita si en su ámbito hay un intento sin
>    cota). Si su cociente ya supera el factor, la condición es **«excede»** y el resultado de cuota
>    es **certificado**, aunque haya intentos sin cota.
> 2. **Estimada.** Si no, y en el ámbito de la condición hay algún intento sin cota, la condición se
>    calcula con conocido + cotas + estimaciones empíricas y se publica como **«estimada»: no
>    garantizada**.
> 3. **Certificada.** Si no hay ningún intento sin cota en su ámbito, la condición es «cumple» o
>    «excede», **certificada**.
>
> - El veredicto de cuota es **«certificada · excede»** si alguna condición queda en el caso 1, o en
>   el caso 3 con «excede».
> - Si no, es **«estimada»** si alguna condición queda en el caso 2, con el resultado estimado y el
>   aviso.
> - En cualquier otro caso es **«certificada · cumple»**.
> - Una subida de más del 10 % sin mejora atribuible deja el veredicto de cuota en «excede»
>   (certificado o estimado, según los consumos de los que dependa).
> - El aviso literal de la cuota estimada es: «Cuota estimada: hubo N intentos de consumo desconocido
>   sin cota; la cifra incluye una estimación empírica no garantizada y no certifica el techo».

### 4.5 §6.4 · Veredicto global → Veredictos de calidad y de cuota

**Actual:**

> ### 6.4 Veredicto global
>
> 0.4 **aprueba** si cumple todo §6.1, no tiene ninguna `regresion` en §6.2 y cumple §6.3. Una sola
> fila roja reprueba (como en `eval/compare.py`): las métricas no se compensan entre sí. Si falta
> evidencia (salidas sin juzgar, discordancias sin resolver, techo no certificable, banco suspendido),
> el veredicto es **«no certificable»**, que no es lo mismo que aprobar.

**Nuevo:**

> ### 6.4 Veredictos de calidad y de cuota
>
> El banco emite **dos veredictos separados** y los publica juntos. Ninguno se deduce del otro.
>
> - **Calidad.** 0.4 **aprueba** en calidad si cumple todo §6.1 y no tiene ninguna `regresion` en
>   §6.2.
>   - Una sola fila roja reprueba (como en `eval/compare.py`): las métricas no se compensan entre sí.
>   - Si falta evidencia de calidad o de identidad (salidas sin juzgar, discordancias sin resolver,
>     fallo sin texto, banco suspendido), el veredicto de calidad es **«no certificable»**.
>   - **Un intento de consumo sin cota no es falta de evidencia de calidad:** solo cuenta por sus
>     efectos propios (turno no completado, fallo sin texto, juicio incompleto).
> - **Cuota.** Lo fija §6.3: «certificada · cumple», «certificada · excede» o «estimada», con el
>   consumo conocido, la estimación empírica no garantizada y el aviso.
> - El resultado nunca se publica como un único «aprueba» si la cuota no es «certificada · cumple».
>   Qué combinación habilita la entrega de 0.4 es una decisión de producto, que se toma con los dos
>   veredictos a la vista.

### 4.6 §9.7 · Publicación

**Se añaden**, al final de la lista:

> - Los dos veredictos se publican **juntos y separados**: el de calidad, con su rótulo de §8.8, y el
>   de cuota, con su estado («certificada» o «estimada»).
> - Una cuota «estimada» se publica con el consumo conocido, la estimación empírica de cada intento
>   sin cota (con sus componentes, la versión de la regla y la instantánea), el número de intentos
>   sin cota y el aviso literal de §6.3. Nunca se presenta como certificada.

### 4.7 §12.4 · C15

**Actual:**

> - **C15.** Precedencia de veredictos: `no_certificable` > `reprueba` > `aprueba`.

**Nuevo:**

> - **C15 (revisada en v1.4).** La precedencia rige **por veredicto**:
>   - calidad: `no_certificable` > `reprueba` > `aprueba`;
>   - cuota: «certificada · excede» > «estimada» > «certificada · cumple», con la regla de «conocido
>     ya excede» de §6.3.
>
>   Ningún motivo de cuota entra en el veredicto de calidad, ni al revés.

### 4.8 §12.6 · C18

**Actual** (frase central):

> Todo intento fallido bajo un alias `cli-*` (Claude o Codex) se
> registra con consumo desconocido y **sin cota**, y el techo de §3.4 y §6.3 queda no certificable.

**Nuevo:**

> Todo intento fallido bajo un alias `cli-*` (Claude o Codex) se
> registra con consumo desconocido y **sin cota**. Por la decisión de Pipe del 2026-10-12 (§12.7),
> eso deja el veredicto de **cuota** en «estimada», con su estimación empírica no garantizada. No
> hace no certificable la calidad. Para la suspensión de §3.4 cuenta la estimación empírica.

**Se añade al final de C18:**

> «Acotar y medir» (v6 del contrato) quedó **revocada**. Ninguna fórmula de cota de CLI se acepta
> mientras no esté acreditado un límite para **todas** las peticiones de una invocación, sus entradas
> y sus salidas. Una medición del fondo es una estimación empírica, no una cota. El banco no modifica
> el entorno del CLI: no fija ni normaliza los reintentos.

### 4.9 §12.6 · C19

**Actual:**

> - **C19 (consumo desconocido durante el circuito).** Con un intento de consumo desconocido y sin cota,
>   el acumulado es solo una cota inferior: no se lanza ningún intento más de juez ni ninguna llamada
>   Codex de producción. La producción Claude puede seguir, pero el techo queda no certificable y las
>   métricas de calidad que se obtengan se publican con esa fila en «no certificable». **Pendiente de
>   Pipe:** si continuar el juicio tras un consumo desconocido puede hacerse con su aprobación expresa,
>   registrada como la reanudación de §3.4. Mientras no lo decida, la conducta es detenerse.

**Nuevo:**

> - **C19 (consumo desconocido durante el circuito; revisada en v1.4).** Con un intento de consumo
>   desconocido y sin cota, el acumulado conocido es solo una cota inferior: no se compromete ningún
>   intento más de juez ni ninguna llamada Codex de producción hasta una reanudación con la
>   aprobación expresa de Pipe (C27).
>   - La producción Claude puede seguir.
>   - Las métricas de calidad que se obtengan **son certificables** y entran en el veredicto de
>     calidad.
>   - El veredicto de cuota queda «estimada» (§6.3).

### 4.10 §12.7 nueva · Versión banco04-v1.4 (2026-10-12): separar calidad y cuota

> **Motivo.** El dictamen de Astra sobre el contrato de la cadena v6 mostró que la cota propuesta
> para el CLI no era conservadora y que fijar los reintentos alteraba la conducta medida (§1 de la
> propuesta).
>
> **Decisión de Pipe (2026-10-12), «Separar calidad y cuota»,** que revoca «Acotar y medir»: dos
> veredictos.
>
> - La calidad es certificable con intentos sin cota.
> - La cuota es «certificada» (cumple / excede) o «estimada», y «excede» si lo conocido ya excede.
> - El techo gobierna la suspensión con conocido + estimación empírica.
> - La reanudación y C27 siguen igual.
> - El banco no toca el entorno del CLI, y la medición del fondo se conserva como estimación
>   empírica versionada.
> - Codex sigue la misma regla.
>
> **Cambios:** cabecera, §3.4, §5.5, §6.3, §6.4, §9.7, C15, C18 y C19.
>
> **No cambian** la muestra, R, las métricas, los umbrales, las cifras de los techos, los jueces ni la
> custodia.
>
> **C27 (se mantiene; integrada en esta versión).**
>
> - **Decisión de Pipe del 2026-10-12:** «que se reanude con mi autorización». Un consumo
>   desconocido sin cota detiene el juicio y la producción Codex, y solo se reanuda con una
>   referencia de aprobación de Pipe que cubra los eventos ya registrados. Un evento nuevo vuelve a
>   detener.
> - **Garantía de compromiso irrevocable (decisión del director):** el punto de compromiso de una
>   llamada es su `seq_envio`, escrito bajo el cerrojo del circuito.
>   - Una llamada comprometida antes del evento es legítima aunque invoque después.
>   - Lo prohibido es comprometer una llamada después del evento sin una autorización que lo cubra.
>   - Residual declarado: esa llamada puede consumir después del evento.
>
>   Detalle en el contrato de la cadena, §4.2 y §5.

---

## 5 · Preguntas para el director (no las decide esta propuesta)

1. **Combinación de veredictos para la entrega de 0.4.** §6.4 nuevo deja explícito que no hay un
   «aprueba» único si la cuota no es «certificada · cumple». La regla de entrega es una decisión de
   producto que este texto no atribuye a nadie.
2. **C27 en el protocolo.** Esta propuesta la integra como parte de §12.7. Si el director prefiere
   integrarla aparte, la v1.4 solo necesita la referencia.
3. **Exigencia `consumo_certificable` de la validación de los jueces** (`banco04_validar_jueces.py`,
   `evaluar_exigencias`). Bajo v1.4 deja de condicionar la utilidad del circuito y pasa a la cuota.
   Es coherente con §6.4 nuevo, pero toca §8.6 por interpretación: Astra debería confirmarlo.
