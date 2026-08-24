"use client";

// Activar MIA — paso 2 del viaje de bienvenida (F3), rediseñado en el bloque D4
// («un solo motor, claves entendibles», bitácora UX 2026-08-19, puntos 2-4):
//
//   · UN paso de motor: Mia detecta qué hay instalado en el equipo (Claude Code /
//     Codex / Ollama), PRESELECCIONA el detectado y el abogado confirma o cambia.
//     OpenRouter dejó de ser una tarjeta hermana: es un respaldo con sección propia.
//   · UNA pantalla de claves: solo las que aplican al motor elegido, cada una con
//     el enunciado de qué habilita y qué pasa si se omite. Lo imprescindible se
//     dice como requisito, no como consejo.
//   · OpenRouter explicado de verdad: qué es, que solo entra cuando el motor
//     principal falla, que el gasto lo paga el abogado y que implica enviar el
//     trabajo a un servicio externo. `allow_openrouter` solo viaja cuando el
//     abogado marca el consentimiento de forma expresa — nunca como efecto
//     colateral de pegar una clave.
//
// Todo en lenguaje llano (§G): NUNCA se muestra "API key", "Voyage", "Anthropic",
// "token", "endpoint", "modelo" ni "LLM". OpenRouter sí se nombra: es la cuenta
// que el abogado mismo crea y carga.
//
// Consumo de infraestructura visual: WelcomeShell + WelcomeProgress (current=1),
// StepTransition entre sub-pasos, Stagger/WelcomeField, MiaLine y NotaMia.

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Cloud,
  Cpu,
  Loader2,
  ShieldAlert,
  Sparkles,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  WelcomeShell,
  WelcomeProgress,
  StepTransition,
  Stagger,
  StaggerItem,
  WelcomeField,
  MiaLine,
  JOURNEY_STEPS,
} from "@/app/_welcome";
import { NotaMia } from "@/app/_components/NotaMia";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { shellInvoke } from "@/lib/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// ── Contratos backend (welcome) ────────────────────────────────────────────
type Politica = "quality_adaptive" | "suscripcion" | "codex" | "nube" | "soberano" | "openrouter";

// Los tres hechos separados que sirve el backend para Codex (commit d0aa95b):
// instalada (hecho del equipo) · sesion (hecho de la cuenta) · habilitada por la
// política de este modo (decisión de Mia). Nunca se mezclan en una sola frase.
interface CodexEstado {
  instalada: boolean;
  sesion: boolean;
  habilitada_por_politica: boolean;
  disponible: boolean;
  motivo: string;
}

interface WelcomeStatus {
  instalado: boolean;
  hay_usuario: boolean;
  faltan_llaves: { busqueda: boolean; respaldo: boolean; openrouter: boolean };
  onboarding_completo: boolean;
  motor_detectado: { claude: boolean; codex: boolean; ollama: boolean };
  motor_estado?: { codex?: CodexEstado };
  politica: Politica;
}

interface TestResult {
  ok: boolean;
  motivo?: string;
}

interface KeysResult {
  guardado: Record<string, unknown>;
  mensaje: string;
  aviso: string | null;
}

type TestState = "idle" | "testing" | "ok" | "error";

// Los pasos del viaje (la constelación de progreso, "Activar" = índice 1) viven en
// `_welcome/WelcomeProgress` como fuente única (JOURNEY_STEPS): se importan, no se duplican.

// Mensaje amable por defecto cuando el backend no da un motivo en llano.
const GENERIC_TEST_ERROR = "No pude usar esa clave. Revísala y vuelve a intentarlo.";
const GENERIC_TEST_UNAVAILABLE = "No pude comprobar la clave en este momento. Puedes intentarlo de nuevo.";

// Extrae el mensaje en llano del backend (§G): solo se muestra un ApiError con
// `detail` redactado para el abogado; nunca un error de red en crudo.
function plainMessage(err: unknown, porDefecto: string): string {
  const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
  return msg || porDefecto;
}

// ── Preselección del motor (D4): lo detectado manda ─────────────────────────
// Regla: si la política ya guardada corresponde a un motor presente en el equipo
// (o no depende del equipo, como "nube"), se respeta; si no, se preselecciona el
// motor DETECTADO en orden de preferencia (Claude Code → Codex → Ollama → nube).
// Detectar no habilita (el backend lo repite): esto solo evita que el abogado
// tenga que adivinar lo que Mia ya sabe.
function preseleccionMotor(s: WelcomeStatus): Politica {
  const d = s.motor_detectado;
  const p = s.politica ?? "quality_adaptive";
  if ((p === "quality_adaptive" || p === "suscripcion") && d.claude) return p;
  if (p === "codex" && d.codex) return p;
  if (p === "soberano" && d.ollama) return p;
  if (p === "nube" || p === "openrouter") return p;
  if (d.claude) return "quality_adaptive";
  if (d.codex) return "codex";
  if (d.ollama) return "soberano";
  return "nube";
}

