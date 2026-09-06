# Chat: continuidad y recuperación de envíos

Continuación de la auditoría del 6 de septiembre de 2026. Implementación propia para
Mia; las referencias Grok aportaron ideas de control de turnos, no código reutilizado.

## Criterios de aceptación del envío

- Cada envío nuevo de la pantalla lleva un identificador aleatorio. Preguntar lo mismo
  deliberadamente constituye otro envío; el texto no es una clave de deduplicación.
- Reintentar conserva identificador y contenido originales. No añade otro mensaje del
  usuario a la pantalla ni vuelve a ejecutar una respuesta que ya está registrada.
- El registro pertenece al despacho y al usuario autenticados. Reutilizar una clave
  con otro contenido se rechaza; nunca devuelve una respuesta de otro usuario.
- Dos peticiones simultáneas con la misma clave no ejecutan dos turnos. Una ejecución
  interrumpida o incierta no se vuelve a ejecutar automáticamente por vencer un plazo.
- Recuperar una respuesta completada no consume IA y puede hacerse aunque el despacho
  haya alcanzado su presupuesto. Los envíos nuevos conservan el control presupuestal.
- Los clientes anteriores sin identificador conservan su contrato; su ausencia no
  ofrece protección durable frente a reenvíos.
- La pantalla bloquea envíos simultáneos y permite recuperar el intento fallido con
  el mismo identificador, sin almacenar el texto en el almacenamiento del navegador.

Esto evita repetir una ejecución conocida. No promete ejecución exactamente una vez
en un proveedor externo: una desconexión puede impedir conocer si este terminó. En
ese caso el registro debe mostrar incertidumbre, sin cobrar otro intento a escondidas.

La clave se conserva en memoria de la pantalla durante el reintento; no se recupera
automáticamente después de recargar o cerrar el navegador. El registro del servidor
sí sobrevive a un reinicio. Dos envíos con claves distintas desde dispositivos
distintos siguen siendo turnos diferentes; esta protección no los serializa por
conversación. Si falla guardar el recibo después del historial, el envío queda
incierto y el historial permite consultar lo que alcanzó a persistirse.

## Continuidad: problema identificado

El historial original se conserva en PostgreSQL, pero el asistente carga únicamente
los últimos 200 mensajes antes de comprimir. Persistir el resumen de esa ventana no
recuperaría los mensajes que ya quedaron fuera. La continuidad requiere un cursor de
cobertura explícito y conservar tanto los originales como los avisos pendientes.

**Estado: propuesta, no implementada.** La memoria del asistente no es completa. La
lectura de `backend/mia/assistant/core.py` usa `ORDER BY created_at DESC, id DESC LIMIT
200`, reordena la ventana y proyecta solo rol y contenido. Además crea un
`ContextCompressor` nuevo por turno: no conserva checkpoint ni antithrashing entre
turnos. La migración `015_assistant.sql` conserva originales bajo RLS, pero no define
un registro de cobertura. La idempotencia de envíos no corrige esta limitación.

### Diseño mínimo pendiente

1. Guardar un checkpoint separado por despacho y conversación: resumen aceptado,
   cursor compuesto `(created_at, id)`, revisión, versión del compresor e intentos
   ineficaces. Conservar íntegra `assistant_messages`. Aplicar RLS forzado y una
   relación que garantice que checkpoint y conversación pertenecen al mismo despacho.
2. Ensamblar primeros cinco mensajes reales, checkpoint, pendientes `[VERIFICAR]`
   preservados y mensajes posteriores al cursor, sin duplicar IDs. Proteger los
   últimos 30. El checkpoint es referencia con los marcadores del compresor; nunca
   instrucciones de sistema ni evidencia que certifique una cita.
3. Usar 200 como tamaño de página, no como salto sobre la historia. Leer desde el
   cursor en orden ascendente y avanzar solo sobre material efectivamente cubierto.
   Una conversación antigua puede requerir varias páginas. Si el presupuesto impide
   completar el tramo, conservar la cobertura real y declarar su límite; no fingir
   que el resumen recuperó mensajes que nunca recibió.
4. Persistir únicamente compresiones útiles de mensajes originales ya guardados.
   Excluir el turno actual enriquecido con contexto efímero de asuntos, recordatorios
   o referencias. Reutilizar el checkpoint hasta que nuevos mensajes justifiquen
   actualizarlo. Una revisión optimista evita sobrescribir una versión más reciente;
   la coordinación entre turnos debe impedir pagar dos resúmenes del mismo tramo.
5. Referenciar los mensajes originales con `[VERIFICAR]` y volver a cargarlos bajo
   RLS, conservándolos verbatim aun cuando avance el cursor. No convertir pendientes
   en hechos verificados ni eliminarlos porque hacen grande el contexto.

Antes de implementarlo hay que resolver dos decisiones operativas: qué hace el turno
cuando el presupuesto no permite cubrir toda la historia y cómo comunica cobertura
parcial o un volumen de pendientes superior a la ventana. Cachear la salida actual
no resuelve ninguna de las dos. No se declara ahorro sostenido ni memoria completa.

### Riesgos y pruebas de aceptación pendientes

- Una historia de 450 mensajes conserva un hecho único del principio y no salta el
  prefijo al cargar los últimos 200; mantiene los originales byte a byte.
- El siguiente turno reutiliza el checkpoint sin otra llamada de resumen cuando
  no hay nuevo tramo elegible. El ahorro se mide en llamadas y tokens, no se presume.
- Un `[VERIFICAR]` anterior al mensaje 200 sigue presente verbatim. Si los pendientes
  no caben, el sistema declara el límite en vez de descartarlos silenciosamente.
- IDs diferentes con la misma fecha se recorren una sola vez. Editar o insertar
  material retroactivo invalida la cobertura; comprobar solo el último ID no basta.
- Otro despacho no puede leer el checkpoint ni asociarlo a una conversación ajena.
- Dos actualizaciones concurrentes no pisan el checkpoint más reciente ni resumen
  el mismo tramo dos veces. La idempotencia de un envío no serializa por sí sola dos
  envíos distintos de la misma conversación.
- Un resumen igual, mayor o fallido no avanza el cursor ni sustituye el checkpoint
  aceptado. El truncado de emergencia no se registra como cobertura durable.
- El antithrashing puede reactivarse ante nuevo material elegible; dos intentos
  ineficaces no deshabilitan para siempre una conversación que sigue creciendo.
- Los enriquecimientos efímeros del turno no se guardan como historia resumida.

La evaluación e implementación verificadas se consignarán en el cierre de HANDOFF.md;
estos criterios por sí solos no acreditan que una función esté terminada.
