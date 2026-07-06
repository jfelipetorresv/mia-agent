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
  | { no_meetings: string[]; hours: string }
  | { enabled: boolean; trigger: string };

type Status = {
  completed: boolean;
  last_updated: string | null;
  responses?: Record<string, AnswerValue>;
};

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
  { name: "Notas (Obsidian)", description: "Mia guarda y consulta tus notas.", comingSoon: true },
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
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [completion, setCompletion] = useState<CompletionResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [qs, st] = await Promise.all([
          apiGet<Question[]>("/api/onboarding/questions"),
          apiGet<Status>("/api/onboarding/status"),
        ]);
        setQuestions(qs.filter((q) => !HIDDEN_QUESTION_IDS.has(q.id)));
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
      const res = await apiSend<CompletionResult>("POST", "/api/onboarding/complete", { responses: answers });
      setCompletion(res);
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

  if (completion !== null) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-12">
        <div className="mb-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <h1 className="mb-4 text-2xl font-semibold text-gray-900">Tu perfil está listo</h1>
          <SummaryMarkdown markdown={completion.summary} />
        </div>
        <details className="mb-6 rounded-lg border border-gray-100 bg-gray-50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-600 hover:text-gray-900">
            Ver detalle técnico
          </summary>
          <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap border-t border-gray-100 px-4 py-3 text-xs leading-relaxed text-gray-600">
            {completion.soul_content}
          </pre>
        </details>
        <div className="flex gap-3">
          <button
            onClick={() => {
              setCompletion(null);
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

function SummaryMarkdown({ markdown }: { markdown: string }) {
  const elements: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  let key = 0;

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${key++}`} className="space-y-2 text-sm leading-relaxed text-gray-700">
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
        <h2 key={`h-${key++}`} className="mb-4 text-lg font-semibold text-gray-900">
          {line.slice(4)}
        </h2>
      );
      continue;
    }

    const bullet = line.match(bulletRe);
    if (bullet) {
      listItems.push(
        <li key={`li-${key++}`}>
          <span className="font-medium text-gray-900">{bullet[1]}:</span> {bullet[2]}
        </li>
      );
      continue;
    }

    const rules = line.match(rulesRe);
    if (rules) {
      listItems.push(
        <li key={`li-${key++}`} className="font-medium text-gray-900">
          {rules[1]}:
        </li>
      );
      continue;
    }

    const sub = line.match(subRe);
    if (sub) {
      listItems.push(
        <li key={`li-${key++}`} className="ml-4 list-disc text-gray-600">
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
      <p key={`p-${key++}`} className="text-sm leading-relaxed text-gray-600">
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
              placeholder="Ej: tu país"
              autoFocus
            />
          </Field>
          <Field label="Ciudad">
            <input
              value={l.city}
              onChange={(e) => onChange({ ...l, city: e.target.value })}
              className={inputCls}
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

    // P18 — herramientas (lista curada con descripción).
    case "p18":
      return <ToolsChecklist value={asList(value)} onChange={onChange} />;

    // P19 (triad_mode) se retiró de la UI — Riesgo #27: no ofrecer lo no implementado.

    default: {
      if (TEXT_IDS.has(question.id)) {
        return (
          <input
            value={asText(value)}
            onChange={(e) => onChange(e.target.value)}
            className={inputCls}
            placeholder="Tu respuesta..."
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
        <input
          value={asText(value)}
          onChange={(e) => onChange(e.target.value)}
          className={inputCls}
          placeholder="Tu respuesta..."
          autoFocus
        />
      );
    }
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
            className={`flex gap-3 rounded-lg border px-4 py-3 ${
              disabled ? "cursor-not-allowed border-gray-100 bg-gray-50 opacity-70" : "cursor-pointer border-gray-200 hover:border-gray-300"
            }`}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled}
              onChange={(e) => toggle(tool.name, e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-gray-300"
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-gray-900">
                {tool.name}
                {tool.comingSoon ? (
                  <span className="ml-2 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-normal text-amber-700">Próximamente</span>
                ) : null}
              </span>
              <span className="mt-0.5 block text-sm text-gray-500">{tool.description}</span>
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
              className="rounded-full bg-gray-900 px-3 py-1 text-xs font-medium text-white"
            >
              {tool} ×
            </button>
          ))}
        </div>
      ) : null}

      <Field label="Otra herramienta">
        <div className="flex gap-2">
          <input
            value={customDraft}
            onChange={(e) => setCustomDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            className={inputCls}
            placeholder="Escribe el nombre y presiona Enter"
          />
          <button
            type="button"
            onClick={addCustom}
            disabled={!customDraft.trim()}
            className="shrink-0 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
          >
            Añadir
          </button>
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
