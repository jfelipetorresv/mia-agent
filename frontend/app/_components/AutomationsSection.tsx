"use client";

import { useCallback, useEffect, useState } from "react";
import { Repeat, Sparkles } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

type BlueprintField = {
  name: string;
  tipo: string;
  etiqueta: string;
  default: unknown;
  opciones: string[];
  min: number | null;
  max: number | null;
  ayuda: string;
};

type Blueprint = {
  key: string;
  nombre: string;
  descripcion: string;
  toca_plazo_procesal: boolean;
  campos: BlueprintField[];
};

type Automation = {
  id: string;
  blueprint_key: string;
  kind: string;
  params: Record<string, unknown>;
  is_procedural: boolean;
  enabled: boolean;
};

type Suggestion = {
  id: string;
  blueprint_key: string;
  params: Record<string, unknown>;
  rationale: string;
  nombre: string;
  toca_plazo_procesal: boolean;
};

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

// Traduce los parámetros de una automatización a lenguaje llano (§G: el abogado
// nunca ve claves técnicas). Si el blueprint trae la etiqueta humana de cada campo
// (blueprint.campos[].etiqueta), se usa esa. Si algún parámetro no tiene etiqueta
// conocida, se prefiere un resumen honesto y vago a exponer una clave cruda.
function paramsSummary(params: Record<string, unknown>, blueprint?: Blueprint): string {
  const dias = params.dias_antes;
  if (dias != null) return `${dias} día${Number(dias) === 1 ? "" : "s"} de anticipación`;
  const entries = Object.entries(params);
  if (entries.length === 0) return "";
  const campos = blueprint?.campos || [];
  const etiquetas = entries.map(([k]) => campos.find((c) => c.name === k)?.etiqueta);
  if (etiquetas.every((e) => Boolean(e))) {
    return entries.map(([, v], i) => `${etiquetas[i]}: ${String(v)}`).join(" · ");
  }
  return "Configuración personalizada";
}

