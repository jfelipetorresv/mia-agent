"use client";

// CP-C4 · "Configura a Mia": el recorrido guiado para dejar a Mia completamente
// conectada sin saber nada técnico. El estado viene de GET /api/setup/status
// (solo lectura); cada paso enlaza a la pantalla donde se hace, o guía el paso
// humano (Telegram). Todo es opcional y retomable (skip/unskip).

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";

type Paso = {
  id: string;
  titulo: string;
  estado: "listo" | "pendiente" | "omitido";
  detalle: string;
  accion: "automatica" | "guiada";
  enlace?: string | null;
};

type Status = {
  pasos: Paso[];
  completados: number;
  total: number;
  siguiente: string | null;
  mensaje: string;
};

export default function ConfigurarPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [telegramOpen, setTelegramOpen] = useState(false);

  async function load() {
    try {
      setS(await apiGet<Status>("/api/setup/status"));
      setError("");
    } catch {
      setError("No se pudo cargar el estado de configuración. Recarga la página.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const [skipMsg, setSkipMsg] = useState("");

  async function toggleSkip(p: Paso) {
    setSkipMsg("");
    const action = p.estado === "omitido" ? "unskip" : "skip";
    try {
      await apiSend("POST", `/api/setup/steps/${p.id}/${action}`);
    } catch {
      setSkipMsg("No se pudo guardar el cambio. Intenta de nuevo.");
    }
    await load();
  }

  if (error) return <div className="p-10 text-sm text-amber-700">{error}</div>;
  if (!s) return <div className="p-10 text-gray-400">Cargando…</div>;

  const pct = Math.round((s.completados / Math.max(1, s.total)) * 100);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="mb-2 text-2xl font-semibold">Configura a Mia</h1>
      <p className="mb-6 text-sm text-gray-500">{s.mensaje}</p>

      <div className="mb-8">
        <div className="h-2 rounded-full bg-gray-100">
          <div className="h-2 rounded-full bg-gray-900 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1 text-right text-xs text-gray-400">{s.completados} de {s.total} pasos listos</div>
      </div>

      {skipMsg ? <p className="mb-3 text-sm text-amber-700">{skipMsg}</p> : null}
      <ul className="space-y-3">
        {s.pasos.map((p) => (
          <li key={p.id} className={`rounded-xl border px-4 py-3 ${p.estado === "listo" ? "border-gray-100 bg-gray-50" : "border-gray-200"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      p.estado === "listo" ? "bg-green-600 text-white" : p.estado === "omitido" ? "bg-gray-200 text-gray-500" : "bg-gray-900 text-white"
                    }`}
                  >
                    {p.estado === "listo" ? "✓" : p.estado === "omitido" ? "–" : "·"}
                  </span>
                  <span className="font-medium">{p.titulo}</span>
                  {p.estado === "omitido" ? <span className="text-xs text-gray-400">(para después)</span> : null}
                </div>
                <p className="mt-1 text-sm text-gray-500">{p.detalle}</p>
                {p.id === "telegram" && telegramOpen ? (
                  <div className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600">
                    <p className="mb-1 font-medium">Cómo activar Mia en tu celular (5 minutos):</p>
                    <ol className="list-inside list-decimal space-y-0.5">
                      <li>En Telegram, busca <span className="font-medium">@BotFather</span> y envíale /newbot.</li>
                      <li>Ponle nombre a tu bot y copia la clave que te entrega.</li>
                      <li>Pídeme la guía completa por el chat («Mia, ayúdame a activar Telegram») y te llevo paso a paso para guardar esa clave.</li>
                      <li>Ejecuta el acceso directo &quot;Iniciar Telegram&quot; y escríbele a tu bot.</li>
                    </ol>
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {p.estado !== "listo" && p.enlace ? (
                  <Link href={p.enlace} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">
                    Ir al paso
                  </Link>
                ) : null}
                {p.estado !== "listo" && p.id === "telegram" ? (
                  <button onClick={() => setTelegramOpen((v) => !v)} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">
                    {telegramOpen ? "Ocultar guía" : "Ver la guía"}
                  </button>
                ) : null}
                {p.estado !== "listo" ? (
                  <button onClick={() => toggleSkip(p)} className="rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100">
                    {p.estado === "omitido" ? "Retomar" : "Dejar para después"}
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <p className="mt-6 text-sm text-gray-400">
        También puedes pedirle ayuda a Mia por el chat: «ayúdame a conectar mi Google Drive».
      </p>
    </div>
  );
}
