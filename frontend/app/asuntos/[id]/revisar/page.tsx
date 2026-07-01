"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/api";

// Resalta los marcadores [VERIFICAR…] en amarillo con tooltip.
function renderDraft(text: string) {
  const parts = text.split(/(\[VERIFICAR[^\]]*\])/g);
  return parts.map((p, i) =>
    p.startsWith("[VERIFICAR") ? (
      <mark key={i} title="Verificar antes de presentar" className="rounded bg-yellow-200 px-1">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

export default function RevisarPage({ params }: { params: { id: string } }) {
  const matterId = params.id;
  const router = useRouter();
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiGet<{ draft: string }>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        setDraft(d.draft);
        setText(d.draft);
      })
      .catch(() => {
        router.push(`/asuntos/${matterId}?sin_borrador=true`);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  async function approve() {
    setBusy(true);
    try {
      await apiSend("POST", `/api/matters/${matterId}/draft/approve`, editing ? { edited_text: text } : {});
      router.push(`/asuntos/${matterId}?confirmed=true`);
    } catch {
      setBusy(false);
      alert("No se pudo confirmar el borrador. Intenta de nuevo.");
    }
  }

  async function reject() {
    setBusy(true);
    try {
      await apiSend("POST", `/api/matters/${matterId}/draft/reject`, { reason: "" });
      router.push(`/asuntos/${matterId}?confirmed=true`);
    } catch {
      setBusy(false);
      alert("No se pudo rechazar el borrador. Intenta de nuevo.");
    }
  }

  if (draft === null) {
    return <div className="p-10 text-gray-400">Cargando borrador…</div>;
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="border-b border-gray-100 px-8 py-4">
        <button onClick={() => router.push(`/asuntos/${matterId}`)} className="text-xs text-gray-400 hover:text-gray-600">
          ← Volver al asunto
        </button>
        <h1 className="mt-1 text-xl font-semibold">Revisar borrador</h1>
      </div>

      <div className="flex-1 overflow-auto px-8 py-8">
        <div className="mx-auto max-w-3xl">
          {editing ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="h-[60vh] w-full rounded-lg border border-gray-200 p-5 text-[16px] leading-relaxed outline-none focus:border-gray-400"
            />
          ) : (
            <div className="whitespace-pre-wrap rounded-lg border border-gray-100 bg-white p-6 text-[16px] leading-relaxed">
              {renderDraft(text)}
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-center gap-3 border-t border-gray-100 px-8 py-4">
        <button
          onClick={approve}
          disabled={busy}
          className="rounded-lg bg-green-600 px-6 py-2.5 font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          Aprobar
        </button>
        <button
          onClick={() => setEditing((v) => !v)}
          className="rounded-lg bg-blue-600 px-6 py-2.5 font-medium text-white hover:bg-blue-700"
        >
          {editing ? "Listo" : "Editar"}
        </button>
        <button
          onClick={reject}
          disabled={busy}
          className="rounded-lg bg-red-600 px-6 py-2.5 font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
    </div>
  );
}
