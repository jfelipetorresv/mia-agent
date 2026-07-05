"use client";

// CP-C4 · "Configura a Mia": el recorrido guiado para dejar a Mia completamente
// conectada sin saber nada técnico. El estado viene de GET /api/setup/status
// (solo lectura); cada paso enlaza a la pantalla donde se hace.
// CP-C4b · El recorrido EXPLICA como un onboarding: cada paso trae su guía
// (qué es, para qué sirve al despacho, cómo se hace paso a paso) y al final
// está el mapa de las secciones de Mia. La guía viene del servidor (fuente
// única: la misma que usa Mia al guiar por chat).

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import MailboxSectionLoader from "@/app/_components/MailboxSectionLoader";

type Guia = {
  que_es: string;
  para_que: string;
  como: string[];
};

type Paso = {
  id: string;
  titulo: string;
  estado: "listo" | "pendiente" | "omitido";
  detalle: string;
  accion: "automatica" | "guiada";
  enlace?: string | null;
  guia?: Guia | null;
};

type Seccion = {
  titulo: string;
  que_es: string;
  para_que: string;
};

type Status = {
  pasos: Paso[];
  secciones?: Seccion[];
  completados: number;
  total: number;
  siguiente: string | null;
  mensaje: string;
};

const ESTADO_TEXTO: Record<Paso["estado"], string> = {
  listo: "Listo",
  pendiente: "Pendiente",
  omitido: "Para después",
};

export default function ConfigurarPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);

  async function load() {
    try {
      setS(await apiGet<Status>("/api/setup/status"));
      setError("");
    } catch {
      setError("No se pudo cargar el estado de configuración. Recarga la página.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const [skipMsg, setSkipMsg] = useState("");

  async function toggleSkip(p: Paso) {
    setSkipMsg("");
    const action = p.estado === "omitido" ? "unskip" : "skip";
    try {
      await apiSend("POST", `/api/setup/steps/${p.id}/${action}`);
    } catch {
      setSkipMsg("No se pudo guardar el cambio. Intenta de nuevo.");
    }
    await load();
  }

  if (error) return <div className="p-10 text-sm text-amber-700">{error}</div>;
  if (!s) return <div className="p-10 text-gray-400">Cargando…</div>;

  const pct = Math.round((s.completados / Math.max(1, s.total)) * 100);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="mb-2 text-2xl font-semibold">Configura a Mia</h1>
      <p className="mb-6 text-sm text-gray-500">{s.mensaje}</p>

      <div className="mb-8">
        <div
          role="progressbar"
          aria-valuenow={s.completados}
          aria-valuemin={0}
          aria-valuemax={s.total}
          aria-label={`Progreso de configuración: ${s.completados} de ${s.total} pasos listos`}
          className="h-2 rounded-full bg-gray-100"
        >
          <div className="h-2 rounded-full bg-gray-900 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1 text-right text-xs text-gray-400">{s.completados} de {s.total} pasos listos</div>
      </div>

      {skipMsg ? <p className="mb-3 text-sm text-amber-700">{skipMsg}</p> : null}
      <ul className="space-y-3">
        {s.pasos.map((p) => (
          <li key={p.id} className={`rounded-xl border px-4 py-3 ${p.estado === "listo" ? "border-gray-100 bg-gray-50" : "border-gray-200"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      p.estado === "listo" ? "bg-green-600 text-white" : p.estado === "omitido" ? "bg-gray-200 text-gray-500" : "bg-gray-900 text-white"
                    }`}
                  >
                    {p.estado === "listo" ? "✓" : p.estado === "omitido" ? "–" : "·"}
                  </span>
                  <span className="font-medium">{p.titulo}</span>
                  <span className="sr-only">Estado: {ESTADO_TEXTO[p.estado]}</span>
                  {p.estado === "omitido" ? <span className="text-xs text-gray-400">(para después)</span> : null}
                </div>
                <p className="mt-1 text-sm text-gray-500">{p.detalle}</p>
                {p.guia && abierta === p.id ? (
                  <div className="mt-2 space-y-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600">
                    <p>
                      <span className="font-medium">¿Qué es?</span> {p.guia.que_es}
                    </p>
                    <p>
                      <span className="font-medium">¿Para qué le sirve a tu despacho?</span> {p.guia.para_que}
                    </p>
                    <div>
                      <p className="mb-1 font-medium">Cómo se hace, paso a paso:</p>
                      <ol className="list-inside list-decimal space-y-0.5">
                        {p.guia.como.map((linea, i) => (
                          <li key={i}>{linea}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {p.estado !== "listo" && p.enlace ? (
                  <Link href={p.enlace} className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700">
                    Ir al paso
                  </Link>
                ) : null}
                {p.guia ? (
                  <button
                    onClick={() => setAbierta((v) => (v === p.id ? null : p.id))}
                    aria-expanded={abierta === p.id}
                    className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                      p.estado === "listo"
                        ? "text-gray-500 hover:bg-gray-100"
                        : "bg-white text-gray-700 ring-1 ring-gray-300 hover:bg-gray-50"
                    }`}
                  >
                    {abierta === p.id ? "Ocultar guía" : "¿Qué es esto?"}
                  </button>
                ) : null}
                {p.estado !== "listo" ? (
                  <button onClick={() => toggleSkip(p)} className="rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100">
                    {p.estado === "omitido" ? "Retomar" : "Dejar para después"}
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <section className="mt-10 rounded-xl border border-gray-200 px-4 py-5">
        <h2 className="mb-3 text-lg font-semibold">Calendario y correo</h2>
        <MailboxSectionLoader />
      </section>

      {s.secciones && s.secciones.length ? (
        <section className="mt-10">
          <h2 className="mb-1 text-lg font-semibold">¿Qué hace cada sección de Mia?</h2>
          <p className="mb-4 text-sm text-gray-500">
            El mapa de la casa: para qué sirve cada pantalla que ves en el menú.
          </p>
          <ul className="space-y-2">
            {s.secciones.map((sec) => (
              <li key={sec.titulo} className="rounded-xl border border-gray-100 px-4 py-3">
                <details>
                  <summary className="cursor-pointer font-medium text-gray-800">{sec.titulo}</summary>
                  <div className="mt-2 space-y-1 text-sm text-gray-600">
                    <p>{sec.que_es}</p>
                    <p>{sec.para_que}</p>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="mt-6 text-sm text-gray-400">
        Cada paso te lleva a la pantalla donde se hace. Cuando actives Telegram,
        también podrás pedirle ayuda a Mia desde el celular.
      </p>
    </div>
  );
}
