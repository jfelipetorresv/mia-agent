"use client";

import { useEffect, useState } from "react";
import { Drama, Lock, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import GuideInterviewWizard from "@/app/_components/GuideInterviewWizard";
import { PageShell } from "@/app/_components/PageShell";
import { SectionTitle } from "@/app/_components/SectionTitle";
import { Card, cardVariants } from "@/components/ui/card";
import { staggerStyle } from "@/lib/motion";
import { cn } from "@/lib/utils";

// Tope de guías que un agente puede priorizar (debe coincidir con MAX_LINKED_PLAYBOOKS del backend).
const MAX_LINKED_GUIDES = 8;

type Guide = { id: string; title: string; status: string };

type Persona = {
  id: string;
  name: string;
  title: string;
  role_prompt: string;
  tone: string;
  focus_areas: string[];
  model_tier: "estandar" | "local";
  summon_phrases: string[];
  description: string;
  enabled: boolean;
  playbook_ids: string[];
  capabilities: string[];
};

/** Una capacidad ofrecible, con lo que ESTA instalación puede cumplir de verdad. */
type Capacidad = {
  clave: string;
  titulo: string;
  descripcion: string;
  disponible: boolean;
  razon: string;
};

type PersonaForm = {
  name: string;
  title: string;
  role_prompt: string;
  tone: string;
  focus_areas: string[];
  model_tier: "estandar" | "local";
  summon_phrases: string[];
  description: string;
  enabled: boolean;
  playbook_ids: string[];
  capabilities: string[];
};

const EMPTY_FORM: PersonaForm = {
  name: "",
  title: "",
  role_prompt: "",
  tone: "",
  focus_areas: [],
  model_tier: "estandar",
  summon_phrases: [],
  description: "",
  enabled: true,
  capabilities: [],
  playbook_ids: [],
};

function motorLabel(tier: string): string {
  return tier === "local" ? "Siempre el motor local — más privado" : "El motor del despacho";
}

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

export default function PersonasPage() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [guides, setGuides] = useState<Guide[]>([]);
  const [capacidades, setCapacidades] = useState<Capacidad[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadErr, setLoadErr] = useState("");
  const [editing, setEditing] = useState<Persona | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<PersonaForm>(EMPTY_FORM);
  const [formMsg, setFormMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [miaNotice, setMiaNotice] = useState("");

  async function load() {
    setLoadErr("");
    try {
      const res = await apiGet<{ personas: Persona[] }>("/api/personas");
      setPersonas(res.personas || []);
    } catch (err) {
      setPersonas([]);
      setLoadErr(apiMessage(err, "No se pudieron cargar los agentes. Recarga la página."));
    } finally {
      setLoaded(true);
    }
  }

  async function loadGuides() {
    try {
      // Se piden TODAS (no solo activas): una guía archivada que siga vinculada a un
      // agente debe verse en el formulario (con su etiqueta) para que el cupo "N de 8"
      // nunca lo ocupen guías invisibles que el abogado no puede desmarcar.
      const res = await apiGet<Guide[]>("/api/playbooks?status=todos");
      setGuides((res || []).map((g) => ({ id: g.id, title: g.title, status: g.status || "active" })));
    } catch {
      setGuides([]);
    }
  }

  async function loadCapacidades() {
    try {
      const res = await apiGet<{ capacidades: Capacidad[] }>("/api/personas/capacidades");
      setCapacidades(res.capacidades || []);
    } catch {
      // Sin catálogo no se ofrece el control: es preferible no mostrarlo a mostrarlo sin
      // poder decir cuáles funcionan de verdad en este equipo.
      setCapacidades([]);
    }
  }

  useEffect(() => {
    load();
    loadGuides();
    loadCapacidades();
  }, []);

  function openCreate() {
    setEditing(null);
    setCreating(true);
    setForm(EMPTY_FORM);
    setFormMsg("");
    setMiaNotice("");
  }

  function openEdit(p: Persona) {
    setCreating(false);
    setEditing(p);
    setForm({
      name: p.name,
      title: p.title || "",
      role_prompt: p.role_prompt,
      tone: p.tone || "",
      focus_areas: [...(p.focus_areas || [])],
      model_tier: p.model_tier === "local" ? "local" : "estandar",
      summon_phrases: [...(p.summon_phrases || [])],
      description: p.description || "",
      enabled: p.enabled,
      playbook_ids: [...(p.playbook_ids || [])],
      capabilities: [...(p.capabilities || [])],
    });
    setFormMsg("");
    setMiaNotice("");
  }

  // Bloque C: Mia terminó de diseñar un agente → se abre el formulario de CREACIÓN
  // precargado con el borrador. Nada se guarda hasta que el abogado pulse Guardar (gate HITL).
  function onMiaDraftReady(
    draft: Record<string, unknown>,
    _explanation: string,
    suggestedPlaybookIds: string[],
  ) {
    const existing = new Set(guides.map((g) => g.id));
    const linked = (suggestedPlaybookIds || []).filter((id) => existing.has(id)).slice(0, MAX_LINKED_GUIDES);
    const asStr = (v: unknown) => (typeof v === "string" ? v : "");
    const asList = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
    setEditing(null);
    setCreating(true);
    setForm({
      name: asStr(draft.name),
      title: asStr(draft.title),
      role_prompt: asStr(draft.role_prompt),
      tone: asStr(draft.tone),
      focus_areas: asList(draft.focus_areas),
      model_tier: "estandar",
      summon_phrases: asList(draft.summon_phrases),
      description: asStr(draft.description),
      enabled: true,
      playbook_ids: linked,
      capabilities: [],
    });
    setFormMsg("");
    setMiaNotice(
      "Mia preparó este borrador. Revísalo y ajústalo — solo se guardará cuando pulses Guardar.",
    );
  }

  function closeForm() {
    setEditing(null);
    setCreating(false);
    setForm(EMPTY_FORM);
    setFormMsg("");
    setMiaNotice("");
  }

  async function saveForm() {
    setFormMsg("");
    if (!form.name.trim() || !form.role_prompt.trim()) {
      setFormMsg("El nombre y cómo debe razonar y hablar son obligatorios.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        name: form.name.trim(),
        title: form.title.trim(),
        role_prompt: form.role_prompt.trim(),
        tone: form.tone.trim(),
        focus_areas: form.focus_areas,
        model_tier: form.model_tier,
        summon_phrases: form.summon_phrases,
        description: form.description.trim(),
        enabled: form.enabled,
        playbook_ids: form.playbook_ids,
        capabilities: form.capabilities,
      };
      if (creating) {
        await apiSend("POST", "/api/personas", body);
      } else if (editing) {
        await apiSend("PUT", `/api/personas/${editing.id}`, body);
      }
      closeForm();
      await load();
    } catch (err) {
      setFormMsg(apiMessage(err, "No se pudo guardar el agente. Intenta de nuevo."));
    } finally {
      setBusy(false);
    }
  }

  async function removePersona(p: Persona) {
    if (!window.confirm(`¿Eliminar a "${p.name}"? Ya no podrás invocarlo en el chat.`)) return;
    setFormMsg("");
    try {
      await apiSend("DELETE", `/api/personas/${p.id}`);
      if (editing?.id === p.id) closeForm();
      await load();
    } catch (err) {
      setFormMsg(apiMessage(err, "No se pudo eliminar el agente. Intenta de nuevo."));
    }
  }

  if (!loaded) {
    return (
      <PageShell className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-lg" />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Agentes jurídicos"
      subtitle="Roles especializados que invocas en el chat — por ejemplo «actúa como litigante» o «revisa las citas». Cada agente colorea el tono de Mia en esa conversación y puede priorizar tus guías; nada se activa solo."
      actions={
        !creating && !editing ? (
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button variant="outline" onClick={() => setWizardOpen(true)} className="gap-2">
              <Sparkles className="h-4 w-4" />
              Crear con Mia
            </Button>
            <Button onClick={openCreate} className="gap-2">
              <Plus className="h-4 w-4" />
              Nuevo agente
            </Button>
          </div>
        ) : null
      }
      className="space-y-8"
    >
      <GuideInterviewWizard
        open={wizardOpen}
        onOpenChange={setWizardOpen}
        kind="agente"
        onDraftReady={onMiaDraftReady}
      />

      {loadErr ? <p role="alert" className="rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{loadErr}</p> : null}
      {formMsg && !creating && !editing ? (
        <p role="alert" className="rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{formMsg}</p>
      ) : null}

      {creating || editing ? (
        <PersonaFormPanel
          title={creating ? "Nuevo agente" : `Editar: ${editing?.name}`}
          form={form}
          setForm={setForm}
          onSave={saveForm}
          onCancel={closeForm}
          busy={busy}
          msg={formMsg}
          guides={guides}
          capacidades={capacidades}
          notice={miaNotice}
        />
      ) : null}

      {personas.length === 0 && !loadErr ? (
        <Card variant="dashed" className="animate-slide-up px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Drama className="h-6 w-6" />
          </div>
          <h2 className="text-title">Aún no hay agentes configurados</h2>
          <p className="mx-auto mt-2 max-w-sm text-body text-muted-foreground">
            Un agente es un rol que Mia adopta cuando se lo pides en el chat:
            un litigante agresivo, un revisor de citas escéptico, un conciliador.
            Crea el primero o recarga para ver los de fábrica.
          </p>
          <Button onClick={openCreate} className="mt-6 gap-2">
            <Plus className="h-4 w-4" />
            Nuevo agente
          </Button>
        </Card>
      ) : (
        <ul className="space-y-3">
          {personas.map((p, i) => (
            <li
              key={p.id}
              className={cn(
                cardVariants(),
                "animate-slide-up px-5 py-4 transition-colors duration-200 hover:border-primary/25",
              )}
              style={staggerStyle(i)}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 gap-3.5">
                  <div
                    className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                      p.enabled ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    <Drama className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-section">{p.name}</span>
                      {p.title ? <span className="text-body text-muted-foreground">· {p.title}</span> : null}
                      {!p.enabled ? <Badge variant="secondary">Deshabilitado</Badge> : null}
                      {p.model_tier === "local" ? (
                        <Badge variant="secondary" className="gap-1 bg-success/15 text-success">
                          <Lock className="h-3 w-3" />
                          Motor local
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-1.5 text-body text-muted-foreground line-clamp-2">
                      {p.description || p.role_prompt}
                    </p>
                    {p.summon_phrases?.length ? (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <span className="text-meta text-muted-foreground">Invócalo con:</span>
                        {p.summon_phrases.map((f) => (
                          <span
                            key={f}
                            className="rounded-full bg-accent px-2 py-0.5 text-meta text-accent-foreground"
                          >
                            «{f}»
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => openEdit(p)} className="gap-1.5">
                    <Pencil className="h-3.5 w-3.5" />
                    Editar
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removePersona(p)}
                    className="gap-1.5 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Eliminar
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}

/**
 * QUÉ PUEDE HACER ESTE AGENTE (D8 · punto 23 de la bitácora 2026-08-19).
 *
 * El formulario dejaba decir el nombre, el encargo, el tono y las frases con las que se
 * le llama, todo texto libre. No había forma de decir qué PUEDE hacer, así que el abogado
 * escribía «que lea los escaneados» dentro del encargo, donde no activa nada: una
 * instrucción en prosa no enciende una capacidad. Lo que se marca aquí viaja al prompt de
 * cada turno del agente (`render_persona_voice`), que es lo que convierte la casilla en
 * un control de verdad y no en una etiqueta.
 *
 * LO QUE ESTA PANTALLA NO HACE ES PROMETER. Marcar una capacidad es una decisión del
 * abogado; que la instalación pueda cumplirla es otra cosa distinta, y se dice por
 * separado con su razón concreta —la misma razón honesta del catálogo de ayudantes— en
 * vez de esconder la casilla o dejarla marcada sin efecto. Una capacidad no disponible se
 * puede conceder igual: queda concedida para cuando el componente esté, y mientras tanto
 * la pantalla dice exactamente qué falta.
 */
function CapacidadesField({
  capacidades,
  selected,
  onChange,
}: {
  capacidades: Capacidad[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  if (capacidades.length === 0) return null;

  function alternar(clave: string) {
    onChange(
      selected.includes(clave) ? selected.filter((c) => c !== clave) : [...selected, clave]
    );
  }

  return (
    <div className="space-y-2">
      <Label>Qué puede hacer</Label>
      <p className="text-meta text-muted-foreground">
        Además de su encargo. Lo que marques aquí se lo digo en cada turno suyo.
      </p>
      <div className="space-y-2">
        {capacidades.map((c) => (
          <label
            key={c.clave}
            className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border/10 bg-card shadow-neu-raised px-3 py-2.5"
          >
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
              checked={selected.includes(c.clave)}
              onChange={() => alternar(c.clave)}
            />
            <span className="min-w-0 flex-1">
              <span className="block text-body font-medium">{c.titulo}</span>
              <span className="block text-meta text-muted-foreground">{c.descripcion}</span>
              {!c.disponible ? (
                <span className="mt-1 block text-meta text-warning">{c.razon}</span>
              ) : null}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

function PersonaFormPanel({
  title,
  form,
  setForm,
  onSave,
  onCancel,
  busy,
  msg,
  guides,
  capacidades,
  notice,
}: {
  title: string;
  form: PersonaForm;
  setForm: (f: PersonaForm) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
  msg: string;
  guides: Guide[];
  capacidades: Capacidad[];
  notice: string;
}) {
  return (
    <Card variant="raised" className="animate-slide-up border-primary/25 p-6">
      <SectionTitle title={title} className="mb-5" />
      {notice ? (
        <p className="mb-5 flex items-start gap-2 rounded-md bg-primary/10 px-3 py-2 text-body text-primary">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
          {notice}
        </p>
      ) : null}
      <div className="space-y-4">
        <TextField label="Nombre" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <TextField label="Título (opcional)" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
        <div className="space-y-1.5">
          <Label htmlFor="role-prompt">Cómo debe razonar y hablar este agente</Label>
          <Textarea
            id="role-prompt"
            value={form.role_prompt}
            onChange={(e) => setForm({ ...form, role_prompt: e.target.value })}
            rows={5}
            className="resize-y"
            placeholder="Descríbelo como le darías instrucciones a un colega: qué prioriza, cómo argumenta, qué evita"
          />
        </div>
        <TextField label="Tono (opcional)" value={form.tone} onChange={(v) => setForm({ ...form, tone: v })} />
        <ChipsField
          label="Áreas de énfasis"
          value={form.focus_areas}
          onChange={(v) => setForm({ ...form, focus_areas: v })}
        />
        <ChipsField
          label="Frases con las que la llamas en el chat"
          value={form.summon_phrases}
          onChange={(v) => setForm({ ...form, summon_phrases: v })}
        />
        <div className="space-y-1.5">
          <Label htmlFor="motor-tier">Motor de trabajo</Label>
          <select
            id="motor-tier"
            value={form.model_tier}
            onChange={(e) => setForm({ ...form, model_tier: e.target.value as "estandar" | "local" })}
            className="h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-body outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="estandar">El motor del despacho</option>
            <option value="local">Siempre el motor local — más privado</option>
          </select>
          <p className="text-meta text-muted-foreground">{motorLabel(form.model_tier)}</p>
        </div>
        <CapacidadesField
          capacidades={capacidades}
          selected={form.capabilities}
          onChange={(c) => setForm({ ...form, capabilities: c })}
        />
        <GuidesLinkField
          guides={guides}
          selected={form.playbook_ids}
          onChange={(ids) => setForm({ ...form, playbook_ids: ids })}
        />
        <div className="space-y-1.5">
          <Label htmlFor="persona-desc">Descripción breve (opcional)</Label>
          <Textarea
            id="persona-desc"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={2}
            className="resize-y"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-body">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
          />
          Agente habilitado (se puede invocar en el chat)
        </label>
      </div>
      {msg ? (
        <p role="alert" className="mt-4 rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{msg}</p>
      ) : null}
      <div className="mt-5 flex gap-2">
        <Button onClick={onSave} disabled={busy}>
          {busy ? "Guardando…" : "Guardar"}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
      </div>
    </Card>
  );
}

function GuidesLinkField({
  guides,
  selected,
  onChange,
}: {
  guides: Guide[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const atMax = selected.length >= MAX_LINKED_GUIDES;
  // Visibles: todas las activas + las archivadas que sigan vinculadas (para que el cupo
  // "N de 8" nunca lo ocupen guías que el abogado no puede ver ni desmarcar).
  const visibles = guides.filter((g) => g.status === "active" || selected.includes(g.id));
  function toggle(id: string, on: boolean) {
    if (on) {
      if (selected.includes(id) || atMax) return;
      onChange([...selected, id]);
    } else {
      onChange(selected.filter((x) => x !== id));
    }
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label>Guías vinculadas</Label>
        <span className="text-meta nums text-muted-foreground">
          {selected.length} de {MAX_LINKED_GUIDES}
        </span>
      </div>
      <p className="text-meta text-muted-foreground">Este agente prioriza estas guías cuando trabaja.</p>
      {visibles.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-3 py-3 text-body text-muted-foreground">
          Todavía no tienes guías activas en el despacho. Crea guías en Conocimiento y podrás vincularlas aquí.
        </p>
      ) : (
        <div className="max-h-52 space-y-1 overflow-auto rounded-lg border border-input bg-card p-2">
          {visibles.map((g) => {
            const checked = selected.includes(g.id);
            const disabled = !checked && atMax;
            const archivada = g.status !== "active";
            return (
              <label
                key={g.id}
                className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-body transition-colors hover:bg-accent ${
                  disabled ? "cursor-not-allowed opacity-50" : ""
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={(e) => toggle(g.id, e.target.checked)}
                  className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
                />
                <span className="min-w-0 truncate">{g.title}</span>
                {archivada && (
                  <Badge variant="outline" className="ml-auto shrink-0 text-meta">
                    Archivada — ya no se usa
                  </Badge>
                )}
              </label>
            );
          })}
        </div>
      )}
      {atMax ? (
        <p className="text-meta text-muted-foreground">
          Llegaste al máximo de {MAX_LINKED_GUIDES} guías. Quita alguna para vincular otra.
        </p>
      ) : null}
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = `persona-field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
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
          <Badge key={chip} variant="secondary" className="gap-1 pr-1">
            {chip}
            <button
              type="button"
              onClick={() => onChange(value.filter((c) => c !== chip))}
              aria-label={`Quitar ${chip}`}
              className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
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
          placeholder="Escribe y presiona Enter"
          className="min-w-[120px] flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
        />
      </div>
    </div>
  );
}
