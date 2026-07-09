"""Mia · ingest.ocr — lectura óptica LOCAL de páginas escaneadas (Fase 3, bloque 3a).

Motor: `rapidocr-onnxruntime` (PaddleOCR sobre ONNX Runtime, CPU, sin binarios de
sistema externos). El documento JAMÁS sale del servidor — pilar de confidencialidad.

El modelo pesa y tarda en cargar (~9 s la primera vez), así que se carga UNA sola vez
por proceso (singleton perezoso). Si la librería no está instalada en un despliegue, el
motor degrada a `None` y la ingesta sigue sin OCR (fail-soft) — nunca revienta.
"""
from __future__ import annotations

import io
import threading

# Singleton perezoso del motor. Se protege con un lock para que dos subidas
# simultáneas no carguen el modelo dos veces.
_engine = None            # instancia de RapidOCR, o None si no hay motor
_engine_loaded = False    # True una vez que se intentó cargar (aunque haya fallado)
_lock = threading.Lock()


def get_ocr_engine():
    """Devuelve el motor OCR (singleton). `None` si la librería no está instalada.

    Nunca lanza: un despliegue sin `rapidocr-onnxruntime` degrada con honestidad
    (el llamador anota que este servidor no tiene lectura óptica)."""
    global _engine, _engine_loaded
    if _engine_loaded:
        return _engine
    with _lock:
        if _engine_loaded:            # otro hilo lo cargó mientras esperábamos
            return _engine
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception:             # ImportError o fallo de init del modelo
            _engine = None
        finally:
            _engine_loaded = True
    return _engine


def ocr_image_png(engine, png_bytes: bytes) -> str:
    """Corre OCR sobre una imagen PNG (bytes) y devuelve el texto en orden de lectura.

    Devuelve "" si la página no tiene texto legible. Puede lanzar si la imagen está
    corrupta — el llamador captura por página para no tumbar el documento entero."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.array(img)
    result, _elapse = engine(arr)
    if not result:
        return ""
    # rapidocr entrega [ [box, texto, confianza], ... ] en orden de lectura.
    return "\n".join(line[1] for line in result).strip()
