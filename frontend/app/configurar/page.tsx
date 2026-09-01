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
//
// BLOQUE 3 DEL REDISEÑO LUXURY (2026-08-19) · DE OCHO PESTAÑAS A CINCO
// ====================================================================
// Ocho pestañas densas obligaban al abogado a adivinar en cuál vivía cada cosa
// ("¿el Banco de oro es calidad o es valor?", "¿el tema de la pantalla es
// sistema o es protección?"). Tres de ellas eran, en realidad, la mitad de otra:
//
//   Carpetas    → es una FUENTE que Mia puede usar, exactamente igual que el
//                 correo o las notas: vive dentro de Conexiones.
//   Calidad     → el Banco de oro es cómo compruebas que el trabajo automático
//                 no empeora: vive junto a las Automatizaciones.
//   Protección  → guardar la llave y el tema de la interfaz son las dos cosas
//   + Sistema     que dependen de ESTE computador: viven juntas.
//
// No se eliminó ninguna funcionalidad: cada sección conserva su `id`, así que
// TODOS los anclas históricos (#carpetas, #calidad, #proteccion, #asistentes)
// siguen resolviendo — ahora abriendo su pestaña nueva y bajando a la sección.
// Cada pestaña estrena una línea que dice para qué sirve, en el idioma del
// oficio, porque el nombre solo no alcanzaba.
//
// Encabezando Conexiones va la GALERÍA DE HERRAMIENTAS (GaleriaHerramientas):
// el reconocimiento a primera vista que pidió Pipe — Outlook, Gmail, OneDrive,
// Obsidian, Claude, Codex, Ollama, NotebookLM, Telegram — con el estado REAL de
// los endpoints que ya existían y un enlace a la tarjeta donde se hace la acción.

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
  Plug,
  Repeat,
  Settings2,
  Sun,
  Laptop,
} from "lucide-react";
import type { ComponentType } from "react";
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
import GaleriaHerramientas from "@/app/_components/GaleriaHerramientas";
import { NeuIcon, SectionTitle, StatCard, fmt } from "@/app/_components/PanelUI";

// Las tres apariencias. Vivían como tres <button> copiados con las clases
// escritas a mano (rounded-2xl, shadow-sm, border-border…): tres recetas del
// mismo objeto. Ahora son datos sobre la primitiva `Card` del sistema.
const TEMAS: { id: Theme; icon: ComponentType<{ className?: string }>; nombre: string; detalle: string }[] = [
  { id: "light", icon: Sun, nombre: "Claro", detalle: "Limpio y tridimensional" },
  { id: "dark", icon: Moon, nombre: "Oscuro", detalle: "Profundo y de alto contraste" },
  { id: "system", icon: Laptop, nombre: "El de tu equipo", detalle: "Cambia solo con tu computador" },
];

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
    /** `null` = la consolidación semanal no ha corrido nunca: NO es 0 %. */
    weekly_approval_rate?: number | null;
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

// Las 5 pestañas de la página, con la línea que dice para qué sirve cada una.
// Los ids son los cuatro anclas históricos más `sistema`: ningún enlace externo
// (setup.py, dashboard, FuentesPanel, OneDriveFolderPicker, ProtectionReminder)
// se rompe, porque el mapa de abajo traduce TODOS los hash de siempre.
type TabId = "primeros-pasos" | "conexiones" | "automatizaciones" | "valor" | "sistema";

// hash → { pestaña, sección a la que bajar }. Los anclas de las tres secciones
// que dejaron de tener pestaña propia (#carpetas, #calidad, #proteccion) abren
// su pestaña nueva y hacen scroll a la sección, que conserva su `id` intacto.
const HASH_TO_TAB: Record<string, { tab: TabId; anchor?: string }> = {
  "#primeros-pasos": { tab: "primeros-pasos" },
  "#conexiones": { tab: "conexiones" },
  "#carpetas": { tab: "conexiones", anchor: "carpetas" },
  "#asistentes": { tab: "conexiones", anchor: "asistentes" },
  "#automatizaciones": { tab: "automatizaciones" },
  "#calidad": { tab: "automatizaciones", anchor: "calidad" },
  "#valor": { tab: "valor" },
  "#proteccion": { tab: "sistema", anchor: "proteccion" },
  "#sistema": { tab: "sistema" },
};

