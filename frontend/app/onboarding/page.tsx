"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, PartyPopper, Scale, Sparkles } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Question = {
  id: string;
  block: string;
  field: string;
  question: string;
  example: string;
};

type NamePair = { firm: string; lawyer: string };
type LocationPair = { country: string; city: string };

type AnswerValue =
  | string
  | string[]
  | NamePair
  | LocationPair
  | { no_meetings: string[]; hours: string }
  | { enabled: boolean; trigger: string };

type Status = {
  completed: boolean;
  last_updated: string | null;
  responses?: Record<string, AnswerValue>;
  draft?: { responses: Record<string, AnswerValue>; idx: number; qid?: string | null } | null;
};

type JurisdictionOption = { code: string; name: string; verified: boolean };

// Clave reservada dentro de `responses` para la selección de jurisdicción (paso local,
// no viene de las preguntas del backend). Se extrae antes de mandar `complete`.
const JURISDICTION_FIELD = "_jurisdicciones";
const JURISDICTION_QUESTION_ID = "_jurisdiction";

type CompletionResult = {
  soul_content: string;
  summary: string;
  path: string;
};

const BLOCK_LABEL: Record<string, string> = {
  identity: "Identidad",
  jurisdiction: "Contexto",
  legal_voice: "Voz",
  mission_rhythm: "Ritmo",
  rhythm: "Ritmo",
};

// Riesgo #27 (CP7): el "modo profundo" (triad_mode) NO está implementado — no se
// ofrece en la UI. Se filtra la pregunta si el backend aún la envía; se
// reintroduce cuando exista la funcionalidad.
const HIDDEN_QUESTION_IDS = new Set(["p19"]);

// Solo P1 y P2 son obligatorias; el resto es opcional.
const REQUIRED_IDS = new Set(["p1", "p2"]);

// Tipos de input por pregunta (onboarding horizontal: sin conocimiento jurídico hardcodeado).
const TEXT_IDS = new Set(["p4", "p5", "p8", "p9", "p11"]);
const TAG_IDS = new Set(["p3", "p6", "p7", "p14"]);
const SELECT_OPTIONS: Record<string, string[]> = {
  p10: ["Narrativo continuo", "Estructurado con secciones", "Depende del tipo de escrito"],
};
const CHECKBOX_OPTIONS: Record<string, string[]> = {
  p17: ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
};

const TOOL_OPTIONS: { name: string; description: string; comingSoon?: boolean }[] = [
  { name: "Correo", description: "Mia vigila tus correos urgentes y te avisa." },
  { name: "Calendario", description: "Mia te recuerda tus eventos y audiencias próximas." },
  { name: "Gestor documental", description: "Mia consulta los documentos del despacho para responder." },
  { name: "Mensajería (Telegram)", description: "Habla con Mia desde tu celular, por texto o por voz." },
  {
    name: "Carpetas en la nube (OneDrive/Google Drive)",
    description: "Mia conoce las carpetas donde guardas tu trabajo.",
  },
  { name: "Notas del despacho", description: "Mia guarda y consulta tus notas.", comingSoon: true },
];

// Sugerencias genéricas (no jurisdicción, ramas del derecho ni tribunales).
const VOICE_SUGGESTIONS = ["Técnico", "Argumentativo", "Conciso", "Formal", "Directo", "Analítico", "Detallado", "Estratégico"];
const LIMIT_SUGGESTIONS = ["Revisión humana obligatoria", "Verificar antes de enviar", "Consultar al abogado antes de actuar"];

// ── Conversores tolerantes (incluyen fallback desde strings de onboardings viejos) ──
function asText(value: AnswerValue | undefined): string {
  return typeof value === "string" ? value : "";
}

function asList(value: AnswerValue | undefined): string[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim()) return value.split(",").map((v) => v.trim()).filter(Boolean);
  return [];
}

function asNamePair(value: AnswerValue | undefined): NamePair {
  if (value && typeof value === "object" && !Array.isArray(value) && "firm" in value) {
    return { firm: value.firm || "", lawyer: value.lawyer || "" };
  }
  return { firm: typeof value === "string" ? value : "", lawyer: "" };
}

