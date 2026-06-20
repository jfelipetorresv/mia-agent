"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiSend, setToken } from "@/lib/api";

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
      setError(err?.message === "Error 409" ? "Ese email ya está registrado." : "No se pudo crear la cuenta.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-white px-6">
      <form onSubmit={submit} className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-gray-900">Crear cuenta</h1>
        <p className="mt-2 text-sm text-gray-500">Crea el espacio privado de tu despacho.</p>

        <label className="mt-8 block text-sm font-medium text-gray-700">Nombre del despacho</label>
        <input
          value={firmName}
          onChange={(e) => setFirmName(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          required
        />

        <label className="mt-4 block text-sm font-medium text-gray-700">Email</label>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          type="email"
          autoComplete="email"
          className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          required
        />

        <label className="mt-4 block text-sm font-medium text-gray-700">Contraseña</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          autoComplete="new-password"
          minLength={8}
          className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
          required
        />

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
        >
          {loading ? "Creando..." : "Crear cuenta"}
        </button>

        <p className="mt-5 text-center text-sm text-gray-500">
          <Link href="/login" className="font-medium text-gray-900 hover:underline">
            Ya tengo cuenta
          </Link>
        </p>
      </form>
    </div>
  );
}
