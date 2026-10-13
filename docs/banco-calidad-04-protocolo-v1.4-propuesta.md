# Banco de calidad 0.4: propuesta de protocolo banco04-v1.4 (cambios exactos sobre v1.3)

Estado: **propuesta** para la revisión de Astra. **No** modifica `docs/banco-calidad-04-protocolo.md`;
el director integra este texto después de la revisión. Mientras tanto rige banco04-v1.3.

Fecha: 2026-10-12. Base: `docs/banco-calidad-04-protocolo.md` en banco04-v1.3, sin cambios desde
`f5d678b`. La acompaña el contrato `docs/banco04-cadena-contrato.md` (banco04-cadena/v8).

**Revisión 2 de la propuesta** (tras el dictamen de Astra sobre la v7,
`r4/veredicto_contrato7.md`):

- la cuota se decide **por intervalo** (§4.4 y §4.7);
- la piloto no invalida la calidad por consumo (§4.2);
- se añaden los textos viejos que faltaban (§4.11 a §4.17);
- se hace el barrido completo del protocolo (§5).

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
> conservadora, para detener antes. Para eso se usa su **estimación empírica inicial congelada**
> (§5.5). Esa suma nunca certifica la cuota (§6.3).

**Actual** («Tanda piloto»):

> repetición 1. Con su consumo medido se proyecta el circuito completo.

**Nuevo:**

> repetición 1. Con su consumo se proyecta el circuito completo: lo conocido, más las cotas finitas,
> más la **estimación empírica inicial congelada** (§5.5) de cada intento sin cota. Esa
> estimación y su conjunto de observaciones quedan registrados en la decisión de R, que se reproduce
> con ellos.
>
> Un intento sin cota en la piloto **no** hace no certificable la calidad ni la decisión de R. La
> selección de aprobaciones sigue siendo la reproducible, y se exigen todas las repeticiones 1..R de
> la R decidida.

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
> - **Estimación inicial congelada.** Se calcula al cerrar el intento con un **corte de secuencia**:
>   solo entran las llamadas conocidas cerradas antes del corte. El conjunto de observaciones usado
>   queda registrado.
>   - Esa es la estimación que sirve para suspender (§3.4) y para decidir R.
>   - Al decidir se publica además una **actualización final** con todas las observaciones del
>     bloque, que no se compara con la inicial: un máximo posterior mayor no es una contradicción.
> - Las dos se publican. **Ninguna certifica.**

**Actual** («Consumo agregado por caso»):

> `consumo_agregado_caso` = **suma** de los
>   tokens de las R corridas del turno, más los de la aprobación de ese caso. Incluye la cota
>   conservadora de los intentos fallidos.

**Nuevo:**

> `consumo_agregado_caso` = **suma** de los
>   tokens de las R corridas del turno, más los de la aprobación de ese caso. Es un **intervalo**:
>   el mínimo es lo conocido y el máximo es lo conocido más las cotas finitas, o infinito si hay un
>   intento sin cota (§6.3). `consumo_max_corrida` es también un intervalo, por la misma regla.

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

> **Veredicto de cuota, por intervalo.** El techo de esta sección y la atribución de subidas forman
> el **veredicto de CUOTA**, separado del de calidad (§6.4).
>
> - **Consumo como intervalo.** Cada consumo es un intervalo `[mínimo, máximo]`. El mínimo es lo
>   conocido. El máximo es lo conocido más las cotas finitas, o infinito si hay un intento sin cota.
> - **Cociente** de dos intervalos: mínimo = mínimo del numerador / máximo del denominador; máximo
>   = máximo del numerador / mínimo del denominador. El total ponderado por caso promedia por
>   separado los mínimos y los máximos de los casos.
> - **Estado de cada condición «≤ umbral»:**
>   1. **«certificada · cumple»** solo si el **máximo** posible cumple;
>   2. **«certificada · excede»** solo si el **mínimo** posible excede;
>   3. **«estimada»** si el intervalo **cruza** el umbral. Se publican el intervalo, la estimación
>      empírica y el aviso de que no es garantía. Vale **también con cotas finitas y sin ningún
>      intento sin cota**.
>
> - El veredicto de cuota es **«certificada · excede»** si alguna condición queda en el caso 2.
> - Si no, es **«estimada»** si alguna queda en el caso 3.
> - Si no, es **«certificada · cumple»**.
> - *Ejemplo:* nueva = 100 conocidos y base = 10 conocidos más un intento con cota 90 (real 1).
>   Cociente [100/100, 100/10] = [1, 10], que cruza 1,25: «estimada», nunca «certificada · cumple».
>   A la inversa, un numerador con una cota sobredimensionada da un intervalo que cruza, y nunca un
>   falso «excede».
> - Una subida de más del 10 % sin mejora atribuible deja el veredicto de cuota en «excede»
>   (certificado o estimado, según los consumos de los que dependa).
> - El aviso literal de la cuota estimada es: «Cuota estimada: el consumo real está en el intervalo
>   publicado y cruza el umbral; la cifra puntual es una estimación empírica no garantizada y no
>   certifica el techo».

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
>   - cuota: «certificada · excede» (algún mínimo excede) > «estimada» (algún intervalo cruza) >
>     «certificada · cumple» (todos los máximos cumplen), por intervalo (§6.3).
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
>   El director la aplica por intervalo (§6.3): solo se certifica lo que el intervalo garantiza.
> - El techo gobierna la suspensión con conocido + estimación empírica.
> - La reanudación y C27 siguen igual.
> - El banco no toca el entorno del CLI, y la medición del fondo se conserva como estimación
>   empírica versionada.
> - Codex sigue la misma regla.
>
> **Cambios:** cabecera, §3.4, §4.1, §5.5, §6.3, §6.4, §8.8, §9.7, §10.2.10, §10.2.13 (P9, P10 y
> P11), nota a P10 de §12.1, C15, C18, C19 y C24.
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

