"use client";

// Mia · "Carpetas en la nube (OneDrive)" del Panel de control (Fase 4 · Fase 3 backend).
// Lista las carpetas de OneDrive registradas como CONOCIMIENTO del despacho
// (kind="knowledge"), con sincronizar/quitar, y el botón que abre el navegador modal
// para agregar una nueva.

import { useCallback, useEffect, useState } from "react";
import { Cloud, Loader2, Plus, RefreshCw } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import OneDriveFolderPicker, { type DriveSource } from "@/app/_components/OneDriveFolderPicker";

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

// Tiempo relativo en español ("hace 3 minutos"), igual que la carpeta local vinculada.
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

export default function OneDriveSourcesSection() {
  const [sources, setSources] = useState<DriveSource[] | null>(null);
  const [msg, setMsg] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiGet<{ sources: DriveSource[] }>("/api/drive/sources");
      setSources((res.sources || []).filter((s) => s.kind === "knowledge"));
    } catch (err) {
      setSources([]);
      setMsg(apiMessage(err, "No se pudieron cargar las carpetas de OneDrive."));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function syncNow(id: string) {
    setBusyId(id);
    setMsg("");
    try {
      const res = await apiSend<{ status: string; message: string }>("POST", `/api/drive/sources/${id}/sync`);
      setMsg(res.message);
      await load();
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo sincronizar la carpeta."));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: string, label: string) {
    if (!window.confirm(`¿Quitar «${label}»? Mia dejará de consultar los documentos de esa carpeta.`)) return;
    setBusyId(id);
    setMsg("");
    try {
      await apiSend("DELETE", `/api/drive/sources/${id}`);
      setMsg("Carpeta retirada.");
      await load();
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo quitar la carpeta."));
    } finally {
      setBusyId(null);
    }
  }

  function onLinked(source: DriveSource) {
    setMsg(`Agregué «${source.label}». Sincronizando…`);
    setSources((prev) => [...(prev || []), source]);
    syncNow(source.id);
  }

  if (sources === null) {
    return <Skeleton className="h-16 w-full rounded-xl" />;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Carpetas de OneDrive que Mia consulta como conocimiento del despacho, sin instalar el programa de escritorio.
        Solo lectura.
      </p>
      {msg ? (
        <p role="status" className="rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground animate-fade-in">
          {msg}
        </p>
      ) : null}

      {sources.length === 0 ? (
        <div className="flex items-start gap-3 rounded-xl border border-dashed border-border bg-card/50 px-4 py-4">
          <Cloud className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
          <p className="text-sm text-muted-foreground">Aún no has agregado ninguna carpeta de OneDrive.</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {sources.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium">{s.label}</div>
                <div className="text-sm text-muted-foreground">
                  {s.last_sync ? `Última revisión ${fmtRelative(s.last_sync)}` : "Aún sin revisar"}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="outline" onClick={() => syncNow(s.id)} disabled={busyId === s.id}>
                  {busyId === s.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                  Sincronizar ahora
                </Button>
                <Button size="sm" variant="ghost" onClick={() => remove(s.id, s.label)} disabled={busyId === s.id}>
                  Quitar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Button variant="outline" size="sm" onClick={() => setPickerOpen(true)} className="gap-1.5">
        <Plus className="h-3.5 w-3.5" />
        Añadir carpeta
      </Button>

      <OneDriveFolderPicker open={pickerOpen} onOpenChange={setPickerOpen} kind="knowledge" onLinked={onLinked} />
    </div>
  );
}
