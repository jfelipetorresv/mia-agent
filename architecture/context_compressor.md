# architecture/context_compressor.md
# Compresión de contexto (Módulo 2c)
# Última actualización: 2026-06-14

> Estado: 2c entregado. Gate `execution/test_context_compressor.py` **22/22** (offline,
> cliente LLM falso → bloqueo haiku verificado end-to-end). Adaptado de
> `hermes-ref/agent/context_compressor.py` (~2.000 líneas), recortado a lo esencial.
> **2026-06-14:** el resumen pasa a `role="user"` (Riesgo #12 cerrado, decisión #15).

---

## 1 · Parámetros LOCKED (no cambiar)

| parámetro          | valor          | nota                                            |
|--------------------|----------------|-------------------------------------------------|
| `protect_first_n`  | **5**          | primeros 5 mensajes siempre intactos            |
| `protect_last_n`   | **30**         | últimos 30 mensajes siempre intactos            |
| `threshold_percent`| **0.55**       | comprime al superar el 55% de la ventana        |
| modelo de resumen  | **claude-haiku** | `call_llm(task="compression")` — BLOQUEO (decisión #7) |
| idioma del resumen | **español jurídico** | nunca inglés (preamble filter-safe)       |

Hermes parametriza estos valores (sus defaults son 0.50/3/20); Mia fija 0.55/5/30 por
decisión de proyecto. No hay contradicción — solo distintos valores.

---

## 2 · Algoritmo (`agent/context_compressor.py`)

`compress(messages, model_context_window) -> messages`:

1. **Cuenta** tokens del historial (`estimate_tokens` por mensaje + 4 de overhead).
2. Si `tokens < 0.55·ventana` → **no comprime** (devuelve los mensajes intactos).
3. **(B) anti-thrashing**: si las últimas 2 compresiones ahorraron <10% → no recomprime.
4. Si hay bloque del medio (`n > 5+30`):
   a. `frozen_inicio` = primeros 5, `frozen_final` = últimos 30, `medio` = el resto.
   b. **`[VERIFICAR]`**: los mensajes del medio que lo contienen NO se resumen — se
      **mueven al frozen_final** (se preservan verbatim).
   c. El resto del medio se resume con `call_llm(task="compression")` (haiku).
   d. El resumen se inserta como **un mensaje `role="user"`** con prefijo
      `[RESUMEN DE CONTEXTO ANTERIOR]` + marcador de fin. **No `role="system"`**:
      Anthropic toma `system` como parámetro ÚNICO al tope del request y LiteLLM
      hoistea todos los mensajes system al inicio — un resumen system mid-array
      perdería su posición entre cabeza y cola (Riesgo #12, decisión #15). El
      `SUMMARY_END_MARKER` desambigua que el resumen es referencia, no la consulta.
   e. Devuelve `frozen_inicio + [resumen] + [VERIFICAR] preservados + frozen_final`.

### Resumen (haiku, español, estructurado)
Preamble **filter-safe**: trata los turnos como material fuente, NO como instrucciones
a cumplir, y exige ESPAÑOL JURÍDICO. Plantilla de secciones:
`## Hechos jurídicos clave · ## Argumentos construidos · ## Decisiones tomadas ·
## Citas y verificaciones pendientes · ## Estado actual del asunto`.

### (A) Resumen iterativo (decisión #13)
El compresor guarda `_previous_summary`. En la **re-compresión**, en vez de resumir
desde cero, ACTUALIZA el resumen previo (lo incorpora al prompt como "RESUMEN PREVIO")
— así no se pierde el contexto jurídico acumulado en matters largos.

### (B) Anti-thrashing (decisión #13)
`_ineffective_count` cuenta compresiones consecutivas con <10% de ahorro; al llegar a
2, `compress` se vuelve no-op (evita quemar llamadas a haiku sin ganancia).

---

## 3 · Integración con el turno (`agent/core.py`, PASO 2)

`MiaAgent.run_turn` llama al compresor **antes** de cada turno sobre `self.messages`.
Si actuó, loguea el ahorro (`tokens_before → tokens_after`). Es **transparente al
abogado**: no aparece en el stream SSE (§G). El `MiaAgent` lleva `context_window`
(`config.MIA_CONTEXT_WINDOW`, default 200k), `matter_id` y un `trace_capture` opcional;
el `compressor` se arma en `__post_init__`.

> El system prompt (10 capas) se arma aparte y se cachea; la compresión solo toca el
> historial, así que NO invalida el prefix cache.

---

## 4 · Traza (`memory/trace_capture.py`, PASO 3)

Cuando el compresor actúa, escribe un EVENTO en el JSONL del tenant vía
`TraceCapture.capture_event`:

```
{schema:"mia.trace.event.v1", type:"context_compressed", timestamp,
 tenant_id, matter_id, tokens_antes, tokens_despues, ratio_compresion}
```

`ratio_compresion = tokens_despues / tokens_antes`. Se distingue de las trazas de turno
(schema `mia.trace.v1`) por el `schema`/`type`; para SFT se filtran por schema.

---

## 5 · Cómo verificar

```
.venv\Scripts\python.exe execution\test_context_compressor.py   # 22/22 (offline)
```

Gate mínimo (subconjunto): threshold 55% ✓ · protect 5/30 intactos ✓ · compression→haiku
siempre ✓ · [VERIFICAR] nunca comprimido ✓ · resumen en español ✓ · traza actualizada ✓.

---

## 6 · Simplificaciones frente a Hermes (no adoptadas, por diseño)
- **Tail por conteo fijo (30)**, no por presupuesto de tokens (Hermes usa token-budget).
  El spec fija `protect_last_n=30`.
- Sin pruning de tool-results, stripping de imágenes ni saneo de pares tool_call/result:
  el historial de Mia es texto simple (sin tool messages ni imágenes hoy).
- Sin redacción de secretos (el contenido es jurídico, no credenciales). Si en el futuro
  entran datos sensibles al historial, conviene portar la redacción de Hermes.
