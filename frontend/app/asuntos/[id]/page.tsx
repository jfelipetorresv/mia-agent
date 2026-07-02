"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend, apiUpload, streamTurn } from "@/lib/api";

type Doc = { id: string; name: string; type?: string; created_at?: string };
type Msg = { role: "user" | "mia"; text: string };
type UploadItem = { name: string; status: "waiting" | "uploading" | "done" | "error" };

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
  const [diagnosis, setDiagnosis] = useState("");
  // CP7: cierre estructurado del diagnostico (problema/normas/riesgo) cuando el
  // backend lo emite (CP6); si no viene, el panel muestra solo la prosa como antes.
  const [summary, setSummary] = useState<DiagnosisSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [uploadSummary, setUploadSummary] = useState("");
  const [streaming, setStreaming] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

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
    // Si el asunto ya tiene un borrador en curso, recupera tambien su diagnostico.
    apiGet<{ diagnosis?: string; awaiting_review?: boolean; diagnosis_summary?: DiagnosisSummary | null }>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        if (d.diagnosis) setDiagnosis(d.diagnosis);
        if (d.diagnosis_summary) setSummary(d.diagnosis_summary);
        if (d.awaiting_review) setHasDraft(true);
      })
      .catch(() => {
        /* sin borrador todavia */
      });
    return () => {
      streamAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  async function uploadFiles(files: File[]) {
    if (files.length === 0) return;
    setUploading(true);
    setUploadSummary("");
    setUploadItems(files.map((file) => ({ name: file.name, status: "waiting" })));
    let added = 0;
    for (let i = 0; i < files.length; i += 1) {
      const file = files[i];
      setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "uploading" } : item)));
      try {
        await apiUpload(`/api/matters/${matterId}/documents`, file);
        added += 1;
        setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "done" } : item)));
      } catch {
        setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "error" } : item)));
      }
    }
    await loadDocs();
    setUploadSummary(`${added} documentos agregados`);
    setUploading(false);
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    await uploadFiles(Array.from(e.target.files ?? []));
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onFolderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []).filter((file) => /\.(pdf|doc|docx)$/i.test(file.name));
    await uploadFiles(files);
    if (folderRef.current) folderRef.current.value = "";
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "mia", text: "" }]);
    setStatus("Mia esta analizando...");
    setHasDraft(false);
    setStreaming(true);
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    try {
      const { stream_url } = await apiSend<{ stream_url: string }>(
        "POST",
        `/api/matters/${matterId}/chat`,
        { message: text },
      );
      await streamTurn(
        stream_url,
        (event, data) => {
          const payload = data as { message?: string; draft?: string; diagnosis?: string; diagnosis_summary?: DiagnosisSummary | null };
          if (event === "thinking") setStatus(payload.message || "Mia esta analizando...");
          else if (event === "draft_ready") setStatus("Mia esta redactando...");
          else if (event === "error") setStatus(payload.message || "No se pudo completar la consulta.");
          else if (event === "awaiting_review") {
            setStatus("Tienes un borrador listo");
            setHasDraft(true);
            if (payload.diagnosis) setDiagnosis(payload.diagnosis);
            if (payload.diagnosis_summary) setSummary(payload.diagnosis_summary);
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = {
                role: "mia",
                text: payload.draft || "He preparado un borrador para tu revision.",
              };
              return copy;
            });
          }
        },
        controller.signal,
      );
    } catch {
      setStatus("No se pudo completar la consulta.");
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex h-screen">
      <div className="flex w-[280px] shrink-0 flex-col border-r border-gray-100">
        <div className="border-b border-gray-100 px-5 py-4">
          <button onClick={() => router.push("/")} className="mb-2 text-xs text-gray-400 hover:text-gray-600">
            Asuntos
          </button>
          <div className="font-semibold leading-tight">{matter?.name || "Asunto"}</div>
        </div>
        <div className="flex-1 overflow-auto px-3 py-3">
          {docs.length === 0 ? (
            <p className="px-2 py-4 text-sm text-gray-400">Sin documentos todavia.</p>
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
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt,.md" multiple onChange={onUpload} className="hidden" />
          <input
            ref={folderRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx"
            onChange={onFolderUpload}
            className="hidden"
            {...({ webkitdirectory: "true", directory: "true" } as any)}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            {uploading ? "Subiendo..." : "Agregar documento"}
          </button>
          <button
            onClick={() => folderRef.current?.click()}
            disabled={uploading}
            className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            Conectar carpeta
          </button>
          {uploadItems.length > 0 ? (
            <div className="mt-3 space-y-2">
              {uploadItems.map((item) => (
                <div key={item.name} className="text-xs text-gray-500">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">{item.name}</span>
                    <span className="shrink-0">
                      {item.status === "waiting"
                        ? "En cola"
                        : item.status === "uploading"
                          ? "Procesando"
                          : item.status === "done"
                            ? "Listo"
                            : "Error"}
                    </span>
                  </div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className={`h-full rounded-full ${
                        item.status === "error" ? "bg-red-500" : item.status === "done" ? "bg-gray-900" : "bg-gray-400"
                      }`}
                      style={{ width: item.status === "waiting" ? "15%" : item.status === "uploading" ? "55%" : "100%" }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {uploadSummary ? <div className="mt-3 text-xs font-medium text-gray-600">{uploadSummary}</div> : null}
        </div>
      </div>

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
                  className={`max-w-[75%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
                    m.role === "user" ? "bg-gray-900 text-white" : "bg-[#f8f9fa] text-gray-900"
                  }`}
                >
                  {m.text || <span className="text-gray-400">...</span>}
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
              placeholder="Escribe tu consulta..."
              className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-2 text-sm outline-none focus:border-gray-400"
            />
            <button
              onClick={send}
              disabled={streaming}
              className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              Enviar
            </button>
          </div>
        </div>
      </div>

      <div className="flex w-[280px] shrink-0 flex-col border-l border-gray-100 px-5 py-6">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">Diagnóstico</h3>
        {diagnosis ? (
          <div className="min-h-0 flex-1 overflow-auto">
            {summary ? (
              <div className="mb-3 space-y-2">
                <SummaryRow label="Problema jurídico" text={summary.problema} />
                <SummaryRow label="Normas y fuentes" text={summary.normas} />
                <SummaryRow label="Riesgo y recomendación" text={summary.riesgo} />
              </div>
            ) : null}
            <div className="whitespace-pre-wrap rounded-lg bg-[#f8f9fa] px-3 py-3 text-sm text-gray-700">
              {diagnosis}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">Mia aún no ha analizado este asunto.</p>
        )}
      </div>
    </div>
  );
}

type DiagnosisSummary = { problema?: string; normas?: string; riesgo?: string };

function SummaryRow({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <div className="rounded-lg border border-gray-100 px-3 py-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</div>
      <div className="text-sm text-gray-700">{text}</div>
    </div>
  );
}
