"use client";


import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  Cloud,
  Cpu,
  Loader2,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  WelcomeShell,
  WelcomeProgress,
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

type Politica = "quality_adaptive" | "suscripcion" | "codex" | "nube" | "soberano" | "openrouter";

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


const GENERIC_TEST_ERROR = "No pude usar esa clave. Revísala y vuelve a intentarlo.";
const GENERIC_TEST_UNAVAILABLE = "No pude comprobar la clave en este momento. Puedes intentarlo de nuevo.";

function plainMessage(err: unknown, porDefecto: string): string {
  const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
  return msg || porDefecto;
}

function preseleccionMotor(s: WelcomeStatus): Politica {
  const d = s.motor_detectado;
  const p = s.politica ?? "quality_adaptive";
  if ((p === "quality_adaptive" || p === "suscripcion") && d.claude) return "quality_adaptive";
  if (p === "codex" && d.codex) return p;
  if (p === "soberano" && d.ollama) return p;
  if (p === "nube" || p === "openrouter") return p;
  if (d.claude) return "quality_adaptive";
  if (d.codex) return "codex";
  if (d.ollama) return "soberano";
  return "nube";
}

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

function useKeyValidation(tipo: "busqueda" | "respaldo" | "openrouter") {
  const [value, setValue] = React.useState("");
  const [state, setState] = React.useState<TestState>("idle");
  const [motivo, setMotivo] = React.useState("");
  const reqRef = React.useRef(0);
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

  const recheck = React.useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    reqRef.current++;
    run(value);
  }, [run, value]);

  return { value, setValue, state, motivo, reset, recheck };
}

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
          type="password"
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

