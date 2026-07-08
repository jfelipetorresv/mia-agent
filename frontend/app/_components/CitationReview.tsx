"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Landmark, ScrollText } from "lucide-react";
import { apiGet } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// Tipos del informe de verificación de citas (CP9 backend). `fuente` solo viene
// en citas respaldadas — nunca se inventa un respaldo que no exista.
export type Fuente = { tipo: string; referencia: string; titulo: string };
export type CitaDetalle = {
  cita: string;
  estado: "marcada" | "respaldada" | "anotada";
  fuente?: Fuente;
};
export type Verification = {
  citas: number;
  marcadas: number;
  respaldadas: number;
  anotadas: number;
  detalle: CitaDetalle[];
};

// Respuesta de GET /api/sources/buscar — puede venir vacía (corpus aún pequeño).
type FuenteBuscada = {
  tipo: "norma" | "providencia";
  referencia: string;
  titulo: string;
  extracto: string;
  organo: string | null;
  fecha: string | null;
  radicado?: string | null;
  magistrado_ponente?: string | null;
};

const ESTADO_INFO: Record<
  CitaDetalle["estado"],
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  respaldada: { label: "Con respaldo", icon: CheckCircle2, className: "text-success" },
  marcada: { label: "Verifícala tú", icon: AlertTriangle, className: "text-warning" },
  anotada: { label: "Sin respaldo — verifícala tú", icon: AlertTriangle, className: "text-warning" },
};

function plural(n: number, singular: string, pluralForm: string): string {
  return n === 1 ? singular : pluralForm;
}

// Resumen legible de la revisión de citas, sin porcentajes fríos (método Lexia).
function resumenTexto(v: Verification): string {
  if (v.citas === 0) return "Mia no encontró citas de normas o sentencias en este borrador.";
  const porVerificar = v.marcadas + v.anotadas;
  const citasTxt = plural(v.citas, "1 cita", `${v.citas} citas`);
  if (porVerificar === 0) {
    return `Mia revisó ${citasTxt}: todas con respaldo en sus fuentes.`;
  }
  if (v.respaldadas === 0) {
    return `Mia revisó ${citasTxt}: todas para tu verificación.`;
  }
  const respaldoTxt = plural(v.respaldadas, "1 con respaldo", `${v.respaldadas} con respaldo`);
  const verificarTxt = plural(porVerificar, "1 para tu verificación", `${porVerificar} para tu verificación`);
  return `Mia revisó ${citasTxt}: ${respaldoTxt} en sus fuentes, ${verificarTxt}.`;
}

export default function CitationReview({ verification }: { verification: Verification }) {
  const [openCita, setOpenCita] = useState<CitaDetalle | null>(null);

  return (
    <TooltipProvider>
      <div>
        <p className="text-sm text-muted-foreground">{resumenTexto(verification)}</p>
        {verification.detalle.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {verification.detalle.map((d, i) => {
              const info = ESTADO_INFO[d.estado] || ESTADO_INFO.marcada;
              const Icon = info.icon;
              return (
                <li
                  key={i}
                  className="animate-slide-up"
                  style={{ animationDelay: `${i * 40}ms`, animationFillMode: "backwards" }}
                >
                  <button
                    type="button"
                    onClick={() => setOpenCita(d)}
                    className="flex w-full items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5 text-left transition-colors hover:bg-accent/60"
                  >
                    <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", info.className)} />
                    <div className="min-w-0 flex-1">
                      <p className="break-words font-serif text-sm">{d.cita}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className={cn("text-xs font-medium", info.className)}>{info.label}</span>
                        {d.fuente ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs text-success">
                                {d.fuente.referencia}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>{d.fuente.titulo}</TooltipContent>
                          </Tooltip>
                        ) : null}
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
      <CitationSourceDialog cita={openCita} onClose={() => setOpenCita(null)} />
    </TooltipProvider>
  );
}

function CitationSourceDialog({ cita, onClose }: { cita: CitaDetalle | null; onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [fuentes, setFuentes] = useState<FuenteBuscada[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!cita) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setFuentes(null);
    apiGet<{ fuentes: FuenteBuscada[] }>(`/api/sources/buscar?q=${encodeURIComponent(cita.cita)}`)
      .then((res) => {
        if (!cancelled) setFuentes(res.fuentes || []);
      })
      .catch(() => {
        if (!cancelled) setError("No pude consultar las fuentes en este momento. Intenta de nuevo.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cita]);

  return (
    <Dialog open={cita !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Fuente de la cita</DialogTitle>
          <DialogDescription className="font-serif text-sm leading-relaxed text-foreground">
            {cita?.cita}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[55vh] space-y-3 overflow-auto">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : error ? (
            <p className="flex items-start gap-2 text-sm text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </p>
          ) : fuentes && fuentes.length > 0 ? (
            fuentes.map((f, i) => (
              <div key={i} className="rounded-lg border border-border p-3">
                <div className="flex items-center gap-1.5 text-sm font-semibold">
                  {f.tipo === "providencia" ? (
                    <Landmark className="h-3.5 w-3.5 shrink-0 text-primary" />
                  ) : (
                    <ScrollText className="h-3.5 w-3.5 shrink-0 text-primary" />
                  )}
                  {f.referencia}
                </div>
                <div className="text-xs text-muted-foreground">{f.titulo}</div>
                {f.organo || f.fecha ? (
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {[f.organo, f.fecha].filter(Boolean).join(" · ")}
                  </div>
                ) : null}
                {f.tipo === "providencia" && (f.radicado || f.magistrado_ponente) ? (
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {[f.radicado ? `Radicado ${f.radicado}` : null, f.magistrado_ponente ? `M.P. ${f.magistrado_ponente}` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                ) : null}
                <p className="mt-2 rounded-lg bg-muted/50 p-4 font-serif text-sm leading-relaxed">{f.extracto}</p>
              </div>
            ))
          ) : (
            <p className="flex items-start gap-2 text-sm text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              Esta cita no está todavía en las fuentes de Mia. Verifícala en la fuente oficial antes de usarla.
            </p>
          )}
        </div>
        <p className="text-xs text-muted-foreground/80">
          Mia propone; tú verificas la fuente oficial antes de radicar.
        </p>
      </DialogContent>
    </Dialog>
  );
}
