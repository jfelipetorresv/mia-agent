"use client";

// Mia · Bloque B (B1-B2-B3) — asistente conversacional que le ayuda al abogado a
// convertir lo que tiene en la cabeza en una guía de trabajo escrita.
//
// Motor STATELESS en el backend: este componente manda el transcript completo en
// cada turno y el backend responde la siguiente pregunta o el borrador final. El
// borrador SOLO existe en la respuesta HTTP — nada se guarda hasta que el abogado
// pulsa "Guardar guía" (gate HITL por construcción, ver interviewer.py).
//
// Reusable: el Bloque C reutiliza este mismo wizard con kind="agente" para crear
// agentes jurídicos con conocimiento propio.

import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { apiSend, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Msg = { role: "assistant" | "user"; content: string };

type Draft = { title: string; summary: string; applies_when: string; content: string };

type InterviewResponse =
  | { done: false; question: string }
  | {
      done: true;
      draft: Record<string, unknown>;
      explanation: string;
      suggested_playbook_ids?: string[];
    };

type Screen = "entrevista" | "revision" | "guardando";

export default function GuideInterviewWizard({
  open,
  onOpenChange,
  kind,
  matterId,
  onSaved,
  onDraftReady,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: "guia" | "agente";
  matterId?: string;
  onSaved?: () => void;
  // Bloque C: cuando kind='agente' y la entrevista termina, el wizard NO guarda ni muestra la
  // revisión de guía — entrega el borrador del agente para precargar el formulario (gate HITL).
  onDraftReady?: (
    draft: Record<string, unknown>,
    explanation: string,
    suggestedPlaybookIds: string[],
  ) => void;
}) {
  const [screen, setScreen] = useState<Screen>("entrevista");
  const [transcript, setTranscript] = useState<Msg[]>([]);
  const [answer, setAnswer] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [explanation, setExplanation] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Al abrir, arranca la entrevista desde cero (primer POST con messages:[]).
  useEffect(() => {
    if (!open) return;
    setScreen("entrevista");
    setTranscript([]);
    setAnswer("");
    setError(null);
    setDraft(null);
    setExplanation("");
    setSaveError(null);
    setSaved(false);
    void ask([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function ask(messages: Msg[]) {
    setThinking(true);
    setError(null);
    try {
      const res = await apiSend<InterviewResponse>("POST", "/api/guides/interview", {
        kind,
        messages,
        matter_id: matterId,
      });
      if (res.done) {
        if (kind === "agente") {
          // El agente NO se guarda aquí: se entrega el borrador para precargar el formulario
          // de creación, donde el abogado revisa y pulsa Guardar (gate HITL por construcción).
          onDraftReady?.(res.draft, res.explanation, res.suggested_playbook_ids ?? []);
          onOpenChange(false);
          return;
        }
        setDraft(res.draft as unknown as Draft);
        setExplanation(res.explanation);
        setScreen("revision");
      } else {
        setTranscript([...messages, { role: "assistant", content: res.question }]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo conectar con Mia. Intenta de nuevo.");
    } finally {
      setThinking(false);
    }
  }

  async function continuar() {
    const text = answer.trim();
    if (!text || thinking) return;
    const next: Msg[] = [...transcript, { role: "user", content: text }];
    setTranscript(next);
    setAnswer("");
    await ask(next);
  }

  async function guardar() {
    if (!draft) return;
    setSaveError(null);
    setScreen("guardando");
    try {
      await apiSend("POST", "/api/playbooks", {
        title: draft.title,
        summary: draft.summary,
        applies_when: draft.applies_when,
        content: draft.content,
        origin: matterId ? "asunto" : "entrevista",
      });
      setSaved(true);
      onSaved?.();
      setTimeout(() => {
        onOpenChange(false);
      }, 900);
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : "No se pudo guardar la guía. Intenta de nuevo.");
      setScreen("revision");
    }
  }

  const lastQuestion = transcript.length > 0
    ? [...transcript].reverse().find((m) => m.role === "assistant")?.content
    : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-lg">
        {screen === "entrevista" ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                {kind === "agente" ? "Diseñar agente con Mia" : "Crear guía con Mia"}
              </DialogTitle>
              <DialogDescription>
                {kind === "agente"
                  ? "Estás diseñando un agente jurídico. Nada se guarda hasta que pulses Guardar en el formulario."
                  : "Mia te hace unas preguntas cortas para entender cómo trabajas y arma un primer borrador de la guía. Tú decides si se guarda."}
              </DialogDescription>
            </DialogHeader>

            {transcript.length > 1 ? (
              <div className="max-h-40 space-y-2 overflow-auto rounded-lg bg-muted/50 p-3 text-sm">
                {transcript.slice(0, -1).map((m, i) => (
                  <div key={i} className={m.role === "assistant" ? "text-muted-foreground" : "font-medium"}>
                    {m.role === "assistant" ? "Mia: " : "Tú: "}
                    {m.content}
                  </div>
                ))}
              </div>
            ) : null}

            {lastQuestion ? (
              <p className="font-serif text-[15px] leading-relaxed text-foreground">{lastQuestion}</p>
            ) : null}

            {thinking ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Mia está pensando la siguiente pregunta…
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="guide-interview-answer">Tu respuesta</Label>
                <Textarea
                  id="guide-interview-answer"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      continuar();
                    }
                  }}
                  className="h-24 resize-none"
                  placeholder="Escribe tu respuesta…"
                  autoFocus
                />
              </div>
            )}

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button onClick={continuar} disabled={thinking || !answer.trim()}>
                Continuar
              </Button>
            </DialogFooter>
          </>
        ) : null}

        {(screen === "revision" || screen === "guardando") && draft ? (
          <>
            <DialogHeader>
              <DialogTitle>Revisa el borrador de la guía</DialogTitle>
              <DialogDescription>
                Esta guía todavía no existe; solo se guardará cuando pulses Guardar.
              </DialogDescription>
            </DialogHeader>

            {explanation ? (
              <p className="rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">{explanation}</p>
            ) : null}

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="guide-draft-title">Título</Label>
                <Input
                  id="guide-draft-title"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="guide-draft-summary">Resumen</Label>
                <Input
                  id="guide-draft-summary"
                  value={draft.summary}
                  onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="guide-draft-applies">Cuándo aplica</Label>
                <Input
                  id="guide-draft-applies"
                  value={draft.applies_when}
                  onChange={(e) => setDraft({ ...draft, applies_when: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="guide-draft-content">Contenido</Label>
                <Textarea
                  id="guide-draft-content"
                  value={draft.content}
                  onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                  className="h-48 resize-none"
                />
              </div>
            </div>

            {saveError ? <p className="text-sm text-destructive">{saveError}</p> : null}
            {saved ? <p className="text-sm text-success">Guía guardada.</p> : null}

            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={screen === "guardando"}>
                Cancelar
              </Button>
              <Button onClick={guardar} disabled={screen === "guardando" || !draft.title.trim() || !draft.content.trim()} className="gap-2">
                {screen === "guardando" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Guardar guía
              </Button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
