"use client";

// Banco de oro · el examen de no-regresión del despacho (Fase 2 · pantalla del abogado).
//
// Qué es, en corto: el abogado toma un asunto REAL que ya resolvió y aprobó, Mia le quita los
// datos identificables, y ese caso queda guardado como EXAMEN para comprobar que Mia no empeora
// con el tiempo. NO alimenta las respuestas de Mia — es una prueba de calidad.
//
// Reglas duras de esta pantalla:
//  · §G — jamás jerga. El abogado nunca lee "PII", "span", "rubric", "chunk", "tenant", "draft".
//  · `aviso`, `nota_pii` y `nota_captura` los redacta el backend en llano: se muestran LITERALES.
//    No se reescriben, no se resumen, no se esconden.
//  · Nada de falsa seguridad: una lista vacía significa "no encontramos nada", NO "está limpio".
//    La revisión humana es la única red real, y la pantalla lo dice.
//  · Los offsets `start`/`end` son sobre el texto GLOBAL concatenado del caso, NO sobre cada
//    campo: usarlos para resaltar dentro de un campo pinta el tramo equivocado. Se resalta por
//    `valor` (ver `marcarPorValor`).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Eye,
  FileText,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { apiGet, apiSend, plainMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConnectorCard, EmptyHint } from "@/app/_components/PanelUI";

// ── tipos del contrato ────────────────────────────────────────────────────────
type Estado = "draft" | "confirmed" | "archived";

type SpanPii = { tipo: string; valor: string; start: number; end: number };

type DocAnon = { filename: string; chunks: string[] };

type GoldCase = {
  gold_case_id: string;
  status: Estado;
  title: string;
  message_anon: string;
  documents_anon: DocAnon[];
  gold_answer_anon: string;
  rubric_propuesta: { citas_clave: string[]; conclusiones_clave: string[] };
  spans_pii_restantes: SpanPii[];
  nota_pii: string;
  aviso: string;
  nota_captura: string;
};

type CasoLista = {
  gold_case_id: string;
  title: string;
  status: Estado;
  n_citas_clave: number;
  n_conclusiones_clave: number;
  updated_at: string | null;
};

type Matter = { id: string; name: string };

// ── lenguaje llano ────────────────────────────────────────────────────────────
const ETIQUETA_ESTADO: Record<Estado, { texto: string; variant: "warning" | "success" | "secondary" }> = {
  draft: { texto: "Sin revisar", variant: "warning" },
  confirmed: { texto: "Listo para el examen", variant: "success" },
  archived: { texto: "Retirado del examen", variant: "secondary" },
};

/**
 * Nombre en llano de un dato identificable confirmado (§G). `tipo` viene del backend como el
 * MARCADOR del patrón que lo detectó, y el juego de marcadores NO es cerrado: cada país que se
 * instale puede sumar los suyos. Por eso hay fallback: ante un marcador que no conozcamos,
 * decimos "Dato identificable" antes que mostrarle al abogado una clave cruda en mayúsculas.
 */
const NOMBRE_DATO: Record<string, string> = {
  EMAIL: "Correo electrónico",
  URL: "Dirección de internet",
  TELEFONO: "Teléfono",
  CUENTA: "Cuenta bancaria",
  DOCUMENTO: "Documento de identidad",
  CEDULA: "Cédula",
  NIT: "NIT",
  RADICADO: "Radicado",
};

const NOMBRE_SOSPECHA: Record<string, string> = {
  sospecha_nombre: "Posible nombre de persona o empresa",
  sospecha_direccion: "Posible dirección",
  sospecha_id: "Posible número de identificación",
};

function esSospecha(tipo: string): boolean {
  return tipo.startsWith("sospecha");
}

function nombreDato(tipo: string): string {
  if (esSospecha(tipo)) return NOMBRE_SOSPECHA[tipo] ?? "Posible dato identificable";
  return NOMBRE_DATO[tipo] ?? "Dato identificable";
}