export default function AutomationsSection() {
  const [plantillas, setPlantillas] = useState<Blueprint[]>([]);
  const [automatizaciones, setAutomatizaciones] = useState<Automation[]>([]);
  const [sugerencias, setSugerencias] = useState<Suggestion[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, Record<string, string>>>({});
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const nameByKey = Object.fromEntries(plantillas.map((p) => [p.key, p.nombre]));
  const blueprintByKey = Object.fromEntries(plantillas.map((p) => [p.key, p]));

  const load = useCallback(async () => {
    setMsg("");
    try {
      const [bp, auto, sug] = await Promise.all([
        apiGet<{ plantillas: Blueprint[] }>("/api/automations/blueprints"),
        apiGet<{ automatizaciones: Automation[] }>("/api/automations"),
        apiGet<{ sugerencias: Suggestion[] }>("/api/automations/suggestions"),
      ]);
      setPlantillas(bp.plantillas || []);
      setAutomatizaciones(auto.automatizaciones || []);
      setSugerencias(sug.sugerencias || []);
      const defaults: Record<string, Record<string, string>> = {};
      for (const p of bp.plantillas || []) {
        defaults[p.key] = {};
        for (const c of p.campos) {
          if (c.default != null) defaults[p.key][c.name] = String(c.default);
        }
      }
      setFormValues(defaults);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudieron cargar las automatizaciones. Recarga la página."));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createAutomation(key: string) {
    setMsg("");
    setBusy(key);
    try {
      const valores: Record<string, unknown> = {};
      const blueprint = plantillas.find((p) => p.key === key);
      for (const c of blueprint?.campos || []) {
        const raw = formValues[key]?.[c.name];
        if (c.tipo === "entero") {
          valores[c.name] = raw != null && raw !== "" ? Number(raw) : c.default;
        } else {
          valores[c.name] = raw ?? c.default ?? "";
        }
      }
      await apiSend("POST", "/api/automations", { plantilla: key, valores });
      await load();
      setExpandedKey(null);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo crear la automatización."));
    } finally {
      setBusy(null);
    }
  }

  async function removeAutomation(id: string) {
    if (!window.confirm("¿Quitar esta automatización? Mia dejará de aplicarla.")) return;
    setBusy(id);
    setMsg("");
    try {
      await apiSend("DELETE", `/api/automations/${id}`);
      await load();
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo quitar la automatización."));
    } finally {
      setBusy(null);
    }
  }

  async function acceptSuggestion(id: string) {
    setBusy(id);
    setMsg("");
    try {
      await apiSend("POST", `/api/automations/suggestions/${id}/accept`);
      await load();
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo aceptar la sugerencia."));
    } finally {
      setBusy(null);
    }
  }

  async function dismissSuggestion(id: string) {
    setBusy(id);
    setMsg("");
    try {
      await apiSend("POST", `/api/automations/suggestions/${id}/dismiss`);
      await load();
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo descartar la sugerencia."));
    } finally {
      setBusy(null);
    }
  }

  if (!loaded) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <p className="text-sm text-muted-foreground">
        Mia puede avisarte con anticipación de plazos o eventos que tú ya fijaste. Nada se activa solo: tú creas o aceptas cada automatización.
      </p>
      {msg ? <p role="alert" className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{msg}</p> : null}

      <div>
        <h3 className="mb-2 text-sm font-semibold">Sugerencias de Mia</h3>
        {sugerencias.length === 0 ? (
          <div className="flex items-start gap-3 rounded-lg border border-dashed border-border bg-card/40 backdrop-blur-md shadow-neu-raised px-4 py-4">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">
              No hay sugerencias pendientes. A medida que uses a Mia, ella te propondrá avisos útiles aquí.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {sugerencias.map((s) => (
              <li key={s.id} className="rounded-lg border border-border/10 bg-card shadow-neu-raised px-4 py-3">
                <div className="font-medium">{s.nombre}</div>
                <p className="mt-1 text-sm text-muted-foreground">{s.rationale}</p>
                {Object.keys(s.params || {}).length ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {paramsSummary(s.params, blueprintByKey[s.blueprint_key])}
                  </p>
                ) : null}
                {s.toca_plazo_procesal ? (
                  <p className="mt-2 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-xs text-warning">
                    Toca plazos procesales — Mia no calcula términos; cada fecha queda pendiente de tu confirmación.
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => acceptSuggestion(s.id)} disabled={busy === s.id}>
                    Activar
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => dismissSuggestion(s.id)} disabled={busy === s.id}>
                    Descartar
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Automatizaciones activas</h3>
        {automatizaciones.length === 0 ? (
          <div className="flex items-start gap-3 rounded-lg border border-dashed border-border bg-card/40 backdrop-blur-md shadow-neu-raised px-4 py-4">
            <Repeat className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">
              Aún no tienes automatizaciones activas. Crea una abajo o acepta una sugerencia de Mia.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {automatizaciones.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/10 bg-card shadow-neu-raised px-4 py-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {/* Nunca `a.kind` a secas: si la plantilla ya no está en el
                        catálogo, esa clave es un nombre técnico (§G). */}
                    {nameByKey[a.blueprint_key] || "Automatización"}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {paramsSummary(a.params || {}, blueprintByKey[a.blueprint_key])}
                  </div>
                  {a.is_procedural ? (
                    <p className="mt-1 text-xs font-medium text-warning">Plazo procesal — confirma tú las fechas</p>
                  ) : null}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeAutomation(a.id)}
                  disabled={busy === a.id}
                  className="shrink-0"
                >
                  Quitar
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Crear automatización</h3>
        <ul className="space-y-3">
          {plantillas.map((p) => {
            const open = expandedKey === p.key;
            return (
              <li key={p.key} className="rounded-lg border border-border/10 bg-card shadow-neu-raised px-4 py-3 transition-colors hover:border-primary/25">
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setExpandedKey(open ? null : p.key)}
                  className="w-full text-left"
                >
                  <div className="font-medium">{p.nombre}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{p.descripcion}</p>
                </button>
                {p.toca_plazo_procesal ? (
                  <p className="mt-2 text-xs font-medium text-warning">
                    Toca plazos procesales — solo avisa lo que tú ya registraste; nunca calcula un término.
                  </p>
                ) : null}
                {open ? (
                  <div className="mt-3 space-y-3 border-t border-border pt-3 animate-fade-in">
                    {p.campos.map((c) => (
                      <div key={c.name}>
                        <Label htmlFor={`${p.key}-${c.name}`} className="mb-1.5 block text-sm">
                          {c.etiqueta}
                        </Label>
                        {c.tipo === "opcion" && c.opciones.length ? (
                          <select
                            id={`${p.key}-${c.name}`}
                            value={formValues[p.key]?.[c.name] ?? String(c.default ?? "")}
                            onChange={(e) =>
                              setFormValues((fv) => ({
                                ...fv,
                                [p.key]: { ...fv[p.key], [c.name]: e.target.value },
                              }))
                            }
                            className="h-10 w-full max-w-xs rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            {c.opciones.map((o) => (
                              <option key={o} value={o}>{o}</option>
                            ))}
                          </select>
                        ) : (
                          <Input
                            id={`${p.key}-${c.name}`}
                            type={c.tipo === "entero" ? "number" : "text"}
                            inputMode={c.tipo === "entero" ? "numeric" : undefined}
                            min={c.min ?? undefined}
                            max={c.max ?? undefined}
                            value={formValues[p.key]?.[c.name] ?? String(c.default ?? "")}
                            onChange={(e) =>
                              setFormValues((fv) => ({
                                ...fv,
                                [p.key]: { ...fv[p.key], [c.name]: e.target.value },
                              }))
                            }
                            className="max-w-xs"
                          />
                        )}
                        {c.ayuda ? <p className="mt-1 text-xs text-muted-foreground">{c.ayuda}</p> : null}
                      </div>
                    ))}
                    <Button size="sm" onClick={() => createAutomation(p.key)} disabled={busy === p.key}>
                      {busy === p.key ? "Guardando…" : "Activar"}
                    </Button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setExpandedKey(p.key)}
                    className="mt-2 text-sm font-medium text-primary transition-colors hover:text-primary/80"
                  >
                    Configurar
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
