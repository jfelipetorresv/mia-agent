"use client";

// "Documentos por confirmar" · la DUDA del clasificador de ingesta (Fase 1).
// Cuando Mia ingiere un documento INFIERE su ficha (tipo, parte, folio/radicado,
// fecha). Lo que tiene claro lo da por bueno; lo que DUDA lo deja aquí para que el
// abogado lo confirme CAMPO POR CAMPO. Esta es su lista propia — NO se reutiliza la
// pantalla de sugerencias del borrador (decisión de diseño).
//
// §G: lenguaje llano, sin jerga. El abogado ve "el dato que Mia no tiene claro",
// su sugerencia, y decide: "Es correcto" (acepta) o "Corregir" (escribe el bueno).
// Al confirmar, se guarda el dato y el campo desaparece de la duda; cuando el
// documento se queda sin dudas, sale de la lista.
//
// Contrato del backend (documents_review.py):
//   GET  /api/matters/{id}/documents/pending  → { documentos: [...] }
//   POST /api/matters/{id}/documents/confirm    { document_id, campo, valor }
//                                              → { pendientes, restantes, completado, ... }
// Componente autocontenido: carga su propia lista al abrirse. NO inventa campos
// fuera del contrato.

import { useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, Loader2, Pencil } from "lucide-react";
import { apiGet, apiSend, plainMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Pendiente = { campo: string; valor: string; confianza: number | null };
type Confirmado = { campo: string; valor: string };
type Documento = {
  id: string;
  nombre: string;
  origin?: string | null;
  created_at?: string | null;
  pendientes: Pendiente[];
  confirmados: Confirmado[];
};
type PendingResponse = { documentos: Documento[] };
type ConfirmResponse = {
  document_id: string;
  campo: string;
  valor: string;
  pendientes: Pendiente[];
  restantes: number;
  completado: boolean;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  matterId: string;
  // Avisa a la pantalla del asunto que la lista cambió (para refrescar su contador).
  onChanged?: () => void;
};

// Nombre en llano de cada campo de la ficha (§G). Esto solo NOMBRA el campo para el
// abogado: NO acota su contenido — 'tipo' y 'parte' son texto libre (Mia es agnóstica
// de jurisdicción, jamás un vocabulario cerrado de un país).
const CAMPO_LABEL: Record<string, string> = {
  tipo: "Tipo de documento",
  parte: "Parte",
  folio_radicado: "Folio o radicado",
  fecha_documento: "Fecha del documento",
};

// Pista de escritura al corregir (solo orienta; el backend acepta el texto libre).
const CAMPO_PLACEHOLDER: Record<string, string> = {
  tipo: "Escribe el tipo de documento",
  parte: "Nombre de la parte",
  folio_radicado: "Folio o número de radicado",
  fecha_documento: "Año-mes-día (por ejemplo 2026-07-19)",
};

// De dónde llegó el documento, en llano (contexto discreto, no una acción).
const ORIGEN_LABEL: Record<string, string> = {
  upload: "Subido por ti",
  folder: "De una carpeta del equipo",
  drive: "De OneDrive",
  mail: "De un correo",
};

function campoLabel(campo: string): string {
  return CAMPO_LABEL[campo] || campo;
}

function confianzaText(c: number | null | undefined): string {
  if (c === null || c === undefined || Number.isNaN(c)) return "";
  return `Mia lo cree con ${Math.round(c * 100)}% de seguridad`;
}

export default function DocumentosPorConfirmarDialog({ open, onOpenChange, matterId, onChanged }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [docs, setDocs] = useState<Documento[]>([]);
  // Valor en edición por campo: clave `${docId}:${campo}`. Si la clave existe, ese
  // campo está en modo "Corregir" (input abierto).
  const [editing, setEditing] = useState<Record<string, string>>({});
  // Solo una confirmación en vuelo a la vez; se marca la fila ocupada para deshabilitarla.
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setActionError("");
    setDocs([]);
    setEditing({});
    apiGet<PendingResponse>(`/api/matters/${matterId}/documents/pending`)
      .then((res) => {
        if (cancelled) return;
        setDocs(res.documentos || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(plainMessage(err, "No pude cargar los documentos por confirmar. Intenta de nuevo."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, matterId]);

  function startEdit(key: string, valor: string) {
    setActionError("");
    setEditing((e) => ({ ...e, [key]: valor }));
  }

  function cancelEdit(key: string) {
    setEditing((e) => {
      const copy = { ...e };
      delete copy[key];
      return copy;
    });
  }

  async function confirmar(docId: string, campo: string, valor: string) {
    const v = valor.trim();
    const key = `${docId}:${campo}`;
    if (!v || busyKey) return;
    setBusyKey(key);
    setActionError("");
    try {
      const res = await apiSend<ConfirmResponse>("POST", `/api/matters/${matterId}/documents/confirm`, {
        document_id: docId,
        campo,
        valor: v,
      });
      setDocs((prev) => {
        const next: Documento[] = [];
        for (const d of prev) {
          if (d.id !== docId) {
            next.push(d);
            continue;
          }
          // Ya no quedan dudas en el documento: sale de la lista.
          if (res.completado) continue;
          // Mueve el campo confirmado al contexto y deja solo las dudas restantes.
          const confirmados = [
            ...d.confirmados.filter((c) => c.campo !== campo),
            { campo, valor: res.valor },
          ];
          next.push({ ...d, pendientes: res.pendientes, confirmados });
        }
        return next;
      });
      cancelEdit(key);
      onChanged?.();
    } catch (err) {
      setActionError(plainMessage(err, "No pude confirmar ese dato. Intenta de nuevo."));
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-primary" />
            Documentos por confirmar
          </DialogTitle>
          <DialogDescription>
            Mia leyó estos documentos y anotó su ficha. Hay un dato que no tiene del todo claro —
            confírmalo o corrígelo para dejarlo bien guardado.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Cargando…
          </div>
        ) : error ? (
          <div className="py-4 text-sm text-warning" role="alert">
            {error}
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <CheckCircle2 className="h-6 w-6 text-success" />
            <p className="text-sm text-muted-foreground">
              Nada por confirmar: Mia tiene clara la ficha de todos los documentos del expediente.
            </p>
          </div>
        ) : (
          <div className="max-h-[62vh] space-y-4 overflow-y-auto pr-1">
            {actionError ? (
              <p role="alert" className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-warning">
                {actionError}
              </p>
            ) : null}
            {docs.map((doc) => {
              const origen = doc.origin ? ORIGEN_LABEL[doc.origin] || "" : "";
              return (
                <div key={doc.id} className="rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                  <div className="mb-2">
                    <div className="truncate text-sm font-semibold text-card-foreground">{doc.nombre}</div>
                    {origen ? <div className="mt-0.5 text-xs text-muted-foreground">{origen}</div> : null}
                  </div>

                  {/* Lo que Mia ya dio por bueno — contexto, no editable aquí. */}
                  {doc.confirmados.length > 0 ? (
                    <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1">
                      {doc.confirmados.map((c) => (
                        <span key={c.campo} className="text-xs text-muted-foreground">
                          <span className="font-medium">{campoLabel(c.campo)}:</span> {c.valor}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {/* Las dudas: un bloque por campo, con "Es correcto" / "Corregir". */}
                  <div className="space-y-2.5">
                    {doc.pendientes.map((p) => {
                      const key = `${doc.id}:${p.campo}`;
                      const isEditing = key in editing;
                      const isBusy = busyKey === key;
                      const conf = confianzaText(p.confianza);
                      return (
                        <div
                          key={p.campo}
                          className="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5"
                        >
                          <div className="text-xs font-semibold uppercase tracking-wide text-primary/80">
                            {campoLabel(p.campo)}
                          </div>

                          {isEditing ? (
                            <div className="mt-2 space-y-2">
                              <Input
                                autoFocus
                                value={editing[key]}
                                onChange={(e) =>
                                  setEditing((prev) => ({ ...prev, [key]: e.target.value }))
                                }
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    confirmar(doc.id, p.campo, editing[key]);
                                  }
                                }}
                                placeholder={CAMPO_PLACEHOLDER[p.campo] || ""}
                                disabled={isBusy}
                              />
                              <div className="flex items-center gap-2">
                                <Button
                                  size="sm"
                                  onClick={() => confirmar(doc.id, p.campo, editing[key])}
                                  disabled={isBusy || !editing[key].trim()}
                                  className="gap-1.5"
                                >
                                  {isBusy ? (
                                    <>
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      Guardando…
                                    </>
                                  ) : (
                                    "Guardar"
                                  )}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => cancelEdit(key)}
                                  disabled={isBusy}
                                >
                                  Cancelar
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="mt-1">
                              <div className="text-sm text-card-foreground">
                                Mia sugiere: <span className="font-medium">{p.valor}</span>
                              </div>
                              {conf ? <div className="mt-0.5 text-xs text-muted-foreground">{conf}</div> : null}
                              <div className="mt-2 flex items-center gap-2">
                                <Button
                                  size="sm"
                                  onClick={() => confirmar(doc.id, p.campo, p.valor)}
                                  disabled={isBusy || busyKey !== null}
                                  className="gap-1.5"
                                >
                                  {isBusy ? (
                                    <>
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      Guardando…
                                    </>
                                  ) : (
                                    <>
                                      <CheckCircle2 className="h-3.5 w-3.5" />
                                      Es correcto
                                    </>
                                  )}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => startEdit(key, p.valor)}
                                  disabled={isBusy || busyKey !== null}
                                  className="gap-1.5"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                  Corregir
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
