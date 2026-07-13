"use client";

// Sala de estrategia · bloque de resultado (vive en el flujo de la conversación
// del asunto). Arriba las CONCLUSIONES (dictamen); abajo el debate completo,
// colapsado, con las intervenciones de cada counsel resaltando [VERIFICAR]
// igual que el borrador (revisar/page.tsx). §G: cero jerga técnica visible.

import { useEffect, useRef, useState } from "react";
import { ChevronRight, Download, FileEdit, Swords } from "lucide-react";
import { apiDownload } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { DebateTurn, TesisViable, WarRoomResult } from "./warroom-types";

// Mismo resaltado que revisar/page.tsx (renderDraft): [VERIFICAR…] es la señal
// de "esto lo confirmas tú" en cualquier texto que Mia redacte.
function renderMarked(text: string) {
  const parts = text.split(/(\[VERIFICAR[^\]]*\])/g);
  return parts.map((p, i) =>
    p.startsWith("[VERIFICAR") ? (
      <mark key={i} title="Verificar antes de presentar" className="rounded bg-warning/20 px-1 font-sans text-sm font-medium text-warning">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

const TESIS_BADGE: Record<TesisViable, { variant: "success" | "warning" | "destructive"; label: string }> = {
  Sí: { variant: "success", label: "Tesis viable" },
  "Con reservas": { variant: "warning", label: "Viable con reservas" },
  Riesgosa: { variant: "destructive", label: "Tesis riesgosa" },
};

function roundLabel(round: number): string {
  if (round === 1) return "Primera ronda · posturas iniciales";
  if (round === 2) return "Segunda ronda · réplicas";
  return `Ronda ${round}`;
}

function groupByRound(debate: DebateTurn[]): { round: number; turns: DebateTurn[] }[] {
  const map = new Map<number, DebateTurn[]>();
  for (const t of debate) {
    const list = map.get(t.round) || [];
    list.push(t);
    map.set(t.round, list);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([round, turns]) => ({ round, turns }));
}

type Props = {
  matterId: string;
  streaming: boolean;
  statusMessage: string;
  // Mensaje de error EN LLANO del backend (evento `error`, p. ej. asunto sin expediente).
  // Se muestra aunque no haya debate ni dictamen — antes el bloque se desmontaba y el error
  // quedaba invisible (MAYOR 2).
  error: string;
  debate: DebateTurn[];
  result: WarRoomResult | null;
  convertingToDraft: boolean;
  onConvertToDraft: () => void;
};

export default function SalaEstrategiaResult({
  matterId,
  streaming,
  statusMessage,
  error,
  debate,
  result,
  convertingToDraft,
  onConvertToDraft,
}: Props) {
  const [debateOpen, setDebateOpen] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState("");
  const hadResult = useRef(false);

  // En cuanto el dictamen queda listo, el debate se colapsa una sola vez —
  // el abogado ya tiene lo que necesita arriba; el debate sigue disponible
  // si quiere revisar el detalle.
  useEffect(() => {
    if (result && !hadResult.current) {
      hadResult.current = true;
      setDebateOpen(false);
    }
  }, [result]);

  async function downloadWord() {
    setDownloadMsg("");
    setDownloading(true);
    try {
      await apiDownload(`/api/matters/${matterId}/warroom.docx`, "sala-de-estrategia.docx");
    } catch {
      setDownloadMsg("No se pudo descargar el documento. Intenta de nuevo.");
    } finally {
      setDownloading(false);
    }
  }

  // Se sigue mostrando el bloque cuando hay un error (aunque no haya llegado ni una sola
  // intervención ni dictamen): así un fallo antes del primer turno —p. ej. asunto sin
  // expediente— es visible para el abogado en llano (MAYOR 2).
  const showError = Boolean(error) && !result;
  if (!streaming && debate.length === 0 && !result && !error) return null;

  const grouped = groupByRound(debate);
  const counselCount = new Set(debate.map((t) => t.persona_id ?? t.name)).size;
  const tesis = result ? TESIS_BADGE[result.conclusions.tesis_viable] : null;

  return (
    <div className="mx-auto w-full max-w-3xl animate-slide-up">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Swords className="h-3.5 w-3.5 text-primary" />
        Sala de estrategia
      </div>

      {showError ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-5">
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          </CardContent>
        </Card>
      ) : !result ? (
        <Card className="border-border bg-card/60">
          <CardContent className="flex items-center gap-3 py-5">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/50" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
            </span>
            <p className="text-sm text-muted-foreground">
              {statusMessage || "Mia está reuniendo la sala de estrategia…"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border">
          <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
            <CardTitle className="text-base">Conclusiones</CardTitle>
            {tesis ? <Badge variant={tesis.variant}>{tesis.label}</Badge> : null}
          </CardHeader>
          <CardContent className="space-y-4 font-serif text-[15px] leading-relaxed">
            {result.conclusions.fortalezas.length > 0 ? (
              <ConclusionList title="Fortalezas" items={result.conclusions.fortalezas} />
            ) : null}
            {result.conclusions.riesgos.length > 0 ? (
              <ConclusionList title="Riesgos" items={result.conclusions.riesgos} />
            ) : null}
            {result.conclusions.puntos_ciegos.length > 0 ? (
              <ConclusionList title="Puntos ciegos" items={result.conclusions.puntos_ciegos} />
            ) : null}
            {result.conclusions.estrategia ? (
              <div>
                <p className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Estrategia
                </p>
                <p className="whitespace-pre-wrap">{renderMarked(result.conclusions.estrategia)}</p>
              </div>
            ) : null}
            {result.conclusions.proximo_paso ? (
              <div>
                <p className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Próximo paso
                </p>
                <p className="whitespace-pre-wrap">{renderMarked(result.conclusions.proximo_paso)}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {debate.length > 0 ? (
        <details
          open={debateOpen}
          onToggle={(e) => setDebateOpen((e.target as HTMLDetailsElement).open)}
          className="group mt-3 rounded-xl border border-border bg-card shadow-sm"
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
            <span className="flex-1">
              Ver el debate completo ({counselCount} {counselCount === 1 ? "counsel" : "counsel"})
            </span>
          </summary>
          <div className="space-y-5 border-t border-border px-4 py-4">
            {grouped.map(({ round, turns }) => (
              <div key={round}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-primary/80">
                  {roundLabel(round)}
                </p>
                <div className="space-y-3">
                  {turns.map((t, i) => (
                    <div key={`${t.persona_id ?? t.name}-${round}-${i}`} className="rounded-lg border border-border/70 px-3 py-2.5">
                      <div className="mb-1 flex flex-wrap items-baseline gap-2">
                        <span className="text-sm font-semibold">{t.name}</span>
                        <span className="text-xs text-muted-foreground">{t.stance_label}</span>
                      </div>
                      <p className="whitespace-pre-wrap font-serif text-sm leading-relaxed">{renderMarked(t.text)}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {result ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={downloadWord} disabled={downloading} className="gap-2">
            <Download className="h-3.5 w-3.5" />
            {downloading ? "Preparando…" : "Descargar en Word"}
          </Button>
          <Button
            variant="cta"
            size="sm"
            onClick={onConvertToDraft}
            disabled={convertingToDraft}
            className="gap-2"
          >
            <FileEdit className="h-3.5 w-3.5" />
            {convertingToDraft ? "Preparando el borrador…" : "Convertir en borrador"}
          </Button>
          {downloadMsg ? <p role="alert" className={cn("w-full text-xs text-warning")}>{downloadMsg}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function ConclusionList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((it, i) => (
          <li key={i}>{renderMarked(it)}</li>
        ))}
      </ul>
    </div>
  );
}
