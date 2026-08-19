// Puente hacia la cáscara de escritorio (Tauri) vía el protocolo custom
// `mia-shell` (http://mia-shell.localhost). La pantalla de MIA corre en
// http://localhost:3100, que para Tauri v2 es un ORIGEN REMOTO sin IPC por
// diseño (hardening: window.__TAURI__ no se inyecta ahí). WebView2 intercepta
// estas peticiones EN PROCESO: no hay puerto TCP y solo funcionan dentro de
// la app de escritorio. En un navegador normal el fetch falla → se lanza
// DESKTOP_ONLY_MESSAGE, mismo comportamiento que el chequeo anterior de
// window.__TAURI__.

export const DESKTOP_ONLY_MESSAGE =
  "Este control está disponible en la aplicación de escritorio.";

const SHELL_BASE = "http://mia-shell.localhost";

type ShellReply = { ok: boolean; data?: unknown; error?: string };

export async function shellInvoke<T>(
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${SHELL_BASE}/${path}`, {
      method: "POST",
      // text/plain evita el preflight CORS; el handler de la cáscara parsea
      // el cuerpo como JSON de todas formas.
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify(body ?? {}),
    });
  } catch {
    // Navegador (dev) o cáscara ausente: el protocolo no existe.
    throw new Error(DESKTOP_ONLY_MESSAGE);
  }
  const reply = (await res.json().catch(() => null)) as ShellReply | null;
  if (!reply || !reply.ok) {
    throw new Error(reply?.error || "La operación no pudo completarse.");
  }
  return reply.data as T;
}