function asLocationPair(value: AnswerValue | undefined): LocationPair {
  if (value && typeof value === "object" && !Array.isArray(value) && "country" in value) {
    return { country: value.country || "", city: value.city || "" };
  }
  return { country: typeof value === "string" ? value : "", city: "" };
}

function asRhythm(value: AnswerValue | undefined): { no_meetings: string[]; hours: string } {
  if (value && typeof value === "object" && !Array.isArray(value) && "no_meetings" in value) {
    return { no_meetings: value.no_meetings, hours: value.hours || "" };
  }
  return { no_meetings: [], hours: typeof value === "string" ? value : "" };
}

// Una pregunta está "completa" si cumple su requisito. Solo P1/P2 son obligatorias.
function isComplete(question: Question, value: AnswerValue | undefined): boolean {
  if (question.id === "p1") {
    const n = asNamePair(value);
    return Boolean(n.firm.trim() && n.lawyer.trim());
  }
  if (question.id === "p2") {
    const l = asLocationPair(value);
    return Boolean(l.country.trim() && l.city.trim());
  }
  return true;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [idx, setIdx] = useState(0);
  const [started, setStarted] = useState(false);
  // Bienvenida cálida antes de la primera pregunta: la entrevista no arranca en frío.
  const [welcomed, setWelcomed] = useState(false);
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [completion, setCompletion] = useState<CompletionResult | null>(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<{ responses: Record<string, AnswerValue>; idx: number; qid?: string | null } | null>(null);
  const [jurisdictionOptions, setJurisdictionOptions] = useState<JurisdictionOption[]>([]);
  // Microtexto discreto de autosave — ayuda, no candado (§ autosave).
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [qs, st] = await Promise.all([
          apiGet<Question[]>("/api/onboarding/questions"),
          apiGet<Status>("/api/onboarding/status"),
        ]);
        let list = qs.filter((q) => !HIDDEN_QUESTION_IDS.has(q.id));

        // Paso local de jurisdicción (Fase 2): NO viene del backend. Se inserta justo
        // después de p2. Fail-open: si /api/jurisdictions falla, el paso se omite en silencio.
        try {
          const jd = await apiGet<{ jurisdictions: JurisdictionOption[] }>("/api/jurisdictions");
          if (jd.jurisdictions && jd.jurisdictions.length > 0) {
            setJurisdictionOptions(jd.jurisdictions);
            const jurisdictionStep: Question = {
              id: JURISDICTION_QUESTION_ID,
              block: "jurisdiction",
              field: JURISDICTION_FIELD,
              question: "¿Con las reglas jurídicas de qué país trabaja tu despacho?",
              example: "",
            };
            const p2Index = list.findIndex((q) => q.id === "p2");
            const insertAt = p2Index >= 0 ? p2Index + 1 : list.length;
            list = [...list.slice(0, insertAt), jurisdictionStep, ...list.slice(insertAt)];
          }
        } catch {
          /* fail-open: sin jurisdicciones disponibles, el paso se omite */
        }

        setQuestions(list);
        if (st.completed) {
          setAlreadyDone(true);
          if (st.responses) setAnswers(st.responses);
        } else {
          setStarted(true);
          if (st.draft) setDraft(st.draft);
        }
      } catch {
        setError("No se pudo cargar la entrevista. Revisa que el servidor esté encendido.");
      }
      setLoading(false);
    })();
  }, []);

  // Autosave fire-and-forget: ayuda, no candado. Si falla, el wizard sigue
  // funcionando — pero el aviso "Avance guardado" solo aparece si de verdad se
  // guardó (decirle al abogado que está a salvo cuando no lo está es peor que
  // callar). Se guarda también el id de la pregunta (qid): al reanudar se busca
  // por identidad, no por posición.
  function triggerAutosave(nextIdx: number, snapshot: Record<string, AnswerValue>) {
    const qid = questions[nextIdx]?.id ?? null;
    apiSend("POST", "/api/onboarding/draft", { responses: snapshot, idx: nextIdx, qid })
      .then(() => {
        setSavedFlash(true);
        window.setTimeout(() => setSavedFlash(false), 1500);
      })
      .catch(() => {});
  }

  const total = questions.length;
  const current = questions[idx];

  function setAnswer(value: AnswerValue) {
    if (!current) return;
    setAnswers((a) => ({ ...a, [current.field]: value }));
  }

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      // La jurisdicción es un paso local (no del SOUL): se extrae de `responses`
      // y viaja aparte como `jurisdictions`.
      const { [JURISDICTION_FIELD]: jurisdictionValue, ...soulResponses } = answers;
      const jurisdictions = asList(jurisdictionValue);
      const res = await apiSend<CompletionResult>("POST", "/api/onboarding/complete", {
        responses: soulResponses,
        ...(jurisdictions.length > 0 ? { jurisdictions } : {}),
      });
      setCompletion(res);
    } catch {
      setError("No se pudo generar tu perfil. Intenta de nuevo.");
    }
    setSubmitting(false);
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-8 py-16">
        <Skeleton className="h-3 w-full rounded-full" />
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }

  // Espera del LLM: Mia "pensando" mientras genera el perfil.
  if (submitting) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-2xl flex-col items-center justify-center px-8 text-center bg-aurora">
        <div className="relative">
          <span className="absolute inset-0 rounded-3xl bg-primary/40 blur-2xl animate-pulse-soft" aria-hidden />
          <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-lg">
            <Scale className="h-8 w-8" />
          </div>
        </div>
        <p className="mt-6 text-lg font-medium">Generando tu perfil…</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Mia está construyendo la identidad de tu despacho. Toma unos segundos.
        </p>
      </div>
    );
  }

  if (completion !== null) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12 md:px-8">
        <div className="mb-6 animate-slide-up rounded-2xl border border-border bg-card p-6 shadow-sm md:p-8">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-success/15 text-success">
              <PartyPopper className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Tu perfil está listo</h1>
          </div>
          <SummaryMarkdown markdown={completion.summary} />
        </div>
        <details className="mb-6 animate-slide-up rounded-xl border border-border bg-card/60" style={{ animationDelay: "80ms", animationFillMode: "backwards" }}>
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
            Ver detalle técnico
          </summary>
          <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap border-t border-border px-4 py-3 text-xs leading-relaxed text-muted-foreground">
            {completion.soul_content}
          </pre>
        </details>
        <div className="flex flex-wrap gap-3 animate-slide-up" style={{ animationDelay: "140ms", animationFillMode: "backwards" }}>
          <Button
            variant="ghost"
            onClick={() => {
              setCompletion(null);
              setIdx(0);
              setStarted(true);
              setWelcomed(true);
              setAlreadyDone(false);
            }}
          >
            Editar
          </Button>
          <Button variant="outline" onClick={() => router.push("/")} className="gap-2">
            Continuar a mis asuntos
          </Button>
          <Button variant="cta" onClick={() => router.push("/configurar")} className="gap-2">
            Seguir con la configuración
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  }

  if (alreadyDone && !started) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-2xl flex-col items-center justify-center px-8 text-center bg-aurora">
        <div className="mb-5 flex h-14 w-14 animate-slide-up items-center justify-center rounded-2xl bg-success/15 text-success">
          <Check className="h-7 w-7" />
        </div>
        <h1 className="animate-slide-up text-2xl font-semibold tracking-tight" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
          Tu despacho ya está configurado
        </h1>
        <p className="mt-2 max-w-md animate-slide-up text-sm text-muted-foreground" style={{ animationDelay: "120ms", animationFillMode: "backwards" }}>
          Mia ya conoce tu identidad, tu voz y tus límites. Puedes revisarlos y actualizarlos.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3 animate-slide-up" style={{ animationDelay: "180ms", animationFillMode: "backwards" }}>
          <Button variant="ghost" onClick={() => router.push("/")}>
            Ir a mis asuntos
          </Button>
          <Button variant="outline" onClick={() => router.push("/configurar")}>
            Ver toda la configuración
          </Button>
          <Button
            onClick={() => {
              setStarted(true);
              setWelcomed(true);
              setIdx(0);
            }}
          >
            Revisar mi perfil
          </Button>
        </div>
        {error ? <p className="mt-6 text-sm text-destructive">{error}</p> : null}
      </div>
    );
  }

  if (!current) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-sm text-muted-foreground">
        {error || "No hay preguntas disponibles."}
      </div>
    );
  }

  // Bienvenida: qué es esto, cuánto tarda y qué gana el abogado. Una sola vez.
  if (!welcomed) {
    return (
      <div className="mx-auto flex min-h-[80vh] max-w-2xl flex-col items-center justify-center px-8 py-12 text-center bg-aurora">
        <div className="relative mb-6 animate-slide-up">
          <div className="absolute inset-0 rounded-3xl bg-primary/30 blur-2xl" aria-hidden />
          <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-lg">
            <Scale className="h-8 w-8" />
          </div>
        </div>
        <h1
          className="text-gradient-brand animate-slide-up text-3xl font-semibold tracking-tight"
          style={{ animationDelay: "60ms", animationFillMode: "backwards" }}
        >
          Hola, soy Mia.
        </h1>
        <p
          className="mt-3 max-w-md animate-slide-up text-muted-foreground"
          style={{ animationDelay: "120ms", animationFillMode: "backwards" }}
        >
          Voy a ser tu asistente jurídica. Para trabajar como a ti te gusta, necesito
          conocerte: te haré {total} preguntas cortas sobre tu despacho, tu forma de
          escribir y tus límites. Solo dos son obligatorias; el resto las puedes saltar.
        </p>
        <p
          className="mt-2 animate-slide-up text-sm text-muted-foreground/80"
          style={{ animationDelay: "160ms", animationFillMode: "backwards" }}
        >
          Toma unos 3 minutos. Podrás cambiar todo después.
        </p>
        {draft ? (
          <div
            className="mt-8 flex flex-wrap justify-center gap-3 animate-slide-up"
            style={{ animationDelay: "220ms", animationFillMode: "backwards" }}
          >
            <Button
              size="lg"
              onClick={() => {
                setAnswers(draft.responses);
                // Reanudar por IDENTIDAD de pregunta (qid): la lista de pasos puede
                // cambiar de largo entre sesiones (p.ej. el paso de jurisdicción no
                // cargó) y un índice posicional mostraría otra pregunta. El índice
                // guardado queda solo como respaldo.
                const porId = draft.qid ? questions.findIndex((q) => q.id === draft.qid) : -1;
                setIdx(porId >= 0 ? porId : Math.max(0, Math.min(total - 1, draft.idx)));
                setWelcomed(true);
              }}
              className="gap-2"
            >
              <Sparkles className="h-4 w-4" />
              Continuar donde ibas
            </Button>
            <Button
              size="lg"
              variant="ghost"
              onClick={() => {
                setAnswers({});
                setIdx(0);
                setDraft(null);
                setWelcomed(true);
              }}
            >
              Empezar de nuevo
            </Button>
          </div>
        ) : (
          <Button
            size="lg"
            onClick={() => setWelcomed(true)}
            className="mt-8 animate-slide-up gap-2"
            style={{ animationDelay: "220ms", animationFillMode: "backwards" }}
          >
            <Sparkles className="h-4 w-4" />
            Empecemos
          </Button>
        )}
      </div>
    );
  }

  const isLast = idx === total - 1;
  const value = answers[current.field];
  const pct = Math.round(((idx + 1) / total) * 100);
  const optional = !REQUIRED_IDS.has(current.id);
  const canAdvance = isComplete(current, value);

  return (
    <div className="mx-auto max-w-2xl px-6 py-12 md:px-8">
      <div className="mb-8">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs text-muted-foreground/70">Configuración de Mia — tu perfil</p>
          <p aria-live="polite" className="text-xs text-muted-foreground/70">
            {savedFlash ? "Avance guardado" : ""}
          </p>
        </div>
        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {BLOCK_LABEL[current.block] ?? current.block} · Pregunta {idx + 1} de {total}
          </span>
          <span className="tabular-nums">{pct}%</span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-primary/80 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div key={current.id} className="animate-slide-up">
        <h1 className="mb-1 text-center text-2xl font-semibold leading-snug tracking-tight">
          {current.question}
          {optional ? <span className="ml-2 align-middle text-sm font-normal text-muted-foreground">(opcional)</span> : null}
        </h1>
        {current.id === JURISDICTION_QUESTION_ID ? (
          <p className="mb-6 text-center text-xs text-muted-foreground">
            Esto le dice a Mia qué normas y jurisprudencia usar. Puedes elegir más de uno.
          </p>
        ) : current.example ? (
          <p className="mb-6 text-center text-xs text-muted-foreground">Ej: {current.example}</p>
        ) : (
          <div className="mb-6" />
        )}

        <QuestionInput question={current} value={value} onChange={setAnswer} jurisdictionOptions={jurisdictionOptions} />
      </div>

      {error ? <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      <div className="mt-8 flex items-center justify-between">
        <Button variant="ghost" onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx === 0} className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Anterior
        </Button>
        {isLast ? (
          <Button variant="cta" onClick={finish} disabled={!canAdvance} className="gap-2">
            <Check className="h-4 w-4" />
            Finalizar
          </Button>
        ) : (
          <Button
            onClick={() => {
              const nextIdx = Math.min(total - 1, idx + 1);
              setIdx(nextIdx);
              triggerAutosave(nextIdx, answers);
            }}
            disabled={!canAdvance}
            className="gap-2"
          >
            Siguiente
            <ArrowRight className="h-4 w-4" />
          </Button>
        )}
      </div>
      {!canAdvance ? (
        <p className="mt-3 text-right text-xs text-muted-foreground">Completa esta pregunta para continuar.</p>
      ) : null}
    </div>
  );
}

