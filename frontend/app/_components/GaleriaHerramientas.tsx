"use client";

// GALERÍA DE HERRAMIENTAS — el reconocimiento a primera vista
// ===========================================================
//
// Bloque 3 del rediseño Luxury. Antes, "Conexiones" era una columna de tarjetas
// largas y grises: el abogado tenía que LEER para saber si su correo estaba
// conectado. Esta galería pone arriba lo que reconoce de un vistazo — el logo de
// Outlook, el de Obsidian, el de Claude — con un chip que dice la verdad del
// estado y un botón que lleva exactamente al sitio donde se hace.
//
// REGLA DURA DE ESTA PANTALLA: no se pinta una herramienta que el producto no
// tenga. Cada tarjeta de aquí abajo lleva, en su comentario, el endpoint real que
// le da el estado. Si una herramienta no es consultable, se dice lo que SÍ es
// cierto ("se configura aquí"), nunca un estado inventado. En particular:
//   · Google Drive SÍ aparece desde 2026-08-19 (decisión de Pipe): el permiso de
//     archivos existe ya para los dos proveedores (`features=mail,drive` en
//     MailboxSection compone Files.Read en Microsoft y drive.readonly en Google), y
//     su estado sale del MISMO campo `conexiones[].archivos` de /api/mailbox/status.
//     Mientras la instalación no tenga registrada la aplicación de Google, la tarjeta
//     lo dice con esas palabras en vez de ofrecer un botón que acabaría en error.
//   · Los "ayudantes externos" (Agent Hub) no llevan logo de marca: el backend los
//     nombra de forma neutra a propósito (agent_hub.py::CONNECTORS) y esta pantalla
//     no le pone una marca encima a un nombre que el backend decidió ocultar.
//
// Fuentes de verdad, todas ya existentes:
//   motores            → GET /api/welcome/status  (motor_detectado, faltan_llaves)
//   correo y archivos  → GET /api/mailbox/status  (conexiones[].proveedor/archivos)
//   espacio de notas   → GET /api/obsidian/status
//   NotebookLM         → GET /api/notebooklm/status
//   avisos por celular → GET /health              (capabilities.telegram)

import { useEffect, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import { Sparkles, FolderSearch, Send, BookOpen, Check, Copy } from "lucide-react";
import { apiGet } from "@/lib/api";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionTitle } from "@/app/_components/SectionTitle";
import { staggerStyle } from "@/lib/motion";
import { cn } from "@/lib/utils";

/* ─────────────────────────── Logotipos ───────────────────────────
 * SVG en línea, sin librerías nuevas ni assets remotos. Son marcas
 * reconocibles a 24px, no reproducciones exactas: lo que tiene que hacer el
 * dibujo es que el ojo diga "ese es mi correo" antes de leer el nombre.
 */

type LogoProps = { className?: string };

function LogoOutlook({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path fill="#0364B8" d="M23 6.5v11a1 1 0 0 1-1 1h-9v-13h9a1 1 0 0 1 1 1Z" />
      <path fill="#28A8EA" d="M23 7.4v10.1a1 1 0 0 1-1 1h-9v-6.2l10-4.9Z" />
      <path fill="#14447D" d="M1 4.2 12 2v20L1 19.8V4.2Z" />
      <ellipse cx="6.5" cy="12" rx="2.6" ry="3.4" fill="#fff" />
      <ellipse cx="6.5" cy="12" rx="1.2" ry="1.9" fill="#14447D" />
    </svg>
  );
}

function LogoOneDrive({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path
        fill="#0364B8"
        d="M9.4 6.3a5 5 0 0 1 8.4 1.9 4 4 0 0 1 3.6 4 4 4 0 0 1-4 4H6.5A4.2 4.2 0 0 1 6 7.9a5 5 0 0 1 3.4-1.6Z"
      />
      <path
        fill="#28A8EA"
        d="M6.5 16.2A4.2 4.2 0 0 1 6 7.9a5 5 0 0 1 2.6-1.5 6.4 6.4 0 0 0-1.7 4.3c0 2.2 1.1 4.2 2.8 5.5H6.5Z"
      />
    </svg>
  );
}

