"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Ban, CheckCircle2, Landmark, ScrollText } from "lucide-react";
import { apiGet, apiSend, plainMessage } from "@/lib/api";
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
  // "quemada": el despacho marcó antes esta cita como falsa, así que Mia la retiró del texto
  // en vez de emitirla (el muro del banco de citas falsas).
  estado: "marcada" | "respaldada" | "anotada" | "quemada" | "omitida";
  fuente?: Fuente;
};
export type Verification = {
  citas: number;
  marcadas: number;
  respaldadas: number;
  anotadas: number;
  detalle: CitaDetalle[];
  // Presentes solo cuando el despacho tiene citas marcadas como falsas.
  quemadas?: number;
  aviso_quemadas?: string;
  // Citas retiradas del texto por falta de ordenamiento declarado (modo genérico).
  omitidas?: number;
  // Afirmaciones negativas sobre un documento que el texto COMPLETO de ese documento podría
  // contradecir («el informe no menciona al garante», y el documento lo nombra cuatro veces).
  afirmaciones_negativas?: {
    n_afirmaciones: number;
    n_a_revisar: number;
    revisar?: { oracion: string; doc: number; archivo: string; terminos_no_vistos: string[] }[];
  };
  // Partes que, según las fichas del despacho, pertenecen a OTRO expediente.
  contaminacion_expediente?: {
    n_partes_ajenas: number;
    partes?: { parte: string; ocurrencias: number }[];
  };
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
  quemada: { label: "Retirada: la marcaste como falsa", icon: Ban, className: "text-destructive" },
  omitida: { label: "Omitida: falta declarar el ordenamiento", icon: AlertTriangle, className: "text-warning" },
};

function plural(n: number, singular: string, pluralForm: string): string {
  return n === 1 ? singular : pluralForm;
}

// Resumen legible de la revisión de citas, sin porcentajes fríos (método Lexia).
//
// El resumen cuenta las TRES suertes que puede correr una cita, no dos. Las retiradas del
// texto —omitidas por falta de ordenamiento declarado, o quemadas porque el despacho las
// marcó como falsas— no son ni respaldadas ni pendientes de verificar. Cuando solo se
// contaban dos, un borrador cuya única cita se había OMITIDO se resumía como «todas con
// respaldo en sus fuentes»: exactamente lo contrario de lo ocurrido, y en la línea que el
// abogado lee primero. Se vio mirando la pantalla, no leyendo el código.
function resumenTexto(v: Verification): string {
  if (v.citas === 0) return "Mia no encontró citas de normas o sentencias en este borrador.";
  const porVerificar = v.marcadas + v.anotadas;
  const retiradas = (v.omitidas || 0) + (v.quemadas || 0);
  const citasTxt = plural(v.citas, "1 cita", `${v.citas} citas`);
  if (v.respaldadas === v.citas) {
    return `Mia revisó ${citasTxt}: todas con respaldo en sus fuentes.`;
  }
  if (porVerificar === v.citas) {
    return `Mia revisó ${citasTxt}: todas para tu verificación.`;
  }
  if (retiradas === v.citas) {
    return plural(v.citas,
      "Mia revisó 1 cita y la retiró del texto.",
      `Mia revisó ${v.citas} citas y las retiró del texto.`);
  }
  const partes: string[] = [];
  if (v.respaldadas > 0) {
    partes.push(plural(v.respaldadas,
      "1 con respaldo en sus fuentes", `${v.respaldadas} con respaldo en sus fuentes`));
  }
  if (porVerificar > 0) {
    partes.push(plural(porVerificar,
      "1 para tu verificación", `${porVerificar} para tu verificación`));
  }
  if (retiradas > 0) {
    partes.push(plural(retiradas,
      "1 retirada del texto", `${retiradas} retiradas del texto`));
  }
  return `Mia revisó ${citasTxt}: ${partes.join(", ")}.`;
}

