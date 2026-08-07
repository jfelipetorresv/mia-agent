"""Mia · embeddings — voyage-law-2 vía LiteLLM (decisión #8).

Fallback documentado si LiteLLM diera problemas con el modelo: SDK `voyageai`.

POR LOTES (sesión 52 · defecto encontrado con un expediente REAL). Antes esta función mandaba
TODOS los textos que le pasaran en UNA sola llamada, y el proveedor rechaza el lote que pasa de
su tope de tokens. Con un expediente de abogado eso no es un caso extremo, es lo normal: al
subir el expediente de un arbitraje (174 páginas) la llamada llegó con 127.058 tokens contra un
tope de 120.000 y la INGESTA FALLÓ ENTERA —

    VoyageException: The max allowed tokens per submitted batch is 120000.
    Your batch has 127058 tokens after truncation. TOO_MANY_TOKENS_IN_BATCH

— con el mismo efecto en el producto: `routes/ux.py::upload_document` pasa de golpe todos los
fragmentos del documento, así que al abogado le reventaba la subida de un documento grande (una
póliza de 90 páginas ya se acerca sola al tope). El arreglo va AQUÍ y no en cada llamador: hay
una docena de sitios que llaman a esta función y ninguno debería tener que saber del tope del
proveedor.

El troceo preserva el ORDEN: quien llama empareja `vectors[i]` con `texts[i]` (así lo hacen
`upload_document` y la siembra del banco), de modo que devolver los vectores desordenados
guardaría cada fragmento con el embedding de otro — un fallo silencioso que envenenaría la
búsqueda del expediente sin que nada lo delatara. Los lotes se concatenan en su orden original y
se verifica que la cuenta final coincida con la de entrada.
"""
from __future__ import annotations

import logging

from . import config

logger = logging.getLogger("mia.embeddings")

# Tope de tokens por lote del proveedor (Voyage: 120.000). Se deja margen porque la cuenta de
# tokens del proveedor no es la nuestra: estimamos por caracteres y su tokenizador puede contar
# más. Un lote rechazado tumba la ingesta entera, así que el margen es barato.
_BATCH_TOKEN_LIMIT = int(getattr(config, "MIA_EMBED_BATCH_TOKEN_LIMIT", 0) or 90_000)
# Tope de ITEMS por lote (Voyage acepta 1.000). Vale igual como red por si los textos son muy
# cortos y el límite que se alcanza primero es el de cantidad, no el de tokens.
_BATCH_ITEM_LIMIT = int(getattr(config, "MIA_EMBED_BATCH_ITEM_LIMIT", 0) or 512)
# Caracteres por token, CONSERVADOR a propósito. En el expediente que destapó el defecto la
# proporción real fue ~4,7 caracteres por token; usar 3,5 sobreestima el tamaño del lote, que es
# el lado seguro: preferimos una llamada extra a un lote rechazado.
_CHARS_PER_TOKEN = 3.5


def _lotes(texts: list[str]) -> list[list[str]]:
    """Trocea respetando el tope de tokens y el de items, SIN reordenar.

    Un texto que por sí solo pase del tope viaja en su propio lote: trocearlo por dentro
    cambiaría el contenido del fragmento (y con él lo que se guarda en la base), y truncarlo en
    silencio perdería expediente. Que decida el proveedor —que ya trunca por su cuenta y lo
    dice— en vez de mutir aquí el material del despacho.
    """
    lotes: list[list[str]] = []
    actual: list[str] = []
    tokens_actual = 0.0
    for t in texts:
        tokens = len(t or "") / _CHARS_PER_TOKEN
        if actual and (tokens_actual + tokens > _BATCH_TOKEN_LIMIT
                       or len(actual) >= _BATCH_ITEM_LIMIT):
            lotes.append(actual)
            actual, tokens_actual = [], 0.0
        actual.append(t)
        tokens_actual += tokens
    if actual:
        lotes.append(actual)
    return lotes


# F1.4 (plan de eficiencia): caché de embeddings de CONSULTA. La misma pregunta del
# abogado se re-embebe 2-3 veces por turno (intake + relectura dirigida) y otra vez si la
# repite en el turno siguiente — cada una es una llamada pagada a Voyage. El embedding es
# determinista por (modelo, texto), así que cachear es seguro. Solo aplica a llamadas
# PEQUEÑAS (consultas): los lotes de ingesta no pasan por aquí y no contaminan la caché.
_QUERY_CACHE_MAX_ITEMS = 4      # una llamada con más textos es ingesta, no consulta
_QUERY_CACHE_MAX_CHARS = 4_000  # una consulta más larga que esto no es una consulta
_QUERY_CACHE_SIZE = 512

from collections import OrderedDict as _OrderedDict  # noqa: E402

_query_cache: "_OrderedDict[tuple[str, str], list[list[float]]]" = _OrderedDict()


def _cache_key(text: str) -> tuple[str, str]:
    import hashlib

    return (config.litellm_embed_model(),
            hashlib.sha256((text or "").encode("utf-8")).hexdigest())


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not config.VOYAGE_API_KEY:
        raise RuntimeError(
            "VOYAGE_API_KEY vacío en .env — necesario para generar embeddings."
        )
    if not texts:
        return []
    cacheable = (len(texts) <= _QUERY_CACHE_MAX_ITEMS
                 and all(len(t or "") <= _QUERY_CACHE_MAX_CHARS for t in texts))
    if cacheable:
        claves = [_cache_key(t) for t in texts]
        if all(k in _query_cache for k in claves):
            for k in claves:
                _query_cache.move_to_end(k)
            return [list(_query_cache[k]) for k in claves]
    import litellm  # import diferido: solo se necesita al ingerir

    lotes = _lotes(list(texts))
    if len(lotes) > 1:
        logger.info("embeddings: %d textos en %d lotes (tope %d tokens/lote)",
                    len(texts), len(lotes), _BATCH_TOKEN_LIMIT)

    vectors: list[list[float]] = []
    for i, lote in enumerate(lotes, 1):
        # timeout/num_retries: la 1a llamada a Voyage tiene latencia variable (0.5s-40s+);
        # sin acotar, colgaba el turno. Acota cada intento y reintenta ante un atasco.
        resp = litellm.embedding(
            model=config.litellm_embed_model(),
            input=lote,
            api_key=config.VOYAGE_API_KEY,
            timeout=15,
            num_retries=2,
        )
        trozo = [item["embedding"] for item in resp.data]
        if len(trozo) != len(lote):
            raise RuntimeError(
                f"El proveedor devolvió {len(trozo)} embeddings para un lote de {len(lote)} "
                f"textos (lote {i} de {len(lotes)}): no se puede emparejar cada fragmento con "
                "su vector sin arriesgar guardar el embedding de otro."
            )
        vectors.extend(trozo)

    for v in vectors:
        if len(v) != config.EMBED_DIM:
            raise RuntimeError(
                f"Dimensión inesperada del embedding: {len(v)} != EMBED_DIM={config.EMBED_DIM}"
            )
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Se pidieron {len(texts)} embeddings y volvieron {len(vectors)}: el emparejamiento "
            "fragmento→vector no es fiable, así que no se guarda nada."
        )
    if cacheable:
        for k, v in zip(claves, vectors):
            _query_cache[k] = list(v)
            _query_cache.move_to_end(k)
        while len(_query_cache) > _QUERY_CACHE_SIZE:
            _query_cache.popitem(last=False)
    return vectors
