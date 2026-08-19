## Checkpoint más reciente: Sesión 47 (2026-07-13/14) — Sala de estrategia (War Room) + OpenRouter como motor propio/respaldo

> Sesión que RETOMÓ tras un "error del computador". Diagnóstico: NO se dañó el repo de MIA
> (`mia/.git` intacto y sincronizado); lo dañado fue un `.git` fantasma y vacío en la carpeta
> contenedora `Mia-Super Agent/` (un `git init` viejo, sin remoto), que se limpió. Regla para el
> futuro: el repo de trabajo es `mia/`, no la raíz — usar `git -C mia`.

### Qué se hizo esta sesión (lenguaje simple)

Dos features nuevas, en paralelo, con orquestación multi-agente (recon → ejecución → auditoría
adversarial → corrección), ambas pusheadas a `main`:

- **Sala de estrategia (commit `e8bcc51`)** — pivote de la apuesta #2 de NotebookLM (era un
  podcast de audio; Pipe lo giró a un **debate ESCRITO** tipo "War Room"). En un ASUNTO con
  expediente, el abogado convoca un panel de 3-4 counsel con posturas OPUESTAS (defiende tu tesis
  / contraparte / juez escéptico / especialista); cada uno analiza el caso citando el expediente
  `[doc n]`, se contrastan en una ronda de réplicas, y un moderador sintetiza un dictamen
  (fortalezas / riesgos / puntos ciegos / estrategia / próximo paso). **Decisiones de Pipe:** MIA
  propone el panel y el abogado lo ajusta; salida = conclusiones arriba + debate desplegable
  abajo; cierre = dictamen + botón "convertir en borrador" (pasa por el gate de citas y HITL
  normales); solo ASUNTOS; nombre de cara al abogado = "Sala de estrategia" (§G, nunca "agente").
  Reutiliza personas.Persona, delegation.run_parallel (patrón research_swarm),
  untrusted.render_documents y verification.annotate_draft en CADA intervención y la síntesis.
- **OpenRouter como motor propio + respaldo (commit `b582541`)** — el abogado conecta su propia
  cuenta de OpenRouter (y la carga de crédito) para usar MIA (1) como MOTOR PRINCIPAL (política
  nueva "openrouter", para despachos sin la suscripción del equipo) y (2) como RESPALDO/overflow
  (en "suscripción"/"nube", con opt-in `allow_openrouter`). Validación en vivo de la clave en
  `/activar` (4ª opción de motor) + activación en caliente.

### Frontend a revisar (Cursor/Pipe — capa 3)

- **Sala de estrategia (TODO NUEVO):** `frontend/app/asuntos/[id]/page.tsx` (botón "Convocar Sala
  de estrategia" en la barra de acciones + estado del stream) y `frontend/app/asuntos/[id]/
  _components/SalaEstrategia{Dialog,Result}.tsx` + `warroom-types.ts`. Recorrido: en un asunto CON
  expediente, convocar la sala → ajustar el panel → ver el debate en vivo (rondas) → dictamen con
  conclusiones + debate colapsable → "Descargar en Word" y "Convertir en borrador". Sin expediente
  debe mostrar aviso en llano (no error mudo).
- **OpenRouter:** `frontend/app/activar/page.tsx` — la 4ª tarjeta de motor "Tu cuenta de
  OpenRouter" con su campo de clave (✓ en vivo) y, en otras políticas, el campo opcional "más uso".

### Resultado de verificación (3 capas)

- **Capa 1 (regresión, DB dev en 55432):** test_warroom **52/52**, `test_rls` **19/19** (HALT,
  +7 checks nuevos de `warroom_results` con RLS fail-closed), `check_env_pins` **9/9** (HALT),
  test_doc_citation_guard **19/19**, CP9 test_document_pipeline **45/45**, test_openrouter_policy
  **16/16**, test_welcome_keys **41/41**, test_litellm_packaging **66/66**, test_model_policy
  **40/40**, test_llm_fallback **25/25**, test_agent_core **26/26**. `tsc --noEmit` verde; `npm run
  build` compila 15/15 páginas (queda un flake ambiental de Windows al generar `500.html`, ajeno
  al código — se reproduce en árbol pristine).
- **Capa 2 (DOS auditorías adversariales independientes):** 0 BLOQUEANTES. **Sala:** aislamiento
  entre despachos y gate de citas OK; 2 mayores + 5 menores corregidos (réplicas desalineadas ante
  fallo parcial de un panelista; error invisible sin expediente; inyección de 2º orden entre
  intervenciones ahora SELLADA con `untrusted.fence_block`; degradación por presupuesto funcional
  a 0.85 del tope; clamp del tamaño de panel en el SSE; agentes reales sin clonar "defensor";
  cobertura RLS de la tabla nueva). **OpenRouter:** la **muralla de confidencialidad SE SOSTIENE**
  ("soberano" jamás enruta a la nube por ningún fallback; la clave nunca se filtra); 1 mayor + 3
  menores corregidos (overflow inerte tras reinicio en caliente → helper `_openrouter_key_present`
  con cache 5s lee el `.env`; auto-omisión del wizard sin la clave del motor; landmine de
  `AgentCore.model` → default None).
- **Capa 3: PENDIENTE — de Pipe** (recorrido visual en vivo de ambas features).

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** recorrer la Sala de estrategia y la nueva opción de OpenRouter en vivo
   (encender MIA Modo B; la DB dev ya quedó arriba en 55432).
2. **ACCIÓN DE PIPE (deuda de OpenRouter):** confirmar los slugs EXACTOS de los modelos en
   openrouter.ai/models (`anthropic/claude-sonnet-4.6`, `anthropic/claude-haiku-4.5`). Un slug
   errado degrada a `mia-local` sin romper, pero pierde el motor OpenRouter en silencio.
3. Acciones de Pipe sin cambio: firma digital (Azure Trusted Signing) + apps OAuth; capa 3 en
   frío del instalador (bloque instalador). Apuesta #3 de NotebookLM (transformaciones al ingerir)
   sigue diferida.

### Trabajo en background sin leer

Nada — 2 recon iniciales (ClaudeClaw, sistema de motor), 3 recon de MIA, 5 ejecutores, 2 auditores
adversariales y 2 correctores: todo leído y reflejado aquí. La regresión la corrió esta terminal.

### Decisiones tomadas y suposiciones declaradas

- **El "War Room" de ClaudeClaw NO existe** (se verificó el zip): ClaudeClaw solo tiene delegación
  1-a-1 + hive mind, no un panel que debate. La Sala de estrategia es diseño propio de MIA.
- **Panelistas sintéticos de código** (`WARROOM_STANCES`, 4 posturas) reemplazables por Agentes
  del despacho — no depende de que el despacho haya creado personas.
- **Política "openrouter" = consentimiento por selección** (no depende de `allow_openrouter`); el
  overflow en "suscripción"/"nube" SÍ exige el opt-in (gate de confidencialidad CP-S3).
- Las dos features tocan archivos DISJUNTOS (Sala: warroom/ux/asuntos/033; OpenRouter:
  llm/config/welcome/settings/activar/yaml) → paralelo seguro sin colisión ni migración compartida.

---

