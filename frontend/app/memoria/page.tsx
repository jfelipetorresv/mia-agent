"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiSend, apiUploadMany } from "@/lib/api";

type Tab = "despacho" | "wiki" | "saber" | "habilidades" | "sugerencias";

export default function MemoriaPage() {
  const [tab, setTab] = useState<Tab>("despacho");
  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="mb-6 text-2xl font-semibold">Conocimiento</h1>
      <div className="mb-6 flex flex-wrap gap-1 border-b border-gray-100">
        <TabBtn active={tab === "despacho"} onClick={() => setTab("despacho")}>Mi despacho</TabBtn>
        <TabBtn active={tab === "wiki"} onClick={() => setTab("wiki")}>Wiki del despacho</TabBtn>
        <TabBtn active={tab === "saber"} onClick={() => setTab("saber")}>Lo que Mia sabe</TabBtn>
        <TabBtn active={tab === "habilidades"} onClick={() => setTab("habilidades")}>Habilidades</TabBtn>
        <TabBtn active={tab === "sugerencias"} onClick={() => setTab("sugerencias")}>Sugerencias de Mia</TabBtn>
      </div>
      {tab === "despacho" ? <Despacho /> : null}
      {tab === "wiki" ? <Wiki /> : null}
      {tab === "saber" ? <Saber /> : null}
      {tab === "habilidades" ? <Habilidades /> : null}
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

type Profile = {
  name?: string;
  lawyer_name?: string;
  jurisdiction?: string;
  practice_areas?: string[];
  voice_adjectives?: string[];
};

function Despacho() {
  const [p, setP] = useState<Profile>({ jurisdiction: "", practice_areas: [], voice_adjectives: [] });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Profile>("/api/profile")
      .then((d) => setP({ jurisdiction: "", practice_areas: [], voice_adjectives: [], ...d }))
      .catch(() => {});
  }, []);

  async function save() {
    await apiSend("PUT", "/api/profile", p);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="space-y-4">
      <TextField label="Nombre del despacho" value={p.name || ""} onChange={(v) => setP({ ...p, name: v })} />
      <TextField label="Abogado responsable" value={p.lawyer_name || ""} onChange={(v) => setP({ ...p, lawyer_name: v })} />
      <TextField label="País y sistema jurídico principal" value={p.jurisdiction || ""} onChange={(v) => setP({ ...p, jurisdiction: v })} />
      <ChipsField label="Áreas de práctica" value={p.practice_areas || []} onChange={(v) => setP({ ...p, practice_areas: v })} />
      <ChipsField label="Estilo" value={p.voice_adjectives || []} onChange={(v) => setP({ ...p, voice_adjectives: v })} />
      <div className="flex items-center gap-3 pt-2">
        <button onClick={save} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">Guardar</button>
        {saved ? <span className="text-sm text-green-600">Guardado</span> : null}
      </div>
    </div>
  );
}

type Concept = { name: string; confidence: number; case_count: number; last_updated?: string };