// Etiqueta honesta de Codex a partir de los tres hechos separados. Regla dura:
// jamás decir "no está instalada" cuando sí lo está — el primer obstáculo real
// es el que se nombra (instalar → habilitar → iniciar sesión).
function etiquetaCodex(s: WelcomeStatus): string | undefined {
  const e = s.motor_estado?.codex;
  if (!e) {
    return s.motor_detectado.codex ? "Ya detecté Codex en este equipo." : undefined;
  }
  if (!e.instalada) return undefined;
  if (!e.habilitada_por_politica) {
    return "Codex está instalado en este equipo, pero esta instalación no lo habilita.";
  }
  if (!e.sesion) {
    return "Ya detecté Codex en este equipo. Su sesión no está iniciada; te lo indico al primer uso.";
  }
  return "Ya detecté Codex en este equipo, con la sesión iniciada.";
}

// ── Hook: validación en vivo de una clave (con debounce y guardia de carrera) ─
function useKeyValidation(tipo: "busqueda" | "respaldo" | "openrouter") {
  const [value, setValue] = React.useState("");
  const [state, setState] = React.useState<TestState>("idle");
  const [motivo, setMotivo] = React.useState("");
  // Contador para descartar respuestas obsoletas (si el abogado sigue tecleando).
  const reqRef = React.useRef(0);
  // Timer del debounce en curso: se guarda para poder CANCELARLO cuando el abogado
  // fuerza la comprobación con Enter, y así no disparar dos POST reales (M2).
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = React.useCallback(
    async (clave: string) => {
      const trimmed = clave.trim();
      if (!trimmed) {
        setState("idle");
        setMotivo("");
        return;
      }
      const id = ++reqRef.current;
      setState("testing");
      setMotivo("");
      try {
        const res = await apiSend<TestResult>("POST", "/api/welcome/keys/test", {
          tipo,
          clave: trimmed,
        });
        if (id !== reqRef.current) return; // respuesta obsoleta
        if (res.ok) {
          setState("ok");
          setMotivo("");
        } else {
          setState("error");
          setMotivo(res.motivo || GENERIC_TEST_ERROR);
        }
      } catch (err) {
        if (id !== reqRef.current) return;
        setState("error");
        setMotivo(plainMessage(err, GENERIC_TEST_UNAVAILABLE));
      }
    },
    [tipo],
  );

  // Debounce: al dejar de teclear ~700ms, comprueba en vivo. Mientras tanto,
  // muestra el spinner (state "testing"). Si el campo queda vacío, vuelve a idle.
  React.useEffect(() => {
    if (!value.trim()) {
      reqRef.current++; // invalida cualquier comprobación pendiente
      setState("idle");
      setMotivo("");
      return;
    }
    setState("testing");
    const t = setTimeout(() => run(value), 700);
    timerRef.current = t;
    return () => clearTimeout(t);
  }, [value, run]);

  const reset = React.useCallback(() => {
    reqRef.current++;
    if (timerRef.current) clearTimeout(timerRef.current);
    setValue("");
    setState("idle");
    setMotivo("");
  }, []);

  // Enter fuerza la comprobación YA: cancela el debounce pendiente (para que no
  // dispare un segundo POST real ~700ms después) e invalida cualquier respuesta en
  // vuelo antes de correr. Resultado: teclear + Enter produce UN solo POST.
  const recheck = React.useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    reqRef.current++;
    run(value);
  }, [run, value]);

  return { value, setValue, state, motivo, reset, recheck };
}

// ── Campo de clave con indicador ✓ / spinner / ✗ y motivo en llano ──────────
interface KeyFieldProps {
  id: string;
  /** Nombre accesible del campo en llano (§G): asociado al input vía htmlFor. */
  label: string;
  value: string;
  onChange: (v: string) => void;
  state: TestState;
  motivo: string;
  placeholder: string;
  onRecheck: () => void;
}

function KeyField({ id, label, value, onChange, state, motivo, placeholder, onRecheck }: KeyFieldProps) {
  return (
    <div className="flex flex-col gap-2">
      {/* Rótulo accesible asociado al input. Visualmente oculto (sr-only) porque el
          enunciado de Mia + la ayuda ya lo describen; el lector de pantalla sí lo anuncia. */}
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="relative">
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onRecheck();
            }
          }}
          type="text"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder={placeholder}
          aria-invalid={state === "error"}
          className={cn(
            "pr-10 font-mono text-sm tracking-tight transition-colors",
            state === "ok" && "border-primary focus-visible:ring-primary",
            state === "error" && "border-destructive focus-visible:ring-destructive",
          )}
        />
        {/* Indicador de estado a la derecha del campo. */}
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
          {state === "testing" && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
          )}
          {state === "ok" && (
            <span
              className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary duration-300 animate-in zoom-in-50 fade-in"
              aria-label="Clave válida"
            >
              <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />
            </span>
          )}
          {state === "error" && (
            <span
              className="flex h-5 w-5 items-center justify-center rounded-full bg-destructive/15 text-destructive duration-300 animate-in zoom-in-50 fade-in"
              aria-label="Clave no válida"
            >
              <X className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />
            </span>
          )}
        </span>
      </div>

      {/* Retroalimentación en llano. */}
      {state === "ok" && (
        <p className="text-xs text-primary duration-300 animate-in fade-in" role="status">
          Perfecto, esa clave funciona.
        </p>
      )}
      {state === "error" && motivo && (
        <p className="text-xs text-destructive duration-300 animate-in fade-in" role="alert">
          {motivo}
        </p>
      )}
    </div>
  );
}

