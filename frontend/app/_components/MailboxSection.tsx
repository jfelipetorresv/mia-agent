"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type Provider = { id: string; nombre: string };

type MailboxStatus =
  | { conectado: false; proveedores: Provider[] }
  | {
      conectado: true;
      proveedor: string;
      proveedor_nombre: string;
      analisis_contenido: boolean;
    };

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

export default function MailboxSection() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<MailboxStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [incluirContenido, setIncluirContenido] = useState(false);

  const load = useCallback(async () => {
    setMsg("");
    try {
      setStatus(await apiGet<MailboxStatus>("/api/mailbox/status"));
    } catch (err) {
      setStatus(null);
      setMsg(apiMessage(err, "No se pudo cargar el estado de calendario y correo."));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const result = searchParams.get("mailbox");
    if (result === "conectado") {
      setMsg("Cuenta conectada correctamente. Mia empezará a avisarte de eventos y correos urgentes.");
      load();
    } else if (result === "error") {
      setMsg("No se pudo completar la conexión. Intenta de nuevo.");
    }
  }, [searchParams, load]);

  async function connect(provider: string) {
    setBusy(provider);
    setMsg("");
    try {
      const q = incluirContenido ? "?content=1" : "";
      const res = await apiSend<{ url: string }>("POST", `/api/mailbox/connect/${provider}${q}`);
      window.location.href = res.url;
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo iniciar la conexión."));
      setBusy(null);
    }
  }

  async function disconnect() {
    if (!window.confirm("¿Desconectar tu calendario y correo? Mia dejará de avisarte de eventos y correos urgentes.")) return;
    setBusy("disconnect");
    setMsg("");
    try {
      await apiSend("DELETE", "/api/mailbox/disconnect");
      await load();
      setMsg("Cuenta desconectada.");
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo desconectar."));
    } finally {
      setBusy(null);
    }
  }

  async function setContentAnalysis(activar: boolean) {
    setBusy("content");
    setMsg("");
    try {
      const res = await apiSend<{ analisis_contenido: boolean }>("PUT", "/api/mailbox/content-analysis", {
        activar,
      });
      await load();
      if (res.analisis_contenido && status?.conectado && status.proveedor === "google") {
        setMsg(
          "Preferencia guardada. Si aún no diste permiso de leer el contenido, desconecta y vuelve a conectar con «Incluir contenido de correos» marcado.",
        );
      }
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo guardar la preferencia."));
    } finally {
      setBusy(null);
    }
  }

  if (!loaded) {
    return <Skeleton className="h-16 w-full rounded-xl" />;
  }

  const proveedores =
    status && !status.conectado ? status.proveedores : [{ id: "microsoft", nombre: "Microsoft 365" }, { id: "google", nombre: "Google Workspace" }];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Mia puede avisarte de audiencias y plazos próximos en tu agenda, y de correos que parecen urgentes.
        Solo lee fechas, remitente y asunto — nunca el contenido del correo, salvo que lo autorices abajo.
      </p>
      {msg ? (
        <p
          role={msg.includes("correctamente") || msg.includes("desconectada") ? "status" : "alert"}
          className={`rounded-md px-3 py-2 text-sm ${
            msg.includes("correctamente") || msg.includes("desconectada")
              ? "bg-success/10 text-success"
              : "bg-warning/10 text-warning"
          }`}
        >
          {msg}
        </p>
      ) : null}

      {status?.conectado ? (
        <div className="rounded-xl border border-success/25 bg-success/10 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium text-success">
            <CheckCircle2 className="h-4 w-4" />
            Conectado con {status.proveedor_nombre}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Mia revisará tu calendario y correo para avisarte. Los plazos siempre quedan pendientes de tu
            confirmación — tú validas cada fecha.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={disconnect} disabled={busy !== null}>
              Desconectar
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Elige tu proveedor para autorizar la lectura (solo lectura, nunca escribe):
          </p>
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={incluirContenido}
              onChange={(e) => setIncluirContenido(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span>
              Incluir contenido de correos (para que Mia pueda resumir correos urgentes — apagado por defecto)
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            {proveedores.map((p) => (
              <Button key={p.id} onClick={() => connect(p.id)} disabled={busy !== null}>
                {busy === p.id ? "Abriendo…" : `Conectar ${p.nombre}`}
              </Button>
            ))}
          </div>
        </div>
      )}

      {status?.conectado ? (
        <div className="rounded-xl border border-border bg-card p-4">
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={status.analisis_contenido}
              onChange={(e) => setContentAnalysis(e.target.checked)}
              disabled={busy !== null}
              className="mt-0.5 h-4 w-4 rounded border-input accent-[hsl(var(--primary))] disabled:opacity-50"
            />
            <span>
              Permitir que Mia resuma el contenido de correos urgentes (tú lo activas; apagado por defecto).
              El texto se trata como dato confidencial y nunca se usa para actuar en tu nombre.
            </span>
          </label>
        </div>
      ) : null}
    </div>
  );
}
