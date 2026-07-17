"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiSend, plainMessage, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  WelcomeShell,
  StepTransition,
  Stagger,
  WelcomeField,
  MiaLine,
} from "@/app/_welcome";

type AuthResponse = { token: string; tenant_id: string };

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await apiSend<AuthResponse>("POST", "/api/auth/login", { email, password });
      setToken(res.token);
      router.replace("/");
    } catch (err: unknown) {
      // Solo se muestran mensajes que VIENEN del backend (ApiError, en llano);
      // un error de red del navegador ("Failed to fetch") jamás llega a pantalla.
      const msg = plainMessage(err, "");
      const generic = !msg || msg === "Credenciales invalidas" || msg === "Sesión expirada";
      setError(generic ? "El correo o la contraseña no coinciden." : msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    // Regreso al despacho: mismo lienzo cinematográfico, versión compacta y SIN
    // la constelación de progreso del viaje (esto no es la primera vez).
    <WelcomeShell
      width="sm"
      footer={
        <span>
          ¿Aún no tienes tu espacio?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Crear mi despacho
          </Link>
        </span>
      }
    >
      <StepTransition stepKey="entrar" direction={1}>
        {/* El propio <form> es el contenedor de stagger (as="form"): los campos,
            hijos DIRECTOS, entran escalonados en vez de todos a la vez. */}
        <Stagger as="form" onSubmit={submit} className="space-y-6">
          <WelcomeField>
            <div className="space-y-2 text-center">
              <MiaLine text="Qué bueno verte otra vez." className="text-xl sm:text-2xl" />
              <p className="text-sm text-muted-foreground">
                Entra al espacio de tu despacho.
              </p>
            </div>
          </WelcomeField>

          <WelcomeField label="Tu correo" htmlFor="email">
            <Input
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="email"
              placeholder="tu@despacho.com"
              autoFocus
              required
            />
          </WelcomeField>

          <WelcomeField label="Tu contraseña" htmlFor="password">
            <Input
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
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
              {loading ? "Entrando…" : "Entrar"}
            </Button>
          </WelcomeField>
        </Stagger>
      </StepTransition>
    </WelcomeShell>
  );
}
