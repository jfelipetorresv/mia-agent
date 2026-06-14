"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type Stats = {
  matters_active?: number;
  documents_indexed?: number;
  knowledge_items?: number;
  proposals_pending?: number;
  cost_month_usd?: number;
  scheduler_jobs?: { label: string; next_run?: string | null; last_run?: string | null }[];
  connectors?: {
    knowledge_base?: { active?: boolean; last_sync?: string | null };
    external_store?: { active?: boolean };
    models?: string[];
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

  useEffect(() => {
    apiGet<Stats>("/api/dashboard/stats").then(setS).catch(() => {});
  }, []);

  if (!s) return <div className="p-10 text-gray-400">Cargando…</div>;
  const c = s.connectors || {};

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
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Modelos disponibles</h2>
        <div className="flex flex-wrap gap-2">
          {(c.models || []).map((m, i) => (
            <span key={i} className="rounded-full bg-gray-100 px-3 py-1 text-sm">{m}</span>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-400">Costo del mes</h2>
        <p className="text-lg">USD {Number(s.cost_month_usd || 0).toFixed(2)} aproximado este mes</p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Conectores</h2>
        <ul className="space-y-2 text-sm">
          <li className="rounded-lg border border-gray-100 px-4 py-3">
            Base de conocimiento:{" "}
            {c.knowledge_base?.active ? `Activo · última sincronización ${fmt(c.knowledge_base?.last_sync)}` : "Inactivo"}
          </li>
          <li className="rounded-lg border border-gray-100 px-4 py-3">
            Almacén externo: {c.external_store?.active ? "Activo" : "No configurado"}
          </li>
        </ul>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-xl border border-gray-100 p-4">
      <div className="text-2xl font-semibold">{value ?? 0}</div>
      <div className="mt-1 text-sm text-gray-500">{label}</div>
    </div>
  );
}