const TAB_HINTS: Record<TabId, string> = {
  "primeros-pasos": "Lo que falta para dejar a Mia lista para trabajar contigo.",
  conexiones:
    "Todo lo que Mia puede usar: el motor con el que piensa, tu correo, tus carpetas, tus notas y los ayudantes de tu equipo. Nada se activa si tú no lo decides.",
  automatizaciones:
    "Lo que Mia hace sola, cada cuánto lo hace, y el examen con el que compruebas que su trabajo no empeora.",
  valor: "Cuánto trabajo te ahorró Mia este mes, cuánto costó y qué está haciendo por dentro.",
  sistema: "Cómo se ve Mia en este computador y cómo se protege lo que guardas aquí.",
};

function tabFromHash(): TabId | null {
  if (typeof window === "undefined") return null;
  return HASH_TO_TAB[window.location.hash]?.tab ?? null;
}

function anchorFromHash(): string | null {
  if (typeof window === "undefined") return null;
  return HASH_TO_TAB[window.location.hash]?.anchor ?? null;
}

// La sección solo existe en el DOM DESPUÉS de que su pestaña se activa: por eso
// el scroll se aplaza un frame en vez de hacerse en el mismo turno del render.
function scrollToAnchor(id: string | null) {
  if (!id || typeof window === "undefined") return;
  window.requestAnimationFrame(() => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

export default function ConfigurarPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);
  // Qué paso está desplegado. `null` = el que el backend señala como siguiente;
  // un id = el abogado eligió mirar otro, y esa elección manda hasta que la
  // cambie. Es distinto de `abierta`, que es la guía «¿Qué es esto?» dentro del
  // paso ya desplegado.
  const [expandido, setExpandido] = useState<string | null>(null);
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
      scrollToAnchor(anchorFromHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Llegada CON hash a una sección sin pestaña propia (#carpetas, #calidad,
  // #proteccion): la pestaña ya quedó elegida por el inicializador perezoso;
  // aquí solo hay que bajar a la sección cuando el contenido ya está montado.
  useEffect(() => {
    if (s) scrollToAnchor(anchorFromHash());
  }, [s]);

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

  // UN PASO ABIERTO A LA VEZ (corrección de Pipe, 2026-09-01)
  // ---------------------------------------------------------
  // Antes los siete pasos se mostraban abiertos, y cada uno ofrecía hasta tres
  // acciones —«Ir al paso», «¿Qué es esto?» y «Dejar para después»—: veintiún
  // controles compitiendo en una pantalla cuyo trabajo es decir QUÉ SIGUE.
  // Ahora lo hecho se colapsa a una línea con su palomita, el paso que sigue se
  // ve entero con sus acciones, y lo que queda es una lista corta que se puede
  // abrir. El backend ya dice cuál es el siguiente (`s.siguiente`); esta
  // pantalla no lo recalcula, solo respeta esa decisión, y `expandido` permite
  // al abogado abrir otro paso sin perder cuál era el siguiente.
  const abiertoId = expandido ?? s.siguiente ?? null;

  const pasosList = (
    <ul className="mt-6 space-y-2">
      {s.pasos.map((p, i) => {
        const abierto = p.id === abiertoId;
        const idPanel = `paso-panel-${p.id}`;

        // Un paso ya hecho: una sola línea. No tiene acciones porque no hay
        // nada que hacer en él, y ocupar media pantalla con eso empuja hacia
        // abajo lo único que sí pide trabajo.
        if (p.estado === "listo") {
          return (
            <li
              key={p.id}
              className="animate-slide-up flex items-center gap-2.5 px-5 py-2.5"
              style={staggerStyle(i, { base: 60 })}
            >
              <span
                aria-hidden
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground"
              >
                <Check className="h-3 w-3" />
              </span>
              <span className="min-w-0 flex-1 truncate text-body text-muted-foreground">
                {p.titulo}
              </span>
              <span className="sr-only">Estado: {ESTADO_TEXTO[p.estado]}</span>
            </li>
          );
        }

        // El paso abierto: la tarjeta completa, con su guía y sus acciones.
        if (abierto) {
          return (
            <li
              key={p.id}
              className={cn(
                cardVariants(),
                "animate-slide-up px-5 py-4 transition-colors",
                p.estado === "omitido" ? "bg-card/60" : "",
              )}
              style={staggerStyle(i, { base: 60 })}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <span
                      aria-hidden
                      className={cn(
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                        p.estado === "omitido"
                          ? "bg-muted text-muted-foreground"
                          : "border-2 border-primary/40 bg-primary/5 text-primary",
                      )}
                    >
                      {p.estado === "omitido" ? (
                        <Minus className="h-3.5 w-3.5" />
                      ) : (
                        <span className="text-meta font-semibold nums">{i + 1}</span>
                      )}
                    </span>
                    <span className="text-section">{p.titulo}</span>
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
                  {p.enlace ? (
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
                      variant="outline"
                      onClick={() => setAbierta((v) => (v === p.id ? null : p.id))}
                      aria-expanded={abierta === p.id}
                    >
                      {abierta === p.id ? "Ocultar guía" : "¿Qué es esto?"}
                    </Button>
                  ) : null}
                  <button
                    onClick={() => toggleSkip(p)}
                    className="rounded-md px-2 py-1 text-meta text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {p.estado === "omitido" ? "Retomar" : "Dejar para después"}
                  </button>
                </div>
              </div>
            </li>
          );
        }

        // Un paso que todavía no toca: fila corta y clicable. Se puede abrir sin
        // haber terminado el anterior — el orden es una sugerencia de Mia, no
        // una puerta cerrada.
        return (
          <li key={p.id} className="animate-slide-up" style={staggerStyle(i, { base: 60 })}>
            <button
              type="button"
              aria-expanded={false}
              aria-controls={idPanel}
              onClick={() => setExpandido(p.id)}
              className="flex w-full items-center gap-2.5 rounded-lg px-5 py-2.5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-meta font-semibold nums",
                  p.estado === "omitido"
                    ? "bg-muted text-muted-foreground"
                    : "border border-primary/30 text-primary",
                )}
              >
                {p.estado === "omitido" ? <Minus className="h-3 w-3" /> : i + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-body">{p.titulo}</span>
              <span className="sr-only">Estado: {ESTADO_TEXTO[p.estado]}</span>
              {p.estado === "omitido" ? (
                <span className="text-meta text-muted-foreground">(para después)</span>
              ) : null}
              <ArrowRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </button>
          </li>
        );
      })}
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
            <Plug className="h-4 w-4" />
            Conexiones
          </TabsTrigger>
          <TabsTrigger value="automatizaciones" className="gap-1.5">
            <Repeat className="h-4 w-4" />
            Trabajo automático
          </TabsTrigger>
          <TabsTrigger value="valor" className="gap-1.5">
            <PiggyBank className="h-4 w-4" />
            Valor y gasto
          </TabsTrigger>
          <TabsTrigger value="sistema" className="gap-1.5">
            <Laptop className="h-4 w-4" />
            Este equipo
          </TabsTrigger>
        </TabsList>

        {/* La línea que dice para qué sirve la pestaña abierta. El nombre solo no
            alcanzaba: "Valor y gasto" no le dice a nadie que ahí se ve cuánto
            trabajo le ahorró Mia este mes. */}
        <p className="mt-3 text-pretty text-body text-muted-foreground">{TAB_HINTS[tab]}</p>

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

          {/* El mapa de la casa dejó de vivir aquí, plegado (punto 15 de la bitácora
              2026-08-19): ahora es «Cómo funciona Mia», su propia pantalla, con el
              cuándo y el cómo de cada sección. Aquí queda la puerta, no una copia:
              dos textos del mismo tema en dos sitios se separan a la primera edición. */}
          <section className="mt-section">
            <SectionTitle
              icon={Map}
              title="¿Qué hace cada sección de Mia?"
              hint="El mapa de la casa: para qué sirve cada pantalla, cuándo te sirve y cómo se usa."
            />
            <Button asChild variant="outline" className="gap-1.5">
              <Link href="/ayuda">
                Abrir el manual
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </section>

          <p className="mt-section text-body text-muted-foreground">
            Cada paso te lleva a la pantalla donde se hace. Cuando actives Telegram,
            también podrás pedirle ayuda a Mia desde el celular.
          </p>
        </TabsContent>

        {/* ── Conexiones ────────────────────────────────────────────── */}
        <TabsContent value="conexiones" className="animate-fade-in">
          {/* La galería va PRIMERO: el abogado reconoce su Outlook o su Obsidian por
              el logo antes de leer una sola palabra, y desde ahí baja a la tarjeta
              donde de verdad se conecta. Detrás no hay estados inventados: cada
              tarjeta lee el endpoint que ya servía ese dato. */}
          <section id="herramientas" className="mt-6 scroll-mt-6">
            <SectionTitle
              icon={Plug}
              title="Tus herramientas"
              hint="Mia reconoce sola lo que ya tienes en este equipo. Lo que no encuentre, te lo dice con su motivo — nunca lo da por hecho."
            />
            <GaleriaHerramientas />
          </section>

          <section id="conexiones" className="mt-section scroll-mt-6">
            <SectionTitle
              icon={Settings2}
              title="Configurar cada conexión"
              hint="El detalle de cada una: activarla, cambiarla o desconectarla."
            />
            <ConexionesSection connectors={c} onChanged={loadStats} />
          </section>

          {/* Las carpetas son una FUENTE más de las que Mia lee, igual que el correo
              o las notas: tenían pestaña propia y eso obligaba a buscarlas aparte.
              El `id` no cambia, así que /configurar#carpetas sigue funcionando. */}
          <section id="carpetas" className="mt-section scroll-mt-6">
            <CarpetasSection />
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

        {/* ── Trabajo automático (automatizaciones + Banco de oro) ────
            El Banco de oro tenía pestaña propia para no mezclarlo con el dinero;
            ese riesgo sigue evitado — aquí no hay pesos, hay trabajo que Mia hace
            sola y el examen con el que se comprueba que no empeora. */}
        <TabsContent value="automatizaciones" className="animate-fade-in">
          <section id="automatizaciones" className="mt-6 scroll-mt-6">
            <SectionTitle
              icon={Repeat}
              title="Automatizaciones"
              hint="Tareas que Mia repite sola para que no tengas que acordarte de pedirlas."
            />
            <AutomationsSection />
          </section>

          <section id="calidad" className="mt-section scroll-mt-6">
            <SectionTitle
              icon={Award}
              title="Banco de oro"
              hint="El examen con el que compruebas que Mia no empeora."
            />
            <BancoOroSection />
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
                {/* NO MEDIBLE, no 0 %: `|| 0` convertía «la consolidación semanal
                    todavía no ha corrido» en «aprobaste el 0 % de lo que Mia propuso»,
                    que es una afirmación falsa sobre el despacho. El servidor ahora
                    manda null mientras no haya medición y aquí se dice por qué. */}
                <StatCard
                  icon={HeartPulse}
                  label="Aprobación semanal"
                  value={
                    brain.weekly_approval_rate == null
                      ? null
                      : Math.round(brain.weekly_approval_rate * 100)
                  }
                  suffix="%"
                  sinMedir="la primera consolidación semanal aún no ha corrido"
                  nota="Cuánto de lo que Mia propuso aprobaste"
                  delay={0}
                />
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

        {/* ── Este equipo (apariencia + protección de datos) ──────────
            Las dos cosas que dependen de ESTE computador y de nadie más: cómo se
            ve Mia aquí y cómo se protege lo que aquí se guarda. Eran dos pestañas
            y ninguna de las dos se buscaba por su nombre. */}
        <TabsContent value="sistema" className="animate-fade-in">
          <section id="sistema" className="mt-6 scroll-mt-6">
            <SectionTitle
              icon={Laptop}
              title="Cómo se ve Mia"
              hint="Elige el aspecto de la interfaz. Se aplica solo en este computador."
            />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {TEMAS.map(({ id, icon: Icon, nombre, detalle }) => {
                const activo = currentTheme === id;
                return (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={activo}
                    onClick={() => handleThemeChange(id)}
                    className={cn(
                      cardVariants({ variant: "raised", padding: "md" }),
                      "flex flex-col items-center gap-3 bg-card/80 text-center backdrop-blur-md",
                      activo ? "border-cta/30 bg-cta/5 text-primary" : "text-muted-foreground",
                    )}
                  >
                    <NeuIcon icon={Icon} tone={activo ? "cta" : "muted"} />
                    <span>
                      <span className="block text-section text-foreground">{nombre}</span>
                      <span className="mt-0.5 block text-meta text-muted-foreground">{detalle}</span>
                    </span>
                    <span className="text-meta font-medium">
                      {activo ? "En uso" : "Usar este"}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Conserva su propio `id="proteccion"`: /configurar#proteccion, que usa el
              recordatorio del escritorio (ProtectionReminder), sigue llegando aquí. */}
          <div className="mt-section">
            <ProteccionDatosSection />
          </div>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
