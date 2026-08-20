"""
Mia · test_google_drive.py — gate del conector de Google Drive (decisión de Pipe 2026-08-19:
Google Drive entra como fuente remota al mismo nivel que OneDrive).

CORRE SIN DB Y SIN RED. Todo lo que necesita base de datos (allowlist, motor de sync, RLS,
cron) ya está cubierto por execution/test_remote_drive.py, que se reutiliza tal cual porque
el motor es LITERALMENTE el mismo (`RemoteDriveSync`): lo único propio de Google es el
cliente HTTP y la resolución de credenciales, y eso es justo lo que este gate ejercita con
dobles.

HONESTIDAD (lo que este gate NO prueba, y nadie debe leer como probado): el flujo OAuth real
contra Google exige una aplicación registrada en Google Cloud Console con el scope de Drive
habilitado. Mientras Pipe no la registre, NADA de esto se ha ejercitado contra Google de
verdad: el HTTP está doblado. Los endpoints y parámetros son los publicados de Drive v3
([VERIFICAR] al conectar la primera cuenta real).

Cubre:
  Scopes (mailbox.oauth):
    · features={"drive"} en Google compone drive.readonly + identidad
    · features={"mail","drive"} suma correo y archivos sin duplicar
    · la autorización de Google es INCREMENTAL (include_granted_scopes) → añadir el permiso
      de archivos no tumba el de correo de una cuenta ya conectada
    · Microsoft NO cambió: sigue componiendo Files.Read + offline_access
  Cliente GoogleDrive (HTTP doblado):
    · list_children pagina (nextPageToken) y mapea la forma común neutral al proveedor
    · carpetas vs archivos, size ausente, etag desde md5Checksum y desde version
    · list_children de la raíz consulta el parent 'root' y excluye la papelera
    · download_file usa alt=media, sigue un redirect y devuelve bytes
    · un status != 200 se convierte en GoogleDriveError (nunca revienta en crudo)
  Servicio (tokens doblados):
    · sin cuenta de Google → None
    · cuenta conectada SOLO con correo (sin drive.readonly) → None (la UI ofrece ampliar)
    · cuenta con el permiso → conector listo
  Motor de sync compartido:
    · RemoteDriveSync acepta el conector de Google sin cambio alguno (misma superficie)
  §G: los mensajes del conector y de la ruta no usan jerga técnica ante el abogado.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_google_drive.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mia.connectors.mailbox import oauth                       # noqa: E402
from mia.connectors.mailbox.base import OAuthCreds             # noqa: E402
from mia.connectors.google_drive import (                      # noqa: E402
    DRIVE_SCOPE,
    GoogleDrive,
    GoogleDriveError,
    GoogleDriveService,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── dobles de HTTP (mismo estilo que test_remote_drive.FakeResp) ──────────────────
class FakeResp:
    def __init__(self, status, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload or {}


class FakeHttp:
    """`get` async que devuelve respuestas encoladas y GUARDA lo pedido, para poder afirmar
    sobre los parámetros exactos que se le mandan a Google."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        if not self._responses:
            return FakeResp(500)
        return self._responses.pop(0)


def file_entry(fid, name, *, folder=False, size=None, md5=None, version=None):
    it = {"id": fid, "name": name,
          "mimeType": "application/vnd.google-apps.folder" if folder else "application/pdf"}
    if size is not None:
        it["size"] = str(size)
    if md5 is not None:
        it["md5Checksum"] = md5
    if version is not None:
        it["version"] = version
    it["modifiedTime"] = "2026-08-19T10:00:00.000Z"
    return it


