"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/api";

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
  | { pillars: string[] }
  | { no_meetings: string[]; hours: string }
  | { enabled: boolean; trigger: string };

type Status = {
  completed: boolean;
  last_updated: string | null;
  responses?: Record<string, AnswerValue>;
};

const BLOCK_LABEL: Record<string, string> = {
  identity: "Identidad",
  jurisdiction: "Contexto",
  legal_voice: "Voz",
  mission_rhythm: "Ritmo",
  triad_mode: "Modo profundo",
};

// Solo P1 y P2 son obligatorias; el resto es opcional.
const REQUIRED_IDS = new Set(["p1", "p2"]);

// Sugerencias clickeables por pregunta (el abogado hace click o escribe el suyo).
const VOICE_SUGGESTIONS = ["Técnico", "Argumentativo", "Conciso", "Formal", "Directo", "Analítico", "Detallado", "Estratégico"];
const PRACTICE_SUGGESTIONS = ["Civil", "Penal", "Laboral", "Comercial", "Constitucional", "Administrativo", "Fiscal", "Familia", "Internacional"];
const HARD_NO_SUGGESTIONS = ["Nunca presentar sin revisión", "Nunca recomendar allanarse sin análisis", "Nunca citar sin verificar"];
const TOOL_SUGGESTIONS = ["Obsidian", "Notion", "Linear", "Slack", "WhatsApp", "Google Drive", "Dropbox"];

const CLIENT_OPTIONS = ["Empresas", "Personas naturales", "Sector público", "Aseguradoras", "Instituciones financieras", "Otro"];
const STRUCTURE_OPTIONS = ["Párrafos narrativos continuos", "Estructurado con secciones y títulos", "Depende del tipo de escrito"];
const WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"];

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

function asPillars(value: AnswerValue | undefined): string[] {
  if (value && typeof value === "object" && !Array.isArray(value) && "pillars" in value) {
    return [...value.pillars, "", "", ""].slice(0, 3);
  }
  if (typeof value === "string" && value.trim()) {
    return [...value.split(/\n|;/).map((v) => v.trim()).filter(Boolean), "", "", ""].slice(0, 3);
  }
  return ["", "", ""];
}

function asRhythm(value: AnswerValue | undefined): { no_meetings: string[]; hours: string } {
  if (value && typeof value === "object" && !Array.isArray(value) && "no_meetings" in value) {
    return { no_meetings: value.no_meetings, hours: value.hours || "" };
  }
  return { no_meetings: [], hours: typeof value === "string" ? value : "" };
}

