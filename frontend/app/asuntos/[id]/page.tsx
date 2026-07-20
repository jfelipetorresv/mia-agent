"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Moon,
  Paperclip,
  Scale,
  Send,
  Sparkles,
  Sunrise,
  Swords,
  X,
} from "lucide-react";
import { apiGet, apiSend, apiUpload, streamPost, streamTurn } from "@/lib/api";
import { useDictation } from "@/lib/useDictation";
import MicButton from "../../_components/MicButton";
import MissionBoard from "../../_components/MissionBoard";
import CitationReview, { type Verification } from "../../_components/CitationReview";
import FuentesPanel from "../../_components/FuentesPanel";
import GuideInterviewWizard from "../../_components/GuideInterviewWizard";
import SalaEstrategiaDialog from "./_components/SalaEstrategiaDialog";
import SalaEstrategiaResult from "./_components/SalaEstrategiaResult";
import DiarioDialog from "./_components/DiarioDialog";
import CierreDialog, { type CierreResult } from "./_components/CierreDialog";
import DocumentosPorConfirmarDialog from "./_components/DocumentosPorConfirmarDialog";
import type { DebateTurn, Panelist, WarRoomResult } from "./_components/warroom-types";
import { Button } from "@/components/ui/button";
import MiaMarkdown from "@/components/MiaMarkdown";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type DelegationProposal = {
  agente?: string;
  nombre?: string;
  texto?: string;
  huella?: string;
  aviso?: string;
};

// GET /api/matters/{id}/warroom devuelve, según el contrato, el último
// WarRoomResult "plano" o `{ result: null }` cuando aún no hay uno — se
// tolera cualquiera de las dos formas (y cualquier respuesta inesperada del
// backend, todavía en construcción en paralelo) sin romper la pantalla.
function parseWarroomGet(res: unknown): WarRoomResult | null {
  if (!res || typeof res !== "object") return null;
  const r = res as Record<string, unknown>;
  if (r.conclusions && typeof r.conclusions === "object") return r as unknown as WarRoomResult;
  if (r.result && typeof r.result === "object") return r.result as WarRoomResult;
  return null;
}

type Doc = { id: string; name: string; type?: string; created_at?: string };
type Msg = { role: "user" | "mia"; text: string };
type UploadItem = { name: string; status: "waiting" | "uploading" | "done" | "error" };
type UploadResponse = { id?: string; name?: string; status?: string; message?: string; fragments?: number };

type MissionsSummary = { count: number; milestonesDone: number; milestonesTotal: number };

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

// useSearchParams() exige un límite <Suspense> en App Router (si no, rompe el
// prerender). El contenido real vive en WorkspacePageContent; este export solo
// monta el límite.
export default function WorkspacePage({ params }: { params: { id: string } }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-[100dvh] items-center justify-center text-sm text-muted-foreground">
          Cargando…
        </div>
      }
    >
      <WorkspacePageContent params={params} />
    </Suspense>
  );
}

