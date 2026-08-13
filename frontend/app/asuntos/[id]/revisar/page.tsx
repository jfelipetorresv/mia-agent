"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, Pencil, X } from "lucide-react";
import { apiDownload, apiGet, streamPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
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
import CitationReview, { type Verification } from "../../../_components/CitationReview";
import { depositarAvisoDeCosto } from "../../../_components/AvisoDeCosto";
import { renderInline } from "@/components/MiaMarkdown";
import { PageShell } from "@/app/_components/PageShell";
import { cardVariants } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type DraftResponse = { draft: string; verification?: Verification | null };

// El resaltado de [VERIFICAR…] —la señal de "esto lo confirmas tú"— vive en
// MiaMarkdown y es el MISMO en todo el producto: borrador, sala de estrategia y
// conversación. No duplicar aquí: si diverge, el gate de citas se rompe visualmente.
function renderDraft(text: string) {
  return renderInline(text, "draft");
}

// El abogado debe verificar TODA cita con la marca [VERIFICAR] en el borrador
// final: las que el redactor ya marcó (marcadas) MÁS las que el verificador
// añadió por no tener respaldo (anotadas). Contar solo `marcadas` subreporta el
// riesgo que este informe existe para evitar (CP9). El resumen y la lista de
// citas los renderiza el componente compartido CitationReview (Fase 1b).
function VerificationReport({ v }: { v: Verification }) {
  const porVerificar = v.marcadas + v.anotadas;

  return (
    // `mt-section` (3rem) y no `mt-4`: la revisión de citas es una SECCIÓN
    // distinta del borrador, no un pie del mismo bloque. Pegada a 16 px se leía
    // como parte del texto que el abogado acaba de leer — justo en la pantalla
    // donde tiene que separar "lo que Mia escribió" de "lo que falta verificar".
    <section
      aria-label="Revisión de citas"
      className={`mt-section rounded-lg border px-5 py-4 ${
        porVerificar > 0 ? "border-warning/30 bg-warning/5" : "border-border bg-card/60"
      }`}
    >
      <CitationReview verification={v} />
    </section>
  );
}

// Detonadores de escalamiento (Fase 1c): Mia NUNCA calcula términos ni plazos
// procesales, prescripción/caducidad ni cuantías — solo puede SEÑALAR que el
// borrador los menciona para que el abogado los confirme antes de aprobar.
type DetonadorCategoria = "plazos" | "prescripcion" | "cuantia";

// Los patrones cubren conjugaciones frecuentes por raíz (venc-, prescrib-,
// prescrit-, caduc-): "vence el 5 de marzo" o "el término caducó" también deben
// disparar la señal. Falsos negativos residuales son aceptables (señalización
// best-effort); falsos positivos solo cuestan un aviso de más.
// "plazos" y "prescripcion" ya son neutrales de jurisdicción (ningún término
// es exclusivo de un país). "cuantia" sí lo era: SMLMV/SMMLV es la sigla
// colombiana del salario mínimo. Se mantiene (sigue siendo válida para un
// despacho colombiano) pero se suma UMA (México), IPREM/SMI (España) y
// "unidad(es) tributaria(s)" (UVT, UIT y equivalentes en otras jurisdicciones)
// para que un despacho no colombiano no pierda la señal solo porque su unidad
// de referencia tiene otro nombre — un falso negativo aquí (el detonador NO
// dispara cuando debía) es el riesgo grave, así que se prefiere sumar
// variantes a recortarlas.
const DETONADOR_REGEX: Record<DetonadorCategoria, RegExp> = {
  plazos: /\b(plazos?|t[ée]rminos? (de|para)|d[íi]as (h[áa]biles|calendario)|venc\w+|dentro de los?\s+\d+)\b/i,
  prescripcion: /\b(prescripci[óo]n|prescrib\w+|prescrit\w+|caduc\w+)\b/i,
  cuantia:
    /\b(cuant[íi]as?|salarios? m[íi]nimos?|SMLMV|SMMLV|UVT|UIT|UMA|IPREM|SMI|unidad(?:es)? (?:tributarias?|de valor tributario))\b|[$€]\s?[\d][\d.,]*/i,
};

const DETONADOR_LABEL: Record<DetonadorCategoria, string> = {
  plazos: "Plazos o términos",
  prescripcion: "Prescripción o caducidad",
  cuantia: "Cuantía o montos",
};

function detectarDetonadores(text: string): DetonadorCategoria[] {
  return (Object.keys(DETONADOR_REGEX) as DetonadorCategoria[]).filter((cat) =>
    DETONADOR_REGEX[cat].test(text),
  );
}

function EscalamientoBanner({ categorias }: { categorias: DetonadorCategoria[] }) {
  if (categorias.length === 0) return null;
  return (
    <div
      role="note"
      aria-label="Requiere tu decisión antes de aprobar"
      className="mb-block flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/5 px-5 py-4 animate-slide-up"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
      <div>
        <p className="text-section text-warning">Requiere tu decisión antes de aprobar</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {categorias.map((cat) => (
            <Badge key={cat} variant="warning">
              {DETONADOR_LABEL[cat]}
            </Badge>
          ))}
        </div>
        <p className="mt-2 text-body text-muted-foreground">
          Mia no calcula términos ni plazos: los datos procesales los confirmas tú antes de presentar.
        </p>
      </div>
    </div>
  );
}

// Texto singular/plural del checkbox del gate de citas (§G: nada de "N=1 citas").
function textoConfirmacionCitas(n: number): string {
  return n === 1
    ? "Verifiqué la cita marcada en el borrador"
    : `Verifiqué las ${n} citas marcadas en el borrador`;
}

// Aprobar/rechazar responden con un flujo de eventos (el mismo canal del turno),
// no con JSON: hay que consumirlo con streamPost y decidir por el evento final.
// El backend emite "done" al terminar bien y "error" (en llano) si algo falló.
async function resumeDraft(path: string, body: unknown): Promise<void> {
  let ok = false;
  let errMsg = "";
  await streamPost(path, body, (event, data) => {
    if (event === "done") ok = true;
    else if (event === "aviso_de_costo") {
      // Cerrar el borrador también razona y puede acabar en crédito de pago. Esta
      // pantalla vuelve al asunto enseguida, así que el aviso viaja con el abogado.
      const d = (data || {}) as { message?: string; sugerencia?: string; veces?: number };
      if (d.message) {
        depositarAvisoDeCosto({ message: d.message, sugerencia: d.sugerencia, veces: d.veces });
      }
    } else if (event === "error") {
      const d = data as { message?: string } | string | null;
      errMsg = typeof d === "string" ? d : d?.message || "";
    }
  });
  if (!ok) throw new Error(errMsg || "La operación no terminó bien.");
}

export default function RevisarPage({ params }: { params: Promise<{ id: string }> }) {
  const matterId = use(params).id;
  const router = useRouter();
  const [draft, setDraft] = useState<string | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState("");
  const [citasVerificadas, setCitasVerificadas] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectBusy, setRejectBusy] = useState(false);
  const [rejectError, setRejectError] = useState("");
  const [showCelebration, setShowCelebration] = useState(false);

  useEffect(() => {
    apiGet<DraftResponse>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        setDraft(d.draft);
        setText(d.draft);
        setVerification(d.verification || null);
      })
      .catch(() => {
        router.push(`/asuntos/${matterId}?sin_borrador=true`);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  // Escaneo de detonadores: se hace sobre el borrador ORIGINAL de Mia, no sobre
  // lo que el abogado vaya editando — la alerta es sobre lo que Mia propuso.
  const detonadores = useMemo(() => detectarDetonadores(draft ?? ""), [draft]);

  // Number(...) || 0 blinda contra metadatos malformados: un NaN silencioso
  // desactivaría el gate justo cuando más se necesita (fail-closed, no fail-open).
  const porVerificar = verification
    ? (Number(verification.marcadas) || 0) + (Number(verification.anotadas) || 0)
    : 0;
  const gateCitasPendiente = porVerificar > 0 && !citasVerificadas;
  // Si el abogado borró todo el texto, "aprobar" no significa nada: el backend
  // ignoraría el texto vacío y aprobaría la propuesta ORIGINAL en silencio —
  // divergencia entre lo que se ve y lo que se aprueba. Se bloquea con aviso.
  const versionVacia = text.trim() === "" && text !== draft;

  // La celebración navega con un setTimeout: si el abogado sale de la pantalla
  // antes de que dispare, hay que limpiarlo para no navegar tras el desmontaje.
  const celebrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
    };
  }, []);

  async function approve() {
    if (busy || gateCitasPendiente || versionVacia) return; // anti doble-clic y gate
    setBusy(true);
    setActionMsg("");
    try {
      await resumeDraft(
        `/api/matters/${matterId}/draft/approve`,
        text !== draft ? { edited_text: text } : {},
      );
      // Micro-celebración (Fase 1c): un respiro breve antes de volver al asunto,
      // reforzando que la decisión fue del abogado y que Mia aprende de ella.
      setShowCelebration(true);
      celebrationTimer.current = setTimeout(() => {
        router.push(`/asuntos/${matterId}?confirmed=true`);
      }, 900);
    } catch {
      setBusy(false);
      setActionMsg("No se pudo confirmar el borrador. Intenta de nuevo.");
    }
  }

  async function submitReject() {
    if (rejectBusy) return; // anti doble-clic
    setRejectBusy(true);
    setRejectError("");
    try {
      await resumeDraft(`/api/matters/${matterId}/draft/reject`, { reason: rejectReason });
      router.push(`/asuntos/${matterId}?confirmed=true`);
    } catch {
      setRejectBusy(false);
      setRejectError("No se pudo rechazar el borrador. Intenta de nuevo.");
    }
  }

  async function downloadWord() {
    setDownloadMsg("");
    setDownloading(true);
    try {
      await apiDownload(`/api/matters/${matterId}/draft.docx`, "borrador.docx");
    } catch {
      setDownloadMsg("No se pudo descargar el documento. Intenta de nuevo.");
    } finally {
      setDownloading(false);
    }
  }

  if (draft === null) {
    return (
      // Mismo contenedor y mismo padding que el resto del producto: esta era la
      // única pantalla con `px-8 py-10` mientras las demás usaban
      // `px-6 py-10 md:px-8`, así que al entrar a revisar el borrador el
      // contenido saltaba de sitio.
      <PageShell className="space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-[50vh] w-full rounded-lg" />
      </PageShell>
    );
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-aurora">
      <div className="flex items-end justify-between gap-3 border-b border-border bg-background/80 px-6 py-4 backdrop-blur md:px-8">
        <div className="animate-slide-up">
          <button
            onClick={() => router.push(`/asuntos/${matterId}`)}
            className="flex items-center gap-1 text-meta text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" />
            Volver al asunto
          </button>
          <h1 className="mt-1 text-title">Revisar borrador</h1>
        </div>
        <div className="text-right">
          <Button variant="outline" onClick={downloadWord} disabled={downloading} className="gap-2">
            <Download className="h-4 w-4" />
            {downloading ? "Preparando…" : "Descargar en Word"}
          </Button>
          {downloadMsg ? (
            <p role="alert" className="mt-1 text-meta text-warning">{downloadMsg}</p>
          ) : null}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-6 py-10 md:px-8">
        <div className="mx-auto max-w-3xl animate-slide-up" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
          <EscalamientoBanner categorias={detonadores} />
          {editing ? (
            <div className="grid gap-block md:grid-cols-2">
              <div>
                <p className="mb-2 text-label text-muted-foreground">Propuesta de Mia</p>
                {/* `text-body` (15/24 en Newsreader) en vez del `text-[16px]`
                    suelto que había: es el rol de lectura del sistema y el
                    borrador es LA superficie de lectura sostenida del producto. */}
                <div
                  className={cn(
                    cardVariants(),
                    "max-h-[60vh] overflow-auto whitespace-pre-wrap p-6 font-serif text-body leading-relaxed",
                  )}
                >
                  {renderDraft(draft)}
                </div>
              </div>
              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-label text-muted-foreground">Tu versión</p>
                  {text !== draft ? (
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-accent px-2 py-0.5 text-meta text-muted-foreground">
                        Editaste el borrador
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setText(draft)}
                        className="h-7 px-2 text-meta"
                      >
                        Restaurar propuesta de Mia
                      </Button>
                    </div>
                  ) : null}
                </div>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  aria-label="Tu versión del borrador"
                  className="h-[60vh] w-full rounded-lg border border-input bg-card p-6 font-serif text-body leading-relaxed outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
            </div>
          ) : (
            <div className={cn(cardVariants(), "whitespace-pre-wrap p-8 font-serif text-body leading-relaxed")}>
              {renderDraft(text)}
            </div>
          )}
          {verification ? <VerificationReport v={verification} /> : null}
        </div>
      </div>

      <div className="border-t border-border bg-background/80 px-6 py-4 backdrop-blur md:px-8">
        {actionMsg ? (
          <p role="alert" className="mb-2 text-center text-body text-warning animate-fade-in">{actionMsg}</p>
        ) : null}
        {porVerificar > 0 ? (
          <div className="mb-3 flex items-center justify-center gap-2">
            <input
              type="checkbox"
              id="citas-verificadas"
              checked={citasVerificadas}
              onChange={(e) => setCitasVerificadas(e.target.checked)}
              className="h-4 w-4 shrink-0 rounded border-input text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <Label htmlFor="citas-verificadas" className="cursor-pointer font-normal">
              {textoConfirmacionCitas(porVerificar)}
            </Label>
          </div>
        ) : null}
        <div className="flex flex-wrap justify-center gap-3">
          <Button
            variant="cta"
            size="lg"
            onClick={approve}
            disabled={busy || gateCitasPendiente || versionVacia}
            className="gap-2"
          >
            <Check className="h-4 w-4" />
            Aprobar
          </Button>
          <Button
            variant="outline"
            size="lg"
            onClick={() => setEditing((v) => !v)}
            disabled={busy}
            className="gap-2"
          >
            <Pencil className="h-4 w-4" />
            {editing ? "Listo" : "Editar"}
          </Button>
          <Button
            variant="ghost"
            size="lg"
            onClick={() => setRejectOpen(true)}
            disabled={busy}
            className="gap-2 text-muted-foreground hover:text-destructive"
          >
            <X className="h-4 w-4" />
            Rechazar
          </Button>
        </div>
        {gateCitasPendiente ? (
          <p className="mt-2 text-center text-meta text-muted-foreground">
            Confirma primero que verificaste las citas marcadas.
          </p>
        ) : null}
        {versionVacia ? (
          <p className="mt-2 text-center text-meta text-warning">
            Tu versión está vacía — escribe el texto o restaura la propuesta de Mia antes de aprobar.
          </p>
        ) : null}
        {/* SIN modificador de opacidad. Antes era `text-muted-foreground/80`, que
            hundía el contraste por debajo de WCAG AA justo en el aviso de
            responsabilidad de la pantalla donde el abogado aprueba: el texto que
            menos se puede permitir ser ilegible era el peor de leer. */}
        <p className="mt-2 text-center text-meta text-muted-foreground">
          Tú tienes la última palabra: nada se envía ni se aplica sin tu aprobación.
        </p>
      </div>

      <Dialog
        open={rejectOpen}
        onOpenChange={(open) => {
          if (rejectBusy) return;
          setRejectOpen(open);
          if (!open) {
            setRejectReason("");
            setRejectError("");
          }
        }}
      >
        <DialogContent aria-label="Rechazar borrador">
          <DialogHeader>
            <DialogTitle>¿Qué debe cambiar?</DialogTitle>
            <DialogDescription>
              Cuéntale a Mia qué no te convence de este borrador — lo tendrá en cuenta para el siguiente intento.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Por ejemplo: el tono es muy agresivo, falta la excepción de prescripción…"
            aria-label="Qué debe cambiar en el borrador (opcional)"
            className="min-h-[110px]"
          />
          {rejectError ? (
            <p role="alert" className="text-body text-warning">{rejectError}</p>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectOpen(false)} disabled={rejectBusy}>
              Cancelar
            </Button>
            <Button
              variant="outline"
              onClick={submitReject}
              disabled={rejectBusy}
              className="text-destructive"
            >
              {rejectBusy ? "Enviando…" : "Rechazar y pedir uno nuevo"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {showCelebration ? (
        <div
          role="status"
          aria-label="Borrador aprobado"
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-background/90 backdrop-blur animate-fade-in"
        >
          <CheckCircle2 className="h-16 w-16 text-success" />
          <p className="text-title">Borrador aprobado</p>
          <p className="text-body text-muted-foreground">Mia aprende de cada decisión tuya.</p>
        </div>
      ) : null}
    </div>
  );
}
