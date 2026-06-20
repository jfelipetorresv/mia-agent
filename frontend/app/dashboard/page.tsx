"use client";

import { useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";

type Stats = {
  matters_active?: number;
  documents_indexed?: number;
  knowledge_items?: number;
  proposals_pending?: number;
  cost_month_usd?: number;
  playbooks_active?: number;
  playbooks_archived?: number;
  scheduler_jobs?: { label: string; next_run?: string | null; last_run?: string | null }[];
  connectors?: {
    knowledge_base?: { active?: boolean; last_sync?: string | null; chunks?: number };
    external_store?: { active?: boolean; vectors_count?: number };
    models?: string[];
  };
  second_brain?: {
    weekly_approval_rate?: number;
    concepts_count?: number;
    skills_active?: number;
    skills_archived?: number;
    next_consolidation?: string | null;
    last_report?: string | null;
  };
};

function fmt(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

export default function DashboardPage() {
  const [s, setS] = useState<Stats | null>(null);
  const [vaultPath, setVaultPath] = useState("");
  const [pineconeKey, setPineconeKey] = useState("");
  const [pineconeIndex, setPineconeIndex] = useState("");
  const [status, setStatus] = useState("");
  const [model, setModel] = useState("");

  async function load() {
    const data = await apiGet<Stats>("/api/dashboard/stats");
    setS(data);
    if (!model && data.connectors?.models?.[0]) setModel(data.connectors.models[0]);
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  async function syncObsidian() {
    setStatus("Sincronizando...");
    const res = await apiSend<{ chunks_indexed: number }>("POST", "/api/connectors/obsidian/sync", { vault_path: vaultPath || null });
    setStatus(`${res.chunks_indexed} documentos sincronizados`);
    await load();
  }

  async function connectPinecone() {
    setStatus("Conectando...");
    const res = await apiSend<{ status: string; vectors_count: number }>("POST", "/api/connectors/pinecone/configure", {
      api_key: pineconeKey,
      index_name: pineconeIndex,
    });
    setStatus(res.status === "active" ? `${res.vectors_count} vectores disponibles` : "No se pudo activar");
    await load();
  }

  if (!s) return <div className="p-10 text-gray-400">Cargando...</div>;
  const c = s.connectors || {};
  const brain = s.second_brain || {};

  return (
    <div className="mx-auto max-w-4xl space-y-10 px-8 py-10">
      <h1 className="text-2xl font-semibold">Panel de control</h1>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Actividad</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Asuntos activos" value={s.matters_active} />
          <Stat label="Documentos" value={s.documents_indexed} />
          <Stat label="Conocimiento" value={s.knowledge_items} />
          <Stat label="Sugerencias" value={s.proposals_pending} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Conectores</h2>
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-100 p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">Obsidian</div>
                <div className="text-sm text-gray-500">
                  {c.knowledge_base?.active ? `Activo · última sync ${fmt(c.knowledge_base.last_sync)}` : "Inactivo"}
                </div>
              </div>
              <button onClick={syncObsidian} className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-700">Sincronizar</button>
            </div>
            <input value={vaultPath} onChange={(e) => setVaultPath(e.target.value)} placeholder="Ruta del vault" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
          </div>

          <div className="rounded-lg border border-gray-100 p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">Pinecone</div>
                <div className="text-sm text-gray-500">
                  {c.external_store?.active ? `Activo · ${c.external_store.vectors_count || 0} vectores` : "Inactivo"}
                </div>
              </div>
              <button onClick={connectPinecone} className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-700">Conectar</button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={pineconeKey} onChange={(e) => setPineconeKey(e.target.value)} placeholder="API key" className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
              <input value={pineconeIndex} onChange={(e) => setPineconeIndex(e.target.value)} placeholder="Index" className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
            </div>
          </div>

          <div className="rounded-lg border border-gray-100 p-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Modelo preferido</label>
            <select value={model} onChange={(e) => setModel(e.target.value)} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400">
              {(c.models || []).map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
          {status ? <p className="text-sm text-gray-500">{status}</p> : null}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Salud del second brain</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Aprobación semanal" value={Math.round((brain.weekly_approval_rate || 0) * 100)} suffix="%" />
          <Stat label="Conceptos" value={brain.concepts_count} />
          <Stat label="Skills activos" value={brain.skills_active} />
          <Stat label="Skills archivados" value={brain.skills_archived} />
        </div>
        <p className="mt-3 text-sm text-gray-500">Próxima consolidación: {fmt(brain.next_consolidation)}</p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Procesos automáticos</h2>
        <ul className="space-y-2">
          {(s.scheduler_jobs || []).map((j, i) => (
            <li key={i} className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3 text-sm">
              <span>{j.label}</span>
              <span className="text-gray-400">Próxima actualización: {fmt(j.next_run)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-400">Costo del mes</h2>
        <p className="text-lg">USD {Number(s.cost_month_usd || 0).toFixed(2)} aproximado este mes</p>
      </section>
    </div>
  );
}

function Stat({ label, value, suffix = "" }: { label: string; value?: number; suffix?: string }) {
  return (
    <div className="rounded-lg border border-gray-100 p-4">
      <div className="text-2xl font-semibold">{value ?? 0}{suffix}</div>
      <div className="mt-1 text-sm text-gray-500">{label}</div>
    </div>
  );
}