function fmtFecha(s: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

// ── resaltado POR VALOR (nunca por offsets) ───────────────────────────────────
type Clase = "confirmado" | "sospecha";
type Trozo = { texto: string; clase: Clase | null };

function escaparRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Tope defensivo: un caso muy sucio podría traer cientos de coincidencias y armar un patrón
// gigantesco. Se resaltan las más largas (las más específicas); el listado de arriba las muestra
// TODAS de todos modos, así que no se le oculta nada al abogado.
const MAX_VALORES_RESALTADOS = 200;

/**
 * Parte un texto en trozos marcando las coincidencias por `valor`.
 *
 * Por qué por valor y no por `start`/`end`: los offsets del backend se calculan sobre el texto
 * GLOBAL del caso (la consulta + la respuesta + todos los fragmentos, unidos con saltos de línea).
 * Aplicarlos a un campo suelto resaltaría un tramo corrido y equivocado. El `valor` es exacto, y
 * un dato identificable que aparece dos veces debe resaltarse las dos veces.
 */
function marcarPorValor(texto: string, spans: SpanPii[]): Trozo[] {
  const clases = new Map<string, Clase>();
  const valores: string[] = [];
  for (const s of spans) {
    const v = (s.valor || "").trim();
    // Un valor de 1-2 caracteres resaltaría media pantalla por coincidencia accidental.
    if (v.length < 3) continue;
    const clase: Clase = esSospecha(s.tipo) ? "sospecha" : "confirmado";
    if (!clases.has(v)) valores.push(v);
    // Si el mismo texto aparece como confirmado y como sospecha, manda confirmado (es lo grave).
    else if (clases.get(v) === "confirmado") continue;
    clases.set(v, clase);
  }
  if (valores.length === 0 || !texto) return [{ texto, clase: null }];

  // De mayor a menor longitud: en una alternancia, el primero que matchea gana, y así
  // "Juan Pérez Gómez" no se parte en el trozo más corto "Juan Pérez".
  const orden = valores.slice().sort((a, b) => b.length - a.length).slice(0, MAX_VALORES_RESALTADOS);
  let rx: RegExp;
  try {
    rx = new RegExp(`(${orden.map(escaparRegex).join("|")})`, "g");
  } catch {
    return [{ texto, clase: null }];
  }

  const trozos: Trozo[] = [];
  let ultimo = 0;
  let m: RegExpExecArray | null;
  while ((m = rx.exec(texto)) !== null) {
    // Un patrón vacío no puede darse (se filtran los valores < 3), pero si lo hiciera, `exec` no
    // avanzaría y esto sería un bucle infinito: se corta explícitamente.
    if (m[0].length === 0) {
      rx.lastIndex += 1;
      continue;
    }
    if (m.index > ultimo) trozos.push({ texto: texto.slice(ultimo, m.index), clase: null });
    trozos.push({ texto: m[0], clase: clases.get(m[0]) ?? "sospecha" });
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) trozos.push({ texto: texto.slice(ultimo), clase: null });
  return trozos;
}

function TextoResaltado({ texto, spans }: { texto: string; spans: SpanPii[] }) {
  const trozos = useMemo(() => marcarPorValor(texto, spans), [texto, spans]);
  if (!texto.trim()) {
    return <p className="text-sm italic text-muted-foreground">Sin texto.</p>;
  }
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
      {trozos.map((t, i) =>
        t.clase === null ? (
          <span key={i}>{t.texto}</span>
        ) : t.clase === "confirmado" ? (
          <mark
            key={i}
            title="Dato identificable que quedó sin ocultar"
            className="rounded-sm bg-destructive/15 px-0.5 font-medium text-destructive underline decoration-destructive/50 decoration-wavy underline-offset-2"
          >
            {t.texto}
          </mark>
        ) : (
          <mark
            key={i}
            title="Mia sospecha que esto identifica a alguien; decides tú"
            className="rounded-sm bg-warning/15 px-0.5 text-warning underline decoration-warning/40 decoration-dotted underline-offset-2"
          >
            {t.texto}
          </mark>
        ),
      )}
    </p>
  );
}

