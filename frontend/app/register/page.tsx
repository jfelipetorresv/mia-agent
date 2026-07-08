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
      router.replace("/onboarding");
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
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Scale className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Crear cuenta</h1>
          <p className="mt-2 text-sm text-muted-foreground">Crea el espacio privado de tu despacho.</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="firm">Nombre del despacho</Label>
            <Input
              id="firm"
              value={firmName}
              onChange={(e) => setFirmName(e.target.value)}
              placeholder="Lexia Abogados"
              required
            />
          </div>

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
              autoComplete="new-password"
              minLength={8}
              placeholder="Mínimo 8 caracteres"
              required
            />
          </div>

          {error ? (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          <Button type="submit" disabled={loading} className="w-full" size="lg">
            {loading ? "Creando…" : "Crear cuenta"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Ingresar
          </Link>
        </p>
      </div>
    </div>
  );
}