function Wiki() {
  const [items, setItems] = useState<Concept[]>([]);
  const [selected, setSelected] = useState<Concept | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [correction, setCorrection] = useState("");

  useEffect(() => {
    apiGet<Concept[]>("/api/wiki/concepts").then(setItems).catch(() => setItems([]));
  }, []);

  async function open(c: Concept) {
    setSelected(c);
    setCorrection("");
    setMarkdown("");
    try {
      const res = await apiGet<{ markdown: string }>(`/api/wiki/concepts/${encodeURIComponent(c.name)}`);
      setMarkdown(res.markdown);
    } catch {
      setSelected(null);
    }
  }

  async function sendCorrection() {
    if (!selected || !correction.trim()) return;
    await apiSend("POST", `/api/wiki/concepts/${encodeURIComponent(selected.name)}/feedback`, { correction: correction.trim() });
    setSelected(null);
  }

  if (items.length === 0) {
    return <p className="py-8 text-center text-gray-400">Mia construirá este wiki a medida que trabajen juntos.</p>;
  }

  return (
    <div>
      <ul className="space-y-2">
        {items.map((c) => (
          <li key={c.name}>
            <button onClick={() => open(c)} className="w-full rounded-lg border border-gray-100 px-4 py-3 text-left hover:bg-gray-50">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="truncate font-medium">{c.name}</div>
                  <div className="text-sm text-gray-500">{c.case_count} casos · {c.last_updated || "sin fecha"}</div>
                </div>
                <div className="w-28">
                  <div className="h-1.5 rounded-full bg-gray-100">
                    <div className="h-1.5 rounded-full bg-gray-900" style={{ width: `${Math.round((c.confidence || 0) * 100)}%` }} />
                  </div>
                  <div className="mt-1 text-right text-xs text-gray-400">{Math.round((c.confidence || 0) * 100)}%</div>
                </div>
              </div>
            </button>
          </li>
        ))}
      </ul>
      {selected ? (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/30 p-4" onClick={() => setSelected(null)}>
          <div className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-semibold">{selected.name}</h2>
            <pre className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-700">{markdown}</pre>
            <label className="mb-1 mt-4 block text-sm font-medium text-gray-700">Sugerir corrección</label>
            <textarea value={correction} onChange={(e) => setCorrection(e.target.value)} className="h-24 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setSelected(null)} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">Cerrar</button>
              <button onClick={sendCorrection} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">Enviar</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

type Playbook = { id: string; title: string; summary: string; applies_when?: string };

function Saber() {
  const [items, setItems] = useState<Playbook[]>([]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ title: "", applies_when: "", content: "", summary: "" });

  async function load() {
    setItems(await apiGet<Playbook[]>("/api/playbooks").catch(() => []));
  }
  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!form.title.trim() || !form.content.trim()) return;
    await apiSend("POST", "/api/playbooks", {
      title: form.title.trim(),
      summary: form.summary.trim() || form.title.trim(),
      applies_when: form.applies_when.trim() || "Depende del contexto del asunto.",
      content: form.content.trim(),
    });
    setModal(false);
    setForm({ title: "", applies_when: "", content: "", summary: "" });
    await load();
  }

  const fileInput = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importDetail, setImportDetail] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);

  async function importFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setImporting(true);
    setImportMsg(null);
    setImportDetail([]);
    try {
      const res = await apiUploadMany<{ importados: string[]; omitidos: string[]; errores: string[] }>(
        "/api/playbooks/import", Array.from(files)
      );
      const n = res.importados?.length || 0;
      const om = res.omitidos?.length || 0;
      const er = res.errores?.length || 0;
      setImportMsg(
        `Se importaron ${n} guía${n === 1 ? "" : "s"}` +
        (om ? ` · ${om} ya existía${om === 1 ? "" : "n"} y se conservaron` : "") +
        (er ? ` · ${er} archivo${er === 1 ? "" : "s"} no se pudieron leer` : "") + "."
      );
      // El backend explica cada omisión/error en lenguaje llano — se muestran tal cual.
      setImportDetail([...(res.errores || []), ...(res.omitidos || []).map((t) => `${t}: ya existía; se conservó la versión guardada.`)]);
      await load();
    } catch {
      setImportMsg("No se pudieron importar las guías. Intenta de nuevo.");
    } finally {
      setImporting(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-end gap-2">
        <input ref={fileInput} type="file" multiple accept=".md,.txt,.docx" className="hidden"
               onChange={(e) => importFiles(e.target.files)} />
        <button onClick={() => fileInput.current?.click()} disabled={importing}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50">
          {importing ? "Importando…" : "Importar guías"}
        </button>
        <button onClick={() => setModal(true)} className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50">Agregar conocimiento</button>
      </div>
      {importMsg ? <p className="mb-1 text-sm text-gray-600">{importMsg}</p> : null}
      {importDetail.length > 0 ? (
        <ul className="mb-3 space-y-0.5 text-sm text-gray-500">
          {importDetail.map((d, i) => <li key={i}>· {d}</li>)}
        </ul>
      ) : null}
      {items.length === 0 ? (
        <p className="py-8 text-center text-gray-400">Mia todavía no tiene conocimiento guardado. Puedes importar las guías de trabajo del despacho (.md, .txt o Word).</p>
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
            <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} className="h-28 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setModal(false)} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">Cancelar</button>
              <button onClick={create} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">Guardar</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

type Skill = { skill_id: string; title: string; approval_rate: number; edit_rate: number; activations: number };

function Habilidades() {
  const [items, setItems] = useState<Skill[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    apiGet<Skill[]>("/api/skills/ranked")
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) {
    return <p className="py-8 text-center text-gray-400">Cargando…</p>;
  }
  if (items.length === 0) {
    return <p className="py-8 text-center text-gray-400">Mia todavía no tiene habilidades medidas. Se construyen a medida que apruebas o corriges su trabajo.</p>;
  }

  return (
    <div>
      <p className="mb-4 text-sm text-gray-500">Qué tan bien le va a Mia con cada procedimiento del despacho, según tus aprobaciones y correcciones.</p>
      <ul className="space-y-2">
        {items.map((s) => (
          <li key={s.skill_id} className="rounded-xl border border-gray-100 px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="truncate font-medium">{s.title}</div>
                <div className="text-sm text-gray-500">
                  Usada {s.activations} {s.activations === 1 ? "vez" : "veces"}
                  {s.activations > 0 ? ` · corregida el ${Math.round((s.edit_rate || 0) * 100)}%` : ""}
                </div>
              </div>
              <div className="w-28 shrink-0">
                <div className="h-1.5 rounded-full bg-gray-100">
                  <div className="h-1.5 rounded-full bg-gray-900" style={{ width: `${Math.round((s.approval_rate || 0) * 100)}%` }} />
                </div>
                <div className="mt-1 text-right text-xs text-gray-400">{Math.round((s.approval_rate || 0) * 100)}% aprobado</div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Proposal = { id: string; type: string; suggestion: string; reason: string; target?: string | null };
type CuratorMerge = { target_title?: string; reason?: string };
type CuratorDeletion = { title?: string; reason?: string };
type CuratorProposal = {
  id: string;
  merges?: CuratorMerge[];
  proposed_merges?: CuratorMerge[];
  deletions?: CuratorDeletion[];
  proposed_deletions?: CuratorDeletion[];
};

function Sugerencias() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [curator, setCurator] = useState<CuratorProposal[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setItems(await apiGet<Proposal[]>("/api/proposals").catch(() => []));
    setCurator(await apiGet<CuratorProposal[]>("/api/curator/proposals").catch(() => []));
    const weekly = await apiGet<{ report: string | null }>("/api/dreams/report").catch(() => ({ report: null }));
    setReport(weekly.report);
  }
  useEffect(() => {
    load();
  }, []);

  async function act(id: string, action: "apply" | "ignore") {
    await apiSend("POST", `/api/proposals/${id}/${action}`).catch(() => {});
    await load();
  }

  async function curatorAct(id: string, action: "approve" | "reject") {
    setMsg(null);
    try {
      await apiSend("POST", `/api/curator/proposals/${id}/${action}`);
    } catch (e) {
      // 409 = el conocimiento cambió desde que se generó (drift); otro error = genérico.
      const drift = e instanceof Error && e.message.includes("409");
      setMsg(drift
        ? "El conocimiento cambió desde que se generó esta propuesta y ya no se puede aplicar tal cual. Recházala: Mia generará una nueva actualizada en su próxima revisión."
        : "No se pudo procesar la propuesta. Intenta de nuevo.");
    }
    await load();
  }

  if (items.length === 0 && curator.length === 0 && !report) {
    return <p className="py-8 text-center text-gray-400">Mia aún no tiene sugerencias. Aparecerán con el uso.</p>;
  }

  return (
    <div className="space-y-3">
      {report ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <div className="mb-2 text-sm font-semibold">Resumen semanal</div>
          <p className="whitespace-pre-wrap text-sm text-gray-700">{report}</p>
        </div>
      ) : null}
      <ul className="space-y-3">
        {items.map((p) => (
          <li key={p.id} className="rounded-xl border border-gray-100 px-4 py-3">
            <div className="mb-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">{p.type}</div>
            {p.target ? (
              <div className="mb-1 text-sm font-medium text-gray-800">Procedimiento que se modificaría: {p.target}</div>
            ) : null}
            <div className="mb-2 whitespace-pre-wrap text-sm text-gray-700">{p.suggestion}</div>
            <div className="text-sm text-gray-500">{p.reason}</div>
            <div className="mt-3 flex gap-2">
              <button onClick={() => act(p.id, "apply")} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">Aplicar</button>
              <button onClick={() => act(p.id, "ignore")} className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">Ignorar</button>
            </div>
          </li>
        ))}
      </ul>
      {curator.length > 0 ? (
        <div>
          <h3 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-gray-400">Orden del conocimiento</h3>
          {msg ? <p className="mb-2 text-sm text-amber-700">{msg}</p> : null}
          <ul className="space-y-3">
            {curator.map((c) => {
              const merges = c.merges || c.proposed_merges || [];
              const deletions = c.deletions || c.proposed_deletions || [];
              return (
                <li key={c.id} className="rounded-xl border border-gray-100 px-4 py-3">
                  <div className="mb-2 text-sm text-gray-700">
                    Mia propone ordenar el conocimiento del despacho:
                    {merges.length > 0 ? ` unir ${merges.length} pareja${merges.length === 1 ? "" : "s"} de guías muy parecidas` : ""}
                    {merges.length > 0 && deletions.length > 0 ? " y" : ""}
                    {deletions.length > 0 ? ` archivar ${deletions.length} guía${deletions.length === 1 ? "" : "s"} sin uso` : ""}.
                  </div>
                  <ul className="mb-2 space-y-1 text-sm text-gray-500">
                    {merges.map((m, i) => <li key={`m${i}`}>· {m.target_title || m.reason}</li>)}
                    {deletions.map((d, i) => <li key={`d${i}`}>· Archivar: {d.title}</li>)}
                  </ul>
                  <div className="flex gap-2">
                    <button onClick={() => curatorAct(c.id, "approve")} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">Aprobar</button>
                    <button onClick={() => curatorAct(c.id, "reject")} className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">Rechazar</button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
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
            <button onClick={() => onChange(value.filter((c) => c !== chip))} className="text-gray-400 hover:text-gray-700">x</button>
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
          placeholder="Escribe y Enter..."
          className="min-w-[120px] flex-1 text-sm outline-none"
        />
      </div>
    </div>
  );
}
