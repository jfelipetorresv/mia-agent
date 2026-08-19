"use client";

// Activar MIA — paso 2 del viaje de bienvenida (F3).
// El abogado confirma el motor de Mia y pega la clave mínima de búsqueda, con
// validación en vivo. Todo en lenguaje llano (§G): NUNCA se muestra "API key",
// "Voyage", "Anthropic", "token", "endpoint", "modelo" ni "LLM".
//
// Consumo de infraestructura visual: WelcomeShell + WelcomeProgress (current=1),
// StepTransition entre sub-pasos, Stagger/WelcomeField y MiaLine para la voz de
// Mia. El motion "grande" lo dan esos wrappers; los micro-remates (✓ que aparece)
// usan clases de tailwindcss-animate — no se importa framer-motion directo.

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Cloud,
  Cpu,
  Loader2,
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
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { shellInvoke } from "@/lib/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// ── Contratos backend (welcome) ────────────────────────────────────────────
type Politica = "quality_adaptive" | "suscripcion" | "codex" | "nube" | "soberano" | "openrouter";

interface WelcomeStatus {
  instalado: boolean;
  hay_usuario: boolean;
  faltan_llaves: { busqueda: boolean; respaldo: boolean; openrouter: boolean };
  onboarding_completo: boolean;
  motor_detectado: { claude: boolean; codex: boolean; ollama: boolean };
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
function plainMessage(err: unknown, fallback: string): string {
  const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
  return msg || fallback;
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
        "group relative w-full rounded-xl border bg-card/60 p-4 text-left transition-all duration-300",
        "hover:border-primary/60 hover:bg-card",
        selected ? "glow-teal border-primary bg-primary/10" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors",
            selected ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground",
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
          {detected && (
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

  // Sub-paso interno: 0 = motor, 1 = clave de búsqueda, 2 = clave de respaldo.
  const [subStep, setSubStep] = React.useState(0);
  const [direction, setDirection] = React.useState(1);

  const [politica, setPolitica] = React.useState<Politica>("quality_adaptive");
  const busqueda = useKeyValidation("busqueda");
  const respaldo = useKeyValidation("respaldo");
  const openrouter = useKeyValidation("openrouter");

  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState("");
  const [result, setResult] = React.useState<{ mensaje: string; aviso: string | null } | null>(null);

  // Al montar: consulta el estado y decide si auto-omitir (modo dev / nada que falta).
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
        setPolitica(s.politica ?? "quality_adaptive");
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

  // Guarda lo que haya (política + claves validadas) y termina el paso.
  // `includeRespaldo=false` / `includeOpenrouter=false` cuando el abogado pulsa
  // "Omitir" — así no se envía esa clave aunque haya alcanzado a validarla antes.
  async function finish(opts: { includeRespaldo?: boolean; includeOpenrouter?: boolean } = {}) {
    const { includeRespaldo = true, includeOpenrouter = true } = opts;
    if (!status) return;
    setSaving(true);
    setSaveError("");
    try {
      // Si el abogado conectó una clave de OpenRouter válida y NO la eligió como
      // motor principal, la está conectando como respaldo/"más uso": ese es el
      // opt-in de confidencialidad para enrutar el overflow a un tercero (regla 2).
      // Con "openrouter" como motor no hace falta (ya funciona sin el flag), pero
      // mandarlo true es inocuo — se decide igual para no bifurcar la lógica.
      const conectoOpenrouter = includeOpenrouter && openrouter.state === "ok" && openrouter.value.trim().length > 0;

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

      // Solo se envían claves que quedaron validadas (✓). Las omitidas no se tocan.
      const payload: { busqueda?: string; respaldo?: string; openrouter?: string } = {};
      if (busqueda.state === "ok" && busqueda.value.trim()) payload.busqueda = busqueda.value.trim();
      if (includeRespaldo && respaldo.state === "ok" && respaldo.value.trim())
        payload.respaldo = respaldo.value.trim();
      if (includeOpenrouter && openrouter.state === "ok" && openrouter.value.trim())
        payload.openrouter = openrouter.value.trim();

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
                className="flex max-w-md items-start gap-3 rounded-xl border border-primary/40 bg-primary/10 px-4 py-3 text-left"
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

  // Encuadre de la clave de respaldo (Anthropic) según el motor elegido: en "nube" ES el
  // motor (obligatoria); en el resto es un plan B opcional.
  const respaldoEsMotor = politica === "nube";
  // La clave de OpenRouter es el MOTOR cuando el abogado eligió "Tu cuenta de OpenRouter"
  // (obligatoria); en "nube"/"suscripción" aparece como respaldo/"más uso" (opcional). En
  // "soberano" no se ofrece (nada sale del equipo).
  const openrouterEsMotor = politica === "openrouter";
  // El paso de OpenRouter existe salvo en "soberano"; el paso de respaldo (Anthropic)
  // existe salvo cuando OpenRouter ya es el motor. El ÚLTIMO paso presente es el que
  // guarda y termina; el paso de respaldo solo es terminal en "soberano".
  const respaldoIsLast = politica === "soberano";

  // ── Sub-pasos del asistente de activación ────────────────────────────────
  const stepMotor = (
    <Stagger className="flex flex-col gap-6">
      <StaggerItem>
        <MiaLine
          text="Para ayudarte necesito un motor que me haga razonar. Elige de dónde saco esa capacidad."
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <WelcomeField>
        <div
          role="radiogroup"
          aria-label="Motor de Mia"
          className="flex flex-col gap-3"
          onKeyDown={(e) => {
            // El orden DEBE coincidir con el orden visual de las tarjetas (abajo):
            // las flechas mueven el foco por índice de DOM.
            const order: Politica[] = ["quality_adaptive", "suscripcion", "codex", "nube", "openrouter", "soberano"];
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
            detected={status.motor_detectado.codex}
            detectedLabel="Detecté Codex local; la primera solicitud comprobará tu sesión y fallará claro si no está iniciada."
            selected={politica === "codex"}
            onSelect={() => setPolitica("codex")}
          />
          <EngineCard
            icon={Cloud}
            title="En la nube"
            description={
              status.motor_detectado.claude
                ? "Me conecto a un motor en internet. Necesitarás una clave de respaldo del motor."
                : "Me conecto a un motor en internet para razonar. Necesitarás una clave de respaldo del motor."
            }
            selected={politica === "nube"}
            onSelect={() => setPolitica("nube")}
          />
          <EngineCard
            icon={Wallet}
            title="Tu cuenta de OpenRouter"
            description="Tú conectas tu cuenta y la cargas de crédito; pagas tu propio uso. Ideal si no usas la suscripción del equipo."
            selected={politica === "openrouter"}
            onSelect={() => setPolitica("openrouter")}
          />
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

  const stepBusqueda = (
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
          text="Ahora, pega tu clave de búsqueda en tus documentos."
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <WelcomeField hint="Con esta clave puedo leer y encontrar lo que necesito dentro de tus documentos. Es la que hace que la búsqueda funcione.">
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

      <WelcomeField>
        <div className="flex flex-col gap-2">
          <Button
            variant="cta"
            size="lg"
            className="w-full"
            disabled={busqueda.state !== "ok"}
            onClick={goNext}
          >
            Continuar
          </Button>
          <Button variant="ghost" size="lg" className="w-full" onClick={goNext}>
            Lo haré después
          </Button>
        </div>
      </WelcomeField>
    </Stagger>
  );

  const stepRespaldo = (
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
          text={
            respaldoEsMotor
              ? "Por último, pega la clave de respaldo del motor."
              : "¿Quieres añadir una clave de respaldo del motor? Es opcional."
          }
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <WelcomeField
        hint={
          respaldoEsMotor
            ? "Es la clave que me da la capacidad de razonar en la nube, así que la necesito para poder ayudarte."
            : "Es un plan B por si tu suscripción no está disponible. No la necesitas para empezar; puedes añadirla ahora o más adelante."
        }
      >
        <KeyField
          id="clave-respaldo"
          label="Clave de respaldo del motor"
          value={respaldo.value}
          onChange={respaldo.setValue}
          state={respaldo.state}
          motivo={respaldo.motivo}
          onRecheck={respaldo.recheck}
          placeholder={
            respaldoEsMotor
              ? "Pega aquí la clave del motor"
              : "Pega aquí tu clave de respaldo (opcional)"
          }
        />
      </WelcomeField>

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
            // En "nube" la clave de respaldo ES el motor primario: obligatoria — el
            // botón exige clave válida. En suscripción/soberano es de verdad opcional:
            // basta que, si escribió algo, esté validado. Cuando este paso NO es el
            // último (suscripción/nube tienen después el paso de OpenRouter), el botón
            // avanza; solo en "soberano" (paso terminal) guarda y termina.
            disabled={
              (respaldoIsLast && saving) ||
              (respaldoEsMotor
                ? respaldo.state !== "ok"
                : respaldo.value.trim().length > 0 && respaldo.state !== "ok")
            }
            onClick={respaldoIsLast ? () => finish({ includeRespaldo: true }) : goNext}
          >
            {respaldoIsLast && saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Guardando…
              </>
            ) : respaldoIsLast ? (
              "Terminar y continuar"
            ) : (
              "Continuar"
            )}
          </Button>
          {/* Salto solo cuando el respaldo es REALMENTE opcional. En "nube" no se ofrece:
              sin esa clave Mia no tiene motor para razonar. Terminal (soberano) omite y
              termina; intermedio (suscripción) simplemente avanza al paso de OpenRouter. */}
          {!respaldoEsMotor && (
            <Button
              variant="ghost"
              size="lg"
              className="w-full"
              disabled={saving}
              onClick={respaldoIsLast ? () => finish({ includeRespaldo: false }) : goNext}
            >
              {respaldoIsLast ? "Omitir por ahora" : "Lo haré después"}
            </Button>
          )}
        </div>
      </WelcomeField>
    </Stagger>
  );

  const stepOpenrouter = (
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
          text={
            openrouterEsMotor
              ? "Para razonar con tu cuenta de OpenRouter necesito tu clave. Tú la creas y la cargas de crédito."
              : "¿Quieres más uso? Conecta tu cuenta de OpenRouter como respaldo."
          }
          className="text-xl leading-snug sm:text-2xl"
        />
      </StaggerItem>

      <WelcomeField
        hint={
          openrouterEsMotor
            ? "Con esta clave uso tu cuenta de OpenRouter para razonar. Tú pagas tu propio uso."
            : "Cuando tu motor principal no esté disponible, sigo trabajando con tu cuenta de OpenRouter. Es opcional; puedes añadirla ahora o más adelante."
        }
      >
        <KeyField
          id="clave-openrouter"
          label="Clave de tu cuenta de OpenRouter"
          value={openrouter.value}
          onChange={openrouter.setValue}
          state={openrouter.state}
          motivo={openrouter.motivo}
          onRecheck={openrouter.recheck}
          placeholder={
            openrouterEsMotor
              ? "Pega aquí la clave de tu cuenta de OpenRouter"
              : "Pega aquí tu clave de OpenRouter (opcional)"
          }
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
            // Motor principal (openrouter): clave OBLIGATORIA. Respaldo/"más uso"
            // (suscripción/nube): opcional — basta que, si escribió algo, esté validado.
            disabled={
              saving ||
              (openrouterEsMotor
                ? openrouter.state !== "ok"
                : openrouter.value.trim().length > 0 && openrouter.state !== "ok")
            }
            onClick={() => finish({ includeOpenrouter: true })}
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Guardando…
              </>
            ) : (
              "Terminar y continuar"
            )}
          </Button>
          {/* "Omitir" solo cuando OpenRouter es opcional (respaldo). Como motor principal
              no se ofrece: sin esa clave Mia no tiene con qué razonar. */}
          {!openrouterEsMotor && (
            <Button
              variant="ghost"
              size="lg"
              className="w-full"
              disabled={saving}
              onClick={() => finish({ includeOpenrouter: false })}
            >
              Omitir por ahora
            </Button>
          )}
        </div>
      </WelcomeField>
    </Stagger>
  );

  // Pasos dinámicos según el motor elegido: motor y búsqueda siempre; el respaldo
  // (Anthropic) salvo cuando OpenRouter YA es el motor; el paso de OpenRouter salvo en
  // "soberano" (nada sale del equipo). El último presente guarda y termina.
  const steps = [stepMotor, stepBusqueda];
  if (politica !== "openrouter") steps.push(stepRespaldo);
  if (politica !== "soberano") steps.push(stepOpenrouter);

  return (
    <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
      <StepTransition stepKey={subStep} direction={direction}>
        {steps[subStep]}
      </StepTransition>
    </WelcomeShell>
  );
}
