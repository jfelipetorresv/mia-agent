"use client";

// D3 · «Casos»: control visible del comportamiento de Mia en ESTE caso.
// Internamente es la columna `kind` de matters ('asunto' | 'proyecto'), pero el
// abogado nunca ve esos nombres (§G): ve dos formas de trabajar, en llano.
//   'asunto'   → «Con revisión de borrador»: todo termina en un borrador que él aprueba.
//   'proyecto' → «Respuesta directa»: Mia responde de una vez y él guarda lo que sirva.
// El cambio llama a PUT /api/matters/{id}/modo; si el caso tiene un borrador (u otra
// decisión) pendiente, el backend responde 409 con el motivo en llano y aquí se
// muestra tal cual — nunca se esconde ni se traduce a un error genérico.

import { useState } from "react";
import { FileCheck2, MessageSquareText, Repeat } from "lucide-react";
import { apiSend, plainMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { NotaMia } from "@/app/_components/NotaMia";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type CaseKind = "asunto" | "proyecto";

export const KIND_LABEL: Record<CaseKind, string> = {
  asunto: "Con revisión de borrador",
  proyecto: "Respuesta directa",
};

const KIND_HELP: Record<CaseKind, string> = {
  asunto:
    "Mia investiga el expediente y todo termina en un borrador que tú revisas y apruebas. Nada sale sin tu visto bueno.",
  proyecto:
    "Mia te responde de una vez en la conversación, con sus citas verificadas, y tú decides qué guardar como archivo del caso.",
};

export default function ModoDeTrabajo({
  matterId,
  kind,
  onChanged,
  className,
}: {
  matterId: string;
  kind: CaseKind;
  /** Se llama SOLO cuando el backend confirmó el cambio. */
  onChanged: (kind: CaseKind) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<CaseKind>(kind);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function abrir() {
    setSelected(kind);
    setError("");
    setOpen(true);
  }

  async function guardar() {
    if (busy) return;
    if (selected === kind) {
      setOpen(false);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await apiSend<{ kind: CaseKind; changed: boolean }>(
        "PUT",
        `/api/matters/${matterId}/modo`,
        { kind: selected },
      );
      setOpen(false);
      onChanged(res.kind);
    } catch (e) {
      // El 409 del backend trae el motivo honesto (p. ej. «tienes un borrador
      // esperando tu revisión»). Se muestra tal cual, sin genéricos.
      setError(plainMessage(e, "No se pudo cambiar cómo trabaja Mia aquí. Intenta de nuevo."));
    } finally {
      setBusy(false);
    }
  }

  const Icon = kind === "asunto" ? FileCheck2 : MessageSquareText;

  return (
    <div className={cn("min-w-0", className)}>
      <button
        type="button"
        onClick={abrir}
        title="Cambiar cómo trabaja Mia en este caso"
        className="group inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{KIND_LABEL[kind]}</span>
        <Repeat className="h-3 w-3 shrink-0 opacity-60 transition-opacity group-hover:opacity-100" />
      </button>

      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)}>
        {/* max-h + scroll: en pantallas bajas el pie (Cancelar/Guardar) debe seguir
            alcanzable — sin esto el botón Guardar quedaba fuera de la pantalla. */}
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>¿Cómo quieres que Mia trabaje en este caso?</DialogTitle>
            <DialogDescription>
              Puedes cambiarlo cuando quieras; solo cambia cómo te entrega Mia su trabajo.
            </DialogDescription>
          </DialogHeader>

          <div role="radiogroup" aria-label="Modo de trabajo" className="space-y-3 py-1">
            {(Object.keys(KIND_LABEL) as CaseKind[]).map((k) => {
              const OptIcon = k === "asunto" ? FileCheck2 : MessageSquareText;
              const activo = selected === k;
              return (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={activo}
                  onClick={() => setSelected(k)}
                  disabled={busy}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-all duration-200",
                    activo
                      ? "border-primary/50 bg-primary/10 shadow-neu-sunken"
                      : "border-border bg-card shadow-neu-raised hover:-translate-y-0.5",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
                      activo ? "bg-primary text-primary-foreground" : "bg-secondary text-primary shadow-neu-sunken",
                    )}
                  >
                    <OptIcon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{KIND_LABEL[k]}</div>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{KIND_HELP[k]}</p>
                  </div>
                </button>
              );
            })}
          </div>

          <NotaMia
            id="caso-modo-de-trabajo"
            icon={Repeat}
            titulo="Qué cambia al moverlo"
            cerrable={false}
          >
            Solo la entrega: con revisión, mi trabajo se detiene en un borrador que tú
            apruebas; con respuesta directa te contesto de una vez. Tus documentos,
            fuentes y la conversación de este caso se conservan igual.
          </NotaMia>

          {error ? (
            <p role="alert" className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              Cancelar
            </Button>
            <Button onClick={guardar} disabled={busy || selected === kind}>
              {busy ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
