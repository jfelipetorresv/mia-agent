"use client";

// Mia · sección "Carpetas" de Configuración — antes vivía en el Panel (dashboard).
// Carpetas de trabajo (detectadas/registradas en este equipo) + Carpetas en la
// nube (OneDrive, sin instalar el programa de escritorio).

import { useEffect, useState } from "react";
import { Cloud, FolderSearch } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyHint, SectionTitle } from "@/app/_components/PanelUI";
import OneDriveSourcesSection from "@/app/_components/OneDriveSourcesSection";
import FolderPicker from "@/app/_components/FolderPicker";

type DetectedCloud = { label: string; path: string; registered: boolean };
type FolderSource = { id: string; path: string; label: string; kind: string; enabled: boolean };
type FoldersData = { detected: DetectedCloud[]; sources: FolderSource[] };

export default function CarpetasSection() {
  const [folders, setFolders] = useState<FoldersData | null>(null);
  const [folderPath, setFolderPath] = useState("");
  const [folderLabel, setFolderLabel] = useState("");
  const [folderMsg, setFolderMsg] = useState("");
  const [folderBusy, setFolderBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  async function loadFolders() {
    try {
      setFolders(await apiGet<FoldersData>("/api/folders/detected"));
    } catch {
      setFolders(null);
    }
  }

  useEffect(() => {
    loadFolders();
  }, []);

  async function addFolder(path: string, label?: string) {
    setFolderMsg("");
    setFolderBusy(true);
    try {
      await apiSend("POST", "/api/folders", { path, label: label || null, kind: "knowledge" });
      setFolderPath("");
      setFolderLabel("");
      setFolderMsg("Carpeta registrada. Mia la revisará en la próxima sincronización.");
      await loadFolders();
    } catch (e) {
      setFolderMsg(e instanceof Error && e.message && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo registrar la carpeta. Revisa la ruta e intenta de nuevo.");
    } finally {
      setFolderBusy(false);
    }
  }

  async function removeFolder(id: string, label: string) {
    if (!window.confirm(`¿Quitar "${label}"? Mia dejará de usar esa carpeta y olvidará lo que leyó de ella.`)) return;
    setFolderMsg("");
    try {
      await apiSend("DELETE", `/api/folders/${id}`);
      setFolderMsg("Carpeta retirada.");
      await loadFolders();
    } catch {
      setFolderMsg("No se pudo quitar la carpeta. Intenta de nuevo.");
    }
  }

  async function syncFoldersNow() {
    setFolderMsg("");
    try {
      const res = await apiSend<{ message: string }>("POST", "/api/folders/sync");
      setFolderMsg(res.message || "Estoy revisando tus carpetas.");
    } catch {
      setFolderMsg("No se pudo iniciar la revisión de carpetas. Intenta de nuevo.");
    }
  }

  return (
    <div className="space-y-10">
      {/* Carpetas de trabajo */}
      <div>
        <div className="mb-4 flex items-center justify-between gap-3">
          <SectionTitle
            icon={FolderSearch}
            title="Carpetas de trabajo"
            hint="Mia solo lee las carpetas que tú registres aquí. Nunca revisa nada fuera de ellas."
            className="mb-0"
          />
          <Button variant="outline" size="sm" onClick={syncFoldersNow} className="shrink-0">
            Revisar carpetas ahora
          </Button>
        </div>
        {folderMsg ? <p role="status" className="mb-3 rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground animate-fade-in">{folderMsg}</p> : null}

        {folders === null ? (
          <p className="text-sm text-muted-foreground">No se pudieron cargar tus carpetas. Recarga la página.</p>
        ) : (
          <div className="space-y-5">
            {folders.detected.length > 0 ? (
              <div>
                <h3 className="mb-2 text-sm font-medium text-muted-foreground">Detectadas en este equipo</h3>
                <ul className="space-y-2">
                  {folders.detected.map((d) => (
                    <li key={d.path} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{d.label}</div>
                        <div className="truncate text-sm text-muted-foreground" title={d.path}>{d.path}</div>
                      </div>
                      {d.registered ? (
                        <Badge variant="success" className="shrink-0 bg-success/15 text-success">Registrada</Badge>
                      ) : (
                        <Button size="sm" onClick={() => addFolder(d.path, d.label)} disabled={folderBusy} className="shrink-0">
                          Registrar
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">Registradas</h3>
              {folders.sources.filter((f) => f.enabled).length === 0 ? (
                <EmptyHint icon={FolderSearch}>Aún no has registrado ninguna carpeta.</EmptyHint>
              ) : (
                <ul className="space-y-2">
                  {folders.sources.filter((f) => f.enabled).map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{f.label}</div>
                        <div className="truncate text-sm text-muted-foreground" title={f.path}>{f.path}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removeFolder(f.id, f.label)} className="shrink-0">
                        Quitar
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (folderPath.trim()) addFolder(folderPath.trim(), folderLabel.trim() || undefined);
              }}
              className="rounded-xl border border-dashed border-border bg-card/50 p-4"
            >
              <h3 className="mb-3 text-sm font-medium text-muted-foreground">Registrar otra carpeta</h3>
              <div className="space-y-3">
                {folderPath ? (
                  <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2">
                    <span className="truncate text-sm" title={folderPath}>{folderPath}</span>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setPickerOpen(true)} className="shrink-0">
                      Cambiar
                    </Button>
                  </div>
                ) : (
                  <Button type="button" variant="outline" onClick={() => setPickerOpen(true)}>
                    Elegir carpeta…
                  </Button>
                )}
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <Input
                    value={folderLabel}
                    onChange={(e) => setFolderLabel(e.target.value)}
                    aria-label="Nombre para identificarla (opcional)"
                    placeholder="Nombre (opcional)"
                  />
                  <Button type="submit" disabled={folderBusy || !folderPath.trim()}>
                    Registrar
                  </Button>
                </div>
              </div>
            </form>

            <FolderPicker
              open={pickerOpen}
              onOpenChange={setPickerOpen}
              onPicked={(path) => setFolderPath(path)}
              title="Elegir carpeta de trabajo"
              description="Navega hasta la carpeta que quieres que Mia revise."
            />
          </div>
        )}
      </div>

      {/* Carpetas en la nube (OneDrive) — distinto de "Carpetas de trabajo" (que lee
          carpetas YA sincronizadas en este equipo): estas se leen directamente de
          OneDrive, sin instalar el programa de escritorio. */}
      <div>
        <SectionTitle
          icon={Cloud}
          title="Carpetas en la nube (OneDrive)"
          hint="Para carpetas de OneDrive que no tienes sincronizadas en este equipo. Requiere tu cuenta de Microsoft conectada con permiso de archivos (en Conexiones)."
        />
        <OneDriveSourcesSection />
      </div>

      {/* Carpetas en la nube (Google Drive) — mismo mecanismo, el otro proveedor. */}
      <div>
        <SectionTitle
          icon={Cloud}
          title="Carpetas en la nube (Google Drive)"
          hint="Para carpetas de Google Drive que no tienes sincronizadas en este equipo. Requiere tu cuenta de Google conectada con permiso de archivos (en Conexiones)."
        />
        <OneDriveSourcesSection provider="google" />
      </div>
    </div>
  );
}
