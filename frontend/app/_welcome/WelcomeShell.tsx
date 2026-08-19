"use client";

import * as React from "react";
import { motion } from "framer-motion";
import BrandMark from "./BrandMark";
import { useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

export interface WelcomeShellProps {
  /** Contenido del paso actual (formulario, pregunta, mensaje…). */
  children: React.ReactNode;
  /** Slot del progreso "constelación" (normalmente `<WelcomeProgress/>`). */
  progress?: React.ReactNode;
  /** Pie opcional: enlaces secundarios ("¿Ya tienes cuenta?", "Lo haré después"). */
  footer?: React.ReactNode;
  /** Oculta el wordmark superior si el paso ya lo muestra en grande. Default false. */
  hideBrand?: boolean;
  /** Tamaño máximo del contenido central. Default "md" (formularios). */
  width?: "sm" | "md" | "lg";
  className?: string;
}

const WIDTH: Record<NonNullable<WelcomeShellProps["width"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-xl",
};

/**
 * Lienzo de pantalla completa para TODA la primera vez del abogado.
 *
 * Look: sigue el tema del usuario (claro/oscuro/sistema). Antes se forzaba el
 * scope `dark` + fondo #060606 aquí, así que la primera vez del abogado salía
 * negra AUNQUE hubiera elegido claro — y el resto de la app sí era clara. Esa
 * incoherencia era la queja #1 de Pipe (2026-08-19): el diseño claro aprobado
 * no se veía nunca en la bienvenida. Ahora el lienzo usa `bg-background` y los
 * tokens resuelven en la versión que el abogado eligió, en ambos temas.
 * Sobre el lienzo: `.bg-aurora` + dos blobs radiales (teal y verde CTA) en
 * deriva LENTA y continua (loop infinito, suave). Arriba el wordmark MIA
 * "respirando". Centro: el paso. Sobre el paso: el progreso.
 *
 * Todo el movimiento es transform/opacity y respeta prefers-reduced-motion
 * (blobs estáticos). Premium, calmado, con profundidad; nunca saturado.
 */
export default function WelcomeShell({
  children,
  progress,
  footer,
  hideBrand = false,
  width = "md",
  className,
}: WelcomeShellProps) {
  const reduce = useReducedMotion();

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Lavado radial base de marca. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-aurora" />

      {/* Blob teal — deriva amplia y muy lenta. */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -left-48 -top-40 h-[46rem] w-[46rem] rounded-full blur-3xl"
        style={{
          backgroundImage:
            "radial-gradient(circle at center, hsl(var(--primary) / 0.22), transparent 65%)",
        }}
        initial={false}
        animate={reduce ? undefined : { x: [0, 70, -20, 0], y: [0, 50, 90, 0], scale: [1, 1.12, 1.04, 1] }}
        transition={reduce ? undefined : { duration: 28, ease: "easeInOut", repeat: Infinity }}
      />

      {/* Blob verde CTA — más pequeño, ritmo distinto para que no "lata" con el teal. */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -bottom-48 -right-40 h-[40rem] w-[40rem] rounded-full blur-3xl"
        style={{
          backgroundImage:
            "radial-gradient(circle at center, hsl(var(--cta) / 0.14), transparent 60%)",
        }}
        initial={false}
        animate={reduce ? undefined : { x: [0, -50, 20, 0], y: [0, -40, -70, 0], scale: [1, 1.08, 1.15, 1] }}
        transition={reduce ? undefined : { duration: 34, ease: "easeInOut", repeat: Infinity }}
      />

      {/* Viñeta sutil para asentar el centro y dar profundidad (por tema). */}
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-vignette-welcome" />

      {/* Contenido. */}
      <div className={cn("relative z-10 flex min-h-screen flex-col items-center px-6 py-10 sm:py-12", className)}>
        {!hideBrand && (
          <header className="shrink-0">
            <BrandMark size="md" />
          </header>
        )}

        {progress && <div className="mt-8 w-full max-w-lg shrink-0">{progress}</div>}

        <main className="flex w-full flex-1 items-center justify-center py-8">
          <div className={cn("w-full", WIDTH[width])}>{children}</div>
        </main>

        {footer && <footer className="shrink-0 pt-2 text-center text-sm text-muted-foreground">{footer}</footer>}
      </div>
    </div>
  );
}
