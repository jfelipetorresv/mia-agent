"use client";

// CP-C4 · "Configuración": el recorrido guiado para dejar a Mia completamente
// conectada sin saber nada técnico, ahora ademas HOGAR de toda la configuración
// del despacho (reestructuración 2026-07-09, feedback de Pipe: el Panel se
// quedaba con demasiada información que en realidad es configuración).
// El estado del recorrido viene de GET /api/setup/status (solo lectura); cada
// paso enlaza a la sección donde se hace. Debajo del recorrido viven las
// secciones: Conexiones, Carpetas, Automatizaciones, Valor y gasto, y —
// plegado— Procesos de fondo (información secundaria de "la salud de Mia").

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CalendarClock,
  Check,
  ChevronDown,
  FileText,
  HeartPulse,
  Lightbulb,
  Map,
  Minus,
  PartyPopper,
  PiggyBank,
  Repeat,
  Settings2,
} from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import AutomationsSection from "@/app/_components/AutomationsSection";
import ConexionesSection from "@/app/_components/ConexionesSection";
import CarpetasSection from "@/app/_components/CarpetasSection";
import ValorGastoSection from "@/app/_components/ValorGastoSection";
import { SectionTitle, StatCard, fmt } from "@/app/_components/PanelUI";

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

// Datos que hoy solo expone GET /api/dashboard/stats (conexiones, valor, salud de
// Mia): la página los pide una vez y los reparte a las secciones que los necesitan.
type DashboardStats = {
  connectors?: {
    knowledge_base?: { active?: boolean; last_sync?: string | null; chunks?: number };
    external_store?: { active?: boolean; vectors_count?: number };
  };
  value?: {
    hours_saved?: number;
    hourly_rate_usd?: number;
    gross_usd?: number;
    cost_usd?: number;
    net_usd?: number;
    drafts_approved?: number;
    consultations?: number;
    is_default_config?: boolean;
  };
  scheduler_jobs?: { label: string; next_run?: string | null; last_run?: string | null }[];
  second_brain?: {
    weekly_approval_rate?: number;
    concepts_count?: number;
    skills_active?: number;
    skills_archived?: number;
    next_consolidation?: string | null;
  };
};

const ESTADO_TEXTO: Record<Paso["estado"], string> = {
  listo: "Listo",
  pendiente: "Pendiente",
  omitido: "Para después",
};

// Navegación interna de la página: chips que saltan a cada sección de configuración.
const SECCIONES_NAV = [
  { id: "conexiones", label: "Conexiones" },
  { id: "carpetas", label: "Carpetas" },
  { id: "automatizaciones", label: "Automatizaciones" },
  { id: "valor", label: "Valor y gasto" },
];

export default function ConfigurarPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);

  async function load() {
    try {
      setS(await apiGet<Status>("/api/setup/status"));
      setError("");
    } catch {
      setError("No se pudo cargar el estado de configuración. Recarga la página.");
    }
  }

  async function loadStats() {
    try {
      setStats(await apiGet<DashboardStats>("/api/dashboard/stats"));
    } catch {
      setStats(null);
    }
  }

  useEffect(() => {
    load();
    loadStats();
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
  const c = stats?.connectors || {};
  const brain = stats?.second_brain || {};
  const jobs = stats?.scheduler_jobs || [];

  const pasosList = (
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
  );

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <header className="animate-slide-up">
        <h1 className="text-2xl font-semibold tracking-tight">Configuración</h1>
        <p className="mt-1 text-sm text-muted-foreground">{s.mensaje}</p>
      </header>

      {skipMsg ? <p className="mt-4 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{skipMsg}</p> : null}

      {completo ? (
        <details className="mt-6 group rounded-xl border border-success/25 bg-success/10 shadow-sm animate-fade-in">
          <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-success [&::-webkit-details-marker]:hidden">
            <PartyPopper className="h-4 w-4" />
            Primeros pasos (completado)
            <ChevronDown className="ml-auto h-4 w-4 shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-success/25 px-4 py-3">
            {pasosList}
          </div>
        </details>
      ) : (
        <>
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
          </div>
          {pasosList}
        </>
      )}

      {/* ── Navegación de secciones ───────────────────────────────── */}
      <nav aria-label="Secciones de configuración" className="mt-10 flex flex-wrap gap-1.5">
        {SECCIONES_NAV.map((sec) => (
          <a
            key={sec.id}
            href={`#${sec.id}`}
            className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {sec.label}
          </a>
        ))}
      </nav>

      {/* ── Conexiones ────────────────────────────────────────────── */}
      <section id="conexiones" className="mt-8 scroll-mt-6">
        <SectionTitle
          icon={Settings2}
          title="Conexiones"
          hint="Lo que Mia puede usar para ayudarte. Todo se activa solo si tú lo decides."
        />
        <ConexionesSection connectors={c} onChanged={loadStats} />
      </section>

      {/* ── Carpetas ──────────────────────────────────────────────── */}
      <section id="carpetas" className="mt-12 scroll-mt-6">
        <CarpetasSection />
      </section>

      {/* ── Automatizaciones ──────────────────────────────────────── */}
      <section id="automatizaciones" className="mt-12 scroll-mt-6">
        <SectionTitle icon={Repeat} title="Automatizaciones" />
        <AutomationsSection />
      </section>

      {/* ── Valor y gasto ─────────────────────────────────────────── */}
      <section id="valor" className="mt-12 scroll-mt-6">
        <SectionTitle icon={PiggyBank} title="Valor y gasto del mes" />
        <ValorGastoSection value={stats?.value} onChanged={loadStats} />
      </section>

      {/* ── Procesos de fondo (información secundaria, plegada) ──── */}
      <details className="mt-12 group rounded-xl border border-border bg-card shadow-sm">
        <summary className="flex cursor-pointer items-center gap-3 px-5 py-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <HeartPulse className="h-4 w-4" />
          </span>
          <span className="flex-1">
            Procesos de fondo
            <span className="ml-2 text-xs font-normal text-muted-foreground">(La salud de Mia)</span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-border px-5 py-4">
          <p className="mb-4 text-sm text-muted-foreground">
            Cómo va el conocimiento que Mia construye de tu despacho y sus procesos de fondo.
          </p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard icon={HeartPulse} label="Aprobación semanal" value={Math.round((brain.weekly_approval_rate || 0) * 100)} suffix="%" delay={0} />
            <StatCard icon={BookOpen} label="Conceptos" value={brain.concepts_count} delay={1} />
            <StatCard icon={Lightbulb} label="Habilidades activas" value={brain.skills_active} delay={2} />
            <StatCard icon={FileText} label="Habilidades archivadas" value={brain.skills_archived} delay={3} />
          </div>
          <p className="mt-3 text-sm text-muted-foreground">Próxima consolidación: {fmt(brain.next_consolidation)}</p>

          {jobs.length > 0 ? (
            <ul className="mt-5 space-y-2">
              {jobs.map((j, i) => (
                <li key={i} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 text-sm shadow-sm">
                  <span className="flex items-center gap-2.5">
                    <CalendarClock className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {j.label}
                  </span>
                  <span className="shrink-0 text-muted-foreground">Próxima actualización: {fmt(j.next_run)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </details>

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
