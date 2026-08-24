"use client";

// "Cerrar por hoy" · resultado del cierre de sesión (POST /api/matters/{id}/cierre).
// §G: sin jerga. Muestra en llano lo que Mia GUARDÓ del cierre: los hechos/decisiones
// durables (van al diario del caso) y las decisiones que quedaron ABIERTAS (te esperan
// mañana en "Arrancar el día"). Si no había nada que guardar, lo dice sin alarma: el
// cierre no fabrica nada (regla dura — solo destila lo que el abogado decidió/instruyó).
//
// Este componente solo PRESENTA el resultado; la llamada al backend vive en la pantalla
// del asunto (page.tsx), que es quien tiene la conversación a destilar.

import { BookOpenCheck, CheckCircle2, Loader2, Moon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// Resultado del cierre manual, tal cual lo devuelve distill_and_write_cierre.
export type CierreResult = {
  written: boolean;
  reason: string;
  durables: string[];
  pendientes: string[];
};

// Motivos en los que NO se escribió nada, traducidos a lenguaje llano (§G). El backend
// no fabrica un cierre si no hay nada durable ni interviene el abogado.
const REASON_MESSAGE: Record<string, string> = {
  sin_intervencion_abogado:
    "No encontré instrucciones ni decisiones tuyas en esta conversación para guardar.",
  nada_durable:
    "Revisé la conversación y no había nada nuevo que valiera la pena guardar en el expediente.",
  fallo_llm: "No pude cerrar la sesión en este momento. Intenta de nuevo en un rato.",
  fallo_escritura: "No pude guardar el cierre en el expediente en este momento. Intenta de nuevo.",
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  result: CierreResult | null;
};

export default function CierreDialog({ open, onOpenChange, busy, result }: Props) {
  const hasDurables = Boolean(result?.durables?.length);
  const hasPendientes = Boolean(result?.pendientes?.length);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Moon className="h-5 w-5 text-primary" />
            Cerrar por hoy
          </DialogTitle>
          <DialogDescription>
            Mia repasa la conversación y guarda en el expediente lo que decidiste.
          </DialogDescription>
        </DialogHeader>

        {busy ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Cerrando la sesión…
          </div>
        ) : result?.written ? (
          <div className="max-h-[60vh] space-y-5 overflow-y-auto pr-1">
            <div className="flex items-start gap-2 text-sm text-success">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Listo. Guardé lo importante de esta sesión en el expediente.</p>
            </div>

            {hasDurables ? (
              <div className="space-y-2">
                <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <BookOpenCheck className="h-3.5 w-3.5" />
                  Guardado en el diario del caso
                </h4>
                <ul className="space-y-1.5">
                  {result!.durables.map((d, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-border/10 bg-card px-3 py-2 text-sm leading-relaxed text-card-foreground shadow-neu-raised"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {hasPendientes ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-primary/80">
                  Te espera mañana — pendiente de tu decisión
                </h4>
                <ul className="space-y-1.5">
                  {result!.pendientes.map((p, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm leading-relaxed text-card-foreground shadow-neu-raised"
                    >
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <CheckCircle2 className="h-6 w-6 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">
              {(result && REASON_MESSAGE[result.reason]) ||
                "No había nada nuevo que guardar en el expediente."}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
