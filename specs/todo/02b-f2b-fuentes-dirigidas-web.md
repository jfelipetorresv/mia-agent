# F2b — El abogado alimenta a MIA: fuentes dirigidas y búsqueda web

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F2b". Corre DESPUÉS de F2 a propósito (contenido web es material no confiable; sin el
guardián endurecido sería un canal nuevo de citas sin respaldo), en paralelo a F3.

## Objetivo
El abogado carga a MIA las normas que usa, sus documentos y borradores, y puede dirigirla a
repositorios (fuentes oficiales) para que MIA descargue lo pertinente o sepa qué usar, con búsqueda
web — con procedencia y cuarentena obligatorias.

## Entradas
Guardián endurecido de F2 (contrato afirmación→span operativo); pipeline de ingesta con procedencia
(migración 045); `corpus_sources.json` del pack de jurisdicción.

## Pasos

1. **Spike de herramientas primero (medio día, con veredicto escrito)**: evaluar Firecrawl, Apify y
   alternativas (Tavily, Exa, Brave Search API, Jina Reader) contra 4 criterios — respeto de
   allowlist de dominios, entrega de texto VERBATIM (no resúmenes: la cita exige el pasaje literal),
   coste por página, y términos de uso. OpenRouter NO compite aquí (es gateway de modelos, no capa
   de búsqueda/descarga). Elegir UNA y cablearla detrás de una interfaz propia (cambiarla después
   debe ser barato).
2. **Fuente dirigida**: el abogado da la URL o el repositorio → MIA descarga → el contenido entra en
   CUARENTENA como material no confiable → se sella con procedencia y origen (dominio + fecha de
   descarga) → ingesta normal. Reusar lo que existe: el task `web_extract` en
   `backend/mia/agent/llm.py`, `corpus_sources.json` del pack, y el pipeline de ingesta con
   procedencia (migración 045).
3. **Estándar de cita web** (heredado de la regla cardinal de Lexia): un resultado web solo respalda
   una cita si viene de un dominio de la allowlist (los dominios oficiales van como DATOS en el pack
   de jurisdicción, nunca en código común) y el pasaje aparece VERBATIM en el texto descargado. Lo
   demás → `[VERIFICAR]`.
4. Gates: suite nueva con mutación (dominio fuera de allowlist → rechazado; pasaje no verbatim →
   `[VERIFICAR]`; cuarentena no saltable), `untrusted_content` y `jurisdiction_agnostic` intactos.
   Casos nuevos del banco: pregunta que exige norma no cargada → MIA propone descargarla de la
   fuente dirigida en vez de citar de memoria.

## Archivos críticos
`backend/mia/agent/llm.py` (task `web_extract`, línea 77 y `_AUX_TASKS` línea 127), packs de
jurisdicción (`corpus_sources.json`, ej. `backend/mia/jurisdiction/packs/co/corpus_sources.json`),
pipeline de ingesta con procedencia (migración `backend/mia/db/migrations/045_fase1_document_provenance.sql`).

## Salida medible (copiada del plan maestro)
El abogado puede dirigir a MIA a un repositorio y verla ingerir el material con procedencia visible;
cero citas certificadas desde dominios fuera de la allowlist (demostrado por mutación); veredicto del
spike documentado con costes.

## Gates
Suite nueva con mutación + `untrusted_content` + `jurisdiction_agnostic` en verde + HALT completo.

## Modelos (matriz del plan)
Cableado: Sonnet (medium). Diseño de cuarentena/estándar: Opus (high). Verifica: Codex (xhigh) — es
exactamente el tipo de superficie de ataque donde el cruce de proveedor paga.

## Regla dura heredada
MIA es AGNÓSTICA DE JURISDICCIÓN — los dominios oficiales de la allowlist van como datos del pack de
jurisdicción, jamás hardcodeados en código común.
