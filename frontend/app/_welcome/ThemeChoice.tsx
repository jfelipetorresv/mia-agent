"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { getStoredTheme, setTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * Elección de apariencia (claro/oscuro) para la PRIMERA VEZ del abogado.
 *
 * Por qué existe: hasta ahora la única forma de elegir tema vivía en el menú
 * lateral, que la primera vez todavía no se ha visto. El abogado recorría alta,
 * activación y entrevista con el tema que le tocara y descubría que se podía
 * cambiar al final del viaje.
 *
 * Persistencia: reutiliza EXACTAMENTE el mecanismo del producto — `lib/theme`
 * (localStorage `mia-theme` + clase `.dark` en <html>), el mismo que usa
 * `app/_components/ThemeToggle`. No hay un segundo almacenamiento.
 *
 * Accesibilidad: son dos `<button>` reales dentro de un grupo etiquetado, así
 * que el foco, Tab y Enter/Espacio funcionan sin JavaScript propio de teclado.
 * `aria-pressed` comunica cuál está elegido.
 */
export interface ThemeChoiceProps {
  /**
   * `pill`  → conmutador compacto de dos iconos (cabecera del lienzo).
   * `cards` → dos tarjetas con etiqueta (paso de bienvenida del onboarding).
   */
  variant?: "pill" | "cards";
  className?: string;
}

const OPTIONS: { value: Exclude<Theme, "system">; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
];

export default function ThemeChoice({ variant = "pill", className }: ThemeChoiceProps) {
  // "system" es un estado legítimo: mientras el abogado no elija, ninguna de las
  // dos opciones se marca como elegida, pero sí se resalta la que está viéndose.
  const [stored, setStored] = React.useState<Theme>("system");
  const [isDark, setIsDark] = React.useState(false);

  const syncIsDark = React.useCallback(() => {
    if (typeof document !== "undefined") {
      setIsDark(document.documentElement.classList.contains("dark"));
    }
  }, []);

  React.useEffect(() => {
    setStored(getStoredTheme());
    syncIsDark();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", syncIsDark);
    return () => mq.removeEventListener("change", syncIsDark);
  }, [syncIsDark]);

  function choose(theme: Exclude<Theme, "system">) {
    setTheme(theme);
    setStored(theme);
    syncIsDark();
  }

  const resolved: Exclude<Theme, "system"> = isDark ? "dark" : "light";

  if (variant === "cards") {
    return (
      <div
        role="group"
        aria-label="Apariencia de Mia"
        className={cn("mx-auto flex max-w-sm justify-center gap-4", className)}
      >
        {OPTIONS.map((o) => {
          const Icon = o.icon;
          const active = stored === o.value || (stored === "system" && resolved === o.value);
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => choose(o.value)}
              aria-pressed={stored === o.value}
              className={cn(
                "flex flex-1 flex-col items-center gap-2 rounded-2xl bg-card/70 p-4 transition-all duration-300",
                active
                  ? "text-primary shadow-neu-sunken"
                  : "text-muted-foreground shadow-neu-raised hover:text-primary"
              )}
            >
              <Icon className="h-6 w-6" />
              <span className="type-control">{o.label}</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Apariencia de Mia"
      className={cn("inline-flex items-center gap-1 rounded-full bg-card/70 p-1 shadow-neu-raised", className)}
    >
      {OPTIONS.map((o) => {
        const Icon = o.icon;
        const active = stored === o.value || (stored === "system" && resolved === o.value);
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => choose(o.value)}
            aria-pressed={stored === o.value}
            title={o.label}
            className={cn(
              "rounded-full p-2 transition-all duration-300",
              active ? "text-primary shadow-neu-sunken" : "text-muted-foreground hover:text-primary"
            )}
          >
            <Icon className="h-4 w-4" />
            <span className="sr-only">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
