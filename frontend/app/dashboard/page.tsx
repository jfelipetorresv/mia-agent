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

type MotorPolicy = { politica: string; nombre: string; opciones: { id: string; nombre: string }[] };
type Reminder = { id: string; text: string; due_at: string; is_procedural: boolean };

function fmt(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

// Para los recordatorios la HORA importa ("mañana a las 9" no es "mañana").
function fmtHora(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("es-CO", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
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
  // CP7 (CP2 · decisión #27): motor de IA por política del despacho, sin nombres
  // de modelos (§G) — "Mi suscripción / Nube / Todo en mi equipo".
  const [policy, setPolicy] = useState<MotorPolicy | null>(null);
  const [policyMsg, setPolicyMsg] = useState("");
  // CP-B3: recordatorios pendientes del despacho.
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [reminderMsg, setReminderMsg] = useState("");

  async function load() {
    const data = await apiGet<Stats>("/api/dashboard/stats");
    setS(data);
    apiGet<MotorPolicy>("/settings/model-policy")
      .then(setPolicy)
      .catch(() => setPolicyMsg("No se pudo cargar el motor de IA. Recarga la página."));
    apiGet<Reminder[]>("/api/assistant/reminders").then(setReminders).catch(() => setReminders([]));
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  async function changePolicy(id: string) {
    setPolicyMsg("");
    try {
      const res = await apiSend<MotorPolicy>("PUT", "/settings/model-policy", { politica: id });
      setPolicy(res);
      setPolicyMsg(`Listo: Mia trabajará con "${res.nombre}".`);
    } catch {
      setPolicyMsg("No se pudo cambiar el motor. Intenta de nuevo.");
    }
  }

  async function cancelReminder(id: string) {
    // Solo se quita de la lista si el servidor CONFIRMÓ la cancelación — un
    // recordatorio ligado a un plazo jamás debe "desaparecer" sin cancelarse.
    setReminderMsg("");
    try {
      await apiSend("POST", `/api/assistant/reminders/${id}/cancel`);
      setReminders((rs) => rs.filter((r) => r.id !== id));
    } catch {
      setReminderMsg("No se pudo cancelar el recordatorio. Intenta de nuevo.");
    }
  }

  async function syncObsidian() {
    setStatus("Sincronizando...");
    try {
      const res = await apiSend<{ chunks_indexed: number }>("POST", "/api/connectors/obsidian/sync", {
        vault_path: vaultPath || null,
      });
      setStatus(`${res.chunks_indexed} documentos sincronizados`);
      await load();
    } catch {
      setStatus("No se pudo sincronizar el vault.");
    }
  }

  async function connectPinecone() {
    setStatus("Conectando...");
    try {
      const res = await apiSend<{ status: string; vectors_count: number }>("POST", "/api/connectors/pinecone/configure", {
        api_key: pineconeKey,
        index_name: pineconeIndex,
      });
      setStatus(res.status === "active" ? `${res.vectors_count} vectores disponibles` : "No se pudo activar");
      await load();
    } catch {
      setStatus("No se pudo conectar con Pinecone.");
    }
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
              <input type="password" autoComplete="off" value={pineconeKey} onChange={(e) => setPineconeKey(e.target.value)} placeholder="Clave de acceso" className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
              <input value={pineconeIndex} onChange={(e) => setPineconeIndex(e.target.value)} placeholder="Index" className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400" />
            </div>
          </div>

          <div className="rounded-lg border border-gray-100 p-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Motor de IA</label>
            <p className="mb-2 text-sm text-gray-500">Con qué trabaja Mia. Puedes cambiarlo cuando quieras.</p>
            <select
              value={policy?.politica || ""}
              onChange={(e) => changePolicy(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
            >
              {(policy?.opciones || []).map((o) => (
                <option key={o.id} value={o.id}>{o.nombre}</option>
              ))}
            </select>
            {policyMsg ? <p className="mt-2 text-sm text-gray-600">{policyMsg}</p> : null}
          </div>
          {status ? <p className="text-sm text-gray-500">{status}</p> : null}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Recordatorios</h2>
        {reminderMsg ? <p className="mb-2 text-sm text-amber-700">{reminderMsg}</p> : null}
        {reminders.length === 0 ? (
          <p className="text-sm text-gray-400">No tienes recordatorios pendientes. Pídelos en el chat: «recuérdame radicar la tutela mañana a las 9».</p>
        ) : (
          <ul className="space-y-2">
            {reminders.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{r.text}</div>
                  <div className="text-sm text-gray-500">
                    Para el {fmtHora(r.due_at)}
                    {r.is_procedural ? " · plazo procesal: confirma tú la fecha" : ""}
                  </div>
                </div>
                <button onClick={() => cancelReminder(r.id)} className="shrink-0 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">Cancelar</button>
              </li>
            ))}
          </ul>
        )}
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
