"use client";

// Redirige a /onboarding la primera vez (antes de que el despacho tenga SOUL.md).
// Verifica GET /api/onboarding/status. Si el backend no responde, no hace nada
// (no se queda en un bucle de redirección). Se monta en el layout raíz.

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";

export default function OnboardingGate() {
  const router = useRouter();
  const pathname = usePathname() || "/";

  useEffect(() => {
    if (pathname.startsWith("/login") || pathname.startsWith("/register")) return;
    if (pathname.startsWith("/onboarding")) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await apiGet<{ completed: boolean }>("/api/onboarding/status");
        if (!cancelled && !st.completed) router.replace("/onboarding");
      } catch {
        /* backend no disponible: no redirige */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  return null;
}
