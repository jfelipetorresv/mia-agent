"use client";

import { useEffect, useState } from "react";
import { ApiError, apiGet, apiSend } from "@/lib/api";

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
};

function motorLabel(tier: string): string {
  return tier === "local" ? "Siempre el motor local — más privado" : "El motor del despacho";
}

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

export default function PersonasPage() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadErr, setLoadErr] = useState("");
  const [editing, setEditing] = useState<Persona | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<PersonaForm>(EMPTY_FORM);
  const [formMsg, setFormMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoadErr("");
    try {
      const res = await apiGet<{ personas: Persona[] }>("/api/personas");
      setPersonas(res.personas || []);
    } catch (err) {
      setPersonas([]);
      setLoadErr(apiMessage(err, "No se pudieron cargar las personas. Recarga la página."));
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openCreate() {
    setEditing(null);
    setCreating(true);
    setForm(EMPTY_FORM);
    setFormMsg("");
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
    });
    setFormMsg("");
  }

  function closeForm() {
    setEditing(null);
    setCreating(false);
    setForm(EMPTY_FORM);
    setFormMsg("");
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
      };
      if (creating) {
        await apiSend("POST", "/api/personas", body);
      } else if (editing) {
        await apiSend("PUT", `/api/personas/${editing.id}`, body);
      }
      closeForm();
      await load();
    } catch (err) {
      setFormMsg(apiMessage(err, "No se pudo guardar la persona. Intenta de nuevo."));
    } finally {
      setBusy(false);
    }
  }

  async function removePersona(p: Persona) {
    if (!window.confirm(`¿Eliminar a "${p.name}"? Ya no podrás invocarla en el chat.`)) return;
    setFormMsg("");
    try {
      await apiSend("DELETE", `/api/personas/${p.id}`);
      if (editing?.id === p.id) closeForm();
      await load();
    } catch (err) {
      setFormMsg(apiMessage(err, "No se pudo eliminar la persona. Intenta de nuevo."));
    }
  }

  if (!loaded) {
    return <div className="p-10 text-gray-400">Cargando...</div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-8 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Personas jurídicas</h1>
          <p className="mt-2 text-sm text-gray-500">
            Roles especializados que invocas en el chat — por ejemplo «actúa como litigante» o «revisa las citas».
            Cada persona colorea el tono de Mia en ese turno; nada se activa solo.
          </p>
        </div>
        {!creating && !editing ? (
          <button
            onClick={openCreate}
            className="shrink-0 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
          >
            Crear persona
          </button>
        ) : null}
      </div>

      {loadErr ? <p role="alert" className="text-sm text-amber-700">{loadErr}</p> : null}
      {formMsg && !creating && !editing ? (
        <p role="alert" className="text-sm text-amber-700">{formMsg}</p>
      ) : null}

      {creating || editing ? (
        <PersonaFormPanel
          title={creating ? "Nueva persona" : `Editar: ${editing?.name}`}
          form={form}
          setForm={setForm}
          onSave={saveForm}
          onCancel={closeForm}
          busy={busy}
          msg={formMsg}
        />
      ) : null}

      {personas.length === 0 && !loadErr ? (
        <p className="py-8 text-center text-gray-400">
          Aún no hay personas configuradas. Crea la primera o recarga para ver las de fábrica.
        </p>
      ) : (
        <ul className="space-y-3">
          {personas.map((p) => (
            <li key={p.id} className="rounded-xl border border-gray-100 px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{p.name}</span>
                    {!p.enabled ? (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                        Deshabilitada
                      </span>
                    ) : null}
                  </div>
                  {p.title ? <div className="text-sm text-gray-500">{p.title}</div> : null}
                  <p className="mt-2 text-sm text-gray-600 line-clamp-2">{p.description || p.role_prompt}</p>
                  <p className="mt-2 text-xs text-gray-400">{motorLabel(p.model_tier)}</p>
                  {p.summon_phrases?.length ? (
                    <p className="mt-1 text-xs text-gray-400">
                      Frases: {p.summon_phrases.join(" · ")}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => openEdit(p)}
                    className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    Editar
                  </button>
                  <button
                    onClick={() => removePersona(p)}
                    className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    Eliminar
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
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
}: {
  title: string;
  form: PersonaForm;
  setForm: (f: PersonaForm) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
  msg: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-5">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      <div className="space-y-4">
        <TextField label="Nombre" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <TextField label="Título (opcional)" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
        <div>
          <label htmlFor="role-prompt" className="mb-1 block text-sm font-medium text-gray-700">
            Cómo debe razonar y hablar esta persona
          </label>
          <textarea
            id="role-prompt"
            value={form.role_prompt}
            onChange={(e) => setForm({ ...form, role_prompt: e.target.value })}
            rows={5}
            className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
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
        <div>
          <label htmlFor="motor-tier" className="mb-1 block text-sm font-medium text-gray-700">
            Motor de trabajo
          </label>
          <select
            id="motor-tier"
            value={form.model_tier}
            onChange={(e) => setForm({ ...form, model_tier: e.target.value as "estandar" | "local" })}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
          >
            <option value="estandar">El motor del despacho</option>
            <option value="local">Siempre el motor local — más privado</option>
          </select>
        </div>
        <div>
          <label htmlFor="persona-desc" className="mb-1 block text-sm font-medium text-gray-700">
            Descripción breve (opcional)
          </label>
          <textarea
            id="persona-desc"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={2}
            className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="h-4 w-4 rounded border-gray-300"
          />
          Persona habilitada (se puede invocar en el chat)
        </label>
      </div>
      {msg ? (
        <p role="alert" className="mt-4 text-sm text-amber-700">{msg}</p>
      ) : null}
      <div className="mt-4 flex gap-2">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {busy ? "Guardando…" : "Guardar"}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
      />
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
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 py-2">
        {value.map((chip) => (
          <span key={chip} className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-sm">
            {chip}
            <button type="button" onClick={() => onChange(value.filter((c) => c !== chip))} className="text-gray-400 hover:text-gray-700">
              ×
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
          placeholder="Escribe y Enter…"
          className="min-w-[120px] flex-1 text-sm outline-none"
        />
      </div>
    </div>
  );
}
