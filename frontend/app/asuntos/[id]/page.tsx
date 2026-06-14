"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend, apiUpload, streamTurn } from "@/lib/api";

type Doc = { id: string; name: string; type?: string; created_at?: string };
type Msg = { role: "user" | "mia"; text: string };

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

export default function WorkspacePage({ params }: { params: { id: string } }) {
  const matterId = params.id;
  const router = useRouter();
  const [matter, setMatter] = useState<{ name?: string } | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [hasDraft, setHasDraft] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function loadDocs() {
    try {
      setDocs(await apiGet<Doc[]>(`/api/matters/${matterId}/documents`));
    } catch {
      /* sin documentos */
    }
  }

  useEffect(() => {
    apiGet<{ name?: string }>(`/api/matters/${matterId}`).then(setMatter).catch(() => {});
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await apiUpload(`/api/matters/${matterId}/documents`, file);
      await loadDocs();
    } catch {
      /* ignore */
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function send() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "mia", text: "" }]);
    setStatus("Mia está analizando…");
    setHasDraft(false);
    try {
      const { stream_url } = await apiSend<{ stream_url: string }>(
        "POST",
        `/api/matters/${matterId}/chat`,
        { message: text },
      );
      await streamTurn(stream_url, (event, data) => {
        if (event === "thinking") setStatus(data.message || "Mia está analizando…");
        else if (event === "draft_ready") setStatus("Mia está redactando…");
        else if (event === "awaiting_review") {
          setStatus("Tienes un borrador listo");
          setHasDraft(true);
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              role: "mia",
              text: data.draft || "He preparado un borrador para tu revisión.",
            };
            return copy;
          });
        }
      });
    } catch {
      setStatus("No se pudo completar la consulta.");
    }
  }

  return (
    <div className="flex h-screen">
      {/* Columna izquierda: documentos */}
      <div className="flex w-[280px] shrink-0 flex-col border-r border-gray-100">
        <div className="border-b border-gray-100 px-5 py-4">
          <button onClick={() => router.push("/")} className="mb-2 text-xs text-gray-400 hover:text-gray-600">
            ← Asuntos
          </button>
          <div className="font-semibold leading-tight">{matter?.name || "Asunto"}</div>
        </div>
        <div className="flex-1 overflow-auto px-3 py-3">
          {docs.length === 0 ? (
            <p className="px-2 py-4 text-sm text-gray-400">Sin documentos todavía.</p>
          ) : (
            <ul className="space-y-1">
              {docs.map((d) => (
                <li key={d.id} className="rounded-lg px-2 py-2 text-sm hover:bg-gray-50">
                  <div className="truncate font-medium">{d.name}</div>
                  <div className="text-xs text-gray-400">{fmtDate(d.created_at)}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t border-gray-100 p-3">
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt,.md" onChange={onUpload} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            {uploading ? "Subiendo…" : "Agregar documento"}
          </button>
        </div>
      </div>

      {/* Columna central: chat */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-auto px-6 py-6">
          {messages.length === 0 ? (
            <p className="mt-20 text-center text-gray-300">Hazle una pregunta a Mia sobre este asunto.</p>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "mia" ? (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-900 text-xs font-semibold text-white">
                    M
                  </div>
                ) : null}
                <div
                  className={`max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                    m.role === "user" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-900"
                  }`}
                >
                  {m.text || <span className="text-gray-400">…</span>}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="border-t border-gray-100 px-6 py-3">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-500">{status}</span>
            {hasDraft ? (
              <button
                onClick={() => router.push(`/asuntos/${matterId}/revisar`)}
                className="rounded-lg bg-orange-500 px-3 py-1 text-xs font-medium text-white hover:bg-orange-600"
              >
                Revisar
              </button>
            ) : null}
          </div>
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              placeholder="Escribe tu consulta…"
              className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-2 text-sm outline-none focus:border-gray-400"
            />
            <button onClick={send} className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700">
              Enviar
            </button>
          </div>
        </div>
      </div>

      {/* Columna derecha: diagnóstico */}
      <div className="w-[280px] shrink-0 border-l border-gray-100 px-5 py-6">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">Diagnóstico</h3>
        <div className="space-y-4 text-sm">
          <DiagField label="Problema jurídico" />
          <DiagField label="Normas aplicables" />
          <DiagField label="Riesgo estimado" />
        </div>
        <p className="mt-6 text-xs text-gray-400">
          El diagnóstico se completará a medida que Mia analice el asunto.
        </p>
      </div>
    </div>
  );
}

function DiagField({ label }: { label: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-gray-300">—</div>
    </div>
  );
}
