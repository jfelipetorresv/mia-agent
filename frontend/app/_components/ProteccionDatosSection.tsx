"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, DatabaseBackup, Download, Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SectionTitle, fmtHora } from "@/app/_components/PanelUI";

type ProtectionStatus = {
  recovery_key_created: boolean;
  recovery_key_saved: boolean;
  last_backup_name: string | null;
  last_backup_at: string | null;
};

type TauriCore = { invoke?: (command: string) => Promise<unknown> };

async function invokeLocal<T>(command: string): Promise<T> {
  const tauri = (
    window as unknown as { __TAURI__?: { core?: TauriCore } }
  ).__TAURI__;
  if (!tauri?.core?.invoke) {
    throw new Error("Este control está disponible en la aplicación de escritorio.");
  }
  return (await tauri.core.invoke(command)) as T;
}

export default function ProteccionDatosSection() {
  const [status, setStatus] = useState<ProtectionStatus | null>(null);
  const [busy, setBusy] = useState<"key" | "confirm" | "backup" | null>(null);
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const raw = await invokeLocal<string>("maintenance_status");
      setStatus(JSON.parse(raw) as ProtectionStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude comprobar la protección de tus datos.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function downloadKey() {
    setBusy("key");
    setError("");
    setMessage("");
    try {
      const location = await invokeLocal<string>("maintenance_export_key");
      setAwaitingConfirmation(true);
      setMessage(`La llave quedó en ${location}. Cópiala también a un lugar privado distinto de este equipo.`);
    } catch {
      setError("No pude preparar la llave de recuperación. Intenta de nuevo.");
    } finally {
      setBusy(null);
    }
  }

  async function confirmKey() {
    setBusy("confirm");
    setError("");
    try {
      await invokeLocal("maintenance_confirm_key");
      setAwaitingConfirmation(false);
      setMessage("Listo. Mia ya puede crear copias recuperables.");
      await load();
    } catch {
      setError("No pude confirmar la llave. Vuelve a guardarla e intenta otra vez.");
    } finally {
      setBusy(null);
    }
  }

  async function createBackup() {
    setBusy("backup");
    setError("");
    setMessage("");
    try {
      await invokeLocal("maintenance_create_backup");
      setMessage("La copia quedó creada y comprobada.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude crear la copia. Intenta de nuevo.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section id="proteccion" className="mt-6 scroll-mt-6">
      <SectionTitle
        icon={ShieldCheck}
        title="Protección de tus datos"
        hint="Una llave privada permite recuperar Mia en otro equipo; las copias se cifran y se comprueban antes de darlas por buenas."
      />

      {error ? <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {message ? <p className="mb-4 rounded-md bg-primary/10 px-3 py-2 text-sm text-primary">{message}</p> : null}

      <div className="space-y-4">
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 font-medium">
                Llave de recuperación
                {status?.recovery_key_saved ? (
                  <span className="inline-flex items-center gap-1 text-xs text-success">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Guardada
                  </span>
                ) : null}
              </div>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                Es la única forma de abrir tus copias si cambias de equipo. Guárdala en un gestor de contraseñas o memoria USB segura. No la compartas.
              </p>
            </div>
            <Button variant="outline" className="shrink-0 gap-2" onClick={downloadKey} disabled={busy !== null}>
              {busy === "key" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {status?.recovery_key_saved ? "Guardar otra copia" : "Guardar llave"}
            </Button>
          </div>

          {awaitingConfirmation ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
              <p className="text-sm">Confirma solo después de comprobar que el archivo quedó guardado.</p>
              <Button size="sm" onClick={confirmKey} disabled={busy !== null}>
                {busy === "confirm" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Ya la guardé
              </Button>
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 font-medium">
                <DatabaseBackup className="h-4 w-4 text-primary" /> Copia de seguridad
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {status?.last_backup_at
                  ? `Última copia comprobada: ${fmtHora(status.last_backup_at)}.`
                  : "Todavía no hay una copia comprobada."}
              </p>
            </div>
            <Button
              className="shrink-0 gap-2"
              onClick={createBackup}
              disabled={busy !== null || !status?.recovery_key_saved}
            >
              {busy === "backup" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <DatabaseBackup className="h-4 w-4" />
              )}
              Crear copia ahora
            </Button>
          </div>
          {!status?.recovery_key_saved ? (
            <p className="mt-3 text-xs text-muted-foreground">Primero guarda y confirma la llave de recuperación.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
