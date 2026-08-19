"use client";

import { AlertTriangle, CheckCircle2, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type RuntimeNotice = { stage: string; text: string };
type Unlisten = () => void;
type TauriEvent = {
  listen?: (
    event: string,
    handler: (event: { payload?: RuntimeNotice }) => void,
  ) => Promise<Unlisten>;
};

/** Estado del supervisor local. En navegador normal no aparece. */
export default function RuntimeHealthBanner() {
  const [notice, setNotice] = useState<RuntimeNotice | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const tauri = (
      window as unknown as { __TAURI__?: { event?: TauriEvent } }
    ).__TAURI__;
    if (!tauri?.event?.listen) return;

    let unlisten: Unlisten | undefined;
    let cancelled = false;
    tauri.event.listen("mia://progress", (event) => {
      const next = event.payload;
      if (!next?.stage.startsWith("runtime-")) return;
      if (timer.current) clearTimeout(timer.current);
      setNotice(next);
      if (next.stage === "runtime-ok") {
        timer.current = setTimeout(() => setNotice(null), 8_000);
      }
    }).then((fn) => {
      if (cancelled) fn();
      else unlisten = fn;
    }).catch(() => undefined);

    return () => {
      cancelled = true;
      unlisten?.();
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
