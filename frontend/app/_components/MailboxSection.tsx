"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, apiGet, apiSend } from "@/lib/api";

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
    return <p className="text-sm text-gray-400">Cargando…</p>;
  }

  const proveedores =
    status && !status.conectado ? status.proveedores : [{ id: "microsoft", nombre: "Microsoft 365" }, { id: "google", nombre: "Google Workspace" }];

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        Mia puede avisarte de audiencias y plazos próximos en tu agenda, y de correos que parecen urgentes.
        Solo lee fechas, remitente y asunto — nunca el contenido del correo, salvo que lo autorices abajo.
      </p>
      {msg ? (
        <p
          role={msg.includes("correctamente") || msg.includes("desconectada") ? "status" : "alert"}
          className={`text-sm ${msg.includes("correctamente") || msg.includes("desconectada") ? "text-gray-600" : "text-amber-700"}`}
        >
          {msg}
        </p>
      ) : null}

      {status?.conectado ? (
        <div className="rounded-lg border border-green-100 bg-green-50 px-4 py-3">
          <p className="text-sm font-medium text-green-900">
            Conectado con {status.proveedor_nombre}
          </p>
          <p className="mt-1 text-sm text-green-800">
            Mia revisará tu calendario y correo para avisarte. Los plazos siempre llevan [VERIFICAR] — tú confirmas las fechas.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={disconnect}
              disabled={busy !== null}
              className="rounded-lg px-3 py-1.5 text-sm text-gray-700 hover:bg-white/80 disabled:opacity-50"
            >
              Desconectar
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Elige tu proveedor para autorizar la lectura (solo lectura, nunca escribe):</p>
          <label className="flex cursor-pointer items-start gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={incluirContenido}
              onChange={(e) => setIncluirContenido(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-gray-300"
            />
            <span>
              Incluir contenido de correos (para que Mia pueda resumir correos urgentes con IA — apagado por defecto en el servidor)
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            {proveedores.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => connect(p.id)}
                disabled={busy !== null}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
              >
                {busy === p.id ? "Abriendo…" : `Conectar ${p.nombre}`}
              </button>
            ))}
          </div>
        </div>
      )}

      {status?.conectado ? (
        <div className="rounded-lg border border-gray-100 p-4">
          <label className="flex cursor-pointer items-start gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={status.analisis_contenido}
              onChange={(e) => setContentAnalysis(e.target.checked)}
              disabled={busy !== null}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 disabled:opacity-50"
            />
            <span>
              Permitir que Mia resuma el contenido de correos urgentes con IA (opt-in; apagado por defecto).
              El texto se trata como dato confidencial y nunca se usa para actuar en tu nombre.
            </span>
          </label>
        </div>
      ) : null}
    </div>
  );
}