function LogoGmail({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path fill="#4285F4" d="M2 6.5A1.5 1.5 0 0 1 3.5 5H5v14H3.5A1.5 1.5 0 0 1 2 17.5v-11Z" />
      <path fill="#34A853" d="M19 5h1.5A1.5 1.5 0 0 1 22 6.5v11a1.5 1.5 0 0 1-1.5 1.5H19V5Z" />
      <path fill="#FBBC04" d="M5 5l7 5.3L19 5v3.4l-7 5.3-7-5.3V5Z" />
      <path fill="#EA4335" d="M5 5l7 5.3L19 5H5Z" />
      <path fill="#C5221F" d="M5 19V8.4l7 5.3 7-5.3V19H5Z" opacity=".08" />
    </svg>
  );
}

function LogoGoogleDrive({ className }: LogoProps) {
  // El triángulo tricolor de Drive: tres caras, tres colores de marca.
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path fill="#0066DA" d="M8.4 3.4h7.2l-3.6 6.3-3.6 6.2L4.8 9.6 8.4 3.4Z" opacity=".9" />
      <path fill="#00AC47" d="M4.8 9.6 8.4 15.8h11.5l-3.6 4.8H6.9L1.9 14.4l2.9-4.8Z" />
      <path fill="#FFBA00" d="M15.6 3.4 22.1 14.4l-2.9 4.9-5.8-9.6 2.2-6.3Z" />
      <path fill="#EA4335" d="M12 9.7 8.4 15.8h7.2L12 9.7Z" opacity=".35" />
    </svg>
  );
}

function LogoObsidian({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path fill="#7C3AED" d="m13.6 2 5.6 6.6-3.9 12.6-8.5-2.2L4 9.9 13.6 2Z" />
      <path fill="#A78BFA" d="m13.6 2 1.7 7.5-5.5 11.5-3-2.2L4 9.9 13.6 2Z" />
      <path fill="#C4B5FD" d="m15.3 9.5 3.9-.9-3.9 12.6-5.5-.7 5.5-11Z" />
    </svg>
  );
}

function LogoClaude({ className }: LogoProps) {
  // El asterisco de Claude, simplificado a seis brazos.
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <g stroke="#D97757" strokeWidth="2.4" strokeLinecap="round">
        <path d="M12 4v16M5.1 8l13.8 8M18.9 8 5.1 16" />
      </g>
    </svg>
  );
}

function LogoCodex({ className }: LogoProps) {
  // El nudo hexagonal de OpenAI, reducido a un trazo legible a 24px.
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
        d="M12 3.2 19.2 7.4v9.2L12 20.8 4.8 16.6V7.4L12 3.2Z"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
        d="M12 7.6 15.8 9.8v4.4L12 16.4l-3.8-2.2V9.8L12 7.6Z"
      />
    </svg>
  );
}

function LogoOllama({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M7 9c0-2.6.9-4.6 1.9-4.6S10.8 6.4 10.8 9M13.2 9c0-2.6.9-4.6 1.9-4.6S17 6.4 17 9" />
        <path d="M5.6 14.2c0-3.2 2.9-5.4 6.4-5.4s6.4 2.2 6.4 5.4c0 1.4-.5 2.4-1.2 3.1.4.9.2 1.9-.6 2.4-.8.5-1.8.2-2.4-.5-.7.2-1.4.3-2.2.3s-1.5-.1-2.2-.3c-.6.7-1.6 1-2.4.5-.8-.5-1-1.5-.6-2.4-.7-.7-1.2-1.7-1.2-3.1Z" />
      </g>
    </svg>
  );
}

function LogoOpenRouter({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M3 12h4l3-4h4M7 12l3 4h4" />
        <circle cx="18.5" cy="8" r="2.2" />
        <circle cx="18.5" cy="16" r="2.2" />
      </g>
    </svg>
  );
}

function LogoNotebookLM({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M5 4.5h11a2 2 0 0 1 2 2v13a1.5 1.5 0 0 0-1.5-1.5H5v-13Z" />
        <path d="M5 4.5A1.5 1.5 0 0 0 3.5 6v13A1.5 1.5 0 0 1 5 17.5" />
        <path d="M8.5 8.5h6M8.5 12h6" />
      </g>
    </svg>
  );
}

