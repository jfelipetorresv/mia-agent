"""Mia · eval.banco04 — banco de calidad 0.4 (protocolo `banco04-v1.2`).

Especificación congelada: `docs/banco-calidad-04-protocolo.md`. Este paquete NO importa
`custodia` (lo escribe otro agente y solo se carga, de forma perezosa, donde se mide).

Módulos del núcleo de juicio:
  · protocolo   — constantes congeladas del protocolo, con hash (§10.2.1).
  · segmentos   — segmentación determinista sin exclusiones por forma (§4.2.1, §10.2.7).
  · ceguera     — retiro de rastros, aviso de alcance aparte, HMAC y barajado (§8.3).
  · jueces      — jueces Opus/Codex, validador §8.4, alineación, adjudicación, kappa (§8).
  · metricas    — métricas §5, umbrales §6, matriz §7.2 y veredicto (§10.2.10).
"""
