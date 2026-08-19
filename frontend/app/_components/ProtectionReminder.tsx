"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { DESKTOP_ONLY_MESSAGE, shellInvoke } from "@/lib/shell";

type ProtectionStatus = { recovery_key_saved: boolean };

/** Aviso persistente: desaparece solo cuando la llave portable fue confirmada. */
export default function ProtectionReminder() {
  const [needsKey, setNeedsKey] = useState(false);
  const pathname = usePathname() || "/";

  useEffect(() => {
    shellInvoke<ProtectionStatus>("maintenance/status")
      .then((status) => setNeedsKey(!status.recovery_key_saved))
      // Navegador (dev): la protección es local al escritorio — sin aviso.
      .catch((err) =>
        setNeedsKey(!(err instanceof Error && err.message === DESKTOP_ONLY_MESSAGE)),
      );

    const confirmed = () => setNeedsKey(false);
    window.addEventListener("mia:recovery-key-confirmed", confirmed);
    return () => window.removeEventListener("mia:recovery-key-confirmed", confirmed);
  }, []);

  if (!needsKey || pathname.startsWith("/login") || pathname.startsWith("/register")) {
    return null;
  }

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-4 py-3 text-sm text-foreground">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0 text-warning" />
          Guarda la llave de recuperación para poder recuperar Mia si cambias o pierdes este equipo.
        </span>
        <Link
          href="/configurar#proteccion"
          className="font-medium text-primary underline underline-offset-2"
        >
          Guardar llave ahora
        </Link>
      </div>
    </div>
  );
}
