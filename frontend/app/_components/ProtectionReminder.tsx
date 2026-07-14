"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type ProtectionStatus = { recovery_key_saved: boolean };
type TauriCore = { invoke?: (command: string) => Promise<unknown> };

/** Aviso persistente: desaparece solo cuando la llave portable fue confirmada. */
export default function ProtectionReminder() {
  const [needsKey, setNeedsKey] = useState(false);
  const pathname = usePathname() || "/";

  useEffect(() => {
    const tauri = (
      window as unknown as { __TAURI__?: { core?: TauriCore } }
    ).__TAURI__;
    if (!tauri?.core?.invoke) return; // navegador: la protección es local al escritorio

    tauri.core.invoke("maintenance_status")
      .then((raw) => {
        const status = (
          typeof raw === "string" ? JSON.parse(raw) : raw
        ) as ProtectionStatus;
        setNeedsKey(!status.recovery_key_saved);
      })
      .catch(() => setNeedsKey(true));

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
