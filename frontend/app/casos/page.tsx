"use client";

// D3 · «Casos»: lista ÚNICA. Antes había dos pestañas («Asuntos» y «Proyectos»)
// para la MISMA tabla (matters, columna kind — migración 028). El abogado ve un
// solo concepto: el caso. Lo único que cambia entre casos es cómo entrega Mia su
// trabajo, y eso se elige al crear (y se puede cambiar dentro del caso).

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  ChevronRight,
  FileCheck2,
  FileClock,
  FolderOpen,
  MessageSquareText,
  Plus,
} from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { NotaMia } from "@/app/_components/NotaMia";
import { COUNTRY_NAME_BY_CODE } from "@/app/_components/CountrySelector";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { KIND_LABEL, type CaseKind } from "./[id]/_components/ModoDeTrabajo";

type Caso = {
  id: string;
  name: string;
  description?: string;
  status?: string;
  created_at?: string;
  pending_review?: boolean;
  kind?: string;
  jurisdictions?: string[];
};

const KIND_HELP: Record<CaseKind, string> = {
  asunto: "Mia investiga y te entrega un borrador que tú apruebas antes de que nada salga.",
  proyecto: "Mia te responde de una vez en la conversación y tú guardas lo que te sirva.",
};

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

// useSearchParams() exige un límite <Suspense> en App Router (si no, rompe el
// prerender). El contenido real vive en CasosPageContent; este export solo
// monta el límite.
export default function CasosPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
          <Skeleton className="mb-8 h-10 w-48" />
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        </div>
      }
    >
      <CasosPageContent />
    </Suspense>
  );
}

function CasosPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [casos, setCasos] = useState<Caso[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<CaseKind>("asunto");
  const [organizationJurisdictions, setOrganizationJurisdictions] = useState<string[]>([]);
  const [selectedJurisdictions, setSelectedJurisdictions] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      // kind=todos: la lista única trae los dos modos (compat: sin el parámetro el
      // backend sigue devolviendo solo los de borrador, contrato intacto).
      setCasos(await apiGet<Caso[]>("/api/matters?kind=todos"));
    } catch {
      setCasos([]);
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    apiGet<{ jurisdictions?: string[] }>("/api/profile/full")
      .then((profile) => setOrganizationJurisdictions(
        (profile.jurisdictions || []).filter((code) => code && code !== "generic"),
      ))
      .catch(() => setOrganizationJurisdictions([]));
  }, []);

  // El buscador de comandos (Ctrl+K → "Nuevo caso") llega aquí como "/casos?nuevo=1".
  // Abrimos el diálogo de una vez y borramos la señal de la URL: así un refresco
  // de la página no vuelve a abrirlo solo.
  useEffect(() => {
    if (searchParams.get("nuevo") === "1") {
      setShowModal(true);
      router.replace("/casos", { scroll: false });
    }
  }, [searchParams, router]);

  function openModal() {
    setName("");
    setDescription("");
    setKind("asunto");
    setSelectedJurisdictions([]);
    setError("");
    setShowModal(true);
  }

  async function create() {
    if (creating) return;
    if (!name.trim()) {
      setError("Ponle un nombre al caso.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const m = await apiSend<Caso>("POST", "/api/matters", {
        name: name.trim(),
        description: description.trim(),
        kind,
        ...(selectedJurisdictions.length > 0 ? { jurisdictions: selectedJurisdictions } : {}),
      });
      setShowModal(false);
      router.push(`/casos/${m.id}`);
    } catch {
      setError("No se pudo crear el caso. Intenta de nuevo.");
    }
    setCreating(false);
  }

  const pendientes = casos.filter((c) => c.pending_review).length;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <div className="mb-6 flex items-end justify-between gap-4 animate-slide-up">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Casos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading
              ? "Cargando los casos de tu firma u organización…"
              : casos.length === 0
                ? "Cada caso reúne sus documentos, sus fuentes y tu conversación con Mia."
                : pendientes > 0
                  ? `${casos.length} en curso · ${pendientes} con borrador esperando tu revisión`
                  : `${casos.length} en curso`}
          </p>
        </div>
        <Button onClick={openModal} className="gap-2">
          <Plus className="h-4 w-4" />
          Nuevo caso
        </Button>
      </div>

      {/* La antigua división Asuntos/Proyectos ahora es UNA decisión dentro del caso. */}
      <NotaMia
        id="casos-lista-unificada"
        icon={FolderOpen}
        titulo="Todos tus casos viven aquí"
        className="mb-6"
      >
        En cada caso decides cómo te entrego mi trabajo: con un borrador que tú
        apruebas, o respondiéndote directo en la conversación. Lo eliges al crearlo
        y puedes cambiarlo dentro del caso.
      </NotaMia>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : casos.length === 0 ? (
        <div className="animate-slide-up rounded-2xl bg-card/60 backdrop-blur-md px-6 py-16 text-center shadow-neu-raised border border-border/20">
          <div className="mx-auto mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-transparent text-primary animate-float" style={{ transformStyle: "preserve-3d" }}>
            <svg viewBox="0 0 200 200" className="h-24 w-24 drop-shadow-[0_8px_16px_hsl(var(--primary)/0.15)]">
              <defs>
                <linearGradient id="geomGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="hsl(var(--cta))" stopOpacity="0.2" />
                </linearGradient>
                <linearGradient id="geomGrad2" x1="100%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="hsl(var(--cta))" stopOpacity="0.7" />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.3" />
                </linearGradient>
              </defs>
              <circle cx="100" cy="100" r="50" fill="url(#geomGrad1)" filter="blur(6px)" opacity="0.4" />
              <path d="M100 30 L155 62 L155 138 L100 170 L45 138 L45 62 Z" fill="url(#geomGrad2)" stroke="hsl(var(--primary) / 0.25)" strokeWidth="1.5" opacity="0.8" />
              <path d="M100 50 L135 70 L135 130 L100 150 L65 130 L65 70 Z" fill="hsl(var(--card) / 0.4)" stroke="hsl(var(--primary) / 0.4)" strokeWidth="1" />
              <circle cx="100" cy="100" r="10" fill="hsl(var(--cta))" className="animate-pulse" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold tracking-tight">Crea tu primer caso</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Un caso reúne los documentos, las carpetas conectadas y tu conversación con
            Mia. Tú decides si Mia te entrega un borrador para aprobar o te responde
            directo — y puedes cambiarlo cuando quieras.
          </p>
          <Button onClick={openModal} className="mt-6 gap-2 shadow-neu-raised hover:-translate-y-0.5 active:shadow-neu-sunken transition-all duration-200">
            <Plus className="h-4 w-4" />
            Nuevo caso
          </Button>
        </div>
      ) : (
        <ul className="space-y-3">
          {casos.map((c, i) => {
            const directo = c.kind === "proyecto";
            const KindIcon = directo ? MessageSquareText : FileCheck2;
            return (
              <li key={c.id} className="animate-slide-up" style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}>
                {/* Fila = enlace nativo "extendido" (el ::after cubre la tarjeta): conserva
                    teclado, foco y "abrir en pestaña nueva"; el botón de revisar es un
                    hermano real, sin anidar controles. */}
                <div className="group relative flex w-full items-center gap-4 rounded-xl bg-card/85 backdrop-blur-sm px-5 py-4 text-left shadow-neu-raised border border-border/10 transition-all duration-300 hover:-translate-y-1 hover:shadow-[var(--neu-raised),_0_12px_24px_-8px_hsl(var(--primary)/0.12)] dark:hover:shadow-[var(--neu-raised),_0_12px_24px_-8px_hsl(var(--primary)/0.25)]">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-secondary shadow-neu-sunken text-primary transition-transform duration-300 group-hover:scale-105">
                    <FolderOpen className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/casos/${c.id}`}
                        className="truncate rounded-sm font-medium after:absolute after:inset-0 after:rounded-xl after:content-['']"
                      >
                        {c.name}
                      </Link>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                          directo
                            ? "border-border bg-muted/60 text-muted-foreground"
                            : "border-primary/25 bg-primary/10 text-primary",
                        )}
                        title={KIND_HELP[directo ? "proyecto" : "asunto"]}
                      >
                        <KindIcon className="h-3 w-3" />
                        {KIND_LABEL[directo ? "proyecto" : "asunto"]}
                      </span>
                      {c.pending_review ? (
                        <Badge className="gap-1 border-transparent bg-cta/15 text-cta-strong hover:bg-cta/20">
                          <FileClock className="h-3 w-3" />
                          Borrador por revisar
                        </Badge>
                      ) : null}
                    </div>
                    {c.description ? (
                      <div className="mt-0.5 truncate text-sm text-muted-foreground">{c.description}</div>
                    ) : null}
                    {c.jurisdictions && c.jurisdictions.length > 0 ? (
                      <div className="mt-1 text-xs text-muted-foreground">
                        Contexto jurídico: {c.jurisdictions.map((code) => COUNTRY_NAME_BY_CODE[code] || "General").join(", ")}
                      </div>
                    ) : null}
                  </div>
                  {c.pending_review ? (
                    <Button
                      asChild
                      size="sm"
                      variant="cta"
                      className="relative z-10 shrink-0 gap-1.5"
                    >
                      <Link href={`/casos/${c.id}/revisar`}>
                        Revisar borrador
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  ) : null}
                  <div className="shrink-0 text-xs text-muted-foreground">{fmtDate(c.created_at)}</div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary" />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={showModal} onOpenChange={(o) => { if (!creating) { setShowModal(o); if (!o) setError(""); } }}>
        {/* max-h + scroll: el diálogo de creación es alto (modo + jurisdicciones) y el
            botón «Crear caso» debe seguir alcanzable en pantallas bajas. */}
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Nuevo caso</DialogTitle>
            <DialogDescription>
              Dale un nombre claro y elige cómo quieres que Mia te entregue su trabajo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="caso-name">Nombre</Label>
              <Input
                id="caso-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ej. Demanda de responsabilidad civil"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    create();
                  }
                }}
              />
            </div>

            <div className="space-y-2">
              <Label>¿Cómo te entrega Mia su trabajo aquí?</Label>
              <div role="radiogroup" aria-label="Modo de trabajo" className="space-y-2">
                {(["asunto", "proyecto"] as CaseKind[]).map((k) => {
                  const OptIcon = k === "asunto" ? FileCheck2 : MessageSquareText;
                  const activo = kind === k;
                  return (
                    <button
                      key={k}
                      type="button"
                      role="radio"
                      aria-checked={activo}
                      onClick={() => setKind(k)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-all duration-200",
                        activo
                          ? "border-primary/50 bg-primary/10 shadow-neu-sunken"
                          : "border-border bg-card shadow-neu-raised hover:-translate-y-0.5",
                      )}
                    >
                      <div
                        className={cn(
                          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                          activo ? "bg-primary text-primary-foreground" : "bg-secondary text-primary shadow-neu-sunken",
                        )}
                      >
                        <OptIcon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold">{KIND_LABEL[k]}</div>
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{KIND_HELP[k]}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground">
                Podrás cambiarlo después, dentro del caso.
              </p>
            </div>

            {organizationJurisdictions.length > 0 ? (
              <div className="space-y-2">
                <Label>Jurisdicción de este caso</Label>
                <p className="text-xs text-muted-foreground">
                  Si no eliges una, Mia usará todas las jurisdicciones de tu firma u organización.
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {organizationJurisdictions.map((code) => (
                    <label key={code} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={selectedJurisdictions.includes(code)}
                        onChange={(event) => setSelectedJurisdictions((current) =>
                          event.target.checked
                            ? [...current, code]
                            : current.filter((item) => item !== code),
                        )}
                      />
                      {COUNTRY_NAME_BY_CODE[code] || code}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="caso-desc">Descripción (opcional)</Label>
              <Textarea
                id="caso-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="h-20 resize-none"
                placeholder="Contexto breve del caso"
              />
            </div>
            {error ? (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowModal(false)} disabled={creating}>
              Cancelar
            </Button>
            <Button onClick={create} disabled={creating}>
              {creating ? "Creando…" : "Crear caso"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
