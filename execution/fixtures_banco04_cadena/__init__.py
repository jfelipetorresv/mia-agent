"""Fixtures SINTÉTICOS de `execution/test_banco04_cadena.py` (banco04-cadena/v5, §6).

Ningún dato de clientes: todo el material (casos custodiados de prueba, claves, reservado de
mutaciones, salidas de los dobles) se fabrica aquí. Los proveedores son dobles en memoria; la
custodia es una custodia FALSA en una carpeta temporal fuera del repositorio.

Módulos:
  · entorno       — proceso hermético (entorno aislado sintético, sin `.env` del repo, sin sesión
                    de CLI, sin red de proveedores), precondición del clúster 55448 e instantáneas.
  · firmas        — firma normalizada de comandos (§4.4) e instantáneas de acreditación de prueba.
  · custodia_falsa— custodia de prueba con los 4 custodiados, las claves y el reservado de prueba.
  · dobles        — dobles de los CLI, de embeddings, de la cadena de política, jueces y `mundo`.
  · escenario     — recorrido de las etapas desde sus `main` y lectura de lo que dejaron en disco.

Las interfaces que el contrato deja abiertas (forma de `proveedores`, `mundo`, `runners`,
`PruebaPuerta`, argumentos de línea de comandos de los `main` nuevos) quedan FIJADAS aquí y se
listan en el informe de las pruebas.
"""