// ── Tarjeta de motor seleccionable ──────────────────────────────────────────
interface EngineCardProps {
  icon: LucideIcon;
  title: string;
  badge?: string;
  description: string;
  detected?: boolean;
  detectedLabel?: string;
  selected: boolean;
  onSelect: () => void;
}

function EngineCard({
  icon: Icon,
  title,
  badge,
  description,
  detected,
  detectedLabel,
  selected,
  onSelect,
}: EngineCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      role="radio"
      aria-checked={selected}
      // Roving tabindex del radiogroup: solo la tarjeta elegida entra en el orden de
      // tabulación; entre tarjetas se navega con flechas (manejadas por el grupo).
      tabIndex={selected ? 0 : -1}
      className={cn(
        "group relative w-full rounded-lg border p-4 text-left transition-all duration-300",
        "hover:border-primary/60",
        selected
          ? "border-primary/50 bg-primary/10 shadow-neu-sunken"
          : "border-border/10 bg-card shadow-neu-raised hover:-translate-y-0.5",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors",
            selected ? "bg-primary text-primary-foreground" : "bg-secondary text-primary shadow-neu-sunken",
          )}
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-foreground">{title}</span>
            {badge && (
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                {badge}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          {detected && detectedLabel && (
            <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-primary">
              <Check className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden />
              {detectedLabel}
            </p>
          )}
        </div>

        {/* Marca de selección. */}
        <span
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
            selected ? "border-primary bg-primary text-primary-foreground" : "border-border",
          )}
          aria-hidden
        >
          {selected && <Check className="h-3.5 w-3.5 duration-200 animate-in zoom-in-50" strokeWidth={3} />}
        </span>
      </div>
    </button>
  );
}

// ── Pantalla ────────────────────────────────────────────────────────────────
type Phase = "cargando" | "error-carga" | "activar" | "listo";

