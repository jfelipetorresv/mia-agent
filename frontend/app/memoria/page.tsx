"use client";

// BLOQUE 4 DEL REDISEÑO LUXURY (2026-08-19) · "CONOCIMIENTO"
// ==========================================================
// Esta pantalla era cuatro pestañas de wiki plano: listas largas de filas
// iguales, sin decir en ninguna parte QUÉ guarda Mia ahí ni PARA QUÉ le sirve
// al abogado. El nombre de la pestaña era toda la explicación disponible.
//
// Lo que cambia (nada de lógica ni de endpoints):
//   · cada pestaña abre con una NOTA DE MIA (`NotaMia`) que explica, en su voz,
//     qué vive ahí y qué gana el abogado. Visible, discreta y cerrable.
//   · la línea de ayuda bajo las pestañas (misma convención que Configuración).
//   · las listas densas pasan al vocabulario del sistema: icono en bajo relieve
//     (`NeuIcon`), cabecera de sección (`SectionTitle`), rejilla en los
//     criterios (dos columnas) en vez de una tira vertical infinita.
//   · lenguaje: registro profesional, sin jerga y sin condicionales. "Guías y
//     habilidades" → "Guías de trabajo"; "Criterios aprendidos" → "Criterios
//     del despacho"; los estados vacíos dicen qué hacer, no solo que no hay nada.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Archive,
  ArchiveRestore,
  BookMarked,
  BookOpen,
  Building2,
  Check,
  FileText,
  FolderOpen,
  GitCompareArrows,
  GraduationCap,
  History,
  Lightbulb,
  Loader2,
  Pencil,
  Plus,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
  Upload,
} from "lucide-react";
import { apiGet, apiSend, apiUploadMany, ApiError, plainMessage } from "@/lib/api";
import GuideInterviewWizard from "../_components/GuideInterviewWizard";
import MiDespachoSection from "../_components/MiDespachoSection";
import { NotaMia } from "../_components/NotaMia";
import { MetricaBarra, NeuIcon, SectionTitle } from "@/app/_components/PanelUI";
import { PageShell } from "@/app/_components/PageShell";
import { Card, cardVariants } from "@/components/ui/card";
import { staggerStyle } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import MiaMarkdown from "@/components/MiaMarkdown";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Tab = "despacho" | "wiki" | "saber" | "sugerencias";

// La línea que dice para qué sirve la pestaña abierta. Misma convención que
// Configuración: el nombre de una pestaña no alcanza para saber qué guarda.
const TAB_HINTS: Record<Tab, string> = {
  despacho:
    "Quién eres, dónde ejerces y con qué normas trabajas. Es lo primero que Mia lee antes de cada encargo.",
  wiki:
    "Lo que Mia ha entendido de tu forma de analizar cada tema. Cuando algo no te representa, se corrige aquí.",
  saber:
    "Los pasos que sigue tu despacho para cada tipo de escrito. Mia los aplica cuando prepara un borrador.",
  sugerencias:
    "Lo que Mia propone para trabajar mejor. Nada de esto cambia hasta que tú lo apruebas.",
};

