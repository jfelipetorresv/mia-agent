"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Sparkles } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { CountrySelector, COUNTRY_NAME_BY_CODE } from "../_components/CountrySelector";
import { TOOL_OPTIONS } from "../_components/toolOptions";
import {
  WelcomeShell,
  WelcomeProgress,
  StepTransition,
  Stagger,
  StaggerItem,
  MiaLine,
  Celebration,
} from "@/app/_welcome";

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

// Nota: el bloque "triad_mode" (p19) NO tiene etiqueta a propósito — Riesgo #27: el
// modo de análisis profundo no está implementado; su pregunta queda filtrada del
// wizard (HIDDEN_QUESTION_IDS) y no debe existir rastro visible de él en el onboarding.
const BLOCK_LABEL: Record<string, string> = {
  identity: "Identidad",
  jurisdiction: "Contexto",
  tools: "Herramientas",
};

// Países para la pregunta ÚNICA de jurisdicción — Colombia primero, resto alfabético
// (decisión de Pipe 2026-07-09: consolidar las dos preguntas de país en una, con todos
// los países de habla hispana y selección múltiple). Los códigos siguen ISO 3166-1
// alfa-2 y coinciden con los códigos de los paquetes jurídicos (p. ej. "co"): la
// selección viaja como `jurisdictions` (códigos, para el enrutamiento de paquetes) y
// además auto-llena `jurisdiction.base` (nombres, para el perfil del despacho). Los
// países CON paquete instalado se marcan con la insignia "Conocimiento jurídico
// profundo"; los demás se pueden elegir igual — quedan en el perfil sin prometer nada.
// COUNTRY_OPTIONS/COUNTRY_NAME_BY_CODE viven en CountrySelector.tsx (C2: extracción para
// compartir con "Mi despacho").

// Riesgo #27 (CP7): el "modo profundo" (triad_mode) NO está implementado — no se
// ofrece en la UI. Se filtra la pregunta si el backend aún la envía; se
// reintroduce cuando exista la funcionalidad.
const HIDDEN_QUESTION_IDS = new Set(["p19"]);

// Solo P1 y P2 son obligatorias; el resto es opcional.
const REQUIRED_IDS = new Set(["p1", "p2"]);

// Tipos de input por pregunta (onboarding horizontal: sin conocimiento jurídico hardcodeado
// fuera de la lista de países del paso de jurisdicción, que es deliberada).
const TEXT_IDS = new Set(["p4", "p8", "p9"]);
const TAG_IDS = new Set(["p3", "p6", "p7"]);

// TOOL_OPTIONS vive en ../_components/toolOptions.ts — compartida con MiDespachoSection
// (C2: una sola fuente para que las dos pantallas nunca se contradigan entre sí).

