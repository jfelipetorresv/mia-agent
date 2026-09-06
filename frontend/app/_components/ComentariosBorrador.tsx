"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquarePlus, Trash2, Send, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

// Comentarios sobre el borrador, al estilo de los comentarios de un documento
// compartido: el abogado marca el pasaje que no le gusta y escribe qué debe cambiar
// AHÍ. Mia corrige ese punto y deja el resto del escrito igual — no lo rehace.
//
// El ancla es el TEXTO, nunca una posición: el documento se reescribe y las posiciones
// mienten. Se guarda el pasaje exacto, el número de párrafo (como pista) y un poco de
// texto antes y después, que es lo que permite volver a encontrarlo aunque el párrafo
// se haya movido o cambiado un poco.

export type ComentarioBorrador = {
  id: string;
  texto_citado: string;
  parrafo_indice: number;
  contexto_antes: string;
  contexto_despues: string;
  instruccion: string;
};

export type ComentarioResuelto = {
  id?: string;
  instruccion?: string;
  texto_citado?: string;
  ubicado?: boolean;
  pasaje_antes?: string;
  pasaje_despues?: string;
  atendido?: boolean;
  cambio?: string;
};

export type AvisoDeCambio = { tipo?: string; antes?: string; despues?: string };

export type InformeComentarios = {
  comentarios?: ComentarioResuelto[];
  avisos?: AvisoDeCambio[];
  resumen?: string;
};

const CONTEXTO_CHARS = 80;

