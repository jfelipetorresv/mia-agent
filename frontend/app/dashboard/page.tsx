"use client";

import { useEffect, useState } from "react";
import {
  BellRing,
  BookOpen,
  CalendarClock,
  FileText,
  FolderOpen,
  FolderSearch,
  HeartPulse,
  Layers,
  Lightbulb,
  Mail,
  Mic,
  NotebookPen,
  PiggyBank,
  Repeat,
  Settings2,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import AutomationsSection from "@/app/_components/AutomationsSection";
import MailboxSectionLoader from "@/app/_components/MailboxSectionLoader";

type Stats = {
  matters_active?: number;
  documents_indexed?: number;
  knowledge_items?: number;
  proposals_pending?: number;
  cost_month_usd?: number;
  // CP-V1 · valor entregado del mes (horas ahorradas × tarifa − costo de IA).
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
  playbooks_active?: number;
  playbooks_archived?: number;
  scheduler_jobs?: { label: string; next_run?: string | null; last_run?: string | null }[];
  connectors?: {
    knowledge_base?: { active?: boolean; last_sync?: string | null; chunks?: number };
    external_store?: { active?: boolean; vectors_count?: number };
    models?: string[];
  };
  second_brain?: {
    weekly_approval_rate?: number;
    concepts_count?: number;
    skills_active?: number;
    skills_archived?: number;
    next_consolidation?: string | null;
    last_report?: string | null;
  };
};

type MotorPolicy = { politica: string; nombre: string; opciones: { id: string; nombre: string }[] };
type Reminder = { id: string; text: string; due_at: string; is_procedural: boolean };

// Carpetas de trabajo (GET /api/folders/detected): nubes espejo detectadas en el
// equipo + carpetas ya registradas por el despacho.
type DetectedCloud = { label: string; path: string; registered: boolean };
type FolderSource = { id: string; path: string; label: string; kind: string; enabled: boolean };
type FoldersData = { detected: DetectedCloud[]; sources: FolderSource[] };

// Estado de Obsidian en este equipo (GET /api/obsidian/status).
type ObsidianStatus = { installed: boolean; vault_configured: boolean; vault_path?: string | null; message: string };

// CP-Z1b · estado del dictado por voz (GET /api/speech/status). Mientras
// descarga, `progreso` trae el avance para la barra.
type SpeechProgress = {
  fase: string;
  descargado_mb: number;
  total_mb: number | null;
  porcentaje: number | null;
};
type SpeechStatus = {
  estado: "instalado" | "no_instalado" | "descargando" | "error";
  listo: boolean;
  mensaje: string;
  progreso: SpeechProgress | null;
};

// CP-E1 · tope de gasto de IA mensual (GET/PUT /api/policy/budget).
type BudgetStatus = {
  monthly_budget_usd: number | null;
  spent_this_month_usd: number;
  remaining_usd: number | null;
  over_budget: boolean;
  unlimited: boolean;
};

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

function fmt(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

// Para los recordatorios la HORA importa ("mañana a las 9" no es "mañana").
function fmtHora(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("es-CO", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

// Navegación interna del panel: el dashboard es largo por naturaleza (aquí vive
// todo lo operativo) — estas anclas evitan que se sienta un pozo sin fondo.
const SECCIONES = [
  { id: "actividad", label: "Actividad" },
  { id: "recomendaciones", label: "Recomendaciones" },
  { id: "recordatorios", label: "Recordatorios" },
  { id: "valor", label: "Valor y gasto" },
  { id: "conexiones", label: "Conexiones" },
  { id: "carpetas", label: "Carpetas" },
  { id: "automatizaciones", label: "Automatizaciones" },
];

export default function DashboardPage() {
  const [s, setS] = useState<Stats | null>(null);
  const [vaultPath, setVaultPath] = useState("");
  const [pineconeKey, setPineconeKey] = useState("");
  const [pineconeIndex, setPineconeIndex] = useState("");
  const [status, setStatus] = useState("");
  // CP7 (CP2 · decisión #27): motor de IA por política del despacho, sin nombres
  // de modelos (§G) — "Mi suscripción / Nube / Todo en mi equipo".
  const [policy, setPolicy] = useState<MotorPolicy | null>(null);
  const [policyMsg, setPolicyMsg] = useState("");
  // CP-B3: recordatorios pendientes del despacho.
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [reminderMsg, setReminderMsg] = useState("");
  // CP-C4b: carpetas de trabajo registradas + nubes detectadas en este equipo.
  const [folders, setFolders] = useState<FoldersData | null>(null);
  const [folderPath, setFolderPath] = useState("");
  const [folderLabel, setFolderLabel] = useState("");
  const [folderMsg, setFolderMsg] = useState("");
  const [folderBusy, setFolderBusy] = useState(false);
  // CP-C4b: estado de Obsidian + instalación guiada (con confirmación explícita).
  const [obsidian, setObsidian] = useState<ObsidianStatus | null>(null);
  const [installConfirm, setInstallConfirm] = useState(false);
  const [installBusy, setInstallBusy] = useState(false);
  // CP-Z1b: dictado por voz — estado, confirmación e instalación desde la tarjeta.
  const [speech, setSpeech] = useState<SpeechStatus | null>(null);
  const [speechConfirm, setSpeechConfirm] = useState(false);
  const [speechBusy, setSpeechBusy] = useState(false);
  const [speechMsg, setSpeechMsg] = useState("");
  // CP-V1: tarifa horaria del despacho (editable desde la tarjeta de valor).
  const [rateInput, setRateInput] = useState("");
  const [rateMsg, setRateMsg] = useState("");
  // CP-E1: tope de gasto de IA mensual del despacho.
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [budgetInput, setBudgetInput] = useState("");
  const [sinLimite, setSinLimite] = useState(true);
  const [budgetMsg, setBudgetMsg] = useState("");
  const [budgetBusy, setBudgetBusy] = useState(false);
  // CP-V2: recomendaciones del auto-diagnóstico semanal.
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [prescriptionsLoaded, setPrescriptionsLoaded] = useState(false);
  const [expandedRx, setExpandedRx] = useState<string | null>(null);
  const [rxMsg, setRxMsg] = useState("");
  const [rxBusy, setRxBusy] = useState<string | null>(null);

  async function loadFolders() {
    try {
      setFolders(await apiGet<FoldersData>("/api/folders/detected"));
    } catch {
      setFolders(null);
    }
  }

  async function loadBudget() {
    try {
      const data = await apiGet<BudgetStatus>("/api/policy/budget");
      setBudget(data);
      setSinLimite(data.unlimited);
      setBudgetInput(data.unlimited || data.monthly_budget_usd == null ? "" : String(data.monthly_budget_usd));
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

  async function load() {
    const data = await apiGet<Stats>("/api/dashboard/stats");
    setS(data);
    apiGet<MotorPolicy>("/settings/model-policy")
      .then(setPolicy)
      .catch(() => setPolicyMsg("No se pudo cargar el motor de IA. Recarga la página."));
    apiGet<Reminder[]>("/api/assistant/reminders").then(setReminders).catch(() => setReminders([]));
    loadFolders();
    apiGet<ObsidianStatus>("/api/obsidian/status").then(setObsidian).catch(() => setObsidian(null));
    apiGet<SpeechStatus>("/api/speech/status").then(setSpeech).catch(() => setSpeech(null));
    loadBudget();
    loadPrescriptions();
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  // CP-Z1b: mientras el componente de voz descarga, la tarjeta se refresca sola
  // cada 2 s (SOLO durante la descarga; el intervalo se limpia al terminar).
  useEffect(() => {
    if (speech?.estado !== "descargando") return;
    // Guard de vuelo: si una consulta tarda más de 2 s, no se apilan más.
    let enVuelo = false;
    const t = setInterval(() => {
      if (enVuelo) return;
      enVuelo = true;
      apiGet<SpeechStatus>("/api/speech/status")
        .then((st) => {
          setSpeech(st);
          // Al terminar, el "Empecé a descargar…" ya no aplica: lo dice la tarjeta.
          if (st.estado !== "descargando") setSpeechMsg("");
        })
        .catch(() => {})
        .finally(() => {
          enVuelo = false;
        });
    }, 2000);
    return () => clearInterval(t);
  }, [speech?.estado]);

  async function changePolicy(id: string) {
    setPolicyMsg("");
    try {
      const res = await apiSend<MotorPolicy>("PUT", "/settings/model-policy", { politica: id });
      setPolicy(res);
      setPolicyMsg(`Listo: Mia trabajará con "${res.nombre}".`);
    } catch {
      setPolicyMsg("No se pudo cambiar el motor. Intenta de nuevo.");
    }
  }

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

  // CP-E1: fija o quita el tope de gasto de IA y refresca la tarjeta con la respuesta.
  async function saveBudget() {
    setBudgetMsg("");
    if (!sinLimite) {
      const amount = Number(budgetInput.replace(",", "."));
      if (!budgetInput.trim() || !Number.isFinite(amount) || amount <= 0) {
        setBudgetMsg("Escribe un tope válido en USD.");
        return;
      }
    }
    setBudgetBusy(true);
    try {
      const res = await apiSend<BudgetStatus>("PUT", "/api/policy/budget", {
        monthly_budget_usd: sinLimite ? null : Number(budgetInput.replace(",", ".")),
      });
      setBudget(res);
      setSinLimite(res.unlimited);
      setBudgetInput(res.unlimited || res.monthly_budget_usd == null ? "" : String(res.monthly_budget_usd));
      setBudgetMsg(sinLimite ? "Sin tope de gasto este mes." : "Tope guardado.");
    } catch (err: unknown) {
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setBudgetMsg(msg || "No se pudo guardar el tope. Intenta de nuevo.");
    } finally {
      setBudgetBusy(false);
    }
  }

  // CP-V1: guarda la tarifa horaria del despacho y refresca la tarjeta de valor.
  async function saveRate() {
    setRateMsg("");
    const rate = Number(rateInput.replace(",", "."));
    if (!rateInput.trim() || !Number.isFinite(rate) || rate <= 0) {
      setRateMsg("Escribe una tarifa válida en USD por hora.");
      return;
    }
    try {
      await apiSend("PUT", "/api/value/settings", { hourly_rate_usd: rate });
      setRateInput("");
      setRateMsg("Tarifa guardada.");
      await load();
    } catch (err: any) {
      // Solo mensajes en llano del backend (ApiError); un error de red no se muestra crudo.
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setRateMsg(msg || "No se pudo guardar la tarifa. Intenta de nuevo.");
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

  async function syncObsidian() {
    setStatus("Sincronizando...");
    try {
      const res = await apiSend<{ chunks_indexed: number }>("POST", "/api/connectors/obsidian/sync", {
        vault_path: vaultPath || null,
      });
      setStatus(`${res.chunks_indexed} documentos sincronizados`);
      await load();
    } catch {
      setStatus("No se pudo sincronizar tu espacio de notas.");
    }
  }

  async function installObsidian() {
    // Instalar software exige confirmación explícita (el backend también la exige:
    // body {"confirmar": true}); el clic accidental nunca instala nada.
    setInstallBusy(true);
    setStatus("Instalando Obsidian… puede tardar unos minutos.");
    try {
      const res = await apiSend<{ installed: boolean; message: string }>(
        "POST", "/api/obsidian/install", { confirmar: true },
      );
      setStatus(res.message);
      apiGet<ObsidianStatus>("/api/obsidian/status").then(setObsidian).catch(() => {});
    } catch (e) {
      setStatus(e instanceof Error && e.message && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo instalar Obsidian en este momento. Intenta de nuevo más tarde.");
    } finally {
      setInstallBusy(false);
      setInstallConfirm(false);
    }
  }

  async function installSpeech() {
    // Descargar ~700 MB exige confirmación explícita (el backend también la
    // exige: body {"confirmar": true}); el clic accidental nunca descarga nada.
    setSpeechBusy(true);
    setSpeechMsg("");
    try {
      const res = await apiSend<{ status: string; message: string }>(
        "POST", "/api/speech/install", { confirmar: true },
      );
      setSpeechMsg(res.message);
      apiGet<SpeechStatus>("/api/speech/status").then(setSpeech).catch(() => {});
    } catch (e) {
      setSpeechMsg(e instanceof ApiError && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo iniciar la instalación del dictado. Intenta de nuevo.");
    } finally {
      setSpeechBusy(false);
      setSpeechConfirm(false);
    }
  }

  async function addFolder(path: string, label?: string) {
    setFolderMsg("");
    setFolderBusy(true);
    try {
      await apiSend("POST", "/api/folders", { path, label: label || null, kind: "knowledge" });
      setFolderPath("");
      setFolderLabel("");
      setFolderMsg("Carpeta registrada. Mia la revisará en la próxima sincronización.");
      await loadFolders();
    } catch (e) {
      setFolderMsg(e instanceof Error && e.message && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo registrar la carpeta. Revisa la ruta e intenta de nuevo.");
    } finally {
      setFolderBusy(false);
    }
  }

  async function removeFolder(id: string, label: string) {
    // Quitar una carpeta borra lo que Mia aprendió de ella — se confirma antes.
    if (!window.confirm(`¿Quitar "${label}"? Mia dejará de usar esa carpeta y olvidará lo que leyó de ella.`)) return;
    setFolderMsg("");
    try {
      await apiSend("DELETE", `/api/folders/${id}`);
      setFolderMsg("Carpeta retirada.");
      await loadFolders();
    } catch {
      setFolderMsg("No se pudo quitar la carpeta. Intenta de nuevo.");
    }
  }

  async function syncFoldersNow() {
    setFolderMsg("");
    try {
      const res = await apiSend<{ message: string }>("POST", "/api/folders/sync");
      setFolderMsg(res.message || "Estoy revisando tus carpetas.");
    } catch {
      setFolderMsg("No se pudo iniciar la revisión de carpetas. Intenta de nuevo.");
    }
  }

  async function connectPinecone() {
    setStatus("Conectando...");
    try {
      const res = await apiSend<{ status: string; vectors_count: number }>("POST", "/api/connectors/pinecone/configure", {
        api_key: pineconeKey,
        index_name: pineconeIndex,
      });
      setStatus(res.status === "active" ? `${res.vectors_count} documentos disponibles` : "No se pudo activar");
      await load();
    } catch {
      setStatus("No se pudo conectar la memoria ampliada.");
    }
  }

  if (!s) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-10 md:px-8">
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
        </div>
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }
  const c = s.connectors || {};
  const brain = s.second_brain || {};

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 md:px-8">
      {/* Encabezado con resumen en llano: el panel saluda con lo que importa hoy. */}
      <header className="animate-slide-up">
        <h1 className="text-2xl font-semibold tracking-tight">Panel del despacho</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {s.matters_active || 0} {s.matters_active === 1 ? "asunto activo" : "asuntos activos"}
          {(s.proposals_pending || 0) > 0
            ? ` · ${s.proposals_pending} ${s.proposals_pending === 1 ? "sugerencia esperando" : "sugerencias esperando"} tu decisión`
            : " · todo al día"}
        </p>
        <nav aria-label="Secciones del panel" className="mt-4 flex flex-wrap gap-1.5">
          {SECCIONES.map((sec) => (
            <a
              key={sec.id}
              href={`#${sec.id}`}
              className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              {sec.label}
            </a>
          ))}
        </nav>
      </header>

      {/* ── Actividad ─────────────────────────────────────────────── */}
      <section id="actividad" className="mt-10 scroll-mt-6">
        <SectionTitle icon={TrendingUp} title="Actividad" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard icon={FolderOpen} label="Asuntos activos" value={s.matters_active} delay={0} />
          <StatCard icon={FileText} label="Documentos" value={s.documents_indexed} delay={1} />
          <StatCard icon={BookOpen} label="Conocimiento" value={s.knowledge_items} delay={2} />
          <StatCard icon={Lightbulb} label="Sugerencias" value={s.proposals_pending} delay={3} />
        </div>
      </section>

      {/* ── Recomendaciones de Mia ────────────────────────────────── */}
      <section id="recomendaciones" className="mt-12 scroll-mt-6">
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
                  className="animate-slide-up rounded-xl border border-border bg-card p-5 shadow-sm"
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

      {/* ── Recordatorios ─────────────────────────────────────────── */}
      <section id="recordatorios" className="mt-12 scroll-mt-6">
        <SectionTitle icon={BellRing} title="Recordatorios" />
        {reminderMsg ? <p className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{reminderMsg}</p> : null}
        {reminders.length === 0 ? (
          <EmptyHint icon={BellRing}>
            No tienes recordatorios pendientes. Pídelos en el chat: «recuérdame radicar la tutela mañana a las 9».
          </EmptyHint>
        ) : (
          <ul className="space-y-2">
            {reminders.map((r, i) => (
              <li
                key={r.id}
                className="flex animate-slide-up items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm"
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

      {/* ── Valor entregado + tope de gasto ───────────────────────── */}
      <section id="valor" className="mt-12 scroll-mt-6">
        <SectionTitle icon={PiggyBank} title="Valor y gasto del mes" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="animate-slide-up rounded-xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-1 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <TrendingUp className="h-4 w-4 text-success" />
              Valor entregado este mes
            </div>
            <div className="mt-2 text-3xl font-semibold tracking-tight">
              USD {Number(s.value?.net_usd ?? 0).toFixed(2)}
              <span className="ml-2 text-sm font-normal text-muted-foreground">de valor neto estimado</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {Number(s.value?.hours_saved ?? 0).toFixed(1)} horas ahorradas (estimado) ×
              USD {Number(s.value?.hourly_rate_usd ?? 0).toFixed(0)}/hora =
              USD {Number(s.value?.gross_usd ?? 0).toFixed(2)}, menos
              USD {Number(s.value?.cost_usd ?? 0).toFixed(2)} de costo de la inteligencia artificial.
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Este mes: {s.value?.drafts_approved ?? 0} borradores aprobados y {s.value?.consultations ?? 0} consultas.
              El cálculo usa estimados configurables{s.value?.is_default_config ? " (valores de fábrica)" : ""}.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Label htmlFor="hourly-rate" className="text-sm text-muted-foreground">
                Tu tarifa horaria (USD):
              </Label>
              <Input
                id="hourly-rate"
                value={rateInput}
                onChange={(e) => setRateInput(e.target.value)}
                placeholder={String(s.value?.hourly_rate_usd ?? 100)}
                inputMode="decimal"
                className="h-9 w-24"
              />
              <Button size="sm" onClick={saveRate}>
                Guardar
              </Button>
              {rateMsg ? <span className="text-sm text-muted-foreground">{rateMsg}</span> : null}
            </div>
          </div>

          <div className="animate-slide-up rounded-xl border border-border bg-card p-6 shadow-sm" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
            <div className="mb-1 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <PiggyBank className="h-4 w-4 text-cta" />
              Tope de gasto de IA este mes
            </div>
            {budget === null ? (
              <p className="mt-3 text-sm text-muted-foreground">No se pudo cargar el tope de gasto. Recarga la página.</p>
            ) : (
              <>
                <div className="mt-2 text-3xl font-semibold tracking-tight">
                  USD {Number(budget.spent_this_month_usd).toFixed(2)}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {budget.unlimited
                      ? "gastados · sin tope este mes"
                      : `de USD ${Number(budget.monthly_budget_usd ?? 0).toFixed(2)}`}
                  </span>
                </div>
                {!budget.unlimited && budget.remaining_usd != null ? (
                  <p className="mt-1 text-sm text-muted-foreground">
                    Restante: USD {Number(budget.remaining_usd).toFixed(2)}
                  </p>
                ) : null}
                {budget.over_budget ? (
                  <p role="alert" className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
                    Se alcanzó el tope; los turnos están en pausa.
                  </p>
                ) : null}
                <div className="mt-4 space-y-3">
                  <div className="flex flex-wrap items-end gap-2">
                    <div>
                      <Label htmlFor="budget-cap" className="mb-1 block text-sm text-muted-foreground">
                        Tope mensual (USD)
                      </Label>
                      <Input
                        id="budget-cap"
                        value={budgetInput}
                        onChange={(e) => setBudgetInput(e.target.value)}
                        disabled={sinLimite || budgetBusy}
                        placeholder="Ej.: 100"
                        inputMode="decimal"
                        className="h-9 w-28"
                      />
                    </div>
                    <Button size="sm" onClick={saveBudget} disabled={budgetBusy}>
                      {budgetBusy ? "Guardando…" : "Guardar"}
                    </Button>
                  </div>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={sinLimite}
                      onChange={(e) => setSinLimite(e.target.checked)}
                      disabled={budgetBusy}
                      className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
                    />
                    Sin límite
                  </label>
                </div>
                {budgetMsg ? (
                  <p
                    role={budgetMsg === "Tope guardado." || budgetMsg === "Sin tope de gasto este mes." ? "status" : "alert"}
                    className={`mt-3 text-sm ${
                      budgetMsg === "Tope guardado." || budgetMsg === "Sin tope de gasto este mes."
                        ? "text-muted-foreground"
                        : "text-warning"
                    }`}
                  >
                    {budgetMsg}
                  </p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

      {/* ── Conexiones ────────────────────────────────────────────── */}
      <section id="conexiones" className="mt-12 scroll-mt-6">
        <SectionTitle
          icon={Settings2}
          title="Conexiones"
          hint="Lo que Mia puede usar para ayudarte. Todo se activa solo si tú lo decides."
        />
        <div className="space-y-4">
          {/* Espacio de notas (Obsidian) */}
          <ConnectorCard
            icon={NotebookPen}
            title="Tu espacio de notas"
            active={Boolean(c.knowledge_base?.active)}
            subtitle={
              c.knowledge_base?.active
                ? `Activo · última sincronización ${fmt(c.knowledge_base.last_sync)}`
                : "Inactivo"
            }
            actions={
              <>
                {obsidian && !obsidian.installed ? (
                  <Button variant="outline" size="sm" onClick={() => setInstallConfirm(true)} disabled={installBusy}>
                    Instalar Obsidian
                  </Button>
                ) : null}
                <Button size="sm" onClick={syncObsidian}>
                  Sincronizar
                </Button>
              </>
            }
          >
            {obsidian ? <p className="mb-3 text-sm text-muted-foreground">{obsidian.message}</p> : null}
            {installConfirm ? (
              <div
                role="alertdialog"
                aria-label="Confirmar instalación de Obsidian"
                className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 animate-fade-in"
              >
                <p className="text-sm text-warning">
                  Esta acción descarga e instala el programa Obsidian en este equipo. ¿Quieres continuar?
                </p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" onClick={installObsidian} disabled={installBusy}>
                    {installBusy ? "Instalando…" : "Sí, instalar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setInstallConfirm(false)} disabled={installBusy}>
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : null}
            <Label htmlFor="vault-path" className="mb-1.5 block text-sm text-muted-foreground">
              Ubicación de tu espacio de notas
            </Label>
            <Input
              id="vault-path"
              value={vaultPath}
              onChange={(e) => setVaultPath(e.target.value)}
              placeholder="Ej.: D:\Notas del despacho"
            />
          </ConnectorCard>

          {/* Dictado por voz */}
          <ConnectorCard
            icon={Mic}
            title="Dictado por voz"
            active={Boolean(speech?.listo)}
            subtitle={
              speech?.listo
                ? "Instalado · dicta con el micrófono desde el chat de tus asuntos"
                : speech?.estado === "descargando"
                  ? "Instalando…"
                  : "Inactivo"
            }
            actions={
              speech && !speech.listo && speech.estado !== "descargando" ? (
                <Button variant="outline" size="sm" onClick={() => setSpeechConfirm(true)} disabled={speechBusy}>
                  Instalar dictado por voz
                </Button>
              ) : null
            }
          >
            {speech ? <p className="mb-3 text-sm text-muted-foreground">{speech.mensaje}</p> : null}
            {speech?.estado === "descargando" && speech.progreso ? (
              <div className="mb-3">
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={speech.progreso.porcentaje ?? undefined}
                  aria-label="Avance de la descarga del dictado por voz"
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${speech.progreso.porcentaje ?? 5}%` }}
                  />
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {speech.progreso.total_mb
                    ? `${speech.progreso.descargado_mb} de ${speech.progreso.total_mb} MB`
                    : `${speech.progreso.descargado_mb} MB descargados`}
                </p>
              </div>
            ) : null}
            {speechConfirm ? (
              <div
                role="alertdialog"
                aria-label="Confirmar instalación del dictado por voz"
                className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 animate-fade-in"
              >
                <p className="text-sm text-warning">
                  Esta acción descarga el componente de dictado por voz (~700 MB) en el servidor de Mia.
                  Puede tardar varios minutos. Tu voz nunca saldrá del servidor del despacho. ¿Quieres continuar?
                </p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" onClick={installSpeech} disabled={speechBusy}>
                    {speechBusy ? "Iniciando…" : "Sí, instalar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setSpeechConfirm(false)} disabled={speechBusy}>
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : null}
            {speechMsg ? <p className="text-sm text-warning">{speechMsg}</p> : null}
          </ConnectorCard>

          {/* Calendario y correo */}
          <ConnectorCard icon={Mail} title="Calendario y correo" subtitle="Microsoft 365 o Google Workspace">
            <p className="mb-3 text-sm text-muted-foreground">
              Conecta tu cuenta para que Mia avise de eventos y correos urgentes.
            </p>
            <MailboxSectionLoader />
          </ConnectorCard>

          {/* Motor de IA */}
          <ConnectorCard icon={Settings2} title="Motor de IA" subtitle="Con qué trabaja Mia. Puedes cambiarlo cuando quieras.">
            <select
              value={policy?.politica || ""}
              onChange={(e) => changePolicy(e.target.value)}
              aria-label="Motor de IA"
              className="h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
            >
              {(policy?.opciones || []).map((o) => (
                <option key={o.id} value={o.id}>{o.nombre}</option>
              ))}
            </select>
            {policyMsg ? <p className="mt-2 text-sm text-muted-foreground">{policyMsg}</p> : null}
          </ConnectorCard>

          {/* Memoria ampliada (avanzado) — plegada: casi nadie la necesita el día 1. */}
          <details className="group rounded-xl border border-border bg-card shadow-sm">
            <summary className="flex cursor-pointer items-center gap-3 px-5 py-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <Layers className="h-4 w-4" />
              </span>
              <span className="flex-1">
                Memoria ampliada
                <span className="ml-2 text-xs font-normal text-muted-foreground">(opcional, avanzado)</span>
              </span>
              <span className="text-xs text-muted-foreground">
                {c.external_store?.active ? `Activa · ${c.external_store.vectors_count || 0} documentos` : "Inactiva"}
              </span>
            </summary>
            <div className="border-t border-border px-5 py-4">
              <p className="mb-3 text-sm text-muted-foreground">
                Un almacén adicional para despachos con miles de documentos. Si no sabes qué es, no lo necesitas.
              </p>
              <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <Input
                  type="password"
                  autoComplete="off"
                  value={pineconeKey}
                  onChange={(e) => setPineconeKey(e.target.value)}
                  placeholder="Clave de acceso"
                  aria-label="Clave de acceso"
                />
                <Input
                  value={pineconeIndex}
                  onChange={(e) => setPineconeIndex(e.target.value)}
                  placeholder="Nombre del índice"
                  aria-label="Nombre del índice"
                />
                <Button onClick={connectPinecone}>Conectar</Button>
              </div>
            </div>
          </details>

          {status ? <p role="status" className="text-sm text-muted-foreground animate-fade-in">{status}</p> : null}
        </div>
      </section>

      {/* ── Carpetas de trabajo ───────────────────────────────────── */}
      <section id="carpetas" className="mt-12 scroll-mt-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <SectionTitle
            icon={FolderSearch}
            title="Carpetas de trabajo"
            hint="Mia solo lee las carpetas que tú registres aquí. Nunca revisa nada fuera de ellas."
            className="mb-0"
          />
          <Button variant="outline" size="sm" onClick={syncFoldersNow} className="shrink-0">
            Revisar carpetas ahora
          </Button>
        </div>
        {folderMsg ? <p role="status" className="mb-3 rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground animate-fade-in">{folderMsg}</p> : null}

        {folders === null ? (
          <p className="text-sm text-muted-foreground">No se pudieron cargar tus carpetas. Recarga la página.</p>
        ) : (
          <div className="space-y-5">
            {folders.detected.length > 0 ? (
              <div>
                <h3 className="mb-2 text-sm font-medium text-muted-foreground">Detectadas en este equipo</h3>
                <ul className="space-y-2">
                  {folders.detected.map((d) => (
                    <li key={d.path} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{d.label}</div>
                        <div className="truncate text-sm text-muted-foreground" title={d.path}>{d.path}</div>
                      </div>
                      {d.registered ? (
                        <Badge variant="success" className="shrink-0 bg-success/15 text-success">Registrada</Badge>
                      ) : (
                        <Button size="sm" onClick={() => addFolder(d.path, d.label)} disabled={folderBusy} className="shrink-0">
                          Registrar
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">Registradas</h3>
              {folders.sources.filter((f) => f.enabled).length === 0 ? (
                <EmptyHint icon={FolderSearch}>Aún no has registrado ninguna carpeta.</EmptyHint>
              ) : (
                <ul className="space-y-2">
                  {folders.sources.filter((f) => f.enabled).map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{f.label}</div>
                        <div className="truncate text-sm text-muted-foreground" title={f.path}>{f.path}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removeFolder(f.id, f.label)} className="shrink-0">
                        Quitar
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (folderPath.trim()) addFolder(folderPath.trim(), folderLabel.trim() || undefined);
              }}
              className="rounded-xl border border-dashed border-border bg-card/50 p-4"
            >
              <h3 className="mb-3 text-sm font-medium text-muted-foreground">Registrar otra carpeta</h3>
              <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                <Input
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  aria-label="Ubicación de la carpeta"
                  placeholder="Ej.: D:\Guías del despacho"
                />
                <Input
                  value={folderLabel}
                  onChange={(e) => setFolderLabel(e.target.value)}
                  aria-label="Nombre para identificarla (opcional)"
                  placeholder="Nombre (opcional)"
                  className="sm:w-44"
                />
                <Button type="submit" disabled={folderBusy || !folderPath.trim()}>
                  Registrar
                </Button>
              </div>
            </form>
          </div>
        )}
      </section>

      {/* ── Automatizaciones ──────────────────────────────────────── */}
      <section id="automatizaciones" className="mt-12 scroll-mt-6">
        <SectionTitle icon={Repeat} title="Automatizaciones" />
        <AutomationsSection />
      </section>

      {/* ── Sistema (lo que Mia hace sola, en segundo plano) ──────── */}
      <section className="mt-12 scroll-mt-6">
        <SectionTitle
          icon={HeartPulse}
          title="La salud de Mia"
          hint="Cómo va el conocimiento que Mia construye de tu despacho y sus procesos de fondo."
        />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard icon={HeartPulse} label="Aprobación semanal" value={Math.round((brain.weekly_approval_rate || 0) * 100)} suffix="%" delay={0} />
          <StatCard icon={BookOpen} label="Conceptos" value={brain.concepts_count} delay={1} />
          <StatCard icon={Lightbulb} label="Habilidades activas" value={brain.skills_active} delay={2} />
          <StatCard icon={FileText} label="Habilidades archivadas" value={brain.skills_archived} delay={3} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">Próxima consolidación: {fmt(brain.next_consolidation)}</p>

        {(s.scheduler_jobs || []).length > 0 ? (
          <ul className="mt-5 space-y-2">
            {(s.scheduler_jobs || []).map((j, i) => (
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
      </section>
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  title,
  hint,
  className = "mb-4",
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
        <Icon className="h-4 w-4 text-primary" />
        {title}
      </h2>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  suffix = "",
  delay = 0,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value?: number;
  suffix?: string;
  delay?: number;
}) {
  return (
    <div
      className="animate-slide-up rounded-xl border border-border bg-card p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
      style={{ animationDelay: `${delay * 45}ms`, animationFillMode: "backwards" }}
    >
      <Icon className="mb-2 h-4 w-4 text-primary" />
      <div className="text-2xl font-semibold tracking-tight">{value ?? 0}{suffix}</div>
      <div className="mt-0.5 text-sm text-muted-foreground">{label}</div>
    </div>
  );
}

function EmptyHint({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-dashed border-border bg-card/50 px-4 py-4">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

function ConnectorCard({
  icon: Icon,
  title,
  subtitle,
  active,
  actions,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  active?: boolean;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
              active ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
            }`}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-medium">
              {title}
              {active ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  Activo
                </span>
              ) : null}
            </div>
            {subtitle ? <div className="mt-0.5 truncate text-sm text-muted-foreground">{subtitle}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}
