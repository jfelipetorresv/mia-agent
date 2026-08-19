# Preflight del benchmark Claude–Codex

Estado: **preflight listo, sin gasto**. El adaptador lateral de Codex puede recorrer el mismo
grafo y payload bajo un `ContextVar` exclusivo del harness. No es —ni se presenta como— un
productor jurídico configurable por tenant o una política productiva de MIA.

## Evidencia obtenida

- Matriz versionada: 6 casos de riesgo + 3 casos holdout sellados × 10 repeticiones × 2
  brazos = **180 turnos**.
- Todos los casos son sintéticos y su integridad queda registrada por SHA-256.
- Claude tiene la política jurídica aislada `quality_adaptive`.
- Codex CLI `0.147.0` está instalado y autenticado mediante ChatGPT.
- El adaptador Codex usa `gpt-5.6-sol` con esfuerzo `max`, directorio temporal vacío,
  `read-only`, configuración/reglas locales ignoradas, entorno allowlist y respuesta JSON.
- Shell, búsqueda web, navegador, computer use, imágenes, apps, plugins, skills y subagentes
  quedan deshabilitados; `--strict-config` hace fallar la corrida si un control no es válido.
- El costo por llamada se registra como `null`, no como cero inventado: la cuota de una
  suscripción no ofrece atribución monetaria por turno. Tokens y latencia sí se capturan.

## Lo que deliberadamente no se hizo

No se efectuó ninguna inferencia durante este preflight ni se fabricaron resultados
Claude–Codex. No existe ganador, puntaje, costo o latencia observada de la matriz. Codex sigue
sin ruta productiva; el único alias `cli-codex-eval` falla fuera del contexto del harness y su
cadena no admite fallback a otro proveedor.

Una corrida autorizada deberá preservar la evaluación humana ciega: el paquete A/B no incluye
proveedor, modelo, costo ni llave; el mapeo privado se guarda aparte. Sin 180 respuestas,
telemetría completa, gate de mutaciones y revisión humana completa, el estado no puede ser
certificable ni declarar ganador.

Contrato de CLI contrastado con la documentación oficial de
[Codex exec](https://developers.openai.com/codex/cli/reference) y la
[referencia de configuración](https://learn.chatgpt.com/docs/config-file/config-reference).
