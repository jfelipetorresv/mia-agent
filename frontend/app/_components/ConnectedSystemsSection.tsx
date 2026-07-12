"use client";

// CP-E6 · Sistemas conectados (gestión documental / consulta de procesos).
// Consent-first: todo nace apagado. Sin jerga (§G): nunca "MCP", "servidor", "tenant".

import { useCallback, useEffect, useState } from "react";
import { FolderSearch, Scale } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ConnectorCard } from "@/app/_components/PanelUI";

type McpField = {
  env_var: string;
  label: string;
  is_secret: boolean;
  required: boolean;
};

type McpSystem = {
  slug: string;
  display_name: string;
  description: string;
  permissions_note: string;
  fields: McpField[];
  enabled: boolean;
  configured: boolean;
  missing: string[];
};

type FormValues = Record<string, string>;

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

/** Clave de secreto en el backend = env_var en snake_case (DMS_API_TOKEN → dms_api_token). */
function secretStorageKey(envVar: string): string {
  return envVar.toLowerCase();
}

function emptyForm(fields: McpField[]): FormValues {
  const out: FormValues = {};
  for (const f of fields) out[f.env_var] = "";
  return out;
}

function systemIcon(slug: string) {
  return slug.includes("proceso") ? Scale : FolderSearch;
}

function SystemCard({
  system,
  onRefresh,
}: {
  system: McpSystem;
  onRefresh: () => Promise<void>;
}) {
  const [form, setForm] = useState<FormValues>(() => emptyForm(system.fields));
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const Icon = systemIcon(system.slug);

  useEffect(() => {
    setForm(emptyForm(system.fields));
    setMsg("");
  }, [system.slug, system.enabled, system.configured]);

  function buildEnableBody(): { env: Record<string, string>; secrets: Record<string, string> } {
    const env: Record<string, string> = {};
    const secrets: Record<string, string> = {};
    for (const f of system.fields) {
      const value = (form[f.env_var] ?? "").trim();
      if (!value) continue;
      if (f.is_secret) secrets[secretStorageKey(f.env_var)] = value;
      else env[f.env_var] = value;
    }
    return { env, secrets };
  }

  async function enable() {
    setBusy("enable");
    setMsg("");
    try {
      await apiSend<McpSystem[]>("POST", `/api/mcp/${system.slug}/enable`, buildEnableBody());
      await onRefresh();
      setMsg("Sistema conectado.");
      setForm(emptyForm(system.fields));
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo guardar la conexión."));
    } finally {
      setBusy(null);
    }
  }

  async function disable() {
    if (
      !window.confirm(
        `¿Desconectar «${system.display_name}»? Mia dejará de usarlo; tus credenciales se conservan por si quieres volver a conectar.`,
      )
    ) {
      return;
    }
    setBusy("disable");
    setMsg("");
    try {
      await apiSend<McpSystem[]>("POST", `/api/mcp/${system.slug}/disable`);
      await onRefresh();
      setMsg("Sistema desconectado.");
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo desconectar."));
    } finally {
      setBusy(null);
    }
  }

  async function forget() {
    if (
      !window.confirm(
        `¿Borrar las credenciales de «${system.display_name}»? Tendrás que ingresarlas de nuevo para conectar.`,
      )
    ) {
      return;
    }
    setBusy("forget");
    setMsg("");
    try {
      await apiSend<McpSystem[]>("POST", `/api/mcp/${system.slug}/forget`);
      await onRefresh();
      setForm(emptyForm(system.fields));
      setMsg("Credenciales borradas.");
    } catch (err) {
      setMsg(apiMessage(err, "No se pudieron borrar las credenciales."));
    } finally {
      setBusy(null);
    }
  }

  const subtitle = system.enabled
    ? "Conectado"
    : system.configured
      ? "Desconectado · credenciales guardadas"
      : "Sin conectar";

  return (
    <ConnectorCard
      icon={Icon}
      title={system.display_name}
      subtitle={subtitle}
      active={system.enabled}
      actions={
        system.enabled ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={disable} disabled={busy !== null}>
              {busy === "disable" ? "Desconectando…" : "Desconectar"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={forget}
              disabled={busy !== null}
              className="text-warning hover:text-warning"
            >
              {busy === "forget" ? "Borrando…" : "Borrar credenciales"}
            </Button>
          </div>
        ) : null
      }
    >
      <p className="text-sm text-muted-foreground">{system.description}</p>
      <p className="mt-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Permisos recomendados:</span>{" "}
        {system.permissions_note}
      </p>

      {system.enabled && system.missing.length > 0 ? (
        <p role="alert" className="mt-3 text-sm text-warning">
          Falta completar: {system.missing.join("; ")}.
        </p>
      ) : null}

      {!system.enabled ? (
        <div className="mt-4 space-y-3">
          {system.configured ? (
            <p className="text-sm text-muted-foreground">
              Tienes credenciales guardadas. Completa el formulario (incluidos los tokens) para volver a conectar.
            </p>
          ) : null}
          {system.fields.map((f) => (
            <div key={f.env_var}>
              <Label htmlFor={`${system.slug}-${f.env_var}`} className="mb-1.5 block text-sm text-muted-foreground">
                {f.label}
                {f.required ? " *" : ""}
              </Label>
              <Input
                id={`${system.slug}-${f.env_var}`}
                type={f.is_secret ? "password" : "text"}
                autoComplete="off"
                value={form[f.env_var] ?? ""}
                onChange={(e) => setForm((prev) => ({ ...prev, [f.env_var]: e.target.value }))}
                disabled={busy !== null}
                placeholder={f.is_secret ? "No se muestra después de guardar" : undefined}
              />
            </div>
          ))}
          <Button size="sm" onClick={enable} disabled={busy !== null}>
            {busy === "enable" ? "Conectando…" : "Conectar"}
          </Button>
        </div>
      ) : null}

      {msg ? (
        <p
          role={msg.includes("conectado") || msg.includes("borradas") || msg.includes("desconectado") ? "status" : "alert"}
          className={`mt-3 text-sm animate-fade-in ${
            msg.includes("conectado") || msg.includes("borradas") || msg.includes("desconectado")
              ? "text-muted-foreground"
              : "text-warning"
          }`}
        >
          {msg}
        </p>
      ) : null}
    </ConnectorCard>
  );
}

export default function ConnectedSystemsSection() {
  const [systems, setSystems] = useState<McpSystem[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setSystems(await apiGet<McpSystem[]>("/api/mcp/status"));
    } catch (err) {
      setSystems(null);
      setError(apiMessage(err, "No se pudieron cargar los sistemas conectados."));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!loaded) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
    );
  }

  if (error) {
    return <p role="alert" className="text-sm text-warning">{error}</p>;
  }

  if (!systems?.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No hay sistemas disponibles para conectar en este momento.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold tracking-tight">Sistemas conectados</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Conecta los sistemas del despacho para que Mia consulte documentos y estados de procesos.
          Todo nace apagado: tú decides cuándo conectar y puedes desconectar o borrar credenciales cuando quieras.
        </p>
      </div>
      {systems.map((s) => (
        <SystemCard key={s.slug} system={s} onRefresh={load} />
      ))}
    </div>
  );
}