function LogoTelegram({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <circle cx="12" cy="12" r="10" fill="#2AABEE" />
      <path
        fill="#fff"
        d="M6.4 11.9 16 8.1c.5-.2.9.1.7.8l-1.6 7.7c-.1.6-.5.7-1 .4l-2.7-2-1.3 1.3c-.2.2-.3.3-.6.3l.2-2.9 5.2-4.7c.2-.2 0-.3-.3-.1L8 11.2l-2.6-.8c-.6-.2-.6-.6.1-.9Z"
      />
    </svg>
  );
}

/* ────────────────────── El chip de estado ────────────────────── */

type Tono = "conectada" | "detectada" | "pendiente" | "ausente";

// Un 12 % de tinte sobre el fondo oscuro del pack no se veía: el chip se leía
// como texto suelto y perdía su papel de ESTADO. El anillo interior del propio
// color es lo que le devuelve el borde en los dos temas sin inventar un token.
const TONO_CLASS: Record<Tono, string> = {
  conectada: "bg-success/15 text-success ring-1 ring-inset ring-success/30",
  detectada: "bg-primary/15 text-primary ring-1 ring-inset ring-primary/30",
  pendiente: "bg-cta/15 text-cta-strong ring-1 ring-inset ring-cta/35",
  ausente: "bg-muted text-muted-foreground ring-1 ring-inset ring-border",
};

function Chip({ tono, children }: { tono: Tono; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-meta font-medium",
        TONO_CLASS[tono]
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          tono === "conectada"
            ? "bg-success"
            : tono === "detectada"
              ? "bg-primary"
              : tono === "pendiente"
                ? "bg-cta-strong"
                : "bg-muted-foreground/60"
        )}
      />
      {children}
    </span>
  );
}

/* ────────────────────── La tarjeta de herramienta ────────────────────── */

type Herramienta = {
  id: string;
  nombre: string;
  /** Qué gana el abogado al conectarla. Una línea, en su idioma. */
  gana: string;
  logo: (p: LogoProps) => ReactNode;
  tono: Tono;
  estado: string;
  /** Ancla de la tarjeta detallada donde SÍ se hace la acción. */
  ancla?: string;
  accion?: string;
  /**
   * Acción SECUNDARIA de la tarjeta, para los estados en los que no hay nada que
   * pulsar porque falta un paso de instalación. Hoy la usa el registro de la
   * aplicación de Google: en vez de dejar al abogado con una frase que describe un
   * bloqueo, la tarjeta abre la guía que lo levanta.
   */
  guia?: { texto: string; abrir: () => void };
};

function ToolCard({ h, delay }: { h: Herramienta; delay: number }) {
  const Logo = h.logo;
  return (
    <Card
      variant="raised"
      padding="md"
      className="flex h-full animate-slide-up flex-col bg-card/80 backdrop-blur-md"
      style={staggerStyle(delay)}
    >
      <div className="flex items-start gap-3">
        {/* Mismo bajo relieve que NeuIcon, pero con el logo de marca dentro: el
            vocabulario del sistema no cambia porque el glifo sea una marca. */}
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted/50 text-muted-foreground shadow-neu-sunken">
          <Logo className="h-[1.375rem] w-[1.375rem]" />
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-section">{h.nombre}</h4>
          <p className="mt-1 text-pretty text-body text-muted-foreground">{h.gana}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <Chip tono={h.tono}>{h.estado}</Chip>
        {h.ancla && h.accion ? (
          <a
            href={`#${h.ancla}`}
            className="rounded-md px-2 py-1 text-meta font-medium text-primary underline-offset-4 transition-colors hover:bg-accent hover:underline"
          >
            {h.accion}
          </a>
        ) : h.guia ? (
          <button
            type="button"
            onClick={h.guia.abrir}
            className="rounded-md px-2 py-1 text-meta font-medium text-primary underline-offset-4 transition-colors hover:bg-accent hover:underline"
          >
            {h.guia.texto}
          </button>
        ) : null}
      </div>
    </Card>
  );
}

