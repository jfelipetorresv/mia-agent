"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Plus, FolderOpen, ChevronRight, FileClock, ArrowRight } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Matter = {
  id: string;
  name: string;
  description?: string;
  status?: string;
  created_at?: string;
  pending_review?: boolean;
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
// prerender). El contenido real vive en AsuntosPageContent; este export solo
// monta el límite. Mismo patrón que app/asuntos/[id]/page.tsx.
export default function AsuntosPage() {
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
      <AsuntosPageContent />
    </Suspense>
  );
}

function AsuntosPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [matters, setMatters] = useState<Matter[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      setMatters(await apiGet<Matter[]>("/api/matters"));
    } catch {
      setMatters([]);
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  // El buscador de comandos (Ctrl+K → "Nuevo asunto") llega aquí como "/?nuevo=1".
  // Abrimos el diálogo de una vez y borramos la señal de la URL: así un refresco
  // de la página no vuelve a abrirlo solo.
  useEffect(() => {
    if (searchParams.get("nuevo") === "1") {
      setShowModal(true);
      router.replace("/", { scroll: false });
    }
  }, [searchParams, router]);

  async function create() {
    if (!name.trim()) {
      setError("Ponle un nombre al asunto.");
      return;
    }
    try {
      const m = await apiSend<Matter>("POST", "/api/matters", {
        name: name.trim(),
        description: description.trim(),
      });
      setShowModal(false);
      setName("");
      setDescription("");
      setError("");
      router.push(`/asuntos/${m.id}`);
    } catch {
      setError("No se pudo crear el asunto.");
    }
  }

  const pendientes = matters.filter((m) => m.pending_review).length;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <div className="mb-8 flex items-end justify-between gap-4 animate-slide-up">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Asuntos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {/* La diferencia con un proyecto vive aquí, en el subtítulo permanente, y
                no solo en el estado vacío: en un asunto Mia siempre termina en un
                borrador que el abogado aprueba. */}
            {loading
              ? "Cargando tu despacho…"
              : matters.length === 0
                ? "Aquí Mia siempre termina en un borrador que tú apruebas."
                : pendientes > 0
                  ? `${matters.length} en curso · ${pendientes} con borrador esperando tu revisión`
                  : `${matters.length} en curso · Mia siempre termina en un borrador que tú apruebas`}
          </p>
        </div>
        <Button onClick={() => setShowModal(true)} className="gap-2">
          <Plus className="h-4 w-4" />
          Nuevo asunto
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : matters.length === 0 ? (
        <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <FolderOpen className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-medium">Crea tu primer asunto</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Un asunto es un caso de tu despacho: conectas carpetas, subes el expediente y
            conversas con Mia — y todo termina en un borrador que tú apruebas antes de que
            salga. Si prefieres que te responda directo, sin ese paso, usa un proyecto.
          </p>
          <Button onClick={() => setShowModal(true)} className="mt-6 gap-2">
            <Plus className="h-4 w-4" />
            Nuevo asunto
          </Button>
        </div>
      ) : (
        <ul className="space-y-3">
          {matters.map((m, i) => (
            <li key={m.id} className="animate-slide-up" style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}>
              {/* La fila es un enlace nativo "extendido" (el ::after cubre la tarjeta):
                  así el abogado conserva teclado, foco y "abrir en pestaña nueva", y
                  el botón de revisar puede ser un hermano real —sin anidar controles—
                  aunque visualmente viva dentro de la tarjeta. */}
              <div className="group relative flex w-full items-center gap-4 rounded-xl border border-border bg-card px-5 py-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform duration-200 group-hover:scale-105">
                  <FolderOpen className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/asuntos/${m.id}`}
                      className="truncate rounded-sm font-medium after:absolute after:inset-0 after:rounded-xl after:content-['']"
                    >
                      {m.name}
                    </Link>
                    {m.pending_review ? (
                      <Badge className="gap-1 border-transparent bg-cta/15 text-cta-strong hover:bg-cta/20">
                        <FileClock className="h-3 w-3" />
                        Borrador por revisar
                      </Badge>
                    ) : null}
                  </div>
                  {m.description ? (
                    <div className="mt-0.5 truncate text-sm text-muted-foreground">{m.description}</div>
                  ) : null}
                </div>
                {m.pending_review ? (
                  <Button
                    asChild
                    size="sm"
                    variant="cta"
                    className="relative z-10 shrink-0 gap-1.5"
                  >
                    <Link href={`/asuntos/${m.id}/revisar`}>
                      Revisar borrador
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </Button>
                ) : null}
                <div className="shrink-0 text-xs text-muted-foreground">{fmtDate(m.created_at)}</div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary" />
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={showModal} onOpenChange={(o) => { setShowModal(o); if (!o) setError(""); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Nuevo asunto</DialogTitle>
            <DialogDescription>
              Dale un nombre claro; podrás subir el expediente en el siguiente paso.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="matter-name">Nombre</Label>
              <Input
                id="matter-name"
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
            <div className="space-y-1.5">
              <Label htmlFor="matter-desc">Descripción (opcional)</Label>
              <Textarea
                id="matter-desc"
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
            <Button variant="ghost" onClick={() => setShowModal(false)}>
              Cancelar
            </Button>
            <Button onClick={create}>Crear asunto</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
