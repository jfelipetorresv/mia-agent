"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  BookMarked,
  BookOpen,
  Building2,
  Check,
  FileText,
  FolderOpen,
  GraduationCap,
  Lightbulb,
  Loader2,
  Plus,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { apiGet, apiSend, apiUploadMany } from "@/lib/api";
import { Button } from "@/components/ui/button";
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

type Tab = "despacho" | "wiki" | "saber" | "habilidades" | "sugerencias";

export default function MemoriaPage() {
  const [tab, setTab] = useState<Tab>("despacho");
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <div className="mb-8 animate-slide-up">
        <h1 className="text-2xl font-semibold tracking-tight">Conocimiento</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Lo que Mia sabe de tu despacho y cómo lo va aprendiendo contigo. Mia propone; tú decides.
        </p>
      </div>

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
            Guías y documentos
          </TabsTrigger>
          <TabsTrigger value="habilidades" className="gap-1.5">
            <Sparkles className="h-4 w-4" />
            Lo que Mia sabe hacer
          </TabsTrigger>
          <TabsTrigger value="sugerencias" className="gap-1.5">
            <Lightbulb className="h-4 w-4" />
            Mejoras que Mia propone
          </TabsTrigger>
        </TabsList>

        <TabsContent value="despacho">
          <Despacho />
        </TabsContent>
        <TabsContent value="wiki">
          <Wiki />
        </TabsContent>
        <TabsContent value="saber">
          <Saber />
        </TabsContent>
        <TabsContent value="habilidades">
          <Habilidades />
        </TabsContent>
        <TabsContent value="sugerencias">
          <Sugerencias />
        </TabsContent>
      </Tabs>
    </div>
  );
}

type Profile = {
  name?: string;
  lawyer_name?: string;
  jurisdiction?: string;
  practice_areas?: string[];
  voice_adjectives?: string[];
};

function Despacho() {
  const [p, setP] = useState<Profile>({ jurisdiction: "", practice_areas: [], voice_adjectives: [] });
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Profile>("/api/profile")
      .then((d) => setP({ jurisdiction: "", practice_areas: [], voice_adjectives: [], ...d }))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    await apiSend("PUT", "/api/profile", p);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full rounded-xl" />
        <Skeleton className="h-14 w-full rounded-xl" />
        <Skeleton className="h-14 w-full rounded-xl" />
        <Skeleton className="h-14 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="animate-slide-up space-y-4">
      <p className="text-sm text-muted-foreground">
        Estos datos le dan contexto a Mia en cada asunto: quién eres, dónde ejerces y cómo te gusta escribir.
      </p>
      <TextField label="Nombre del despacho" value={p.name || ""} onChange={(v) => setP({ ...p, name: v })} />
      <TextField label="Abogado responsable" value={p.lawyer_name || ""} onChange={(v) => setP({ ...p, lawyer_name: v })} />
      <TextField label="País y sistema jurídico principal" value={p.jurisdiction || ""} onChange={(v) => setP({ ...p, jurisdiction: v })} />
      <ChipsField label="Áreas de práctica" value={p.practice_areas || []} onChange={(v) => setP({ ...p, practice_areas: v })} />
      <ChipsField label="Estilo" value={p.voice_adjectives || []} onChange={(v) => setP({ ...p, voice_adjectives: v })} />
      <div className="flex items-center gap-3 pt-2">
        <Button onClick={save}>Guardar</Button>
        {saved ? (
          <span className="flex items-center gap-1.5 text-sm text-success animate-fade-in">
            <Check className="h-4 w-4" />
            Guardado
          </span>
        ) : null}
      </div>
    </div>
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
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <BookOpen className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-medium">Aún no hay criterios aprendidos</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
          A medida que trabajen asuntos juntos, Mia irá consolidando aquí los criterios
          jurídicos de tu despacho: cómo analizas cada tema y qué posiciones defiendes.
        </p>
        <Button asChild variant="outline" className="mt-6 gap-2">
          <Link href="/">
            <FolderOpen className="h-4 w-4" />
            Ir a mis asuntos
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <ul className="space-y-3">
        {items.map((c, i) => (
          <li key={c.name} className="animate-slide-up" style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}>
            <button
              onClick={() => open(c)}
              className="group flex w-full items-center justify-between gap-4 rounded-xl border border-border bg-card px-5 py-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md"
            >
              <div className="min-w-0">
                <div className="truncate font-medium">{c.name}</div>
                <div className="mt-0.5 text-sm text-muted-foreground">
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
                <div className="mt-1 text-right text-xs text-muted-foreground">
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
            <div className="whitespace-pre-wrap rounded-lg bg-muted/50 p-4 font-serif text-sm leading-relaxed text-foreground">
              {markdown}
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

type Playbook = { id: string; title: string; summary: string; applies_when?: string };

function Saber() {
  const [items, setItems] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ title: "", applies_when: "", content: "", summary: "" });

  async function load() {
    setItems(await apiGet<Playbook[]>("/api/playbooks").catch(() => []));
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
          {importing ? "Importando…" : "Importar guías"}
        </Button>
        <Button variant="outline" onClick={() => setModal(true)} className="gap-2">
          <GraduationCap className="h-4 w-4" />
          Enseñarle algo a Mia
        </Button>
      </div>

      {importMsg ? (
        <p
          className={`mb-2 rounded-md px-3 py-2 text-sm ${
            importError ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
          }`}
        >
          {importMsg}
        </p>
      ) : null}
      {importDetail.length > 0 ? (
        <ul className="mb-3 space-y-0.5 text-sm text-muted-foreground">
          {importDetail.map((d, i) => <li key={i}>· {d}</li>)}
        </ul>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      ) : items.length === 0 ? (
        <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <BookMarked className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-medium">Mia aún no tiene guías del despacho</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Aquí viven las guías de trabajo de tu despacho: cómo contestar una demanda,
            cómo estructurar un recurso. Impórtalas (.md, .txt o Word) o escríbelas tú mismo.
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
          </div>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((p, i) => (
            <li
              key={p.id}
              className="flex animate-slide-up items-start gap-4 rounded-xl border border-border bg-card px-5 py-4 shadow-sm"
              style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <FileText className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <div className="truncate font-medium">{p.title}</div>
                <div className="mt-0.5 text-sm text-muted-foreground">{p.summary}</div>
              </div>
            </li>
          ))}
        </ul>
      )}

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
    </div>
  );
}

