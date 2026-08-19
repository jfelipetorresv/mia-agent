# CIERRE — 2026-07-17 (tarde), sesión 49 — las 3 features inertes + instalador + atajos: CABLEADAS

## Qué se hizo esta sesión
Se ejecutó, con orquestación multi-agente dinámica (Opus coordina, Sonnet implementa,
Opus verifica adversarial), **todo el backlog de metas del handoff de la mañana**: las tres
capacidades que el abogado veía "activas" pero por dentro no hacían nada (Banco de oro, Pinecone,
MCP), el blindaje del instalador, la limpieza trivial y — por decisión de Pipe — los atajos de
despacho con salud de guías. **6 commits, uno por meta, repo con 6 commits nuevos sobre `fe1ecab`.**

Método: 1 workflow de recon read-only (6 scouts) + 4 olas de implementación en grupos de archivos
DISJUNTOS; el coordinador (esta terminal) fue el único que tocó git y preparó los archivos
compartidos (`pyproject.toml`, numeración de migraciones). Cada meta con su gate verde y un
verificador Opus independiente que RE-CORRIÓ el gate antes de aprobar.

## Las 6 metas (commit · gate)
- **C — Banco de oro al examen** (`e4e921b`): `run_full_suite()` suma los casos confirmados del
  despacho a los sintéticos; `POST /gold-cases:evaluate` gated por `allow_eval_real_data`. Gate
  `test_gold_cases_influence_eval` 11/11 + regresión eval 25/25, gold_cases_api 57/57.
- **F — limpieza** (`9be48e9`): borrada `gepa_run_all_tenants()` huérfana. Gates gepa/dreams/curator/feedback verdes.
- **A — Pinecone store secundario** (`e5c9cfe`): espejo `upsert/delete/query` opt-in por despacho,
  aislado por namespace de tenant, **fail-soft total** (si falla, sigue pgvector), solo espeja
  conocimiento del despacho, **nunca el expediente**. Gate `test_pinecone_wiring` 23/23 + connector 16/16.
- **B — MCP consumidor real** (`75a59bd`): `mcp/client.py` (stdio en sandbox por tenant) +
  `mcp/turn.py` (sub-turno de tools) + `graph._mcp_context` (salida SELLADA `[VERIFICAR]`). Muro:
  `soberano` BLOQUEA antes de lanzar el subproceso. Fail-soft en 5 capas. Gate `test_mcp` 39/39.
- **D — blindaje instalador** (`062adc3`): `/health` reporta migraciones aplicadas vs esperadas +
  checkpointer (migración **043**); la cáscara Tauri frena con mensaje en llano si la base no terminó
  de actualizarse; backups rotan a 3. Gate `test_first_run` 71/71, backup/maintenance/config_anchor verdes, `cargo check` exit 0.
- **E — atajos + salud de guías** (`c0df832`, decisión de Pipe = "las dos completas"): chips de un
  clic en el chat vacío que **pre-llenan** el mensaje (consent-first, nunca auto-envían) reusando
  guías/personas del despacho; badge sana/revisar por guía (migración **044**, fail-open). §G
  validado string por string. Gates `test_playbook_health` 29/29, `test_despacho_atajos` 17/17, `tsc` exit 0.

## Estado de verificación
- **Capa 1:** cada meta con su gate verde (arriba). **HALT re-corridos al cierre sobre el estado
  final acumulado: `test_rls` 19/19, `check_env_pins` 10/10.** NO se corrió la regresión completa (no cabe).
- **Capa 2:** un verificador Opus adversarial independiente por meta, que re-corrió cada gate. 0 bloqueantes.
- **Capa 3 (en vivo): PENDIENTE — de Pipe.** Nada probado con MIA encendida.

## Pendientes y próximo paso (capa 3 de Pipe)
1. **MCP de punta a punta EN VIVO** (lo más importante): la sección `stdio-live` de `test_mcp`
   (ida-y-vuelta real, guard de soberano sin subproceso, sin proceso huérfano) hizo **SKIP honesto**
   porque LiteLLM `:4000` no estaba arriba. Node/npx SÍ están. Falta: arrancar Modo B y re-correr
   `test_mcp.py` para ejercitar e6b-01/02/03.
2. **Pinecone en vivo:** las llaves reales del despacho + un índice dim 1024 coseno; hoy verificado
   con índice falso (FakeIndex). El opt-in y el fail-soft ya están; falta la escritura/lectura real.
3. **Banco de oro de punta a punta** y **delegación D3** (Riesgo #66) siguen pendientes de vivo.
4. **Ajuste opcional (no bloqueante, decisión de Pipe):** `memory/atajos.py::list_shortcuts` corta a
   6 guías por uso ANTES de anexar personas → con ≥6 guías activas los agentes del despacho no salen
   como chips. Si Pipe quiere cupo garantizado para 1-2 agentes, es un ajuste de una línea.

## Decisiones tomadas
- **Pipe — meta E completa** (atajos + salud de guías), elegido en sesión sobre "solo salud" o "diferir".
- **Coordinación de archivos compartidos por el coordinador** (no por los agentes): `pyproject.toml`
  (declara `pinecone>=3` y `mcp>=1.10,<2`), y la numeración de migración (D=043, E=044) para evitar
  el choque del `038` de la sesión 48. Un solo escritor de git.
- **Pinecone NO externaliza el expediente** (solo `knowledge_chunks`): elección de confidencialidad,
  no se mandan documentos de casos a un cloud sin que nadie lo pida.

---

