"use client";

// Mia · panel "Fuentes" unificado (Bloque A · Ola A3 "Proyectos Cowork").
// Reemplaza los tres bloques sueltos que había antes en la pantalla del asunto
// (carpeta local, carpeta de OneDrive, correos del caso) por una sola lista con
// un único botón "+ Conectar fuente". Autocontenido: carga y refresca sus datos
// solo contra GET /api/matters/{id}/sources — el backend entrega cada fuente ya
// en llano (estado, documentos, última revisión) para que este panel no tenga
// que traducir nada técnico (§G).
//
// Reusable: recibe `kind` ("asunto" | "proyecto") para hablar en el idioma
// correcto de la pantalla que lo monta, sin cambiar de contrato ni de lógica.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Cloud, Folder, Loader2, Mail, MoreVertical, Plus, Search } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import FolderPicker from "./FolderPicker";
import OneDriveFolderPicker from "./OneDriveFolderPicker";
import MailSearchDialog from "./MailSearchDialog";

type FuenteTipo = "carpeta" | "onedrive" | "correo";

type Fuente = {
  tipo: FuenteTipo;
  id: string | null;
  nombre: string;
  detalle: string;
  documentos: number;
  last_sync: string | null;
  estado: string;
};

type ItemMsg = { text: string; showConnect?: boolean };

type Props = {
  matterId: string;
  kind: "asunto" | "proyecto";
  /** Se llama tras cualquier cambio (vincular, sincronizar, desvincular, traer correos)
   * para que la pantalla que lo monta refresque lo que dependa de las fuentes (p. ej. el
   * expediente de documentos). */
  onChanged?: () => void;
};

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

function itemKey(f: Fuente): string {
  return `${f.tipo}:${f.id ?? "correo"}`;
}

function iconFor(tipo: FuenteTipo) {
  if (tipo === "carpeta") return Folder;
  if (tipo === "onedrive") return Cloud;
  return Mail;
}

