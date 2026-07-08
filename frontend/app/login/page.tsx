"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Scale } from "lucide-react";
import { ApiError, apiSend, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
    } catch (err: any) {
      // Solo se muestran mensajes que VIENEN del backend (ApiError, en llano);
      // un error de red del navegador ("Failed to fetch") jamás llega a pantalla.
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      const generic = !msg || msg === "Credenciales invalidas" || msg === "Sesión expirada";
      setError(generic ? "Email o contraseña incorrectos." : msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Scale className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Bienvenido a Mia</h1>
          <p className="mt-2 text-sm text-muted-foreground">Tu asistente jurídica. Accede al espacio de tu despacho.</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="email"
              placeholder="tu@despacho.com"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Contraseña</Label>
            <Input
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              required
            />
          </div>

          {error ? (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          <Button type="submit" disabled={loading} className="w-full" size="lg">
            {loading ? "Ingresando…" : "Ingresar"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          ¿Aún no tienes cuenta?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Crear cuenta
          </Link>
        </p>
      </div>
    </div>
  );
}
