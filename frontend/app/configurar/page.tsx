"use client";

// CP-C4 · "Configuración": el recorrido guiado para dejar a Mia completamente
// conectada sin saber nada técnico, ahora ademas HOGAR de toda la configuración
// del despacho (reestructuración 2026-07-09, feedback de Pipe: el Panel se
// quedaba con demasiada información que en realidad es configuración).
// El estado del recorrido viene de GET /api/setup/status (solo lectura); cada
// paso enlaza a la sección donde se hace. Debajo del recorrido viven las
// secciones: Conexiones, Carpetas, Automatizaciones, Valor y gasto, y —
// plegado— Procesos de fondo (información secundaria de "la salud de Mia").
//
// CP-C3 · reorganizada en subtabs de shadcn con deep-link por hash: cada
// sección vivía como <section id> + scroll nativo; ahora vive como TabsContent
// (el contenido inactivo no está en el DOM, así que el deep-link se resuelve
// seleccionando el tab, no haciendo scroll). Los anclas externas (setup.py,
// dashboard/page.tsx, FuentesPanel.tsx, OneDriveFolderPicker.tsx) siguen
// apuntando a /configurar#conexiones, #carpetas, #valor — por eso el mapa
// hash→tab conserva esos mismos ids.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Award,
  Bot,
  BookOpen,
  CalendarClock,
  Check,
  ChevronDown,
  FileText,
  HeartPulse,
  Lightbulb,
  Map,
  Minus,
  Moon,
  PartyPopper,
  PiggyBank,
  Repeat,
  ShieldCheck,
  Settings2,
  Sun,
  Laptop,
} from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getStoredTheme, setTheme, type Theme } from "@/lib/theme";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cardVariants } from "@/components/ui/card";
import { staggerStyle } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { PageShell } from "@/app/_components/PageShell";
import AsistentesSection from "@/app/_components/AsistentesSection";
import AutomationsSection from "@/app/_components/AutomationsSection";
import BancoOroSection from "@/app/_components/BancoOroSection";
import ConexionesSection from "@/app/_components/ConexionesSection";
import CarpetasSection from "@/app/_components/CarpetasSection";
import ValorGastoSection from "@/app/_components/ValorGastoSection";
import ProteccionDatosSection from "@/app/_components/ProteccionDatosSection";
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

// Los 5 subtabs de la página. Los ids coinciden con los anclas históricos
// (#conexiones, #carpetas, #automatizaciones, #valor) para que ningún enlace
// externo (setup.py, dashboard, FuentesPanel, OneDriveFolderPicker) se rompa.
type TabId =
  | "primeros-pasos"
  | "conexiones"
  | "carpetas"
  | "automatizaciones"
  | "valor"
  | "calidad"
  | "proteccion"
  | "sistema";

const HASH_TO_TAB: Record<string, TabId> = {
  "#primeros-pasos": "primeros-pasos",
  "#conexiones": "conexiones",
  "#carpetas": "carpetas",
  "#automatizaciones": "automatizaciones",
  "#valor": "valor",
  "#calidad": "calidad",
  "#proteccion": "proteccion",
  "#sistema": "sistema",
};

function tabFromHash(): TabId | null {
  if (typeof window === "undefined") return null;
  return HASH_TO_TAB[window.location.hash] ?? null;
}

