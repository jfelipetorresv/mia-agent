"""Protección de claves locales con Windows DPAPI (stdlib, sin pywin32).

DPAPI cifra para el usuario actual de Windows. Sirve para que una llave guardada
en disco no sea útil al copiar el archivo o leer un backup de la carpeta local.
No sustituye una llave de recuperación exportada: al cambiar de usuario o equipo,
el blob DPAPI ya no puede abrirse.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class DPAPIUnavailableError(RuntimeError):
    pass


class DPAPIError(RuntimeError):
    pass


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_ENTROPY = b"Mia.LocalProtection.v1"


def _input_blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buffer


def _require_windows() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    if os.name != "nt":
        raise DPAPIUnavailableError(
            "La protección local de secretos requiere Windows DPAPI en este modo."
        )
    # ``use_last_error=True`` mantiene el código de error de Win32 asociado a
    # cada llamada ctypes. ``ctypes.windll`` no lo garantiza y podía reportar 0
    # o un error viejo cuando DPAPI fallaba.
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def protect(data: bytes, *, description: str = "Mia") -> bytes:
    """Cifra bytes para el usuario actual de Windows, sin interfaz gráfica."""
    crypt32, kernel32 = _require_windows()
    source, source_buffer = _input_blob(data)
    entropy, entropy_buffer = _input_blob(_ENTROPY)
    output = _DATA_BLOB()
    # Los buffers deben permanecer referenciados hasta terminar la llamada.
    _ = (source_buffer, entropy_buffer)
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        description,
        ctypes.byref(entropy),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise DPAPIError(f"Windows no pudo proteger la llave (error {ctypes.get_last_error()}).")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def unprotect(data: bytes) -> bytes:
    """Descifra un blob creado por :func:`protect` para este usuario/equipo."""
    crypt32, kernel32 = _require_windows()
    source, source_buffer = _input_blob(data)
    entropy, entropy_buffer = _input_blob(_ENTROPY)
    output = _DATA_BLOB()
    _ = (source_buffer, entropy_buffer)
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise DPAPIError(
            "No pude abrir la llave local. Puede pertenecer a otro usuario o equipo."
        )
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
