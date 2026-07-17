"use client";

// Mia · espacio de trabajo de un Proyecto (Bloque A · Ola A4). Tres columnas:
// fuentes conectadas (izquierda), chat con Mia (centro, protagonista) y archivos
// que Mia va produciendo (derecha). Sin diagnóstico ni aprobación de borrador —
// eso es exclusivo de la pantalla de Asuntos (asuntos/[id]/page.tsx), de la que
// este archivo toma prestado el mecanismo de streaming (mismo transporte SSE),
// pero el contrato de eventos del proyecto es más simple: "thinking" (avance),
// "reply" (respuesta final de Mia) y "error" — sin awaiting_review ni draft_ready.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, FileText, Save, Send, Sparkles } from "lucide-react";
import { apiDownload, apiGet, apiSend, streamTurn } from "@/lib/api";
import MicButton from "../../_components/MicButton";
import FuentesPanel from "../../_components/FuentesPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDictation } from "@/lib/useDictation";
import { cn } from "@/lib/utils";

type Matter = { name?: string; kind?: string };
type Msg = { role: "user" | "mia"; text: string };
type Output = { id: string; title: string; created_at?: string };

// Umbral a partir del cual vale la pena ofrecer "Guardar en el proyecto" bajo una
// respuesta de Mia — respuestas cortas (confirmaciones, aclaraciones) no son un
// archivo que valga la pena conservar aparte.
const SAVE_THRESHOLD = 600;

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

// Prellena el título del diálogo de guardado con las primeras palabras del texto
// (tope de caracteres para que quepa cómodo como nombre de archivo).
function primerasPalabras(text: string, maxChars = 60): string {
  const limpio = text.trim().replace(/\s+/g, " ");
  if (limpio.length <= maxChars) return limpio;
  const corte = limpio.slice(0, maxChars);
  const ultimoEspacio = corte.lastIndexOf(" ");
  return (ultimoEspacio > 20 ? corte.slice(0, ultimoEspacio) : corte).trim();
}