export default function ActivarPage() {
  const router = useRouter();

  const [phase, setPhase] = React.useState<Phase>("cargando");
  const [status, setStatus] = React.useState<WelcomeStatus | null>(null);

  // Sub-paso interno: 0 = motor · 1 = claves del motor elegido · 2 = respaldo
  // OpenRouter (solo cuando aplica).
  const [subStep, setSubStep] = React.useState(0);
  const [direction, setDirection] = React.useState(1);

  const [politica, setPolitica] = React.useState<Politica>("quality_adaptive");
  const busqueda = useKeyValidation("busqueda");
  const respaldo = useKeyValidation("respaldo");
  const openrouter = useKeyValidation("openrouter");

  // Consentimiento EXPRESO del respaldo OpenRouter (opt-in de confidencialidad):
  // sin esta casilla marcada, la clave no se guarda y `allow_openrouter` no viaja.
  const [orConsent, setOrConsent] = React.useState(false);

  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState("");
  const [result, setResult] = React.useState<{ mensaje: string; aviso: string | null } | null>(null);

  // Al montar: consulta el estado, PRESELECCIONA el motor detectado (D4) y decide
  // si auto-omitir (modo dev / nada que falta).
  React.useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const s = await apiGet<WelcomeStatus>("/api/welcome/status");
        if (cancel) return;
        // MENOR 3 (revisión capa 2): si el motor elegido es la cuenta de OpenRouter y esa
        // clave falta, NO auto-saltar — el asistente debe pedirla; de lo contrario Mia
        // razonaría en local en silencio. La clave de OpenRouter solo es imprescindible
        // cuando ES el motor (política 'openrouter'); como respaldo opcional no bloquea.
        const faltaMotorOpenrouter = s.politica === "openrouter" && s.faltan_llaves.openrouter;
        const nadaQueFalta =
          !s.faltan_llaves.busqueda && !s.faltan_llaves.respaldo && !faltaMotorOpenrouter;
        // En modo dev (no instalado) o si no falta ninguna clave, este paso no debe
        // estorbar: se salta directo a "Conocer tu despacho".
        if (!s.instalado || nadaQueFalta) {
          router.replace("/onboarding");
          return;
        }
        setStatus(s);
        setPolitica(preseleccionMotor(s));
        setPhase("activar");
      } catch {
        if (cancel) return;
        // Fail-open amable: nada bloquea al abogado; ofrecemos reintentar o seguir.
        setPhase("error-carga");
      }
    })();
    return () => {
      cancel = true;
    };
  }, [router]);

  function goNext() {
    setDirection(1);
    setSubStep((s) => s + 1);
  }
  function goBack() {
    setDirection(-1);
    setSubStep((s) => s - 1);
  }

  // Encuadres derivados del motor elegido.
  // · "nube": la clave de respaldo ES el motor (obligatoria).
  // · "openrouter" (solo instalaciones que ya venían con esa elección): su clave
  //   es el motor (obligatoria) y no hay sección de respaldo aparte.
  // · "soberano": nada sale del equipo — no se ofrece ningún respaldo externo.
  const respaldoEsMotor = politica === "nube";
  const openrouterEsMotor = politica === "openrouter";
  // El respaldo con la cuenta de OpenRouter solo aplica cuando hay un motor
  // principal distinto y el abogado no eligió máxima privacidad.
  const openrouterRespaldoAplica = !openrouterEsMotor && politica !== "soberano";
  // La clave de respaldo del motor (plan B) solo aplica con motores por suscripción
  // o membresía; en "nube" ese mismo campo es el motor, y en "soberano" no existe.
  const respaldoAplica = politica !== "openrouter" && politica !== "soberano";
  // ¿La pantalla de claves es la terminal (no hay sección de respaldo después)?
  const clavesEsTerminal = !openrouterRespaldoAplica;

  // Guarda lo que haya (política + claves validadas) y termina el paso.
  async function finish() {
    if (!status) return;
    setSaving(true);
    setSaveError("");
    try {
      // Opt-in de confidencialidad (regla 2, bloque D4): `allow_openrouter` SOLO
      // viaja cuando el abogado marcó el consentimiento expreso del respaldo Y su
      // clave quedó validada. Cuando OpenRouter es el propio motor elegido, la
      // elección ya es expresa y el flag es inocuo (funciona sin él); se manda
      // para no bifurcar la lógica del backend.
      const openrouterAutorizado = openrouterEsMotor || (openrouterRespaldoAplica && orConsent);
      const conectoOpenrouter =
        openrouterAutorizado && openrouter.state === "ok" && openrouter.value.trim().length > 0;

      // Fija la política si el abogado la cambió, o si hace falta mandar el opt-in
      // de OpenRouter (el PUT es el único lugar que persiste ambas cosas juntas).
      if (politica !== status.politica || conectoOpenrouter) {
        try {
          await apiSend("PUT", "/settings/model-policy", {
            politica,
            ...(conectoOpenrouter ? { allow_openrouter: true } : {}),
          });
        } catch (err) {
          // NO fail-soft: si la elección de motor no se persiste, seguir mostraría
          // "listo" y el abogado creería que Mia trabaja con el motor que eligió
          // cuando sigue con otro. Se detiene aquí con un motivo en llano; puede
          // reintentar sin perder lo que ya escribió.
          setSaveError(
            plainMessage(err, "No pude guardar tu elección de motor. Inténtalo de nuevo."),
          );
          return;
        }
      }

      // Solo se envían claves que quedaron validadas (✓) y que aplican al motor
      // elegido. La clave de OpenRouter exige además el consentimiento expreso.
      const payload: { busqueda?: string; respaldo?: string; openrouter?: string } = {};
      if (busqueda.state === "ok" && busqueda.value.trim()) payload.busqueda = busqueda.value.trim();
      if ((respaldoAplica || respaldoEsMotor) && respaldo.state === "ok" && respaldo.value.trim())
        payload.respaldo = respaldo.value.trim();
      if (conectoOpenrouter) payload.openrouter = openrouter.value.trim();

      if (payload.busqueda || payload.respaldo || payload.openrouter) {
        const res = await apiSend<KeysResult>("POST", "/api/welcome/keys", payload);
        // Si el backend devolvió `aviso` (se guardó una clave DIFERIDA que solo
        // el proxy lee al arrancar) Y estamos dentro de la cáscara de escritorio,
        // reinicia el motor EN CALIENTE para que la clave quede activa de una vez
        // — así el abogado no tiene que "cerrar y reabrir". Solo se quita el aviso
        // si el motor de verdad se reinició ("reiniciado"); "no-aplica"/"en-curso"
        // o un fallo conservan el aviso. En dev (navegador) el puente mia-shell
        // no existe → shellInvoke falla y el aviso se conserva.
        let aviso = res.aviso;
        if (aviso) {
          try {
            const r = await shellInvoke<string>("restart-litellm");
            if (r === "reiniciado") aviso = null;
          } catch {
            /* dev/navegador o fallo del reinicio: conserva el aviso "cierra y reabre" */
          }
        }
        setResult({ mensaje: res.mensaje, aviso });
        setPhase("listo");
      } else {
        // No hay claves que guardar: continúa directo (la política ya se persistió).
        router.push("/onboarding");
      }
    } catch (err) {
      setSaveError(plainMessage(err, "No pude guardar los cambios. Inténtalo de nuevo."));
    } finally {
      setSaving(false);
    }
  }

  // ── Estados de carga y error de la consulta inicial ──────────────────────
  if (phase === "cargando") {
    return (
      <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
        <div className="flex flex-col items-center gap-3 py-10 text-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden />
          <p className="text-sm">Preparando la activación de Mia…</p>
        </div>
      </WelcomeShell>
    );
  }

  if (phase === "error-carga") {
    return (
      <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
        <Stagger className="flex flex-col items-center gap-4 text-center">
          <StaggerItem>
            <MiaLine
              text="Tuve un problema para preparar este paso."
              className="text-xl sm:text-2xl"
            />
          </StaggerItem>
          <StaggerItem>
            <p className="text-sm text-muted-foreground">
              No te preocupes: puedes intentarlo otra vez o seguir y activar la búsqueda más adelante.
            </p>
          </StaggerItem>
          <StaggerItem>
            <div className="mt-2 flex flex-col items-center gap-2 sm:flex-row">
              <Button variant="cta" size="lg" onClick={() => window.location.reload()}>
                Intentar de nuevo
              </Button>
              <Button variant="ghost" size="lg" onClick={() => router.push("/onboarding")}>
                Seguir por ahora
              </Button>
            </div>
          </StaggerItem>
        </Stagger>
      </WelcomeShell>
    );
  }

  // ── Pantalla "Listo" del paso (confirmación con mensaje + aviso) ─────────
  if (phase === "listo" && result) {
    return (
      <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
        <Stagger className="flex flex-col items-center gap-4 text-center">
          <StaggerItem>
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/15 text-primary duration-500 animate-in zoom-in-50 fade-in">
              <Check className="h-7 w-7" strokeWidth={2.5} aria-hidden />
            </span>
          </StaggerItem>
          <StaggerItem>
            <MiaLine text={result.mensaje} className="text-xl sm:text-2xl" />
          </StaggerItem>
          {/* Aviso FUERTE del backend: solo llega cuando se guardó una clave que sirve
              al MOTOR de modelos (no para la clave de búsqueda, que activa al instante).
              Se muestra como llamada de atención prominente, no como nota al pie: sin
              este paso, Mia no termina de activar su capacidad de razonar. */}
          {result.aviso && (
            <StaggerItem>
              <div
                role="status"
                className="flex max-w-md items-start gap-3 rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-left shadow-neu-raised"
              >
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
                <p className="text-sm font-medium text-foreground">{result.aviso}</p>
              </div>
            </StaggerItem>
          )}
          <StaggerItem>
            <Button variant="cta" size="lg" className="mt-2" onClick={() => router.push("/onboarding")}>
              Continuar
            </Button>
          </StaggerItem>
        </Stagger>
      </WelcomeShell>
    );
  }

  if (!status) return null; // salvaguarda de tipos

  const algoDetectado =
    status.motor_detectado.claude || status.motor_detectado.codex || status.motor_detectado.ollama;

  // ── Sub-paso 0 · UN solo motor principal ──────────────────────────────────
  // Las tarjetas son los MOTORES de verdad. La cuenta de OpenRouter no compite
  // aquí: es un respaldo y tiene su sección propia. La única excepción es una
  // instalación que YA venía con esa elección guardada — quitarle la tarjeta le
  // cambiaría el motor en silencio, así que en ese caso sí se muestra.
  const engineOrder: Politica[] = [
    "quality_adaptive",
    "suscripcion",
    "codex",
    "nube",
    ...(status.politica === "openrouter" ? (["openrouter"] as Politica[]) : []),
    "soberano",
  ];

  const stepMotor = (
    <Stagger className="flex flex-col gap-6">
      <StaggerItem>
        <MiaLine
          text={
            algoDetectado
              ? "Revisé este equipo y dejé seleccionado el motor que ya tienes instalado. Confírmalo o elige otro: trabajo con uno solo como principal."
              : "Elige el motor con el que voy a razonar. Trabajo con uno solo como principal."
          }
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <WelcomeField>
        <div
          role="radiogroup"
          aria-label="Motor principal de Mia"
          className="flex flex-col gap-3"
          onKeyDown={(e) => {
            // El orden DEBE coincidir con el orden visual de las tarjetas (abajo):
            // las flechas mueven el foco por índice de DOM.
            const order = engineOrder;
            const forward = e.key === "ArrowDown" || e.key === "ArrowRight";
            const backward = e.key === "ArrowUp" || e.key === "ArrowLeft";
            if (!forward && !backward) return;
            e.preventDefault();
            const cur = order.indexOf(politica);
            const next = (cur + (forward ? 1 : -1) + order.length) % order.length;
            setPolitica(order[next]);
            // Mueve el foco al radio recién seleccionado (la selección sigue al foco).
            const radios = e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]');
            radios[next]?.focus();
          }}
        >
          <EngineCard
            icon={Sparkles}
            title="Calidad jurídica adaptativa"
            badge="Recomendado"
            // Honestidad del aviso: el cambio de motor se informa AL CERRAR el turno (así
            // está construido el SSE aviso_de_costo); prometer "antes" sería falso.
            // Decisión de Pipe 2026-08-14: el más inteligente piensa y orquesta; la
            // ejecución se asigna por tarea. §G: sin nombres de modelo en el copy.
            description="El motor más capaz piensa y dirige tu asunto, y asigna cada tarea al ejecutor adecuado: profundidad donde se decide, agilidad donde se ejecuta. Si una capacidad no está disponible, Mia falla claro o te informa cada cambio de motor y su costo al terminar el turno."
            detected={status.motor_detectado.claude}
            detectedLabel="Ya detecté Claude Code en este equipo."
            selected={politica === "quality_adaptive"}
            onSelect={() => setPolitica("quality_adaptive")}
          />
          <EngineCard
            icon={Sparkles}
            title="Mi suscripción"
            // La recomendación del plan Max va AQUÍ, en la instalación, y no solo cuando ya
            // pasó (decisión de Pipe, sesión 52). Medido con un expediente real de 174
            // páginas: una suscripción normal no alcanzó a responderlo y el trabajo se
            // resolvió con crédito de pago. Mejor que el abogado lo sepa al elegir el motor
            // que enterarse por un cargo. En llano y sin cifras que no podemos sostener.
            description="Usa directamente la configuración habitual de tu suscripción. Con un plan Max, un expediente extenso cabe en lo que ya pagas, sin costo extra; en planes inferiores no cabe y genera cobros de crédito adicionales. Si una capacidad no está disponible, Mia te lo mostrará y usará el respaldo que hayas autorizado."
            detected={status.motor_detectado.claude}
            detectedLabel="Ya la detecté lista en este equipo."
            selected={politica === "suscripcion"}
            onSelect={() => setPolitica("suscripcion")}
          />
          <EngineCard
            icon={Sparkles}
            title="Codex en este equipo"
            description="Usa tu membresía de Codex como motor jurídico principal en este computador. No funciona en servidores ni cambia a Claude, nube ni otro motor sin que tú cambies esta selección."
            detected={Boolean(status.motor_estado?.codex?.instalada ?? status.motor_detectado.codex)}
            detectedLabel={etiquetaCodex(status)}
            selected={politica === "codex"}
            onSelect={() => setPolitica("codex")}
          />
          <EngineCard
            icon={Cloud}
            title="En la nube"
            description="Me conecto a un motor en internet para razonar. Requiere la clave del motor; te la pido en el paso siguiente."
            selected={politica === "nube"}
            onSelect={() => setPolitica("nube")}
          />
          {status.politica === "openrouter" && (
            <EngineCard
              icon={Wallet}
              title="Tu cuenta de OpenRouter"
              description="Esta instalación ya venía con tu cuenta de OpenRouter como motor. Tú la cargas de crédito y pagas tu propio uso; tu trabajo sale hacia ese servicio externo."
              selected={politica === "openrouter"}
              onSelect={() => setPolitica("openrouter")}
            />
          )}
          <EngineCard
            icon={Cpu}
            title="Todo en tu equipo"
            description="Razono sin que nada salga de tu computador. Ideal si quieres máxima privacidad."
            detected={status.motor_detectado.ollama}
            detectedLabel="Ya lo detecté listo en este equipo."
            selected={politica === "soberano"}
            onSelect={() => setPolitica("soberano")}
          />
        </div>
      </WelcomeField>

      <WelcomeField>
        <Button variant="cta" size="lg" className="w-full" onClick={goNext}>
          Continuar
        </Button>
      </WelcomeField>
    </Stagger>
  );

  // ── Sub-paso 1 · UNA sola pantalla de claves (solo las que aplican) ───────
  // Reglas de copy (memoria del dueño): registro profesional, indicativo, y lo
  // imprescindible se enuncia como requisito, no como consejo.
  const puedeContinuarClaves =
    // La clave del motor (cuando el motor la exige) es obligatoria.
    (!respaldoEsMotor || respaldo.state === "ok") &&
    (!openrouterEsMotor || openrouter.state === "ok") &&
    // La de búsqueda es requisito para continuar por el camino principal.
    busqueda.state === "ok" &&
    // El plan B opcional, si se escribió, tiene que estar validado.
    (!respaldoAplica || respaldoEsMotor || !respaldo.value.trim() || respaldo.state === "ok");

  // Camino secundario: seguir sin activar la búsqueda. Exige igual la clave del
  // motor cuando el motor la requiere — sin motor, Mia no razona.
  const puedeOmitirBusqueda =
    (!respaldoEsMotor || respaldo.state === "ok") &&
    (!openrouterEsMotor || openrouter.state === "ok") &&
    (!respaldoAplica || respaldoEsMotor || !respaldo.value.trim() || respaldo.state === "ok");

  const stepClaves = (
    <Stagger className="flex flex-col gap-6">
      <StaggerItem>
        <button
          type="button"
          onClick={goBack}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Volver
        </button>
      </StaggerItem>

      <StaggerItem>
        <MiaLine
          text="Estas son las claves que aplican al motor que elegiste. Te digo qué activa cada una."
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      {/* 1 · Clave de búsqueda: REQUISITO de la búsqueda documental, siempre aplica. */}
      <WelcomeField
        label="Búsqueda en tus documentos"
        htmlFor="clave-busqueda"
        hint="Esta clave es un requisito para la búsqueda: sin ella no leo ni encuentro nada dentro de tus documentos. Con ella, la búsqueda queda activa de inmediato."
      >
        <KeyField
          id="clave-busqueda"
          label="Clave de búsqueda en tus documentos"
          value={busqueda.value}
          onChange={busqueda.setValue}
          state={busqueda.state}
          motivo={busqueda.motivo}
          onRecheck={busqueda.recheck}
          placeholder="Pega aquí tu clave de búsqueda"
        />
      </WelcomeField>

      {/* 2 · Clave del motor, SOLO cuando el motor elegido la exige. */}
      {respaldoEsMotor && (
        <WelcomeField
          label="Motor en la nube"
          htmlFor="clave-respaldo"
          hint="Elegiste razonar en la nube: esta clave ES tu motor. Sin ella no puedo razonar, así que la necesito para continuar."
        >
          <KeyField
            id="clave-respaldo"
            label="Clave del motor en la nube"
            value={respaldo.value}
            onChange={respaldo.setValue}
            state={respaldo.state}
            motivo={respaldo.motivo}
            onRecheck={respaldo.recheck}
            placeholder="Pega aquí la clave del motor"
          />
        </WelcomeField>
      )}

      {openrouterEsMotor && (
        <WelcomeField
          label="Tu cuenta de OpenRouter"
          htmlFor="clave-openrouter-motor"
          hint="Elegiste tu cuenta de OpenRouter como motor: esta clave es la que me deja razonar. Tú la creas, la cargas de crédito y pagas tu propio uso."
        >
          <KeyField
            id="clave-openrouter-motor"
            label="Clave de tu cuenta de OpenRouter"
            value={openrouter.value}
            onChange={openrouter.setValue}
            state={openrouter.state}
            motivo={openrouter.motivo}
            onRecheck={openrouter.recheck}
            placeholder="Pega aquí la clave de tu cuenta de OpenRouter"
          />
          <div className="mt-3 flex flex-col gap-1.5 text-xs text-muted-foreground">
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noreferrer"
              className="inline-flex w-fit items-center gap-1 text-primary underline-offset-4 transition-colors hover:underline"
            >
              Crea tu clave en openrouter.ai/keys
            </a>
            <span>Ponle un tope de gasto en OpenRouter para no llevarte sorpresas.</span>
          </div>
        </WelcomeField>
      )}

      {/* 3 · Plan B del motor: solo con motores por suscripción o membresía. */}
      {respaldoAplica && !respaldoEsMotor && (
        <WelcomeField
          label="Respaldo del motor (opcional)"
          htmlFor="clave-respaldo"
          hint="Cuando tu motor principal no está disponible, uso esta clave para seguir trabajando. Sin ella, si el motor principal falla me detengo y te aviso. Puedes agregarla ahora o más adelante."
        >
          <KeyField
            id="clave-respaldo"
            label="Clave de respaldo del motor"
            value={respaldo.value}
            onChange={respaldo.setValue}
            state={respaldo.state}
            motivo={respaldo.motivo}
            onRecheck={respaldo.recheck}
            placeholder="Pega aquí tu clave de respaldo (opcional)"
          />
        </WelcomeField>
      )}

      {saveError && clavesEsTerminal && (
        <StaggerItem>
          <p
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
          >
            {saveError}
          </p>
        </StaggerItem>
      )}

      <WelcomeField>
        <div className="flex flex-col gap-2">
          <Button
            variant="cta"
            size="lg"
            className="w-full"
            disabled={saving || !puedeContinuarClaves}
            onClick={clavesEsTerminal ? () => finish() : goNext}
          >
            {clavesEsTerminal && saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Guardando…
              </>
            ) : clavesEsTerminal ? (
              "Terminar y continuar"
            ) : (
              "Continuar"
            )}
          </Button>
          {/* Camino secundario, con la consecuencia dicha de frente: sin la clave de
              búsqueda, la búsqueda queda desactivada. Solo aparece mientras esa clave
              no está validada, y nunca salta la clave del MOTOR (sin motor no hay Mia). */}
          {busqueda.state !== "ok" && (
            <Button
              variant="ghost"
              size="lg"
              className="w-full"
              disabled={saving || !puedeOmitirBusqueda}
              onClick={clavesEsTerminal ? () => finish() : goNext}
            >
              Seguir sin activar la búsqueda por ahora
            </Button>
          )}
        </div>
      </WelcomeField>
    </Stagger>
  );

  // ── Sub-paso 2 · Respaldo con tu cuenta de OpenRouter (consentimiento) ────
  const stepOpenrouterRespaldo = (
    <Stagger className="flex flex-col gap-6">
      <StaggerItem>
        <button
          type="button"
          onClick={goBack}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Volver
        </button>
      </StaggerItem>

      <StaggerItem>
        <MiaLine
          text="Un respaldo adicional, aparte de tu motor: tu cuenta de OpenRouter. Es opcional y decides tú."
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <StaggerItem>
        <NotaMia
          id="activar-openrouter-respaldo"
          icon={ShieldAlert}
          titulo="Qué es OpenRouter y qué implica activarlo"
          cerrable={false}
        >
          OpenRouter es un servicio externo que da acceso a motores de razonamiento por
          internet. Solo entra a trabajar cuando tu motor principal falla. El gasto corre
          por tu cuenta: tú la creas, la cargas de crédito y le pones un tope. Al usarlo,
          la información de tu trabajo sale de este equipo hacia ese servicio externo.
        </NotaMia>
      </StaggerItem>

      {/* Consentimiento EXPRESO: la casilla es la puerta. Sin marcarla no aparece el
          campo de la clave, no se guarda nada y el permiso no se activa. */}
      <WelcomeField>
        <label
          htmlFor="consentimiento-openrouter"
          className="flex cursor-pointer items-start gap-3 rounded-lg border border-border/10 bg-card p-4 shadow-neu-raised transition-colors hover:border-primary/60"
        >
          <input
            id="consentimiento-openrouter"
            type="checkbox"
            checked={orConsent}
            onChange={(e) => setOrConsent(e.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 accent-primary"
          />
          <span className="text-sm text-foreground">
            Autorizo que, cuando mi motor principal falle, Mia continúe el trabajo con mi
            cuenta de OpenRouter. Entiendo que eso envía la información de mi trabajo a un
            servicio externo y que ese uso lo pago yo.
          </span>
        </label>
      </WelcomeField>

      {orConsent && (
        <WelcomeField
          label="Clave de tu cuenta de OpenRouter"
          htmlFor="clave-openrouter"
          hint="Con esta clave activo el respaldo que acabas de autorizar. La clave queda guardada en este equipo."
        >
          <KeyField
            id="clave-openrouter"
            label="Clave de tu cuenta de OpenRouter"
            value={openrouter.value}
            onChange={openrouter.setValue}
            state={openrouter.state}
            motivo={openrouter.motivo}
            onRecheck={openrouter.recheck}
            placeholder="Pega aquí la clave de tu cuenta de OpenRouter"
          />
          <div className="mt-3 flex flex-col gap-1.5 text-xs text-muted-foreground">
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noreferrer"
              className="inline-flex w-fit items-center gap-1 text-primary underline-offset-4 transition-colors hover:underline"
            >
              Crea tu clave en openrouter.ai/keys
            </a>
            <span>Ponle un tope de gasto en OpenRouter para no llevarte sorpresas.</span>
          </div>
        </WelcomeField>
      )}

      {saveError && (
        <StaggerItem>
          <p
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
          >
            {saveError}
          </p>
        </StaggerItem>
      )}

      <WelcomeField>
        <div className="flex flex-col gap-2">
          <Button
            variant="cta"
            size="lg"
            className="w-full"
            // Con consentimiento marcado, la clave escrita tiene que quedar validada;
            // sin consentimiento, este botón termina sin activar nada de OpenRouter.
            disabled={saving || (orConsent && openrouter.value.trim().length > 0 && openrouter.state !== "ok")}
            onClick={() => finish()}
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Guardando…
              </>
            ) : orConsent ? (
              "Activar el respaldo y terminar"
            ) : (
              "Terminar sin este respaldo"
            )}
          </Button>
        </div>
      </WelcomeField>
    </Stagger>
  );

  // Pasos dinámicos según el motor elegido: motor y claves siempre; la sección de
  // respaldo con OpenRouter solo cuando hay un motor principal distinto y el
  // abogado no eligió máxima privacidad ("soberano": nada sale del equipo).
  const steps = [stepMotor, stepClaves];
  if (openrouterRespaldoAplica) steps.push(stepOpenrouterRespaldo);

  return (
    <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
      <StepTransition stepKey={subStep} direction={direction}>
        {steps[Math.min(subStep, steps.length - 1)]}
      </StepTransition>
    </WelcomeShell>
  );
}
