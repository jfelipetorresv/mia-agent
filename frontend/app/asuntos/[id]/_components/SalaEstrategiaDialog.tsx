"use client";

// Sala de estrategia · modal de ajuste del panel (§G: "counsel", "posturas" —
// nunca "agente"/"war room"/"LLM"). Carga la propuesta de Mia (3-4 counsel con
// posturas opuestas), permite quitarlos o sumar Agentes jurídicos reales del
// despacho, y arranca la sesión. El streaming vive en la pantalla del asunto
// (page.tsx) — este modal solo arma el panel y dispara `onStart`.

import { useEffect, useState } from "react";
import { Loader2, Plus, UserX } from "lucide-react";
import { ApiError, apiGet } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AvailablePersona, Panelist, PanelProposal } from "./warroom-types";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  matterId: string;
  // Si el asunto AÚN no tiene expediente, la sala no puede correr (el motor exige documentos):
  // se avisa en llano y se bloquea "Empezar" antes de arrancar (MAYOR 2).
  hasDocuments: boolean;
  starting: boolean;
  onStart: (panel: Panelist[], question: string) => void;
};

const MIN_PANEL = 2;

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

export default function SalaEstrategiaDialog({ open, onOpenChange, matterId, hasDocuments, starting, onStart }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [proposal, setProposal] = useState<PanelProposal | null>(null);
  const [panel, setPanel] = useState<Panelist[]>([]);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setProposal(null);
    apiGet<PanelProposal>(`/api/matters/${matterId}/warroom/panel`)
      .then((res) => {
        if (cancelled) return;
        setProposal(res);
        setPanel(res.proposed || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(apiMessage(err, "No pude preparar la sala de estrategia. Intenta de nuevo."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, matterId]);

  function removeFromPanel(idx: number) {
    setPanel((p) => p.filter((_, i) => i !== idx));
  }

  function addAvailable(persona: AvailablePersona) {
    setPanel((p) => [
      ...p,
      {
        persona_id: persona.persona_id,
        stance: "personalizado",
        name: persona.name,
        stance_label: persona.title,
        focus: persona.focus_areas.join(", "),
      },
    ]);
  }

  function handleClose(nextOpen: boolean) {
    if (starting) return; // anti doble-clic mientras arranca
    onOpenChange(nextOpen);
    if (!nextOpen) setQuestion("");
  }

  const yaEnPanel = new Set(panel.map((p) => p.persona_id).filter(Boolean));
  const disponibles = (proposal?.available || []).filter((a) => !yaEnPanel.has(a.persona_id));
  const puedeEmpezar = panel.length >= MIN_PANEL && !starting && !loading && hasDocuments;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent aria-label="Sala de estrategia" className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Convocar la sala de estrategia</DialogTitle>
          <DialogDescription>
            Mia reúne un panel de counsel con posturas opuestas para contrastar tu caso desde varios
            ángulos y cerrar con un dictamen. Puedes ajustar quién participa.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Preparando el panel…
          </div>
        ) : error ? (
          <p role="alert" className="py-4 text-sm text-warning">
            {error}
          </p>
        ) : (
          <div className="space-y-4">
            {!hasDocuments ? (
              <p role="alert" className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-sm text-warning">
                Sube documentos del expediente para convocar la sala de estrategia: el panel
                debate sobre las pruebas reales del asunto.
              </p>
            ) : null}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Panel propuesto
              </p>
              {panel.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
                  Sin counsel en el panel — suma al menos {MIN_PANEL} para empezar.
                </p>
              ) : (
                <ul className="space-y-2">
                  {panel.map((p, idx) => (
                    <li
                      key={`${p.persona_id ?? "sintetico"}-${p.stance}-${idx}`}
                      className="flex items-start justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2.5 text-sm"
                    >
                      <div className="min-w-0">
                        <div className="font-medium">{p.name}</div>
                        <div className="text-xs text-primary/80">{p.stance_label}</div>
                        {p.focus ? <div className="mt-0.5 text-xs text-muted-foreground">{p.focus}</div> : null}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeFromPanel(idx)}
                        aria-label={`Quitar a ${p.name} del panel`}
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                      >
                        <UserX className="h-4 w-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {disponibles.length > 0 ? (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Sumar del despacho
                </p>
                <ul className="space-y-2">
                  {disponibles.map((a) => (
                    <li
                      key={a.persona_id}
                      className="flex items-start justify-between gap-2 rounded-lg border border-border px-3 py-2.5 text-sm"
                    >
                      <div className="min-w-0">
                        <div className="font-medium">{a.name}</div>
                        <div className="text-xs text-muted-foreground">{a.title}</div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => addAvailable(a)}
                        aria-label={`Sumar a ${a.name} al panel`}
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-primary"
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div>
              <Label htmlFor="warroom-question" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Algo puntual que quieras que discutan (opcional)
              </Label>
              <Textarea
                id="warroom-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Por ejemplo: ¿la excepción de prescripción tiene piso?"
                className="mt-2 min-h-[80px]"
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleClose(false)} disabled={starting}>
            Cancelar
          </Button>
          <Button
            variant="cta"
            onClick={() => onStart(panel, question.trim())}
            disabled={!puedeEmpezar}
            className="gap-2"
          >
            {starting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Reuniendo la sala…
              </>
            ) : (
              "Empezar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
