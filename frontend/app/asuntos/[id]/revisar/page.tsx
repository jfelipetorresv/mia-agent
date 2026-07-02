"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiDownload, apiGet, apiSend } from "@/lib/api";

// Informe del verificador de citas (CP9). Llega en GET /api/matters/{id}/draft;
// es null en borradores de turnos anteriores.
type Verification = {
  citas?: number;
  marcadas?: number;
  respaldadas?: number;
  anotadas?: number;
  detalle?: { cita: string; estado: string }[];
};

type DraftResponse = { draft: string; verification?: Verification | null };

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

// Estado de cada cita en lenguaje llano (los valores vienen del servidor).
const ESTADO_CITA: Record<string, { label: string; className: string }> = {
  marcada: { label: "Verifícala tú", className: "bg-yellow-100 text-yellow-800" },
  respaldada: { label: "Con respaldo", className: "bg-green-100 text-green-800" },
  anotada: { label: "Anotada", className: "bg-gray-100 text-gray-600" },
};

function VerificationReport({ v }: { v: Verification }) {
  const [open, setOpen] = useState(false);
  const citas = v.citas ?? 0;
  // El abogado debe verificar TODA cita con la marca [VERIFICAR] en el borrador
  // final: las que el redactor ya marcó (marcadas) MÁS las que el verificador
  // añadió por no tener respaldo (anotadas). Contar solo `marcadas` subreporta el
  // riesgo que este informe existe para evitar (CP9).
  const porVerificar = (v.marcadas ?? 0) + (v.anotadas ?? 0);
  const detalle = v.detalle || [];

  const resumen =
    citas === 0
      ? "Mia no encontró citas de normas o sentencias en este borrador."
      : porVerificar === 0
        ? `Mia revisó ${citas === 1 ? "1 cita" : `${citas} citas`}; todas quedaron con respaldo.`
        : `Mia revisó ${citas === 1 ? "1 cita" : `${citas} citas`}; ${
            porVerificar === 1 ? "1 quedó marcada" : `${porVerificar} quedaron marcadas`
          } para tu verificación.`;

  return (
    <section aria-label="Revisión de citas" className="mt-4 rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-700">{resumen}</p>
        {detalle.length > 0 ? (
          <button
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="text-sm font-medium text-gray-500 underline-offset-2 hover:text-gray-800 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400"
          >
            {open ? "Ocultar detalle" : "Ver cita por cita"}
          </button>
        ) : null}
      </div>
      {open && detalle.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {detalle.map((d, i) => {
            const estado = ESTADO_CITA[d.estado] || { label: d.estado, className: "bg-gray-100 text-gray-600" };
            return (
              <li key={i} className="flex items-start justify-between gap-3 rounded-md bg-white px-3 py-2">
                <span className="min-w-0 break-words text-sm text-gray-800">{d.cita}</span>
                <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${estado.className}`}>
                  {estado.label}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

export default function RevisarPage({ params }: { params: { id: string } }) {
  const matterId = params.id;
  const router = useRouter();
  const [draft, setDraft] = useState<string | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState("");

  useEffect(() => {
    apiGet<DraftResponse>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        setDraft(d.draft);
        setText(d.draft);
        setVerification(d.verification || null);
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

  async function downloadWord() {
    setDownloadMsg("");
    setDownloading(true);
    try {
      await apiDownload(`/api/matters/${matterId}/draft.docx`, "borrador.docx");
    } catch {
      setDownloadMsg("No se pudo descargar el documento. Intenta de nuevo.");
    } finally {
      setDownloading(false);
    }
  }

  if (draft === null) {
    return <div className="p-10 text-gray-400">Cargando borrador…</div>;
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-end justify-between gap-3 border-b border-gray-100 px-8 py-4">
        <div>
          <button onClick={() => router.push(`/asuntos/${matterId}`)} className="text-xs text-gray-400 hover:text-gray-600">
            ← Volver al asunto
          </button>
          <h1 className="mt-1 text-xl font-semibold">Revisar borrador</h1>
        </div>
        <div className="text-right">
          <button
            onClick={downloadWord}
            disabled={downloading}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {downloading ? "Preparando…" : "Descargar en Word"}
          </button>
          {downloadMsg ? (
            <p role="alert" className="mt-1 text-xs text-amber-700">{downloadMsg}</p>
          ) : null}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-8 py-8">
        <div className="mx-auto max-w-3xl">
          {editing ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-label="Texto del borrador"
              className="h-[60vh] w-full rounded-lg border border-gray-200 p-5 text-[16px] leading-relaxed outline-none focus:border-gray-400"
            />
          ) : (
            <div className="whitespace-pre-wrap rounded-lg border border-gray-100 bg-white p-6 text-[16px] leading-relaxed">
              {renderDraft(text)}
            </div>
          )}
          {verification ? <VerificationReport v={verification} /> : null}
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
