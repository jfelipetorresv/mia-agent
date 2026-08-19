# CIERRE — 2026-08-08 (sesión 56) · Circuit-breaker de la suscripción + el approve medido de verdad · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para el E2E: los 4 servicios arriba y
> `node e2e\recorrido_primera_vez.mjs --corrida N`. Detalle en `architecture/e2e_runbook.md`
> §0-bis y bitácora en `validation/validation-log.md`.

Rama `feat/fase1-inc1-cleanup-scaffolding`, repo limpio tras este cierre.

## Qué pasó en esta sesión (2026-08-08, 56ª)

Los dos frentes que dejó la 55, cerrados — uno con código y otro con medición honesta:

1. **Circuit-breaker por TURNO del motor de suscripción** (`backend/mia/agent/llm.py`). El
   salto rápido de la s52 evitaba reintentos dentro de UNA llamada, pero cada nodo del grafo
   volvía a intentar la suscripción y volvía a pagar hasta 300 s — 2-3 nodos ≈ los ~13 min
   medidos. Ahora el primer timeout de un alias `cli-*` lo marca AGOTADO por el resto del
   turno (ContextVar atado a `recolectar_cambios_de_motor`, la frontera del turno): los nodos
   siguientes saltan directo al respaldo. Por ALIAS (que `cli-claude` no aguante el expediente
   no condena a `cli-claude-haiku`), muere con el turno, y cada salto queda contado en el
   aviso de costo. Si el alias agotado es el ÚLTIMO de la cadena se intenta igual (mejor tarde
   que sin respuesta). Gate: `test_cambio_de_motor_aviso.py` §3-bis (46/46) — ejerce `call_llm`
   completo con la cadena real: 3 nodos, un solo timeout pagado, turno nuevo reintenta.

2. **El approve de ~90 s NO era lo que el plan creía — y no se movió código a ciegas.** El plan
   decía «mover sellos + index_trace a background». Medido: con el despacho demo el approve
   entero tarda 0,7 s; en la corrida 5 REAL, 1,8 s de punta a punta (servidor: grafo 0,2 s;
   capture 0,1 + index 0,1 + sellos 0,0). Los 91,5 s de la corrida 4 fueron circunstancia del
   entorno (ese día TODO estuvo lento: turno 20,7 min vs 8 min hoy con el mismo expediente).
   Lo que queda es la BARRERA: instrumentación permanente de tiempos por etapa en
   `hitl._resume` (`resume(...): abrir/estado/grafo`) y `finalize_node`
   (`finalize(...): capture/index/sellos`) — la próxima regresión se LEE en el log del
   backend, no se investiga. Descartados en el camino: nodo HITL re-ejecutando trabajo al
   reanudar (interrupt es la primera línea), tareas de fondo bloqueando el loop (usan
   to_thread), y el path de edición disfrazado (el E2E aprueba sin editar).

## Corrida 5 del E2E — VERDE (la más rápida de la serie)

| corrida | total | turno | aprobar | ## aprendido |
|---|---|---|---|---|
| 4 (s55) | 22,8 min | 20,7 min | 91,5 s | poblado |
| **5 (s56)** | **8,7 min** | **8,1 min** | **1,8 s** | poblado |

El turno entero corrió EN LA SUSCRIPCIÓN sin un timeout ni un salto de motor. Ojo: n=1, el
motor estuvo notablemente más rápido hoy — no se afirma mejora de p50 con una corrida.

## Gates del cierre

test_rls 19/19 · test_gates_no_ciegos 9/9 · check_env_pins 12/12 · test_cambio_de_motor_aviso
46/46 · test_llm_fallback 25/25 · test_model_policy 43/43 · test_citation_seals 14/14 ·
test_aprendido 34/34 · test_seed_despacho_demo 17/17 (despacho demo RE-SEMBRADO después) ·
test_e2e 58/58. `test_hitl_flow` 20/21: FAIL PREEXISTENTE (idéntico en `f2266ad` limpio,
verificado con stash) — riesgo #86 en bugs-and-risks, parece check desactualizado frente al
grafo post-F0-F2.

## Pendientes que siguen

- **De Pipe (de la s55, sigue abierto)**: ¿muro + gate LLM (como está) o solo muro? El gate
  gasta un turno de modelo por borrador.
- **Sesión 57**: riesgo #86 (check desactualizado de test_hitl_flow, barato); F3 del plan de
  eficiencia (función→nivel) y F4 (memoria progresiva); residuos F0-F2 (KPI sellos en panel,
  extractos por rol, caché ficha).

---

