"""Mia · setup — bootstrap de primer arranque (F2, bloque instalador).

Paquete NUEVO (sesión 43). `first_run.main()` es el punto de entrada que la
cáscara de escritorio invoca en una máquina limpia para dejar Mia lista para
arrancar: carpeta de datos, .env semilla, initdb, migraciones y checkpointer.
`db_bootstrap.py` y `paths.py` son la lógica reutilizable que también usan,
sin duplicarla, los scripts de `execution/init_db.py` e
`execution/init_checkpointer.py`.
"""
from __future__ import annotations
