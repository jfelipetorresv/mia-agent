"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { apiGet, clearToken, getToken } from "@/lib/api";

// Rutas SIN sesión (primera vez o regreso). `/activar` NO está aquí a propósito:
// es parte del viaje de bienvenida pero el abogado ya tiene sesión (viene de crear
// su despacho), así que debe exigir sesión como cualquier ruta privada.
const PUBLIC_PATHS = ["/login", "/register"];

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    let cancelled = false;
    if (isPublic) {
      setReady(true);
      return;
    }
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        await apiGet("/api/auth/me");
        if (!cancelled) setReady(true);
      } catch {
        clearToken();
        if (!cancelled) router.replace("/login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isPublic, pathname, router]);

  if (isPublic) return <>{children}</>;
  if (!ready) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden />
      </div>
    );
  }
  return <>{children}</>;
}
