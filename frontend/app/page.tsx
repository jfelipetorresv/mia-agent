"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/api";

type Matter = {
  id: string;
  name: string;
  description?: string;
  status?: string;
  created_at?: string;
  pending_review?: boolean;
};

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

export default function AsuntosPage() {
  const router = useRouter();
  const [matters, setMatters] = useState<Matter[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      setMatters(await apiGet<Matter[]>("/api/matters"));
    } catch {
      setMatters([]);
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!name.trim()) {
      setError("Ponle un nombre al asunto.");
      return;
    }
    try {
      const m = await apiSend<Matter>("POST", "/api/matters", {
        name: name.trim(),
        description: description.trim(),
      });
      setShowModal(false);
      setName("");
      setDescription("");
      setError("");
      router.push(`/asuntos/${m.id}`);
    } catch {
      setError("No se pudo crear el asunto.");
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Asuntos</h1>
        <button
          onClick={() => setShowModal(true)}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          Nuevo asunto
        </button>
      </div>

      {loading ? (
        <p className="text-gray-400">Cargando…</p>
      ) : matters.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 py-16 text-center text-gray-400">
          Aún no tienes asuntos activos.
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-100">
          {matters.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => router.push(`/asuntos/${m.id}`)}
                className="flex w-full items-center gap-3 px-5 py-4 text-left transition hover:-translate-y-px hover:bg-gray-50"
              >
                {m.pending_review ? (
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-orange-500" title="Borrador esperando tu revisión" />
                ) : (
                  <span className="h-2.5 w-2.5 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{m.name}</div>
                  {m.description ? <div className="truncate text-sm text-gray-500">{m.description}</div> : null}
                </div>
                <div className="shrink-0 text-xs text-gray-400">{fmtDate(m.created_at)}</div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {showModal ? (
        <div
          className="fixed inset-0 z-10 flex items-center justify-center bg-black/30 p-4"
          onClick={() => setShowModal(false)}
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-semibold">Nuevo asunto</h2>
            <label className="mb-1 block text-sm font-medium text-gray-700">Nombre</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mb-4 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
              placeholder="Ej. Demanda de responsabilidad civil"
              autoFocus
            />
            <label className="mb-1 block text-sm font-medium text-gray-700">Descripción (opcional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mb-2 h-20 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
            />
            {error ? <p className="mb-2 text-sm text-red-600">{error}</p> : null}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => setShowModal(false)} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancelar
              </button>
              <button onClick={create} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">
                Crear
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
