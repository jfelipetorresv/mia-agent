"use client";

// Mia · "Mi despacho" (Bloque C · C2: Perfil del despacho editable y unificado).
// Reemplaza a la vieja Despacho() de memoria/page.tsx, que editaba solo 5 campos contra
// el PUT /api/profile legado (una tabla desconectada de lo que el abogado respondió al
// conocer a Mia). Ahora edita la MISMA fuente canónica del onboarding (las respuestas de
// la entrevista) vía GET/PUT /api/profile/full — un solo lugar, un solo dato.
import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { apiGet, apiSend, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { CountrySelector, COUNTRY_NAME_BY_CODE } from "./CountrySelector";
import { TOOL_OPTIONS } from "./toolOptions";

type AnswerValue =
  | string
  | string[]
  | { firm?: string; lawyer?: string }
  | { country?: string; city?: string }
  | undefined;

type FullProfile = {
  responses: Record<string, AnswerValue>;
  jurisdictions: string[];
  extras: { tp_number: string; preferred_sources: string[] };
  summary: string;
  completed: boolean;
};

// TOOL_OPTIONS vive en ./toolOptions.ts — compartida con onboarding/page.tsx (p18): el
// abogado edita después de la entrevista con exactamente las mismas opciones, desde la
// MISMA fuente (C2: una sola lista, para que las dos pantallas nunca se contradigan).

// ── Conversores tolerantes (mismo criterio que onboarding/page.tsx) ─────────────────
function asNamePair(value: AnswerValue): { firm: string; lawyer: string } {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const v = value as { firm?: string; lawyer?: string };
    return { firm: v.firm || "", lawyer: v.lawyer || "" };
  }
  return { firm: typeof value === "string" ? value : "", lawyer: "" };
}

function asLocationPair(value: AnswerValue): { country: string; city: string } {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const v = value as { country?: string; city?: string };
    return { country: v.country || "", city: v.city || "" };
  }
  return { country: typeof value === "string" ? value : "", city: "" };
}

function asList(value: AnswerValue): string[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim()) {
    return value.split(",").map((v) => v.trim()).filter(Boolean);
  }
  return [];
}