export default function ActivarPage() {
  const router = useRouter();
  const [status, setStatus] = React.useState<WelcomeStatus | null>(null);
  const [politica, setPolitica] = React.useState<Politica>("quality_adaptive");
  const [advanced, setAdvanced] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [aviso, setAviso] = React.useState<string | null>(null);
  const busqueda = useKeyValidation("busqueda");
  const respaldo = useKeyValidation("respaldo");
  const openrouter = useKeyValidation("openrouter");

  React.useEffect(() => {
    let cancelled = false;
    apiGet<WelcomeStatus>("/api/welcome/status").then((s) => {
      if (cancelled) return;
      setStatus(s);
      setPolitica(preseleccionMotor(s));
    }).catch(() => {
      if (!cancelled) setError("No pude comprobar las conexiones. Vuelve a intentarlo.");
    });
    return () => { cancelled = true; };
  }, []);

  if (!status) return (
    <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
      <p role={error ? "alert" : "status"}>{error || "Comprobando las conexiones de este equipo…"}</p>
      {error && <Button onClick={() => window.location.reload()}>Volver a intentar</Button>}
    </WelcomeShell>
  );

  const subscription = ["quality_adaptive", "suscripcion", "codex"].includes(politica);
  const preferred = status.motor_detectado.claude ? "quality_adaptive" : "codex";
  const hasSubscription = status.motor_detectado.claude || status.motor_detectado.codex;
  const cloud = politica === "nube" || politica === "openrouter";
  const selectedKey = politica === "openrouter" ? openrouter : respaldo;
  const savedKey = politica === "openrouter" ? !status.faltan_llaves.openrouter : !status.faltan_llaves.respaldo;
  const canContinue = (!subscription || hasSubscription) &&
    (politica !== "soberano" || status.motor_detectado.ollama) &&
    (!cloud || savedKey || selectedKey.state === "ok") &&
    (!cloud || !selectedKey.value.trim() || selectedKey.state === "ok") &&
    (!busqueda.value.trim() || busqueda.state === "ok");
  const order: Politica[] = [subscription ? politica : preferred, "nube",
    ...(status.politica === "openrouter" ? ["openrouter" as Politica] : []), "soberano"];

  async function finish() {
    if (!status || !canContinue || saving) return;
    setSaving(true);
    setError("");
    try {
      let pendingNotice: string | null = null;
      const payload: { busqueda?: string; respaldo?: string; openrouter?: string } = {};
      if (busqueda.state === "ok" && busqueda.value.trim()) payload.busqueda = busqueda.value.trim();
      if (cloud && selectedKey.state === "ok" && selectedKey.value.trim()) {
        if (politica === "openrouter") payload.openrouter = selectedKey.value.trim();
        else payload.respaldo = selectedKey.value.trim();
      }
      if (Object.keys(payload).length) {
        const res = await apiSend<KeysResult>("POST", "/api/welcome/keys", payload);
        if (res.aviso) {
          let restarted = false;
          try { restarted = await shellInvoke<string>("restart-litellm") === "reiniciado"; } catch { /* Keep the server's restart notice. */ }
          if (!restarted) pendingNotice = res.aviso;
        }
      }
      await apiSend("PUT", "/settings/model-policy", { politica });
      if (pendingNotice) setAviso(pendingNotice);
      else router.push("/onboarding");
    } catch (err) {
      setError(plainMessage(err, "No pude guardar la conexión. Inténtalo de nuevo."));
    } finally { setSaving(false); }
  }

  if (aviso) return (
    <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
      <div className="space-y-5">
        <MiaLine text="Conexión guardada" className="text-xl sm:text-2xl" />
        <p role="alert" className="text-sm">{aviso}</p>
        <Button variant="cta" onClick={() => router.push("/onboarding")}>Continuar</Button>
      </div>
    </WelcomeShell>
  );

  return (
    <WelcomeShell progress={<WelcomeProgress steps={JOURNEY_STEPS} current={1} />}>
      <Stagger className="flex flex-col gap-5">
        <StaggerItem>
          <MiaLine text="Conecta lo que ya usas" className="text-xl sm:text-2xl" />
          <p className="mt-2 text-sm text-muted-foreground">
            Mia detecta Claude Code y Codex en este equipo. Sus sesiones permiten usar tu suscripción; no necesitas una clave API para esa conexión.
          </p>
        </StaggerItem>
        <WelcomeField>
          <div role="radiogroup" aria-label="Cómo conectar Mia" className="flex flex-col gap-3"
            onKeyDown={(e) => {
              if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(e.key)) return;
              e.preventDefault();
              const next = (order.indexOf(politica) + (["ArrowDown", "ArrowRight"].includes(e.key) ? 1 : -1) + order.length) % order.length;
              setPolitica(order[next]);
              e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]')[next]?.focus();
            }}>
            <EngineCard icon={Sparkles} title="Mis suscripciones" badge={hasSubscription ? "Detectadas" : undefined}
              description="Usa Claude Code o Codex con la cuenta conectada en este equipo. Se aplican los límites y condiciones de tu plan."
              selected={subscription} onSelect={() => setPolitica(preferred)} />
            <EngineCard icon={Cloud} title="Cuenta API de Anthropic"
              description="Conexión opcional con facturación por uso, independiente de la suscripción de Claude. Requiere una clave API."
              selected={politica === "nube"} onSelect={() => setPolitica("nube")} />
            {status.politica === "openrouter" && <EngineCard icon={Cloud} title="Cuenta API de OpenRouter"
              description="Conserva tu conexión existente, con facturación por uso de OpenRouter."
              selected={politica === "openrouter"} onSelect={() => setPolitica("openrouter")} />}
            <EngineCard icon={Cpu} title="IA local con Ollama"
              description="Usa los modelos instalados en este computador."
              detected={status.motor_detectado.ollama} detectedLabel="Ollama detectado."
              selected={politica === "soberano"} onSelect={() => setPolitica("soberano")} />
          </div>
        </WelcomeField>
        {subscription && <WelcomeField>
          <div className="space-y-2 text-sm">
            <p>{status.motor_detectado.claude ? "Claude Code detectado. La sesión se comprueba al usarlo." : "Claude Code no detectado."}</p>
            <p>{etiquetaCodex(status) || "Codex no detectado."}</p>
            {status.motor_detectado.claude && status.motor_detectado.codex && <label className="block">
              Conexión preferida
              <select aria-label="Conexión preferida" className="mt-2 w-full rounded-lg border border-input bg-background p-3 shadow-neu-sunken"
                value={politica === "codex" ? "codex" : "quality_adaptive"}
                onChange={(e) => setPolitica(e.target.value as Politica)}>
                <option value="quality_adaptive">Claude Code</option><option value="codex">Codex</option>
              </select>
            </label>}
            {!hasSubscription && <p role="status">Inicia sesión en Claude Code o Codex y vuelve a comprobar las conexiones.</p>}
            <p className="text-muted-foreground">Mia organiza el trabajo según la tarea. Los documentos siguen siendo borradores hasta que los apruebes.</p>
          </div>
        </WelcomeField>}
        {cloud && <WelcomeField label={politica === "openrouter" ? "Clave API de OpenRouter" : "Clave API de Anthropic"}
          htmlFor="clave-api" hint={savedKey ? "Ya hay una clave guardada. Solo completa este campo si quieres cambiarla." : "Esta cuenta factura el uso por separado. La clave se guarda en este equipo."}>
          <KeyField id="clave-api" label="Clave API" value={selectedKey.value} onChange={selectedKey.setValue}
            state={selectedKey.state} motivo={selectedKey.motivo} onRecheck={selectedKey.recheck} placeholder="Clave API del proveedor seleccionado" />
        </WelcomeField>}
        <WelcomeField>
          <button type="button" className="text-sm text-primary underline" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
            {advanced ? "Ocultar opciones adicionales" : "Búsqueda documental avanzada (opcional)"}
          </button>
          {advanced && <div className="mt-3 space-y-3">
            <p className="text-sm text-muted-foreground">Voyage AI permite buscar por significado en los documentos indexados por Mia. Es un servicio API independiente; su clave no activa Claude, Codex ni Perplexity. El acceso mediante herramientas conectadas se configura por separado.</p>
            {!status.faltan_llaves.busqueda && <p className="text-sm">Ya tienes una clave de Voyage AI guardada.</p>}
            <KeyField id="clave-busqueda" label="Clave API de Voyage AI" value={busqueda.value} onChange={busqueda.setValue}
              state={busqueda.state} motivo={busqueda.motivo} onRecheck={busqueda.recheck} placeholder="Clave API de Voyage AI (opcional)" />
          </div>}
        </WelcomeField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <WelcomeField>
          <Button variant="cta" size="lg" className="w-full" disabled={saving || !canContinue} onClick={finish}>
            {saving ? "Guardando…" : "Continuar"}
          </Button>
        </WelcomeField>
      </Stagger>
    </WelcomeShell>
  );
}
