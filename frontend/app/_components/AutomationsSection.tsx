"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiGet, apiSend } from "@/lib/api";

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

function paramsSummary(params: Record<string, unknown>): string {
  const dias = params.dias_antes;
  if (dias != null) return `${dias} día${Number(dias) === 1 ? "" : "s"} de anticipación`;
  return Object.entries(params)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");
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
    return <p className="text-sm text-gray-400">Cargando automatizaciones…</p>;
  }

  return (
    <div className="space-y-8">
      <p className="text-sm text-gray-500">
        Mia puede avisarte con anticipación de plazos o eventos que tú ya fijaste. Nada se activa solo: tú creas o aceptas cada automatización.
      </p>
      {msg ? <p role="alert" className="text-sm text-amber-700">{msg}</p> : null}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Sugerencias de Mia</h3>
        {sugerencias.length === 0 ? (
          <p className="text-sm text-gray-400">No hay sugerencias pendientes.</p>
        ) : (
          <ul className="space-y-3">
            {sugerencias.map((s) => (
              <li key={s.id} className="rounded-xl border border-gray-100 px-4 py-3">
                <div className="font-medium text-gray-900">{s.nombre}</div>
                <p className="mt-1 text-sm text-gray-600">{s.rationale}</p>
                {Object.keys(s.params || {}).length ? (
                  <p className="mt-1 text-xs text-gray-500">{paramsSummary(s.params)}</p>
                ) : null}
                {s.toca_plazo_procesal ? (
                  <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800">
                    Toca plazos procesales — Mia no calcula términos; tú confirmas cada fecha [VERIFICAR]
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => acceptSuggestion(s.id)}
                    disabled={busy === s.id}
                    className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
                  >
                    Activar
                  </button>
                  <button
                    type="button"
                    onClick={() => dismissSuggestion(s.id)}
                    disabled={busy === s.id}
                    className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
                  >
                    Descartar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Automatizaciones activas</h3>
        {automatizaciones.length === 0 ? (
          <p className="text-sm text-gray-400">Aún no tienes automatizaciones activas.</p>
        ) : (
          <ul className="space-y-2">
            {automatizaciones.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-100 px-4 py-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {nameByKey[a.blueprint_key] || a.kind}
                  </div>
                  <div className="text-sm text-gray-500">{paramsSummary(a.params || {})}</div>
                  {a.is_procedural ? (
                    <p className="mt-1 text-xs text-amber-700">Plazo procesal — confirma tú las fechas</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => removeAutomation(a.id)}
                  disabled={busy === a.id}
                  className="shrink-0 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Crear automatización</h3>
        <ul className="space-y-3">
          {plantillas.map((p) => {
            const open = expandedKey === p.key;
            return (
              <li key={p.key} className="rounded-xl border border-gray-100 px-4 py-3">
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setExpandedKey(open ? null : p.key)}
                  className="w-full text-left"
                >
                  <div className="font-medium text-gray-900">{p.nombre}</div>
                  <p className="mt-1 text-sm text-gray-500">{p.descripcion}</p>
                </button>
                {p.toca_plazo_procesal ? (
                  <p className="mt-2 text-xs text-amber-700">
                    Toca plazos procesales — solo avisa lo que tú ya registraste; nunca calcula un término.
                  </p>
                ) : null}
                {open ? (
                  <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
                    {p.campos.map((c) => (
                      <div key={c.name}>
                        <label htmlFor={`${p.key}-${c.name}`} className="mb-1 block text-sm text-gray-700">
                          {c.etiqueta}
                        </label>
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
                            className="w-full max-w-xs rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
                          >
                            {c.opciones.map((o) => (
                              <option key={o} value={o}>{o}</option>
                            ))}
                          </select>
                        ) : (
                          <input
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
                            className="w-full max-w-xs rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
                          />
                        )}
                        {c.ayuda ? <p className="mt-1 text-xs text-gray-400">{c.ayuda}</p> : null}
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => createAutomation(p.key)}
                      disabled={busy === p.key}
                      className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
                    >
                      {busy === p.key ? "Guardando…" : "Activar"}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setExpandedKey(p.key)}
                    className="mt-2 text-sm font-medium text-gray-600 hover:text-gray-900"
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
