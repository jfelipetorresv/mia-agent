"""Mia · embeddings — voyage-law-2 vía LiteLLM (decisión #8).

Fallback documentado si LiteLLM diera problemas con el modelo: SDK `voyageai`.
"""
from __future__ import annotations

from . import config


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not config.VOYAGE_API_KEY:
        raise RuntimeError(
            "VOYAGE_API_KEY vacío en .env — necesario para generar embeddings."
        )
    import litellm  # import diferido: solo se necesita al ingerir

    # timeout/num_retries: la 1a llamada a Voyage tiene latencia variable (0.5s-40s+);
    # sin acotar, colgaba el turno. Acota cada intento y reintenta ante un atasco.
    resp = litellm.embedding(
        model=config.litellm_embed_model(),
        input=texts,
        api_key=config.VOYAGE_API_KEY,
        timeout=15,
        num_retries=2,
    )
    vectors = [item["embedding"] for item in resp.data]
    for v in vectors:
        if len(v) != config.EMBED_DIM:
            raise RuntimeError(
                f"Dimensión inesperada del embedding: {len(v)} != EMBED_DIM={config.EMBED_DIM}"
            )
    return vectors
