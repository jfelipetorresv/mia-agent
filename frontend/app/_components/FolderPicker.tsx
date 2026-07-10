"use client";

// Mia · selector visual de carpetas del equipo (Ola A1 "Proyectos Cowork").
// Clon estructural de OneDriveFolderPicker.tsx pero para el sistema de archivos
// local: arranca en los puntos de entrada que da el backend (Escritorio,
// Documentos, unidades…), deja navegar con breadcrumb y devuelve la ruta elegida
// a quien lo abrió — nunca llama por su cuenta al endpoint que registra la
// carpeta (eso lo hace cada pantalla, porque el contrato de registro cambia
// según dónde se use: /api/folders, /api/matters/{id}/folder, etc.).

import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Cloud, Folder, Loader2 } from "lucide-react";
import { ApiError, apiGet } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type FolderRoot = { label: string; path: string; registrable: boolean };
type BrowseItem = { name: string; path: string };
type BrowseResponse = { path: string; parent: string | null; items: BrowseItem[]; truncated: boolean };
type Crumb = { path: string | null; name: string; registrable: boolean };

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

function isCloudLabel(label: string): boolean {
  return /onedrive|nube|drive/i.test(label);
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Se llama con la ruta elegida; este componente no registra nada por su cuenta. */
  onPicked: (path: string) => void;
  title?: string;
  description?: string;
};

const HOME: Crumb = { path: null, name: "Inicio", registrable: false };

export default function FolderPicker({
  open,
  onOpenChange,
  onPicked,
  title = "Elegir carpeta",
  description = "Navega hasta la carpeta que quieres usar.",
}: Props) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([HOME]);
  const [roots, setRoots] = useState<FolderRoot[]>([]);
  const [items, setItems] = useState<BrowseItem[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [disabledMsg, setDisabledMsg] = useState("");
  const [error, setError] = useState("");

  const current = crumbs[crumbs.length - 1];

  async function fetchFolder(path: string): Promise<BrowseResponse> {
    return apiGet<BrowseResponse>(`/api/folders/browse?path=${encodeURIComponent(path)}`);
  }

  const loadRoots = useCallback(async () => {
    setLoading(true);
    setError("");
    setDisabledMsg("");
    try {
      const res = await apiGet<{ roots: FolderRoot[] }>("/api/folders/browse");
      setRoots(res.roots || []);
      setItems([]);
      setTruncated(false);
    } catch (err) {
      setRoots([]);
      if (err instanceof ApiError && err.status === 503) {
        setDisabledMsg(apiMessage(err, "Esta función no está disponible en este despliegue."));
      } else {
        setError(apiMessage(err, "No pude abrir el explorador de carpetas. Intenta de nuevo."));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setCrumbs([HOME]);
      setError("");
      setDisabledMsg("");
      loadRoots();
    }
  }, [open, loadRoots]);

  // Navega hacia una carpeta nueva (root o subcarpeta). Solo avanza el
  // breadcrumb si la carpeta se pudo leer: ante un 400 el abogado se queda
  // donde estaba, con el motivo a la vista, en vez de quedar parado en un
  // callejón sin salida.
  async function enter(path: string, name: string, registrable: boolean) {
    setLoading(true);
    setError("");
    try {
      const res = await fetchFolder(path);
      setItems(res.items || []);
      setTruncated(Boolean(res.truncated));
      setCrumbs((prev) => [...prev, { path, name, registrable }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setDisabledMsg(apiMessage(err, "Esta función no está disponible en este despliegue."));
      } else {
        setError(apiMessage(err, "No pude abrir esa carpeta."));
      }
    } finally {
      setLoading(false);
    }
  }

  function goTo(index: number) {
    const target = crumbs[index];
    if (target.path === null) {
      setCrumbs([HOME]);
      loadRoots();
      return;
    }
    setLoading(true);
    setError("");
    fetchFolder(target.path)
      .then((res) => {
        setItems(res.items || []);
        setTruncated(Boolean(res.truncated));
        setCrumbs(crumbs.slice(0, index + 1));
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 503) {
          setDisabledMsg(apiMessage(err, "Esta función no está disponible en este despliegue."));
        } else {
          setError(apiMessage(err, "No pude abrir esa carpeta."));
        }
      })
      .finally(() => setLoading(false));
  }

  function choose() {
    if (!current.path || !current.registrable) return;
    onPicked(current.path);
    onOpenChange(false);
  }

  const canChoose = Boolean(current.path) && current.registrable;

  return (
    <Dialog open={open} onOpenChange={(o) => !loading && onOpenChange(o)}>
      <DialogContent aria-label={title} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {disabledMsg ? (
          <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
            <p>{disabledMsg}</p>
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
              ) : current.path === null ? (
                roots.length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                    No encontré carpetas para mostrar.
                  </p>
                ) : (
                  <ul className="divide-y divide-border">
                    {roots.map((r) => (
                      <li key={r.path}>
                        <button
                          type="button"
                          onClick={() => enter(r.path, r.label, r.registrable)}
                          className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent/60"
                        >
                          {isCloudLabel(r.label) ? (
                            <Cloud className="h-4 w-4 shrink-0 text-primary/70" />
                          ) : (
                            <Folder className="h-4 w-4 shrink-0 text-primary/70" />
                          )}
                          <span className="truncate">{r.label}</span>
                          <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              ) : items.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">Esta carpeta está vacía.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {items.map((item) => (
                    <li key={item.path}>
                      <button
                        type="button"
                        onClick={() => enter(item.path, item.name, true)}
                        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent/60"
                      >
                        <Folder className="h-4 w-4 shrink-0 text-primary/70" />
                        <span className="truncate">{item.name}</span>
                        <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {truncated ? (
              <p className="text-xs text-muted-foreground">Hay más carpetas de las que puedo mostrar aquí.</p>
            ) : null}

            {!canChoose && !loading && !error ? (
              <p className="text-xs text-muted-foreground">Entra a una carpeta para poder elegirla.</p>
            ) : null}
          </>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          {!disabledMsg ? (
            <Button onClick={choose} disabled={!canChoose || loading}>
              Elegir esta carpeta
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