// Sugerencias genéricas (no jurisdicción, ramas del derecho ni tribunales).
const VOICE_SUGGESTIONS = ["Técnico", "Argumentativo", "Conciso", "Formal", "Directo", "Analítico", "Detallado", "Estratégico"];

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
  // Dirección de la transición entre preguntas: +1 avanza, -1 retrocede.
  const [direction, setDirection] = useState(1);
  const [started, setStarted] = useState(false);
  // Bienvenida cálida antes de la primera pregunta: la entrevista no arranca en frío.
  const [welcomed, setWelcomed] = useState(false);
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [completion, setCompletion] = useState<CompletionResult | null>(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<{ responses: Record<string, AnswerValue>; idx: number; qid?: string | null } | null>(null);
  // Códigos de país con paquete jurídico instalado (insignia "Conocimiento jurídico profundo").
  const [packCodes, setPackCodes] = useState<Set<string>>(new Set());
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

        // Paso local de jurisdicción: la ÚNICA pregunta de país (consolidación 2026-07-09).
        // La lista de países es fija (COUNTRY_OPTIONS); el paso SIEMPRE se inserta después
        // de p2. /api/jurisdictions solo aporta qué países tienen paquete jurídico instalado
        // (insignia "Conocimiento jurídico profundo"). Fail-open: si falla, sin insignias.
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
        try {
          const jd = await apiGet<{ jurisdictions: JurisdictionOption[] }>("/api/jurisdictions");
          setPackCodes(new Set((jd.jurisdictions ?? []).map((j) => j.code)));
        } catch {
          /* fail-open: sin insignias de paquete */
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

  // Navegación con dirección: alimenta la transición direccional de StepTransition.
  function goNext() {
    const nextIdx = Math.min(total - 1, idx + 1);
    setDirection(1);
    setIdx(nextIdx);
    triggerAutosave(nextIdx, answers);
  }

  function goBack() {
    setDirection(-1);
    setIdx((i) => Math.max(0, i - 1));
  }

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      // La selección de país se extrae de `responses` y viaja DOBLE: como
      // `jurisdictions` (códigos, para el enrutamiento de paquetes jurídicos) y como
      // `jurisdiction.base` (nombres, auto-llenado para que el SOUL.md y el resumen
      // sigan mostrando la jurisdicción — la pregunta descriptiva p5 ya no existe).
      const { [JURISDICTION_FIELD]: jurisdictionValue, ...soulResponses } = answers;
      const jurisdictions = asList(jurisdictionValue);
      const countryNames = jurisdictions.map((c) => COUNTRY_NAME_BY_CODE[c] ?? c);
      if (countryNames.length > 0) soulResponses["jurisdiction.base"] = countryNames;
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

  // ── Carga: esqueleto sereno dentro del lienzo cinematográfico ──
  if (loading) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={2} />} width="lg">
        <div className="space-y-5">
          <Skeleton className="mx-auto h-8 w-3/4 rounded-lg" />
          <Skeleton className="h-32 w-full rounded-2xl" />
        </div>
      </WelcomeShell>
    );
  }

  // ── Mia "pensando" mientras arma el perfil del despacho ──
  if (submitting) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={2} />}>
        <div className="space-y-3 text-center">
          <MiaLine
            text="Estoy armando el perfil de tu despacho…"
            className="text-center text-xl font-semibold tracking-tight sm:text-2xl"
          />
          <p className="text-sm text-muted-foreground">Un momento — casi listo.</p>
        </div>
      </WelcomeShell>
    );
  }

  // ── Pantalla final: celebración detrás del resumen "Así entendí a tu despacho" ──
  if (completion !== null) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={3} />} width="lg">
        <div className="relative">
          {/* Celebración a pantalla completa DETRÁS del resumen (fixed inset-0, z-0, sin
              capturar clics): así el estallido cubre toda la ventana en vez de recortarse
              a la columna acotada (max-w) del contenido. */}
          <Celebration fullscreen />

          <div className="relative z-10 space-y-6">
            <div className="space-y-2 text-center">
              <MiaLine
                text="Así entendí a tu despacho."
                className="text-center text-2xl font-semibold tracking-tight sm:text-3xl"
              />
              <p className="mx-auto max-w-md text-sm text-muted-foreground">
                Ya puedo empezar a trabajar contigo. Podrás cambiar lo que quieras cuando quieras.
              </p>
            </div>

            <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm backdrop-blur-sm md:p-8">
              <SummaryMarkdown markdown={completion.summary} />
            </div>

            <details className="rounded-xl border border-border bg-card/50">
              <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
                Ver el perfil completo que guardé
              </summary>
              <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap border-t border-border px-4 py-3 text-xs leading-relaxed text-muted-foreground">
                {completion.soul_content}
              </pre>
            </details>

            <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
              <Button
                variant="ghost"
                onClick={() => {
                  setCompletion(null);
                  setDirection(-1);
                  setIdx(0);
                  setStarted(true);
                  setWelcomed(true);
                  setAlreadyDone(false);
                }}
              >
                Editar mis respuestas
              </Button>
              <Button variant="cta" size="lg" onClick={() => router.push("/")} className="gap-2">
                Entrar a Mia
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </WelcomeShell>
    );
  }

  // ── Ya configurado: retorno del abogado que ya se presentó ──
  if (alreadyDone && !started) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={3} />}>
        <StepTransition stepKey="ya-listo" direction={1}>
          <Stagger className="space-y-6 text-center">
            <StaggerItem className="space-y-2">
              <MiaLine
                text="Ya nos conocemos."
                className="text-center text-2xl font-semibold tracking-tight sm:text-3xl"
              />
              <p className="mx-auto max-w-md text-sm text-muted-foreground">
                Ya conozco tu despacho, tu jurisdicción y tus herramientas. Puedes revisarlas y
                actualizarlas cuando quieras.
              </p>
            </StaggerItem>
            <StaggerItem className="flex flex-wrap justify-center gap-3">
              <Button variant="ghost" onClick={() => router.push("/")}>
                Ir a mis asuntos
              </Button>
              <Button
                variant="cta"
                size="lg"
                onClick={() => {
                  setStarted(true);
                  setWelcomed(true);
                  setDirection(1);
                  setIdx(0);
                }}
              >
                Revisar mi perfil
              </Button>
            </StaggerItem>
            {error ? (
              <StaggerItem>
                <p className="text-sm text-destructive">{error}</p>
              </StaggerItem>
            ) : null}
          </Stagger>
        </StepTransition>
      </WelcomeShell>
    );
  }

  if (!current) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={2} />}>
        <p className="text-center text-sm text-muted-foreground">
          {error || "No hay preguntas disponibles."}
        </p>
      </WelcomeShell>
    );
  }

  // ── Bienvenida: qué es esto, cuánto tarda y qué gana el abogado. Una sola vez. ──
  if (!welcomed) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={2} />}>
        <StepTransition stepKey="intro" direction={1}>
          <Stagger className="space-y-6 text-center">
            <StaggerItem>
              <MiaLine
                text="Hola, soy Mia. Voy a ser tu asistente."
                className="text-center text-2xl font-semibold tracking-tight sm:text-3xl"
              />
            </StaggerItem>
            <StaggerItem>
              <p className="mx-auto max-w-md text-muted-foreground">
                Para trabajar como a ti te gusta, primero quiero conocerte. Te haré {total}{" "}
                preguntas cortas sobre tu despacho, tu jurisdicción y tus herramientas. Solo dos son
                obligatorias; el resto las puedes saltar.
              </p>
            </StaggerItem>
            <StaggerItem>
              <p className="text-sm text-muted-foreground/80">
                Toma unos 3 minutos y podrás cambiar todo cuando quieras.
              </p>
            </StaggerItem>
            <StaggerItem>
              {draft ? (
                <div className="flex flex-wrap justify-center gap-3">
                  <Button
                    variant="cta"
                    size="lg"
                    onClick={() => {
                      setAnswers(draft.responses);
                      // Reanudar por IDENTIDAD de pregunta (qid): la lista de pasos puede
                      // cambiar de largo entre sesiones (p.ej. el paso de jurisdicción no
                      // cargó) y un índice posicional mostraría otra pregunta. El índice
                      // guardado queda solo como respaldo.
                      const porId = draft.qid ? questions.findIndex((q) => q.id === draft.qid) : -1;
                      setDirection(1);
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
                      setDirection(1);
                      setIdx(0);
                      setDraft(null);
                      setWelcomed(true);
                    }}
                  >
                    Empezar de nuevo
                  </Button>
                </div>
              ) : (
                <Button variant="cta" size="lg" onClick={() => setWelcomed(true)} className="gap-2">
                  <Sparkles className="h-4 w-4" />
                  Empecemos
                </Button>
              )}
            </StaggerItem>
          </Stagger>
        </StepTransition>
      </WelcomeShell>
    );
  }

  const isLast = idx === total - 1;
  const value = answers[current.field];
  const pct = Math.round(((idx + 1) / total) * 100);
  const optional = !REQUIRED_IDS.has(current.id);
  const canAdvance = isComplete(current, value);

  return (
    <WelcomeShell progress={<WelcomeProgress current={2} />} width="lg">
      <div className="w-full">
        {/* Sub-progreso sutil: en qué parte de la conversación vamos, sin competir con la
            constelación del viaje. Junto al aviso discreto de autosave (aria-live). */}
        <div className="mb-6">
          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground/70">
            <span>
              {BLOCK_LABEL[current.block] ?? current.block} · {idx + 1} de {total}
            </span>
            <span aria-live="polite" className="transition-opacity">
              {savedFlash ? "Avance guardado" : ""}
            </span>
          </div>
          <div className="h-0.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-primary/70 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* Cada pregunta entra/sale con transición direccional real; sus elementos se
            escalonan. Mia "habla" el enunciado con el efecto máquina de escribir. */}
        <StepTransition stepKey={current.id} direction={direction}>
          <Stagger className="space-y-6">
            <StaggerItem className="space-y-2 text-center">
              <MiaLine
                text={current.question}
                className="text-center text-2xl font-semibold leading-snug tracking-tight"
              />
              {current.id === JURISDICTION_QUESTION_ID ? (
                <p className="text-xs text-muted-foreground">
                  Esto le dice a Mia qué normas y jurisprudencia usar. Puedes elegir más de uno.
                </p>
              ) : current.example ? (
                <p className="text-xs text-muted-foreground">Ej: {current.example}</p>
              ) : null}
              {optional ? (
                <p className="text-xs text-muted-foreground/70">Opcional — puedes saltarla.</p>
              ) : null}
            </StaggerItem>

            <StaggerItem>
              <QuestionInput question={current} value={value} onChange={setAnswer} packCodes={packCodes} />
            </StaggerItem>
          </Stagger>
        </StepTransition>

        {error ? (
          <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        ) : null}

        <div className="mt-8 flex items-center justify-between">
          <Button variant="ghost" onClick={goBack} disabled={idx === 0} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Anterior
          </Button>
          {isLast ? (
            <Button variant="cta" onClick={finish} disabled={!canAdvance} className="gap-2">
              <Check className="h-4 w-4" />
              Finalizar
            </Button>
          ) : (
            <Button onClick={goNext} disabled={!canAdvance} className="gap-2">
              Siguiente
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>
        {!canAdvance ? (
          <p className="mt-3 text-right text-xs text-muted-foreground/70">
            Completa esta pregunta para continuar.
          </p>
        ) : null}
      </div>
    </WelcomeShell>
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
  packCodes,
}: {
  question: Question;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  packCodes: Set<string>;
}) {
  switch (question.id) {
    // Paso local de jurisdicción — la única pregunta de país (multi-select de 21 países).
    case JURISDICTION_QUESTION_ID:
      return <CountrySelector packCodes={packCodes} value={asList(value)} onChange={onChange} />;
    // P1 — dos campos: despacho + abogado.
    case "p1": {
      const n = asNamePair(value);
      return (
        <div className="space-y-3">
          <Field label="Nombre del despacho">
            <Input
              value={n.firm}
              onChange={(e) => onChange({ ...n, firm: e.target.value })}
              placeholder="Ej: Fajardo & Asociados"
              autoFocus
            />
          </Field>
          <Field label="Tu nombre (abogado principal)">
            <Input
              value={n.lawyer}
              onChange={(e) => onChange({ ...n, lawyer: e.target.value })}
              placeholder="Ej: Nombre Apellido · número de registro profesional 000.000"
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
        return (
          <TagInput
            value={asList(value)}
            onChange={onChange}
            suggestions={[]}
            placeholder="Escribe y presiona Enter"
          />
        );
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

// Paso local de jurisdicción: ver CountrySelector.tsx (C2 — extracción, mismo componente
// que usa "Mi despacho" al editar la jurisdicción después del onboarding).
