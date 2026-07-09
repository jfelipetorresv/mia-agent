"use client";

// Mia · "Vincular carpeta de OneDrive" en la pantalla del asunto (Fase 4 · kind="matters").
// Mismo navegador modal que el Panel de control, pero atado a ESTE expediente. Vive junto
// al bloque de la carpeta local en el aside del expediente.

import { useCallback, useEffect, useRef, useState } from "react";
import { Cloud, Link2, Loader2, MoreVertical, RefreshCw } from "lucide-react";
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
import OneDriveFolderPicker, { type DriveSource } from "@/app/_components/OneDriveFolderPicker";

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

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

type Props = {
  matterId: string;
  /** Se llama tras registrar o sincronizar, para que el asunto refresque su lista de documentos. */
  onSynced?: () => void;
};

export default function MatterDriveFolder({ matterId, onSynced }: Props) {
  // undefined = aún cargando; null = sin carpeta vinculada.
  const [source, setSource] = useState<DriveSource | null | undefined>(undefined);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [msg, setMsg] = useState("");
  const [unlinkOpen, setUnlinkOpen] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await apiGet<{ sources: DriveSource[] }>("/api/drive/sources");
      const found = (res.sources || []).find((s) => s.kind === "matters" && s.matter_id === matterId) || null;
      setSource(found);
    } catch {
      setSource(null);
    }
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  // Limpia el sondeo si el componente se desmonta a mitad de una sincronización.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  // Tras pedir la sincronización, sondea cada ~5s (máx. ~30s) hasta que la última revisión
  // avance respecto a la de referencia; entonces refresca la lista de documentos del asunto.
  function startSyncPolling(id: string, baseline: string | null | undefined) {
    stopPolling();
    let tries = 0;
    pollRef.current = setInterval(async () => {
      tries += 1;
      try {
        const res = await apiGet<{ sources: DriveSource[] }>("/api/drive/sources");
        const found = (res.sources || []).find((s) => s.id === id);
        if (found && found.last_sync && found.last_sync !== baseline) {
          stopPolling();
          setSource(found);
          setSyncing(false);
          setMsg("Listo. Revisé la carpeta y actualicé los documentos del expediente.");
          onSynced?.();
          return;
        }
      } catch {
        /* reintenta en el siguiente tick */
      }
      if (tries >= 6) {
        stopPolling();
        setSyncing(false);
      }
    }, 5000);
  }

  async function syncNow(id: string, baseline: string | null | undefined) {
    setSyncing(true);
    setMsg("");
    try {
      const res = await apiSend<{ status: string; message: string }>("POST", `/api/drive/sources/${id}/sync`);
      setMsg(res.message);
      if (res.status === "started" || res.status === "in_progress") {
        startSyncPolling(id, baseline);
      } else {
        // "up_to_date" u otro: no hay corrida que esperar; refresca por si acaso.
        setSyncing(false);
        onSynced?.();
      }
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo sincronizar la carpeta."));
      setSyncing(false);
    }
  }

  function onLinked(s: DriveSource) {
    setSource(s);
    setMsg("Vinculé la carpeta. Estoy revisando sus documentos.");
    syncNow(s.id, s.last_sync ?? null);
  }

  async function unlink() {
    if (!source || unlinking) return;
    setUnlinking(true);
    try {
      await apiSend("DELETE", `/api/drive/sources/${source.id}`);
      setSource(null);
      setUnlinkOpen(false);
      setMsg("Quité la carpeta de OneDrive. Los documentos que ya había traído siguen en tu expediente.");
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo quitar la carpeta."));
    } finally {
      setUnlinking(false);
    }
  }

  if (source === undefined) return null;

  return (
    <div className="mb-3">
      {source ? (
        <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 font-medium text-foreground">
                <Cloud className="h-3.5 w-3.5 shrink-0 text-primary" />
                Carpeta de OneDrive
              </div>
              <div className="mt-0.5 truncate text-muted-foreground" title={source.label}>
                {source.label}
              </div>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" aria-label="Más acciones">
                  <MoreVertical className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setUnlinkOpen(true)} className="text-destructive">
                  Quitar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <div className="mt-2 text-muted-foreground">
            {source.last_sync ? `Última revisión ${fmtRelative(source.last_sync)}` : "Aún sin revisar"}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => syncNow(source.id, source.last_sync)}
            disabled={syncing}
            className="mt-2 w-full gap-1.5"
          >
            {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {syncing ? "Revisando…" : "Sincronizar ahora"}
          </Button>
          {msg ? <p className="mt-1.5 text-muted-foreground">{msg}</p> : null}
        </div>
      ) : (
        <>
          <Button variant="outline" onClick={() => setPickerOpen(true)} className="mb-1.5 w-full justify-start gap-2">
            <Link2 className="h-4 w-4" />
            Vincular carpeta de OneDrive
          </Button>
          {msg ? <p className="text-xs text-muted-foreground">{msg}</p> : null}
        </>
      )}

      <OneDriveFolderPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        kind="matters"
        matterId={matterId}
        onLinked={onLinked}
      />

      <Dialog open={unlinkOpen} onOpenChange={(o) => !unlinking && setUnlinkOpen(o)}>
        <DialogContent aria-label="Quitar carpeta de OneDrive">
          <DialogHeader>
            <DialogTitle>¿Quitar la carpeta de OneDrive?</DialogTitle>
            <DialogDescription>
              Mia dejará de revisar esta carpeta. Los documentos que ya trajo se conservan en el expediente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUnlinkOpen(false)} disabled={unlinking}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={unlink} disabled={unlinking}>
              {unlinking ? "Quitando…" : "Quitar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
