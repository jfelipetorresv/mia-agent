"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/api";

type Question = {
  id: string;
  block: string;
  field: string;
  question: string;
  example: string;
};

type AnswerValue =
  | string
  | string[]
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

const TEXT_IDS = new Set(["p1", "p2", "p4", "p5", "p8", "p9", "p12", "p13", "p14", "p15"]);
const TAG_IDS = new Set(["p3", "p6", "p7", "p11", "p18"]);

const SELECT_OPTIONS: Record<string, string[]> = {
};

const CHECKBOX_OPTIONS: Record<string, string[]> = {
};

const STRUCTURE_OPTIONS = ["Narrativo continuo", "Estructurado con secciones", "Depende del tipo de escrito"];
const DAYS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"];

function asText(value: AnswerValue | undefined): string {
  return typeof value === "string" ? value : "";
}

function asList(value: AnswerValue | undefined): string[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim()) return value.split(",").map((v) => v.trim()).filter(Boolean);
  return [];
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

      <h1 className="mb-3 text-center text-2xl font-semibold leading-snug">{current.question}</h1>
      <p className="mb-5 rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-500">
        <span className="font-medium text-gray-600">Ejemplo: </span>
        {current.example}
      </p>

      <QuestionInput question={current} value={value} onChange={setAnswer} />

      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      <div className="mt-8 flex items-center justify-between">
        <button
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          disabled={idx === 0}
          className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40"
        >
          Anterior
        </button>
        {isLast ? (
          <button
            onClick={finish}
            disabled={submitting}
            className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {submitting ? "Generando tu perfil..." : "Finalizar"}
          </button>
        ) : (
          <button onClick={() => setIdx((i) => Math.min(total - 1, i + 1))} className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700">
            Siguiente
          </button>
        )}
      </div>
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
  if (TAG_IDS.has(question.id)) return <TagInput value={asList(value)} onChange={onChange} />;

  if (SELECT_OPTIONS[question.id]) {
    return (
      <select
        value={asText(value)}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
        autoFocus
      >
        <option value="">Selecciona una opcion</option>
        {SELECT_OPTIONS[question.id].map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (CHECKBOX_OPTIONS[question.id]) {
    return <CheckboxGroup options={CHECKBOX_OPTIONS[question.id]} value={asList(value)} onChange={onChange} />;
  }

  if (question.id === "p10") {
    return <RadioGroup options={STRUCTURE_OPTIONS} value={asText(value)} onChange={onChange} />;
  }

  if (question.id === "p16") {
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
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
            placeholder={`Pilar ${index + 1}`}
            autoFocus={index === 0}
          />
        ))}
      </div>
    );
  }

  if (question.id === "p17") {
    const rhythm = asRhythm(value);
    return (
      <div className="space-y-5">
        <CheckboxGroup
          label="Dias sin reuniones"
          options={DAYS}
          value={rhythm.no_meetings}
          onChange={(days) => onChange({ ...rhythm, no_meetings: days as string[] })}
        />
        <input
          value={rhythm.hours}
          onChange={(e) => onChange({ ...rhythm, hours: e.target.value })}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          placeholder="Horario en el que trabajas mejor"
        />
      </div>
    );
  }

  if (question.id === "p19") {
    const triad = asTriad(value);
    return (
      <div className="space-y-4">
        <label className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
          <span className="text-sm font-medium text-gray-700">Habilitar modo de analisis profundo</span>
          <input
            type="checkbox"
            checked={triad.enabled}
            onChange={(e) => onChange({ ...triad, enabled: e.target.checked })}
            className="h-5 w-5 rounded border-gray-300"
          />
        </label>
        {triad.enabled ? (
          <textarea
            value={triad.trigger}
            onChange={(e) => onChange({ ...triad, trigger: e.target.value })}
            className="h-24 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
            placeholder="Cuando debe activarse"
          />
        ) : null}
      </div>
    );
  }

  if (TEXT_IDS.has(question.id)) {
    return (
      <textarea
        value={asText(value)}
        onChange={(e) => onChange(e.target.value)}
        className="h-32 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
        placeholder="Tu respuesta..."
        autoFocus
      />
    );
  }

  return (
    <textarea
      value={asText(value)}
      onChange={(e) => onChange(e.target.value)}
      className="h-32 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
      placeholder="Tu respuesta..."
      autoFocus
    />
  );
}

function TagInput({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const [draft, setDraft] = useState("");

  function addTag() {
    const tag = draft.trim();
    if (!tag || value.includes(tag)) return;
    onChange([...value, tag]);
    setDraft("");
  }

  return (
    <div className="rounded-lg border border-gray-200 px-3 py-2 focus-within:border-gray-400">
      <div className="mb-2 flex flex-wrap gap-2">
        {value.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => onChange(value.filter((v) => v !== tag))}
            className="rounded-full bg-gray-900 px-3 py-1 text-xs font-medium text-white"
          >
            {tag} x
          </button>
        ))}
      </div>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            addTag();
          }
        }}
        onBlur={addTag}
        className="w-full text-sm outline-none"
        placeholder="Escribe y presiona Enter"
        autoFocus
      />
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
            <label key={option} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm">
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
        <label key={option} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm">
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
