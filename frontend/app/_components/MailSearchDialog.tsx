"use client";

// Mia · "Traer correos del caso" en la pantalla del asunto (Fase 4 · Fase 2 backend).
// Busca en el correo conectado del abogado y deja elegir cuáles vincular al expediente
// (cuerpo + adjuntos legibles entran como documentos del caso).

import { useState } from "react";
import { Paperclip, Search } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type MailResult = {
  id: string;
  subject: string;
  sender: string;
  sender_name?: string;
  date: string;
  snippet: string;
  has_attachments: boolean;
  provider: string;
};

type LinkResponse = { added: string[]; skipped: { name: string; reason: string }[]; already: string[] };

const MAX_ITEMS = 20;

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

function fmtDate(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

function keyOf(r: MailResult): string {
  return `${r.provider}:${r.id}`;
}

type Props = {
  matterId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Se llama tras añadir correos, para que el asunto refresque su lista de documentos. */
  onLinked: () => void;
};

export default function MailSearchDialog({ matterId, open, onOpenChange, onLinked }: Props) {
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [results, setResults] = useState<MailResult[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [linking, setLinking] = useState(false);
  const [summary, setSummary] = useState("");

  function reset() {
    setQ("");
    setResults([]);
    setSearched(false);
    setSelected(new Set());
    setError("");
    setSummary("");
  }

  async function search() {
    const text = q.trim();
    if (!text || searching) return;
    setSearching(true);
    setSearched(false);
    setError("");
    setSummary("");
    setSelected(new Set());
    try {
      const res = await apiGet<{ resultados: MailResult[] }>(
        `/api/matters/${matterId}/mail/search?q=${encodeURIComponent(text)}`,
      );
      setResults(res.resultados || []);
    } catch (err) {
      setResults([]);
      setError(apiMessage(err, "No se pudo buscar en tu correo. Intenta de nuevo."));
    } finally {
      setSearching(false);
      setSearched(true);
    }
  }

  function toggle(r: MailResult) {
    const key = keyOf(r);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else if (next.size < MAX_ITEMS) next.add(key);
      return next;
    });
  }

  async function linkSelected() {
    if (selected.size === 0 || linking) return;
    setLinking(true);
    setError("");
    setSummary("");
    try {
      const items = results.filter((r) => selected.has(keyOf(r))).map((r) => ({ provider: r.provider, message_id: r.id }));
      const res = await apiSend<LinkResponse>("POST", `/api/matters/${matterId}/mail/link`, { items });
      const parts: string[] = [];
      if (res.added.length) {
        parts.push(`${res.added.length} ${res.added.length === 1 ? "correo agregado" : "correos agregados"} al expediente`);
      }
      if (res.already.length) {
        parts.push(`${res.already.length} ya ${res.already.length === 1 ? "estaba" : "estaban"} en el expediente`);
      }
      if (res.skipped.length) {
        parts.push(`${res.skipped.length} no se ${res.skipped.length === 1 ? "pudo" : "pudieron"} agregar`);
      }
      setSummary(parts.join(" · ") || "Listo.");
      setSelected(new Set());
      onLinked();
    } catch (err) {
      setError(apiMessage(err, "No se pudieron vincular los correos. Intenta de nuevo."));
    } finally {
      setLinking(false);
    }
  }

  // Única puerta de cierre: no cierra mientras vincula y SIEMPRE resetea al cerrar (así el
  // botón "Cerrar" y la X/overlay comparten el mismo camino — antes "Cerrar" saltaba el reset).
  function handleOpenChange(o: boolean) {
    if (linking) return;
    onOpenChange(o);
    if (!o) reset();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent aria-label="Traer correos del caso" className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Traer correos del caso</DialogTitle>
          <DialogDescription>
            Busca en tu correo conectado y elige los que quieres agregar al expediente. El cuerpo y los adjuntos que
            Mia pueda leer entran como documentos del caso.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                search();
              }
            }}
            placeholder="Ej.: contrato, nombre de la contraparte, número del caso…"
            aria-label="Buscar en tu correo"
          />
          <Button onClick={search} disabled={searching || !q.trim()} className="shrink-0 gap-1.5">
            <Search className="h-3.5 w-3.5" />
            {searching ? "Buscando…" : "Buscar"}
          </Button>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-warning">
            {error}
          </p>
        ) : null}

        <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
          {searching ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">Buscando…</p>
          ) : searched && results.length === 0 && !error ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">No encontré correos con esa búsqueda.</p>
          ) : results.length > 0 ? (
            <ul className="divide-y divide-border">
              {results.map((r) => {
                const key = keyOf(r);
                const checked = selected.has(key);
                return (
                  <li key={key}>
                    <label className="flex cursor-pointer items-start gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-accent/60">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(r)}
                        disabled={!checked && selected.size >= MAX_ITEMS}
                        className="mt-1 h-4 w-4 shrink-0 rounded border-input accent-[hsl(var(--primary))]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate font-medium">{r.sender_name || r.sender}</span>
                          {r.has_attachments ? <Paperclip className="h-3 w-3 shrink-0 text-muted-foreground" /> : null}
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">{fmtDate(r.date)}</span>
                        </div>
                        <div className="truncate text-sm">{r.subject || "(sin asunto)"}</div>
                        {r.snippet ? <div className="truncate text-xs text-muted-foreground">{r.snippet}</div> : null}
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">Escribe qué buscar y presiona «Buscar».</p>
          )}
        </div>

        {summary ? (
          <p role="status" className="text-sm text-success">
            {summary}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={linking}>
            Cerrar
          </Button>
          <Button onClick={linkSelected} disabled={selected.size === 0 || linking}>
            {linking ? "Agregando…" : `Añadir al expediente (${selected.size})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
