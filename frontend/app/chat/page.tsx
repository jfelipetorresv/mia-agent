"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Scale,
  Plus,
  Send,
  Sparkles,
  FolderOpen,
  BellRing,
  Settings2,
  MessagesSquare,
  Wand2,
  UserRound,
  SlidersHorizontal,
  Pin,
} from "lucide-react";
import { apiGet, streamPost, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import MiaMarkdown from "@/components/MiaMarkdown";
import { AtajosPanel } from "./_components/AtajosPanel";
import { cn } from "@/lib/utils";

type Conversation = { id: string; title: string; updated_at: string };
type Role = "user" | "assistant";
type Message = { role: Role; content: string };
// Atajo de la firma u organización: un clic PRE-LLENA el cuadro de mensaje
// con `texto` — el abogado revisa y decide si lo envía (consent-first, nunca se auto-envía).
// `clave` identifica el atajo para la pantalla donde el abogado los gobierna ("guia:<id>",
// "agente:<id>", "propio:<id>"); `fijado` es lo que él marcó para tenerlo siempre a mano.
type Atajo = {
  kind: "guia" | "agente" | "propio";
  id: string;
  clave: string;
  label: string;
  texto: string;
  fijado?: boolean;
};

// Ejemplos que ENSEÑAN qué puede hacer Mia (empty state). Cada uno toca una
// capacidad real: sus asuntos, un recordatorio, la configuración y lo que Mia ya
// sabe del despacho.
//
// AGNÓSTICOS DE JURISDICCIÓN — obligatorio. Estos textos los ve CUALQUIER despacho de
// CUALQUIER país el primer día, antes de configurar nada, así que no pueden nombrar una
// figura jurídica, una rama del derecho, un tipo de trámite, un órgano judicial ni una
// moneda de ningún ordenamiento concreto. Preguntan por el PROPIO trabajo del abogado y
// por el estado de Mia, que existen en todas partes. (Antes había aquí una figura del
// derecho administrativo de un solo país y una llamada a un órgano judicial: se
// eliminaron.) Al añadir un ejemplo nuevo, leelo como si fueras un despacho del otro
// lado del mundo: si tiene que traducir el concepto, no sirve.
const EXAMPLES = [
  { icon: FolderOpen, text: "¿Qué asuntos tengo pendientes?" },
  { icon: BellRing, text: "Recuérdame revisar mis plazos mañana a las 9" },
  { icon: Settings2, text: "¿Qué me falta para terminar de configurar a Mia?" },
  { icon: Sparkles, text: "¿Qué has aprendido de mi firma u organización hasta ahora?" },
];

function saludoDelDia(): string {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function ChatPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [atajos, setAtajos] = useState<Atajo[]>([]);
  const [panelAtajos, setPanelAtajos] = useState(false);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [typing, setTyping] = useState(false); // Mia "escribiendo" (typewriter activo)
  const [matterRequired, setMatterRequired] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const typerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  async function loadConversations() {
    try {
      setConversations(await apiGet<Conversation[]>("/api/assistant/conversations"));
    } catch {
      /* sin conversaciones todavía */
    }
  }

  // Los atajos se recargan también tras cada cambio en la pantalla de atajos, para que el
  // abogado vea el efecto de fijar, ocultar o renombrar sin recargar la página.
  const cargarAtajos = useCallback(() => {
    apiGet<{ atajos: Atajo[] }>("/api/atajos")
      .then((res) => setAtajos(res.atajos || []))
      .catch(() => setAtajos([]));
  }, []);

  useEffect(() => {
    loadConversations();
    cargarAtajos();
    return () => {
      abortRef.current?.abort();
      if (typerRef.current) clearInterval(typerRef.current);
    };
  }, [cargarAtajos]);

  // Consent-first: PRE-LLENA el cuadro de mensaje con el texto del atajo. El abogado lo
  // revisa y edita antes de enviar — nunca se auto-envía.
  // Se llama `aplicarAtajo` y NO `useAtajo`: es un manejador de clic corriente, no un
  // hook. Con el nombre anterior la regla `react-hooks/rules-of-hooks` lo tomaba por
  // hook y marcaba error al invocarlo dentro de onClick.
  function aplicarAtajo(texto: string) {
    setInput(texto);
    inputRef.current?.focus();
  }

  // Autoscroll al fondo mientras Mia responde o llega un mensaje nuevo.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  async function openConversation(id: string) {
    if (streaming) return;
    setActiveId(id);
    setStatus("");
    setMatterRequired(false);
    try {
      const rows = await apiGet<{ role: Role; content: string }[]>(
        `/api/assistant/conversations/${id}/messages`,
      );
      setMessages(rows.map((r) => ({ role: r.role, content: r.content })));
    } catch {
      setMessages([]);
    }
  }

  function newConversation() {
    if (streaming) return;
    setActiveId(null);
    setMessages([]);
    setStatus("");
    setInput("");
    setMatterRequired(false);
    inputRef.current?.focus();
  }

  // Revela la respuesta de Mia carácter a carácter: el motor responde en bloque,
  // así que la sensación de escritura la damos en el navegador (nunca un pegote de
  // golpe). ~2 s para textos largos; los cortos aparecen casi al instante.
  function typewriter(full: string) {
    if (typerRef.current) clearInterval(typerRef.current);
    setTyping(true);
    let shown = 0;
    const step = Math.max(1, Math.round(full.length / 120));
    typerRef.current = setInterval(() => {
      shown = Math.min(full.length, shown + step);
      const slice = full.slice(0, shown);
      setMessages((m) => {
        const copy = [...m];
        const last = copy.length - 1;
        if (last >= 0 && copy[last].role === "assistant") {
          copy[last] = { role: "assistant", content: slice };
        }
        return copy;
      });
      if (shown >= full.length && typerRef.current) {
        clearInterval(typerRef.current);
        typerRef.current = null;
        setTyping(false);
      }
    }, 16);
  }

  async function send(preset?: string) {
    const text = (preset ?? input).trim();
    if (!text || streaming) return;
    setInput("");
    setMatterRequired(false);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setStatus("Mia está pensando…");
    setStreaming(true);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let answered = false;
    try {
      await streamPost(
        "/api/assistant/chat/stream",
        { message: text, conversation_id: activeId },
        (event, data) => {
          const payload = data as { message?: string; conversation_id?: string };
          if (event === "thinking") {
            setStatus(payload.message || "Mia está pensando…");
          } else if (event === "reply") {
            answered = true;
            setStatus("");
            if (payload.conversation_id) setActiveId(payload.conversation_id);
            typewriter(payload.message || "");
          } else if (event === "matter_required") {
            answered = true;
            setStatus("");
            setMatterRequired(true);
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = {
                role: "assistant",
                content: payload.message || "Este trabajo debe continuar dentro de un asunto.",
              };
              return copy;
            });
          } else if (event === "error") {
            answered = true;
            setStatus("");
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = {
                role: "assistant",
                content: payload.message || "No pude responder en este momento.",
              };
              return copy;
            });
          }
        },
        controller.signal,
      );
      if (!answered) throw new Error("sin respuesta");
      // Refresca la lista: una conversación nueva estrena título con este turno.
      loadConversations();
    } catch (err) {
      setStatus("");
      const msg =
        err instanceof ApiError && !err.message.startsWith("Error ")
          ? err.message
          : "No pude responder en este momento. Intenta de nuevo en unos minutos.";
      setMessages((m) => {
        const copy = [...m];
        if (copy.length && copy[copy.length - 1].role === "assistant") {
          copy[copy.length - 1] = { role: "assistant", content: msg };
        }
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }

  const empty = messages.length === 0;
  const lastIdx = messages.length - 1;

  return (
    <div className="flex h-[100dvh] min-h-0">
      {/* Historial de conversaciones — se pliega en móvil para dar todo el ancho al hilo. */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/40 md:flex">
        <div className="p-3">
          <Button onClick={newConversation} variant="outline" className="w-full justify-start gap-2">
            <Plus className="h-4 w-4" />
            Nueva conversación
          </Button>
        </div>
        <nav className="flex-1 overflow-auto px-2 pb-3">
          {conversations.length === 0 ? (
            <div className="px-2 py-6 text-center">
              <MessagesSquare className="mx-auto mb-2 h-5 w-5 text-muted-foreground/50" />
              <p className="text-xs text-muted-foreground">
                Tus conversaciones con Mia aparecerán aquí.
              </p>
            </div>
          ) : (
            <ul className="space-y-0.5">
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => openConversation(c.id)}
                    className={cn(
                      "relative w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors",
                      c.id === activeId
                        ? "bg-accent font-medium text-accent-foreground before:absolute before:left-0 before:top-1/2 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-primary"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    {c.title || "Conversación"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </aside>

      {/* Hilo */}
      <div className="flex min-w-0 flex-1 flex-col bg-aurora">
        <div className="flex-1 overflow-auto">
          {empty ? (
            <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col items-center justify-center px-4 py-16 text-center">
              {/* Avatar de Mia — MISMA forma y mismo acabado que en el hilo
                  (rounded-full, color plano): el objeto no cambia de identidad al
                  pasar de la pantalla vacía a la conversación. Sin halo desenfocado
                  detrás ni degradado: son decoración, no información. */}
              <div className="mb-6 flex h-16 w-16 animate-slide-up items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Scale className="h-8 w-8" />
              </div>
              <h1
                className="animate-slide-up text-display"
                style={{ animationDelay: "60ms", animationFillMode: "backwards" }}
              >
                {saludoDelDia()}. Soy Mia.
              </h1>
              <p
                className="mt-3 max-w-md animate-slide-up text-muted-foreground"
                style={{ animationDelay: "120ms", animationFillMode: "backwards" }}
              >
                Aquí puedo ayudarte a organizar tu trabajo y tus recordatorios. Para analizar
                un caso o preparar un escrito, entra al asunto correspondiente.
              </p>
              <div className="mt-10 grid w-full max-w-lg gap-3 sm:grid-cols-2">
                {EXAMPLES.map((ex, i) => (
                  <button
                    key={ex.text}
                    onClick={() => send(ex.text)}
                    className="group animate-slide-up rounded-lg border border-border/10 bg-card/80 px-4 py-3.5 text-left text-sm text-card-foreground shadow-neu-raised backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[var(--neu-raised),_0_12px_24px_-8px_hsl(var(--primary)/0.12)]"
                    style={{ animationDelay: `${180 + i * 70}ms`, animationFillMode: "backwards" }}
                  >
                    <ex.icon className="mb-2 h-4 w-4 text-primary transition-transform duration-200 group-hover:scale-110" />
                    {ex.text}
                  </button>
                ))}
              </div>
              {/* Atajos: los propongo yo y el abogado manda sobre ellos. El acceso para
                  gobernarlos vive AQUÍ, junto a los propios atajos, porque es aquí donde se
                  le ocurre que uno sobra o que falta otro; mandarlo a otra pantalla a
                  buscarlo es la forma más segura de que no lo haga nunca. */}
              <div
                className="mt-8 flex w-full max-w-lg animate-slide-up flex-wrap items-center justify-center gap-2"
                style={{ animationDelay: "420ms", animationFillMode: "backwards" }}
              >
                {atajos.map((a) => (
                  <button
                    key={a.clave || `${a.kind}-${a.id}`}
                    onClick={() => aplicarAtajo(a.texto)}
                    title="Se agrega a tu cuadro de mensaje para que lo revises antes de enviar"
                    className="group inline-flex items-center gap-1.5 rounded-full border border-border/10 bg-card/80 px-3.5 py-1.5 text-xs font-medium text-card-foreground shadow-neu-raised backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40"
                  >
                    {a.fijado ? (
                      <Pin className="h-3.5 w-3.5 text-primary" />
                    ) : a.kind === "agente" ? (
                      <UserRound className="h-3.5 w-3.5 text-primary" />
                    ) : (
                      <Wand2 className="h-3.5 w-3.5 text-primary" />
                    )}
                    {a.label}
                  </button>
                ))}
                <button
                  onClick={() => setPanelAtajos(true)}
                  title="Fija los que quieras tener siempre, aparta los que te estorben o escribe uno tuyo"
                  className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border bg-transparent px-3.5 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:text-foreground"
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  {atajos.length > 0 ? "Ajustar mis atajos" : "Crear un atajo"}
                </button>
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-2xl px-4 py-6">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "mb-6 flex gap-3 animate-message-in",
                    m.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  {m.role === "assistant" ? (
                    <div className="relative mt-0.5 h-8 w-8 shrink-0">
                      {streaming && i === lastIdx && !m.content ? (
                        <span
                          className="absolute inset-0 rounded-full bg-primary/40 blur-md animate-pulse-soft"
                          aria-hidden
                        />
                      ) : null}
                      <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
                        <Scale className="h-4 w-4" />
                      </div>
                    </div>
                  ) : null}
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-neu-raised"
                        : "max-w-[80%] pt-1 font-serif text-[15px] leading-relaxed text-foreground"
                    }
                  >
                    {m.content ? (
                      m.role === "assistant" ? (
                        <MiaMarkdown
                          text={m.content}
                          trailing={
                            typing && i === lastIdx ? (
                              <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-blink bg-primary" aria-hidden />
                            ) : null
                          }
                        />
                      ) : (
                        m.content
                      )
                    ) : (
                      <ThinkingDots />
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
              {matterRequired ? (
                <div className="mb-6 flex justify-center animate-slide-up">
                  <Button onClick={() => router.push("/")} variant="cta" className="gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Ir a mis asuntos
                  </Button>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Barra de escritura */}
        <div className="bg-gradient-to-t from-background via-background/95 to-transparent pt-2">
          <div className="mx-auto w-full max-w-2xl px-4 pb-4">
            {status ? (
              <p className="mb-2 flex items-center gap-2 text-sm text-muted-foreground animate-fade-in">
                <span className="flex gap-1">
                  <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
                </span>
                {status}
              </p>
            ) : null}
            <div className="flex items-end gap-2 rounded-lg border border-border/20 bg-secondary/30 p-2 shadow-neu-sunken transition-colors focus-within:border-primary/40">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={1}
                placeholder="Escribe tu consulta a Mia…"
                className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
              />
              <Button
                onClick={() => send()}
                disabled={streaming || !input.trim()}
                size="icon"
                aria-label="Enviar"
                className="transition-transform active:scale-95"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            {/* Aviso de responsabilidad del producto: se lee SIEMPRE. Sin modificador
                de opacidad (lo dejaba por debajo del contraste mínimo AA) y con el
                token de texto meta, no con un tamaño suelto. */}
            <p className="mt-2 text-center text-meta text-muted-foreground">
              Mia propone; tú decides. Revisa siempre antes de usar.
            </p>
          </div>
        </div>
      </div>

      <AtajosPanel
        open={panelAtajos}
        onOpenChange={setPanelAtajos}
        onCambio={cargarAtajos}
      />
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex gap-1 py-1 align-middle text-muted-foreground">
      <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
    </span>
  );
}

function Dot({ delay = "0ms" }: { delay?: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current"
      style={{ animationDelay: delay }}
    />
  );
}