function asTriad(value: AnswerValue | undefined): { enabled: boolean; trigger: string } {
  if (value && typeof value === "object" && !Array.isArray(value) && "enabled" in value) {
    return { enabled: Boolean(value.enabled), trigger: value.trigger || "" };
  }
  return { enabled: typeof value === "string" ? value.toLowerCase().startsWith("si") : false, trigger: "" };
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
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [soul, setSoul] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [qs, st] = await Promise.all([
          apiGet<Question[]>("/api/onboarding/questions"),
          apiGet<Status>("/api/onboarding/status"),
        ]);
        setQuestions(qs);
        if (st.completed) {
          setAlreadyDone(true);
          if (st.responses) setAnswers(st.responses);
        } else {
          setStarted(true);
        }
      } catch {
        setError("No se pudo cargar la entrevista. Revisa que el servidor este encendido.");
      }
      setLoading(false);
    })();
  }, []);

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
      const res = await apiSend<{ soul_content: string; path: string }>(
        "POST",
        "/api/onboarding/complete",
        { responses: answers }
      );
      setSoul(res.soul_content);
    } catch {
      setError("No se pudo generar tu perfil. Intenta de nuevo.");
    }
    setSubmitting(false);
  }

  if (loading) {
    return <div className="mx-auto max-w-2xl px-8 py-16 text-gray-400">Cargando...</div>;
  }

  // Espera del LLM: spinner visible mientras genera el perfil.
  if (submitting) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-center px-8 py-24 text-center">
        <Spinner />
        <p className="mt-6 text-lg font-medium text-gray-700">Generando tu perfil...</p>
        <p className="mt-2 text-sm text-gray-400">Mia está construyendo la identidad de tu despacho. Toma unos segundos.</p>
      </div>
    );
  }

  if (soul !== null) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-12">
        <h1 className="mb-2 text-2xl font-semibold">Tu perfil esta listo</h1>
        <p className="mb-6 text-sm text-gray-500">Asi entiende Mia a tu despacho. Puedes ajustarlo cuando quieras.</p>
        <pre className="mb-6 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border border-gray-100 bg-gray-50 p-5 text-sm leading-relaxed text-gray-800">
          {soul}
        </pre>
        <div className="flex gap-3">
          <button
            onClick={() => {
              setSoul(null);
              setIdx(0);
              setStarted(true);
              setAlreadyDone(false);
            }}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
          >
            Editar
          </button>
          <button
            onClick={() => router.push("/")}
            className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700"
          >
            Continuar a mis asuntos
          </button>
        </div>
      </div>
    );
  }

  if (alreadyDone && !started) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-center">
        <h1 className="mb-3 text-2xl font-semibold">Tu despacho ya esta configurado</h1>
        <p className="mb-8 text-sm text-gray-500">
          Mia ya conoce tu identidad, tu voz y tus limites. Puedes revisarlos y actualizarlos.
        </p>
        <div className="flex justify-center gap-3">
          <button onClick={() => router.push("/")} className="rounded-lg px-5 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100">
            Ir a mis asuntos
          </button>
          <button
            onClick={() => {
              setStarted(true);
              setIdx(0);
            }}
            className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700"
          >
            Revisar mi perfil
          </button>
        </div>
        {error ? <p className="mt-6 text-sm text-red-600">{error}</p> : null}
      </div>
    );
  }

  if (!current) {
    return <div className="mx-auto max-w-2xl px-8 py-16 text-gray-400">{error || "No hay preguntas disponibles."}</div>;
  }

  const isLast = idx === total - 1;
  const value = answers[current.field];
  const pct = Math.round(((idx + 1) / total) * 100);
  const optional = !REQUIRED_IDS.has(current.id);
  const canAdvance = isComplete(current, value);

  return (
    <div className="mx-auto max-w-2xl px-8 py-12">
      <div className="mb-8">
        <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
          <span>
            {BLOCK_LABEL[current.block] ?? current.block} · Pregunta {idx + 1} de {total}
          </span>
          <span>{pct}%</span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-gray-100">
          <div className="h-full rounded-full bg-gray-900 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <h1 className="mb-1 text-center text-2xl font-semibold leading-snug">
        {current.question}
        {optional ? <span className="ml-2 align-middle text-sm font-normal text-gray-400">(opcional)</span> : null}
      </h1>
      {current.example ? (
        <p className="mb-6 text-center text-xs text-gray-400">Ej: {current.example}</p>
      ) : (
        <div className="mb-6" />
      )}

      <QuestionInput question={current} value={value} onChange={setAnswer} />

      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      <div className="mt-8 flex items-center justify-between">
        <button
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          disabled={idx === 0}
          className="rounded-lg px-5 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40"
        >
          Anterior
        </button>
        {isLast ? (
          <button
            onClick={finish}
            disabled={!canAdvance}
            className="rounded-lg bg-gray-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Finalizar
          </button>
        ) : (
          <button
            onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}
            disabled={!canAdvance}
            className="rounded-lg bg-gray-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Siguiente
          </button>
        )}
      </div>
      {!canAdvance ? (
        <p className="mt-3 text-right text-xs text-gray-400">Completa esta pregunta para continuar.</p>
      ) : null}
    </div>
  );
}

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: Question;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
}) {
  switch (question.id) {
    // P1 — dos campos: despacho + abogado.
    case "p1": {
      const n = asNamePair(value);
      return (
        <div className="space-y-3">
          <Field label="Nombre del despacho">
            <input
              value={n.firm}
              onChange={(e) => onChange({ ...n, firm: e.target.value })}
              className={inputCls}
              placeholder="Ej: Lexia Abogados S.A.S."
              autoFocus
            />
          </Field>
          <Field label="Tu nombre (abogado principal)">
            <input
              value={n.lawyer}
              onChange={(e) => onChange({ ...n, lawyer: e.target.value })}
              className={inputCls}
              placeholder="Ej: Juan Felipe Torres · T.P. 227.698"
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
            <input
              value={l.country}
              onChange={(e) => onChange({ ...l, country: e.target.value })}
              className={inputCls}
              placeholder="Ej: Colombia"
              autoFocus
            />
          </Field>
          <Field label="Ciudad">
            <input
              value={l.city}
              onChange={(e) => onChange({ ...l, city: e.target.value })}
              className={inputCls}
              placeholder="Ej: Bogotá"
            />
          </Field>
        </div>
      );
    }

    // P3 — 3 adjetivos de estilo (máx 3, con sugerencias).
    case "p3":
      return <TagInput value={asList(value)} onChange={onChange} suggestions={VOICE_SUGGESTIONS} max={3} placeholder="Escribe un adjetivo y presiona Enter" />;

    // P4 — canales (opcional, texto simple).
    case "p4":
      return <input value={asText(value)} onChange={(e) => onChange(e.target.value)} className={inputCls} placeholder="Ej: lexia.co — LinkedIn Lexia Abogados" autoFocus />;

    // P5 — jurisdicción (texto libre).
    case "p5":
      return <input value={asText(value)} onChange={(e) => onChange(e.target.value)} className={inputCls} placeholder="¿En qué país y sistema jurídico trabajas?" autoFocus />;

    // P6 — áreas de práctica (tags libres con sugerencias, sin límite).
    case "p6":
      return <TagInput value={asList(value)} onChange={onChange} suggestions={PRACTICE_SUGGESTIONS} placeholder="Escribe un área y presiona Enter" />;

    // P7 — tipo de cliente (checkboxes múltiples).
    case "p7":
      return <CheckboxGroup options={CLIENT_OPTIONS} value={asList(value)} onChange={onChange} />;

    // P10 — estructura de escritos (radio).
    case "p10":
      return <RadioGroup options={STRUCTURE_OPTIONS} value={asText(value)} onChange={onChange} />;

    // P11 — palabras prohibidas (tags libres).
    case "p11":
      return <TagInput value={asList(value)} onChange={onChange} placeholder="Escribe una palabra o frase y presiona Enter" />;

    // P14 — hard nos (tags con sugerencias).
    case "p14":
      return <TagInput value={asList(value)} onChange={onChange} suggestions={HARD_NO_SUGGESTIONS} placeholder="Escribe un límite y presiona Enter" />;

    // P15 — objetivo del año (una línea).
    case "p15":
      return <input value={asText(value)} onChange={(e) => onChange(e.target.value)} className={inputCls} placeholder="Una oración. Si se logra, el año fue exitoso." autoFocus />;

    // P16 — 3 pilares (tres campos separados).
    case "p16": {
      const pillars = asPillars(value);
      return (
        <div className="space-y-3">
          {pillars.map((pillar, index) => (
            <input
              key={index}
              value={pillar}
              onChange={(e) => {
                const next = [...pillars];
                next[index] = e.target.value;
                onChange({ pillars: next });
              }}
              className={inputCls}
              placeholder={`Pilar ${index + 1}`}
              autoFocus={index === 0}
            />
          ))}
        </div>
      );
    }

    // P17 — ritmo: días sin reuniones (L-V) + horario de trabajo profundo.
    case "p17": {
      const rhythm = asRhythm(value);
      return (
        <div className="space-y-5">
          <CheckboxGroup
            label="Días sin reuniones"
            options={WEEKDAYS}
            value={rhythm.no_meetings}
            onChange={(days) => onChange({ ...rhythm, no_meetings: days as string[] })}
          />
          <Field label="Horario de trabajo profundo">
            <input
              value={rhythm.hours}
              onChange={(e) => onChange({ ...rhythm, hours: e.target.value })}
              className={inputCls}
              placeholder="Ej: 7am-12pm"
            />
          </Field>
        </div>
      );
    }

    // P18 — herramientas (tags con sugerencias).
    case "p18":
      return <TagInput value={asList(value)} onChange={onChange} suggestions={TOOL_SUGGESTIONS} placeholder="Escribe una herramienta y presiona Enter" />;

    // P19 — triad mode (toggle grande + descripción + trigger condicional).
    case "p19": {
      const triad = asTriad(value);
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => onChange({ ...triad, enabled: !triad.enabled })}
            className={`flex w-full items-center justify-between rounded-xl border-2 px-5 py-4 text-left transition-colors ${
              triad.enabled ? "border-gray-900 bg-gray-900 text-white" : "border-gray-200 bg-white text-gray-700 hover:border-gray-400"
            }`}
          >
            <div>
              <div className="text-base font-semibold">Modo de análisis profundo</div>
              <div className={`mt-1 text-sm ${triad.enabled ? "text-gray-300" : "text-gray-500"}`}>
                Análisis profundo con múltiples modelos para casos de alta complejidad. Más tiempo y costo, mayor calidad.
              </div>
            </div>
            <span
              className={`ml-4 flex h-7 w-12 shrink-0 items-center rounded-full px-1 transition-colors ${
                triad.enabled ? "bg-white" : "bg-gray-300"
              }`}
            >
              <span className={`h-5 w-5 rounded-full transition-transform ${triad.enabled ? "translate-x-5 bg-gray-900" : "bg-white"}`} />
            </span>
          </button>
          {triad.enabled ? (
            <Field label="¿Cuándo activarlo?">
              <input
                value={triad.trigger}
                onChange={(e) => onChange({ ...triad, trigger: e.target.value })}
                className={inputCls}
                placeholder="Ej: imputaciones fiscales >$1.000M COP y arbitrajes"
                autoFocus
              />
            </Field>
          ) : null}
        </div>
      );
    }

    default:
      return <input value={asText(value)} onChange={(e) => onChange(e.target.value)} className={inputCls} placeholder="Tu respuesta..." autoFocus />;
  }
}

