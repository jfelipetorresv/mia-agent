"use client";

// Mia · Panel del despacho — reestructurado (feedback de Pipe 2026-07-09): el
// Panel muestra SOLO lo accionable del día. Todo lo demás (conexiones, carpetas,
// automatizaciones, formularios de tarifa/tope, salud interna de Mia) vive ahora
// en Configuración (/configurar).

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BellRing,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileText,
  FolderOpen,
  ListChecks,
  Sparkles,
} from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyHint, SectionTitle, StatCard, fmtHora } from "@/app/_components/PanelUI";

type Stats = {
  matters_active?: number;
  documents_indexed?: number;
  proposals_pending?: number;
  // CP-V1 · valor entregado del mes (horas ahorradas × tarifa − costo de IA).
  value?: {
    hours_saved?: number;
    net_usd?: number;
    drafts_approved?: number;
  };
};

type Reminder = { id: string; text: string; due_at: string; is_procedural: boolean };

// CP-E1 · tope de gasto de IA mensual (GET /api/policy/budget) — el Panel solo
// necesita saber si ya se pasó, para la alerta; el formulario vive en Configuración.
type BudgetStatus = { over_budget: boolean };

// CP-V2 · recomendaciones del auto-diagnóstico semanal (GET /api/dreams/prescriptions).
type Prescription = {
  id: string;
  category: string;
  headline: string;
  prescription: string;
  evidence: string[];
  dollar_impact: number | null;
  time_impact_mins: number | null;
  status: "new" | "recurring";
  age_days: number;
};

// Asuntos con un borrador esperando aprobación (GET /api/matters → pending_review):
// es la única fuente que hoy relaciona "algo pendiente" con un asunto concreto.
type Matter = { id: string; name: string; pending_review?: boolean };

