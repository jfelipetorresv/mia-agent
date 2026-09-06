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

## Memoria durable de conversaciones largas (0.3.1)

La lectura del modelo ya no se limita a los últimos 200 mensajes. Se recorre todo el
historial original en páginas de 200 bajo un snapshot de lectura. Las páginas son una
forma de leer; no una autorización para omitir mensajes anteriores.

La migración 066 añade un checkpoint por despacho/conversación con cursor compuesto,
huella del prefijo cubierto, versión del compresor y revisión. La relación exige el
mismo despacho en conversación y checkpoint; ambas tablas de memoria tienen RLS forzado.
Los mensajes originales siguen intactos y son la fuente del historial visible.

### Cómo continúa un turno

1. Reconstruye primeros cinco mensajes, resumen aceptado, advertencias `[VERIFICAR]`
   originales y todos los mensajes posteriores al cursor. Protege los últimos 30.
2. Si el contexto requiere reducción, resume solo mensajes persistidos elegibles en
   tramos limitados por mensajes y tokens. El prompt del resumidor también se mide.
   El modelo y la política de compresión existentes no cambian.
3. Publica únicamente un candidato que reduzca el total y cuyo origen siga vigente.
   Una transacción corta comprueba huella y revisión; los cambios en originales se
   coordinan con ese sellado. Las modificaciones retroactivas invalidan el checkpoint.
4. Reutiliza el checkpoint en solicitudes posteriores. Una reserva por entrada impide
   ejecutar simultáneamente dos resúmenes del mismo tramo. Una compresión fallida
   conocida puede retomarse en un turno posterior; una ejecución incierta no se repite
   automáticamente. Un candidato inútil solo se vuelve a intentar al crecer el tramo.
5. El turno actual y sus adjuntos o consultas efímeras se añaden después: no se guardan
   dentro del checkpoint. Antes del modelo principal se comprueba el prompt completo,
   incluido el mensaje de sistema y los adjuntos.

Si el resumen falla pero el contexto original completo cabe, Mia conserva esos
originales y sigue. Si no cabe, no recorta silenciosamente ni responde como si hubiera
recordado todo: guarda un aviso explícito y conserva el avance útil. El usuario puede
volver a solicitar la continuación. El límite de ocho segmentos por turno acota el
trabajo; no convierte un tramo pendiente en cobertura acreditada.

### Límites y evidencia

Un resumen es contexto derivado, no fuente probatoria ni verificación de citas. Los
`[VERIFICAR]` originales permanecen textuales fuera del resumen. El ahorro de llamadas
por reutilización no demuestra por sí solo ahorro monetario ni fidelidad perfecta del
modelo. El historial original siempre permanece disponible.

`execution/test_conversation_memory.py` comprueba historias de 450 mensajes, hechos
anteriores a la ventana antigua, reutilización, edición retroactiva, concurrencia,
ausencia de ahorro, límites y aislamiento con PostgreSQL temporal y resumidor simulado.
Los resultados finales y el instalador se consignan en el cierre de `HANDOFF.md`.