// Tiempo relativo en español ("hace 3 minutos") para la última revisión de una fuente.
function fmtRelative(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 60) return "hace un momento";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} ${diffMin === 1 ? "minuto" : "minutos"}`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `hace ${diffHr} ${diffHr === 1 ? "hora" : "horas"}`;
  const diffDay = Math.floor(diffHr / 24);
  return `hace ${diffDay} ${diffDay === 1 ? "día" : "días"}`;
}

// Mientras una fuente está en pleno escaneo, el backend lo dice en llano
// ("Leyendo la carpeta…") — con eso basta para decidir si seguimos sondeando.
function algunaEnLectura(list: Fuente[]): boolean {
  return list.some((f) => /leyendo/i.test(f.estado));
}

export default function FuentesPanel({ matterId, kind, onChanged }: Props) {
  const [sources, setSources] = useState<Fuente[] | null>(null);
  const [loadError, setLoadError] = useState<{ text: string; showConnect?: boolean } | null>(null);
  const [banner, setBanner] = useState<{ type: "success" | "error"; text: string; showConnect?: boolean } | null>(
    null,
  );
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [msgs, setMsgs] = useState<Record<string, ItemMsg>>({});

  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [onedrivePickerOpen, setOnedrivePickerOpen] = useState(false);
  const [mailDialogOpen, setMailDialogOpen] = useState(false);

  const [unlinkTarget, setUnlinkTarget] = useState<Fuente | null>(null);
  const [unlinking, setUnlinking] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const kindWord = kind === "proyecto" ? "este proyecto" : "este asunto";

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }

  // Mientras alguna fuente siga "leyendo", sondea cada ~5s (máx. 30s) para que el
  // abogado vea el conteo avanzar sin recargar la página — mismo patrón que ya usaba
  // la carpeta del expediente.
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const list = await loadSources();
      if (list && !algunaEnLectura(list)) stopPolling();
    }, 5000);
    pollTimeoutRef.current = setTimeout(stopPolling, 30000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  function maybeStartPolling(list: Fuente[]) {
    if (algunaEnLectura(list)) startPolling();
    else stopPolling();
  }

  // notify=false en la carga inicial: la pantalla que nos monta ya hizo su propia
  // carga inicial de lo que dependa de las fuentes; solo avisamos en cambios reales.
  const loadSources = useCallback(
    async (notify = true): Promise<Fuente[] | null> => {
      try {
        const res = await apiGet<{ sources: Fuente[] }>(`/api/matters/${matterId}/sources`);
        const list = res.sources || [];
        setSources(list);
        setLoadError(null);
        if (notify) onChanged?.();
        return list;
      } catch (err) {
        setLoadError({
          text: apiMessage(err, `No pude cargar las fuentes de ${kindWord}. Intenta de nuevo.`),
          showConnect: err instanceof ApiError && err.status === 503,
        });
        return null;
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [matterId],
  );

  useEffect(() => {
    loadSources(false).then((list) => {
      if (list) maybeStartPolling(list);
    });
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  async function refresh() {
    const list = await loadSources();
    if (list) maybeStartPolling(list);
  }

  async function syncSource(f: Fuente) {
    if (!f.id || f.tipo === "correo") return;
    const key = itemKey(f);
    setBusy((b) => ({ ...b, [key]: true }));
    setMsgs((m) => ({ ...m, [key]: { text: "" } }));
    try {
      const path =
        f.tipo === "carpeta"
          ? `/api/matters/${matterId}/folders/${f.id}/sync`
          : `/api/drive/sources/${f.id}/sync`;
      const res = await apiSend<{ status: string; message: string }>("POST", path);
      setMsgs((m) => ({ ...m, [key]: { text: res.message || "Estoy revisando esta fuente." } }));
    } catch (err) {
      setMsgs((m) => ({
        ...m,
        [key]: {
          text: apiMessage(err, "No se pudo revisar esta fuente. Intenta de nuevo."),
          showConnect: err instanceof ApiError && err.status === 503,
        },
      }));
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
    await refresh();
  }

  async function performUnlink() {
    if (!unlinkTarget || unlinking || !unlinkTarget.id) return;
    const f = unlinkTarget;
    setUnlinking(true);
    try {
      const path =
        f.tipo === "carpeta" ? `/api/matters/${matterId}/folders/${f.id}` : `/api/drive/sources/${f.id}`;
      const res = await apiSend<{ status: string; message: string }>("DELETE", path);
      setUnlinkTarget(null);
      setBanner({
        type: "success",
        text: res.message || "Desvinculé la fuente. Los documentos que ya había traído siguen en tu expediente.",
      });
    } catch (err) {
      setBanner({ type: "error", text: apiMessage(err, "No se pudo desvincular esta fuente. Intenta de nuevo.") });
    } finally {
      setUnlinking(false);
    }
    await refresh();
  }

  async function linkFolder(path: string) {
    setBanner(null);
    try {
      const res = await apiSend<{ status: string; message: string }>("POST", `/api/matters/${matterId}/folders`, {
        path,
      });
      setBanner({ type: "success", text: res.message || "Vinculé la carpeta al expediente." });
    } catch (err) {
      setBanner({ type: "error", text: apiMessage(err, "No se pudo vincular la carpeta. Intenta de nuevo.") });
    }
    await refresh();
  }

  async function onOneDriveLinked(source: { id: string }) {
    setBanner({ type: "success", text: "Vinculé la carpeta de OneDrive. Estoy revisando sus documentos." });
    try {
      // El registro de la fuente no dispara una revisión inicial por su cuenta —
      // hay que pedirla aparte (a diferencia de la carpeta local, que sí la dispara sola).
      await apiSend("POST", `/api/drive/sources/${source.id}/sync`);
    } catch {
      /* si la primera revisión falla, el abogado puede pedirla luego con "Revisar ahora" */
    }
    await refresh();
  }

  async function onMailLinked() {
    await refresh();
  }

  return (
    <div className="mb-3">
      <h3 className="mb-2 text-sm font-semibold">Fuentes</h3>

      {banner ? (
        <div
          className={cn(
            "mb-2 rounded-lg border px-3 py-2 text-xs",
            banner.type === "error"
              ? "border-warning/30 bg-warning/10 text-warning"
              : "border-success/30 bg-success/10 text-success",
          )}
        >
          {banner.text}
          {banner.showConnect ? (
            <>
              {" · "}
              <Link href="/configurar#conexiones" className="underline">
                Ir a Configuración
              </Link>
            </>
          ) : null}
        </div>
      ) : null}

      {sources === null ? (
        loadError ? (
          <div className="mb-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            {loadError.text}
            {loadError.showConnect ? (
              <>
                {" · "}
                <Link href="/configurar#conexiones" className="underline">
                  Ir a Configuración
                </Link>
              </>
            ) : null}
          </div>
        ) : (
          <div className="flex items-center gap-2 px-1 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Cargando fuentes…
          </div>
        )
      ) : sources.length === 0 ? (
        <div className="mb-2 rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
          Conecta la primera fuente para que Mia trabaje con tus documentos.
        </div>
      ) : (
        <ul className="mb-2 space-y-2">
          {sources.map((f) => {
            const key = itemKey(f);
            const Icon = iconFor(f.tipo);
            const msg = msgs[key];
            const isBusy = Boolean(busy[key]);
            return (
              <li key={key} className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 font-medium text-foreground">
                      <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                      <span className="truncate">{f.nombre}</span>
                    </div>
                    {f.detalle ? (
                      <div className="mt-0.5 truncate text-muted-foreground" title={f.detalle}>
                        {f.detalle}
                      </div>
                    ) : null}
                  </div>
                  {f.tipo === "correo" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setMailDialogOpen(true)}
                      className="h-6 shrink-0 gap-1 px-2 text-xs"
                    >
                      <Search className="h-3 w-3" />
                      Buscar correos
                    </Button>
                  ) : (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" aria-label="Más acciones">
                          <MoreVertical className="h-3.5 w-3.5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => syncSource(f)} disabled={isBusy}>
                          {isBusy ? "Revisando…" : "Revisar ahora"}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setUnlinkTarget(f)} className="text-destructive">
                          Desvincular
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
                <div className="mt-2 text-muted-foreground">
                  {f.estado}
                  {f.last_sync ? ` · última revisión ${fmtRelative(f.last_sync)}` : ""}
                </div>
                {msg && msg.text ? (
                  <p className="mt-1.5 text-muted-foreground">
                    {msg.text}
                    {msg.showConnect ? (
                      <>
                        {" · "}
                        <Link href="/configurar#conexiones" className="underline">
                          Ir a Configuración
                        </Link>
                      </>
                    ) : null}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="w-full justify-start gap-2">
            <Plus className="h-4 w-4" />
            Conectar fuente
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuItem onClick={() => setFolderPickerOpen(true)}>Carpeta del equipo</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setOnedrivePickerOpen(true)}>Carpeta de OneDrive</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setMailDialogOpen(true)}>Correos del caso</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <FolderPicker
        open={folderPickerOpen}
        onOpenChange={setFolderPickerOpen}
        onPicked={linkFolder}
        title="Elegir carpeta"
        description={`Navega hasta la carpeta que quieres vincular a ${kindWord}.`}
      />

      <OneDriveFolderPicker
        open={onedrivePickerOpen}
        onOpenChange={setOnedrivePickerOpen}
        kind="matters"
        matterId={matterId}
        onLinked={onOneDriveLinked}
      />

      <MailSearchDialog matterId={matterId} open={mailDialogOpen} onOpenChange={setMailDialogOpen} onLinked={onMailLinked} />

      {/* Desvincular una fuente (carpeta local u OneDrive) */}
      <Dialog open={Boolean(unlinkTarget)} onOpenChange={(open) => !unlinking && !open && setUnlinkTarget(null)}>
        <DialogContent aria-label="Desvincular fuente">
          <DialogHeader>
            <DialogTitle>¿Desvincular «{unlinkTarget?.nombre}»?</DialogTitle>
            <DialogDescription>
              Mia dejará de revisar esta fuente. Los documentos que ya trajo se conservan en el expediente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUnlinkTarget(null)} disabled={unlinking}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={performUnlink} disabled={unlinking}>
              {unlinking ? "Desvinculando…" : "Desvincular"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
