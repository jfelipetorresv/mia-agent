"use client";

import { useEffect, useRef, useState } from "react";
import {
  Scale,
  Plus,
  Send,
  Sparkles,
  FolderOpen,
  BellRing,
  Settings2,
  MessagesSquare,
} from "lucide-react";
import { apiGet, streamPost, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Conversation = { id: string; title: string; updated_at: string };
type Role = "user" | "assistant";
type Message = { role: Role; content: string };

// Ejemplos que ENSEÑAN qué puede hacer Mia (empty state). Cada uno toca una
// capacidad real: sus asuntos, un recordatorio, la configuración y una consulta libre.
const EXAMPLES = [
  { icon: FolderOpen, text: "¿Qué asuntos tengo pendientes?" },
  { icon: BellRing, text: "Recuérdame llamar al juzgado mañana a las 9" },
  { icon: Settings2, text: "¿Qué me falta para terminar de configurar a Mia?" },
  { icon: Sparkles, text: "Explícame la caducidad de la acción contractual" },
];

function saludoDelDia(): string {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [typing, setTyping] = useState(false); // Mia "escribiendo" (typewriter activo)
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

  useEffect(() => {
    loadConversations();
    return () => {
      abortRef.current?.abort();
      if (typerRef.current) clearInterval(typerRef.current);
    };
  }, []);

  // Autoscroll al fondo mientras Mia responde o llega un mensaje nuevo.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  async function openConversation(id: string) {
    if (streaming) return;
    setActiveId(id);
    setStatus("");
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
              <div className="relative mb-6 animate-slide-up">
                <div className="absolute inset-0 rounded-3xl bg-primary/30 blur-2xl" aria-hidden />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-lg">
                  <Scale className="h-8 w-8" />
                </div>
              </div>
              <h1
                className="text-gradient-brand animate-slide-up text-3xl font-semibold tracking-tight"
                style={{ animationDelay: "60ms", animationFillMode: "backwards" }}
              >
                {saludoDelDia()}. Soy Mia.
              </h1>
              <p
                className="mt-3 max-w-md animate-slide-up text-muted-foreground"
                style={{ animationDelay: "120ms", animationFillMode: "backwards" }}
              >
                Pregúntame lo que necesites: tus asuntos, un recordatorio o una duda
                jurídica. Yo propongo, tú tienes la última palabra.
              </p>
              <div className="mt-10 grid w-full max-w-lg gap-3 sm:grid-cols-2">
                {EXAMPLES.map((ex, i) => (
                  <button
                    key={ex.text}
                    onClick={() => send(ex.text)}
                    className="group animate-slide-up rounded-xl border border-border bg-card/80 px-4 py-3.5 text-left text-sm text-card-foreground shadow-sm backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                    style={{ animationDelay: `${180 + i * 70}ms`, animationFillMode: "backwards" }}
                  >
                    <ex.icon className="mb-2 h-4 w-4 text-primary transition-transform duration-200 group-hover:scale-110" />
                    {ex.text}
                  </button>
                ))}
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
                      <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-sm">
                        <Scale className="h-4 w-4" />
                      </div>
                    </div>
                  ) : null}
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm"
                        : "max-w-[80%] whitespace-pre-wrap pt-1 font-serif text-[15px] leading-relaxed text-foreground"
                    }
                  >
                    {m.content ? (
                      <>
                        {m.content}
                        {typing && i === lastIdx ? (
                          <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-blink bg-primary" aria-hidden />
                        ) : null}
                      </>
                    ) : (
                      <ThinkingDots />
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
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
            <div className="flex items-end gap-2 rounded-2xl border border-input bg-card p-2 shadow-lg shadow-primary/5 transition-shadow focus-within:border-primary/40 focus-within:shadow-primary/10">
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
            <p className="mt-2 text-center text-xs text-muted-foreground/80">
              Mia propone; tú decides. Revisa siempre antes de usar.
            </p>
          </div>
        </div>
      </div>
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
