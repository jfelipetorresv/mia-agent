// Mia · cliente HTTP del frontend. El token vive en localStorage.
// Todas las llamadas mandan Authorization: Bearer <token>. EventSource no admite headers,
// por eso el SSE se consume con fetch + ReadableStream (streamTurn).

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("mia_token");
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem("mia_token", token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem("mia_token");
}

function handleUnauthorized(): void {
  clearToken();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}`, ...extra } : { ...extra };
}

async function checkResponse(res: Response): Promise<void> {
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Sesión expirada");
  }
  if (!res.ok) throw new Error(`Error ${res.status}`);
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders(), cache: "no-store" });
  await checkResponse(res);
  return res.json();
}

export async function apiSend<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  await checkResponse(res);
  return res.json();
}

export async function apiUpload<T = unknown>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API}${path}`, { method: "POST", headers: authHeaders(), body: fd });
  await checkResponse(res);
  return res.json();
}

export type SseHandler = (event: string, data: unknown) => void;

// Consume un SSE (event/data) sobre fetch para poder mandar el header Authorization.
export async function streamTurn(
  streamPath: string,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${streamPath}`, { headers: authHeaders(), signal, cache: "no-store" });
  await checkResponse(res);
  if (!res.body) throw new Error("Sin cuerpo en la respuesta");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) {
        try {
          onEvent(event, JSON.parse(data));
        } catch {
          /* ignora líneas que no son JSON */
        }
      }
    }
  }
  // Procesa el bloque final si el stream cerró sin \n\n terminal.
  if (buffer.trim()) {
    let event = "message";
    let data = "";
    for (const line of buffer.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (data) {
      try {
        onEvent(event, JSON.parse(data));
      } catch {
        /* ignora */
      }
    }
  }
}

export const apiConfig = { hasToken: () => Boolean(getToken()) };
