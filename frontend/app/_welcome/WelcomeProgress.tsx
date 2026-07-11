"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { POP_SPRING, useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

export interface WelcomeProgressProps {
  /** Etiquetas de los pasos del viaje completo. Por defecto, el viaje de 4 pasos. */
  steps?: string[];
  /** Índice (0-based) del paso actual. Los anteriores se muestran cumplidos. */
  current: number;
  className?: string;
}

// Los 4 pasos del viaje de bienvenida. Fuente única de verdad: se re-exporta
// desde `_welcome` para que otras pantallas (p. ej. /activar) la importen en vez
// de duplicarla y arriesgar que se desincronicen.
export const JOURNEY_STEPS = ["Tu despacho", "Activar", "Conocerte", "Listo"];

/**
 * Progreso "constelación" que abarca TODO el viaje de bienvenida (no un % por
 * pantalla). Nodos conectados por un hilo que se tiñe de teal al avanzar:
 *  - cumplido → círculo teal con check que hace micro-pop (spring).
 *  - activo   → círculo con halo `.glow-teal` y un punto que late suave.
 *  - próximo  → círculo tenue con su número.
 * Elegante y legible; nunca infantil. Respeta prefers-reduced-motion.
 */
export default function WelcomeProgress({
  steps = JOURNEY_STEPS,
  current,
  className,
}: WelcomeProgressProps) {
  const reduce = useReducedMotion();

  return (
    <ol className={cn("flex w-full items-start", className)} aria-label="Progreso de la bienvenida">
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <React.Fragment key={label}>
            <li
              className="flex shrink-0 flex-col items-center gap-2"
              aria-current={active ? "step" : undefined}
            >
              <div
                className={cn(
                  "relative flex h-8 w-8 items-center justify-center rounded-full border text-xs font-medium transition-colors duration-500",
                  done && "border-primary bg-primary/20 text-primary",
                  active && "glow-teal border-primary bg-primary/10 text-primary",
                  !done && !active && "border-border bg-transparent text-muted-foreground"
                )}
              >
                {done ? (
                  <motion.span
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={reduce ? { duration: 0.2 } : POP_SPRING}
                  >
                    <Check className="h-4 w-4" strokeWidth={2.5} />
                  </motion.span>
                ) : active ? (
                  <motion.span
                    className="h-2 w-2 rounded-full bg-primary"
                    animate={reduce ? undefined : { opacity: [0.5, 1, 0.5], scale: [1, 1.25, 1] }}
                    transition={reduce ? undefined : { duration: 2.2, ease: "easeInOut", repeat: Infinity }}
                  />
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>
              <span
                className={cn(
                  "whitespace-nowrap text-[11px] tracking-wide transition-colors duration-500",
                  active ? "text-foreground" : done ? "text-primary/80" : "text-muted-foreground"
                )}
              >
                {label}
              </span>
            </li>

            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "mt-4 h-px flex-1 rounded-full transition-colors duration-500",
                  done ? "bg-primary/70" : "bg-border"
                )}
              />
            )}
          </React.Fragment>
        );
      })}
    </ol>
  );
}