### 4.11 §4.1 · Qué texto se juzga

**Actual:**

> Una corrida sin texto completo (`harness.evidence_audit`) cuenta como corrida faltante y bloquea la
> certificación.

**Nuevo:**

> Una corrida sin texto completo (`harness.evidence_audit`) cuenta como corrida faltante y bloquea la
> certificación **de calidad** (§6.4). No tiene efecto sobre la cuota, salvo por el consumo que
> haya registrado.

### 4.12 §8.8 · Rotulación (delimitada a CALIDAD; CUOTA distinguida)

**Actual:**

> Todo número publicado lleva uno de estos dos rótulos:
>
> - «Evaluación automática (Opus high y Codex en cribado doble, adjudicación por mayoría)»;
> - «… calibrada con revisión humana ciega (n = 10)».
>
> Nunca se publica como «validado por abogado» ni como «certificado».

**Nuevo:**

> Todo número **de calidad** publicado lleva uno de estos dos rótulos:
>
> - «Evaluación automática (Opus high y Codex en cribado doble, adjudicación por mayoría)»;
> - «… calibrada con revisión humana ciega (n = 10)».
>
> Un número de calidad nunca se publica como «validado por abogado» ni como «certificado».
>
> **La cuota es distinta.** No es una evaluación de los jueces sino un recuento de consumo, y lleva
> su propio rótulo: **«cuota certificada»** solo si el intervalo lo garantiza, o **«cuota
> estimada»**, con el aviso de §6.3. «Certificada» aplicado a la cuota significa únicamente que el
> intervalo de consumo garantiza el resultado. No es una certificación de la calidad, ni de un
> abogado, ni de un tercero.

### 4.13 §10.2.10 · Métricas y veredicto

**Actual:**

> Cubre §5, §6.1, el bootstrap
>     por casos de §6.2, el techo en tres niveles de §6.3, la matriz de §7.2, las cotas de §3.3 y el
>     veredicto «aprueba / reprueba / no certificable».

**Nuevo:**

> Cubre §5, §6.1, el bootstrap
>     por casos de §6.2, el techo en tres niveles de §6.3, **por intervalo**, la matriz de §7.2, las
>     cotas de §3.3 y los **dos** veredictos: calidad «aprueba / reprueba / no certificable» y cuota
>     «certificada · cumple / certificada · excede / estimada».

### 4.14 §10.2.13 · Gates (P9, P10 y P11)

**Actual:**

>     - los ejemplos {100 ×4, 10 000 ×3} y {100, 100, 100, 10 000, 10 000} reprueban el techo aunque
>       la mediana no cambie (P9);

**Nuevo:**

>     - los ejemplos {100 ×4, 10 000 ×3} y {100, 100, 100, 10 000, 10 000} dan cuota «certificada ·
>       excede» aunque la mediana no cambie, sin afectar a la calidad (P9);

**Actual:**

>     - un intento fallido sin cota hace el techo no certificable (P10);
>     - el contador alcanza el techo, suspende y publica «incompleto — no certificable» (P11);

**Nuevo:**

>     - un intento fallido sin cota deja **la cuota** «estimada», con máximo infinito en su ámbito,
>       y **no** hace no certificable la calidad. Un intento con una cota finita que cruza el umbral
>       también deja la cuota «estimada». El contraejemplo «nueva 100; base 10 + cota 90» nunca da
>       «certificada · cumple», y un numerador sobredimensionado nunca da un falso «excede» (P10, v1.4);
>     - el contador (conocido + cotas + estimación empírica inicial) alcanza el techo, suspende y
>       publica «incompleto — no certificable» en la calidad y la cuota por separado (P11);

### 4.15 §12.1 · Registro de P10 (nota, sin reescribir el histórico)

La tabla de §12.1 es el registro de la ronda 1 y no se reescribe. Al final de la fila **P10** se añade:

> *(v1.4: un intento sin cota ya no deja el techo «no certificable»; deja la cuota «estimada» por
> intervalo, §6.3, y no afecta a la calidad.)*

### 4.16 §12.6 · C24

**Actual** (frase central):

> exige las repeticiones exactas 1..R por
>   versión y caso, consumo de los 17 casos en las dos versiones y pares completos, y recalcula las
>   comparativas desde los casos agregados de 0.3.3 y 0.4 con su semilla. Toda ausencia es
>   `no_certificable`.

