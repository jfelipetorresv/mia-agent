"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, Globe2, Pencil, X } from "lucide-react";
import { apiDownload, apiGet, plainMessage, streamPost } from "@/lib/api";
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
import { COUNTRY_NAME_BY_CODE } from "@/app/_components/CountrySelector";

type Argumento = {
  id?: string;
  tesis?: string;
  seleccionado?: boolean;
  fuente_refs?: string[];
  contraparte?: string;
  prueba?: string;
};

type Descarte = {
  tesis?: string;
  motivo?: string;
};

type DraftResponse = {
  draft: string;
  verification?: Verification | null;
  draft_hash: string;
  final_ready: boolean;
  final_status?: string;
  argumentos?: Argumento[] | null;
  descartes?: Descarte[] | null;
  argument_selection?: { include?: string[]; exclude?: string[] } | Record<string, boolean> | null;
};

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
type LearningReceipt = {
  decision_saved?: boolean;
  learning?: { status?: "queued" | "partially_queued" | "blocked" | "completed" | "needs_attention" | "not_applicable" };
  final_ready?: boolean;
  final_status?: string;
};

async function resumeDraft(path: string, body: unknown): Promise<LearningReceipt> {
  let ok = false;
  let errMsg = "";
  let receipt: LearningReceipt = {};
  await streamPost(path, body, (event, data) => {
    if (event === "done") {
      ok = true;
      receipt = (data || {}) as LearningReceipt;
    }
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
  return receipt;
}

function initialSelection(
  argumentos: Argumento[] | null | undefined,
  saved: DraftResponse["argument_selection"],
): Record<string, boolean> {
  const flags: Record<string, boolean> = {};
  for (const arg of argumentos || []) {
    if (!arg.id) continue;
    flags[arg.id] = arg.seleccionado !== false;
  }
  if (saved && typeof saved === "object") {
    const include = "include" in saved ? (saved as { include?: unknown }).include : undefined;
    const exclude = "exclude" in saved ? (saved as { exclude?: unknown }).exclude : undefined;
    if (Array.isArray(include) || Array.isArray(exclude)) {
      for (const id of (Array.isArray(include) ? include : [])) {
        if (typeof id === "string") flags[id] = true;
      }
      for (const id of (Array.isArray(exclude) ? exclude : [])) {
        if (typeof id === "string") flags[id] = false;
      }
    } else {
      for (const [id, on] of Object.entries(saved as Record<string, boolean>)) {
        flags[id] = Boolean(on);
      }
    }
  }
  return flags;
}

function ArgumentMatrix({
  argumentos,
  descartes,
  selected,
  onToggle,
}: {
  argumentos: Argumento[];
  descartes: Descarte[];
  selected: Record<string, boolean>;
  onToggle: (id: string) => void;
}) {
  return (
    <section
      aria-label="Matriz de argumentos"
      className="mb-block rounded-lg border border-border bg-card/60 px-5 py-4"
    >
      <p className="text-section">Argumentos de este escrito</p>
      <p className="mt-1 text-meta text-muted-foreground">
        Marca los que deben entrar al borrador. Un cambio pide una sola reescritura
        de los seleccionados y vuelve a esta revisión; no relanza el ciclo automático
        de calidad.
      </p>
      <ul className="mt-3 space-y-2">
        {argumentos.map((arg) => {
          if (!arg.id) return null;
          const on = selected[arg.id] !== false;
          return (
            <li key={arg.id} className="flex items-start gap-2">
              <input
                type="checkbox"
                id={`arg-${arg.id}`}
                checked={on}
                onChange={() => onToggle(arg.id as string)}
                className="mt-1 h-4 w-4 shrink-0 rounded border-input text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <Label htmlFor={`arg-${arg.id}`} className="cursor-pointer font-normal">
                <span className="text-meta text-muted-foreground">{arg.id}</span>
                {" — "}
                {arg.tesis || "Tesis sin texto"}
              </Label>
            </li>
          );
        })}
      </ul>
      {descartes.length > 0 ? (
        <div className="mt-4 border-t border-border pt-3">
          <p className="text-label text-muted-foreground">Descartes (no se desarrollan)</p>
          <ul className="mt-2 space-y-1 text-body text-muted-foreground">
            {descartes.map((d, i) => (
              <li key={`${d.tesis || "d"}-${i}`}>
                {d.tesis}
                {d.motivo ? ` — ${d.motivo}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default function RevisarPage({ params }: { params: Promise<{ id: string }> }) {
  const matterId = use(params).id;
  const router = useRouter();
  const [draft, setDraft] = useState<string | null>(null);
  const [draftHash, setDraftHash] = useState("");
  const [finalReady, setFinalReady] = useState(false);
  const [jurisdictions, setJurisdictions] = useState<string[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState("");
  const [citasVerificadas, setCitasVerificadas] = useState(false);
  const [revisionAtestada, setRevisionAtestada] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectBusy, setRejectBusy] = useState(false);
  const [rejectError, setRejectError] = useState("");
  const [showCelebration, setShowCelebration] = useState(false);
  const [learningMessage, setLearningMessage] = useState("Tu decisión quedó guardada.");
  const [argumentos, setArgumentos] = useState<Argumento[]>([]);
  const [descartes, setDescartes] = useState<Descarte[]>([]);
  const [argSelected, setArgSelected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    apiGet<{ jurisdictions?: string[] }>(`/api/matters/${matterId}`)
      .then((matter) => setJurisdictions(matter.jurisdictions || []))
      .catch(() => setJurisdictions([]));
    apiGet<DraftResponse>(`/api/matters/${matterId}/draft`)
      .then((d) => {
        setDraft(d.draft);
        setText(d.draft);
        setVerification(d.verification || null);
        setDraftHash(d.draft_hash || "");
        setFinalReady(Boolean(d.final_ready));
        const args = Array.isArray(d.argumentos) ? d.argumentos : [];
        const drops = Array.isArray(d.descartes) ? d.descartes : [];
        setArgumentos(args);
        setDescartes(drops);
        setArgSelected(initialSelection(args, d.argument_selection));
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
  const argIds = argumentos.map((a) => a.id).filter((id): id is string => Boolean(id));
  const hasMatrix = argIds.length > 0;
  const noneSelected = hasMatrix && argIds.every((id) => argSelected[id] === false);

  function argumentSelectionPayload() {
    if (!hasMatrix) return undefined;
    return {
      include: argIds.filter((id) => argSelected[id] !== false),
      exclude: argIds.filter((id) => argSelected[id] === false),
    };
  }

  // La celebración navega con un setTimeout: si el abogado sale de la pantalla
  // antes de que dispare, hay que limpiarlo para no navegar tras el desmontaje.
  const celebrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
    };
  }, []);

  async function approve() {
    if (busy || gateCitasPendiente || versionVacia || !draftHash || !revisionAtestada || noneSelected) return;
    setBusy(true);
    setActionMsg("");
    try {
      const receipt = await resumeDraft(
        `/api/matters/${matterId}/draft/approve`,
        text !== draft
          ? { edited_text: text, draft_hash: draftHash, attested: true,
              ...(argumentSelectionPayload() ? { argument_selection: argumentSelectionPayload() } : {}) }
          : { draft_hash: draftHash, attested: true,
              ...(argumentSelectionPayload() ? { argument_selection: argumentSelectionPayload() } : {}) },
      );
      setFinalReady(Boolean(receipt.final_ready));
      if (!receipt.final_ready) {
        setBusy(false);
        setActionMsg("Tu revisión quedó registrada, pero el documento todavía no puede salir como final.");
        return;
      }
      const learningStatus = receipt.learning?.status;
      setLearningMessage(
        learningStatus === "queued"
          ? "Tu decisión quedó guardada. El aprendizaje continúa en segundo plano."
          : learningStatus === "completed"
            ? "Tu decisión quedó guardada y el aprendizaje ya terminó."
          : learningStatus === "partially_queued"
            ? "Tu decisión quedó guardada. Parte del aprendizaje continúa en segundo plano."
            : learningStatus === "needs_attention"
              ? "Tu decisión quedó guardada. Una parte del aprendizaje necesita reintentarse."
            : learningStatus === "blocked"
              ? "Tu decisión quedó guardada, pero el aprendizaje no se inició."
              : "Tu decisión quedó guardada.",
      );
      // Micro-celebración (Fase 1c): un respiro breve antes de volver al asunto,
      // reforzando que la decisión fue del abogado y que Mia aprende de ella.
      setShowCelebration(true);
      celebrationTimer.current = setTimeout(() => {
        router.push(`/asuntos/${matterId}?confirmed=true`);
      }, 900);
    } catch (e) {
      setBusy(false);
      // El backend redacta el `detail` del 409 en llano (borrador desactualizado,
      // revisión independiente pendiente). Tragarlo dejaba al abogado reintentando
      // algo que reintentar no arregla.
      setActionMsg(plainMessage(e, "No se pudo confirmar el borrador. Intenta de nuevo."));
    }
  }

  async function submitReject() {
    if (rejectBusy) return; // anti doble-clic
    setRejectBusy(true);
    setRejectError("");
    try {
      await resumeDraft(`/api/matters/${matterId}/draft/reject`, { reason: rejectReason });
      router.push(`/asuntos/${matterId}?confirmed=true`);
    } catch (e) {
      setRejectBusy(false);
      setRejectError(plainMessage(e, "No se pudo rechazar el borrador. Intenta de nuevo."));
    }
  }

  async function downloadDraftWord() {
    setDownloadMsg("");
    setDownloading(true);
    try {
      await apiDownload(`/api/matters/${matterId}/draft.docx`, "borrador-no-presentar.docx");
    } catch {
      setDownloadMsg("No se pudo descargar el documento. Intenta de nuevo.");
    } finally {
      setDownloading(false);
    }
  }

  async function downloadFinalWord() {
    setDownloadMsg("");
    setDownloading(true);
    try {
      await apiDownload(`/api/matters/${matterId}/final.docx`, "documento-final-verificado.docx");
    } catch {
      setDownloadMsg("No se pudo descargar el documento final. Intenta de nuevo.");
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
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-meta text-muted-foreground">
            <Globe2 className="h-3.5 w-3.5 text-primary" />
            <span>Contexto jurídico:</span>
            {(jurisdictions.length ? jurisdictions : ["generic"]).map((code) => (
              <span key={code} className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-primary">
                {COUNTRY_NAME_BY_CODE[code] || "General"}
              </span>
            ))}
          </div>
        </div>
        <div className="text-right">
          <Button variant="outline" onClick={downloadDraftWord} disabled={downloading} className="gap-2">
            <Download className="h-4 w-4" />
            {downloading ? "Preparando…" : "Descargar borrador — no presentar"}
          </Button>
          {finalReady ? (
            <Button variant="cta" onClick={downloadFinalWord} disabled={downloading} className="mt-2 gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Descargar documento final verificado
            </Button>
          ) : (
            <p className="mt-1 text-meta text-muted-foreground">
              El documento final se habilita solo después de la aprobación y las verificaciones.
            </p>
          )}
          {downloadMsg ? (
            <p role="alert" className="mt-1 text-meta text-warning">{downloadMsg}</p>
          ) : null}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-6 py-10 md:px-8">
        <div className="mx-auto max-w-3xl animate-slide-up" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
          <EscalamientoBanner categorias={detonadores} />
          {hasMatrix ? (
            <ArgumentMatrix
              argumentos={argumentos}
              descartes={descartes}
              selected={argSelected}
              onToggle={(id) => setArgSelected((prev) => ({ ...prev, [id]: prev[id] === false }))}
            />
          ) : null}
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
        <div className="mb-3 flex items-center justify-center gap-2">
          <input
            type="checkbox"
            id="revision-humana"
            checked={revisionAtestada}
            onChange={(e) => setRevisionAtestada(e.target.checked)}
            className="h-4 w-4 shrink-0 rounded border-input text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Label htmlFor="revision-humana" className="cursor-pointer font-normal">
            Revisé personalmente esta versión y confirmo que es la que deseo aprobar
          </Label>
        </div>
        <p className="mb-3 text-center text-meta text-muted-foreground">
          Esta constancia registra tu decisión; no reemplaza la verificación independiente de Mia.
        </p>
        {!finalReady && actionMsg ? (
          <p className="mb-3 text-center text-meta text-warning">
            Estado: pendiente de superar todos los controles. Solo entonces se habilita el documento final.
          </p>
        ) : null}
        <div className="flex flex-wrap justify-center gap-3">
          <Button
            variant="cta"
            size="lg"
            onClick={approve}
            disabled={busy || gateCitasPendiente || versionVacia || !draftHash || !revisionAtestada || noneSelected}
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
        {noneSelected ? (
          <p className="mt-2 text-center text-meta text-warning">
            Marca al menos un argumento para redactar, o restaura la propuesta de Mia.
          </p>
        ) : null}
        {versionVacia ? (
          <p className="mt-2 text-center text-meta text-warning">
            Tu versión está vacía — escribe el texto o restaura la propuesta de Mia antes de aprobar.
          </p>
        ) : null}
        {!draftHash ? (
          <p className="mt-2 text-center text-meta text-warning">
            Esta versión no se puede aprobar todavía. Recarga el borrador para verificar su integridad.
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
          <p className="text-body text-muted-foreground">{learningMessage}</p>
        </div>
      ) : null}
    </div>
  );
}
