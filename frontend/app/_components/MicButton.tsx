// Mia · CP-Z1b — botón de micrófono del dictado por voz (presentacional).
// El estado se comunica con TEXTO además del color (accesibilidad): el pulso
// rojo al grabar y el spinner al transcribir van acompañados de su etiqueta.
"use client";

import { Loader2, Mic } from "lucide-react";

import type { DictationState } from "../../lib/useDictation";

const LABELS: Record<DictationState, string> = {
  inactivo: "Dictar con tu voz",
  grabando: "Dictando… toca para terminar",
  transcribiendo: "Mia está escribiendo tu dictado…",
};

export default function MicButton({
  state,
  onToggle,
}: {
  state: DictationState;
  onToggle: () => void;
}) {
  const grabando = state === "grabando";
  const transcribiendo = state === "transcribiendo";
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onToggle}
        disabled={transcribiendo}
        aria-pressed={grabando}
        aria-label={LABELS[state]}
        title={LABELS[state]}
        className={
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition active:scale-[0.98] " +
          (grabando
            ? "animate-pulse border-destructive/40 bg-destructive/10 text-destructive"
            : transcribiendo
              ? "border-border bg-muted text-muted-foreground"
              : "border-border bg-card text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground")
        }
      >
        {transcribiendo ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : (
          <Mic className="h-4 w-4" aria-hidden />
        )}
      </button>
      {(grabando || transcribiendo) && (
        <span
          className={
            "text-xs " + (grabando ? "text-destructive" : "text-muted-foreground")
          }
          role="status"
        >
          {LABELS[state]}
        </span>
      )}
    </div>
  );
}
