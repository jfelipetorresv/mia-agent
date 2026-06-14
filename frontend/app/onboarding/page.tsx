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

type Status = {
  completed: boolean;
  last_updated: string | null;
  responses?: Record<string, string>;
};

const BLOCK_LABEL: Record<string, string> = {
  identity: "Identidad",
  jurisdiction: "Jurisdicción",
  legal_voice: "Voz jurídica",
  mission_rhythm: "Misión y ritmo",
  triad_mode: "Modo profundo",
};

// Campos cortos → input de una línea; el resto → textarea.
const SHORT_FIELDS = new Set(["identity.location", "identity.channels"]);

export default function OnboardingPage() {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
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
          setStarted(true); // primera vez: arranca la entrevista directamente
        }
      } catch {
        setError("No se pudo cargar la entrevista. ¿Está el servidor encendido?");
      }
      setLoading(false);
    })();
  }, []);

  const total = questions.length;
  const current = questions[idx];

  function setAnswer(value: string) {
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
    return <div className="mx-auto max-w-2xl px-8 py-16 text-gray-400">Cargando…</div>;
  }

  // Resultado: el SOUL.md generado.
  if (soul !== null) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-12">
        <h1 className="mb-2 text-2xl font-semibold">Tu perfil está listo</h1>
        <p className="mb-6 text-sm text-gray-500">
          Así entiende Mia a tu despacho. Puedes ajustarlo cuando quieras.
        </p>
        <pre className="mb-6 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-gray-100 bg-gray-50 p-5 text-sm leading-relaxed text-gray-800">
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

  // Pantalla de entrada cuando el onboarding ya se completó antes.
  if (alreadyDone && !started) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-center">
        <h1 className="mb-3 text-2xl font-semibold">Tu despacho ya está configurado</h1>
        <p className="mb-8 text-sm text-gray-500">
          Mia ya conoce tu identidad, tu voz y tus límites. Puedes revisarlos y actualizarlos.
        </p>
        <div className="flex justify-center gap-3">
          <button
            onClick={() => router.push("/")}
            className="rounded-lg px-5 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
          >
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
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-gray-400">
        {error || "No hay preguntas disponibles."}
      </div>
    );
  }

  const isLast = idx === total - 1;
  const value = answers[current.field] ?? "";
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
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
          <div className="h-full rounded-full bg-gray-900 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <h1 className="mb-3 text-xl font-semibold leading-snug">{current.question}</h1>
      <p className="mb-5 rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-500">
        <span className="font-medium text-gray-600">Ejemplo: </span>
        {current.example}
      </p>

      {SHORT_FIELDS.has(current.field) ? (
        <input
          value={value}
          onChange={(e) => setAnswer(e.target.value)}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          placeholder="Tu respuesta…"
          autoFocus
        />
      ) : (
        <textarea
          value={value}
          onChange={(e) => setAnswer(e.target.value)}
          className="h-32 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          placeholder="Tu respuesta… (puedes dejarla en blanco si no aplica)"
          autoFocus
        />
      )}

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
            {submitting ? "Generando tu perfil…" : "Finalizar"}
          </button>
        ) : (
          <button
            onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}
            className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700"
          >
            Siguiente
          </button>
        )}
      </div>
    </div>
  );
}
