"""Mia · channels — canales de conversación externos (CP-B2, Pilar B).

Cada canal es un puente hacia el API del modo asistente (POST /api/assistant/chat):
el canal NO habla con el motor directamente, solo con el API autenticado por JWT,
para que RLS, política de modelo y toda la disciplina del backend apliquen igual
que en el frontend. v1: telegram_bridge (bot privado single-chat, opt-in).
"""
