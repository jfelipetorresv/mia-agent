// Mia · cliente HTTP del frontend. El token vive en localStorage.
// Todas las llamadas mandan Authorization: Bearer <token>. EventSource no admite headers,
// por eso el SSE se consume con fetch + ReadableStream (streamTurn).

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Error que VIENE del backend (con `detail` en lenguaje llano, §G). Distinguirlo
// de los errores de red del navegador ("Failed to fetch") permite a las pantallas
// mostrar el mensaje del backend sin arriesgarse a mostrar jerga técnica.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Mensaje mostrable al abogado (§G). Solo devuelve el texto del backend cuando
 * viene redactado en llano: si la respuesta no traía `detail`, el constructor de
 * ApiError arma "Error 500" como mensaje, y eso es jerga técnica que nunca debe
 * llegar a la pantalla. En ese caso —y ante un error de red— cae al fallback.
 */
export function plainMessage(err: unknown, fallback: string): string {
  const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
  return msg || fallback;
}

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
    // Este módulo no puede usar el hook de Next Router; el cierre de sesión debe
    // reiniciar el estado de toda la aplicación antes de cargar la ruta pública.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}`, ...extra } : { ...extra };
}

async function checkResponse(res: Response): Promise<void> {
  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError("Sesión expirada", 401);
  }
  if (!res.ok) {
    // El backend redacta `detail` en lenguaje llano para el abogado (§G):
    // si viene, se usa como mensaje del error en vez del código HTTP.
    let detail = "";
    try {
      const body = await res.clone().json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(detail || `Error ${res.status}`, res.status);
  }
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders(), cache: "no-store" });
  await checkResponse(res);
  return res.json();
}

/**
 * GET que NUNCA lanza: ante cualquier fallo devuelve el valor de respaldo.
 *
 * Es la pieza que permite que una pantalla compuesta por varias tarjetas
 * independientes (el Panel) se degrade tarjeta a tarjeta en vez de quedarse en
 * blanco entera porque una fuente no respondió. Devuelve `null` en el respaldo
 * cuando la tarjeta debe DESAPARECER, y nunca un dato inventado: una cifra
 * plausible es peor que una ausencia (§3 — ningún dato sin fuente).
 *
 * REGLA DEL RESPALDO — el `fallback` tiene que ser una AUSENCIA reconocible,
 * no una forma que la pantalla pueda leer como un dato. `null` siempre que la
 * pantalla deba poder preguntar "¿llegó esto?". Nunca `{}` para un resumen de
 * cifras ni `[]` para una lista de la que se afirme algo: `{}` se pinta como
 * ceros ("no aprobaste ningún borrador") y `[]` como "no tienes nada
 * pendiente" — dos afirmaciones falsas sobre el trabajo del despacho nacidas
 * de una petición que simplemente no respondió. `[]` solo vale cuando la
 * pantalla no concluye nada de que la lista venga vacía.
 */
export async function apiGetSoft<T>(path: string, fallback: T): Promise<T> {
  try {
    return await apiGet<T>(path);
  } catch {
    return fallback;
  }
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

// CP-Z1b: subida de un Blob con nombre de campo propio y campos extra — el
// dictado envía `audio` (WAV generado en el navegador) + `pulir`, y apiUpload
// tiene el campo "file" fijo (lo usan documentos y guías; no se toca su firma).
export async function apiUploadBlob<T = unknown>(
  path: string,
  field: string,
  blob: Blob,
  filename: string,
  extra: Record<string, string> = {},
): Promise<T> {
  const fd = new FormData();
  fd.append(field, blob, filename);
  for (const [k, v] of Object.entries(extra)) fd.append(k, v);
  const res = await fetch(`${API}${path}`, { method: "POST", headers: authHeaders(), body: fd });
  await checkResponse(res);
  return res.json();
}

// CP7: subida de VARIOS archivos en una sola petición (campo "files" repetido),
// para importar las guías de trabajo del despacho (POST /api/playbooks/import).
export async function apiUploadMany<T = unknown>(path: string, files: File[]): Promise<T> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(`${API}${path}`, { method: "POST", headers: authHeaders(), body: fd });
  await checkResponse(res);
  return res.json();
}

