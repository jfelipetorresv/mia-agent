// Mia · cliente HTTP del frontend. Token de desarrollo (#23) desde .env.local.
// Todas las llamadas mandan Authorization: Bearer <token>. EventSource no admite headers,
// por eso el SSE se consume con fetch + ReadableStream (streamTurn).

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_DEV_TOKEN || "";

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { Authorization: `Bearer ${TOKEN}`, ...extra };
}

export async function apiGet<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}

export async function apiSend<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}

export async function apiUpload<T = any>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API}${path}`, { method: "POST", headers: authHeaders(), body: fd });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}

export type SseHandler = (event: string, data: any) => void;

// Consume un SSE (event/data) sobre fetch para poder mandar el header Authorization.
export async function streamTurn(streamPath: string, onEvent: SseHandler): Promise<void> {
  const res = await fetch(`${API}${streamPath}`, { headers: authHeaders() });
  if (!res.body) return;
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
}

export const apiConfig = { hasToken: Boolean(TOKEN) };
