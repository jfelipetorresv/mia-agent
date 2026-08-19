# Retrospective: cablear 6 features inertes con orquestación multi-agente

**Date**: 2026-07-17 (sesión 49, tarde)
**File**: retrospective-2026-07-17-002-cablear-features-inertes.md

## Summary

Se ejecutó el backlog completo del handoff de la mañana: las tres capacidades que el abogado
veía "activas" pero por dentro no hacían nada (Banco de oro, Pinecone, MCP), el blindaje del
instalador, la limpieza trivial y —por decisión de Pipe— los atajos de despacho con salud de
guías. **6 metas, 6 commits, cada una con su gate verde y un verificador Opus adversarial
independiente que re-corrió el gate.** Cierre con los dos HALT (`test_rls` 19/19,
`check_env_pins` 10/10) y verificación visual en vivo de las dos pantallas nuevas (PASA).

Método: Opus coordinó; 1 workflow de recon read-only (6 scouts Sonnet) → 4 olas de
implementación en grupos de archivos DISJUNTOS (Sonnet implementa, Opus verifica). El
coordinador (la terminal principal) fue el único que tocó git y preparó los archivos
compartidos.

## Errors Encountered

| Error | Cause | Resolution | Prevention |
|-------|-------|------------|------------|
| `Test-NetConnection` y `netstat` cuelgan el shell (timeout 2 min) | El entorno de shell de esta máquina se congela en sondeos de red del sistema | Sondear puertos con Python `socket.settimeout(1.5)` y HTTP con `curl --max-time` | Nunca usar `Test-NetConnection`/`netstat` para sondear puertos aquí; socket/curl con timeout corto |
| Migración `043` reservada por DOS metas (D y E) | Dos planes del recon reclamaron el mismo número libre | El coordinador reasignó D=043, E=044 antes de implementar | Reservar el número al EMPEZAR y que la asignación la haga el coordinador, no los agentes (ya era regla, Riesgo #73) |
| `ModuleNotFoundError: pinecone` | El conector existía pero el paquete no estaba instalado | `pip install "pinecone>=3"` + declarar en `pyproject` (coordinador) | Un feature "inerte" puede esconder deps faltantes; el recon debe confirmar imports |

## Snags & Blockers

- **Colisión de archivos compartidos entre metas**: `pyproject.toml` (Pinecone+MCP), `api/main.py`
  (routers de C/D/E) y la numeración de migración. Impacto: no se podían correr las 6 en paralelo
  sin corromper el estado. Resuelto ordenando en olas y dejando que el coordinador tocara los
  archivos compartidos.
- **`cosechar-aprendizaje` no aplica a sesiones de código**: es una skill jurídica (corpus, fichas
  A-*/J-*/N-*, un caso cerrado). Snag de enrutamiento de skill; se sustituyó por el protocolo de
  retrospectivas del vault.
- **MCP stdio-live no ejercitable sin LiteLLM**: la sección de ida-y-vuelta real de `test_mcp` hizo
  SKIP honesto (node/npx presentes, LiteLLM `:4000` apagado). Queda para la capa 3 en vivo.

## Workarounds Applied

- **Login sin formulario en la verificación visual**: se inyectó un JWT minteado con `JWT_SECRET`
  en `localStorage.mia_token` vía Playwright headless. Legítimo para verificación; no es una vía de
  producción.
- **Seed de datos para ver atajos/badges**: tenant de demo con 2 guías + 1 persona insertado por
  psycopg directo. Datos de prueba; conviene limpiarlos de la DB portable si estorban.

## Lessons Learned

1. **El patrón recon→olas disjuntas→verificador adversarial funcionó a cero bloqueantes en 6 metas.**
   El recon read-only barato (que clasifica readiness LOCAL vs infra) evita tocar producción a ciegas.
2. **El verificador que RE-CORRE el gate atrapa el "verde inventado".** Vale su costo: en cada meta
   confirmó los números de forma independiente.
3. **Un solo escritor de git + grupos disjuntos + coordinador para archivos compartidos = cero
   corrupción multiagente** (evita el hazard conocido de dos agentes sobre la misma carpeta git).
4. **Delegar el arranque Modo B + Playwright a un subagente aislado protege el contexto**: devuelve un
   veredicto objetivo (tabla de rutas con status/consola/marcadores) en vez de PNGs que inflan el contexto.
5. **Separar lo verificable en local de lo que exige capa 3 en vivo** mantiene honesto el "hecho":
   MCP y Pinecone quedan cableados y probados con dobles/fakes, pero "funciona en vivo" sigue sin verificar.

## Command Improvements

- `/EA-visual-verify`: el fallback headless con token inyectado + veredicto objetivo (tabla por ruta)
  funcionó bien; documentar que en este entorno el sondeo de puertos debe ir por socket/curl, no netstat.
- `/EA-retrospective`: su destino por defecto `docs/retrospectives/` queda anulado por el protocolo del
  vault de Pipe (la retrospectiva canónica va a `01-operacion\retrospectivas\`).

## Process Improvements

- Cuando un feature esté marcado "inerte", el recon debe confirmar **imports y llamadores reales** (no
  solo que el archivo existe) antes de estimar esfuerzo.
- El coordinador reserva números de migración y edita deps/`main.py`; los agentes nunca tocan archivos
  compartidos.

## Metrics

- Metas completadas: 6/6 (+ verificación visual + 2 HALT).
- Commits: 7 (6 features + HANDOFF).
- Bloqueantes de capa 1/2: 0.
- Snags de entorno: 2 (red del shell, deps faltantes) — sin pérdida de trabajo.

## Next Session Recommendations

- [ ] **MCP de punta a punta en vivo**: arrancar Modo B (LiteLLM `:4000`) y re-correr `test_mcp.py`
  para ejercitar la sección stdio-live (e6b-01/02/03).
- [ ] **Pinecone real**: llaves del despacho + índice dim 1024 coseno; hoy verificado con FakeIndex.
- [ ] **Banco de oro de punta a punta** y **delegación D3** (Riesgo #66) en vivo.
- [ ] **`list_shortcuts` (atajos)**: reservar cupo para 1-2 agentes cuando hay ≥6 guías activas (ajuste de una línea, decisión de Pipe).
- [ ] Limpiar el tenant de demo `VISUAL_VERIFY Lexia Demo` de la DB portable si estorba.
