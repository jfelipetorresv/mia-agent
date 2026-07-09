"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  FolderCheck,
  Link2,
  Loader2,
  MoreVertical,
  Paperclip,
  RefreshCw,
  Scale,
  Send,
  Sparkles,
} from "lucide-react";
import { ApiError, apiGet, apiSend, apiUpload, streamTurn } from "@/lib/api";
import { useDictation } from "@/lib/useDictation";
import MicButton from "../../_components/MicButton";
import MissionBoard from "../../_components/MissionBoard";
import CitationReview, { type Verification } from "../../_components/CitationReview";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type Doc = { id: string; name: string; type?: string; created_at?: string };
type Msg = { role: "user" | "mia"; text: string };
type UploadItem = { name: string; status: "waiting" | "uploading" | "done" | "error" };
type UploadResponse = { id?: string; name?: string; status?: string; message?: string; fragments?: number };

// Carpeta vinculada del expediente (Fase 3.1(B)): GET/POST/DELETE /api/matters/{id}/folder.
type FolderStatus = {
  linked: boolean;
  path: string | null;
  last_sync: string | null;
  files_indexed: number;
  pending_retry: number;
};
type DetectedFolder = { label: string; path: string; registered?: boolean };
type MissionsSummary = { count: number; milestonesDone: number; milestonesTotal: number };

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

