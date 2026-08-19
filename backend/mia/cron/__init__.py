"""Mia · cron — scheduler propio de tareas periódicas (sin dependencia externa).

`Scheduler` es un registro de jobs en memoria (Módulo 3c). `build_scheduler()`
devuelve el scheduler con los jobs del sistema: sync Obsidian, sugerencias de
automatizaciones, y el resto de jobs periódicos.
"""
from .scheduler import Scheduler, build_scheduler, sync_obsidian_all_tenants

__all__ = ["Scheduler", "build_scheduler", "sync_obsidian_all_tenants"]