**Nuevo:**

> exige las repeticiones exactas 1..R por
>   versión y caso, **los registros** de consumo de los 17 casos en las dos versiones y pares
>   completos, y recalcula las comparativas desde los casos agregados de 0.3.3 y 0.4 con su
>   semilla. Toda ausencia **de registros** es `no_certificable` en calidad (identidad y
>   completitud). Un intento sin cota no es una ausencia de registro: entra en la cuota por
>   intervalo (§6.3).

### 4.17 §12.6 · C19: habilitación del circuito de jueces

**Se añade al final de C19:**

> De las exigencias que habilitan el circuito de jueces (§8.6) se retira **solo** la de consumo
> certificable. Siguen exigidos:
>
> - el contador compartido, con la suspensión y la reanudación de C27;
> - cero salidas sin evaluar;
> - cero discordancias sin resolver;
> - la acreditación del reservado.
>
> El consumo de la validación entra en la cuota.

---

## 5 · Barrido del protocolo v1.3 (búsquedas `certific`, `techo`, `no_certificable` y «no certificable»)

Se recorrió todo `docs/banco-calidad-04-protocolo.md`. Cada aparición queda clasificada:

| Línea (v1.3) | Texto | Clasificación |
|---|---|---|
| 53 | «No certifica proveedores» | ajena a la cuota; sin cambio |
| 230, 232 | techos de 32 M y 8 M (autorización) | cifras; sin cambio |
| 253-273 | §3.4, techos duros, reserva, piloto | **cambia** la medición del acumulado y la piloto (§4.2) |
| 275-281 | §3.4, suspensión e «incompleto — no certificable»; «un resultado incompleto nunca se certifica» | **cambia** el primer punto (§4.2); el resto sigue: lo incompleto no se certifica en calidad |
| 292 | §4.1, «bloquea la certificación» | **cambia** (§4.11): calidad |
| 455 | §5.5, `consumo_agregado_caso` «incluye la cota conservadora» | **cambia** (§4.3): intervalo |
| 467-468 | §5.5, «el techo queda no certificable» | **cambia** (§4.3) |
| 470-471 | §5.5, cuota de los jueces en el techo del circuito | sin cambio |
| 559 | §6.2, extensión «dentro del techo (§3.4)» | sin cambio (presupuesto del circuito) |
| 576-599 | §6.3 | **cambia** (§4.4): intervalo |
| 601-606 | §6.4, «techo no certificable» | **cambia** (§4.5) |
| 632 | «techo de lectura» (#82) | ajena (lectura, no cuota) |
| 832, 886, 933 | jueces: «no certifica», «no certificable por discordancia», «no certifican el cero» | calidad; sin cambio |
| 937-942 | §8.8, «nunca … certificado» | **cambia** (§4.12): delimitado a calidad |
| 1042 | §9.7, «no certificable se publica como tal» | sin cambio; se complementa (§4.6) |
| 1066, 1082 | §10.2.1 y §10.2.6, constantes y contador | sin cambio |
| 1092-1093 | §10.2.10 | **cambia** (§4.13) |
| 1112 | P9 «reprueban el techo» | **cambia** (§4.14) |
| 1126 | P10 «hace el techo no certificable» | **cambia** (§4.14) |
| 1127 | P11 | **cambia** (§4.14) |
| 1144, 1148 | §11, decisiones 3 y 4 de Pipe | registro histórico; sin cambio |
| 1182, 1184, 1196, 1211, 1216 | registros de P9, P11 y de la ronda 2 | registro histórico; sin cambio |
| 1183 | registro de P10 | nota añadida (§4.15) |
| 1258 | C15 | **cambia** (§4.7) |
| 1277, 1289 | §12.5 y §12.6: «no cambian … los techos» | sin cambio (cifras) |
| 1296 | C18 | **cambia** (§4.8) |
| 1305-1306 | C19 | **cambia** (§4.9 y §4.17) |
| 1312 | C20, «techo Codex menos la reserva» | sin cambio |
| 1344 | C24, «Toda ausencia es `no_certificable`» | **cambia** (§4.16): registros |
| 1357-1361 | límites declarados de la ronda 2 | registro histórico; sin cambio |

No queda ningún otro texto que haga no certificable el techo ni que lleve la falta de cota a la
calidad.

---

## 6 · Preguntas para el director (no las decide esta propuesta)

1. **Combinación de veredictos para la entrega de 0.4.** §6.4 nuevo deja explícito que no hay un
   «aprueba» único si la cuota no es «certificada · cumple». La regla de entrega es una decisión de
   producto que este texto no atribuye a nadie.
2. **C27 en el protocolo.** Esta propuesta la integra como parte de §12.7. Si el director prefiere
   integrarla aparte, la v1.4 solo necesita la referencia.
3. ~~Exigencia `consumo_certificable` de la validación de los jueces.~~ Resuelta: Astra la confirmó
   en su dictamen sobre la v7 (e), y queda explícita en §4.17. Se retira solo ese predicado.
