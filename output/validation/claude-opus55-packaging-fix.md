# Opus5.5 high: preflight de entrega

Modelo confirmado: claude-opus-5-5. Solo lectura.

**Veredicto: APTO (revisión estática y focal).** No encuentro ningún bug concreto que bloquee el delta. Solo he leído código: no he ejecutado ni editado nada, y ni el smoke de PS5 ni `execution/test_frontend_smoke.py` los he corrido yo. Los tiempos que citas los aportaste tú.

## El delta punto por punto

- **Deadline de 20 a 180 s y timeout por petición de 2 a 4 s** (`packaging/build_frontend.ps1:246,259,270`). Ahora coinciden con la shell del producto. Lo peor que puede tardar es unos 184 s, porque el último sondeo puede empezar justo antes del límite. El `timeout=200` del test cubre ese margen.
- **El catch guarda el tipo y el código HTTP** (`:262-266`). En PS5.1, `WebException.Response` da el código correctamente, por ejemplo 503. No se filtran el cuerpo ni el mensaje, y el test lo comprueba con un texto centinela.
- **Logs en TEMP con GUID, fuera del payload** (`:230-238, 301-303`). Se conservan también si la prueba pasa, así que se acumulan en TEMP. Es aceptable.
- **Limpieza** (`:304-313`). Hace Stop y luego `WaitForExit(5000)` solo sobre nuestro PID, y restaura PORT y HOSTNAME distinguiendo si antes no estaban definidas. Es correcto dentro del `try`.
- **Prueba de comportamiento con arranque de 24 s frente a la mutación a 20 s** (`test_frontend_smoke.py:61-77`). Distingue bien los dos casos. Si el `replace("AddSeconds(180)", …)` dejara de encontrar el texto, la segunda aserción fallaría de forma visible, así que no hay falso PASS. Exige `HTTP=503` y que el centinela no aparezca. Solo cubre el deadline, no el paso de 2 a 4 s por petición. Eso cumple lo pedido y no lo exijo.

## Correcciones recomendadas antes del commit limpio

No condicionan el APTO.

1. **HOSTNAME no se restaura en todos los casos.** Se borra en `:179`, antes del `try` de `:229`. Si la búsqueda de puerto lanza el error de `:221`, el `finally` no se ejecuta. No hace daño en la práctica, porque `build_installer.ps1:140` lanza un `powershell` hijo. Aun así, contradice lo de "restaura HOSTNAME". Para arreglarlo basta con mover `:178-179` dentro del `try` o hacer que el `try` empiece antes. PORT no tiene este problema.
2. **El catch no distingue una conexión rechazada de un timeout.** En PS5.1 ambos casos dan `type=WebException; HTTP=none`. Es justo la ambigüedad del diagnóstico, y la causa del fallo inicial sigue sin conocerse. Si vuelve a pasar en la reconstrucción completa, faltaría ese dato. Basta una línea en `:265`:
   ```powershell
   $lastProbe = "type=$($_.Exception.GetType().Name); status=$($_.Exception.Status); HTTP=$httpCode"
   ```
   `WebExceptionStatus` (ConnectFailure, Timeout, ProtocolError…) no expone el cuerpo ni valores privados.
3. **Comentarios desactualizados (detalle menor).** `:18-19` y `:249-252` dicen que se "vuelca stdout/stderr", pero el código solo imprime las rutas en TEMP (`:302`). Hay que alinear el texto con el código.

## Límites conocidos del harness

Ninguno bloquea.

- El test lee el script con `utf-8-sig` y lo reescribe con BOM. Por eso no prueba que el `.ps1` real se interprete bien en PS5.1 si algún día pierde el BOM, por ejemplo con el em-dash de la cadena en `:146`. Si pasara, fallaría de forma visible al cargar el script.
- **Posible fallo, sin confirmar:** si el test de salida temprana fallara **solo** en `"exit code 7"`, sería la conocida peculiaridad de PS5.1 en que `Start-Process -PassThru` devuelve `ExitCode` nulo. Se arregla añadiendo `$null = $proc.Handle` después de `:238`. No afirmo que ocurra.

Queda claro que la decisión de no usar SkipPayloads y reconstruirlo todo es compatible con este delta. No exijo repetir el resto de la auditoría funcional.