const inputCls = "w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm outline-none focus:border-gray-400";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-gray-500">{label}</span>
      {children}
    </label>
  );
}

function Spinner() {
  return <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-gray-900" />;
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
      <div className="rounded-lg border border-gray-200 px-3 py-2 focus-within:border-gray-400">
        {value.length > 0 ? (
          <div className="mb-2 flex flex-wrap gap-2">
            {value.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => onChange(value.filter((v) => v !== tag))}
                className="rounded-full bg-gray-900 px-3 py-1 text-xs font-medium text-white"
              >
                {tag} ×
              </button>
            ))}
          </div>
        ) : null}
        {atMax ? (
          <p className="py-1 text-xs text-gray-400">Máximo {max}. Quita uno para cambiarlo.</p>
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
            className="w-full py-1 text-sm outline-none"
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
              className="rounded-full border border-gray-300 px-3 py-1 text-xs text-gray-600 transition-colors hover:border-gray-900 hover:text-gray-900"
            >
              + {s}
            </button>
          ))}
        </div>
      ) : null}
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
      {label ? <div className="mb-2 text-xs font-medium uppercase text-gray-400">{label}</div> : null}
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const checked = value.includes(option);
          return (
            <label key={option} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2.5 text-sm">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  if (e.target.checked) onChange([...value, option]);
                  else onChange(value.filter((v) => v !== option));
                }}
                className="h-4 w-4 rounded border-gray-300"
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
        <label key={option} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2.5 text-sm">
          <input
            type="radio"
            checked={value === option}
            onChange={() => onChange(option)}
            className="h-4 w-4 border-gray-300"
          />
          <span>{option}</span>
        </label>
      ))}
    </div>
  );
}
