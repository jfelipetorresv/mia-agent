"use client";

import { AlertTriangle, CheckCircle2, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { shellInvoke } from "@/lib/shell";

type RuntimeNotice = { stage: string; text: string };
type RuntimeHealth = { seq: number; stage: string; text: string } | null;

// Mismo ritmo que el supervisor de la cáscara (SUPERVISOR_INTERVAL = 5s).
const POLL_MS = 5_000;

/** Estado del supervisor local. En navegador normal no aparece.
 *
 * Historia: este banner escuchaba `window.__TAURI__.event.listen("mia://progress")`,
 * pero la ventana de MIA navega a http://localhost:3100 — para Tauri v2 un ORIGEN
 * REMOTO que por el hardening deliberado (sin capability `remote`, sin
 * `dangerousRemoteUrlIpcAccess`) no recibe IPC: `window.__TAURI__` nunca existe ahí
 * y el banner llevaba muerto desde siempre (HANDOFF 2026-08-19). Ahora LEE el último
 * aviso `runtime-*` por el puente `mia-shell` (POST /runtime/health, misma allowlist
 * de Origin y rutas cerradas que Protección) con polling. En un navegador normal el
 * primer fetch falla (el protocolo no existe) y el polling se apaga solo. */
export default function RuntimeHealthBanner() {
  const [notice, setNotice] = useState<RuntimeNotice | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    // 0 = todavía sin línea base. El primer poll fija la línea base: un
    // `runtime-ok` viejo no se pinta (ruido), pero un error pendiente SÍ — antes
    // el listener se perdía todo lo emitido antes de montar la página.
    let lastSeq = 0;
    let baselined = false;

    const show = (next: RuntimeNotice) => {
      if (timer.current) clearTimeout(timer.current);
      setNotice(next);
      if (next.stage === "runtime-ok") {
        timer.current = setTimeout(() => setNotice(null), 8_000);
      }
    };

    const tick = async () => {
      let health: RuntimeHealth;
      try {
        health = await shellInvoke<RuntimeHealth>("runtime/health");
      } catch {
        // Navegador (dev) o cáscara ausente: no hay supervisor que vigilar.
        if (interval) clearInterval(interval);
        return;
      }
      if (cancelled || !health) return;
      if (!baselined) {
        baselined = true;
        lastSeq = health.seq;
        // Un problema aún vigente se muestra desde el primer render.
        if (health.stage !== "runtime-ok") show(health);
        return;
      }
      if (health.seq === lastSeq) return;
      lastSeq = health.seq;
      show(health);
    };

    tick();
    interval = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  if (!notice) return null;
  const failed = notice.stage === "runtime-error";
  const recovered = notice.stage === "runtime-ok";
  const Icon = failed ? AlertTriangle : recovered ? CheckCircle2 : LoaderCircle;

  return (
    <div
      role={failed ? "alert" : "status"}
      className={failed
        ? "border-b border-destructive/30 bg-destructive/10 px-4 py-3 text-sm"
        : recovered
          ? "border-b border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm"
          : "border-b border-warning/30 bg-warning/10 px-4 py-3 text-sm"}
    >
      <div className="mx-auto flex max-w-6xl items-center gap-2">
        <Icon className={`h-4 w-4 shrink-0 ${!failed && !recovered ? "animate-spin" : ""}`} />
        <span>{notice.text}</span>
      </div>
    </div>
  );
}