export default function MemoriaPage() {
  const [tab, setTab] = useState<Tab>("despacho");
  return (
    <PageShell
      title="Conocimiento"
      subtitle="Todo lo que Mia sabe de tu despacho, en un solo sitio. Ella lo propone; la última palabra es tuya."
    >
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-block">
        <TabsList className="h-auto flex-wrap justify-start gap-1">
          <TabsTrigger value="despacho" className="gap-1.5">
            <Building2 className="h-4 w-4" />
            Mi despacho
          </TabsTrigger>
          <TabsTrigger value="wiki" className="gap-1.5">
            <BookOpen className="h-4 w-4" />
            Criterios del despacho
          </TabsTrigger>
          <TabsTrigger value="saber" className="gap-1.5">
            <BookMarked className="h-4 w-4" />
            Guías de trabajo
          </TabsTrigger>
          <TabsTrigger value="sugerencias" className="gap-1.5">
            <Lightbulb className="h-4 w-4" />
            Mejoras que propone Mia
          </TabsTrigger>
        </TabsList>

        <p className="mt-3 text-pretty text-body text-muted-foreground">{TAB_HINTS[tab]}</p>

        <TabsContent value="despacho" className="animate-fade-in">
          <div className="mt-6 space-y-6">
            <NotaMia id="conocimiento-despacho" icon={Building2} titulo="Esta es la ficha de tu despacho">
              Es lo mismo que respondiste al conocer a Mia: tu nombre, tu firma y las jurisdicciones en
              las que ejerces. Se edita aquí sin repetir la entrevista, y lo leo antes de cada encargo.
            </NotaMia>
            <MiDespachoSection />
          </div>
        </TabsContent>
        <TabsContent value="wiki" className="animate-fade-in">
          <div className="mt-6 space-y-6">
            <NotaMia id="conocimiento-criterios" icon={BookOpen} titulo="Así voy aprendiendo cómo piensas">
              Cada vez que trabajamos un caso anoto el criterio que aplicaste sobre ese tema. Abre
              cualquiera para ver cómo lo entiendo hoy y corrígeme cuando no refleje al despacho.
            </NotaMia>
            <Wiki />
          </div>
        </TabsContent>
        <TabsContent value="saber" className="animate-fade-in">
          <div className="mt-6 space-y-6">
            <NotaMia id="conocimiento-guias" icon={BookMarked} titulo="Tus guías son mi manual de trabajo">
              Una guía es el paso a paso de tu despacho para un tipo de escrito. Cuando preparo un
              borrador aplico las que estén activas, así que aquí decides qué método sigo.
            </NotaMia>
            <Saber />
          </div>
        </TabsContent>
        <TabsContent value="sugerencias" className="animate-fade-in">
          <div className="mt-6 space-y-6">
            <NotaMia id="conocimiento-mejoras" icon={Lightbulb} titulo="Te propongo; tú decides">
              Reviso mi trabajo reciente y te traigo aquí lo que creo que puede mejorar: guías nuevas,
              criterios que se contradicen, conocimiento repetido. Nada se aplica sin tu aprobación.
            </NotaMia>
            <Sugerencias />
          </div>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}

type Concept = { name: string; confidence: number; case_count: number; last_updated?: string };

function Wiki() {
  const [items, setItems] = useState<Concept[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Concept | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [correction, setCorrection] = useState("");

  useEffect(() => {
    apiGet<Concept[]>("/api/wiki/concepts")
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  async function open(c: Concept) {
    setSelected(c);
    setCorrection("");
    setMarkdown("");
    try {
      const res = await apiGet<{ markdown: string }>(`/api/wiki/concepts/${encodeURIComponent(c.name)}`);
      setMarkdown(res.markdown);
    } catch {
      setSelected(null);
    }
  }

  async function sendCorrection() {
    if (!selected || !correction.trim()) return;
    await apiSend("POST", `/api/wiki/concepts/${encodeURIComponent(selected.name)}/feedback`, { correction: correction.trim() });
    setSelected(null);
  }

  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-lg" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card variant="dashed" className="animate-slide-up px-6 py-14 text-center">
        <NeuIcon icon={BookOpen} tone="primary" className="mx-auto mb-4" />
        <h2 className="text-title">Todavía no hay criterios del despacho</h2>
        <p className="mx-auto mt-2 max-w-md text-pretty text-body text-muted-foreground">
          Los criterios nacen del trabajo: en cuanto analicen un caso juntos, Mia anota aquí cómo
          abordas ese tema y qué posición defiende tu despacho. Empieza abriendo un caso.
        </p>
        <Button asChild className="mt-6 gap-2">
          <Link href="/casos">
            <FolderOpen className="h-4 w-4" />
            Ir a mis casos
          </Link>
        </Button>
      </Card>
    );
  }

  return (
    <div>
      <SectionTitle
        icon={BookOpen}
        title="Temas que Mia ya conoce de tu despacho"
        hint="Abre un tema para leer cómo lo entiende hoy. La barra indica cuánto trabajo respalda ese criterio."
      />
      {/* Rejilla, no tira vertical: doce criterios en una columna se leen como
          un índice de wiki; en dos columnas se leen como un tablero de temas. */}
      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((c, i) => (
          <li key={c.name} className="animate-slide-up" style={staggerStyle(i)}>
            <button
              onClick={() => open(c)}
              className={cn(
                cardVariants({ interactive: true }),
                "group flex h-full w-full flex-col gap-3 p-5 text-left hover:border-primary/35",
              )}
            >
              <div className="flex min-w-0 items-start gap-3">
                <NeuIcon icon={BookOpen} tone="primary" size="sm" />
                <div className="min-w-0">
                  {/* Sin `truncate`: el nombre de un criterio ES el dato. Cortarlo
                      a media palabra obliga a abrir la tarjeta para saber de qué
                      tema se trata. Dos líneas completas y luego sí se recorta. */}
                  <div className="text-pretty text-section line-clamp-2">{c.name}</div>
                  <div className="mt-0.5 text-body text-muted-foreground">
                    {c.case_count} {c.case_count === 1 ? "caso trabajado" : "casos trabajados"} ·{" "}
                    {c.last_updated || "sin fecha"}
                  </div>
                </div>
              </div>
              {/* null ≠ cero (regla operativa §18). `confidence` es una HEURÍSTICA con
                  suelo por volumen: un criterio con evidencia nunca sale exactamente en
                  0, así que un 0 solo puede significar que ese concepto todavía no tiene
                  la métrica escrita. Pintarlo como «0 % consolidado» afirmaba de un
                  criterio recién nacido que no ha resistido nada, que es un juicio, no
                  un dato. */}
              <div className="mt-auto">
                <MetricaBarra
                  label="% consolidado"
                  fraccion={c.confidence ? c.confidence : null}
                  sinMedir="este criterio aún no ha pasado por tu aprobación"
                  bloque
                />
              </div>
            </button>
          </li>
        ))}
      </ul>

      <Dialog open={!!selected} onOpenChange={(o) => { if (!o) setSelected(null); }}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selected?.name}</DialogTitle>
            <DialogDescription>
              Así entiende Mia este tema hoy, con lo que ha visto en tus casos. Si algo no
              representa al despacho, escríbeselo abajo y lo ajusta.
            </DialogDescription>
          </DialogHeader>
          {markdown ? (
            <div className="rounded-lg bg-muted/50 p-4 font-serif text-body leading-relaxed text-foreground">
              <MiaMarkdown text={markdown} />
            </div>
          ) : (
            <div className="space-y-2 rounded-lg bg-muted/50 p-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="wiki-correction">Corrígeme</Label>
            <Textarea
              id="wiki-correction"
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              className="h-24 resize-none"
              placeholder="Dile a Mia qué debe ajustar de este criterio"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Cerrar
            </Button>
            <Button onClick={sendCorrection}>Enviar la corrección</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

type Playbook = {
  id: string;
  title: string;
  summary: string;
  applies_when?: string;
  status?: string;
  protected?: boolean;
  origin?: string;
  content?: string;
  health_status?: string;
};
type Skill = { skill_id: string; title: string; approval_rate: number; edit_rate: number; activations: number };
type PlaybookVersion = { id: string; changed_by: string; reason: string; created_at: string; title: string };

const ORIGIN_LABEL: Record<string, string> = {
  manual: "Escrita a mano",
  importada: "Importada",
  entrevista: "Creada con Mia",
  asunto: "Nacida de un caso",
  aprendida: "Aprendida por Mia",
};

function originLabel(origin?: string): string {
  return ORIGIN_LABEL[origin || "manual"] || "Escrita a mano";
}

// Salud de la guía: 'sano' (citas en regla), 'revisar' (hay algo sin verificar) o
// 'sin_revisar' (todavía no se ha chequeado). Nunca se muestra el nombre técnico del campo.
const HEALTH_LABEL: Record<string, string> = {
  sano: "Citas en regla",
  revisar: "Citas por revisar",
  sin_revisar: "Sin comprobar",
};

function healthBadge(status?: string) {
  const s = status || "sin_revisar";
  const label = HEALTH_LABEL[s] || "Sin comprobar";
  if (s === "sano") {
    return (
      <Badge variant="success" className="gap-1">
        <ShieldCheck className="h-3 w-3" />
        {label}
      </Badge>
    );
  }
  if (s === "revisar") {
    return (
      <Badge variant="warning" className="gap-1">
        <ShieldAlert className="h-3 w-3" />
        {label}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground">
      <ShieldQuestion className="h-3 w-3" />
      {label}
    </Badge>
  );
}

function fmtDateTime(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

function Saber() {
  const [items, setItems] = useState<Playbook[]>([]);
  const [skills, setSkills] = useState<Record<string, Skill>>({});
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [form, setForm] = useState({ title: "", applies_when: "", content: "", summary: "" });

  const [viewing, setViewing] = useState<Playbook | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  const [editing, setEditing] = useState<Playbook | null>(null);
  const [editForm, setEditForm] = useState({ title: "", summary: "", applies_when: "", content: "" });
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [historyFor, setHistoryFor] = useState<Playbook | null>(null);
  const [versions, setVersions] = useState<PlaybookVersion[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [healthBusyId, setHealthBusyId] = useState<string | null>(null);

  async function load() {
    const [pbs, ranked] = await Promise.all([
      apiGet<Playbook[]>("/api/playbooks?status=todos").catch(() => []),
      apiGet<Skill[]>("/api/skills/ranked").catch(() => []),
    ]);
    setItems(pbs);
    const map: Record<string, Skill> = {};
    for (const s of ranked) map[s.skill_id] = s;
    setSkills(map);
  }
  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  async function create() {
    if (!form.title.trim() || !form.content.trim()) return;
    await apiSend("POST", "/api/playbooks", {
      title: form.title.trim(),
      summary: form.summary.trim() || form.title.trim(),
      applies_when: form.applies_when.trim() || "Depende del contexto del caso.",
      content: form.content.trim(),
      origin: "manual",
    });
    setModal(false);
    setForm({ title: "", applies_when: "", content: "", summary: "" });
    await load();
  }

  const fileInput = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importError, setImportError] = useState(false);
  const [importDetail, setImportDetail] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);

  async function importFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setImporting(true);
    setImportMsg(null);
    setImportError(false);
    setImportDetail([]);
    try {
      const res = await apiUploadMany<{ importados: string[]; omitidos: string[]; errores: string[] }>(
        "/api/playbooks/import", Array.from(files)
      );
      const n = res.importados?.length || 0;
      const om = res.omitidos?.length || 0;
      const er = res.errores?.length || 0;
      setImportMsg(
        `Se importaron ${n} guía${n === 1 ? "" : "s"}` +
        (om ? ` · ${om} ya existía${om === 1 ? "" : "n"} y se conservaron` : "") +
        (er ? ` · ${er} archivo${er === 1 ? "" : "s"} no se pudieron leer` : "") + "."
      );
      // El backend explica cada omisión/error en lenguaje llano — se muestran tal cual.
      setImportDetail([...(res.errores || []), ...(res.omitidos || []).map((t) => `${t}: ya existía; se conservó la versión guardada.`)]);
      await load();
    } catch {
      setImportError(true);
      setImportMsg("No se pudieron importar las guías. Intenta de nuevo.");
    } finally {
      setImporting(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function openView(p: Playbook) {
    setViewing(p);
    setViewLoading(true);
    try {
      setViewing(await apiGet<Playbook>(`/api/playbooks/${p.id}`));
    } catch {
      setViewing(null);
    } finally {
      setViewLoading(false);
    }
  }

  async function openEdit(p: Playbook) {
    setEditError(null);
    setEditing(p);
    try {
      const detail = await apiGet<Playbook>(`/api/playbooks/${p.id}`);
      setEditing(detail);
      setEditForm({
        title: detail.title,
        summary: detail.summary,
        applies_when: detail.applies_when || "",
        content: detail.content || "",
      });
    } catch {
      setEditing(null);
    }
  }

  async function saveEdit() {
    if (!editing) return;
    if (!editForm.title.trim() || !editForm.content.trim()) return;
    setEditSaving(true);
    setEditError(null);
    try {
      await apiSend("PUT", `/api/playbooks/${editing.id}`, editForm);
      setEditing(null);
      await load();
    } catch (e) {
      setEditError(plainMessage(e, "No se pudo guardar la guía. Intenta de nuevo."));
    } finally {
      setEditSaving(false);
    }
  }

  async function toggleArchive(p: Playbook) {
    const archiving = p.status !== "archived";
    if (
      !window.confirm(
        archiving
          ? `¿Desactivar "${p.title}"? Mia dejará de usarla hasta que la reactives.`
          : `¿Reactivar "${p.title}"? Mia volverá a usarla en sus borradores.`
      )
    ) {
      return;
    }
    setBusyId(p.id);
    try {
      await apiSend("POST", `/api/playbooks/${p.id}/${archiving ? "archive" : "restore"}`);
      await load();
    } catch {
      /* el abogado puede reintentar desde la lista */
    } finally {
      setBusyId(null);
    }
  }

  async function checkHealth(p: Playbook) {
    setHealthBusyId(p.id);
    try {
      const res = await apiSend<{ health_status: string }>("POST", `/api/playbooks/${p.id}/health`);
      setItems((prev) =>
        prev.map((it) => (it.id === p.id ? { ...it, health_status: res.health_status } : it))
      );
    } catch {
      /* el abogado puede reintentar desde la lista */
    } finally {
      setHealthBusyId(null);
    }
  }

  async function openHistory(p: Playbook) {
    setHistoryFor(p);
    setRestoreError(null);
    setHistoryLoading(true);
    try {
      const res = await apiGet<{ versions: PlaybookVersion[] }>(`/api/playbooks/${p.id}/versions`);
      setVersions(res.versions || []);
    } catch {
      setVersions([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function restoreVersion(versionId: string) {
    if (!historyFor) return;
    if (
      !window.confirm(
        "¿Restaurar esta versión? Reemplazará el contenido actual (se guarda un respaldo del estado de hoy antes de restaurar)."
      )
    ) {
      return;
    }
    setRestoreError(null);
    try {
      await apiSend("POST", `/api/playbooks/${historyFor.id}/versions/${versionId}/restore`);
      setHistoryFor(null);
      await load();
    } catch (e) {
      setRestoreError(plainMessage(e, "No se pudo restaurar esta versión. Intenta de nuevo."));
    }
  }

  return (
    <div>
      <input
        ref={fileInput}
        type="file"
        multiple
        accept=".md,.txt,.docx"
        className="hidden"
        onChange={(e) => importFiles(e.target.files)}
      />
      {/* Los tres caminos para enseñarle algo a Mia dejan de ser tres botones
          sueltos sobre la lista: viven en la cabecera de la sección, que además
          dice de qué lista se trata. */}
      <SectionTitle
        icon={BookMarked}
        title="Las guías que Mia sigue"
        hint="Tres caminos para enseñarle: traer las que ya tienes escritas, redactarlas aquí o construirlas con ella respondiendo unas preguntas."
        actions={
          <>
            <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={importing} className="gap-2">
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {importing ? "Importando…" : "Importar"}
            </Button>
            <Button variant="outline" onClick={() => setModal(true)} className="gap-2">
              <GraduationCap className="h-4 w-4" />
              Escribir una
            </Button>
            <Button onClick={() => setWizardOpen(true)} className="gap-2">
              <Sparkles className="h-4 w-4" />
              Crear con Mia
            </Button>
          </>
        }
      />

      {importMsg ? (
        <p
          className={`mb-2 rounded-md px-3 py-2 text-body ${
            importError ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
          }`}
        >
          {importMsg}
        </p>
      ) : null}
      {importDetail.length > 0 ? (
        <ul className="mb-3 space-y-0.5 text-body text-muted-foreground">
          {importDetail.map((d, i) => <li key={i}>· {d}</li>)}
        </ul>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
        </div>
      ) : items.length === 0 ? (
        <Card variant="dashed" className="animate-slide-up px-6 py-14 text-center">
          <NeuIcon icon={BookMarked} tone="primary" className="mx-auto mb-4" />
          <h2 className="text-title">Todavía no hay guías de trabajo</h2>
          <p className="mx-auto mt-2 max-w-md text-pretty text-body text-muted-foreground">
            Una guía es el método de tu despacho para un tipo de escrito: cómo contestar una demanda,
            cómo estructurar un recurso. Empieza por el camino que te resulte más cómodo — importar
            las que ya tienes en Word, texto o Markdown es el más rápido.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Button onClick={() => fileInput.current?.click()} disabled={importing} className="gap-2">
              <Upload className="h-4 w-4" />
              Importar guías
            </Button>
            <Button variant="outline" onClick={() => setModal(true)} className="gap-2">
              <Plus className="h-4 w-4" />
              Escribir una guía
            </Button>
            <Button variant="outline" onClick={() => setWizardOpen(true)} className="gap-2">
              <Sparkles className="h-4 w-4" />
              Crear con Mia
            </Button>
          </div>
        </Card>
      ) : (
        <ul className="space-y-3">
          {items.map((p, i) => {
            const skill = skills[p.id];
            const archived = p.status === "archived";
            return (
              <li
                key={p.id}
                className={cn(
                  cardVariants(),
                  "flex animate-slide-up items-start gap-4 px-5 py-4",
                  archived && "opacity-60",
                )}
                style={staggerStyle(i)}
              >
                <NeuIcon icon={FileText} tone={archived ? "muted" : "primary"} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate text-section">{p.title}</span>
                    <Badge variant="secondary">{originLabel(p.origin)}</Badge>
                    {healthBadge(p.health_status)}
                    {p.protected ? (
                      <Badge variant="outline" className="gap-1">
                        <ShieldCheck className="h-3 w-3" />
                        Protegida
                      </Badge>
                    ) : null}
                    {archived ? <Badge variant="warning">Archivada</Badge> : null}
                  </div>
                  <div className="mt-0.5 text-body text-muted-foreground">{p.summary}</div>
                  {skill ? (
                    // null ≠ cero (regla operativa §18). `approval_rate` es aprobados /
                    // veces usada: sin usos, el backend devuelve 0.0 por la división que
                    // no se hace, y esta línea lo leía como «la aprobaste el 0 % de las
                    // veces» — un reproche sobre una guía que Mia nunca llegó a usar. Lo
                    // que decide si hay medida son las activaciones, no la tasa.
                    <MetricaBarra
                      className="mt-2"
                      label="La aprobaste el % de las veces"
                      fraccion={skill.activations > 0 ? skill.approval_rate : null}
                      sinMedir="Mia todavía no ha usado esta guía en ningún caso"
                      sufijo={` · Mia la usó ${skill.activations} ${skill.activations === 1 ? "vez" : "veces"}`}
                    />
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <Button size="sm" variant="ghost" onClick={() => openView(p)}>
                      Ver
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => openEdit(p)} className="gap-1.5">
                      <Pencil className="h-3.5 w-3.5" />
                      Editar
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => toggleArchive(p)}
                      disabled={busyId === p.id}
                      className="gap-1.5"
                    >
                      {archived ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
                      {archived ? "Reactivar" : "Desactivar"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => openHistory(p)} className="gap-1.5">
                      <History className="h-3.5 w-3.5" />
                      Historial
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => checkHealth(p)}
                      disabled={healthBusyId === p.id}
                      className="gap-1.5"
                    >
                      {healthBusyId === p.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ShieldCheck className="h-3.5 w-3.5" />
                      )}
                      Comprobar citas
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Escribir una guía a mano */}
      <Dialog open={modal} onOpenChange={setModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Enseñarle algo a Mia</DialogTitle>
            <DialogDescription>
              Escribe una guía de trabajo del despacho para que Mia la aplique en sus borradores.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <TextField label="Título" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
            <TextField label="Cuándo aplica" value={form.applies_when} onChange={(v) => setForm({ ...form, applies_when: v })} />
            <div className="space-y-1.5">
              <Label htmlFor="playbook-content">Contenido</Label>
              <Textarea
                id="playbook-content"
                value={form.content}
                onChange={(e) => setForm({ ...form, content: e.target.value })}
                className="h-28 resize-none"
                placeholder="Explica el paso a paso como se lo explicarías a un abogado junior"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setModal(false)}>
              Cancelar
            </Button>
            <Button onClick={create}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Ver (solo lectura) */}
      <Dialog open={!!viewing} onOpenChange={(o) => { if (!o) setViewing(null); }}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{viewing?.title}</DialogTitle>
            <DialogDescription>{viewing?.applies_when || viewing?.summary}</DialogDescription>
          </DialogHeader>
          {viewLoading ? (
            <div className="space-y-2 rounded-lg bg-muted/50 p-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <div className="whitespace-pre-wrap rounded-lg bg-muted/50 p-4 font-serif text-body leading-relaxed text-foreground">
              {viewing?.content}
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setViewing(null)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Editar */}
      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Editar guía</DialogTitle>
            <DialogDescription>
              Los cambios quedan guardados en el historial de esta guía por si necesitas volver atrás.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <TextField label="Título" value={editForm.title} onChange={(v) => setEditForm({ ...editForm, title: v })} />
            <TextField label="Resumen" value={editForm.summary} onChange={(v) => setEditForm({ ...editForm, summary: v })} />
            <TextField
              label="Cuándo aplica"
              value={editForm.applies_when}
              onChange={(v) => setEditForm({ ...editForm, applies_when: v })}
            />
            <div className="space-y-1.5">
              <Label htmlFor="playbook-edit-content">Contenido</Label>
              <Textarea
                id="playbook-edit-content"
                value={editForm.content}
                onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                className="h-48 resize-none"
              />
            </div>
          </div>
          {editError ? <p className="text-body text-destructive">{editError}</p> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)} disabled={editSaving}>
              Cancelar
            </Button>
            <Button onClick={saveEdit} disabled={editSaving} className="gap-2">
              {editSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Guardar cambios
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Historial de versiones */}
      <Dialog open={!!historyFor} onOpenChange={(o) => { if (!o) setHistoryFor(null); }}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Historial — {historyFor?.title}</DialogTitle>
            <DialogDescription>Versiones anteriores de esta guía. Puedes restaurar cualquiera.</DialogDescription>
          </DialogHeader>
          {historyLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-14 w-full rounded-lg" />
              <Skeleton className="h-14 w-full rounded-lg" />
            </div>
          ) : versions.length === 0 ? (
            <p className="text-body text-muted-foreground">Esta guía todavía no tiene versiones anteriores.</p>
          ) : (
            <ul className="space-y-2">
              {versions.map((v) => (
                <li key={v.id} className={cn(cardVariants(), "px-3 py-2.5")}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-label">{v.title}</div>
                      <div className="mt-0.5 text-meta text-muted-foreground">
                        {v.changed_by === "mia" ? "Cambio de Mia" : "Cambio del abogado"} · {fmtDateTime(v.created_at)}
                        {v.reason ? ` · ${v.reason}` : ""}
                      </div>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => restoreVersion(v.id)} className="shrink-0">
                      Restaurar
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {restoreError ? <p className="text-body text-destructive">{restoreError}</p> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setHistoryFor(null)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <GuideInterviewWizard open={wizardOpen} onOpenChange={setWizardOpen} kind="guia" onSaved={load} />
    </div>
  );
}

type Proposal = {
  id: string;
  type: string;
  suggestion: string;
  reason: string;
  target?: string | null;
  source_matters?: string[];
};
type CuratorMerge = { target_title?: string; reason?: string };
type CuratorDeletion = { title?: string; reason?: string };
// Una guía en conflicto, tal como la ve el abogado: su texto, su fecha y de dónde salió.
// `dice` resume lo que ordena ESTA versión por separado — nunca una mezcla de las dos.
type ConflictSide = {
  id: string;
  title?: string;
  summary?: string;
  applies_when?: string;
  extracto?: string;
  fecha?: string;
  procedencia?: string;
  dice?: string;
};
type CuratorConflict = { a: ConflictSide; b: ConflictSide; score?: number; confianza?: number };
type CuratorProposal = {
  id: string;
  // 'cleanup' = unir parecidas / archivar sin uso (se aprueba en bloque).
  // 'conflict' = dos versiones que se contradicen (se elige una, o ninguna).
  kind?: string;
  conflict?: CuratorConflict | null;
  merges?: CuratorMerge[];
  proposed_merges?: CuratorMerge[];
  deletions?: CuratorDeletion[];
  proposed_deletions?: CuratorDeletion[];
};

function Sugerencias() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [curator, setCurator] = useState<CuratorProposal[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // B2 · disparo manual del aprendizaje ("Revisar ahora").
  const [reviewing, setReviewing] = useState(false);
  const [reviewMsg, setReviewMsg] = useState<string | null>(null);
  // Conflicto que se está resolviendo (para no dejar votar dos veces mientras viaja).
  const [conflictBusy, setConflictBusy] = useState<string | null>(null);

  // B4 · "Editar antes de aplicar": el abogado corrige el título/contenido antes
  // de que la sugerencia se convierta en guía o modifique una existente.
  const [editing, setEditing] = useState<Proposal | null>(null);
  const [editForm, setEditForm] = useState({ title: "", content: "" });
  const [editSaving, setEditSaving] = useState(false);

  async function load() {
    const results = await Promise.allSettled([
      apiGet<Proposal[]>("/api/proposals"),
      apiGet<CuratorProposal[]>("/api/curator/proposals"),
      apiGet<{ report: string | null }>("/api/dreams/report"),
    ]);
    const proposals = results[0].status === "fulfilled" ? results[0].value : [];
    const curatorProposals = results[1].status === "fulfilled" ? results[1].value : [];
    const weekly = results[2].status === "fulfilled" ? results[2].value : { report: null };
    setItems(proposals);
    setCurator(curatorProposals);
    setReport(weekly.report);
    setLoadError(
      results.some((result) => result.status === "rejected")
        ? "No pude actualizar todas las mejoras. Estos datos pueden estar incompletos."
        : null,
    );
  }
  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  async function act(id: string, action: "apply" | "ignore") {
    setMsg(null);
    try {
      await apiSend("POST", `/api/proposals/${id}/${action}`);
    } catch (e) {
      setMsg(plainMessage(e, "No se pudo procesar la propuesta. Intenta de nuevo."));
    }
    await load();
  }

  function openEdit(p: Proposal) {
    setEditForm({ title: p.target || "", content: p.suggestion });
    setEditing(p);
  }

  async function saveEditAndApply() {
    if (!editing) return;
    if (!editForm.content.trim()) return;
    setEditSaving(true);
    try {
      await apiSend("POST", `/api/proposals/${editing.id}/apply`, {
        content: editForm.content.trim(),
        title: editForm.title.trim() || undefined,
      });
      setEditing(null);
      await load();
    } catch {
      /* el abogado puede reintentar desde la lista */
    } finally {
      setEditSaving(false);
    }
  }

  async function curatorAct(id: string, action: "approve" | "reject") {
    setMsg(null);
    try {
      await apiSend("POST", `/api/curator/proposals/${id}/${action}`);
    } catch (e) {
      // 409 = el conocimiento cambió desde que se generó (drift); otro error = genérico.
      const drift = e instanceof ApiError && e.status === 409;
      setMsg(drift
        ? "El conocimiento cambió desde que se generó esta propuesta y ya no se puede aplicar tal cual. Recházala: Mia generará una nueva actualizada en su próxima revisión."
        : "No se pudo procesar la propuesta. Intenta de nuevo.");
    }
    await load();
  }

  // Conflicto de criterio: el abogado elige con qué versión se queda el despacho ('a' | 'b'),
  // o decide sostener las dos ('none'). Mia nunca las funde.
  async function resolveConflict(id: string, choice: "a" | "b" | "none") {
    setMsg(null);
    setConflictBusy(id);
    try {
      await apiSend("POST", `/api/curator/proposals/${id}/resolve`, { choice });
    } catch (e) {
      // Mismo criterio que arriba: 409 = el conocimiento cambió desde que se detectó.
      const drift = e instanceof ApiError && e.status === 409;
      setMsg(drift
        ? "El conocimiento cambió desde que Mia detectó esta contradicción, así que no se aplicó nada. Mia volverá a plantearla actualizada en su próxima revisión."
        : plainMessage(e, "No se pudo guardar tu decisión. Intenta de nuevo."));
    } finally {
      setConflictBusy(null);
    }
    await load();
  }

  // B2 · Mia revisa su trabajo reciente AHORA (sin esperar al ciclo diario) y propone mejoras.
  async function revisarAhora() {
    setReviewMsg(null);
    setReviewing(true);
    try {
      const res = await apiSend<{ propuestas_nuevas: number }>("POST", "/api/learning/run");
      await load();
      const n = res?.propuestas_nuevas ?? 0;
      setReviewMsg(
        n > 0
          ? `Mia propuso ${n} mejora${n === 1 ? "" : "s"} nueva${n === 1 ? "" : "s"} para tu revisión.`
          : "Mia no encontró nada nuevo que proponer todavía."
      );
    } catch {
      setReviewMsg("No se pudo completar la revisión. Intenta de nuevo.");
    } finally {
      setReviewing(false);
    }
  }

  // La barra de revisión sube a superficie del sistema: es una ACCIÓN del
  // abogado sobre esta pantalla, no un pie de página. Con su icono en bajo
  // relieve se lee como control, que es lo que es.
  const reviewBar = (
    <Card padding="sm" className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <NeuIcon icon={Sparkles} tone="primary" size="sm" />
        <div className="min-w-0">
          <p className="text-section">Mia revisa su propio trabajo</p>
          <p className="mt-0.5 text-pretty text-body text-muted-foreground">
            {reviewMsg ||
              "Cada día repasa los casos recientes y anota qué puede hacer mejor. Pídele que lo haga ahora si acabas de cerrar algo importante."}
          </p>
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={revisarAhora}
        disabled={reviewing}
        className="gap-1.5"
      >
        {reviewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        {reviewing ? "Mia está revisando…" : "Revisar ahora"}
      </Button>
    </Card>
  );

  const loadErrorBanner = loadError ? (
    <Card padding="sm" className="flex flex-wrap items-center justify-between gap-3 border-warning/30 bg-warning/5">
      <p role="alert" className="text-body text-warning">{loadError}</p>
      <Button size="sm" variant="outline" onClick={load}>Reintentar</Button>
    </Card>
  ) : null;

  // Dos cosas distintas que exigen dos decisiones distintas: la limpieza se aprueba en bloque;
  // el conflicto se resuelve eligiendo. Un solo botón para ambas sería el atajo que corrompe
  // el criterio.
  const cleanups = curator.filter((c) => c.kind !== "conflict");
  const conflicts = curator.filter((c) => c.kind === "conflict" && !!c.conflict);

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
    );
  }

  if (items.length === 0 && curator.length === 0 && !report && !loadError) {
    return (
      <div className="space-y-4">
        {reviewBar}
        <Card variant="dashed" className="animate-slide-up px-6 py-14 text-center">
          <NeuIcon icon={Lightbulb} tone="primary" className="mx-auto mb-4" />
          <h2 className="text-title">No hay mejoras esperando tu decisión</h2>
          <p className="mx-auto mt-2 max-w-md text-pretty text-body text-muted-foreground">
            Cuando Mia encuentre una guía que mejorar, dos criterios que se contradicen o
            conocimiento repetido, lo verás aquí con su motivo. Si quieres adelantar el repaso,
            usa «Revisar ahora».
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviewBar}
      {loadErrorBanner}
      {msg ? (
        <p className="rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{msg}</p>
      ) : null}
      {report ? (
        <Card className="animate-slide-up p-5">
          <div className="mb-3 flex items-center gap-3">
            <NeuIcon icon={Lightbulb} tone="primary" size="sm" />
            <div>
              <p className="text-section">Lo que aprendí esta semana</p>
              <p className="text-body text-muted-foreground">El resumen de Mia sobre el trabajo de los últimos días.</p>
            </div>
          </div>
          <p className="whitespace-pre-wrap font-serif text-body leading-relaxed text-foreground">{report}</p>
        </Card>
      ) : null}
      {items.length > 0 ? (
        <SectionTitle
          level="h3"
          icon={Lightbulb}
          title="Esperan tu decisión"
          hint="Aplica lo que te sirva, corrígelo antes de guardarlo o descártalo. Lo que descartes no vuelve a proponerse igual."
          className="mb-3 mt-6"
        />
      ) : null}
      <ul className="space-y-3">
        {items.map((p, i) => (
          <li
            key={p.id}
            className={cn(cardVariants(), "animate-slide-up px-5 py-4")}
            style={staggerStyle(i)}
          >
            <div className="flex items-start gap-3">
              <NeuIcon icon={Lightbulb} tone="primary" size="sm" />
              <div className="min-w-0 flex-1">
                <Badge variant="secondary" className="mb-2">{p.type}</Badge>
                {p.target ? (
                  <div className="mb-1 text-label">Guía que cambia si lo apruebas: {p.target}</div>
                ) : null}
                <div className="mb-2 whitespace-pre-wrap text-pretty text-body">{p.suggestion}</div>
                <div className="text-pretty text-body text-muted-foreground">{p.reason}</div>
                {p.source_matters && p.source_matters.length > 0 ? (
                  <div className="mt-1.5 text-meta text-muted-foreground">
                    Lo aprendí trabajando en: {p.source_matters.join(", ")}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => act(p.id, "apply")} className="gap-1.5">
                <Check className="h-3.5 w-3.5" />
                Aplicar
              </Button>
              <Button size="sm" variant="outline" onClick={() => openEdit(p)} className="gap-1.5">
                <Pencil className="h-3.5 w-3.5" />
                Editar antes de aplicar
              </Button>
              <Button size="sm" variant="ghost" onClick={() => act(p.id, "ignore")}>
                Ignorar
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Editar antes de aplicar</DialogTitle>
            <DialogDescription>
              Corrige lo que Mia propone antes de guardarlo. Nada cambia hasta que confirmes aquí.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <TextField
              label="Título de la guía"
              value={editForm.title}
              onChange={(v) => setEditForm({ ...editForm, title: v })}
            />
            <div className="space-y-1.5">
              <Label htmlFor="proposal-edit-content">Contenido</Label>
              <Textarea
                id="proposal-edit-content"
                value={editForm.content}
                onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                className="h-48 resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)} disabled={editSaving}>
              Cancelar
            </Button>
            <Button onClick={saveEditAndApply} disabled={editSaving} className="gap-2">
              {editSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Aplicar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {conflicts.length > 0 ? (
        <div>
          <SectionTitle
            level="h3"
            icon={GitCompareArrows}
            title="Dos guías dicen lo contrario"
            hint="Mia no las une por su cuenta: eso dejaría un criterio que nadie escribió. Elige tú cuál rige hoy."
            className="mb-3 mt-6"
          />
          <ul className="space-y-3">
            {conflicts.map((c, i) => (
              <li
                key={c.id}
                className={cn(cardVariants(), "animate-slide-up border-warning/40 px-5 py-4")}
                style={staggerStyle(i)}
              >
                <div className="mb-3 flex items-start gap-3">
                  <NeuIcon icon={GitCompareArrows} tone="warning" size="sm" />
                  <p className="text-pretty text-body text-muted-foreground">
                    Estas dos se parecen tanto que Mia iba a unirlas, pero ordenan cosas opuestas.
                    Lee lo que dice cada una y quédate con la que representa al despacho hoy.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(["a", "b"] as const).map((side) => {
                    const v = c.conflict?.[side];
                    if (!v) return null;
                    return (
                      <div key={side} className="flex flex-col rounded-lg shadow-neu-raised border border-border/10 border-border/10 bg-muted/30 p-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="truncate text-section">{v.title}</span>
                          <Badge variant="secondary">{originLabel(v.procedencia)}</Badge>
                        </div>
                        <div className="mt-0.5 text-meta text-muted-foreground">
                          {v.fecha ? `Actualizada el ${v.fecha}` : "Sin fecha"}
                        </div>
                        <div className="mt-2 text-body">
                          <span className="text-muted-foreground">Esta dice: </span>
                          {v.dice}
                        </div>
                        {v.extracto ? (
                          <p className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-sm bg-background/60 p-2 font-serif text-meta leading-relaxed text-muted-foreground">
                            {v.extracto}
                          </p>
                        ) : null}
                        <Button
                          size="sm"
                          onClick={() => resolveConflict(c.id, side)}
                          disabled={conflictBusy === c.id}
                          className="mt-3 gap-1.5"
                        >
                          {conflictBusy === c.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Check className="h-3.5 w-3.5" />
                          )}
                          Me quedo con esta
                        </Button>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => resolveConflict(c.id, "none")}
                    disabled={conflictBusy === c.id}
                  >
                    Dejar las dos
                  </Button>
                  <span className="text-meta text-muted-foreground">
                    La que no elijas se archiva y puedes reactivarla cuando quieras. Si dejas las
                    dos, Mia las conserva y no vuelve a proponer unirlas.
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {cleanups.length > 0 ? (
        <div>
          <SectionTitle
            level="h3"
            icon={Sparkles}
            title="Poner orden en lo que ya sabe"
            hint="Unir guías casi idénticas y apartar las que nadie usa. Se aprueba en bloque y siempre se puede reactivar lo archivado."
            className="mb-3 mt-6"
          />
          <ul className="space-y-3">
            {cleanups.map((c, i) => {
              const merges = c.merges || c.proposed_merges || [];
              const deletions = c.deletions || c.proposed_deletions || [];
              return (
                <li
                  key={c.id}
                  className={cn(cardVariants(), "animate-slide-up px-5 py-4")}
                  style={staggerStyle(i)}
                >
                  <div className="mb-2 text-body">
                    Mia propone ordenar el conocimiento del despacho:
                    {merges.length > 0 ? ` unir ${merges.length} pareja${merges.length === 1 ? "" : "s"} de guías muy parecidas` : ""}
                    {merges.length > 0 && deletions.length > 0 ? " y" : ""}
                    {deletions.length > 0 ? ` archivar ${deletions.length} guía${deletions.length === 1 ? "" : "s"} sin uso` : ""}.
                  </div>
                  <ul className="mb-3 space-y-1 text-body text-muted-foreground">
                    {merges.map((m, j) => <li key={`m${j}`}>· {m.target_title || m.reason}</li>)}
                    {deletions.map((d, j) => <li key={`d${j}`}>· Archivar: {d.title}</li>)}
                  </ul>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => curatorAct(c.id, "approve")} className="gap-1.5">
                      <Check className="h-3.5 w-3.5" />
                      Aprobar
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => curatorAct(c.id, "reject")}>
                      Rechazar
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

