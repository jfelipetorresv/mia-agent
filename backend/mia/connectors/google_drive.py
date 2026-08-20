"""Mia · connectors.google_drive — Google Drive remoto SELECTIVO (decisión de Pipe 2026-08-19).

Gemelo de `connectors/graph_drive.py` (OneDrive) para el otro proveedor: el abogado NAVEGA su
Google Drive, ELIGE subcarpetas concretas ("la información que yo quiero ver", nunca todo el
drive) y Mia las sincroniza de forma incremental hacia el conocimiento del despacho
(kind='knowledge') o hacia un expediente (kind='matters', origin='drive'). SOLO LECTURA:
jamás se escribe contra la API de Google.

DIVISIÓN DEL TRABAJO — este módulo aporta SOLO el cliente de la API y la resolución de
credenciales. Todo lo demás se REUTILIZA tal cual de graph_drive.py, para que OneDrive y
Google Drive no puedan divergir en comportamiento:
  · la allowlist por despacho (`register_source`/`list_sources`/`delete_source`, tabla
    `remote_drive_sources`, ahora con provider='google' — migración 060),
  · el motor de sincronización incremental `RemoteDriveSync` (BFS, detección barata de
    cambios, sha256, poda acotada por fuente, movimiento por renombre),
  · los topes por corrida y el lock anti-duplicado `SYNCS_IN_FLIGHT`.
`GoogleDrive` implementa exactamente la misma superficie que `GraphDrive`
(`list_children` / `download_file`) y devuelve la MISMA forma común
{id, name, is_folder, size, etag, modified}.

Diferencias reales frente a Microsoft Graph, dichas sin adornos:
  · Detección barata de cambios: Drive v3 no expone eTag por ítem en el listado. Se usa
    `md5Checksum` cuando el archivo lo trae (binarios) y, si no, `version` (contador que Drive
    incrementa en cada modificación). Ambos cumplen el papel del eTag: distinto ⇒ hay que
    volver a descargar. Un `version` que cambia sin que cambie el contenido solo provoca una
    descarga de más — el sha256 posterior evita re-ingerir (mismo camino que en OneDrive).
  · Documentos NATIVOS de Google (Docs, Sheets, Slides): NO se ingieren. No son archivos
    descargables con `alt=media` y no tienen extensión en el nombre, así que el filtro de
    extensiones del escaneo los deja fuera. Exportarlos a PDF/Word es trabajo aparte, no
    disponible hoy: no se promete en ninguna pantalla.
  · Scope: Google no publica un permiso equivalente a `Files.Read` acotado por carpeta; el
    mínimo de solo lectura es `drive.readonly`. Quien limita el alcance es Mia (solo se
    recorre lo que el despacho registró en `remote_drive_sources`), no el proveedor.

[VERIFICAR] endpoints y parámetros son los publicados de Drive v3; los gates mockean el
HTTP, así que no se ejercitan en vivo. Confirmar al conectar la primera cuenta real (mismo
criterio que oauth.py y agent_hub.build_args). Sin la app OAuth de Google registrada por el
administrador, este conector no se puede probar de punta a punta.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

from .mailbox.service import MailboxService

logger = logging.getLogger("mia.connectors.google_drive")

DRIVE_BASE = "https://www.googleapis.com/drive/v3"
# El scope de SOLO LECTURA que exige este conector (el mismo que compone
# `mailbox.oauth.scopes_for(..., features={"drive"})` para Google).
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
# Id reservado de la raíz del Drive del usuario en la API v3.
ROOT_ID = "root"
FOLDER_MIME = "application/vnd.google-apps.folder"
# Prefijo de los formatos NATIVOS de Google (Docs/Sheets/Slides/Forms…): no se descargan.
NATIVE_MIME_PREFIX = "application/vnd.google-apps."
PAGE_SIZE = 200


class GoogleDriveError(RuntimeError):
    """Fallo al leer Google Drive (se traduce a 502 en llano en la ruta).

    Gemelo de `graph_drive.GraphDriveError`: la ruta trata a los dos igual."""


class GoogleDrive:
    """Lectura de Google Drive vía la API v3. `http` (get async estilo httpx) se inyecta para
    probar sin red. Ante cualquier error de API se lanza `GoogleDriveError`.

    Misma superficie que `graph_drive.GraphDrive`: el motor de sincronización no distingue
    con cuál de los dos está trabajando."""

    provider = "google"

    def __init__(self, creds, *, http, base: str = DRIVE_BASE) -> None:
        self._creds = creds
        self._http = http
        self._base = base

    async def _get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self._creds.access_token}",
                   "Accept": "application/json"}
        resp = await self._http.get(url, params=params or {}, headers=headers)
        status = getattr(resp, "status_code", 0)
        if status != 200:
            raise GoogleDriveError(f"GET {url.split('?')[0]} devolvió status {status}")
        return resp.json()

    async def list_children(self, item_id: Optional[str] = None) -> list[dict]:
        """Carpetas y archivos de UN nivel (raíz si `item_id` es None). Sigue la paginación
        `nextPageToken` y devuelve la FORMA COMÚN neutral al proveedor:
        {id, name, is_folder, size, etag, modified}.

        `trashed = false`: lo que el abogado mandó a la papelera NO es conocimiento vigente.
        Se incluyen las unidades compartidas (`supportsAllDrives`) porque muchos despachos
        guardan los expedientes ahí y no en "Mi unidad"."""
        parent = str(item_id or ROOT_ID)
        base_params = {
            "q": f"'{parent}' in parents and trashed = false",
            "fields": ("nextPageToken, files(id, name, mimeType, size, "
                       "modifiedTime, md5Checksum, version)"),
            "pageSize": str(PAGE_SIZE),
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            # Necesario cuando se incluyen unidades compartidas.
            "corpora": "allDrives",
        }
        out: list[dict] = []
        token: Optional[str] = None
        while True:
            params = dict(base_params)
            if token:
                params["pageToken"] = token
            data = await self._get_json(f"{self._base}/files", params=params)
            for it in data.get("files") or []:
                out.append(self._to_common(it))
            token = data.get("nextPageToken")
            if not token:
                break
        return out

    async def download_file(self, item_id: str) -> bytes:
        """Bytes de UN archivo (`alt=media`). El tope de 20 MB se controla ANTES en el motor
        de sync usando el tamaño del árbol, así un archivo grande nunca llega a descargarse.
        Se sigue un eventual redirect igual que en OneDrive (Google responde 200 directo en
        el caso normal, pero el redirect es barato de soportar y no cuesta correción)."""
        url = f"{self._base}/files/{quote(str(item_id), safe='')}"
        headers = {"Authorization": f"Bearer {self._creds.access_token}"}
        resp = await self._http.get(
            url, params={"alt": "media", "supportsAllDrives": "true"}, headers=headers)
        status = getattr(resp, "status_code", 0)
        if status in (301, 302, 303, 307, 308):
            location = _resp_header(resp, "Location")
            if not location:
                raise GoogleDriveError("descarga sin URL de redirección")
            resp = await self._http.get(location, headers={})
            status = getattr(resp, "status_code", 0)
        if status != 200:
            raise GoogleDriveError(f"descarga de archivo devolvió status {status}")
        content = getattr(resp, "content", b"")
        return content if isinstance(content, (bytes, bytearray)) else bytes(content or b"")

    @staticmethod
    def _to_common(it: dict) -> dict:
        """file de Drive v3 → forma común.

        `mimeType == folder` ⇒ carpeta. `etag` se compone con `md5Checksum` (huella real del
        contenido, presente en binarios) y, a falta de él, con `version` (contador de
        modificaciones): distinto ⇒ hay cambio que mirar. `size` llega como string y falta en
        los documentos nativos de Google — 0 en ese caso (no se ingieren de todos modos, el
        filtro de extensiones del escaneo los descarta)."""
        mime = str(it.get("mimeType") or "")
        try:
            size = int(it.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return {
            "id": str(it.get("id") or ""),
            "name": str(it.get("name") or ""),
            "is_folder": mime == FOLDER_MIME,
            "size": size,
            "etag": str(it.get("md5Checksum") or it.get("version") or ""),
            "modified": str(it.get("modifiedTime") or ""),
        }


def _resp_header(resp, name: str) -> str:
    """Lee una cabecera de la respuesta HTTP tolerando mayúsculas/minúsculas (httpx.Headers
    es case-insensitive; un doble de test usa un dict simple)."""
    headers = getattr(resp, "headers", None) or {}
    try:
        val = headers.get(name)
        if val is None:
            val = headers.get(name.lower())
        return str(val or "")
    except Exception:  # noqa: BLE001
        return ""


class GoogleDriveService:
    """Resuelve un `GoogleDrive` listo para el tenant, reutilizando la plomería de tokens de
    MailboxService (cargar + refrescar + persistir). Devuelve None si el despacho no tiene
    Google conectado, o si lo conectó SIN permiso de archivos (drive.readonly) — en ambos
    casos la ruta responde 503 en llano, igual que OneDrive. `http`/`store_mod`/... se
    inyectan para pruebas."""

    def __init__(self, *, http=None, store_mod=None, oauth_mod=None,
                 client_credentials=None) -> None:
        self._svc = MailboxService(http=http, store_mod=store_mod, oauth_mod=oauth_mod,
                                   client_credentials=client_credentials)

    async def connector_for(self, tenant_id: str, provider: str = "google"):
        """GoogleDrive del tenant, o None (sin cuenta de Google / sin permiso de archivos)."""
        creds = await self._svc.fresh_creds(tenant_id, "google")
        if creds is None:
            return None
        if DRIVE_SCOPE not in (creds.scopes or ()):
            # Conectado (correo), pero sin el permiso de archivos: se trata como "no
            # disponible" — la UI ofrece AMPLIAR el permiso sin desconectar la cuenta.
            return None
        return GoogleDrive(creds, http=self._svc.client_http())

    async def aclose(self) -> None:
        await self._svc.aclose()
