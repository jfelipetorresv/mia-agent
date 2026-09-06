# Entrada, conversación y fuentes · 2026-09-06

Decisión de Pipe a partir de siete capturas de la instalación 0.3.1.

## Comportamiento esperado

- Una categoría «Mis suscripciones» abarca Claude Code y Codex detectados. La conexión preferida conserva la selección efectiva; no confundirla con el reparto interno de tareas ni prometer conocer el plan contratado.
- Las cuentas API se identifican por proveedor y facturación separada. No exigir volver a pegar una clave presente. Voyage es búsqueda semántica opcional, no requisito universal de lectura.
- El ingreso no exige identificar clientes habituales, configurar aprobación ni enumerar prohibiciones del producto. El contexto de firma se puede completar progresivamente, sin datos inventados ni identidad del desarrollador.
- Crear un caso abre una conversación. No elegir entre «revisión» y «respuesta directa». Los documentos quedan como borradores hasta aprobación de la versión correspondiente.
- El chat del caso entrega respuesta o un error recuperable comprensible; nunca deja una burbuja vacía como único resultado.
- Las fuentes autorizadas son accesibles sin duplicarlas innecesariamente ni requerir una API de embeddings. Mantener aislamiento entre despachos y casos, acceso acotado y procedencia.

## Organización de esta sesión

Astra dirige la implementación; Sol se encarga de chat y fuentes y de revisión independiente; Terra simplifica entrevista y creación de casos. La preferencia de Pipe por Sol/Terra/Luna según función corresponde a la ejecución de esta sesión; no se cambia por inferencia el catálogo de modelos de Mia.

## Verificación

Pruebas de conducta focales y negativas, navegador con datos sintéticos, tipos/lint/build e invariantes de aislamiento. Las pruebas con proveedores simulados no demuestran calidad de modelos reales. Estado final y límites en HANDOFF.md.

## Resultado de implementación

La entrada reutiliza el nombre de organización del registro y conserva perfiles
existentes. La identidad del abogado no se infiere de documentos sobre terceros.
Las políticas de suscripción conservan llamadas CLI y respaldos locales ya previstos;
no introducen llamadas API por conservar una clave o autorización antigua.
Las carpetas locales vinculadas se leen al conversar. Importar al índice se vuelve
una acción explícita separada. Los extractos forman parte de los registros normales
del turno; la lectura limitada avisa que no revisó toda la carpeta.

Entrega de escritorio: versión 0.3.2. Validación y fuente exacta del instalador se
registrarán en HANDOFF.md y validation/entry-0.3.2.json.
