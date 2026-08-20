"use client";

// Mia · navegador modal de carpetas en la nube (Fase 4 "fuentes remotas" — Ola 5).
// Empieza en la raíz, deja entrar a subcarpetas (breadcrumb) y registra la carpeta
// elegida vía POST /api/drive/sources. Solo lectura — nunca cambia nada en la nube
// del abogado. Se reutiliza en Configuración (kind="knowledge") y en la pantalla
// del asunto (kind="matters" + matterId).
//
// DOS PROVEEDORES, UN SOLO COMPONENTE (decisión de Pipe 2026-08-19): `provider`
// elige OneDrive (default, contrato de siempre) o Google Drive. Solo cambian el
// nombre que ve el abogado y el `?provider=` de la ruta; el flujo es el mismo.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, FileText, Folder, Loader2 } from "lucide-react";
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

export type DriveSource = {
  id: string;
  label: string;
  kind: string;
  matter_id: string | null;
  enabled: boolean;
  remote_item_id: string;
  created_at: string;
  last_sync: string | null;
  /** "microsoft" (OneDrive) o "google" (Google Drive). */
  provider?: DriveProvider;
};

export type DriveProvider = "microsoft" | "google";

/** Nombre en llano del servicio, y de dónde arranca la navegación. */
export const DRIVE_NAMES: Record<DriveProvider, string> = {
  microsoft: "OneDrive",
  google: "Google Drive",
};
const DRIVE_ROOT_NAMES: Record<DriveProvider, string> = {
  microsoft: "Mi OneDrive",
  google: "Mi unidad",
};
const rootCrumb = (p: DriveProvider): Crumb => ({ id: null, name: DRIVE_ROOT_NAMES[p] });

type DriveItem = { id: string; name: string; is_folder: boolean; size?: number; etag?: string; modified?: string };
type Crumb = { id: string | null; name: string };

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: "knowledge" | "matters";
  matterId?: string;
  onLinked: (source: DriveSource) => void;
  /** A dónde enviar al abogado si no hay cuenta con permiso de archivos. */
  connectHref?: string;
  /** Servicio a navegar. Default "microsoft" (OneDrive), el contrato de siempre. */
  provider?: DriveProvider;
};

export default function OneDriveFolderPicker({
  open,
  onOpenChange,
  kind,
  matterId,
  onLinked,
  connectHref = "/configurar#conexiones",
  provider = "microsoft",
}: Props) {
  const servicio = DRIVE_NAMES[provider];
  const [crumbs, setCrumbs] = useState<Crumb[]>([rootCrumb(provider)]);
  const [items, setItems] = useState<DriveItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [noAccount, setNoAccount] = useState(false);
  const [error, setError] = useState("");
  const [linking, setLinking] = useState(false);
  const [linkMsg, setLinkMsg] = useState("");

  const current = crumbs[crumbs.length - 1];

  const load = useCallback(async (itemId: string | null) => {
    setLoading(true);
    setError("");
    setNoAccount(false);
    try {
      const q = `?provider=${provider}${itemId ? `&item_id=${encodeURIComponent(itemId)}` : ""}`;
      const res = await apiGet<{ items: DriveItem[] }>(`/api/drive/browse${q}`);
      setItems(res.items || []);
    } catch (err) {
      setItems([]);
      if (err instanceof ApiError && err.status === 503) {
        setNoAccount(true);
      } else {
        setError(
          apiMessage(err, `No pude leer tu ${DRIVE_NAMES[provider]} en este momento. Intenta de nuevo en unos minutos.`),
        );
      }
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    if (open) {
      setCrumbs([rootCrumb(provider)]);
      setLinkMsg("");
      load(null);
    }
  }, [open, load, provider]);

  function enter(item: DriveItem) {
    if (!item.is_folder) return;
    const next = [...crumbs, { id: item.id, name: item.name }];
    setCrumbs(next);
    load(item.id);
  }

  function goTo(index: number) {
    const next = crumbs.slice(0, index + 1);
    setCrumbs(next);
    load(next[next.length - 1].id);
  }

  async function chooseFolder() {
    if (!current.id || linking) return;
    setLinking(true);
    setLinkMsg("");
    try {
      const source = await apiSend<DriveSource>("POST", "/api/drive/sources", {
        remote_item_id: current.id,
        label: current.name,
        kind,
        matter_id: kind === "matters" ? matterId : undefined,
        provider,
      });
      onLinked(source);
      onOpenChange(false);
    } catch (err) {
      setLinkMsg(apiMessage(err, "No se pudo agregar la carpeta. Intenta de nuevo."));
    } finally {
      setLinking(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !linking && onOpenChange(o)}>
      <DialogContent aria-label={`Elegir carpeta de ${servicio}`} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Elegir carpeta de {servicio}</DialogTitle>
          <DialogDescription>
            Navega hasta la carpeta que quieres que Mia revise. Solo lectura: Mia nunca cambia ni borra nada en tu{" "}
            {servicio}.
            {provider === "google"
              ? " Los documentos creados dentro de Google (Documentos, Hojas de cálculo, Presentaciones) no se leen todavía: Mia trabaja con los archivos PDF, Word, texto y similares que estén en la carpeta."
              : ""}
          </DialogDescription>
        </DialogHeader>

        {noAccount ? (
          <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
            <p>
              Para leer esta carpeta, Mia necesita tu cuenta de {provider === "google" ? "Google" : "Microsoft"} conectada
              con permiso de archivos. Se hace una sola vez, en Conexiones.
            </p>
            <Button asChild size="sm" variant="outline" className="mt-2">
              <Link href={connectHref} onClick={() => onOpenChange(false)}>
                Ir a Conexiones
              </Link>
            </Button>
          </div>
        ) : (
          <>
            <nav aria-label="Ruta de carpetas" className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
              {crumbs.map((c, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 ? <ChevronRight className="h-3.5 w-3.5" /> : null}
                  <button
                    type="button"
                    onClick={() => goTo(i)}
                    disabled={i === crumbs.length - 1}
                    className={
                      i === crumbs.length - 1
                        ? "font-medium text-foreground"
                        : "transition-colors hover:text-foreground hover:underline"
                    }
                  >
                    {c.name}
                  </button>
                </span>
              ))}
            </nav>

            <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
              {loading ? (
                <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Cargando…
                </div>
              ) : error ? (
                <p role="alert" className="px-4 py-6 text-sm text-warning">
                  {error}
                </p>
              ) : items.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">Esta carpeta está vacía.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {items.map((item) => (
                    <li key={item.id}>
                      {item.is_folder ? (
                        <button
                          type="button"
                          onClick={() => enter(item)}
                          className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent/60"
                        >
                          <Folder className="h-4 w-4 shrink-0 text-primary/70" />
                          <span className="truncate">{item.name}</span>
                          <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        </button>
                      ) : (
                        <div className="flex items-center gap-2 px-4 py-2.5 text-sm text-muted-foreground/50">
                          <FileText className="h-4 w-4 shrink-0" />
                          <span className="truncate">{item.name}</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {linkMsg ? (
              <p role="alert" className="text-sm text-warning">
                {linkMsg}
              </p>
            ) : null}
          </>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={linking}>
            Cancelar
          </Button>
          {!noAccount ? (
            <Button onClick={chooseFolder} disabled={!current.id || linking || loading}>
              {linking ? "Agregando…" : "Elegir esta carpeta"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
