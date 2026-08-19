# CIERRE — 2026-08-04 (sesión 54) · El recorrido de primera vez, automatizado: 3 corridas verdes

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; la DB portable (55432) vive en
> `..\tools\pgdata-portable`. Para el E2E del recorrido: los 4 servicios arriba, luego
> `.venv\Scripts\python.exe e2e\generar_expediente.py` (una vez) y
> `node e2e\recorrido_primera_vez.mjs --corrida N` (~25-30 min por corrida). Detalle en
> `architecture/e2e_runbook.md` §0-bis y bitácora en `validation/validation-log.md`.

Rama `feat/fase1-inc1-cleanup-scaffolding`. Repo limpio tras `af49c19` + este cierre.

## Tres commits de PIPE entre la 53 y esta (confirmado por él, 2026-08-04)

`f264b1e` (principios Lexia en el grafo), `e7ff81b` (gobierno de vaults) y `f52c945` (rediseño
«Neumorfismo Pro») los hizo Pipe desde otra herramienta y LOS QUIERE — no revertir. Esta sesión
trabajó sobre ese estado y el recorrido completo pasó en verde encima del rediseño. Queda solo
una revisión técnica ligera de lo que tocaron en `graph.py`/`prompt_builder.py` (calidad, no
permanencia).

## Qué pasó en esta sesión (2026-08-04, 54ª)

**El punto 1 de «Qué sigue» de la 53, cerrado**: el E2E automatizado de la primera vez existe,
corrió 3 veces consecutivas en verde sin intervención manual, y quedó medido y archivado.

- **`e2e/recorrido_primera_vez.mjs`** (Playwright) recorre register → activar (auto-salto en
  dev) → onboarding (7 pasos, ficha de país incluida) → asunto → expediente → pregunta →
  borrador → gate de citas → aprobar → sonda del `## aprendido`. Screenshot por paso +
  `tiempos.json` en `validation/screenshots/corrida-N/`.
- **`e2e/generar_expediente.py`**: el expediente sintético FIJO que exige la spec, derivado del
  caso de oro voluminoso (3 .txt, 252 fragmentos) — versionado como código, no como binarios.
- **Medición (política suscripción)**: 30,1 / 28,6 / 23,3 min → **p50 28,6 · p95 ≈ 30,0**. El
  95 % es el turno del grafo. `tsc` 0 errores; test_rls, test_gates_no_ciegos y check_env_pins
  PASAN. El `## aprendido` se pobló en las 3 corridas. El muro se vio funcionar de punta a
  punta (el borrador declara sus citas pendientes y el gate exige la decisión del abogado).

## Defectos y hallazgos destapados (los tests no los veían; la pantalla sí)

1. **DEFECTO UI-A (abierto, reproducible 5/5)**: a 1440×900 el aside derecho del asunto tapa el
   botón «Revisar borrador» y le intercepta el clic. Un abogado con esa pantalla no puede
   pulsarlo. El E2E lo rodea (navega directo a `/revisar`) y lo avisa en su salida. **Es el
   candidato #1 a primera tarea de la próxima sesión.**
2. **Lentitud señalable**: el motor de la suscripción agota su timeout (~13 min) con el caso
   voluminoso y salta a claude-sonnet — turnos de 20-28 min. Y `POST /draft/approve` corre el
   cierre del grafo sincrónico: 81-100 s de espera tras el clic en Aprobar.

## Qué sigue (en orden, sin necesitar a Pipe)

1. **Arreglar el DEFECTO UI-A** (el aside sobre «Revisar borrador») y re-correr el E2E.
2. **Revisión técnica ligera de los 3 commits de Pipe** (`f264b1e`, `e7ff81b`, `f52c945`):
   son deseados y se quedan; solo verificar calidad de lo que tocaron en grafo y prompt.
3. Checklist de honestidad de UI por paso (la otra mitad de la salida medible de F3).
4. Producto (plan maestro): lo que quede de F3.

## Pendientes de Pipe (sin cambios desde la 53)

- Prueba del instalador en máquina limpia (el instalador NO se ha re-ensamblado desde la 52).
- Lectura de las 6 salidas de `docs/f1-paquete-decision-pipe.md`.
- Azure Trusted Signing y registro de apps OAuth (`docs/tramites-terceros-pipe.md`).
- Decidir sobre el alcance (leer más cuesta crédito de tarjeta).

---