export default function ConfigurarPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [currentTheme, setCurrentTheme] = useState<Theme>("system");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentTheme(getStoredTheme());
    }
  }, []);

  const handleThemeChange = (t: Theme) => {
    setTheme(t);
    setCurrentTheme(t);
  };

  // Lazy initializer: si se llega con un hash reconocido, ese tab manda desde
  // el primer render (evita el "flash" del tab por defecto). Si no hay hash,
  // arrancamos en "primeros-pasos" y, cuando cargue `s`, ajustamos el default
  // a "conexiones" si el recorrido ya estaba completo — pero solo si el
  // abogado no llegó con hash y no cambió de tab por su cuenta mientras tanto.
  const [tab, setTab] = useState<TabId>(() => tabFromHash() ?? "primeros-pasos");
  const hashOnMount = useRef(tabFromHash() !== null);
  const tabChangedByUser = useRef(false);

  function handleTabChange(v: string) {
    const id = v as TabId;
    setTab(id);
    tabChangedByUser.current = true;
    // replaceState (no pushState): cambiar de tab no debe ensuciar el historial.
    window.history.replaceState(null, "", `#${id}`);
  }

  // Cubre navegación con next/link hacia /configurar#valor estando YA en
  // /configurar (el <a>/<Link> solo cambia el hash, no remonta la página).
  useEffect(() => {
    function onHashChange() {
      const id = tabFromHash();
      if (id) setTab(id);
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!s || hashOnMount.current || tabChangedByUser.current) return;
    setTab(s.completados >= s.total ? "conexiones" : "primeros-pasos");
  }, [s]);

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
      <PageShell>
        <p className="rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{error}</p>
      </PageShell>
    );
  }
  if (!s) {
    return (
      <PageShell className="space-y-4">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-3 w-full rounded-full" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </PageShell>
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
            cardVariants(),
            "animate-slide-up px-5 py-4 transition-colors",
            p.estado === "listo"
              ? "bg-muted/40"
              : p.estado === "omitido"
                ? "bg-card/60"
                : "",
          )}
          style={staggerStyle(i, { base: 100 })}
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
                    <span className="text-meta font-semibold nums">{i + 1}</span>
                  )}
                </span>
                <span className={cn("text-section", p.estado === "listo" && "text-muted-foreground")}>
                  {p.titulo}
                </span>
                <span className="sr-only">Estado: {ESTADO_TEXTO[p.estado]}</span>
                {p.estado === "omitido" ? (
                  <span className="text-meta text-muted-foreground">(para después)</span>
                ) : null}
              </div>
              <p className="mt-1.5 pl-[34px] text-body text-muted-foreground">{p.detalle}</p>
              {p.guia && abierta === p.id ? (
                <div className="ml-[34px] mt-3 space-y-2.5 rounded-lg bg-muted/60 px-4 py-3 text-body animate-fade-in">
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
                  className="rounded-md px-2 py-1 text-meta text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
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
    <PageShell title="Configuración" subtitle={s.mensaje}>
      {skipMsg ? <p className="mt-4 rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{skipMsg}</p> : null}

      <Tabs value={tab} onValueChange={handleTabChange} className="mt-block">
        <TabsList className="h-auto flex-wrap justify-start gap-1">
          <TabsTrigger value="primeros-pasos" className="gap-1.5">
            {completo ? (
              <>
                <Check className="h-3.5 w-3.5" aria-hidden />
                Primeros pasos
              </>
            ) : (
              <>
                Primeros pasos · {s.completados} de {s.total}
              </>
            )}
          </TabsTrigger>
          <TabsTrigger value="conexiones" className="gap-1.5">
            <Settings2 className="h-4 w-4" />
            Conexiones
          </TabsTrigger>
          <TabsTrigger value="carpetas" className="gap-1.5">
            Carpetas
          </TabsTrigger>
          <TabsTrigger value="automatizaciones" className="gap-1.5">
            <Repeat className="h-4 w-4" />
            Automatizaciones
          </TabsTrigger>
          <TabsTrigger value="valor" className="gap-1.5">
            <PiggyBank className="h-4 w-4" />
            Valor y gasto
          </TabsTrigger>
          <TabsTrigger value="calidad" className="gap-1.5">
            <Award className="h-4 w-4" />
            Calidad
          </TabsTrigger>
          <TabsTrigger value="proteccion" className="gap-1.5">
            <ShieldCheck className="h-4 w-4" />
            Protección
          </TabsTrigger>
          <TabsTrigger value="sistema" className="gap-1.5">
            <Laptop className="h-4 w-4" />
            Sistema
          </TabsTrigger>
        </TabsList>

        {/* ── Primeros pasos ────────────────────────────────────────── */}
        <TabsContent value="primeros-pasos" className="animate-fade-in">
          {completo ? (
            <div className="mt-6 flex items-center gap-2 rounded-lg border border-success/25 bg-success/10 px-4 py-3 text-body font-medium text-success">
              <PartyPopper className="h-4 w-4" />
              Ya completaste los primeros pasos
            </div>
          ) : (
            <div className="mt-6">
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
                <span className="shrink-0 text-label nums text-muted-foreground">
                  {s.completados} de {s.total}
                </span>
              </div>
            </div>
          )}
          {pasosList}

          {s.secciones && s.secciones.length ? (
            <section className="mt-section">
              <SectionTitle
                icon={Map}
                title="¿Qué hace cada sección de Mia?"
                hint="El mapa de la casa: para qué sirve cada pantalla que ves en el menú."
              />
              <ul className="space-y-2">
                {s.secciones.map((sec) => (
                  <li key={sec.titulo}>
                    <details className={cn(cardVariants(), "group transition-colors hover:border-primary/25")}>
                      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-section [&::-webkit-details-marker]:hidden">
                        {sec.titulo}
                        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                      </summary>
                      <div className="space-y-1.5 border-t border-border px-4 py-3 text-body text-muted-foreground">
                        <p>{sec.que_es}</p>
                        <p>{sec.para_que}</p>
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <p className="mt-section text-body text-muted-foreground">
            Cada paso te lleva a la pantalla donde se hace. Cuando actives Telegram,
            también podrás pedirle ayuda a Mia desde el celular.
          </p>
        </TabsContent>

        {/* ── Conexiones ────────────────────────────────────────────── */}
        <TabsContent value="conexiones" className="animate-fade-in">
          <section id="conexiones" className="mt-6 scroll-mt-6">
            <SectionTitle
              icon={Settings2}
              title="Conexiones"
              hint="Lo que Mia puede usar para ayudarte. Todo se activa solo si tú lo decides."
            />
            <ConexionesSection connectors={c} onChanged={loadStats} />
          </section>

          {/* Los ayudantes externos son otra cosa que Mia "puede usar", así que viven
              aquí y no en un tab propio: lo que cambia es que son programas del propio
              equipo del abogado y que Mia solo los llama si él se lo pide por su nombre. */}
          <section id="asistentes" className="mt-section scroll-mt-6">
            <SectionTitle
              icon={Bot}
              title="Ayudantes externos"
              hint="Programas de tu equipo que Mia puede usar para una tarea puntual, solo si se lo pides."
            />
            <AsistentesSection />
          </section>
        </TabsContent>

        {/* ── Carpetas ──────────────────────────────────────────────── */}
        <TabsContent value="carpetas" className="animate-fade-in">
          <section id="carpetas" className="mt-6 scroll-mt-6">
            <CarpetasSection />
          </section>
        </TabsContent>

        {/* ── Automatizaciones ──────────────────────────────────────── */}
        <TabsContent value="automatizaciones" className="animate-fade-in">
          <section id="automatizaciones" className="mt-6 scroll-mt-6">
            <SectionTitle icon={Repeat} title="Automatizaciones" />
            <AutomationsSection />
          </section>
        </TabsContent>

        {/* ── Valor y gasto ─────────────────────────────────────────── */}
        <TabsContent value="valor" className="animate-fade-in">
          <section id="valor" className="mt-6 scroll-mt-6">
            <SectionTitle icon={PiggyBank} title="Valor y gasto del mes" />
            <ValorGastoSection value={stats?.value} onChanged={loadStats} />
          </section>

          {/* ── Procesos de fondo (información secundaria, plegada) ──── */}
          <details className={cn(cardVariants(), "mt-section group")}>
            <summary className="flex cursor-pointer items-center gap-3 px-5 py-4 text-section [&::-webkit-details-marker]:hidden">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                <HeartPulse className="h-4 w-4" />
              </span>
              <span className="flex-1">
                Procesos de fondo
                <span className="ml-2 text-meta font-normal text-muted-foreground">(La salud de Mia)</span>
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div className="border-t border-border px-5 py-4">
              <p className="mb-4 text-body text-muted-foreground">
                Cómo va el conocimiento que Mia construye de tu despacho y sus procesos de fondo.
              </p>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard icon={HeartPulse} label="Aprobación semanal" value={Math.round((brain.weekly_approval_rate || 0) * 100)} suffix="%" delay={0} />
                <StatCard icon={BookOpen} label="Conceptos" value={brain.concepts_count} delay={1} />
                <StatCard icon={Lightbulb} label="Habilidades activas" value={brain.skills_active} delay={2} />
                <StatCard icon={FileText} label="Habilidades archivadas" value={brain.skills_archived} delay={3} />
              </div>
              <p className="mt-3 text-body text-muted-foreground">Próxima consolidación: {fmt(brain.next_consolidation)}</p>

              {jobs.length > 0 ? (
                <ul className="mt-5 space-y-2">
                  {jobs.map((j, i) => (
                    <li key={i} className={cn(cardVariants(), "flex items-center justify-between gap-3 px-4 py-3 text-body")}>
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
        </TabsContent>

        {/* ── Calidad (Banco de oro) ────────────────────────────────
            Tab propio y no dentro de "Valor y gasto": aquello es dinero y esto es
            un examen de no-regresión. Mezclarlos haría creer que la calidad de Mia
            se mide en pesos. */}
        <TabsContent value="calidad" className="animate-fade-in">
          <section id="calidad" className="mt-6 scroll-mt-6">
            <SectionTitle
              icon={Award}
              title="Banco de oro"
              hint="El examen con el que compruebas que Mia no empeora."
            />
            <BancoOroSection />
          </section>
        </TabsContent>

        <TabsContent value="proteccion" className="animate-fade-in">
          <ProteccionDatosSection />
        </TabsContent>

        <TabsContent value="sistema" className="animate-fade-in">
          <section id="sistema" className="mt-6 scroll-mt-6 space-y-6">
            <SectionTitle
              icon={Laptop}
              title="Apariencia y Sistema"
              hint="Personaliza cómo se ve y responde la interfaz de tu despacho."
            />
            
            <div className={cn(cardVariants(), "p-6 space-y-6")}>
              <div className="space-y-2">
                <h3 className="font-bold text-lg">Tema de la Interfaz</h3>
                <p className="text-sm text-muted-foreground">
                  Elige entre el Modelo Claro (diseño neumórfico con relieve) y el Modelo Oscuro (diseño espacial profundo).
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 max-w-2xl">
                <button
                  type="button"
                  onClick={() => handleThemeChange("light")}
                  className={cn(
                    "flex flex-col items-center gap-3 rounded-2xl p-6 border transition-all shadow-sm bg-card/40 hover:bg-card/75",
                    currentTheme === "light"
                      ? "border-primary bg-primary/5 text-primary shadow-neu-raised"
                      : "border-border hover:border-primary/50 text-muted-foreground"
                  )}
                >
                  <Sun className="h-8 w-8" />
                  <div className="text-center">
                    <span className="block font-semibold text-sm">Modelo Claro</span>
                    <span className="block text-xs text-muted-foreground/80 mt-0.5">Limpio y tridimensional</span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleThemeChange("dark")}
                  className={cn(
                    "flex flex-col items-center gap-3 rounded-2xl p-6 border transition-all shadow-sm bg-card/40 hover:bg-card/75",
                    currentTheme === "dark"
                      ? "border-primary bg-primary/5 text-primary shadow-neu-raised"
                      : "border-border hover:border-primary/50 text-muted-foreground"
                  )}
                >
                  <Moon className="h-8 w-8" />
                  <div className="text-center">
                    <span className="block font-semibold text-sm">Modelo Oscuro</span>
                    <span className="block text-xs text-muted-foreground/80 mt-0.5">Espacial y de alto contraste</span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleThemeChange("system")}
                  className={cn(
                    "flex flex-col items-center gap-3 rounded-2xl p-6 border transition-all shadow-sm bg-card/40 hover:bg-card/75",
                    currentTheme === "system"
                      ? "border-primary bg-primary/5 text-primary shadow-neu-raised"
                      : "border-border hover:border-primary/50 text-muted-foreground"
                  )}
                >
                  <Laptop className="h-8 w-8" />
                  <div className="text-center">
                    <span className="block font-semibold text-sm">Tema del Sistema</span>
                    <span className="block text-xs text-muted-foreground/80 mt-0.5">Sincronizado con tu dispositivo</span>
                  </div>
                </button>
              </div>
            </div>
          </section>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
