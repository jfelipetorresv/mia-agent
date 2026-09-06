# Mia — reglas de construcción y calidad

Mia ayuda a cada despacho a trabajar sobre sus propios asuntos, fuentes y metodología.
El resultado esperado es un diagnóstico respaldado y un borrador que el abogado pueda
revisar y aprobar. Identidad, jurisdicción y criterio pertenecen a cada despacho; no se
importan los de la firma que desarrolla el producto.

## Entrada y alcance

- Leer `CLAUDE.md`, el cierre más reciente de `HANDOFF.md` y los aprendizajes pertinentes
  de `APRENDIZAJES.md`. Consultar `architecture/` solo para el área que se va a tocar.
- Comprobar el estado actual y los consumidores reales antes de ejecutar pendientes
  históricos. Una ruta ausente o una búsqueda incompleta no demuestra ausencia de función.
- Fijar el comportamiento esperado y sus criterios de aceptación antes de modificarlo.
  Consolidar los cambios dependientes antes de pedir una revisión completa.
- Preservar datos, fuentes, jurisdicción y autorizaciones de cada despacho. Las pruebas
  usan asuntos sintéticos y sustituyen proveedores cuando no necesitan medir calidad real.

## Calidad que llega al producto

- Una aprobación acredita únicamente la versión revisada. Si una selección o corrección
  genera otro borrador, devolver texto, huella y verificación nuevos y pedir nueva revisión.
- Informar el estado persistido, no el estado solicitado: un clic en aprobar no demuestra
  que exista un documento final. Un fallo o una medición ausente nunca equivale a aprobado.
- Las fuentes y los informes de verificación son cosas distintas. Un sello acredita
  integridad; no reemplaza el cotejo del contenido contra su fuente.
- Mantener la independencia de productor y revisor. Los controles automáticos comprueban
  propiedades concretas; no certifican por sí solos profundidad ni utilidad profesional.

## Rapidez, contexto y costo

- Reutilizar trabajo válido sin repetir verificaciones ya exitosas, salvo cambio relevante,
  resultado inconcluso o petición expresa. Ejecutar en paralelo solo trabajos independientes.
- Reducir contexto redundante, nunca fuentes necesarias, advertencias pendientes ni
  cobertura de verificación. No bajar el nivel de razonamiento para ocultar un costo.
- Una compresión solo se acepta si reduce el total, incluido su envoltorio. En caso
  contrario conservar los originales y contabilizar el intento improductivo.
- Incluir el checkpoint propio una sola vez al actualizar un resumen. No retirar mensajes
  distintos por parecer resúmenes, ni eliminar marcas de verificación pendiente.
- Respetar los presupuestos y rutas de modelos existentes; no crear otra política paralela.
  Medir tokens, tiempo, reintentos y calidad juntos. Costo no medido no es costo cero;
  un ahorro estimado de tokens no se presenta como ahorro monetario real.
- Identificar reintentos por envío, despacho y usuario, nunca por similitud del texto.
  Recuperar una respuesta registrada no dispara otra inferencia. Una ejecución incierta
  no se vuelve segura por vencer un plazo: conservar el registro y comunicar el límite.

## Verificación y cierre

- Entrada común: `scripts/verify.ps1`; catálogo: `config/verification.json`.
  Aislamiento: `execution/test_rls.py` (bloqueante). Núcleo:
  `execution/test_e2e.py`; compresión: `execution/test_context_compressor.py`;
  recibo de revisión: `execution/test_hitl_resume_state.py`.
- Las pruebas nuevas ejercen conducta positiva y negativa; demostrar que detectan el
  defecto anterior o una mutación equivalente. No conformarse con buscar una cadena.
- Verificar UI en navegador además de tipos, lint y compilación. Diferenciar respuestas
  simuladas, servicios reales, escritorio instalado y calidad de modelos reales.
- Dejar evidencia de lo verificado y los límites en `HANDOFF.md`, con commit descriptivo.
  No declarar «sin bugs» ni producto comercial listo cuando faltan recorridos por comprobar.

Adaptación genérica de principios operativos de Lexia Litigio, septiembre de 2026.
La matriz de aplicación y sus límites vive en `docs/auditoria-mia-2026-09-06.md`.
