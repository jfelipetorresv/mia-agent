"use client";

// Mia · pestaña "Proyectos" (Bloque A · Ola A4). Lista + creación en dos pasos.
// ÚNICA diferencia real con un Asunto: en un Proyecto Mia responde directo y el
// abogado guarda lo que ella produce; en un Asunto todo termina en un borrador que
// el abogado aprueba. Todo lo demás es idéntico — conectar carpetas NO distingue a
// los dos: ambos usan el mismo FuentesPanel (ver app/asuntos/[id]/page.tsx). Los
// textos de esta pantalla no deben insinuar lo contrario.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, FolderKanban, ChevronRight } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import FuentesPanel from "../_components/FuentesPanel";

type Proyecto = {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
};

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

export default function ProyectosPage() {
  const router = useRouter();
  const [proyectos, setProyectos] = useState<Proyecto[]>([]);
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  // Paso 1: nombre + descripción → crea el proyecto de una vez. Paso 2: conectar
  // fuentes sobre el proyecto ya creado (FuentesPanel es autocontenido y guarda
  // cada fuente en el momento, no hace falta un segundo POST al salir).
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setProyectos(await apiGet<Proyecto[]>("/api/matters?kind=proyecto"));
    } catch {
      setProyectos([]);
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  function openModal() {
    setStep(1);
    setName("");
    setDescription("");
    setError("");
    setNewId(null);
    setShowModal(true);
  }

  async function crearProyecto() {
    if (creating) return;
    if (!name.trim()) {
      setError("Ponle un nombre al proyecto.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const m = await apiSend<{ id: string }>("POST", "/api/matters", {
        name: name.trim(),
        description: description.trim(),
        kind: "proyecto",
      });
      setNewId(m.id);
      setStep(2);
    } catch {
      setError("No se pudo crear el proyecto. Intenta de nuevo.");
    }
    setCreating(false);
  }

  function irAlProyecto() {
    const id = newId;
    setShowModal(false);
    if (id) router.push(`/proyectos/${id}`);
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:px-8">
      <div className="mb-8 flex items-end justify-between gap-4 animate-slide-up">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Proyectos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {/* La diferencia con un asunto vive aquí, en el subtítulo permanente, y no
                solo en el estado vacío: en un proyecto Mia responde directo, sin
                borrador que aprobar. */}
            {loading
              ? "Cargando tus proyectos…"
              : proyectos.length === 0
                ? "Aquí Mia te responde directo, sin borrador que aprobar."
                : `${proyectos.length} en curso · Mia responde directo, sin borrador que aprobar`}
          </p>
        </div>
        <Button onClick={openModal} className="gap-2">
          <Plus className="h-4 w-4" />
          Nuevo proyecto
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : proyectos.length === 0 ? (
        <div className="animate-slide-up rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <FolderKanban className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-medium">Crea tu primer proyecto</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Un proyecto se parece a un asunto en todo — conectas carpetas y conversas con Mia
            sobre tus documentos — salvo en una cosa: aquí Mia te responde directo y guardas
            lo que produce, sin borrador que aprobar. Cuando necesites ese borrador, abre un
            asunto.
          </p>
          <Button onClick={openModal} className="mt-6 gap-2">
            <Plus className="h-4 w-4" />
            Nuevo proyecto
          </Button>
        </div>
      ) : (
        <ul className="space-y-3">
          {proyectos.map((p, i) => (
            <li key={p.id} className="animate-slide-up" style={{ animationDelay: `${i * 45}ms`, animationFillMode: "backwards" }}>
              <button
                onClick={() => router.push(`/proyectos/${p.id}`)}
                className="group flex w-full items-center gap-4 rounded-xl border border-border bg-card px-5 py-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform duration-200 group-hover:scale-105">
                  <FolderKanban className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="truncate font-medium">{p.name}</span>
                  {p.description ? (
                    <div className="mt-0.5 truncate text-sm text-muted-foreground">{p.description}</div>
                  ) : null}
                </div>
                <div className="shrink-0 text-xs text-muted-foreground">{fmtDate(p.created_at)}</div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={showModal}
        onOpenChange={(o) => {
          if (o) {
            setShowModal(true);
            return;
          }
          // El proyecto del paso 2 ya quedó creado — cerrar el diálogo sin terminar
          // de conectar fuentes igual debe llevar al abogado a su espacio de trabajo.
          if (step === 2 && newId) {
            irAlProyecto();
          } else {
            setShowModal(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          {step === 1 ? (
            <>
              <DialogHeader>
                <DialogTitle>Nuevo proyecto</DialogTitle>
                <DialogDescription>
                  Dale un nombre claro; en el siguiente paso conectas las carpetas.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-1">
                <div className="space-y-1.5">
                  <Label htmlFor="proyecto-name">Nombre</Label>
                  <Input
                    id="proyecto-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Ej. Debida diligencia contrato XYZ"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        crearProyecto();
                      }
                    }}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="proyecto-desc">Descripción (opcional)</Label>
                  <Textarea
                    id="proyecto-desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="h-20 resize-none"
                    placeholder="Contexto breve del proyecto"
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
                <Button onClick={crearProyecto} disabled={creating}>
                  {creating ? "Creando…" : "Continuar"}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Conecta las carpetas del proyecto</DialogTitle>
                <DialogDescription>
                  Mia trabajará sobre los documentos de las fuentes que conectes. Puedes agregar
                  o quitar fuentes cuando quieras, también después.
                </DialogDescription>
              </DialogHeader>
              {newId ? <FuentesPanel matterId={newId} kind="proyecto" /> : null}
              <DialogFooter>
                <Button variant="ghost" onClick={irAlProyecto}>
                  Omitir por ahora
                </Button>
                <Button onClick={irAlProyecto}>Ir al proyecto</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
