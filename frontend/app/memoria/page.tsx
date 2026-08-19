"use client";

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

export default function MemoriaPage() {
  const [tab, setTab] = useState<Tab>("despacho");
  return (
    <PageShell
      title="Conocimiento"
      subtitle="Lo que Mia sabe de tu despacho y cómo lo va aprendiendo contigo. Mia propone; tú decides."
    >
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList className="mb-6 h-auto flex-wrap justify-start gap-1">
          <TabsTrigger value="despacho" className="gap-1.5">
            <Building2 className="h-4 w-4" />
            Mi despacho
          </TabsTrigger>
          <TabsTrigger value="wiki" className="gap-1.5">
            <BookOpen className="h-4 w-4" />
            Criterios aprendidos
          </TabsTrigger>
          <TabsTrigger value="saber" className="gap-1.5">
            <BookMarked className="h-4 w-4" />
            Guías y habilidades
          </TabsTrigger>
          <TabsTrigger value="sugerencias" className="gap-1.5">
            <Lightbulb className="h-4 w-4" />
            Mejoras que Mia propone
          </TabsTrigger>
        </TabsList>

        <TabsContent value="despacho">
          <MiDespachoSection />
        </TabsContent>
        <TabsContent value="wiki">
          <Wiki />
        </TabsContent>
        <TabsContent value="saber">
          <Saber />
        </TabsContent>
        <TabsContent value="sugerencias">
          <Sugerencias />
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
      <div className="space-y-3">
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card variant="dashed" className="animate-slide-up px-6 py-16 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <BookOpen className="h-6 w-6" />
        </div>
        <h2 className="text-title">Aún no hay criterios aprendidos</h2>
        <p className="mx-auto mt-2 max-w-sm text-body text-muted-foreground">
          A medida que trabajen asuntos juntos, Mia irá consolidando aquí los criterios
          jurídicos de tu despacho: cómo analizas cada tema y qué posiciones defiendes.
        </p>
        <Button asChild variant="outline" className="mt-6 gap-2">
          <Link href="/">
            <FolderOpen className="h-4 w-4" />
            Ir a mis asuntos
          </Link>
        </Button>
      </Card>
    );
  }

  return (
    <div>
      <ul className="space-y-3">
        {items.map((c, i) => (
          <li key={c.name} className="animate-slide-up" style={staggerStyle(i)}>
            <button
              onClick={() => open(c)}
              className={cn(
                cardVariants({ interactive: true }),
                "group flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:border-primary/35",
              )}
            >
              <div className="min-w-0">
                <div className="truncate text-section">{c.name}</div>
                <div className="mt-0.5 text-body text-muted-foreground">
                  {c.case_count} {c.case_count === 1 ? "caso" : "casos"} · {c.last_updated || "sin fecha"}
                </div>
              </div>
              <div className="w-28 shrink-0">
                <div className="h-1.5 rounded-full bg-muted">
                  <div
                    className="h-1.5 rounded-full bg-primary transition-all duration-200"
                    style={{ width: `${Math.round((c.confidence || 0) * 100)}%` }}
                  />
                </div>
                <div className="mt-1 text-right text-meta nums text-muted-foreground">
                  {Math.round((c.confidence || 0) * 100)}% consolidado
                </div>
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
              Así entiende Mia este tema hoy. Si algo no refleja el criterio del despacho, corrígelo abajo.
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
            <Label htmlFor="wiki-correction">Sugerir corrección</Label>
            <Textarea
              id="wiki-correction"
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              className="h-24 resize-none"
              placeholder="Explícale a Mia qué debe ajustar de este criterio"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Cerrar
            </Button>
            <Button onClick={sendCorrection}>Enviar</Button>
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
  asunto: "Nacida de un asunto",
  aprendida: "Aprendida por Mia",
};

function originLabel(origin?: string): string {
  return ORIGIN_LABEL[origin || "manual"] || "Escrita a mano";
}

// Salud de la guía: 'sano' (citas en regla), 'revisar' (hay algo sin verificar) o
// 'sin_revisar' (todavía no se ha chequeado). Nunca se muestra el nombre técnico del campo.
const HEALTH_LABEL: Record<string, string> = {
  sano: "Sana",
  revisar: "Revisar",
  sin_revisar: "Sin revisar",
};

function healthBadge(status?: string) {
  const s = status || "sin_revisar";
  const label = HEALTH_LABEL[s] || "Sin revisar";
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
      applies_when: form.applies_when.trim() || "Depende del contexto del asunto.",
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
      <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".md,.txt,.docx"
          className="hidden"
          onChange={(e) => importFiles(e.target.files)}
        />
        <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={importing} className="gap-2">
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {importing ? "Importando…" : "Importar"}
        </Button>
        <Button variant="outline" onClick={() => setModal(true)} className="gap-2">
          <GraduationCap className="h-4 w-4" />
          Escribir
        </Button>
        <Button onClick={() => setWizardOpen(true)} className="gap-2">
          <Sparkles className="h-4 w-4" />
          Crear con Mia
        </Button>
      </div>

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
        <Card variant="dashed" className="animate-slide-up px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <BookMarked className="h-6 w-6" />
          </div>
          <h2 className="text-title">Mia aún no tiene guías del despacho</h2>
          <p className="mx-auto mt-2 max-w-sm text-body text-muted-foreground">
            Aquí viven las guías de trabajo de tu despacho: cómo contestar una demanda,
            cómo estructurar un recurso. Impórtalas (.md, .txt o Word), escríbelas tú mismo
            o deja que Mia te ayude a extraerlas con unas preguntas.
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
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="h-5 w-5" />
                </div>
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
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 w-24 shrink-0 rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full bg-primary transition-all duration-200"
                          style={{ width: `${Math.round((skill.approval_rate || 0) * 100)}%` }}
                        />
                      </div>
                      <span className="text-meta nums text-muted-foreground">
                        {Math.round((skill.approval_rate || 0) * 100)}% aprobado · usada {skill.activations}{" "}
                        {skill.activations === 1 ? "vez" : "veces"}
                      </span>
                    </div>
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
                      Revisar salud
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
    setItems(await apiGet<Proposal[]>("/api/proposals").catch(() => []));
    setCurator(await apiGet<CuratorProposal[]>("/api/curator/proposals").catch(() => []));
    const weekly = await apiGet<{ report: string | null }>("/api/dreams/report").catch(() => ({ report: null }));
    setReport(weekly.report);
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

  const reviewBar = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        {reviewMsg ? (
          <p className="text-body text-muted-foreground">{reviewMsg}</p>
        ) : (
          <p className="text-body text-muted-foreground">
            Mia revisa su trabajo reciente y te propone mejoras. Puedes pedirle que revise ahora.
          </p>
        )}
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={revisarAhora}
        disabled={reviewing}
        className="gap-1.5"
      >
        {reviewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        {reviewing ? "Mia está revisando su trabajo reciente…" : "Revisar ahora"}
      </Button>
    </div>
  );

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

  if (items.length === 0 && curator.length === 0 && !report) {
    return (
      <div className="space-y-4">
        {reviewBar}
        <Card variant="dashed" className="animate-slide-up px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Lightbulb className="h-6 w-6" />
          </div>
          <h2 className="text-title">Mia aún no propone mejoras</h2>
          <p className="mx-auto mt-2 max-w-sm text-body text-muted-foreground">
            Cuando Mia detecte formas de mejorar sus guías o de ordenar el conocimiento del
            despacho, te las propondrá aquí. Nada cambia sin tu aprobación.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviewBar}
      {msg ? (
        <p className="rounded-md bg-warning/10 px-3 py-2 text-body text-warning">{msg}</p>
      ) : null}
      {report ? (
        <Card className="animate-slide-up px-5 py-4">
          <div className="mb-2 flex items-center gap-2 text-section">
            <Lightbulb className="h-4 w-4 text-primary" />
            Resumen semanal
          </div>
          <p className="whitespace-pre-wrap font-serif text-body leading-relaxed text-foreground">{report}</p>
        </Card>
      ) : null}
      <ul className="space-y-3">
        {items.map((p, i) => (
          <li
            key={p.id}
            className={cn(cardVariants(), "animate-slide-up px-5 py-4")}
            style={staggerStyle(i)}
          >
            <Badge variant="secondary" className="mb-2">{p.type}</Badge>
            {p.target ? (
              <div className="mb-1 text-label">Procedimiento que se modificaría: {p.target}</div>
            ) : null}
            <div className="mb-2 whitespace-pre-wrap text-body">{p.suggestion}</div>
            <div className="text-body text-muted-foreground">{p.reason}</div>
            {p.source_matters && p.source_matters.length > 0 ? (
              <div className="mt-1.5 text-meta text-muted-foreground">
                Aprendí esto trabajando en: {p.source_matters.join(", ")}
              </div>
            ) : null}
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
          <h3 className="mb-2 mt-6 text-section text-muted-foreground">
            Criterios que se contradicen
          </h3>
          <ul className="space-y-3">
            {conflicts.map((c, i) => (
              <li
                key={c.id}
                className={cn(cardVariants(), "animate-slide-up border-warning/40 px-5 py-4")}
                style={staggerStyle(i)}
              >
                <div className="mb-1 flex items-center gap-2 text-section">
                  <GitCompareArrows className="h-4 w-4 text-warning" />
                  Estas dos guías dicen lo contrario
                </div>
                <p className="mb-3 text-body text-muted-foreground">
                  Se parecen tanto que Mia iba a unirlas, pero ordenan cosas opuestas. No las va a
                  unir: eso dejaría un criterio que nadie escribió. Dime cuál es el criterio del
                  despacho hoy.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(["a", "b"] as const).map((side) => {
                    const v = c.conflict?.[side];
                    if (!v) return null;
                    return (
                      <div key={side} className="flex flex-col rounded-lg border border-border bg-muted/30 p-3">
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
          <h3 className="mb-2 mt-6 text-section text-muted-foreground">
            Orden del conocimiento
          </h3>
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