function SummaryMarkdown({ markdown }: { markdown: string }) {
  const elements: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  let key = 0;

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${key++}`} className="space-y-2 text-sm leading-relaxed">
          {listItems}
        </ul>
      );
      listItems = [];
    }
  }

  const bulletRe = /^- \*\*(.+?):\*\* (.+)$/;
  const rulesRe = /^- \*\*(.+?)\*\*$/;
  const subRe = /^  - (.+)$/;

  for (const line of markdown.split("\n")) {
    if (line.startsWith("### ")) {
      flushList();
      elements.push(
        <h2 key={`h-${key++}`} className="mb-4 text-lg font-semibold tracking-tight">
          {line.slice(4)}
        </h2>
      );
      continue;
    }

    const bullet = line.match(bulletRe);
    if (bullet) {
      listItems.push(
        <li key={`li-${key++}`}>
          <span className="font-medium">{bullet[1]}:</span>{" "}
          <span className="text-muted-foreground">{bullet[2]}</span>
        </li>
      );
      continue;
    }

    const rules = line.match(rulesRe);
    if (rules) {
      listItems.push(
        <li key={`li-${key++}`} className="font-medium">
          {rules[1]}:
        </li>
      );
      continue;
    }

    const sub = line.match(subRe);
    if (sub) {
      listItems.push(
        <li key={`li-${key++}`} className="ml-4 list-disc text-muted-foreground">
          {sub[1]}
        </li>
      );
      continue;
    }

    if (line.trim() === "") {
      flushList();
      continue;
    }

    flushList();
    elements.push(
      <p key={`p-${key++}`} className="text-sm leading-relaxed text-muted-foreground">
        {line}
      </p>
    );
  }

  flushList();
  return <div className="space-y-3">{elements}</div>;
}

function QuestionInput({
  question,
  value,
  onChange,
  jurisdictionOptions,
}: {
  question: Question;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  jurisdictionOptions: JurisdictionOption[];
}) {
  switch (question.id) {
    // Paso local de jurisdicción (Fase 2) — no viene de las preguntas del backend.
    case JURISDICTION_QUESTION_ID:
      return <JurisdictionCheckboxes options={jurisdictionOptions} value={asList(value)} onChange={onChange} />;
    // P1 — dos campos: despacho + abogado.
    case "p1": {
      const n = asNamePair(value);
      return (
        <div className="space-y-3">
          <Field label="Nombre del despacho">
            <Input
              value={n.firm}
              onChange={(e) => onChange({ ...n, firm: e.target.value })}
              placeholder="Ej: Lexia Abogados S.A.S."
              autoFocus
            />
          </Field>
          <Field label="Tu nombre (abogado principal)">
            <Input
              value={n.lawyer}
              onChange={(e) => onChange({ ...n, lawyer: e.target.value })}
              placeholder="Ej: Nombre Apellido · tarjeta profesional 000.000"
            />
          </Field>
        </div>
      );
    }

    // P2 — dos campos: país + ciudad.
    case "p2": {
      const l = asLocationPair(value);
      return (
        <div className="space-y-3">
          <Field label="País">
            <Input
              value={l.country}
              onChange={(e) => onChange({ ...l, country: e.target.value })}
              placeholder="Ej: tu país"
              autoFocus
            />
          </Field>
          <Field label="Ciudad">
            <Input
              value={l.city}
              onChange={(e) => onChange({ ...l, city: e.target.value })}
              placeholder="Ej: tu ciudad"
            />
          </Field>
        </div>
      );
    }

    // P3 — adjetivos de estilo (tags libres con sugerencias genéricas).
    case "p3":
      return <TagInput value={asList(value)} onChange={onChange} suggestions={VOICE_SUGGESTIONS} max={3} placeholder="Escribe un adjetivo y presiona Enter" />;

    // P17 — ritmo: días sin reuniones + horario de trabajo profundo.
    case "p17": {
      const rhythm = asRhythm(value);
      return (
        <div className="space-y-5">
          <CheckboxGroup
            label="Días sin reuniones"
            options={CHECKBOX_OPTIONS.p17}
            value={rhythm.no_meetings}
            onChange={(days) => onChange({ ...rhythm, no_meetings: days as string[] })}
          />
          <Field label="Horario de trabajo profundo">
            <Input
              value={rhythm.hours}
              onChange={(e) => onChange({ ...rhythm, hours: e.target.value })}
              placeholder="Ej: 7am-12pm"
            />
          </Field>
        </div>
      );
    }

    // P18 — herramientas (lista curada con descripción).
    case "p18":
      return <ToolsChecklist value={asList(value)} onChange={onChange} />;

    // P19 (triad_mode) se retiró de la UI — Riesgo #27: no ofrecer lo no implementado.

    default: {
      if (TEXT_IDS.has(question.id)) {
        return (
          <Input
            value={asText(value)}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Tu respuesta…"
            autoFocus
          />
        );
      }
      if (TAG_IDS.has(question.id)) {
        const hints = question.id === "p14" ? LIMIT_SUGGESTIONS : [];
        return (
          <TagInput
            value={asList(value)}
            onChange={onChange}
            suggestions={hints}
            placeholder="Escribe y presiona Enter"
          />
        );
      }
      if (SELECT_OPTIONS[question.id]) {
        return <RadioGroup options={SELECT_OPTIONS[question.id]} value={asText(value)} onChange={onChange} />;
      }
      return (
        <Input
          value={asText(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Tu respuesta…"
          autoFocus
        />
      );
    }
  }
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function ToolsChecklist({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const [customDraft, setCustomDraft] = useState("");
  const curatedNames = new Set(TOOL_OPTIONS.map((t) => t.name));
  const customTools = value.filter((v) => !curatedNames.has(v));

  function toggle(name: string, checked: boolean) {
    if (checked) onChange([...value, name]);
    else onChange(value.filter((v) => v !== name));
  }

  function addCustom() {
    const tool = customDraft.trim();
    if (!tool || value.includes(tool)) {
      setCustomDraft("");
      return;
    }
    onChange([...value, tool]);
    setCustomDraft("");
  }

  return (
    <div className="space-y-3">
      {TOOL_OPTIONS.map((tool) => {
        const checked = value.includes(tool.name);
        const disabled = Boolean(tool.comingSoon);
        return (
          <label
            key={tool.name}
            className={cn(
              "flex gap-3 rounded-xl border px-4 py-3 transition-colors",
              disabled
                ? "cursor-not-allowed border-border bg-muted/40 opacity-70"
                : checked
                  ? "cursor-pointer border-primary/40 bg-primary/5"
                  : "cursor-pointer border-border bg-card hover:border-primary/25",
            )}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled}
              onChange={(e) => toggle(tool.name, e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium">
                {tool.name}
                {tool.comingSoon ? (
                  <span className="ml-2 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-normal text-warning">Próximamente</span>
                ) : null}
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{tool.description}</span>
            </span>
          </label>
        );
      })}

      {customTools.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {customTools.map((tool) => (
            <button
              key={tool}
              type="button"
              onClick={() => onChange(value.filter((v) => v !== tool))}
              className="rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-85"
            >
              {tool} ×
            </button>
          ))}
        </div>
      ) : null}

      <Field label="Otra herramienta">
        <div className="flex gap-2">
          <Input
            value={customDraft}
            onChange={(e) => setCustomDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            placeholder="Escribe el nombre y presiona Enter"
          />
          <Button type="button" variant="outline" onClick={addCustom} disabled={!customDraft.trim()} className="shrink-0">
            Añadir
          </Button>
        </div>
      </Field>
    </div>
  );
}

function TagInput({
  value,
  onChange,
  suggestions = [],
  max,
  placeholder = "Escribe y presiona Enter",
}: {
  value: string[];
  onChange: (value: string[]) => void;
  suggestions?: string[];
  max?: number;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const atMax = typeof max === "number" && value.length >= max;

  function addTag(raw?: string) {
    const tag = (raw ?? draft).trim();
    if (!tag || value.includes(tag) || atMax) {
      setDraft("");
      return;
    }
    onChange([...value, tag]);
    setDraft("");
  }

  const available = suggestions.filter((s) => !value.includes(s));

  return (
    <div>
      <div className="rounded-lg border border-input bg-card px-3 py-2 transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background">
        {value.length > 0 ? (
          <div className="mb-2 flex flex-wrap gap-2">
            {value.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => onChange(value.filter((v) => v !== tag))}
                className="rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-85"
              >
                {tag} ×
              </button>
            ))}
          </div>
        ) : null}
        {atMax ? (
          <p className="py-1 text-xs text-muted-foreground">Máximo {max}. Quita uno para cambiarlo.</p>
        ) : (
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTag();
              }
            }}
            onBlur={() => addTag()}
            className="w-full bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
            placeholder={placeholder}
            autoFocus
          />
        )}
      </div>
      {available.length > 0 && !atMax ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {available.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => addTag(s)}
              className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            >
              + {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// Paso local de jurisdicción (Fase 2): muestra `name` (viene del API), guarda `code`.
// Los nombres de jurisdicción NUNCA se hardcodean — llegan siempre de GET /api/jurisdictions.
function JurisdictionCheckboxes({
  options,
  value,
  onChange,
}: {
  options: JurisdictionOption[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  function toggle(code: string, checked: boolean) {
    if (checked) onChange([...value, code]);
    else onChange(value.filter((v) => v !== code));
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {options.map((option) => {
        const checked = value.includes(option.code);
        return (
          <label
            key={option.code}
            className={cn(
              "flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-sm transition-colors",
              checked ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-primary/25",
            )}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => toggle(option.code, e.target.checked)}
              className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span>{option.name}</span>
          </label>
        );
      })}
    </div>
  );
}

function CheckboxGroup({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <div>
      {label ? <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div> : null}
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const checked = value.includes(option);
          return (
            <label
              key={option}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-sm transition-colors",
                checked ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-primary/25",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  if (e.target.checked) onChange([...value, option]);
                  else onChange(value.filter((v) => v !== option));
                }}
                className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
              />
              <span>{option}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function RadioGroup({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      {options.map((option) => (
        <label
          key={option}
          className={cn(
            "flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-sm transition-colors",
            value === option ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-primary/25",
          )}
        >
          <input
            type="radio"
            checked={value === option}
            onChange={() => onChange(option)}
            className="h-4 w-4 border-input accent-[hsl(var(--primary))]"
          />
          <span>{option}</span>
        </label>
      ))}
    </div>
  );
}