function Grupo({
  icon,
  title,
  hint,
  items,
  offset,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  hint: string;
  items: Herramienta[];
  offset: number;
}) {
  if (!items.length) return null;
  return (
    <section>
      <SectionTitle icon={icon} title={title} hint={hint} level="h3" className="mb-3" />
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((h, i) => (
          <ToolCard key={h.id} h={h} delay={offset + i} />
        ))}
      </div>
    </section>
  );
}

/* ────────────────────── La guía de registro de Google ──────────────────────
 *
 * Google Drive y Gmail no se conectan con un botón mientras la INSTALACIÓN no tenga
 * registrada su propia aplicación en Google Cloud. Ese registro lo hace una vez quien
 * instala Mia, y hasta 2026-08-20 la tarjeta se limitaba a decir que faltaba: un
 * bloqueo enunciado sin salida. Esta guía es la salida.
 *
 * FUENTE TÉCNICA (no se inventa nada aquí): el flujo real de
 * `backend/mia/connectors/mailbox/oauth.py` — `drive.readonly` para Drive,
 * `gmail.metadata` / `gmail.readonly` y `calendar.readonly` para correo y agenda — y la
 * URI de retorno de la instalación, que viaja desde `config.MAILBOX_OAUTH_REDIRECT_URI`
 * por `/api/mailbox/status` y NO se cablea en esta pantalla.
 *
 * Los nombres de la consola de Google van en su forma literal: quien sigue la guía los
 * va a leer tal cual en la pantalla que tiene delante.
 */

function BotonCopiar({ valor }: { valor: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        // `navigator.clipboard` no existe en contextos no seguros. Si no está, el campo
        // sigue siendo seleccionable a mano: el botón no promete lo que no puede cumplir.
        void navigator.clipboard?.writeText(valor).then(
          () => {
            setCopiado(true);
            window.setTimeout(() => setCopiado(false), 2000);
          },
          () => setCopiado(false)
        );
      }}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2 py-1 text-meta font-medium text-foreground transition-colors hover:bg-accent"
    >
      {copiado ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      {copiado ? "Copiada" : "Copiar"}
    </button>
  );
}

function Paso({ n, titulo, children }: { n: number; titulo: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted/60 text-meta font-semibold text-foreground shadow-neu-sunken">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-label font-medium text-foreground">{titulo}</p>
        <div className="mt-1 space-y-2 text-pretty text-body text-muted-foreground">{children}</div>
      </div>
    </li>
  );
}

