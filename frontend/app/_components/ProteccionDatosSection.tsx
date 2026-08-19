"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, DatabaseBackup, Download, Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SectionTitle, fmtHora } from "@/app/_components/PanelUI";
import { apiGet } from "@/lib/api";

type ProtectionStatus = {
  recovery_key_created: boolean;
  recovery_key_saved: boolean;
  last_backup_name: string | null;
  last_backup_at: string | null;
  pending_restore?: boolean;
  pending_restore_failed?: boolean;
};

type BackupFile = { name: string; created_at: string; size_bytes: number };

type ExportRow = {
  matter_id: string;
  artifact_hash: string;
  export_format: string;
  actor: string;
  created_at: string;
};

type TauriCore = { invoke?: (command: string, args?: Record<string, unknown>) => Promise<unknown> };

async function invokeLocal<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const tauri = (
    window as unknown as { __TAURI__?: { core?: TauriCore } }
  ).__TAURI__;
  if (!tauri?.core?.invoke) {
    throw new Error("Este control está disponible en la aplicación de escritorio.");
  }
  return (await tauri.core.invoke(command, args)) as T;
}

export default function ProteccionDatosSection() {
  const [status, setStatus] = useState<ProtectionStatus | null>(null);
  const [busy, setBusy] = useState<"key" | "confirm" | "backup" | "restore" | null>(null);
  const [backups, setBackups] = useState<BackupFile[] | null>(null);
  const [exports, setExports] = useState<ExportRow[] | null>(null);
  const [restoreSource, setRestoreSource] = useState("");
  const [restoreConfirm, setRestoreConfirm] = useState("");
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
    apiGet<{ exports: ExportRow[] }>("/api/exports")
      .then((data) => setExports(data.exports || []))
      .catch(() => setExports([]));
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
      window.dispatchEvent(new Event("mia:recovery-key-confirmed"));
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

  async function openRestore() {
    setError("");
    setMessage("");
    try {
      const raw = await invokeLocal<string>("maintenance_list_backups");
      const list = JSON.parse(raw) as BackupFile[];
      setBackups(list);
      setRestoreSource(list[0]?.name || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude listar las copias de seguridad.");
    }
  }

  async function stageRestore() {
    setBusy("restore");
    setError("");
    setMessage("");
    try {
      await invokeLocal("maintenance_stage_restore", {
        source: restoreSource,
        confirmDatabase: restoreConfirm.trim(),
      });
      setBackups(null);
      setRestoreConfirm("");
      setMessage(
        "Recuperación preparada. Se aplicará la próxima vez que abras Mia: ciérrala y vuelve a abrirla. " +
        "Antes de recuperar, Mia crea y comprueba una copia del estado actual.",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude preparar la recuperación.");
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

        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 font-medium">
                <DatabaseBackup className="h-4 w-4 text-primary" /> Recuperar desde una copia
              </div>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                Reemplaza los datos actuales por los de una copia comprobada. La recuperación se
                aplica al reiniciar Mia, con una copia previa del estado actual. Para traer una
                copia de otro equipo, ponla en la carpeta de copias de Mia junto con tu llave de
                recuperación importada.
              </p>
            </div>
            <Button variant="outline" className="shrink-0 gap-2" onClick={openRestore} disabled={busy !== null}>
              Recuperar…
            </Button>
          </div>
          {status?.pending_restore ? (
            <p className="mt-3 rounded-md bg-warning/10 px-3 py-2 text-sm">
              Hay una recuperación preparada: se aplicará la próxima vez que abras Mia.
            </p>
          ) : null}
          {status?.pending_restore_failed ? (
            <p className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              La última recuperación preparada no pudo aplicarse; Mia sigue con los datos
              actuales. El detalle quedó en los registros.
            </p>
          ) : null}
          {backups !== null ? (
            backups.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">No hay copias .mia-backup en la carpeta de copias.</p>
            ) : (
              <div className="mt-4 space-y-3 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
                <label className="block text-sm">
                  Copia a recuperar
                  <select
                    value={restoreSource}
                    onChange={(e) => setRestoreSource(e.target.value)}
                    className="mt-1 h-10 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  >
                    {backups.map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.name} — {fmtHora(b.created_at)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm">
                  Esto reemplaza tus datos actuales. Escribe el nombre de la base para confirmar
                  (normalmente <span className="font-mono">mia</span>)
                  <input
                    value={restoreConfirm}
                    onChange={(e) => setRestoreConfirm(e.target.value)}
                    className="mt-1 h-10 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                    placeholder="mia"
                  />
                </label>
                <div className="flex gap-2">
                  <Button size="sm" onClick={stageRestore} disabled={busy !== null || !restoreSource || !restoreConfirm.trim()}>
                    {busy === "restore" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Preparar recuperación
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setBackups(null)} disabled={busy !== null}>
                    Cancelar
                  </Button>
                </div>
              </div>
            )
          ) : null}
        </div>
      </div>
      <div className="rounded-xl border border-border bg-card p-5 space-y-3">
        <h3 className="text-sm font-semibold tracking-tight">Salidas de documentos finales</h3>
        <p className="text-sm text-muted-foreground">
          Cada descarga de un escrito final queda registrada. Aquí ves la auditoría, no el documento.
        </p>
        {exports === null ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : exports.length === 0 ? (
          <p className="text-sm text-muted-foreground">Todavía no hay salidas finales registradas.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {exports.map((row) => (
              <li key={`${row.artifact_hash}-${row.created_at}`} className="text-muted-foreground">
                {fmtHora(String(row.created_at))} · {row.export_format} · {row.actor}
                <span className="ml-2 font-mono text-xs">{row.artifact_hash.slice(0, 12)}…</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