export default function ProyectoWorkspacePage({ params }: { params: { id: string } }) {
  const matterId = params.id;
  const router = useRouter();
  const [matter, setMatter] = useState<Matter | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);
  const [dictationNotice, setDictationNotice] = useState("");

  const [outputs, setOutputs] = useState<Output[]>([]);
  const [outputsLoading, setOutputsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState("");

  const [saveOpen, setSaveOpen] = useState(false);
  const [saveContent, setSaveContent] = useState("");
  const [saveTitle, setSaveTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveNotice, setSaveNotice] = useState("");

  const dictation = useDictation(
    (text) => {
      setDictationNotice("");
      setInput((prev) => (prev.trim() ? prev.trimEnd() + " " + text : text));
    },
    (notice) => setDictationNotice(notice),
  );

  async function loadOutputs() {
    setOutputsLoading(true);
    try {
      const res = await apiGet<{ outputs: Output[] }>(`/api/matters/${matterId}/outputs`);
      setOutputs(res.outputs || []);
    } catch {
      setOutputs([]);
    }
    setOutputsLoading(false);
  }

  useEffect(() => {
    apiGet<Matter>(`/api/matters/${matterId}`)
      .then((m) => {
        if (m.kind && m.kind !== "proyecto") {
          router.replace(`/asuntos/${matterId}`);
          return;
        }
        setMatter(m);
      })
      .catch(() => setNotFound(true));
    loadOutputs();
    return () => {
      streamAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "mia", text: "" }]);
    setStatus("Mia está trabajando…");
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
          const payload = data as { message?: string; reply?: string };
          if (event === "thinking") {
            setStatus(payload.message || "Mia está trabajando…");
          } else if (event === "reply") {
            setStatus("");
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = {
                role: "mia",
                text: payload.reply || "No pude generar una respuesta.",
              };
              return copy;
            });
          } else if (event === "error") {
            const mensaje = payload.message || "No pude completar esta consulta.";
            setStatus(mensaje);
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: "mia", text: mensaje };
              return copy;
            });
          }
        },
        controller.signal,
      );
    } catch {
      const mensaje = "No se pudo completar la consulta.";
      setStatus(mensaje);
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "mia", text: mensaje };
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }

  function abrirGuardar(text: string) {
    setSaveContent(text);
    setSaveTitle(primerasPalabras(text));
    setSaveError("");
    setSaveOpen(true);
  }

  async function guardarSalida() {
    if (saving) return;
    if (!saveTitle.trim()) {
      setSaveError("Ponle un título al archivo.");
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      const res = await apiSend<{ id: string; title: string; status: string; message?: string }>(
        "POST",
        `/api/matters/${matterId}/outputs`,
        { title: saveTitle.trim(), content: saveContent },
      );
      setSaveOpen(false);
      setSaveNotice(
        res.status === "duplicado"
          ? res.message || "Ese archivo ya estaba guardado en el proyecto."
          : `Guardé «${res.title}» en los archivos del proyecto.`,
      );
      await loadOutputs();
    } catch {
      setSaveError("No se pudo guardar este archivo. Intenta de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  async function descargar(o: Output) {
    setDownloadError("");
    setDownloadingId(o.id);
    try {
      await apiDownload(`/api/matters/${matterId}/outputs/${o.id}.docx`, `${o.title}.docx`);
    } catch {
      setDownloadError("No se pudo descargar el archivo. Intenta de nuevo.");
    } finally {
      setDownloadingId(null);
    }
  }

  const lastIdx = messages.length - 1;

  if (notFound) {
    return (
      <div className="mx-auto max-w-md px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">No pude abrir este proyecto.</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/proyectos")}>
          Volver a proyectos
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-border bg-background/80 px-5 py-3 backdrop-blur">
        <button
          onClick={() => router.push("/proyectos")}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" />
          Proyectos
        </button>
        <span className="text-muted-foreground/40">·</span>
        <span className="truncate font-semibold leading-tight">{matter?.name || "Proyecto"}</span>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[280px_1fr_300px] lg:overflow-hidden">
        {/* Fuentes conectadas del proyecto */}
        <aside className="flex shrink-0 flex-col border-b border-border bg-card/40 px-4 py-4 lg:border-b-0 lg:border-r lg:overflow-y-auto">
          <FuentesPanel matterId={matterId} kind="proyecto" />
        </aside>

        {/* Chat con Mia — protagonista del proyecto */}
        <div className="flex min-h-[60vh] min-w-0 flex-col lg:min-h-0">
          <div className="flex-1 space-y-5 overflow-auto px-6 py-6">
            {messages.length === 0 ? (
              <div className="mt-16 text-center animate-slide-up">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Sparkles className="h-5 w-5" />
                </div>
                <p className="text-sm text-muted-foreground">
                  Hazle una pregunta a Mia sobre las fuentes de este proyecto.
                  <br />
                  Lo que responda lo puedes guardar como archivo del proyecto.
                </p>
              </div>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  className={cn("flex flex-col gap-1 animate-message-in", m.role === "user" ? "items-end" : "items-start")}
                >
                  <div className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}>
                    {m.role === "mia" ? (
                      <div className="relative mt-0.5 h-8 w-8 shrink-0">
                        {streaming && i === lastIdx && !m.text ? (
                          <span className="absolute inset-0 rounded-full bg-primary/40 blur-md animate-pulse-soft" aria-hidden />
                        ) : null}
                        <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-sm">
                          <Sparkles className="h-4 w-4" />
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
                  {m.role === "mia" && m.text.length > SAVE_THRESHOLD ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => abrirGuardar(m.text)}
                      className="ml-11 gap-1.5 text-xs"
                    >
                      <Save className="h-3.5 w-3.5" />
                      Guardar en el proyecto
                    </Button>
                  ) : null}
                </div>
              ))
            )}
          </div>
          <div className="border-t border-border bg-gradient-to-t from-background to-transparent px-6 py-3">
            <div className="mb-2 flex min-h-5 items-center text-sm text-muted-foreground">{status}</div>
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
                placeholder="Escribe tu consulta sobre este proyecto…"
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

        {/* Archivos del proyecto */}
        <aside className="flex shrink-0 flex-col border-t border-border bg-card/40 px-4 py-4 lg:border-t-0 lg:border-l lg:overflow-y-auto">
          <h3 className="mb-2 text-sm font-semibold">Archivos del proyecto</h3>
          {saveNotice ? (
            <div className="mb-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
              {saveNotice}
            </div>
          ) : null}
          {downloadError ? (
            <div className="mb-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
              {downloadError}
            </div>
          ) : null}
          {outputsLoading ? (
            <div className="px-1 py-3 text-xs text-muted-foreground">Cargando…</div>
          ) : outputs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
              Cuando le pidas a Mia algo que valga la pena guardar, aparecerá aquí.
            </div>
          ) : (
            <ul className="space-y-2">
              {outputs.map((o) => (
                <li key={o.id} className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 font-medium text-foreground">
                        <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
                        <span className="truncate">{o.title}</span>
                      </div>
                      <div className="mt-0.5 text-muted-foreground">{fmtDate(o.created_at)}</div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      aria-label="Descargar en Word"
                      onClick={() => descargar(o)}
                      disabled={downloadingId === o.id}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      {/* Guardar una respuesta de Mia como archivo del proyecto */}
      <Dialog open={saveOpen} onOpenChange={(o) => !saving && setSaveOpen(o)}>
        <DialogContent aria-label="Guardar en el proyecto">
          <DialogHeader>
            <DialogTitle>Guardar en el proyecto</DialogTitle>
            <DialogDescription>Ponle un título a este archivo — podrás descargarlo en Word.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="output-title">Título</Label>
            <Input
              id="output-title"
              value={saveTitle}
              onChange={(e) => setSaveTitle(e.target.value)}
              placeholder="Título del archivo"
              autoFocus
            />
          </div>
          {saveError ? (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {saveError}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSaveOpen(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button onClick={guardarSalida} disabled={saving}>
              {saving ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
