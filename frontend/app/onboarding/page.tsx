"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MiaLine, Stagger, StaggerItem, StepTransition, WelcomeProgress, WelcomeShell } from "@/app/_welcome";

type Status = { completed: boolean };

/**
 * El perfil inicial no es una entrevista. Mia empieza sin atribuir identidad,
 * práctica ni preferencias al despacho y aprende solo de información que el
 * abogado incorpore y apruebe durante el uso.
 */
export default function OnboardingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Status>("/api/onboarding/status")
      .then((status) => setCompleted(status.completed))
      .catch(() => setError("No se pudo preparar tu espacio. Revisa que Mia esté abierta."))
      .finally(() => setLoading(false));
  }, []);

  async function start() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await apiSend("POST", "/api/onboarding/complete", { responses: {} });
      router.push("/casos?nuevo=1");
    } catch {
      setError("No se pudo abrir tu espacio. Intenta de nuevo.");
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <WelcomeShell progress={<WelcomeProgress current={2} />} width="lg">
        <div className="space-y-5">
          <Skeleton className="mx-auto h-8 w-3/4 rounded-lg" />
          <Skeleton className="h-32 w-full rounded-2xl" />
        </div>
      </WelcomeShell>
    );
  }

  return (
    <WelcomeShell progress={<WelcomeProgress current={2} />} width="lg">
      <StepTransition stepKey={completed ? "listo" : "inicio"} direction={1}>
        <Stagger className="space-y-7 text-center">
          <StaggerItem className="space-y-3">
            <MiaLine
              text="Tu espacio está listo."
              className="text-center text-2xl font-semibold tracking-tight sm:text-3xl"
            />
            <p className="mx-auto max-w-lg text-sm leading-relaxed text-muted-foreground">
              Crea un caso y conversa con Mia. Cada documento se entrega como borrador para tu
              revisión.
            </p>
          </StaggerItem>
          <StaggerItem className="rounded-2xl border border-primary/15 bg-card/60 px-5 py-4 text-left text-sm leading-relaxed text-muted-foreground shadow-neu-raised">
            El contexto de tu firma u organización se completará con la información que aportes
            al trabajar. Puedes revisarlo en Configuración.
          </StaggerItem>
          {error ? <StaggerItem><p className="text-sm text-destructive" role="alert">{error}</p></StaggerItem> : null}
          <StaggerItem>
            {completed ? (
              <Button variant="cta" size="lg" onClick={() => router.push("/casos?nuevo=1")} className="gap-2 rounded-full px-8">
                <ArrowRight className="h-4 w-4" />
                Crear un caso
              </Button>
            ) : (
              <Button variant="cta" size="lg" onClick={start} disabled={saving} className="gap-2 rounded-full px-8">
                {saving ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Check className="h-4 w-4" />}
                {saving ? "Abriendo tu espacio…" : "Crear mi primer caso"}
              </Button>
            )}
          </StaggerItem>
        </Stagger>
      </StepTransition>
    </WelcomeShell>
  );
}