function GuiaRegistroGoogle({
  abierta,
  onClose,
  uriRetorno,
}: {
  abierta: boolean;
  onClose: () => void;
  uriRetorno: string;
}) {
  return (
    <Dialog open={abierta} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Registrar la aplicación de Google</DialogTitle>
          <DialogDescription>
            Es un trámite único de esta instalación y lo hace quien instaló Mia. Al terminar,
            el despacho conecta sus cuentas de Google con un botón. Toma unos quince minutos y
            no tiene costo.
          </DialogDescription>
        </DialogHeader>

        <ol className="space-y-4">
          <Paso n={1} titulo="Abre un proyecto en Google Cloud Console y habilita las APIs">
            <p>
              Entra a console.cloud.google.com con la cuenta de Google del despacho. Crea un
              proyecto nuevo o abre uno existente. En <b>APIs y servicios → Biblioteca</b>,
              habilita <b>Google Drive API</b>. Si el despacho va a usar también correo y
              agenda, habilita en el mismo sitio <b>Gmail API</b> y <b>Google Calendar API</b>.
            </p>
          </Paso>

          <Paso n={2} titulo="Configura la pantalla de consentimiento de OAuth">
            <p>
              En <b>APIs y servicios → Pantalla de consentimiento de OAuth</b>, elige el tipo{" "}
              <b>Externo</b> y escribe el nombre de la aplicación y el correo de contacto.
            </p>
            <p>
              En el paso de permisos añade los de <b>solo lectura</b> que Mia usa:{" "}
              <code className="break-all rounded bg-muted/60 px-1 py-0.5 text-meta">
                .../auth/drive.readonly
              </code>{" "}
              para los archivos y, si habilitaste correo y agenda,{" "}
              <code className="break-all rounded bg-muted/60 px-1 py-0.5 text-meta">
                .../auth/gmail.metadata
              </code>{" "}
              y{" "}
              <code className="break-all rounded bg-muted/60 px-1 py-0.5 text-meta">
                .../auth/calendar.readonly
              </code>
              . Mia lee; no escribe ni borra nada en las cuentas del despacho.
            </p>
            <p>
              En <b>Usuarios de prueba</b> agrega su propia cuenta de Google y las de los
              abogados que vayan a conectarse. La aplicación queda en estado <b>Prueba</b>, y en
              ese estado funciona de inmediato para esas cuentas: no hace falta esperar la
              verificación de Google.
            </p>
          </Paso>

          <Paso n={3} titulo="Crea la credencial de tipo «Aplicación web»">
            <p>
              En <b>APIs y servicios → Credenciales</b>, elige <b>Crear credenciales → ID de
              cliente de OAuth</b> y como tipo de aplicación, <b>Aplicación web</b>.
            </p>
            <p>
              En <b>URIs de redireccionamiento autorizados</b> pega esta dirección exacta de
              esta instalación. Un carácter de diferencia hace que Google rechace la conexión:
            </p>
            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2">
              <code className="min-w-0 flex-1 break-all text-meta text-foreground">
                {uriRetorno}
              </code>
              <BotonCopiar valor={uriRetorno} />
            </div>
          </Paso>

          <Paso n={4} titulo="Pega las dos claves en el archivo .env de Mia y reinicia">
            <p>
              Google muestra un <b>ID de cliente</b> y un <b>Secreto de cliente</b>. Cópialos al
              archivo <code className="rounded bg-muted/60 px-1 py-0.5 text-meta">.env</code> de
              Mia, en estas dos líneas:
            </p>
            <pre className="overflow-x-auto rounded-lg border border-border bg-muted/40 px-3 py-2 text-meta text-foreground">
              GOOGLE_OAUTH_CLIENT_ID=…{"\n"}GOOGLE_OAUTH_CLIENT_SECRET=…
            </pre>
            <p>Guarda el archivo y reinicia Mia: las claves se leen al arrancar.</p>
          </Paso>

          <Paso n={5} titulo="Comprueba que quedó">
            <p>
              Vuelve a esta pantalla. Esta tarjeta pasa sola a <b>Sin conectar</b> y aparece el
              botón <b>Conectar</b>. Ese es el aviso de que el registro quedó bien hecho.
            </p>
          </Paso>
        </ol>

        <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-pretty text-meta text-muted-foreground">
          Gmail y Google Calendar usan esta misma aplicación de Google: con este registro
          quedan habilitados los tres, sin repetir el trámite.
        </p>
      </DialogContent>
    </Dialog>
  );
}

/* ────────────────────── Estados que llegan del backend ────────────────────── */

type MotorDetectado = { claude?: boolean; codex?: boolean; ollama?: boolean };
/** Los tres hechos separados de un motor local: estar instalado, tener sesión y estar
 *  habilitado por la política de este modo de Mia. Mezclarlos producía una frase falsa
 *  sobre el equipo del abogado (defecto D1, 2026-08-20). */
type MotorEstado = {
  instalada?: boolean;
  sesion?: boolean;
  habilitada_por_politica?: boolean;
  disponible?: boolean;
  motivo?: "no_instalada" | "sin_sesion" | "no_habilitada_en_este_modo" | "disponible";
};
type WelcomeStatus = {
  motor_detectado?: MotorDetectado;
  motor_estado?: { codex?: MotorEstado };
  faltan_llaves?: { busqueda?: boolean; respaldo?: boolean; openrouter?: boolean };
};
type Conexion = { proveedor: string; conectado: boolean; archivos?: boolean; disponible?: boolean };
type MailboxStatus = {
  conexiones?: Conexion[];
  /** URI de retorno de ESTA instalación (config.MAILBOX_OAUTH_REDIRECT_URI). */
  uri_de_retorno?: string;
};
type ObsidianStatus = { installed: boolean; vault_configured: boolean };
type NbStatus = { estado: string; instalado: boolean; autenticado: boolean };
type HealthCaps = { capabilities?: { telegram?: { available?: boolean; reason?: string } } };

