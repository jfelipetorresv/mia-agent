// Mia · CP-Z1b — botón de micrófono del dictado por voz (presentacional).
// El estado se comunica con TEXTO además del color (accesibilidad): el pulso
// rojo al grabar y el spinner al transcribir van acompañados de su etiqueta.
"use client";

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
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition " +
          (grabando
            ? "animate-pulse border-red-300 bg-red-100 text-red-700"
            : transcribiendo
              ? "border-gray-200 bg-gray-100 text-gray-400"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-400")
        }
      >
        {transcribiendo ? (
          <svg
            viewBox="0 0 24 24"
            className="h-4 w-4 animate-spin"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
          </svg>
        ) : (
          <svg
            viewBox="0 0 24 24"
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" strokeLinecap="round" />
            <path d="M12 18v3" strokeLinecap="round" />
          </svg>
        )}
      </button>
      {(grabando || transcribiendo) && (
        <span
          className={
            "text-xs " + (grabando ? "text-red-700" : "text-gray-500")
          }
          role="status"
        >
          {LABELS[state]}
        </span>
      )}
    </div>
  );
}
