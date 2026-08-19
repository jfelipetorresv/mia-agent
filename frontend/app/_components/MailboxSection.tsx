"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type Provider = { id: string; nombre: string };

type Conexion = {
  proveedor: string;
  proveedor_nombre: string;
  conectado: boolean;
  funciones: string[];
  // ¿La cuenta ya otorgó permiso de archivos de OneDrive? (solo Microsoft lo usa)
  archivos?: boolean;
  // ¿La instalación ya tiene registrada la app OAuth de este proveedor? Si no,
  // "Conectar" no se ofrece (honestidad de UI): el clic solo acabaría en un error.
  disponible?: boolean;
};

// El backend ahora reporta conexiones POR PROVEEDOR (un despacho puede tener Microsoft
// Y Google a la vez). `conexiones` siempre viene; `proveedores` solo si nadie está
// conectado (compatibilidad de forma con la versión anterior).
type MailboxStatus = {
  conectado: boolean;
  conexiones: Conexion[];
  analisis_contenido: boolean;
  proveedores?: Provider[];
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
  // Fase 3 "fuentes remotas": al conectar Microsoft, ofrece incluir permiso de archivos
  // (para poder vincular carpetas de OneDrive más adelante). Solo aplica a Microsoft.
  const [incluirOneDrive, setIncluirOneDrive] = useState(false);

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
      const feats = [incluirContenido ? "mail_content" : "mail"];
      if (provider === "microsoft" && incluirOneDrive) feats.push("drive");
      const q = `?features=${feats.join(",")}`;
      const res = await apiSend<{ url: string }>("POST", `/api/mailbox/connect/${provider}${q}`);
      window.location.href = res.url;
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo iniciar la conexión."));
      setBusy(null);
    }
  }

  // M3: agrega el permiso de archivos de OneDrive a una cuenta Microsoft YA conectada, sin
  // desconectarla. Conserva las funciones ya otorgadas (en Microsoft, "mail" y su contenido
  // comparten scopes) y añade "drive"; redirige al consentimiento.
  async function addDrivePermission() {
    setBusy("microsoft-drive");
    setMsg("");
    try {
      const res = await apiSend<{ url: string }>(
        "POST",
        "/api/mailbox/connect/microsoft?features=mail,drive",
      );
      window.location.href = res.url;
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo iniciar la conexión."));
      setBusy(null);
    }
  }

  async function disconnect(provider: string, nombre: string) {
    if (!window.confirm(`¿Desconectar ${nombre}? Mia dejará de avisarte de sus eventos y correos urgentes.`)) return;
    setBusy(`disconnect-${provider}`);
    setMsg("");
    try {
      await apiSend("DELETE", `/api/mailbox/disconnect?provider=${provider}`);
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
      const googleConectado = status?.conexiones.some((c) => c.proveedor === "google" && c.conectado);
      if (res.analisis_contenido && googleConectado) {
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

  // Lista para ofrecer "Conectar X": las conexiones que el backend reporta, o el
  // default (ambos proveedores) si el status no cargó bien.
  const todasLasConexiones: Conexion[] =
    status?.conexiones ?? [
      { proveedor: "microsoft", proveedor_nombre: "Microsoft 365", conectado: false, funciones: [] },
      { proveedor: "google", proveedor_nombre: "Google Workspace", conectado: false, funciones: [] },
    ];
  const conectadas = todasLasConexiones.filter((c) => c.conectado);
  // Honestidad de UI: "Conectar" solo se ofrece si la instalación tiene registrada la
  // app OAuth del proveedor (`disponible`). Si el status no trae el campo (versión
  // vieja del backend), se asume disponible para no ocultar una función que sí existe.
  const disponibles = todasLasConexiones.filter((c) => !c.conectado && c.disponible !== false);
  const pendientesDeHabilitar = todasLasConexiones.filter(
    (c) => !c.conectado && c.disponible === false,
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Mia puede avisarte de audiencias y plazos próximos en tu agenda, y de correos que parecen urgentes.
        Solo lee fechas, remitente y asunto — nunca el contenido del correo, salvo que lo autorices abajo. Puedes
        conectar Microsoft 365 y Google Workspace a la vez.
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

      {conectadas.map((c) => (
        <div key={c.proveedor} className="rounded-xl border border-success/25 bg-success/10 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium text-success">
            <CheckCircle2 className="h-4 w-4" />
            Conectado con {c.proveedor_nombre}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Mia revisará su calendario y correo para avisarte. Los plazos siempre quedan pendientes de tu
            confirmación — tú validas cada fecha.
          </p>
          {c.proveedor === "microsoft" && !c.archivos ? (
            <p className="mt-2 text-sm text-muted-foreground">
              ¿Quieres que Mia también pueda vincular carpetas de tu OneDrive (del despacho o de un caso)?
              Puedes darle ese permiso sin desconectar tu cuenta.
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => disconnect(c.proveedor, c.proveedor_nombre)}
              disabled={busy !== null}
            >
              Desconectar
            </Button>
            {c.proveedor === "microsoft" && !c.archivos ? (
              <Button size="sm" variant="outline" onClick={addDrivePermission} disabled={busy !== null}>
                {busy === "microsoft-drive" ? "Abriendo…" : "Añadir permiso de archivos"}
              </Button>
            ) : null}
          </div>
        </div>
      ))}

      {disponibles.length > 0 ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {conectadas.length > 0
              ? "Conecta también:"
              : "Elige tu proveedor para autorizar la lectura (solo lectura, nunca escribe):"}
          </p>
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={incluirContenido}
              onChange={(e) => setIncluirContenido(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span>
              Incluir el contenido de mis correos (para que Mia pueda resumir correos urgentes y para poder traer
              correos completos a un expediente cuando tú lo pidas — apagado por defecto)
            </span>
          </label>
          {disponibles.some((c) => c.proveedor === "microsoft") ? (
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={incluirOneDrive}
                onChange={(e) => setIncluirOneDrive(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
              />
              <span>Incluir mis archivos de OneDrive (solo Microsoft — para poder vincular carpetas del despacho o de un caso)</span>
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {disponibles.map((c) => (
              <Button key={c.proveedor} onClick={() => connect(c.proveedor)} disabled={busy !== null}>
                {busy === c.proveedor ? "Abriendo…" : `Conectar ${c.proveedor_nombre}`}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      {pendientesDeHabilitar.length > 0 ? (
        <div className="rounded-xl border border-border bg-muted/40 px-4 py-3">
          <p className="text-sm text-muted-foreground">
            La conexión con {pendientesDeHabilitar.map((c) => c.proveedor_nombre).join(" y ")} aún
            no está habilitada en este equipo. Es un paso único del administrador — pídele que
            registre la conexión (guía en Configuración).
          </p>
        </div>
      ) : null}

      {conectadas.length > 0 ? (
        <div className="rounded-xl border border-border bg-card p-4">
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={status?.analisis_contenido ?? false}
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
