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
import { ArrowRight, Check, ChevronDown, Mail, Map, Minus, PartyPopper } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
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

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
        <p className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{error}</p>
      </div>
    );
  }
  if (!s) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-6 py-10 md:px-8">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-3 w-full rounded-full" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }

  const pct = Math.round((s.completados / Math.max(1, s.total)) * 100);
  const completo = s.completados >= s.total;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <header className="animate-slide-up">
        <h1 className="text-2xl font-semibold tracking-tight">Configura a Mia</h1>
        <p className="mt-1 text-sm text-muted-foreground">{s.mensaje}</p>
      </header>

      {/* Progreso: el abogado ve de un vistazo cuánto falta. */}
      <div className="mt-6 animate-slide-up" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
        <div className="flex items-center gap-3">
          <div
            role="progressbar"
            aria-valuenow={s.completados}
            aria-valuemin={0}
            aria-valuemax={s.total}
            aria-label={`Progreso de configuración: ${s.completados} de ${s.total} pasos listos`}
            className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted"
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary to-primary/80 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="shrink-0 text-sm font-medium tabular-nums text-muted-foreground">
            {s.completados} de {s.total}
          </span>
        </div>
        {completo ? (
          <p className="mt-3 flex items-center gap-2 rounded-xl border border-success/25 bg-success/10 px-4 py-3 text-sm font-medium text-success animate-fade-in">
            <PartyPopper className="h-4 w-4" />
            Mia quedó lista. Ya puedes trabajar con ella todos los días.
          </p>
        ) : null}
      </div>

      {skipMsg ? <p className="mt-4 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{skipMsg}</p> : null}

      <ul className="mt-6 space-y-3">
        {s.pasos.map((p, i) => (
          <li
            key={p.id}
            className={cn(
              "animate-slide-up rounded-xl border px-5 py-4 shadow-sm transition-colors",
              p.estado === "listo"
                ? "border-border bg-muted/40"
                : p.estado === "omitido"
                  ? "border-border bg-card/60"
                  : "border-border bg-card",
            )}
            style={{ animationDelay: `${100 + i * 45}ms`, animationFillMode: "backwards" }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2.5">
                  <span
                    aria-hidden
                    className={cn(
                      "flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                      p.estado === "listo"
                        ? "bg-success text-success-foreground"
                        : p.estado === "omitido"
                          ? "bg-muted text-muted-foreground"
                          : "border-2 border-primary/40 bg-primary/5 text-primary",
                    )}
                  >
                    {p.estado === "listo" ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : p.estado === "omitido" ? (
                      <Minus className="h-3.5 w-3.5" />
                    ) : (
                      <span className="text-xs font-semibold">{i + 1}</span>
                    )}
                  </span>
                  <span className={cn("font-medium", p.estado === "listo" && "text-muted-foreground")}>
                    {p.titulo}
                  </span>
                  <span className="sr-only">Estado: {ESTADO_TEXTO[p.estado]}</span>
                  {p.estado === "omitido" ? (
                    <span className="text-xs text-muted-foreground">(para después)</span>
                  ) : null}
                </div>
                <p className="mt-1.5 pl-[34px] text-sm text-muted-foreground">{p.detalle}</p>
                {p.guia && abierta === p.id ? (
                  <div className="ml-[34px] mt-3 space-y-2.5 rounded-lg bg-muted/60 px-4 py-3 text-sm animate-fade-in">
                    <p>
                      <span className="font-medium">¿Qué es?</span>{" "}
                      <span className="text-muted-foreground">{p.guia.que_es}</span>
                    </p>
                    <p>
                      <span className="font-medium">¿Para qué le sirve a tu despacho?</span>{" "}
                      <span className="text-muted-foreground">{p.guia.para_que}</span>
                    </p>
                    <div>
                      <p className="mb-1 font-medium">Cómo se hace, paso a paso:</p>
                      <ol className="list-inside list-decimal space-y-1 text-muted-foreground">
                        {p.guia.como.map((linea, j) => (
                          <li key={j}>{linea}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                {p.estado !== "listo" && p.enlace ? (
                  <Button asChild size="sm" className="gap-1.5">
                    <Link href={p.enlace}>
                      Ir al paso
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </Button>
                ) : null}
                {p.guia ? (
                  <Button
                    size="sm"
                    variant={p.estado === "listo" ? "ghost" : "outline"}
                    onClick={() => setAbierta((v) => (v === p.id ? null : p.id))}
                    aria-expanded={abierta === p.id}
                  >
                    {abierta === p.id ? "Ocultar guía" : "¿Qué es esto?"}
                  </Button>
                ) : null}
                {p.estado !== "listo" ? (
                  <button
                    onClick={() => toggleSkip(p)}
                    className="rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {p.estado === "omitido" ? "Retomar" : "Dejar para después"}
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <section className="mt-10 animate-slide-up rounded-xl border border-border bg-card p-5 shadow-sm" style={{ animationDelay: "200ms", animationFillMode: "backwards" }}>
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold tracking-tight">
          <Mail className="h-4 w-4 text-primary" />
          Calendario y correo
        </h2>
        <MailboxSectionLoader />
      </section>

      {s.secciones && s.secciones.length ? (
        <section className="mt-10">
          <h2 className="mb-1 flex items-center gap-2 text-base font-semibold tracking-tight">
            <Map className="h-4 w-4 text-primary" />
            ¿Qué hace cada sección de Mia?
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            El mapa de la casa: para qué sirve cada pantalla que ves en el menú.
          </p>
          <ul className="space-y-2">
            {s.secciones.map((sec) => (
              <li key={sec.titulo}>
                <details className="group rounded-xl border border-border bg-card shadow-sm transition-colors hover:border-primary/25">
                  <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 font-medium [&::-webkit-details-marker]:hidden">
                    {sec.titulo}
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="space-y-1.5 border-t border-border px-4 py-3 text-sm text-muted-foreground">
                    <p>{sec.que_es}</p>
                    <p>{sec.para_que}</p>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="mt-8 text-sm text-muted-foreground">
        Cada paso te lleva a la pantalla donde se hace. Cuando actives Telegram,
        también podrás pedirle ayuda a Mia desde el celular.
      </p>
    </div>
  );
}