export default function CitationReview({ verification }: { verification: Verification }) {
  const [openCita, setOpenCita] = useState<CitaDetalle | null>(null);

  return (
    <TooltipProvider>
      <div>
        <p className="text-sm text-muted-foreground">{resumenTexto(verification)}</p>
        {verification.quemadas ? (
          <p className="mt-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {verification.quemadas === 1
                ? "Retiré 1 cita que marcaste como falsa."
                : `Retiré ${verification.quemadas} citas que marcaste como falsas.`}{" "}
              No las vuelvo a usar, aunque una fuente parezca respaldarlas.
            </span>
          </p>
        ) : null}
        <AvisosDeRevision verification={verification} />
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

// Dos avisos que Mia levanta sola al revisar su propio borrador. Son AVISOS: no frenan nada y no
// cambian el texto — quien decide es el abogado. Se muestran solo cuando hay algo que decir.
function AvisosDeRevision({ verification }: { verification: Verification }) {
  const neg = verification.afirmaciones_negativas;
  const cruce = verification.contaminacion_expediente;
  const hayNeg = Boolean(neg && neg.n_a_revisar > 0);
  const hayCruce = Boolean(cruce && cruce.n_partes_ajenas > 0);
  if (!hayNeg && !hayCruce) return null;

  return (
    <div className="mt-2 space-y-2">
      {hayNeg && neg ? (
        <div className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs">
          <p className="flex items-start gap-2 font-medium text-warning">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {neg.n_a_revisar === 1
              ? "Hay 1 afirmación de que un documento NO dice algo, y el documento completo podría contradecirla."
              : `Hay ${neg.n_a_revisar} afirmaciones de que un documento NO dice algo, y el documento completo podría contradecirlas.`}
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {(neg.revisar || []).map((r, i) => (
              <li key={i} className="text-muted-foreground">
                <span className="font-serif text-foreground">“{r.oracion}”</span>
                <br />
                {r.archivo ? <>En {r.archivo}: </> : null}
                aparece {r.terminos_no_vistos.join(", ")} en partes del documento que no llegué a
                leer.
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-muted-foreground/80">
            Vale la pena revisarlo: una negativa que se cae con una sola página arrastra el resto
            del escrito.
          </p>
        </div>
      ) : null}
      {hayCruce && cruce ? (
        <div className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs">
          <p className="flex items-start gap-2 font-medium text-warning">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            El escrito nombra{" "}
            {cruce.n_partes_ajenas === 1 ? "una parte" : `${cruce.n_partes_ajenas} partes`} de otro
            expediente
          </p>
          <p className="mt-1 text-muted-foreground">
            {(cruce.partes || []).map((p) => p.parte).join(" · ")}
          </p>
          <p className="mt-1.5 text-muted-foreground/80">
            Puede ser legítimo, o puede ser material de otro caso. Revísalo antes de radicar.
          </p>
        </div>
      ) : null}
    </div>
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
        {cita ? <MarcarCitaFalsa cita={cita.cita} yaRetirada={cita.estado === "quemada"} /> : null}
        <p className="text-xs text-muted-foreground/80">
          Mia propone; tú verificas la fuente oficial antes de radicar.
        </p>
      </DialogContent>
    </Dialog>
  );
}

// El abogado encontró una cita que NO existe, o que no dice lo que se le atribuye. Al marcarla,
// entra al banco de citas falsas del despacho y Mia no la vuelve a emitir — ni aunque una fuente
// parezca respaldarla. Es la única decisión de esta pantalla que cambia el comportamiento futuro,
// así que pide confirmación y explica el alcance antes de hacerla.
function MarcarCitaFalsa({ cita, yaRetirada }: { cita: string; yaRetirada: boolean }) {
  const [abierto, setAbierto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [hecho, setHecho] = useState("");
  const [error, setError] = useState("");

  // Al cambiar de cita, el formulario vuelve a cero: un motivo escrito para una cita no puede
  // quedarse pegado en la siguiente.
  useEffect(() => {
    setAbierto(false);
    setMotivo("");
    setHecho("");
    setError("");
  }, [cita]);

  async function marcar() {
    setEnviando(true);
    setError("");
    try {
      const r = await apiSend<{ mensaje?: string }>("POST", "/api/citas-quemadas", {
        cita,
        motivo: motivo.trim(),
      });
      setHecho(r?.mensaje || "Marcada. No la volveré a usar en este despacho.");
      setAbierto(false);
    } catch (e) {
      setError(plainMessage(e, "No pude marcar la cita en este momento. Intenta de nuevo."));
    } finally {
      setEnviando(false);
    }
  }

  if (hecho) {
    return (
      <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {hecho}
      </p>
    );
  }

  if (yaRetirada) {
    return (
      <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Ya marcaste esta cita como falsa, así que la retiré del borrador.
      </p>
    );
  }

  if (!abierto) {
    return (
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className="text-xs font-medium text-destructive underline-offset-2 hover:underline"
        >
          Esta cita no existe o no dice eso
        </button>
        {error ? <p className="text-xs text-warning">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
      <p className="text-xs text-foreground">
        La marcaré como falsa y no la volveré a usar en este despacho, ni aunque una fuente parezca
        respaldarla. Puedes reactivarla después si te corriges.
      </p>
      <textarea
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        rows={2}
        placeholder="¿Qué está mal? (opcional — por ejemplo: la sentencia real trata otro tema)"
        className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={marcar}
          disabled={enviando}
          className="rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground disabled:opacity-60"
        >
          {enviando ? "Marcando…" : "Marcar como falsa"}
        </button>
        <button
          type="button"
          onClick={() => setAbierto(false)}
          disabled={enviando}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Cancelar
        </button>
      </div>
      {error ? <p className="text-xs text-warning">{error}</p> : null}
    </div>
  );
}