# ── 1 · scopes ───────────────────────────────────────────────────────────────────
def test_scopes() -> None:
    print("\n== Permisos que se le piden a Google ==")
    solo_drive = oauth.scopes_for("google", {"drive"})
    check("Google + solo archivos → drive.readonly", DRIVE_SCOPE in solo_drive)
    check("Google + solo archivos conserva la identidad de la cuenta",
          "openid" in solo_drive and "email" in solo_drive)
    check("Google + solo archivos NO pide correo",
          not any("gmail" in s for s in solo_drive))

    mail_drive = oauth.scopes_for("google", {"mail", "drive"})
    check("Google + correo y archivos compone los dos",
          DRIVE_SCOPE in mail_drive
          and "https://www.googleapis.com/auth/gmail.metadata" in mail_drive)
    check("sin permisos duplicados", len(mail_drive) == len(set(mail_drive)))

    contenido_drive = oauth.scopes_for("google", {"mail_content", "drive"})
    check("Google + contenido de correo y archivos: gmail.readonly reemplaza a metadata",
          "https://www.googleapis.com/auth/gmail.readonly" in contenido_drive
          and "https://www.googleapis.com/auth/gmail.metadata" not in contenido_drive
          and DRIVE_SCOPE in contenido_drive)

    url = oauth.authorize_url("google", client_id="cid", redirect_uri="http://x/cb",
                              state="st", features={"mail", "drive"})
    # Sin esto, dar el permiso de archivos a una cuenta con Gmail ya conectado le QUITARÍA
    # el de correo: Google reemplaza el consentimiento salvo que se pida sumarlo.
    check("el consentimiento de Google es incremental (include_granted_scopes=true)",
          "include_granted_scopes=true" in url)
    check("Google sigue entregando refresh token (access_type=offline)",
          "access_type=offline" in url)
    check("la URL de consentimiento lleva el permiso de Drive",
          "drive.readonly" in url)

    # Microsoft intacto: este cambio no puede tocar las conexiones que ya existen.
    ms = oauth.scopes_for("microsoft", {"mail", "drive"})
    check("Microsoft no cambió (Files.Read + offline_access)",
          "Files.Read" in ms and "offline_access" in ms)
    try:
        oauth.scopes_for("dropbox", {"drive"})
        ok = False
    except ValueError:
        ok = True
    check("un proveedor desconocido se rechaza", ok)


# ── 2 · cliente de Drive v3 ──────────────────────────────────────────────────────
def test_client() -> None:
    print("\n== Cliente de Google Drive (HTTP doblado) ==")
    creds = OAuthCreds(provider="google", access_token="tok", refresh_token="r",
                       expires_at=None, scopes=(DRIVE_SCOPE,))

    http = FakeHttp([
        FakeResp(200, {"files": [file_entry("f1", "Expedientes", folder=True),
                                 file_entry("f2", "demanda.pdf", size=1234, md5="abc")],
                       "nextPageToken": "p2"}),
        FakeResp(200, {"files": [file_entry("f3", "acta.docx", size=99, version="7")]}),
    ])
    items = asyncio.run(GoogleDrive(creds, http=http).list_children(None))
    check("pagina con nextPageToken hasta agotar", len(items) == 3)
    check("la carpeta se reconoce como carpeta",
          items[0]["is_folder"] is True and items[0]["name"] == "Expedientes")
    check("el archivo NO se reconoce como carpeta y trae su tamaño",
          items[1]["is_folder"] is False and items[1]["size"] == 1234)
    check("la huella de cambio sale de md5Checksum cuando existe", items[1]["etag"] == "abc")
    check("y del contador de versión cuando no hay md5", items[2]["etag"] == "7")
    check("la forma es la MISMA que la de OneDrive",
          set(items[0]) == {"id", "name", "is_folder", "size", "etag", "modified"})
    first_params = http.calls[0][1]
    check("la raíz se pide como 'root'", "'root' in parents" in first_params.get("q", ""))
    check("la papelera queda fuera", "trashed = false" in first_params.get("q", ""))
    check("la segunda página va con pageToken", http.calls[1][1].get("pageToken") == "p2")

    http2 = FakeHttp([FakeResp(200, {"files": []})])
    asyncio.run(GoogleDrive(creds, http=http2).list_children("CARPETA-X"))
    check("una subcarpeta se pide por su id",
          "'CARPETA-X' in parents" in http2.calls[0][1].get("q", ""))

    # Descarga: 302 → URL pre-firmada → bytes.
    http3 = FakeHttp([
        FakeResp(302, headers={"Location": "https://descarga/firmada"}),
        FakeResp(200, content=b"PDF-BYTES"),
    ])
    blob = asyncio.run(GoogleDrive(creds, http=http3).download_file("f2"))
    check("la descarga sigue el redirect y devuelve los bytes", blob == b"PDF-BYTES")
    check("la descarga pide el contenido crudo (alt=media)",
          http3.calls[0][1].get("alt") == "media")

    http4 = FakeHttp([FakeResp(200, content=b"OK")])
    check("la descarga directa (sin redirect) también funciona",
          asyncio.run(GoogleDrive(creds, http=http4).download_file("f9")) == b"OK")

    for status in (401, 403, 404, 500):
        http5 = FakeHttp([FakeResp(status, {})])
        try:
            asyncio.run(GoogleDrive(creds, http=http5).list_children(None))
            ok = False
        except GoogleDriveError:
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        check(f"un error {status} de Google se convierte en error del dominio", ok)