export default function MiDespachoSection() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [firm, setFirm] = useState({ firm: "", lawyer: "" });
  const [location, setLocation] = useState({ country: "", city: "" });
  const [countryCodes, setCountryCodes] = useState<string[]>([]);
  const [practiceAreas, setPracticeAreas] = useState<string[]>([]);
  const [clientType, setClientType] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [tpNumber, setTpNumber] = useState("");
  const [preferredSources, setPreferredSources] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [warning, setWarning] = useState("");
  const [summary, setSummary] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const full = await apiGet<FullProfile>("/api/profile/full");
        const r = full.responses || {};
        setFirm(asNamePair(r["identity.name"]));
        setLocation(asLocationPair(r["identity.location"]));
        setPracticeAreas(asList(r["jurisdiction.practice_areas"]));
        setClientType(asList(r["jurisdiction.client_type"]));
        setTools(asList(r["memory.tools_that_survived"]));
        setCountryCodes(full.jurisdictions || []);
        setTpNumber(full.extras?.tp_number || "");
        setPreferredSources(full.extras?.preferred_sources || []);
      } catch {
        setLoadError("No se pudo cargar tu perfil. Recarga la página.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    setSaveError("");
    setWarning("");
    try {
      // El merge del backend pisa por clave completa: se manda el OBJETO/VALOR
      // completo de cada clave que se edita aquí (nunca un parche parcial).
      const responses: Record<string, unknown> = {
        "identity.name": { firm: firm.firm, lawyer: firm.lawyer },
        "identity.location": { country: location.country, city: location.city },
        "jurisdiction.practice_areas": practiceAreas,
        "jurisdiction.client_type": clientType,
        "memory.tools_that_survived": tools,
      };
      // Mismo auto-llenado que onboarding/page.tsx finish(): la jurisdicción elegida
      // también rellena `jurisdiction.base` con los NOMBRES (para el SOUL.md/resumen).
      const countryNames = countryCodes.map((c) => COUNTRY_NAME_BY_CODE[c] ?? c);
      if (countryNames.length > 0) responses["jurisdiction.base"] = countryNames;

      const res = await apiSend<{ ok: boolean; summary: string; warning?: string }>(
        "PUT",
        "/api/profile/full",
        {
          responses,
          jurisdictions: countryCodes,
          extras: { tp_number: tpNumber, preferred_sources: preferredSources },
        },
      );
      setSummary(res.summary || "");
      if (res.warning) setWarning(res.warning);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      // Solo se muestra el mensaje del backend cuando viene en llano (detail); un código
      // crudo tipo "Error 500" jamás se le enseña al abogado (§G).
      setSaveError(
        e instanceof ApiError && !e.message.startsWith("Error ")
          ? e.message
          : "No se pudo guardar tu perfil. Intenta de nuevo.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>;
  }

  return (
    <div className="animate-slide-up space-y-5">
      <p className="text-sm text-muted-foreground">
        Es lo mismo que respondiste al conocer a Mia — edítalo aquí sin repetir la entrevista.
      </p>

      <section className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">Identidad</h3>
        <TextField label="Nombre del despacho" value={firm.firm} onChange={(v) => setFirm({ ...firm, firm: v })} />
        <TextField
          label="Tu nombre (abogado principal)"
          value={firm.lawyer}
          onChange={(v) => setFirm({ ...firm, lawyer: v })}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="País" value={location.country} onChange={(v) => setLocation({ ...location, country: v })} />
          <TextField label="Ciudad" value={location.city} onChange={(v) => setLocation({ ...location, city: v })} />
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">Jurisdicción y práctica</h3>
        <p className="text-xs text-muted-foreground">
          Esto le dice a Mia qué normas y jurisprudencia usar. Puedes elegir más de un país.
        </p>
        <CountrySelector value={countryCodes} onChange={setCountryCodes} />
        <ChipsField label="Áreas de práctica" value={practiceAreas} onChange={setPracticeAreas} />
        <ChipsField label="Tipo de cliente" value={clientType} onChange={setClientType} />
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">Datos profesionales</h3>
        <TextField label="Tarjeta profesional" value={tpNumber} onChange={setTpNumber} />
        <ChipsField label="Fuentes preferidas" value={preferredSources} onChange={setPreferredSources} />
      </section>

      <section className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">Herramientas</h3>
        <ToolsChecklist value={tools} onChange={setTools} />
      </section>

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button onClick={save} disabled={saving}>
          {saving ? "Guardando…" : "Guardar"}
        </Button>
        {saved ? (
          <span className="flex items-center gap-1.5 text-sm text-success animate-fade-in">
            <Check className="h-4 w-4" />
            Guardado
          </span>
        ) : null}
      </div>
      {saveError ? <p className="text-sm text-destructive">{saveError}</p> : null}
      {warning ? <p className="text-sm text-warning">{warning}</p> : null}
      {summary ? (
        <details className="rounded-xl border border-border bg-card/60">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
            Así entendí a tu despacho
          </summary>
          <div className="whitespace-pre-wrap border-t border-border px-4 py-3 text-sm leading-relaxed text-muted-foreground">
            {summary}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = `despacho-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function ChipsField({ label, value, onChange }: { label: string; value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  }
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-input bg-card px-2 py-2 transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background">
        {value.map((chip) => (
          <span
            key={chip}
            className="flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
          >
            {chip}
            <button
              type="button"
              onClick={() => onChange(value.filter((c) => c !== chip))}
              aria-label={`Quitar ${chip}`}
              className="rounded-full p-0.5 transition-opacity hover:opacity-75"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={add}
          placeholder="Escribe y presiona Enter"
          className="min-w-[120px] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
        />
      </div>
    </div>
  );
}

function ToolsChecklist({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const [customDraft, setCustomDraft] = useState("");
  const curatedNames = new Set(TOOL_OPTIONS.map((t) => t.name));
  const customTools = value.filter((v) => !curatedNames.has(v));

  function toggle(name: string, checked: boolean) {
    if (checked) onChange([...value, name]);
    else onChange(value.filter((v) => v !== name));
  }

  function addCustom() {
    const tool = customDraft.trim();
    if (!tool || value.includes(tool)) {
      setCustomDraft("");
      return;
    }
    onChange([...value, tool]);
    setCustomDraft("");
  }

  return (
    <div className="space-y-3">
      {TOOL_OPTIONS.map((tool) => {
        const checked = value.includes(tool.name);
        const disabled = Boolean(tool.comingSoon);
        return (
          <label
            key={tool.name}
            className={`flex gap-3 rounded-xl border px-4 py-3 transition-colors ${
              disabled
                ? "cursor-not-allowed border-border bg-muted/40 opacity-70"
                : checked
                  ? "cursor-pointer border-primary/40 bg-primary/5"
                  : "cursor-pointer border-border bg-card hover:border-primary/25"
            }`}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled}
              onChange={(e) => toggle(tool.name, e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium">
                {tool.name}
                {tool.comingSoon ? (
                  <span className="ml-2 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-normal text-warning">
                    Próximamente
                  </span>
                ) : null}
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{tool.description}</span>
            </span>
          </label>
        );
      })}

      {customTools.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {customTools.map((tool) => (
            <button
              key={tool}
              type="button"
              onClick={() => onChange(value.filter((v) => v !== tool))}
              className="rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-85"
            >
              {tool} ×
            </button>
          ))}
        </div>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor="despacho-otra-herramienta">Otra herramienta</Label>
        <div className="flex gap-2">
          <Input
            id="despacho-otra-herramienta"
            value={customDraft}
            onChange={(e) => setCustomDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            placeholder="Escribe el nombre y presiona Enter"
          />
          <Button type="button" variant="outline" onClick={addCustom} disabled={!customDraft.trim()} className="shrink-0">
            Añadir
          </Button>
        </div>
      </div>
    </div>
  );
}