// ── editor de una lista de textos (citas clave / conclusiones clave) ──────────
function ListaEditable({
  id,
  valores,
  onChange,
  placeholder,
  disabled,
  textoVacio,
}: {
  id: string;
  valores: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  disabled?: boolean;
  textoVacio: string;
}) {
  const [nuevo, setNuevo] = useState("");

  function agregar() {
    const v = nuevo.trim();
    if (!v) return;
    onChange([...valores, v]);
    setNuevo("");
  }

  return (
    <div className="space-y-2">
      {valores.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">{textoVacio}</p>
      ) : (
        <ul className="space-y-2">
          {valores.map((v, i) => (
            <li key={i} className="flex items-start gap-2">
              <Textarea
                aria-label={`${placeholder} ${i + 1}`}
                value={v}
                rows={2}
                disabled={disabled}
                onChange={(e) => onChange(valores.map((x, j) => (j === i ? e.target.value : x)))}
                className="min-h-0 flex-1 text-sm"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                aria-label={`Quitar ${placeholder.toLowerCase()} ${i + 1}`}
                onClick={() => onChange(valores.filter((_, j) => j !== i))}
                className="shrink-0 text-muted-foreground hover:text-warning"
              >
                <X className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-start gap-2">
        <Input
          id={id}
          value={nuevo}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setNuevo(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              agregar();
            }
          }}
        />
        <Button type="button" variant="outline" size="sm" onClick={agregar} disabled={disabled || !nuevo.trim()} className="shrink-0">
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </div>
    </div>
  );
}

// ── un campo de texto del caso: se lee resaltado, se edita en crudo ───────────
function CampoTexto({
  titulo,
  ayuda,
  texto,
  spans,
  onChange,
  editable,
  filas = 6,
}: {
  titulo: string;
  ayuda?: string;
  texto: string;
  spans: SpanPii[];
  onChange: (v: string) => void;
  editable: boolean;
  filas?: number;
}) {
  const [editando, setEditando] = useState(false);

  return (
    <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm font-semibold tracking-tight">{titulo}</h4>
          {ayuda ? <p className="mt-0.5 text-sm text-muted-foreground">{ayuda}</p> : null}
        </div>
        {editable ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setEditando((e) => !e)}
            className="shrink-0"
          >
            {editando ? (
              <>
                <Eye className="h-4 w-4" />
                Ver resaltado
              </>
            ) : (
              <>
                <Pencil className="h-4 w-4" />
                Editar
              </>
            )}
          </Button>
        ) : null}
      </div>
      {editando && editable ? (
        <>
          <Textarea
            aria-label={titulo}
            value={texto}
            rows={filas}
            onChange={(e) => onChange(e.target.value)}
            className="text-sm"
          />
          <p className="mt-1.5 text-xs text-muted-foreground">
            Mientras editas no se resalta nada. Vuelve a «Ver resaltado» para revisar lo que quedó.
          </p>
        </>
      ) : (
        <TextoResaltado texto={texto} spans={spans} />
      )}
    </div>
  );
}