# ── 3 · resolución de credenciales ───────────────────────────────────────────────
class FakeMailboxService:
    def __init__(self, creds):
        self._creds = creds
        self.closed = False

    async def fresh_creds(self, tenant_id, provider):
        return self._creds

    def client_http(self):
        return FakeHttp([])

    async def aclose(self):
        self.closed = True


def _service_with(creds) -> GoogleDriveService:
    svc = GoogleDriveService()
    svc._svc = FakeMailboxService(creds)   # noqa: SLF001 — seam de prueba, igual que OneDrive
    return svc


def test_service() -> None:
    print("\n== Cuándo hay conector y cuándo no ==")
    check("sin cuenta de Google conectada → no hay conector",
          asyncio.run(_service_with(None).connector_for("t1")) is None)

    solo_correo = OAuthCreds(provider="google", access_token="a", refresh_token="r",
                             expires_at=None,
                             scopes=("https://www.googleapis.com/auth/gmail.metadata",))
    check("cuenta conectada SOLO con correo → no hay conector (falta el permiso de archivos)",
          asyncio.run(_service_with(solo_correo).connector_for("t1")) is None)

    con_archivos = OAuthCreds(provider="google", access_token="a", refresh_token="r",
                              expires_at=None,
                              scopes=("https://www.googleapis.com/auth/gmail.metadata",
                                      DRIVE_SCOPE))
    conn = asyncio.run(_service_with(con_archivos).connector_for("t1"))
    check("cuenta con permiso de archivos → conector listo", isinstance(conn, GoogleDrive))
    check("el conector se identifica como google", getattr(conn, "provider", "") == "google")


# ── 4 · el motor de sync es el mismo ─────────────────────────────────────────────
def test_engine_shared() -> None:
    print("\n== El motor de sincronización no distingue proveedor ==")
    from mia.connectors.graph_drive import DRIVE_PROVIDERS, GraphDrive, RemoteDriveSync

    check("la allowlist admite los dos proveedores",
          set(DRIVE_PROVIDERS) == {"microsoft", "google"})
    check("GoogleDrive expone la MISMA superficie que GraphDrive",
          all(hasattr(GoogleDrive, m) for m in ("list_children", "download_file"))
          and all(hasattr(GraphDrive, m) for m in ("list_children", "download_file")))
    creds = OAuthCreds(provider="google", access_token="a", refresh_token="r",
                       expires_at=None, scopes=(DRIVE_SCOPE,))
    engine = RemoteDriveSync(GoogleDrive(creds, http=FakeHttp([])))
    check("RemoteDriveSync acepta el conector de Google sin adaptador",
          engine._drive.provider == "google")   # noqa: SLF001

    # La migración que habilita provider='google' existe y trae el vocabulario COMPLETO.
    mig = ROOT / "backend" / "mia" / "db" / "migrations" / "060_google_drive_sources.sql"
    texto = mig.read_text(encoding="utf-8") if mig.exists() else ""
    check("la migración habilita provider='google' sin quitar 'microsoft'",
          "'microsoft'" in texto and "'google'" in texto)


# ── 5 · §G: nada de jerga técnica ante el abogado ────────────────────────────────
def test_plain_language() -> None:
    print("\n== §G · lo que lee el abogado ==")
    from mia.api.routes import remote_drive as rd

    mensajes = list(rd._NO_ACCOUNT.values()) + list(rd._DRIVE_DOWN.values())  # noqa: SLF001
    prohibidas = ("oauth", "scope", "token", "graph", "tenant", "api", "drive.readonly")
    sucios = [m for m in mensajes
              if any(p in m.lower() for p in prohibidas)]
    check("los mensajes de la ruta no usan jerga técnica", not sucios)
    check("el mensaje de Google nombra a Google (no a Microsoft)",
          "Google" in rd._NO_ACCOUNT["google"]                   # noqa: SLF001
          and "Microsoft" not in rd._NO_ACCOUNT["google"])       # noqa: SLF001


def main() -> int:
    print("== Google Drive como fuente remota (sin DB, sin red) ==")
    test_scopes()
    test_client()
    test_service()
    test_engine_shared()
    test_plain_language()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Google Drive OK (con HTTP doblado — el flujo OAuth real sigue "
              "pendiente de la aplicación de Google Cloud).")
        return 0
    print("Google Drive FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