type Skill = { skill_id: string; title: string; approval_rate: number; edit_rate: number; activations: number };

function Habilidades() {
  const [items, setItems] = useState<Skill[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    apiGet<Skill[]>("/api/skills/ranked")
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Sparkles className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-medium">Mia todavía no tiene habilidades medidas</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
          Cada vez que apruebas o corriges el trabajo de Mia, aquí verás qué tan bien le va
          con cada procedimiento del despacho. Empieza aprobando su primer borrador.
        </p>
        <Button asChild variant="outline" className="mt-6 gap-2">
          <Link href="/">
            <FolderOpen className="h-4 w-4" />
            Ir a mis asuntos
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-4 text-sm text-muted-foreground">
        Qué tan bien le va a Mia con cada procedimiento del despacho, según tus aprobaciones y correcciones.
      </p>
      <ul className="space-y-3">
        {items.map((s, i) => (
          <li
            key={s.skill_id}
            className="animate-slide-up rounded-xl border border-border bg-card px-5 py-4 shadow-sm"
            style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}
          >
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="truncate font-medium">{s.title}</div>
                <div className="mt-0.5 text-sm text-muted-foreground">
                  Usada {s.activations} {s.activations === 1 ? "vez" : "veces"}
                  {s.activations > 0 ? ` · corregida el ${Math.round((s.edit_rate || 0) * 100)}%` : ""}
                </div>
              </div>
              <div className="w-28 shrink-0">
                <div className="h-1.5 rounded-full bg-muted">
                  <div
                    className="h-1.5 rounded-full bg-primary transition-all duration-200"
                    style={{ width: `${Math.round((s.approval_rate || 0) * 100)}%` }}
                  />
                </div>
                <div className="mt-1 text-right text-xs text-muted-foreground">
                  {Math.round((s.approval_rate || 0) * 100)}% aprobado
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Proposal = { id: string; type: string; suggestion: string; reason: string; target?: string | null };
type CuratorMerge = { target_title?: string; reason?: string };
type CuratorDeletion = { title?: string; reason?: string };
type CuratorProposal = {
  id: string;
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
    await apiSend("POST", `/api/proposals/${id}/${action}`).catch(() => {});
    await load();
  }

  async function curatorAct(id: string, action: "approve" | "reject") {
    setMsg(null);
    try {
      await apiSend("POST", `/api/curator/proposals/${id}/${action}`);
    } catch (e) {
      // 409 = el conocimiento cambió desde que se generó (drift); otro error = genérico.
      const drift = e instanceof Error && e.message.includes("409");
      setMsg(drift
        ? "El conocimiento cambió desde que se generó esta propuesta y ya no se puede aplicar tal cual. Recházala: Mia generará una nueva actualizada en su próxima revisión."
        : "No se pudo procesar la propuesta. Intenta de nuevo.");
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
          <p className="text-sm text-muted-foreground">{reviewMsg}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
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

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }

  if (items.length === 0 && curator.length === 0 && !report) {
    return (
      <div className="space-y-4">
        {reviewBar}
        <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Lightbulb className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-medium">Mia aún no propone mejoras</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Cuando Mia detecte formas de mejorar sus guías o de ordenar el conocimiento del
            despacho, te las propondrá aquí. Nada cambia sin tu aprobación.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviewBar}
      {report ? (
        <div className="animate-slide-up rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Lightbulb className="h-4 w-4 text-primary" />
            Resumen semanal
          </div>
          <p className="whitespace-pre-wrap font-serif text-sm leading-relaxed text-foreground">{report}</p>
        </div>
      ) : null}
      <ul className="space-y-3">
        {items.map((p, i) => (
          <li
            key={p.id}
            className="animate-slide-up rounded-xl border border-border bg-card px-5 py-4 shadow-sm"
            style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}
          >
            <Badge variant="secondary" className="mb-2">{p.type}</Badge>
            {p.target ? (
              <div className="mb-1 text-sm font-medium">Procedimiento que se modificaría: {p.target}</div>
            ) : null}
            <div className="mb-2 whitespace-pre-wrap text-sm">{p.suggestion}</div>
            <div className="text-sm text-muted-foreground">{p.reason}</div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => act(p.id, "apply")} className="gap-1.5">
                <Check className="h-3.5 w-3.5" />
                Aplicar
              </Button>
              <Button size="sm" variant="ghost" onClick={() => act(p.id, "ignore")}>
                Ignorar
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {curator.length > 0 ? (
        <div>
          <h3 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Orden del conocimiento
          </h3>
          {msg ? (
            <p className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{msg}</p>
          ) : null}
          <ul className="space-y-3">
            {curator.map((c, i) => {
              const merges = c.merges || c.proposed_merges || [];
              const deletions = c.deletions || c.proposed_deletions || [];
              return (
                <li
                  key={c.id}
                  className="animate-slide-up rounded-xl border border-border bg-card px-5 py-4 shadow-sm"
                  style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}
                >
                  <div className="mb-2 text-sm">
                    Mia propone ordenar el conocimiento del despacho:
                    {merges.length > 0 ? ` unir ${merges.length} pareja${merges.length === 1 ? "" : "s"} de guías muy parecidas` : ""}
                    {merges.length > 0 && deletions.length > 0 ? " y" : ""}
                    {deletions.length > 0 ? ` archivar ${deletions.length} guía${deletions.length === 1 ? "" : "s"} sin uso` : ""}.
                  </div>
                  <ul className="mb-3 space-y-1 text-sm text-muted-foreground">
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

function ChipsField({ label, value, onChange }: { label: string; value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  }
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-input bg-card px-2 py-2 transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background">
        {value.map((chip) => (
          <Badge key={chip} variant="secondary" className="gap-1 pr-1">
            {chip}
            <button
              type="button"
              onClick={() => onChange(value.filter((c) => c !== chip))}
              aria-label={`Quitar ${chip}`}
              className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Escribe y presiona Enter"
          className="min-w-[120px] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
        />
      </div>
    </div>
  );
}