export default function DashboardPage() {
  const [s, setS] = useState<Stats | null>(null);
  // CP-B3: recordatorios pendientes del despacho.
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [reminderMsg, setReminderMsg] = useState("");
  // CP-E1: solo la alerta; el formulario del tope vive en Configuración.
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  // CP-V2: recomendaciones del auto-diagnóstico semanal.
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [prescriptionsLoaded, setPrescriptionsLoaded] = useState(false);
  const [expandedRx, setExpandedRx] = useState<string | null>(null);
  const [rxMsg, setRxMsg] = useState("");
  const [rxBusy, setRxBusy] = useState<string | null>(null);
  // Asuntos con borrador pendiente, para la tarjeta "Para tu decisión".
  const [pendingMatters, setPendingMatters] = useState<Matter[]>([]);

  async function loadBudget() {
    try {
      setBudget(await apiGet<BudgetStatus>("/api/policy/budget"));
    } catch {
      setBudget(null);
    }
  }

  async function loadPrescriptions() {
    try {
      const data = await apiGet<{ prescriptions: Prescription[] }>("/api/dreams/prescriptions");
      setPrescriptions(data.prescriptions || []);
    } catch {
      setPrescriptions([]);
    } finally {
      setPrescriptionsLoaded(true);
    }
  }

  async function loadPendingMatters() {
    try {
      const matters = await apiGet<Matter[]>("/api/matters");
      setPendingMatters((matters || []).filter((m) => m.pending_review));
    } catch {
      setPendingMatters([]);
    }
  }

  async function load() {
    const data = await apiGet<Stats>("/api/dashboard/stats");
    setS(data);
    apiGet<Reminder[]>("/api/assistant/reminders").then(setReminders).catch(() => setReminders([]));
    loadBudget();
    loadPrescriptions();
    loadPendingMatters();
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  // CP-V2: el abogado acepta o descarta una recomendación; desaparece de la lista.
  async function decidePrescription(id: string, action: "accept" | "dismiss") {
    setRxMsg("");
    setRxBusy(id);
    try {
      await apiSend("POST", `/api/dreams/prescriptions/${id}/decision`, { action });
      setPrescriptions((items) => items.filter((p) => p.id !== id));
      if (expandedRx === id) setExpandedRx(null);
    } catch (err: unknown) {
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setRxMsg(msg || "No se pudo registrar tu decisión. Intenta de nuevo.");
      await loadPrescriptions();
    } finally {
      setRxBusy(null);
    }
  }

  async function cancelReminder(id: string) {
    // Solo se quita de la lista si el servidor CONFIRMÓ la cancelación — un
    // recordatorio ligado a un plazo jamás debe "desaparecer" sin cancelarse.
    setReminderMsg("");
    try {
      await apiSend("POST", `/api/assistant/reminders/${id}/cancel`);
      setReminders((rs) => rs.filter((r) => r.id !== id));
    } catch {
      setReminderMsg("No se pudo cancelar el recordatorio. Intenta de nuevo.");
    }
  }

  if (!s) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-10 md:px-8">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }

  // Las dos colas que piden decisión del abogado: borradores por revisar (por
  // asunto) y sugerencias de mejora de Mia (se revisan en Conocimiento).
  const decisiones = pendingMatters.length + (s.proposals_pending || 0);

  return (
    <div className="bg-aurora mx-auto max-w-5xl px-6 py-10 md:px-8">
      {/* Encabezado con resumen en llano: el panel saluda con lo que importa hoy. */}
      <header className="animate-slide-up">
        <h1 className="text-gradient-brand text-2xl font-semibold tracking-tight">Panel del despacho</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {s.matters_active || 0} {s.matters_active === 1 ? "asunto activo" : "asuntos activos"}
          {decisiones > 0
            ? ` · ${decisiones} ${decisiones === 1 ? "decisión esperando" : "decisiones esperando"}`
            : " · todo al día"}
        </p>
      </header>

      {/* ── Para tu decisión ──────────────────────────────────────── */}
      {decisiones > 0 ? (
        <section className="mt-8 animate-slide-up rounded-xl border border-cta/30 bg-cta/5 p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cta/15 text-cta-strong">
              <ListChecks className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold tracking-tight">Para tu decisión</h2>
              {pendingMatters.length > 0 ? (
                <>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {pendingMatters.length === 1
                      ? "Este asunto tiene un borrador esperando tu revisión:"
                      : `${pendingMatters.length} asuntos tienen un borrador esperando tu revisión:`}
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {pendingMatters.slice(0, 5).map((m) => (
                      <li key={m.id}>
                        <Link
                          href={`/asuntos/${m.id}/revisar`}
                          className="group flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary"
                        >
                          {m.name}
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {pendingMatters.length > 5 ? (
                    <p className="mt-1.5 text-xs text-muted-foreground">y {pendingMatters.length - 5} más…</p>
                  ) : null}
                </>
              ) : null}
              {(s.proposals_pending || 0) > 0 ? (
                <p className={`${pendingMatters.length > 0 ? "mt-3" : "mt-1"} text-sm text-muted-foreground`}>
                  {pendingMatters.length > 0 ? "Además, " : ""}Mia tiene {s.proposals_pending}{" "}
                  {s.proposals_pending === 1 ? "sugerencia de mejora" : "sugerencias de mejora"} para tu
                  aprobación en{" "}
                  <Link href="/memoria" className="font-medium text-foreground underline underline-offset-2 hover:text-primary">
                    Conocimiento
                  </Link>
                  .
                </p>
              ) : null}
              {pendingMatters.length > 0 ? (
                <Button asChild variant="cta" size="sm" className="mt-4 gap-1.5">
                  <Link href="/">
                    Ver asuntos
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      {/* ── Alerta de tope de gasto ───────────────────────────────── */}
      {budget?.over_budget ? (
        <section className="mt-8 animate-slide-up rounded-xl border border-warning/30 bg-warning/10 p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-warning">
                Se alcanzó el tope de gasto de este mes; los turnos están en pausa.
              </p>
              <Link href="/configurar#valor" className="mt-1.5 inline-block text-sm font-medium text-warning underline underline-offset-2">
                Ajustar el tope en Configuración
              </Link>
            </div>
          </div>
        </section>
      ) : null}

      {/* ── Recordatorios ─────────────────────────────────────────── */}
      <section className="mt-12">
        <SectionTitle icon={BellRing} title="Recordatorios" />
        {reminderMsg ? <p className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{reminderMsg}</p> : null}
        {reminders.length === 0 ? (
          <EmptyHint icon={BellRing}>
            No tienes recordatorios pendientes. Pídelos en el chat: «recuérdame presentar la contestación mañana a las 9».
          </EmptyHint>
        ) : (
          <ul className="space-y-2">
            {reminders.map((r, i) => (
              <li
                key={r.id}
                className="card-depth flex animate-slide-up items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
                style={{ animationDelay: `${i * 40}ms`, animationFillMode: "backwards" }}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{r.text}</div>
                  <div className="mt-0.5 text-sm text-muted-foreground">
                    Para el {fmtHora(r.due_at)}
                    {r.is_procedural ? (
                      <span className="ml-1.5 font-medium text-warning">· plazo procesal: confirma tú la fecha</span>
                    ) : null}
                  </div>
                </div>
                <Button size="sm" variant="ghost" className="shrink-0" onClick={() => cancelReminder(r.id)}>
                  Cancelar
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Recomendaciones de Mia ────────────────────────────────── */}
      <section className="mt-12">
        <SectionTitle
          icon={Sparkles}
          title="Recomendaciones de Mia"
          hint="Del diagnóstico semanal, con evidencia real de la actividad del despacho."
        />
        {rxMsg ? <p role="alert" className="mb-3 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{rxMsg}</p> : null}
        {!prescriptionsLoaded ? (
          <Skeleton className="h-24 w-full rounded-xl" />
        ) : prescriptions.length === 0 ? (
          <EmptyHint icon={Sparkles}>
            Mia aún no tiene recomendaciones — necesita más actividad para hablar con evidencia.
          </EmptyHint>
        ) : (
          <ul className="space-y-3">
            {prescriptions.map((p, i) => {
              const expanded = expandedRx === p.id;
              return (
                <li
                  key={p.id}
                  className="card-depth animate-slide-up rounded-xl border border-border bg-card p-5"
                  style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{p.headline}</span>
                        {p.status === "recurring" && p.age_days > 0 ? (
                          <Badge variant="warning" className="bg-warning/15 text-warning">
                            Recurrente · {p.age_days} {p.age_days === 1 ? "día" : "días"}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-2 text-sm text-muted-foreground">{p.prescription}</p>
                      {p.dollar_impact != null || p.time_impact_mins != null ? (
                        <p className="mt-2 text-sm font-medium text-primary">
                          {p.dollar_impact != null ? `Impacto estimado: USD ${p.dollar_impact.toFixed(0)}/mes` : null}
                          {p.dollar_impact != null && p.time_impact_mins != null ? " · " : null}
                          {p.time_impact_mins != null ? `${p.time_impact_mins} min/mes ahorrables` : null}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  {p.evidence?.length ? (
                    <div className="mt-3">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => setExpandedRx(expanded ? null : p.id)}
                        className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {expanded ? "Ocultar evidencia" : "Ver evidencia"}
                      </button>
                      {expanded ? (
                        <ul className="mt-2 space-y-1 rounded-lg bg-muted/60 px-3 py-2 text-sm text-muted-foreground animate-fade-in">
                          {p.evidence.map((line, j) => (
                            <li key={j}>· {line}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => decidePrescription(p.id, "accept")} disabled={rxBusy === p.id}>
                      Lo haré
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => decidePrescription(p.id, "dismiss")} disabled={rxBusy === p.id}>
                      Descartar
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* ── Este mes ──────────────────────────────────────────────── */}
      <section className="mt-12 mb-4">
        <SectionTitle icon={BarChart3} title="Este mes" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard icon={FolderOpen} label="Asuntos activos" value={s.matters_active} delay={0} />
          <StatCard icon={FileText} label="Documentos" value={s.documents_indexed} delay={1} />
          <StatCard icon={CheckCircle2} label="Borradores aprobados" value={s.value?.drafts_approved} delay={2} />
          <StatCard icon={Clock} label="Horas ahorradas" value={s.value?.hours_saved} delay={3} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Valor neto estimado: USD {Number(s.value?.net_usd ?? 0).toFixed(2)}.{" "}
          <Link href="/configurar#valor" className="font-medium text-primary hover:underline">
            Ajustar el cálculo en Configuración
          </Link>
        </p>
      </section>
    </div>
  );
}