// Descarga un archivo autenticado (el header Authorization no viaja en un <a href>,
// así que se baja por fetch y se entrega como Blob al navegador).
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders(), cache: "no-store" });
  await checkResponse(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type SseHandler = (event: string, data: unknown) => void;

// Núcleo compartido: parsea el cuerpo de una respuesta SSE (event/data) obtenida
// por fetch — así podemos mandar el header Authorization (EventSource no lo admite).
async function consumeSse(res: Response, onEvent: SseHandler): Promise<void> {
  if (!res.body) throw new Error("Sin cuerpo en la respuesta");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // El servidor separa eventos con \r\n\r\n (así emite sse-starlette); el spec
    // SSE admite \r\n, \n o mezcla. Un separador partido entre chunks (p.ej. el
    // buffer termina en "\r\n\r") no matchea aún y espera al siguiente chunk.
    const blocks = buffer.split(/\r?\n\r?\n/);
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

// Consume un SSE por GET. Queda para warroom/stream y compat; el turno del asunto
// debe usar streamPost para que el mensaje no viaje en la URL.
export async function streamTurn(
  streamPath: string,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${streamPath}`, { headers: authHeaders(), signal, cache: "no-store" });
  await checkResponse(res);
  await consumeSse(res, onEvent);
}

// Consume un SSE por POST con cuerpo JSON — turno del asunto, chat del asistente,
// HITL y delegación: el texto no viaja en query string (historial/proxy logs).
export async function streamPost(
  streamPath: string,
  body: unknown,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${streamPath}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  await checkResponse(res);
  await consumeSse(res, onEvent);
}

/* ────────────────────────────────────────────────────────────────────────────
 * Clientes tipados de las fuentes que alimentan el Panel
 *
 * Estas cuatro fuentes ya existían en el servidor y estaban MAL EXPUESTAS: dos
 * no las llamaba nadie y dos se leían recortadas (el Panel declaraba 1 de los 6
 * campos del gasto y 4 de los ~15 del resumen). Se tipan aquí, junto al
 * transporte, para que la forma viva en UN sitio y la pantalla no vuelva a
 * inventar campos.
 *
 * Todas se consumen con `apiGetSoft`: si una falla, su tarjeta se degrada sola.
 * ──────────────────────────────────────────────────────────────────────────── */

/** Un paso del recorrido de puesta a punto. El servidor ya redacta `titulo` y
 *  `detalle` en lenguaje llano y resuelve `enlace`: la pantalla solo los pinta. */
export type SetupPaso = {
  id: string;
  titulo: string;
  estado: "listo" | "pendiente" | "omitido";
  detalle: string;
  accion: "automatica" | "guiada";
  enlace: string | null;
  guia: { que_es: string; para_que: string; como: string[] } | null;
};

export type SetupStatus = {
  pasos: SetupPaso[];
  secciones: { titulo: string; que_es: string; para_que: string }[];
  completados: number;
  total: number;
  siguiente: string | null;
  mensaje: string;
};

/** Salud de las guías de trabajo del despacho. Las tres claves llegan siempre,
 *  aunque valgan 0. `revisar` = guías con citas que hay que verificar. */
export type PlaybookHealth = { sano: number; revisar: number; sin_revisar: number };

/** Resumen del día de UN asunto. Determinista y sin modelo: sale de lo que hay
 *  en el expediente, así que ninguna línea es una afirmación generada. */
export type DailyItem = {
  ref: string;
  requiere_decision: boolean;
  origen: "pendiente" | "bandeja" | "bitacora";
  texto: string;
};

export type DailyBriefing = {
  matter_id: string;
  items: DailyItem[];
  requieren_decision: number;
  resumen: string;
};

/** Gasto de IA del mes. `monthly_budget_usd`/`remaining_usd` son `null` cuando
 *  el despacho no fijó tope (`unlimited`), y `null` NO es 0: no se pinta cifra. */
export type BudgetStatus = {
  monthly_budget_usd: number | null;
  spent_this_month_usd: number;
  reserved_usd: number;
  remaining_usd: number | null;
  over_budget: boolean;
  unlimited: boolean;
};

export const getSetupStatus = () => apiGetSoft<SetupStatus | null>("/api/setup/status", null);

export const getPlaybookHealth = () =>
  apiGetSoft<PlaybookHealth | null>("/api/playbooks/health/summary", null);

export const getBudget = () => apiGetSoft<BudgetStatus | null>("/api/policy/budget", null);

export const getMatterDaily = (matterId: string) =>
  apiGetSoft<DailyBriefing | null>(`/api/matters/${matterId}/daily`, null);
