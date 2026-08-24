"use client";

// "Arrancar el día" · resumen priorizado del asunto (GET /api/matters/{id}/daily).
// §G: nada de jerga. El abogado abre el asunto y ve, arriba y marcado, lo que
// REQUIERE su decisión (decisiones abiertas del cierre anterior + bandeja sin
// clasificar); abajo, lo informativo (bitácora reciente). Componente
// autocontenido: carga su propia lista al abrirse. Fail-soft — el backend nunca
// responde 500 por leer disco, así que aquí solo distinguimos "vacío" de "error".

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Sunrise } from "lucide-react";
import { ApiError, apiGet } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type DailyItem = {
  ref: string;
  requiere_decision: boolean;
  origen: "pendiente" | "bandeja" | "bitacora" | string;
  texto: string;
};

type DailyBriefing = {
  matter_id: string;
  items: DailyItem[];
  requieren_decision: number;
  resumen: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  matterId: string;
};

// Etiqueta en llano del origen de cada punto (§G: el abogado no ve "inbox" ni
// "HANDOFF"). El nombre interno del origen se mapea a algo humano.
const ORIGEN_LABEL: Record<string, string> = {
  pendiente: "Pendiente de tu decisión",
  bandeja: "En la bandeja",
  bitacora: "Del diario del caso",
};

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

export default function DiarioDialog({ open, onOpenChange, matterId }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setBriefing(null);
    apiGet<DailyBriefing>(`/api/matters/${matterId}/daily`)
      .then((res) => {
        if (cancelled) return;
        setBriefing(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(apiMessage(err, "No pude preparar el resumen del día. Intenta de nuevo."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, matterId]);

  const requieren = briefing?.items.filter((it) => it.requiere_decision) ?? [];
  const informativos = briefing?.items.filter((it) => !it.requiere_decision) ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sunrise className="h-5 w-5 text-primary" />
            Arrancar el día
          </DialogTitle>
          <DialogDescription>
            Lo que Mia dejó apuntado en este caso. Lo que necesita tu decisión va arriba.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Preparando tu resumen…
          </div>
        ) : error ? (
          <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{error}</p>
          </div>
        ) : briefing && briefing.items.length > 0 ? (
          <div className="max-h-[60vh] space-y-5 overflow-y-auto pr-1">
            <p className="text-sm text-muted-foreground">{briefing.resumen}</p>

            {requieren.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-primary/80">
                  Requiere tu decisión
                </h4>
                {requieren.map((it) => (
                  <DailyRow key={it.ref} item={it} highlight />
                ))}
              </div>
            ) : null}

            {informativos.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Para tu información
                </h4>
                {informativos.map((it) => (
                  <DailyRow key={it.ref} item={it} />
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <CheckCircle2 className="h-6 w-6 text-success" />
            <p className="text-sm text-muted-foreground">
              {briefing?.resumen || "Sin novedades en el expediente: nada pendiente de tu decisión hoy."}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DailyRow({ item, highlight = false }: { item: DailyItem; highlight?: boolean }) {
  const origen = ORIGEN_LABEL[item.origen] || "";
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2.5 shadow-neu-raised",
        highlight ? "border-primary/30 bg-primary/5" : "border-border/10 bg-card",
      )}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 text-xs font-semibold text-muted-foreground">{item.ref}</span>
        <div className="min-w-0 flex-1">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-card-foreground">{item.texto}</p>
          {origen ? (
            <p className={cn("mt-1 text-xs", highlight ? "text-primary/80" : "text-muted-foreground")}>{origen}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