// Tiempo relativo en español ("hace 3 minutos") para la última revisión de la carpeta.
function fmtRelative(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 60) return "hace un momento";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} ${diffMin === 1 ? "minuto" : "minutos"}`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `hace ${diffHr} ${diffHr === 1 ? "hora" : "horas"}`;
  const diffDay = Math.floor(diffHr / 24);
  return `hace ${diffDay} ${diffDay === 1 ? "día" : "días"}`;
}

function apiErrorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
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

  // Fase 3.1(B) · carpeta vinculada del expediente.
  const [folder, setFolder] = useState<FolderStatus | null>(null);
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [detectedFolders, setDetectedFolders] = useState<DetectedFolder[]>([]);
  const [folderPathInput, setFolderPathInput] = useState("");
  const [linking, setLinking] = useState(false);
  const [linkMsg, setLinkMsg] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");
  const [unlinkOpen, setUnlinkOpen] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const folderPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const folderPollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fase 3.1(B) · Plan de trabajo (aside): contador liviano para el header de la card.
  const [missionsSummary, setMissionsSummary] = useState<MissionsSummary | null>(null);
  const [planOpen, setPlanOpen] = useState(false);

  const dictation = useDictation(
    (text) => {
      setDictationNotice("");
      setInput((prev) => (prev.trim() ? prev.trimEnd() + " " + text : text));
    },
    (notice) => setDictationNotice(notice),
  );

  async function loadDocs() {
    try {
      setDocs(await apiGet<Doc[]>(`/api/matters/${matterId}/documents`));
    } catch {
      /* sin documentos */
    }
  }

  async function loadFolder() {
    try {
      setFolder(await apiGet<FolderStatus>(`/api/matters/${matterId}/folder`));
    } catch {
      /* no se pudo cargar el estado de la carpeta */
    }
  }

  function stopFolderPolling() {
    if (folderPollRef.current) {
      clearInterval(folderPollRef.current);
      folderPollRef.current = null;
    }
    if (folderPollTimeoutRef.current) {
      clearTimeout(folderPollTimeoutRef.current);
      folderPollTimeoutRef.current = null;
    }
  }

  // Tras vincular o pedir una revisión, refresca el estado cada ~5s hasta que
  // files_indexed se mueva (o hasta 30s máx.) — así el abogado ve avance sin recargar.
  function startFolderPolling(baselineFilesIndexed: number) {
    stopFolderPolling();
    folderPollRef.current = setInterval(async () => {
      try {
        const status = await apiGet<FolderStatus>(`/api/matters/${matterId}/folder`);
        setFolder(status);
        if (status.files_indexed !== baselineFilesIndexed) {
          stopFolderPolling();
          loadDocs();
        }
      } catch {
        /* reintenta en el siguiente tick */
      }
    }, 5000);
    folderPollTimeoutRef.current = setTimeout(stopFolderPolling, 30000);
  }

  useEffect(() => {
    apiGet<{ name?: string }>(`/api/matters/${matterId}`).then(setMatter).catch(() => {});
    loadDocs();
    loadFolder();
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
      diagnosis?: string;
      awaiting_review?: boolean;
      diagnosis_summary?: DiagnosisSummary | null;
      verification?: Verification | null;
    }>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        if (d.diagnosis) setDiagnosis(d.diagnosis);
        if (d.diagnosis_summary) setSummary(d.diagnosis_summary);
        if (d.verification) setVerification(d.verification);
        if (d.awaiting_review) setHasDraft(true);
      })
      .catch(() => {
        /* sin borrador todavia */
      });
    return () => {
      streamAbortRef.current?.abort();
      stopFolderPolling();
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
          const payload = data as {
            message?: string;
            draft?: string;
            diagnosis?: string;
            diagnosis_summary?: DiagnosisSummary | null;
            verification?: Verification | null;
          };
          if (event === "thinking") setStatus(payload.message || "Mia esta analizando...");
          else if (event === "draft_ready") setStatus("Mia esta redactando...");
          else if (event === "error") setStatus(payload.message || "No se pudo completar la consulta.");
          else if (event === "awaiting_review") {
            setStatus("Tienes un borrador listo");
            setHasDraft(true);
            if (payload.diagnosis) setDiagnosis(payload.diagnosis);
            if (payload.diagnosis_summary) setSummary(payload.diagnosis_summary);
            if (payload.verification) setVerification(payload.verification);
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

  async function openFolderDialog() {
    setFolderDialogOpen(true);
    setLinkMsg("");
    try {
      const res = await apiGet<{ detected: DetectedFolder[] }>("/api/folders/detected");
      setDetectedFolders(res.detected || []);
    } catch {
      setDetectedFolders([]);
    }
  }

  async function linkFolder() {
    const path = folderPathInput.trim();
    if (!path || linking) return;
    setLinking(true);
    setLinkMsg("");
    try {
      await apiSend("POST", `/api/matters/${matterId}/folder`, { path });
      setFolderDialogOpen(false);
      setFolderPathInput("");
      const status = await apiGet<FolderStatus>(`/api/matters/${matterId}/folder`);
      setFolder(status);
      startFolderPolling(status.files_indexed);
    } catch (err) {
      setLinkMsg(apiErrorMessage(err, "No se pudo vincular la carpeta. Revisa la ruta e intenta de nuevo."));
    } finally {
      setLinking(false);
    }
  }

  async function syncFolderNow() {
    if (syncing) return;
    setSyncing(true);
    setSyncMsg("");
    try {
      const res = await apiSend<{ status: string; message: string }>(
        "POST",
        `/api/matters/${matterId}/folder/sync`,
      );
      setSyncMsg(res.message || "Estoy revisando la carpeta del expediente.");
      const status = await apiGet<FolderStatus>(`/api/matters/${matterId}/folder`);
      setFolder(status);
      if (res.status === "started") startFolderPolling(status.files_indexed);
    } catch (err) {
      setSyncMsg(apiErrorMessage(err, "No se pudo revisar la carpeta. Intenta de nuevo."));
    } finally {
      setSyncing(false);
    }
  }

  async function unlinkFolder() {
    if (unlinking) return;
    setUnlinking(true);
    try {
      const res = await apiSend<{ message: string }>("DELETE", `/api/matters/${matterId}/folder`);
      stopFolderPolling();
      setFolder({ linked: false, path: null, last_sync: null, files_indexed: 0, pending_retry: 0 });
      setUnlinkOpen(false);
      setSyncMsg(res.message || "Desvinculé la carpeta. Los documentos que ya había traído siguen en tu expediente.");
    } catch (err) {
      setSyncMsg(apiErrorMessage(err, "No se pudo desvincular la carpeta. Intenta de nuevo."));
    } finally {
      setUnlinking(false);
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
          {/* Carpeta del expediente (Fase 3.1(B)): vínculo real contra el backend,
              con revisión incremental — reemplaza la vieja subida webkitdirectory. */}
          {folder?.linked ? (
            <div className="mb-3 rounded-lg border border-border bg-card px-3 py-2.5 text-xs">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 font-medium text-foreground">
                    <FolderCheck className="h-3.5 w-3.5 shrink-0 text-primary" />
                    Carpeta del expediente
                  </div>
                  <div className="mt-0.5 truncate text-muted-foreground" title={folder.path ?? undefined}>
                    {folder.path}
                  </div>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" aria-label="Más acciones">
                      <MoreVertical className="h-3.5 w-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setUnlinkOpen(true)} className="text-destructive">
                      Desvincular
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="mt-2 text-muted-foreground">
                {folder.files_indexed} {folder.files_indexed === 1 ? "documento leído" : "documentos leídos"}
                {folder.last_sync ? ` · última revisión ${fmtRelative(folder.last_sync)}` : " · aún sin revisar"}
              </div>
              {folder.pending_retry > 0 ? (
                <Badge variant="warning" className="mt-2 bg-warning/15 text-warning">
                  {folder.pending_retry}{" "}
                  {folder.pending_retry === 1
                    ? "archivo abierto quedó para la próxima revisión"
                    : "archivos abiertos quedaron para la próxima revisión"}
                </Badge>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                onClick={syncFolderNow}
                disabled={syncing}
                className="mt-2 w-full gap-1.5"
              >
                {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                {syncing ? "Revisando…" : "Revisar ahora"}
              </Button>
              {syncMsg ? <p className="mt-1.5 text-muted-foreground">{syncMsg}</p> : null}
            </div>
          ) : (
            <Button
              variant="outline"
              onClick={openFolderDialog}
              className="mb-3 w-full justify-start gap-2"
            >
              <Link2 className="h-4 w-4" />
              Vincular carpeta del expediente
            </Button>
          )}

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
                      : "max-w-[75%] whitespace-pre-wrap pt-1 font-serif text-[15px] leading-relaxed text-foreground"
                  }
                >
                  {m.text || <ThinkingDots />}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="border-t border-border bg-gradient-to-t from-background to-transparent px-6 py-3">
          <div className="mb-2 flex min-h-5 items-center justify-between text-sm">
            <span className="text-muted-foreground">{status}</span>
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

      {/* Vincular carpeta del expediente */}
      <Dialog
        open={folderDialogOpen}
        onOpenChange={(open) => {
          if (linking) return;
          setFolderDialogOpen(open);
          if (!open) {
            setFolderPathInput("");
            setLinkMsg("");
          }
        }}
      >
        <DialogContent aria-label="Vincular carpeta del expediente" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Vincular carpeta del expediente</DialogTitle>
            <DialogDescription>
              Mia revisará esta carpeta y mantendrá el expediente al día: lo nuevo, lo cambiado y lo
              borrado. Nada sale de tu equipo.
            </DialogDescription>
          </DialogHeader>
          {detectedFolders.length > 0 ? (
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                Sugerencias detectadas en este equipo
              </p>
              <ul className="space-y-1.5">
                {detectedFolders.map((d) => (
                  <li key={d.path}>
                    <button
                      type="button"
                      onClick={() => setFolderPathInput(d.path)}
                      className="w-full rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent/50"
                    >
                      <div className="font-medium">{d.label}</div>
                      <div className="truncate text-xs text-muted-foreground">{d.path}</div>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-xs text-muted-foreground">
                También puedes pegar la ruta de una subcarpeta específica de este caso abajo.
              </p>
            </div>
          ) : null}
          <div>
            <Label htmlFor="folder-path" className="mb-1.5 block text-sm">
              Ruta de la carpeta
            </Label>
            <Input
              id="folder-path"
              value={folderPathInput}
              onChange={(e) => setFolderPathInput(e.target.value)}
              placeholder="Ej.: C:\Users\TuUsuario\OneDrive\Casos\Asunto 123"
            />
          </div>
          {linkMsg ? (
            <p role="alert" className="text-sm text-warning">
              {linkMsg}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setFolderDialogOpen(false)} disabled={linking}>
              Cancelar
            </Button>
            <Button onClick={linkFolder} disabled={linking || !folderPathInput.trim()}>
              {linking ? "Vinculando…" : "Vincular carpeta"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Desvincular carpeta del expediente */}
      <Dialog open={unlinkOpen} onOpenChange={(open) => !unlinking && setUnlinkOpen(open)}>
        <DialogContent aria-label="Desvincular carpeta del expediente">
          <DialogHeader>
            <DialogTitle>¿Desvincular la carpeta del expediente?</DialogTitle>
            <DialogDescription>
              Mia dejará de revisar esta carpeta. Los documentos que ya leyó se conservan en el
              expediente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUnlinkOpen(false)} disabled={unlinking}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={unlinkFolder} disabled={unlinking}>
              {unlinking ? "Desvinculando…" : "Desvincular"}
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