export default function GaleriaHerramientas() {
  const [welcome, setWelcome] = useState<WelcomeStatus | null>(null);
  const [mailbox, setMailbox] = useState<MailboxStatus | null>(null);
  const [obsidian, setObsidian] = useState<ObsidianStatus | null>(null);
  const [nb, setNb] = useState<NbStatus | null>(null);
  const [caps, setCaps] = useState<HealthCaps["capabilities"] | null>(null);
  const [listo, setListo] = useState(false);
  const [guiaGoogle, setGuiaGoogle] = useState(false);

  useEffect(() => {
    let vivo = true;
    Promise.allSettled([
      apiGet<WelcomeStatus>("/api/welcome/status"),
      apiGet<MailboxStatus>("/api/mailbox/status"),
      apiGet<ObsidianStatus>("/api/obsidian/status"),
      apiGet<NbStatus>("/api/notebooklm/status"),
      apiGet<HealthCaps>("/health"),
    ]).then(([w, m, o, n, h]) => {
      if (!vivo) return;
      if (w.status === "fulfilled") setWelcome(w.value);
      if (m.status === "fulfilled") setMailbox(m.value);
      if (o.status === "fulfilled") setObsidian(o.value);
      if (n.status === "fulfilled") setNb(n.value);
      if (h.status === "fulfilled") setCaps(h.value.capabilities || null);
      setListo(true);
    });
    return () => {
      vivo = false;
    };
  }, []);

  if (!listo) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  const motor = welcome?.motor_detectado || {};
  // Si el backend es anterior a 2026-08-20 no trae `motor_estado`: sin ese dato no se
  // afirma nada sobre el equipo más allá de lo que `motor_detectado` ya dice.
  const codexEstado: MotorEstado = welcome?.motor_estado?.codex || {};
  const conexion = (p: string) => (mailbox?.conexiones || []).find((c) => c.proveedor === p);
  const ms = conexion("microsoft");
  const google = conexion("google");
  // El registro de la app de Google es UN trámite para Gmail, Calendar y Drive (misma
  // aplicación OAuth), así que las dos tarjetas afectadas abren la MISMA guía.
  const guiaRegistro = { texto: "Ver los pasos", abrir: () => setGuiaGoogle(true) };
  // Si el backend no trajo la URI (API anterior a 2026-08-20), se cae al MISMO valor de
  // fábrica que usa config.py cuando el .env no fija MAILBOX_OAUTH_REDIRECT_URI: no es una
  // dirección inventada, es el default declarado del producto.
  const uriRetorno = mailbox?.uri_de_retorno || "http://localhost:8000/api/mailbox/oauth/callback";

  // ── El cerebro: qué motores de IA reconoce este equipo.
  // Verdad: GET /api/welcome/status → motor_detectado (welcome.py, shutil.which).
  const cerebro: Herramienta[] = [
    {
      id: "claude",
      nombre: "Claude Code",
      gana: "Mia razona con la suscripción de Claude que ya pagas, sin costo por consulta.",
      logo: LogoClaude,
      ...(motor.claude
        ? { tono: "detectada" as Tono, estado: "Detectada en este equipo", ancla: "conector-motor", accion: "Usarla" }
        : { tono: "ausente" as Tono, estado: "No está instalada en este equipo" }),
    },
    {
      id: "codex",
      nombre: "Codex",
      gana: "Delega a Codex el análisis pesado sin que salga nada del expediente.",
      logo: LogoCodex,
      ...(codexEstado.motivo === "disponible" || (motor.codex && !codexEstado.motivo)
        ? { tono: "detectada" as Tono, estado: "Detectada e iniciada", ancla: "conector-motor", accion: "Usarla" }
        : codexEstado.motivo === "sin_sesion"
          ? {
              tono: "pendiente" as Tono,
              estado: "Está instalada en este equipo, pero no has iniciado sesión en ella",
            }
          : codexEstado.motivo === "no_habilitada_en_este_modo"
            ? {
                tono: "pendiente" as Tono,
                estado: "Está instalada, pero este modo de Mia no la usa",
              }
            : codexEstado.motivo === "no_instalada"
              ? { tono: "ausente" as Tono, estado: "No está instalada en este equipo" }
              : {
                  // Sin `motor_estado` no hay hecho comprobado: se dice lo único cierto.
                  tono: "ausente" as Tono,
                  estado: "Mia no la está usando como motor en este equipo",
                }),
    },
    {
      id: "ollama",
      nombre: "Ollama",
      gana: "El modo en el que nada sale de tu computador, ni siquiera el texto.",
      logo: LogoOllama,
      ...(motor.ollama
        ? { tono: "detectada" as Tono, estado: "Detectada en este equipo", ancla: "conector-motor", accion: "Usarla" }
        : { tono: "ausente" as Tono, estado: "No está instalada en este equipo" }),
    },
    {
      id: "openrouter",
      nombre: "OpenRouter",
      gana: "Una sola clave para varios modelos de nube cuando quieras compararlos.",
      logo: LogoOpenRouter,
      ...(welcome?.faltan_llaves?.openrouter === false
        ? { tono: "conectada" as Tono, estado: "Clave guardada", ancla: "conector-motor", accion: "Usarla" }
        : { tono: "pendiente" as Tono, estado: "Falta guardar la clave", ancla: "conector-motor", accion: "Configurar" }),
    },
  ];

  // ── Correo y archivos. Verdad: GET /api/mailbox/status.
  // Los cuatro estados salen de conexiones[].conectado / .archivos / .disponible.
  const oficina: Herramienta[] = [
    {
      id: "microsoft",
      nombre: "Microsoft 365 · Outlook",
      gana: "Mia vigila los términos que llegan por correo y avisa antes de que venzan.",
      logo: LogoOutlook,
      ...(ms?.conectado
        ? { tono: "conectada" as Tono, estado: "Conectada", ancla: "conector-correo", accion: "Administrar" }
        : ms?.disponible === false
          ? { tono: "ausente" as Tono, estado: "Esta instalación todavía no tiene registrada la aplicación de Microsoft" }
          : { tono: "pendiente" as Tono, estado: "Sin conectar", ancla: "conector-correo", accion: "Conectar" }),
    },
    {
      id: "onedrive",
      nombre: "OneDrive",
      gana: "Vincula carpetas de la nube para que Mia lea expedientes sin bajarlos.",
      logo: LogoOneDrive,
      ...(ms?.conectado && ms?.archivos
        ? { tono: "conectada" as Tono, estado: "Con permiso de archivos", ancla: "conector-correo", accion: "Administrar" }
        : ms?.conectado
          ? { tono: "pendiente" as Tono, estado: "Falta el permiso de archivos", ancla: "conector-correo", accion: "Añadir permiso" }
          : { tono: "ausente" as Tono, estado: "Llega con Microsoft 365: conéctalo primero", ancla: "conector-correo", accion: "Ir a Microsoft" }),
    },
    {
      id: "google",
      nombre: "Gmail · Google Workspace",
      gana: "Lo mismo que Outlook, si el despacho trabaja con Google.",
      logo: LogoGmail,
      ...(google?.conectado
        ? { tono: "conectada" as Tono, estado: "Conectada", ancla: "conector-correo", accion: "Administrar" }
        : google?.disponible === false
          ? {
              tono: "ausente" as Tono,
              estado: "Esta instalación todavía no tiene registrada la aplicación de Google",
              guia: guiaRegistro,
            }
          : { tono: "pendiente" as Tono, estado: "Sin conectar", ancla: "conector-correo", accion: "Conectar" }),
    },
    {
      id: "google-drive",
      nombre: "Google Drive",
      gana: "Vincula carpetas de Google Drive para que Mia lea expedientes sin bajarlos.",
      logo: LogoGoogleDrive,
      ...(google?.conectado && google?.archivos
        ? { tono: "conectada" as Tono, estado: "Con permiso de archivos", ancla: "conector-correo", accion: "Administrar" }
        : google?.conectado
          ? { tono: "pendiente" as Tono, estado: "Falta el permiso de archivos", ancla: "conector-correo", accion: "Añadir permiso" }
          : google?.disponible === false
            ? {
                tono: "ausente" as Tono,
                estado: "Esta instalación todavía no tiene registrada la aplicación de Google",
                guia: guiaRegistro,
              }
            : { tono: "ausente" as Tono, estado: "Llega con Google Workspace: conéctalo primero", ancla: "conector-correo", accion: "Ir a Google" }),
    },
  ];

  // ── Notas y conocimiento. Verdad: /api/obsidian/status y /api/notebooklm/status.
  const notas: Herramienta[] = [
    {
      id: "obsidian",
      nombre: "Obsidian",
      gana: "Mia lee y organiza las notas y el criterio que el despacho ya escribió.",
      logo: LogoObsidian,
      ...(obsidian?.installed && obsidian?.vault_configured
        ? { tono: "conectada" as Tono, estado: "Conectada", ancla: "conector-notas", accion: "Administrar" }
        : obsidian?.installed
          ? { tono: "detectada" as Tono, estado: "Instalada — falta indicarle la carpeta", ancla: "conector-notas", accion: "Elegir carpeta" }
          : { tono: "pendiente" as Tono, estado: "No está instalada — Mia puede instalarla", ancla: "conector-notas", accion: "Instalar" }),
    },
    {
      id: "notebooklm",
      nombre: "NotebookLM",
      gana: "Mia consulta lo que tú ya cargaste en tu propio NotebookLM.",
      logo: LogoNotebookLM,
      ...(nb?.estado === "conectado"
        ? { tono: "conectada" as Tono, estado: "Conectada", ancla: "conector-notebooklm", accion: "Administrar" }
        : nb?.instalado
          ? { tono: "detectada" as Tono, estado: "Instalada — falta iniciar sesión", ancla: "conector-notebooklm", accion: "Conectar cuenta" }
          : { tono: "pendiente" as Tono, estado: "No está instalada — Mia puede instalarla", ancla: "conector-notebooklm", accion: "Instalar" }),
    },
  ];

  // ── Avisos. Verdad: GET /health → capabilities.telegram (razón honesta incluida).
  const avisos: Herramienta[] = [
    {
      id: "telegram",
      nombre: "Telegram",
      gana: "Pídele ayuda a Mia desde el celular y recibe sus avisos fuera del despacho.",
      logo: LogoTelegram,
      ...(caps?.telegram?.available
        ? { tono: "conectada" as Tono, estado: "Puente listo", ancla: "conector-capacidades", accion: "Ver detalle" }
        : {
            tono: "ausente" as Tono,
            estado: caps?.telegram?.reason || "Sin configurar en esta instalación",
            ancla: "conector-capacidades",
            accion: "Ver detalle",
          }),
    },
  ];

  return (
    <div className="space-y-section">
      <Grupo
        icon={Sparkles}
        title="El motor con el que piensa Mia"
        hint="Es lo que hace el trabajo de fondo. Con uno basta; tener varios solo te da alternativas."
        items={cerebro}
        offset={0}
      />
      <Grupo
        icon={FolderSearch}
        title="Correo y archivos del despacho"
        hint="De aquí sale lo que Mia vigila: los términos que llegan y los expedientes que lee."
        items={oficina}
        offset={4}
      />
      <Grupo
        icon={BookOpen}
        title="Notas y conocimiento"
        hint="Lo que el despacho ya escribió. Mia lo usa como criterio propio, no como una búsqueda cualquiera."
        items={notas}
        offset={7}
      />
      <Grupo
        icon={Send}
        title="Avisos fuera del despacho"
        hint="Para enterarte de un término aunque no estés frente al computador."
        items={avisos}
        offset={9}
      />
      <GuiaRegistroGoogle
        abierta={guiaGoogle}
        onClose={() => setGuiaGoogle(false)}
        uriRetorno={uriRetorno}
      />
    </div>
  );
}