function parrafosDe(texto: string): string[] {
  return texto
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/** Dónde cae el pasaje seleccionado dentro del borrador: párrafo y texto vecino. */
export function anclaDe(draft: string, seleccion: string) {
  const limpio = seleccion.replace(/\s+/g, " ").trim();
  const pos = draft.replace(/\s+/g, " ").indexOf(limpio);
  const plano = draft.replace(/\s+/g, " ");
  const contexto_antes = pos > 0 ? plano.slice(Math.max(0, pos - CONTEXTO_CHARS), pos).trim() : "";
  const contexto_despues =
    pos >= 0 ? plano.slice(pos + limpio.length, pos + limpio.length + CONTEXTO_CHARS).trim() : "";
  const parrafos = parrafosDe(draft);
  const parrafo_indice = parrafos.findIndex((p) => p.replace(/\s+/g, " ").includes(limpio));
  return { texto_citado: limpio, parrafo_indice, contexto_antes, contexto_despues };
}

function nuevoId() {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function Recorte({ texto, className }: { texto: string; className?: string }) {
  return (
    <p className={cn("font-serif text-meta italic text-muted-foreground", className)}>
      «{texto.length > 220 ? `${texto.slice(0, 220)}…` : texto}»
    </p>
  );
}

/**
 * Carril lateral de comentarios + botón flotante «Comentar» sobre la selección.
 *
 * `children` es la superficie de lectura del borrador: el componente escucha las
 * selecciones que ocurren dentro de ella.
 */
export default function ComentariosBorrador({
  draft,
  comentarios,
  onChange,
  onEnviar,
  enviando,
  error,
  informe,
  children,
}: {
  draft: string;
  comentarios: ComentarioBorrador[];
  onChange: (siguientes: ComentarioBorrador[]) => void;
  onEnviar: () => void;
  enviando: boolean;
  error?: string;
  informe?: InformeComentarios | null;
  children: React.ReactNode;
}) {
  const zonaRef = useRef<HTMLDivElement | null>(null);
  const contenedorRef = useRef<HTMLDivElement | null>(null);
  const [burbuja, setBurbuja] = useState<{ top: number; left: number; seleccion: string } | null>(
    null,
  );
  const [borrandoTexto, setBorrandoTexto] = useState("");
  const [activo, setActivo] = useState<string | null>(null);

  const capturarSeleccion = useCallback(() => {
    const sel = typeof window !== "undefined" ? window.getSelection() : null;
    const texto = sel?.toString() ?? "";
    if (!sel || sel.isCollapsed || texto.trim().length < 3) {
      setBurbuja(null);
      return;
    }
    const zona = zonaRef.current;
    const caja = contenedorRef.current;
    if (!zona || !caja || !zona.contains(sel.anchorNode)) {
      setBurbuja(null);
      return;
    }
    const rango = sel.getRangeAt(0).getBoundingClientRect();
    const base = caja.getBoundingClientRect();
    setBurbuja({
      top: rango.bottom - base.top + 8,
      left: Math.max(0, rango.left - base.left),
      seleccion: texto,
    });
  }, []);

  useEffect(() => {
    // `mouseup` cubre el ratón; `keyup` cubre seleccionar con Shift + flechas.
    document.addEventListener("mouseup", capturarSeleccion);
    document.addEventListener("keyup", capturarSeleccion);
    return () => {
      document.removeEventListener("mouseup", capturarSeleccion);
      document.removeEventListener("keyup", capturarSeleccion);
    };
  }, [capturarSeleccion]);

  function comentarSeleccion() {
    if (enviando || !burbuja) return;
    const ancla = anclaDe(draft, burbuja.seleccion);
    const id = nuevoId();
    onChange([...comentarios, { id, instruccion: "", ...ancla }]);
    setActivo(id);
    setBurbuja(null);
    window.getSelection()?.removeAllRanges();
    // El foco viaja al comentario recién creado: comentar con teclado no debe
    // obligar a buscar el cuadro de texto con el ratón.
    setTimeout(() => {
      document.getElementById(`comentario-${id}`)?.focus();
    }, 30);
  }

  function editar(id: string, instruccion: string) {
    if (enviando) return;
    onChange(comentarios.map((c) => (c.id === id ? { ...c, instruccion } : c)));
  }

  function eliminar(id: string) {
    if (enviando) return;
    const fuera = comentarios.find((c) => c.id === id);
    onChange(comentarios.filter((c) => c.id !== id));
    setBorrandoTexto(fuera ? "Comentario eliminado." : "");
  }

  const listos = comentarios.filter((c) => c.instruccion.trim().length > 0);

  return (
    <div ref={contenedorRef} className="relative grid gap-block lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div ref={zonaRef}>{children}</div>

      {burbuja ? (
        <div
          className="absolute z-30 animate-fade-in"
          style={{ top: burbuja.top, left: burbuja.left }}
        >
          <Button size="sm" variant="outline" className="gap-2 shadow-lg" onClick={comentarSeleccion} disabled={enviando}>
            <MessageSquarePlus className="h-4 w-4" />
            Comentar
          </Button>
        </div>
      ) : null}

      <aside aria-label="Tus comentarios sobre el borrador" className="space-y-3">
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised/60 px-4 py-3">
          <p className="text-section">Tus comentarios</p>
          <p className="mt-1 text-meta text-muted-foreground">
            Marca un pasaje del borrador y pulsa «Comentar». Mia corrige solo esos puntos y
            conserva el resto del escrito.
          </p>
        </div>

        <p aria-live="polite" className="sr-only">
          {borrandoTexto}
        </p>

        {comentarios.length === 0 ? (
          <p className="px-1 text-meta text-muted-foreground">
            Todavía no has comentado nada.
          </p>
        ) : null}

        {comentarios.map((c, i) => (
          <div
            key={c.id}
            className={cn(
              "rounded-lg shadow-neu-raised border border-border/10 bg-card/60 px-4 py-3 transition-colors",
              activo === c.id ? "border-primary/50" : "border-border",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-label text-muted-foreground">Comentario {i + 1}</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-meta text-muted-foreground hover:text-destructive"
                onClick={() => eliminar(c.id)}
                disabled={enviando}
                aria-label={`Eliminar el comentario ${i + 1}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Recorte texto={c.texto_citado} className="mt-1" />
            <Label htmlFor={`comentario-${c.id}`} className="sr-only">
              Qué debe cambiar en este pasaje
            </Label>
            <Textarea
              id={`comentario-${c.id}`}
              value={c.instruccion}
              disabled={enviando}
              onChange={(e) => editar(c.id, e.target.value)}
              onFocus={() => setActivo(c.id)}
              placeholder="Por ejemplo: aquí suaviza el tono, cita la cláusula quinta, este monto está mal…"
              className="mt-2 min-h-[80px] text-body"
            />
          </div>
        ))}

        {comentarios.length > 0 ? (
          <div className="space-y-2">
            <Button
              variant="cta"
              className="w-full gap-2"
              onClick={onEnviar}
              disabled={enviando || listos.length === 0}
            >
              <Send className="h-4 w-4" />
              {enviando ? "Mia está corrigiendo…" : "Pedir estos cambios"}
            </Button>
            {listos.length === 0 ? (
              <p className="text-meta text-muted-foreground">
                Escribe qué debe cambiar en cada pasaje antes de enviarlos.
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="text-body text-warning">
                {error}
              </p>
            ) : null}
          </div>
        ) : null}

        {informe ? <ResolucionDeComentarios informe={informe} /> : null}
      </aside>
    </div>
  );
}

/** Cómo quedó cada comentario tras la corrección, y qué más se movió. */
export function ResolucionDeComentarios({ informe }: { informe: InformeComentarios }) {
  const comentarios = informe.comentarios || [];
  const avisos = informe.avisos || [];
  if (comentarios.length === 0 && avisos.length === 0) return null;
  return (
    <section
      aria-label="Cómo quedaron tus comentarios"
      className="rounded-lg border border-border/10 bg-card shadow-neu-raised/60 px-4 py-3"
    >
      <p className="text-section">Cómo quedaron tus comentarios</p>
      {informe.resumen ? (
        <p className="mt-1 text-meta text-muted-foreground">{informe.resumen}</p>
      ) : null}
      <ul className="mt-3 space-y-3">
        {comentarios.map((c, i) => (
          <li key={c.id || i} className="border-t border-border pt-3 first:border-0 first:pt-0">
            <div className="flex items-start gap-2">
              {c.atendido ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              )}
              <div className="min-w-0">
                <p className="text-body">{c.instruccion}</p>
                <p className="mt-1 text-meta text-muted-foreground">{c.cambio}</p>
                {c.pasaje_despues ? (
                  <Recorte texto={c.pasaje_despues} className="mt-1 not-italic text-foreground/80" />
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {avisos.length > 0 ? (
        <div className="mt-3 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2">
          <p className="text-label text-warning">También cambié esto, que no me pediste</p>
          <ul className="mt-2 space-y-2">
            {avisos.map((a, i) => (
              <li key={i}>
                <Recorte texto={a.despues || a.antes || ""} />
                <p className="text-meta text-muted-foreground">
                  {a.tipo === "agregado"
                    ? "Este pasaje es nuevo."
                    : a.tipo === "eliminado"
                      ? "Este pasaje ya no está."
                      : "Este pasaje quedó redactado de otra manera."}{" "}
                  Revísalo antes de aprobar.
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