function WorkspacePageContent({ params }: { params: { id: string } }) {
  const matterId = params.id;
  const router = useRouter();
  const searchParams = useSearchParams();
  const [matter, setMatter] = useState<{ name?: string } | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [hasDraft, setHasDraft] = useState(false);
  const [delegation, setDelegation] = useState<DelegationProposal | null>(null);
  const [delegationRemember, setDelegationRemember] = useState(false);
  const [delegationBusy, setDelegationBusy] = useState(false);
  // B3: "Convierte lo que hicimos aquí en una guía" — solo visible cuando el
  // desenlace real del borrador fue APROBADO. `awaiting_review=false` por sí solo NO
  // alcanza como señal: el grafo también llega a END (deja de estar pausado) cuando el
  // abogado RECHAZA o EDITA el borrador, así que se usa el desenlace explícito
  // (hitl_outcome) que expone GET /matters/{id}/draft, no un proxy.
  const [draftApproved, setDraftApproved] = useState(false);
  const [guideWizardOpen, setGuideWizardOpen] = useState(false);
  const [diagnosis, setDiagnosis] = useState("");
  // CP7: cierre estructurado del diagnostico (problema/normas/riesgo) cuando el
  // backend lo emite (CP6); si no viene, el panel muestra solo la prosa como antes.
  const [summary, setSummary] = useState<DiagnosisSummary | null>(null);
  // Fase 1(b): informe de verificación de citas del borrador (CP9), en línea en
  // este panel — null hasta que el backend lo entregue en el draft o el turno.
  const [verification, setVerification] = useState<Verification | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [uploadSummary, setUploadSummary] = useState("");
  const [streaming, setStreaming] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  // CP-Z1b: dictado por voz — el texto transcrito se agrega al campo sin borrar
  // lo ya escrito; los avisos ("no se escuchó voz") van en ámbar bajo el input.
  const [dictationNotice, setDictationNotice] = useState("");

  // Avisos en llano cuando se llega desde /revisar con una señal en la URL
  // (§G: nada de "sin_borrador=true" visible). Se leen una sola vez y se
  // limpia el query para que un refresco de la página no repita el aviso.
  const [notice, setNotice] = useState<{ type: "warning" | "success"; text: string } | null>(null);
  useEffect(() => {
    const sinBorrador = searchParams.get("sin_borrador") === "true";
    const confirmed = searchParams.get("confirmed") === "true";
    if (sinBorrador) {
      setNotice({
        type: "warning",
        text: "Ese borrador ya no está disponible para revisión. Puede que ya se haya resuelto o que se haya reemplazado por uno nuevo — pídele a Mia que lo retome si lo necesitas.",
      });
    } else if (confirmed) {
      setNotice({ type: "success", text: "El borrador quedó aprobado. Mia guardó tu decisión." });
    }
    if (sinBorrador || confirmed) {
      router.replace(`/asuntos/${matterId}`, { scroll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Fase 3.1(B) · Plan de trabajo (aside): contador liviano para el header de la card.
  const [missionsSummary, setMissionsSummary] = useState<MissionsSummary | null>(null);
  const [planOpen, setPlanOpen] = useState(false);

  // Sala de estrategia (nombre interno: warroom) — §G: sin jerga visible.
  const [warroomDialogOpen, setWarroomDialogOpen] = useState(false);
  const [warroomStarting, setWarroomStarting] = useState(false);
  const [warroomStreaming, setWarroomStreaming] = useState(false);
  const [warroomStatus, setWarroomStatus] = useState("");
  // Error en llano de la sala (asunto sin expediente, fallo antes del primer turno, etc.):
  // se muestra aunque no haya debate ni dictamen (MAYOR 2).
  const [warroomError, setWarroomError] = useState("");
  const [warroomDebate, setWarroomDebate] = useState<DebateTurn[]>([]);
  const [warroomResult, setWarroomResult] = useState<WarRoomResult | null>(null);
  const [convertingToDraft, setConvertingToDraft] = useState(false);

  // Pieza 4 · sesión de trabajo del expediente (botones, nunca comandos §G):
  // "Arrancar el día" (/daily) y "Cerrar por hoy" (/cierre). El cierre destila
  // lo que el abogado decidió en la conversación; por eso necesita el hilo
  // visible. Se dispara MANUAL (botón) y AUTOMÁTICO al llenarse el contexto (~65%,
  // gateado en el backend) para no perder contexto — decisión de Pipe.
  const [diarioOpen, setDiarioOpen] = useState(false);
  const [cierreOpen, setCierreOpen] = useState(false);
  const [cierreBusy, setCierreBusy] = useState(false);
  const [cierreResult, setCierreResult] = useState<CierreResult | null>(null);
  // "Documentos por confirmar": la DUDA del clasificador de ingesta. La lista vive en
  // su propio diálogo (no se reusa la revisión del borrador); aquí solo llevamos un
  // contador liviano para el acceso/indicador y para refrescarlo al confirmar.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  // Espejo siempre-fresco del hilo: send()/runChatStream capturan `messages` del
  // render y quedan obsoletos tras el streaming; el cierre lee este ref.
  const messagesRef = useRef<Msg[]>([]);
  // El cierre-auto dispara UNA vez al cruzar el umbral, para no re-destilar (coste
  // LLM) en cada turno posterior; el abogado siempre puede cerrar a mano después.
  const autoCierreDoneRef = useRef(false);

  const dictation = useDictation(
    (text) => {
      setDictationNotice("");
      setInput((prev) => (prev.trim() ? prev.trimEnd() + " " + text : text));
    },
    (notice) => setDictationNotice(notice),
  );

  // Mantén el espejo del hilo al día para que el cierre destile SIEMPRE la
  // conversación más reciente (los closures de send/runChatStream se congelan).
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  async function loadDocs() {
    try {
      setDocs(await apiGet<Doc[]>(`/api/matters/${matterId}/documents`));
    } catch {
      /* sin documentos */
    }
  }

  // Contador de "Documentos por confirmar": cuántos documentos del asunto tienen
  // un dato que Mia dejó como duda. Solo cuenta para el indicador — la lista real la
  // carga el diálogo cuando se abre. Fail-soft: si falla, se asume 0 (no molesta).
  async function loadPendingCount() {
    try {
      const res = await apiGet<{ documentos?: unknown[] }>(
        `/api/matters/${matterId}/documents/pending`,
      );
      setPendingCount((res.documentos || []).length);
    } catch {
      setPendingCount(0);
    }
  }

  useEffect(() => {
    apiGet<{ name?: string }>(`/api/matters/${matterId}`).then(setMatter).catch(() => {});
    loadDocs();
    loadPendingCount();
    // Contador liviano del plan de trabajo: decide si la card empieza expandida.
    apiGet<{ missions: Array<{ progress?: { done?: number; total?: number } }> }>(
      `/api/missions?matter_id=${encodeURIComponent(matterId)}`,
    )
      .then((res) => {
        const missions = res.missions || [];
        const summary: MissionsSummary = {
          count: missions.length,
          milestonesDone: missions.reduce((n, m) => n + (m.progress?.done || 0), 0),
          milestonesTotal: missions.reduce((n, m) => n + (m.progress?.total || 0), 0),
        };
        setMissionsSummary(summary);
        setPlanOpen(summary.count > 0);
      })
      .catch(() => setMissionsSummary(null));
    // Si el asunto ya tiene un borrador en curso, recupera tambien su diagnostico.
    apiGet<{
      draft?: string | null;
      diagnosis?: string;
      awaiting_review?: boolean;
      hitl_outcome?: "approved" | "rejected" | "edited" | null;
      diagnosis_summary?: DiagnosisSummary | null;
      verification?: Verification | null;
    }>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        if (d.diagnosis) setDiagnosis(d.diagnosis);
        if (d.diagnosis_summary) setSummary(d.diagnosis_summary);
        if (d.verification) setVerification(d.verification);
        if (d.awaiting_review) setHasDraft(true);
        setDraftApproved(Boolean(d.draft) && d.hitl_outcome === "approved");
      })
      .catch(() => {
        /* sin borrador todavia */
      });
    // Recupera el último resultado de la sala de estrategia, si lo hay, para
    // que sobreviva recargas de la página.
    apiGet<unknown>(`/api/matters/${matterId}/warroom`)
      .then((res) => {
        const result = parseWarroomGet(res);
        if (result) {
          setWarroomResult(result);
          setWarroomDebate(result.debate || []);
        }
      })
      .catch(() => {
        /* sin sala de estrategia todavia */
      });
    // Repinta el hilo de la conversacion tras un F5: los turnos viven guardados,
    // pero la pantalla no los pedia y se perdian al recargar.
    apiGet<{ mensajes?: Msg[] }>(`/api/matters/${matterId}/historial`)
      .then((h) => {
        if (h.mensajes && h.mensajes.length) setMessages(h.mensajes);
      })
      .catch(() => {
        /* hilo nuevo, sin turnos previos */
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
    let duplicated = 0;
    let duplicateNotice = "";
    for (let i = 0; i < files.length; i += 1) {
      const file = files[i];
      setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "uploading" } : item)));
      try {
        const res = await apiUpload<UploadResponse>(`/api/matters/${matterId}/documents`, file);
        if (res.status === "duplicado") {
          duplicated += 1;
          duplicateNotice = res.message || duplicateNotice;
        } else {
          added += 1;
        }
        setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "done" } : item)));
      } catch {
        setUploadItems((items) => items.map((item, idx) => (idx === i ? { ...item, status: "error" } : item)));
      }
    }
    await loadDocs();
    // Un documento recién subido puede quedar con dudas de ficha cuando termine su
    // clasificación (asíncrona); refrescamos el contador para que el indicador aparezca.
    void loadPendingCount();
    // El duplicado es informativo, no un error (§G): se anuncia en el mismo resumen.
    const parts: string[] = [];
    if (added > 0) parts.push(`${added} ${added === 1 ? "documento agregado" : "documentos agregados"}`);
    if (duplicated > 0) {
      parts.push(duplicated === 1 ? "1 ya estaba en el expediente" : `${duplicated} ya estaban en el expediente`);
    }
    setUploadSummary(parts.join(" · ") || duplicateNotice);
    setUploading(false);
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    await uploadFiles(Array.from(e.target.files ?? []));
    if (fileRef.current) fileRef.current.value = "";
  }

  // Maneja los eventos del turno normal del asunto (chat y, tras "Convertir en
  // borrador" desde la sala de estrategia, el mismo flujo de redacción con
  // gate de citas). Extraído de `send()` para reusarlo en ambos casos.
  function handleChatEvent(event: string, data: unknown) {
    const payload = data as {
      message?: string;
      draft?: string;
      diagnosis?: string;
      diagnosis_summary?: DiagnosisSummary | null;
      verification?: Verification | null;
      propuesta?: DelegationProposal;
    };
    if (event === "thinking") setStatus(payload.message || "Mia está analizando...");
    else if (event === "draft_ready") setStatus("Mia está redactando...");
    else if (event === "error") setStatus(payload.message || "No se pudo completar la consulta.");
    else if (event === "awaiting_delegation") {
      setStatus(payload.message || "Mia propone pedirle ayuda a un asistente externo.");
      setDelegation(payload.propuesta || {});
      setDelegationRemember(false);
      setMessages((m) => {
        const copy = [...m];
        const nombre = payload.propuesta?.nombre || "un asistente externo";
        copy[copy.length - 1] = {
          role: "mia",
          text:
            payload.message ||
            `Mia propone pedirle ayuda a ${nombre}. Revisa el texto antes de autorizar.`,
        };
        return copy;
      });
    } else if (event === "awaiting_review") {
      setDelegation(null);
      setStatus("Tienes un borrador listo");
      setHasDraft(true);
      if (payload.diagnosis) setDiagnosis(payload.diagnosis);
      if (payload.diagnosis_summary) setSummary(payload.diagnosis_summary);
      if (payload.verification) setVerification(payload.verification);
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          role: "mia",
          text: payload.draft || "He preparado un borrador para tu revisión.",
        };
        return copy;
      });
    }
  }

  async function runChatStream(stream_url: string, message: string) {
    setStreaming(true);
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    try {
      await streamPost(stream_url, { message }, handleChatEvent, controller.signal);
    } catch {
      setStatus("No se pudo completar la consulta.");
    } finally {
      setStreaming(false);
      // Cierre-auto tras el turno: diferido para que el último mensaje ya esté en
      // el ref (setMessages del streaming se aplica en el próximo render). El
      // backend gatea por llenado (~65%); si no aplica, es una llamada barata.
      setTimeout(() => {
        void maybeAutoCierre();
      }, 0);
    }
  }

  async function respondDelegation(aprobar: boolean) {
    if (!delegation || delegationBusy || streaming) return;
    if (aprobar && !delegation.huella) {
      setStatus("No se pudo confirmar la propuesta. Intenta de nuevo.");
      return;
    }
    setDelegationBusy(true);
    setStreaming(true);
    setStatus(aprobar ? "Mia está retomando el trabajo…" : "Mia continúa sin el ayudante…");
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    try {
      const path = aprobar
        ? `/api/matters/${matterId}/delegation/aprobar`
        : `/api/matters/${matterId}/delegation/descartar`;
      const body = aprobar
        ? { huella: delegation.huella, recordar: delegationRemember }
        : {};
      setDelegation(null);
      await streamPost(path, body, handleChatEvent, controller.signal);
    } catch {
      setStatus("No se pudo responder a la propuesta. Intenta de nuevo.");
    } finally {
      setDelegationBusy(false);
      setStreaming(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming || delegation) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "mia", text: "" }]);
    setStatus("Mia está analizando...");
    setHasDraft(false);
    try {
      const { stream_url } = await apiSend<{ stream_url: string }>(
        "POST",
        `/api/matters/${matterId}/chat`,
        { message: text },
      );
      await runChatStream(stream_url, text);
    } catch {
      setStatus("No se pudo completar la consulta.");
    }
  }

  // Sala de estrategia: arranca la sesión con el panel ajustado por el
  // abogado en el modal. El debate se va poblando en vivo (counsel_turn) y el
  // dictamen se fija al final (conclusions_ready).
  async function startWarroom(panel: Panelist[], question: string) {
    setWarroomStarting(true);
    try {
      const { stream_url } = await apiSend<{ stream_url: string }>(
        "POST",
        `/api/matters/${matterId}/warroom`,
        { panel, question: question || undefined },
      );
      setWarroomDialogOpen(false);
      setWarroomDebate([]);
      setWarroomResult(null);
      setWarroomError("");
      setWarroomStatus("Mia está reuniendo la sala de estrategia...");
      setWarroomStreaming(true);
      await streamTurn(stream_url, (event, data) => {
        const payload = data as {
          message?: string;
          round?: number;
          persona_id?: string | null;
          name?: string;
          stance_label?: string;
          text?: string;
          result?: WarRoomResult;
        };
        if (event === "thinking") {
          setWarroomStatus(payload.message || "Mia está trabajando...");
        } else if (event === "counsel_turn") {
          setWarroomDebate((d) => [
            ...d,
            {
              round: payload.round ?? 1,
              persona_id: payload.persona_id ?? null,
              name: payload.name || "",
              stance_label: payload.stance_label || "",
              text: payload.text || "",
            },
          ]);
        } else if (event === "conclusions_ready") {
          if (payload.result) setWarroomResult(payload.result);
          setWarroomStatus("");
        } else if (event === "error") {
          const msg = payload.message || "No se pudo completar la sala de estrategia.";
          setWarroomStatus(msg);
          setWarroomError(msg);
        }
      });
    } catch {
      const msg = "No se pudo convocar la sala de estrategia. Intenta de nuevo.";
      setWarroomStatus(msg);
      setWarroomError(msg);
    } finally {
      setWarroomStarting(false);
      setWarroomStreaming(false);
    }
  }

  // "Convertir en borrador": toma el dictamen de la sala de estrategia y
  // arranca el flujo de redacción normal — el borrador resultante pasa por el
  // mismo gate de citas que cualquier otro (revisar/page.tsx).
  async function convertWarroomToDraft() {
    if (convertingToDraft || streaming || delegation) return;
    setConvertingToDraft(true);
    setStatus("Mia está preparando tu borrador...");
    setHasDraft(false);
    setMessages((m) => [...m, { role: "mia", text: "" }]);
    try {
      const { stream_url, message } = await apiSend<{ stream_url: string; message: string }>(
        "POST",
        `/api/matters/${matterId}/warroom/to-draft`,
      );
      await runChatStream(stream_url, message);
    } catch {
      setStatus("No se pudo preparar el borrador. Intenta de nuevo.");
    } finally {
      setConvertingToDraft(false);
    }
  }

  // Hilo visible en el formato que espera /cierre ({role, content}); el backend
  // destila SOLO los mensajes del abogado (role "user"). Se leen del ref para
  // tomar la conversación más reciente, no la del render que abrió el closure.
  function cierrePayload(): Array<{ role: string; content: string }> {
    return messagesRef.current
      .filter((m) => m.text.trim())
      .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
  }

  // "Cerrar por hoy" (manual): destila lo que el abogado decidió y lo guarda en el
  // expediente. Muestra en un diálogo qué se guardó (o por qué no había nada).
  async function runCierre() {
    if (cierreBusy || streaming) return;
    setCierreResult(null);
    setCierreOpen(true);
    setCierreBusy(true);
    try {
      const res = await apiSend<CierreResult>("POST", `/api/matters/${matterId}/cierre`, {
        messages: cierrePayload(),
      });
      setCierreResult(res);
      // Un cierre a mano que sí guardó cuenta como cierre de la sesión: no lo
      // repitas automáticamente después.
      if (res.written) autoCierreDoneRef.current = true;
    } catch {
      setCierreResult({
        written: false,
        reason: "fallo_escritura",
        durables: [],
        pendientes: [],
      });
    } finally {
      setCierreBusy(false);
    }
  }

  // Cierre AUTOMÁTICO: se llama tras cada turno; el backend decide si la ventana
  // llegó a ~65% (gate) y solo entonces destila. Silencioso salvo cuando guarda
  // algo — ahí avisa en llano y no vuelve a dispararse (una vez por sesión).
  // TODO(pieza-4e): el gate del backend mide contra MIA_CONTEXT_WINDOW; el
  // frontend no conoce la ventana efectiva del modelo, así que no envía
  // `context_window` (usa el default del backend). Si en el futuro se quiere que
  // el umbral refleje el presupuesto real de la conversación, pasar aquí un
  // context_window medido — no inventar uno.
  async function maybeAutoCierre() {
    if (autoCierreDoneRef.current) return;
    const payload = cierrePayload();
    if (payload.length === 0) return;
    try {
      const res = await apiSend<{ triggered?: boolean; written?: boolean }>(
        "POST",
        `/api/matters/${matterId}/cierre`,
        { messages: payload, auto: true },
      );
      if (res.triggered) {
        // Disparó el destilado (corrió el LLM): no re-destilar en turnos siguientes.
        autoCierreDoneRef.current = true;
        if (res.written) {
          setNotice({
            type: "success",
            text:
              "La conversación se hizo larga, así que guardé por ti en el expediente lo que " +
              "decidiste hasta aquí. Puedes seguir sin perder el hilo.",
          });
        }
      }
    } catch {
      /* el cierre-auto nunca molesta al abogado: si falla, se ignora en silencio */
    }
  }

  const lastIdx = messages.length - 1;

  return (
    <div className="flex h-[100dvh] min-h-0">
      {/* Expediente (documentos del asunto) */}
      <aside className="hidden w-[280px] shrink-0 flex-col border-r border-border bg-card/40 lg:flex">
        <div className="border-b border-border px-5 py-4">
          <button
            onClick={() => router.push("/")}
            className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" />
            Asuntos
          </button>
          <div className="font-semibold leading-tight">{matter?.name || "Asunto"}</div>
        </div>
        <div className="flex-1 overflow-auto px-3 py-3">
          {docs.length === 0 ? (
            <div className="px-2 py-6 text-center">
              <FileText className="mx-auto mb-2 h-5 w-5 text-muted-foreground/50" />
              <p className="text-xs text-muted-foreground">
                Sube el expediente para que Mia trabaje con las pruebas reales.
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {docs.map((d) => (
                <li
                  key={d.id}
                  className="flex items-start gap-2 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-accent/60"
                >
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary/70" />
                  <div className="min-w-0">
                    <div className="truncate font-medium">{d.name}</div>
                    <div className="text-xs text-muted-foreground">{fmtDate(d.created_at)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t border-border p-3">
          {/* Panel "Fuentes" unificado (Bloque A · Ola A3): carpetas del equipo, OneDrive
              y correos del caso — antes tres bloques sueltos, ahora un único componente
              autocontenido que carga y refresca su propia lista. */}
          <FuentesPanel matterId={matterId} kind="asunto" onChanged={loadDocs} />

          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" multiple onChange={onUpload} className="hidden" />
          <Button
            variant="outline"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="w-full justify-start gap-2"
          >
            <Paperclip className="h-4 w-4" />
            {uploading ? "Subiendo…" : "Agregar documento"}
          </Button>
          {uploadItems.length > 0 ? (
            <div className="mt-3 space-y-2">
              {uploadItems.map((item) => (
                <div key={item.name} className="text-xs text-muted-foreground">
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
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all duration-300",
                        item.status === "error" ? "bg-destructive" : item.status === "done" ? "bg-success" : "bg-primary",
                      )}
                      style={{ width: item.status === "waiting" ? "15%" : item.status === "uploading" ? "55%" : "100%" }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {uploadSummary ? <div className="mt-3 text-xs font-medium text-success">{uploadSummary}</div> : null}
        </div>
      </aside>

      {/* Consulta: espacio único de conversación (el plan vive en el aside derecho) */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-5 overflow-auto px-6 py-6">
          {notice ? (
            <div
              role={notice.type === "warning" ? "alert" : "status"}
              className={cn(
                "flex items-start gap-3 rounded-xl border px-5 py-4 animate-slide-up",
                notice.type === "warning"
                  ? "border-warning/30 bg-warning/5 text-warning"
                  : "border-success/30 bg-success/10 text-success",
              )}
            >
              {notice.type === "warning" ? (
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
              )}
              <p className="flex-1 text-sm">{notice.text}</p>
              <button
                onClick={() => setNotice(null)}
                aria-label="Cerrar aviso"
                className="shrink-0 opacity-70 transition-opacity hover:opacity-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : null}
          {messages.length === 0 ? (
            <div className="mt-20 text-center animate-slide-up">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Sparkles className="h-5 w-5" />
              </div>
              <p className="text-sm text-muted-foreground">
                Hazle una pregunta a Mia sobre este asunto.
                <br />
                Ella investiga el expediente y te propone un borrador — tú decides.
              </p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={cn("flex gap-3 animate-message-in", m.role === "user" ? "justify-end" : "justify-start")}>
                {m.role === "mia" ? (
                  <div className="relative mt-0.5 h-8 w-8 shrink-0">
                    {streaming && i === lastIdx && !m.text ? (
                      <span className="absolute inset-0 rounded-full bg-primary/40 blur-md animate-pulse-soft" aria-hidden />
                    ) : null}
                    <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-sm">
                      <Scale className="h-4 w-4" />
                    </div>
                  </div>
                ) : null}
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm"
                      : "max-w-[75%] pt-1 font-serif text-[15px] leading-relaxed text-foreground"
                  }
                >
                  {m.text ? (
                    m.role === "mia" ? <MiaMarkdown text={m.text} /> : m.text
                  ) : (
                    <ThinkingDots />
                  )}
                </div>
              </div>
            ))
          )}
          <SalaEstrategiaResult
            matterId={matterId}
            streaming={warroomStreaming}
            statusMessage={warroomStatus}
            error={warroomError}
            debate={warroomDebate}
            result={warroomResult}
            convertingToDraft={convertingToDraft}
            onConvertToDraft={convertWarroomToDraft}
          />
        </div>
        <div className="border-t border-border bg-gradient-to-t from-background to-transparent px-6 py-3">
          <div className="mb-2 flex min-h-5 items-center justify-between text-sm">
            <span className="text-muted-foreground">{status}</span>
            <div className="flex items-center gap-2">
              {pendingCount > 0 ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmOpen(true)}
                  className="gap-1.5 border-primary/40 text-primary animate-slide-up hover:bg-primary/5"
                >
                  <ClipboardCheck className="h-3.5 w-3.5" />
                  Documentos por confirmar
                  <span className="ml-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
                    {pendingCount}
                  </span>
                </Button>
              ) : null}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDiarioOpen(true)}
                className="gap-1.5"
              >
                <Sunrise className="h-3.5 w-3.5" />
                Arrancar el día
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={runCierre}
                disabled={streaming || cierreBusy || messages.length === 0}
                className="gap-1.5"
              >
                <Moon className="h-3.5 w-3.5" />
                Cerrar por hoy
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setWarroomDialogOpen(true)}
                disabled={streaming || warroomStreaming || warroomStarting}
                className="gap-1.5"
              >
                <Swords className="h-3.5 w-3.5" />
                Convocar Sala de estrategia
              </Button>
              {draftApproved && !hasDraft ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setGuideWizardOpen(true)}
                  className="gap-1.5 animate-slide-up"
                >
                  <BookOpen className="h-3.5 w-3.5" />
                  Convertir en guía
                </Button>
              ) : null}
              {hasDraft ? (
                <Button
                  variant="cta"
                  size="sm"
                  onClick={() => router.push(`/asuntos/${matterId}/revisar`)}
                  className="gap-1.5 animate-slide-up"
                >
                  <FileText className="h-3.5 w-3.5" />
                  Revisar borrador
                </Button>
              ) : null}
            </div>
          </div>
          <div className="flex items-end gap-2 rounded-2xl border border-input bg-card p-2 shadow-lg shadow-primary/5 transition-shadow focus-within:border-primary/40 focus-within:shadow-primary/10">
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
              placeholder="Escribe tu consulta sobre este asunto…"
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
            />
            <MicButton state={dictation.state} onToggle={dictation.toggle} />
            <Button
              onClick={send}
              disabled={streaming || !input.trim()}
              size="icon"
              aria-label="Enviar"
              className="transition-transform active:scale-95"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
          {dictation.error ? (
            <p className="mt-2 text-xs text-warning">{dictation.error}</p>
          ) : dictationNotice ? (
            <p className="mt-2 text-xs text-warning">{dictationNotice}</p>
          ) : null}
        </div>
      </div>

      {/* Diagnóstico + Plan de trabajo */}
      <aside className="hidden w-[300px] shrink-0 flex-col gap-5 overflow-y-auto border-l border-border bg-card/40 px-5 py-6 xl:flex">
        <div>
          <h3 className="mb-3 text-sm font-semibold">Diagnóstico</h3>
          {diagnosis ? (
            <div className="animate-fade-in">
              {summary ? (
                <div className="mb-3 space-y-2">
                  <SummaryRow label="Problema jurídico" text={summary.problema} />
                  <SummaryRow label="Normas y fuentes" text={summary.normas} />
                  <SummaryRow label="Riesgo y recomendación" text={summary.riesgo} />
                </div>
              ) : null}
              <div className="whitespace-pre-wrap rounded-xl border border-border bg-card px-3 py-3 font-serif text-sm leading-relaxed text-card-foreground shadow-sm">
                {diagnosis}
              </div>
              {verification && verification.citas > 0 ? (
                <div className="mt-5">
                  <h3 className="mb-3 text-sm font-semibold">Citas del borrador</h3>
                  <CitationReview verification={verification} />
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Cuando le hagas tu primera consulta, aquí verás el problema jurídico, las
              normas aplicables y el riesgo del caso.
            </p>
          )}
        </div>

        {/* Fase 3.1(B): el Plan (antes una pestaña separada, poco descubierta) ahora
            vive aquí, plegable, junto al Diagnóstico. */}
        <details
          open={planOpen}
          onToggle={(e) => setPlanOpen((e.target as HTMLDetailsElement).open)}
          className="group shrink-0 rounded-xl border border-border bg-card shadow-sm"
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
            <span className="flex-1">Plan de trabajo</span>
            {missionsSummary && missionsSummary.count > 0 ? (
              <span className="shrink-0 text-xs font-normal text-muted-foreground">
                {missionsSummary.count} {missionsSummary.count === 1 ? "misión" : "misiones"} ·{" "}
                {missionsSummary.milestonesDone}/{missionsSummary.milestonesTotal} hitos
              </span>
            ) : null}
          </summary>
          <div className="border-t border-border px-4 py-4">
            <p className="mb-3 text-xs text-muted-foreground">
              Aquí vive el plan del caso: misiones e hitos que tú controlas. Pídele a Mia en la
              conversación que te proponga un plan y guárdalo aquí.
            </p>
            <MissionBoard matterId={matterId} compact />
          </div>
        </details>
      </aside>

      <GuideInterviewWizard
        open={guideWizardOpen}
        onOpenChange={setGuideWizardOpen}
        kind="guia"
        matterId={matterId}
      />

      <SalaEstrategiaDialog
        open={warroomDialogOpen}
        onOpenChange={setWarroomDialogOpen}
        matterId={matterId}
        hasDocuments={docs.length > 0}
        starting={warroomStarting}
        onStart={startWarroom}
      />

      <DiarioDialog open={diarioOpen} onOpenChange={setDiarioOpen} matterId={matterId} />

      <DocumentosPorConfirmarDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        matterId={matterId}
        onChanged={loadPendingCount}
      />

      <CierreDialog
        open={cierreOpen}
        onOpenChange={setCierreOpen}
        busy={cierreBusy}
        result={cierreResult}
      />

      <Dialog
        open={Boolean(delegation)}
        onOpenChange={() => {
          /* Debe elegir Autorizar o Descartar: cerrar sin decidir dejaría el asunto en 409. */
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {delegation?.nombre
                ? `¿Autorizar a ${delegation.nombre}?`
                : "¿Autorizar al asistente externo?"}
            </DialogTitle>
            <DialogDescription>
              {delegation?.aviso ||
                "Esto es una propuesta para que la revises, no algo que Mia ya hizo. Solo saldrá el texto de abajo."}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap">
            {delegation?.texto || "(Sin texto propuesto)"}
          </div>
          <label className="flex items-start gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              className="mt-1"
              checked={delegationRemember}
              onChange={(e) => setDelegationRemember(e.target.checked)}
              disabled={delegationBusy || streaming}
            />
            <span>No volver a preguntarme por este ayudante en este asunto</span>
          </label>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              disabled={delegationBusy || streaming}
              onClick={() => respondDelegation(false)}
            >
              Descartar
            </Button>
            <Button
              disabled={delegationBusy || streaming || !delegation?.huella}
              onClick={() => respondDelegation(true)}
            >
              Autorizar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

type DiagnosisSummary = { problema?: string; normas?: string; riesgo?: string };

function SummaryRow({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2 shadow-sm">
      <div className="text-xs font-semibold uppercase tracking-wide text-primary/80">{label}</div>
      <div className="mt-0.5 text-sm text-card-foreground">{text}</div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex gap-1 py-1 align-middle text-muted-foreground">
      <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
    </span>
  );
}

function Dot({ delay = "0ms" }: { delay?: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current"
      style={{ animationDelay: delay }}
    />
  );
}
