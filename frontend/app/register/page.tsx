"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, apiSend, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  WelcomeShell,
  WelcomeProgress,
  StepTransition,
  Stagger,
  WelcomeField,
  MiaLine,
} from "@/app/_welcome";

type AuthResponse = { token: string; tenant_id: string };

export default function RegisterPage() {
  const router = useRouter();
  const [firmName, setFirmName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await apiSend<AuthResponse>("POST", "/api/auth/register", {
        firm_name: firmName,
        email,
        password,
      });
      setToken(res.token);
      // Primer viaje: tras crear el despacho seguimos a la activación de Mia,
      // no directo a conocerte. La navegación explícita la dispara esta pantalla.
      router.replace("/activar");
    } catch (err: any) {
      // Solo mensajes del backend (ApiError, en llano — p. ej. "Email ya registrado"
      // o el freno anti fuerza-bruta); un error de red jamás se muestra en crudo.
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setError(msg || "No se pudo crear la cuenta.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <WelcomeShell
      progress={<WelcomeProgress current={0} />}
      footer={
        <span>
          ¿Ya trabajas con Mia?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Entrar
          </Link>
        </span>
      }
    >
      <StepTransition stepKey="crear" direction={1}>
        {/* El propio <form> es el contenedor de stagger (as="form"): así cada
            WelcomeField es hijo DIRECTO y su entrada se escalona de verdad. */}
        <Stagger as="form" onSubmit={submit} className="space-y-6">
          <WelcomeField>
            <div className="space-y-2 text-center">
              <MiaLine
                text="Soy Mia. Creemos el espacio de tu despacho."
                className="text-xl sm:text-2xl"
              />
              <p className="text-sm text-muted-foreground">
                Un lugar privado, solo tuyo, para trabajar tus casos conmigo.
              </p>
            </div>
          </WelcomeField>

          <WelcomeField label="¿Cómo se llama tu despacho?" htmlFor="firm">
            <Input
              id="firm"
              value={firmName}
              onChange={(e) => setFirmName(e.target.value)}
              placeholder="Ej: Fajardo & Asociados"
              autoFocus
              required
            />
          </WelcomeField>

          <WelcomeField label="Tu correo" htmlFor="email">
            <Input
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="email"
              placeholder="tu@despacho.com"
              required
            />
          </WelcomeField>

          <WelcomeField label="Crea una contraseña" htmlFor="password" hint="Mínimo 8 caracteres.">
            <Input
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="new-password"
              minLength={8}
              placeholder="••••••••"
              required
            />
          </WelcomeField>

          {error ? (
            <WelcomeField>
              <p
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {error}
              </p>
            </WelcomeField>
          ) : null}

          <WelcomeField>
            <Button
              type="submit"
              disabled={loading}
              variant="cta"
              size="lg"
              className="w-full"
            >
              {loading ? "Creando tu espacio…" : "Crear mi despacho"}
            </Button>
          </WelcomeField>
        </Stagger>
      </StepTransition>
    </WelcomeShell>
  );
}