// ── pantalla ──────────────────────────────────────────────────────────────────
export default function BancoOroSection() {
  const [permitido, setPermitido] = useState<boolean | null>(null);
  const [casos, setCasos] = useState<CasoLista[]>([]);
  const [cargado, setCargado] = useState(false);
  const [errorCarga, setErrorCarga] = useState("");

  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tono: "ok" | "mal"; texto: string } | null>(null);

  // Captura
  const [capturando, setCapturando] = useState(false);
  const [asuntos, setAsuntos] = useState<Matter[] | null>(null);
  const [asuntoElegido, setAsuntoElegido] = useState("");

  // Revisión
  const [caso, setCaso] = useState<GoldCase | null>(null);
  const [titulo, setTitulo] = useState("");
  const [consulta, setConsulta] = useState("");
  const [respuesta, setRespuesta] = useState("");
  const [documentos, setDocumentos] = useState<DocAnon[]>([]);
  const [citas, setCitas] = useState<string[]>([]);
  const [conclusiones, setConclusiones] = useState<string[]>([]);
  const [confirmando, setConfirmando] = useState(false);
  const [porBorrar, setPorBorrar] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setErrorCarga("");
    try {
      const [consent, lista] = await Promise.all([
        apiGet<{ permitido: boolean }>("/settings/eval-consent"),
        apiGet<{ casos: CasoLista[]; total: number }>("/api/gold-cases"),
      ]);
      setPermitido(consent.permitido);
      setCasos(lista.casos ?? []);
    } catch (err) {
      setErrorCarga(plainMessage(err, "No se pudo cargar el banco de oro."));
    } finally {
      setCargado(true);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function abrirCaso(g: GoldCase) {
    setCaso(g);
    setTitulo(g.title);
    setConsulta(g.message_anon);
    setRespuesta(g.gold_answer_anon);
    setDocumentos(g.documents_anon ?? []);
    setCitas(g.rubric_propuesta?.citas_clave ?? []);
    setConclusiones(g.rubric_propuesta?.conclusiones_clave ?? []);
    setConfirmando(false);
    setMsg(null);
  }

  function cerrarCaso() {
    setCaso(null);
    setConfirmando(false);
    setMsg(null);
  }

  async function cambiarConsentimiento(valor: boolean) {
    setBusy("consent");
    setMsg(null);
    try {
      const r = await apiSend<{ permitido: boolean }>("PUT", "/settings/eval-consent", { permitido: valor });
      setPermitido(r.permitido);
      setMsg({
        tono: "ok",
        texto: r.permitido
          ? "Autorización concedida. Ya puedes guardar un caso resuelto como caso del examen."
          : "Autorización retirada. Los casos que ya guardaste siguen ahí: son anónimos.",
      });
    } catch (err) {
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudo cambiar la autorización.") });
    } finally {
      setBusy(null);
    }
  }

  async function abrirCaptura() {
    setCapturando(true);
    setMsg(null);
    if (asuntos !== null) return;
    try {
      const ms = await apiGet<Matter[]>("/api/matters");
      setAsuntos(ms ?? []);
    } catch (err) {
      setAsuntos([]);
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudieron cargar tus casos.") });
    }
  }

  async function capturar() {
    if (!asuntoElegido) return;
    setBusy("capturar");
    setMsg(null);
    try {
      // Sin cuerpo, a propósito: el servidor arma el caso leyendo el asunto y solo nos devuelve
      // la versión ya anonimizada. El material sin anonimizar NUNCA pasa por el navegador.
      const g = await apiSend<GoldCase>("POST", `/api/matters/${asuntoElegido}/gold-cases:draft`);
      await cargar();
      setCapturando(false);
      setAsuntoElegido("");
      abrirCaso(g);
    } catch (err) {
      setMsg({
        tono: "mal",
        texto: plainMessage(err, "No se pudo guardar este caso como caso del examen."),
      });
    } finally {
      setBusy(null);
    }
  }

  async function releer(id: string) {
    setBusy(id);
    setMsg(null);
    try {
      abrirCaso(await apiGet<GoldCase>(`/api/gold-cases/${id}`));
    } catch (err) {
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudo abrir el caso.") });
    } finally {
      setBusy(null);
    }
  }

  async function guardar() {
    if (!caso) return;
    setBusy("guardar");
    setMsg(null);
    try {
      await apiSend("PATCH", `/api/gold-cases/${caso.gold_case_id}`, {
        title: titulo,
        message: consulta,
        gold_answer: respuesta,
        documents: documentos,
        rubric: { citas_clave: citas, conclusiones_clave: conclusiones },
      });
      // Se relee para que el resaltado refleje lo que quedó DESPUÉS de editar: el servidor
      // recalcula lo identificable pendiente sobre el texto ya guardado.
      const g = await apiGet<GoldCase>(`/api/gold-cases/${caso.gold_case_id}`);
      abrirCaso(g);
      await cargar();
      setMsg({ tono: "ok", texto: "Cambios guardados." });
    } catch (err) {
      // 400 = el texto todavía trae datos identificables: el backend NO guardó nada y su aviso
      // se muestra tal cual (§G: lo redacta él en llano).
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudieron guardar los cambios.") });
    } finally {
      setBusy(null);
    }
  }

  async function confirmar() {
    if (!caso) return;
    setBusy("confirmar");
    setMsg(null);
    try {
      await apiSend<{ gold_case_id: string; status: Estado }>(
        "POST",
        `/api/gold-cases/${caso.gold_case_id}:confirm`,
      );
      const g = await apiGet<GoldCase>(`/api/gold-cases/${caso.gold_case_id}`);
      abrirCaso(g);
      await cargar();
      setMsg({ tono: "ok", texto: "Caso confirmado. Ya forma parte del examen del despacho." });
    } catch (err) {
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudo confirmar el caso.") });
    } finally {
      setBusy(null);
      setConfirmando(false);
    }
  }

  async function borrar(id: string) {
    setBusy(id);
    setMsg(null);
    try {
      await apiSend("DELETE", `/api/gold-cases/${id}`);
      if (caso?.gold_case_id === id) cerrarCaso();
      await cargar();
      setMsg({ tono: "ok", texto: "Caso borrado. Ya no forma parte del examen." });
    } catch (err) {
      setMsg({ tono: "mal", texto: plainMessage(err, "No se pudo borrar el caso.") });
    } finally {
      setBusy(null);
      setPorBorrar(null);
    }
  }

  // Lo identificable pendiente, separado en dos clases: lo CONFIRMADO (grave: sobrevivió a la
  // limpieza) y lo que Mia solo SOSPECHA (no lo ocultó; decide el abogado).
  const { confirmados, sospechas } = useMemo(() => {
    const spans = caso?.spans_pii_restantes ?? [];
    return {
      confirmados: spans.filter((s) => !esSospecha(s.tipo)),
      sospechas: spans.filter((s) => esSospecha(s.tipo)),
    };
  }, [caso]);

  if (!cargado) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
    );
  }

  if (errorCarga) {
    return (
      <p role="alert" className="text-sm text-warning">
        {errorCarga}
      </p>
    );
  }

  const avisoMsg = msg ? (
    <p
      role={msg.tono === "ok" ? "status" : "alert"}
      className={`animate-fade-in rounded-md px-3 py-2 text-sm ${
        msg.tono === "ok" ? "bg-muted text-muted-foreground" : "bg-warning/10 text-warning"
      }`}
    >
      {msg.texto}
    </p>
  ) : null;

  // ── vista: revisión de un caso ──────────────────────────────────────────────
  if (caso) {
    const editable = caso.status === "draft";
    const etiqueta = ETIQUETA_ESTADO[caso.status] ?? ETIQUETA_ESTADO.draft;

    return (
      <div className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <button
              type="button"
              onClick={cerrarCaso}
              className="text-sm font-medium text-primary transition-colors hover:text-primary/80"
            >
              ← Volver al banco de oro
            </button>
            <h3 className="mt-1 flex items-center gap-2 text-base font-semibold tracking-tight">
              Revisa el caso antes de confirmarlo
              <Badge variant={etiqueta.variant}>{etiqueta.texto}</Badge>
            </h3>
          </div>
          {editable ? (
            <Button size="sm" variant="outline" onClick={guardar} disabled={busy !== null} className="shrink-0">
              {busy === "guardar" ? "Guardando…" : "Guardar cambios"}
            </Button>
          ) : null}
        </div>

        {/* El backend redacta estos textos en llano: se muestran LITERALES, sin retocar. */}
        <p role="alert" className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
          {caso.aviso}
        </p>
        {caso.nota_captura ? (
          <p role="alert" className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
            {caso.nota_captura}
          </p>
        ) : null}

        {avisoMsg}

        {/* Lo identificable pendiente. Dos clases, distinguidas a la vista y por escrito. */}
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
          <h4 className="text-sm font-semibold tracking-tight">Lo que quedó sin ocultar</h4>
          <p className="mt-1 text-sm text-muted-foreground">{caso.nota_pii}</p>

          {confirmados.length === 0 && sospechas.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">
              No marcamos nada en este caso. Aun así, léelo entero: tu revisión es lo único que de
              verdad garantiza que aquí no quede nada del cliente.
            </p>
          ) : (
            <div className="mt-3 space-y-4">
              {confirmados.length > 0 ? (
                <div>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
                    <span className="text-sm font-medium text-destructive">
                      Datos identificables que quedaron sin ocultar ({confirmados.length})
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Esto identifica al cliente y sigue en el texto. Bórralo o cámbialo: sin eso no
                    podrás confirmar el caso.
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {confirmados.map((s, i) => (
                      <li key={`c-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
                        <Badge variant="destructive">{nombreDato(s.tipo)}</Badge>
                        <span className="break-all font-medium text-destructive">{s.valor}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {sospechas.length > 0 ? (
                <div>
                  <div className="flex items-center gap-2">
                    <Eye className="h-4 w-4 shrink-0 text-warning" />
                    <span className="text-sm font-medium text-warning">
                      Marcado por si acaso: decides tú ({sospechas.length})
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Mia no ocultó esto, solo lo señala porque PODRÍA identificar a alguien. Puede
                    ser un nombre real o algo inofensivo. Míralo y decide.
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {sospechas.map((s, i) => (
                      <li key={`s-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
                        <Badge variant="warning">{nombreDato(s.tipo)}</Badge>
                        <span className="break-all text-foreground">{s.valor}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Nombre del caso */}
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
          <Label htmlFor="oro-titulo" className="mb-1.5 block text-sm font-semibold">
            Nombre del caso
          </Label>
          <p className="mb-2 text-sm text-muted-foreground">
            Así lo verás en la lista. Que no lleve el nombre del cliente ni su identificación.
          </p>
          <Input
            id="oro-titulo"
            value={titulo}
            disabled={!editable}
            onChange={(e) => setTitulo(e.target.value)}
          />
        </div>

        <CampoTexto
          titulo="La consulta"
          ayuda="Lo que se le preguntó a Mia, ya sin los datos del cliente. Es el punto de partida del examen."
          texto={consulta}
          spans={caso.spans_pii_restantes}
          onChange={setConsulta}
          editable={editable}
        />

        <CampoTexto
          titulo="La respuesta que aprobaste"
          ayuda="Tu borrador aprobado, ya sin los datos del cliente. Es la respuesta con la que se compara a Mia."
          texto={respuesta}
          spans={caso.spans_pii_restantes}
          onChange={setRespuesta}
          editable={editable}
          filas={10}
        />

        {/* Documentos */}
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-semibold tracking-tight">Los documentos del caso</h4>
            <p className="mt-0.5 text-sm text-muted-foreground">
              El texto de los documentos, ya sin los datos del cliente.
            </p>
          </div>
          {documentos.length === 0 ? (
            <EmptyHint icon={FileText}>Este caso no guardó texto de documentos.</EmptyHint>
          ) : (
            documentos.map((d, di) => (
              <div key={di} className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
                <div className="mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm font-medium">{d.filename || "Documento sin nombre"}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {d.chunks.length} {d.chunks.length === 1 ? "fragmento" : "fragmentos"}
                  </span>
                </div>
                <div className="space-y-3">
                  {d.chunks.map((c, ci) => (
                    <div key={ci} className="rounded-lg shadow-neu-raised border border-border/10 border-border/60 bg-background/40 p-3">
                      {editable ? (
                        <Textarea
                          aria-label={`Texto ${ci + 1} de ${d.filename || "documento"}`}
                          value={c}
                          rows={4}
                          onChange={(e) =>
                            setDocumentos((prev) =>
                              prev.map((doc, j) =>
                                j === di
                                  ? { ...doc, chunks: doc.chunks.map((x, k) => (k === ci ? e.target.value : x)) }
                                  : doc,
                              ),
                            )
                          }
                          className="text-sm"
                        />
                      ) : (
                        <TextoResaltado texto={c} spans={caso.spans_pii_restantes} />
                      )}
                    </div>
                  ))}
                </div>
                {editable ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    El texto de los documentos se edita directamente; no se resalta mientras lo cambias.
                  </p>
                ) : null}
              </div>
            ))
          )}
        </div>

        {/* Lo que se le va a exigir a Mia */}
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
          <h4 className="text-sm font-semibold tracking-tight">Qué se le va a exigir a Mia</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            Esto es el examen: cada vez que se corra, se comprobará que la respuesta de Mia traiga
            estas citas y llegue a estas conclusiones. Si algo aquí sobra o falta, el examen mide mal.
          </p>

          <div className="mt-4">
            <Label htmlFor="oro-cita-nueva" className="mb-1.5 block text-sm font-medium">
              Citas clave
            </Label>
            <p className="mb-2 text-sm text-muted-foreground">
              Las normas y sentencias que Mia tiene que citar. Mia las sacó de tu borrador aprobado:
              quita las que no sean esenciales.
            </p>
            <ListaEditable
              id="oro-cita-nueva"
              valores={citas}
              onChange={setCitas}
              disabled={!editable}
              placeholder="Añadir una cita clave"
              textoVacio="No hay citas clave. Añade las que Mia no pueda dejar de citar."
            />
          </div>

          <div className="mt-6">
            <Label htmlFor="oro-concl-nueva" className="mb-1.5 block text-sm font-medium">
              Conclusiones clave
            </Label>
            {/* En la captura automática esta lista SIEMPRE llega vacía: el diagnóstico del turno no
                se guarda en ningún sitio, así que no hay de dónde proponerlas. No es un error, y no
                se inventan: se le pide al abogado que las escriba, explicándole para qué sirven. */}
            {conclusiones.length === 0 ? (
              <div className="mb-2 rounded-lg shadow-neu-raised border border-border/10 border-dashed border-primary/40 bg-primary/5 px-3 py-2.5">
                <p className="text-sm text-foreground">
                  <span className="font-medium">Esto lo tienes que escribir tú.</span> Mia puede
                  proponerte las citas porque están en el borrador, pero no puede adivinar a qué
                  conclusión querías llegar.
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Escribe, en una frase cada una, las conclusiones a las que Mia tenía que llegar en
                  este caso: el problema de fondo, el riesgo, la salida que recomendaste. Es lo que se
                  le va a exigir en el examen. Sin esto, el examen solo comprobará que cite bien, no
                  que acierte.
                </p>
              </div>
            ) : (
              <p className="mb-2 text-sm text-muted-foreground">
                Una frase por conclusión: el problema de fondo, el riesgo, la salida que recomendaste.
              </p>
            )}
            <ListaEditable
              id="oro-concl-nueva"
              valores={conclusiones}
              onChange={setConclusiones}
              disabled={!editable}
              placeholder="Añadir una conclusión clave"
              textoVacio="Todavía no escribiste ninguna conclusión clave."
            />
          </div>
        </div>

        {/* Confirmar / borrar */}
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
          {editable ? (
            <>
              <h4 className="text-sm font-semibold tracking-tight">Confirmar el caso</h4>
              <p className="mt-1 text-sm text-muted-foreground">
                Al confirmarlo, el caso entra al examen del despacho y ya no se puede volver a
                editar. Si más adelante quieres sacarlo, tendrás que borrarlo.
              </p>

              {confirmando ? (
                <div
                  role="alertdialog"
                  aria-label="Confirmar el caso de oro"
                  className="mt-3 animate-fade-in rounded-lg border border-warning/30 bg-warning/10 p-3"
                >
                  <p className="text-sm font-medium text-warning">
                    ¿Confirmas este caso? Después no podrás editarlo.
                  </p>
                  {confirmados.length > 0 ? (
                    <p className="mt-2 text-sm text-destructive">
                      Todavía hay {confirmados.length}{" "}
                      {confirmados.length === 1 ? "dato identificable" : "datos identificables"} en el
                      texto ({confirmados.map((s) => s.valor).join(", ")}). No vas a poder confirmar
                      hasta quitarlos.
                    </p>
                  ) : null}
                  {sospechas.length > 0 ? (
                    <p className="mt-2 text-sm text-warning">
                      Además marcamos {sospechas.length}{" "}
                      {sospechas.length === 1 ? "cosa" : "cosas"} que podrían identificar a alguien
                      ({sospechas.map((s) => s.valor).join(", ")}). Mia no las ocultó: si alguna es
                      real, quítala antes de continuar.
                    </p>
                  ) : null}
                  {conclusiones.length === 0 ? (
                    <p className="mt-2 text-sm text-warning">
                      No escribiste conclusiones clave. Puedes confirmar así, pero el examen solo
                      comprobará las citas, no si Mia acierta el fondo.
                    </p>
                  ) : null}
                  <p className="mt-2 text-sm text-warning">
                    Lo que no hayas revisado tú, nadie lo revisó.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" onClick={confirmar} disabled={busy !== null}>
                      {busy === "confirmar" ? "Confirmando…" : "Sí, confirmar"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmando(false)} disabled={busy !== null}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => setConfirmando(true)} disabled={busy !== null}>
                    <Check className="h-4 w-4" />
                    Confirmar caso
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setPorBorrar(caso.gold_case_id)}
                    disabled={busy !== null}
                    className="text-warning hover:text-warning"
                  >
                    <Trash2 className="h-4 w-4" />
                    Borrar caso
                  </Button>
                </div>
              )}
            </>
          ) : (
            <>
              <h4 className="text-sm font-semibold tracking-tight">Este caso ya está confirmado</h4>
              <p className="mt-1 text-sm text-muted-foreground">
                Forma parte del examen del despacho y no se puede editar. Si quieres sacarlo, bórralo.
              </p>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPorBorrar(caso.gold_case_id)}
                disabled={busy !== null}
                className="mt-3 text-warning hover:text-warning"
              >
                <Trash2 className="h-4 w-4" />
                Borrar caso
              </Button>
            </>
          )}

          {porBorrar === caso.gold_case_id ? (
            <div
              role="alertdialog"
              aria-label="Confirmar borrado del caso"
              className="mt-3 animate-fade-in rounded-lg border border-warning/30 bg-warning/10 p-3"
            >
              <p className="text-sm text-warning">
                ¿Borrar «{caso.title || "este caso"}»? Se borra de verdad y no se puede recuperar. El
                examen dejará de incluirlo.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => borrar(caso.gold_case_id)}
                  disabled={busy !== null}
                >
                  {busy === caso.gold_case_id ? "Borrando…" : "Sí, borrar"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPorBorrar(null)} disabled={busy !== null}>
                  Cancelar
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  // ── vista: lista + captura ──────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* El título lo pone SectionTitle desde la página (patrón del resto de secciones);
          aquí queda solo la explicación, que sí es propia de esta pantalla. */}
      <div>
        <p className="text-sm text-muted-foreground">
          Es el examen de tu despacho. Guarda aquí casos que ya resolviste y aprobaste: Mia les
          quita los datos del cliente y los conserva como prueba para comprobar, con el tiempo, que
          no empeora. Estos casos <span className="font-medium text-foreground">no</span> alimentan
          sus respuestas: solo la califican.
        </p>
      </div>

      {avisoMsg}

      {/* Consentimiento — manda sobre todo lo demás. Apagado de fábrica. */}
      <ConnectorCard
        icon={ShieldCheck}
        title="Autorización para usar casos reales"
        subtitle={permitido ? "Concedida" : "No concedida"}
        active={Boolean(permitido)}
        actions={
          <Button
            size="sm"
            variant={permitido ? "outline" : "default"}
            onClick={() => cambiarConsentimiento(!permitido)}
            disabled={busy !== null}
          >
            {busy === "consent" ? "Guardando…" : permitido ? "Retirar autorización" : "Autorizar"}
          </Button>
        }
      >
        <p className="text-sm text-muted-foreground">
          Para armar un caso del examen, Mia tiene que leer un caso real: el expediente, tu consulta
          y el borrador que aprobaste. Lo que queda guardado va{" "}
          <span className="font-medium text-foreground">sin los datos del cliente</span> y lo revisas
          tú antes de que cuente, pero la captura sí toca material real. Por eso te lo preguntamos
          antes, y viene apagado.
        </p>
        {permitido ? (
          <p className="mt-2 text-sm text-muted-foreground">
            Puedes retirar la autorización cuando quieras: Mia dejará de capturar casos nuevos. Los
            casos que ya guardaste no se borran, porque ya son anónimos; para sacar uno concreto,
            bórralo desde la lista.
          </p>
        ) : null}
      </ConnectorCard>

      {/* Captura */}
      {permitido ? (
        <div className="rounded-lg border border-border/10 bg-card shadow-neu-raised p-4">
          <h4 className="text-sm font-semibold tracking-tight">Guardar un caso resuelto como caso del examen</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            Solo sirven los casos que ya resolviste y en los que aprobaste un borrador: el examen
            necesita saber cuál era la buena respuesta. Elige uno e inténtalo; si no sirve, te decimos
            por qué.
          </p>
          {capturando ? (
            <div className="mt-3 space-y-3 animate-fade-in">
              <div>
                <Label htmlFor="oro-asunto" className="mb-1.5 block text-sm">
                  ¿Qué caso quieres guardar?
                </Label>
                {asuntos === null ? (
                  <Skeleton className="h-10 w-full max-w-md rounded-md" />
                ) : asuntos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Todavía no tienes casos. Resuelve uno y aprueba su borrador para poder guardarlo.
                  </p>
                ) : (
                  <select
                    id="oro-asunto"
                    value={asuntoElegido}
                    onChange={(e) => setAsuntoElegido(e.target.value)}
                    className="h-10 w-full max-w-md rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="">Elige un caso…</option>
                    {asuntos.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={capturar} disabled={busy !== null || !asuntoElegido}>
                  {busy === "capturar" ? "Preparando el caso…" : "Guardar y revisar"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setCapturando(false);
                    setAsuntoElegido("");
                  }}
                  disabled={busy !== null}
                >
                  Cancelar
                </Button>
              </div>
            </div>
          ) : (
            <Button size="sm" onClick={abrirCaptura} className="mt-3">
              <Plus className="h-4 w-4" />
              Guardar un caso
            </Button>
          )}
        </div>
      ) : null}

      {/* Lista */}
      <div>
        <h4 className="mb-2 text-sm font-semibold tracking-tight">
          Casos guardados{casos.length ? ` (${casos.length})` : ""}
        </h4>
        {casos.length === 0 ? (
          <EmptyHint icon={ShieldCheck}>
            Todavía no hay casos en el examen. {permitido
              ? "Guarda un caso que ya resolviste para empezar."
              : "Autoriza arriba el uso de casos reales para poder guardar el primero."}
          </EmptyHint>
        ) : (
          <ul className="space-y-2">
            {casos.map((c) => {
              const etiqueta = ETIQUETA_ESTADO[c.status] ?? ETIQUETA_ESTADO.draft;
              return (
                <li
                  key={c.gold_case_id}
                  className="rounded-lg border border-border/10 bg-card shadow-neu-raised px-4 py-3 transition-colors hover:border-primary/25"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium">{c.title || "Caso sin nombre"}</span>
                        <Badge variant={etiqueta.variant}>{etiqueta.texto}</Badge>
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {c.n_citas_clave} {c.n_citas_clave === 1 ? "cita clave" : "citas clave"} ·{" "}
                        {c.n_conclusiones_clave}{" "}
                        {c.n_conclusiones_clave === 1 ? "conclusión clave" : "conclusiones clave"} ·
                        actualizado {fmtFecha(c.updated_at)}
                      </div>
                      {c.status === "draft" ? (
                        <p className="mt-1 text-xs font-medium text-warning">
                          Falta que lo revises: no cuenta en el examen hasta que lo confirmes.
                        </p>
                      ) : null}
                      {c.status === "confirmed" && c.n_conclusiones_clave === 0 ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Sin conclusiones clave: solo se comprueban las citas.
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => releer(c.gold_case_id)} disabled={busy !== null}>
                        {busy === c.gold_case_id ? "Abriendo…" : c.status === "draft" ? "Revisar" : "Ver"}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setPorBorrar(c.gold_case_id)}
                        disabled={busy !== null}
                        className="text-muted-foreground hover:text-warning"
                      >
                        Borrar
                      </Button>
                    </div>
                  </div>

                  {porBorrar === c.gold_case_id ? (
                    <div
                      role="alertdialog"
                      aria-label="Confirmar borrado del caso"
                      className="mt-3 animate-fade-in rounded-lg border border-warning/30 bg-warning/10 p-3"
                    >
                      <p className="text-sm text-warning">
                        ¿Borrar «{c.title || "este caso"}»? Se borra de verdad y no se puede
                        recuperar. El examen dejará de incluirlo.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => borrar(c.gold_case_id)}
                          disabled={busy !== null}
                        >
                          {busy === c.gold_case_id ? "Borrando…" : "Sí, borrar"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setPorBorrar(null)} disabled={busy !== null}>
                          Cancelar
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
