"use client";

import { useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";

type Tab = "despacho" | "saber" | "sugerencias";

export default function MemoriaPage() {
  const [tab, setTab] = useState<Tab>("despacho");
  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="mb-6 text-2xl font-semibold">Conocimiento</h1>
      <div className="mb-6 flex gap-1 border-b border-gray-100">
        <TabBtn active={tab === "despacho"} onClick={() => setTab("despacho")}>Mi despacho</TabBtn>
        <TabBtn active={tab === "saber"} onClick={() => setTab("saber")}>Lo que Mia sabe</TabBtn>
        <TabBtn active={tab === "sugerencias"} onClick={() => setTab("sugerencias")}>Sugerencias de Mia</TabBtn>
      </div>
      {tab === "despacho" ? <Despacho /> : null}
      {tab === "saber" ? <Saber /> : null}
      {tab === "sugerencias" ? <Sugerencias /> : null}
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
        active ? "border-gray-900 text-gray-900" : "border-transparent text-gray-400 hover:text-gray-600"
      }`}
    >
      {children}
    </button>
  );
}

// ── Mi despacho ──────────────────────────────────────────────────────────────
type Profile = {
  name?: string;
  lawyer_name?: string;
  jurisdiction?: string;
  practice_areas?: string[];
  voice_adjectives?: string[];
};

function Despacho() {
  const [p, setP] = useState<Profile>({ jurisdiction: "colombia", practice_areas: [], voice_adjectives: [] });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Profile>("/api/profile")
      .then((d) => setP({ jurisdiction: "colombia", practice_areas: [], voice_adjectives: [], ...d }))
      .catch(() => {});
  }, []);

  async function save() {
    try {
      await apiSend("PUT", "/api/profile", p);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-4">
      <TextField label="Nombre del despacho" value={p.name || ""} onChange={(v) => setP({ ...p, name: v })} />
      <TextField label="Abogado responsable" value={p.lawyer_name || ""} onChange={(v) => setP({ ...p, lawyer_name: v })} />
      <TextField label="Jurisdicción" value={p.jurisdiction || ""} onChange={(v) => setP({ ...p, jurisdiction: v })} />
      <ChipsField label="Áreas de práctica" value={p.practice_areas || []} onChange={(v) => setP({ ...p, practice_areas: v })} />
      <ChipsField label="Estilo (3 adjetivos)" value={p.voice_adjectives || []} onChange={(v) => setP({ ...p, voice_adjectives: v })} />
      <div className="flex items-center gap-3 pt-2">
        <button onClick={save} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">
          Guardar
        </button>
        {saved ? <span className="text-sm text-green-600">Guardado</span> : null}
      </div>
    </div>
  );
}

// ── Lo que Mia sabe (playbooks) ──────────────────────────────────────────────
type Playbook = { id: string; title: string; summary: string; applies_when?: string };

function Saber() {
  const [items, setItems] = useState<Playbook[]>([]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ title: "", applies_when: "", content: "", summary: "" });

  async function load() {
    try {
      setItems(await apiGet<Playbook[]>("/api/playbooks"));
    } catch {
      setItems([]);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!form.title.trim() || !form.content.trim()) return;
    try {
      await apiSend("POST", "/api/playbooks", {
        title: form.title.trim(),
        summary: form.summary.trim() || form.title.trim(),
        applies_when: form.applies_when.trim() || "—",
        content: form.content.trim(),
      });
      setModal(false);
      setForm({ title: "", applies_when: "", content: "", summary: "" });
      await load();
    } catch {
      /* ignore */
    }
  }

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button onClick={() => setModal(true)} className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50">
          Agregar conocimiento
        </button>
      </div>
      {items.length === 0 ? (
        <p className="py-8 text-center text-gray-400">Mia todavía no tiene conocimiento guardado.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((p) => (
            <li key={p.id} className="rounded-xl border border-gray-100 px-4 py-3">
              <div className="font-medium">{p.title}</div>
              <div className="text-sm text-gray-500">{p.summary}</div>
            </li>
          ))}
        </ul>
      )}

      {modal ? (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/30 p-4" onClick={() => setModal(false)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-semibold">Enseñarle algo a Mia</h2>
            <TextField label="Título" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
            <TextField label="Cuándo aplica" value={form.applies_when} onChange={(v) => setForm({ ...form, applies_when: v })} />
            <div className="mb-1 mt-3 block text-sm font-medium text-gray-700">Contenido</div>
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              className="h-28 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setModal(false)} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancelar
              </button>
              <button onClick={create} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">
                Guardar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── Sugerencias de Mia (feedback_proposals) ─────────────────────────────────
type Proposal = { id: string; type: string; suggestion: string; reason: string };

function Sugerencias() {
  const [items, setItems] = useState<Proposal[]>([]);

  async function load() {
    try {
      setItems(await apiGet<Proposal[]>("/api/proposals"));
    } catch {
      setItems([]);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function act(id: string, action: "apply" | "ignore") {
    try {
      await apiSend("POST", `/api/proposals/${id}/${action}`);
      await load();
    } catch {
      /* ignore */
    }
  }

  if (items.length === 0) {
    return <p className="py-8 text-center text-gray-400">Mia aún no tiene sugerencias. Aparecerán con el uso.</p>;
  }

  return (
    <ul className="space-y-3">
      {items.map((p) => (
        <li key={p.id} className="rounded-xl border border-gray-100 px-4 py-3">
          <div className="mb-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">{p.type}</div>
          <div className="text-sm text-gray-700">{p.reason}</div>
          <div className="mt-3 flex gap-2">
            <button onClick={() => act(p.id, "apply")} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">
              Aplicar
            </button>
            <button onClick={() => act(p.id, "ignore")} className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">
              Ignorar
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ── campos reutilizables ─────────────────────────────────────────────────────
function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
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
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 px-2 py-2">
        {value.map((chip) => (
          <span key={chip} className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-sm">
            {chip}
            <button onClick={() => onChange(value.filter((c) => c !== chip))} className="text-gray-400 hover:text-gray-700">
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
