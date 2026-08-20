"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

export interface CelebrationProps {
  /** Dispara la celebración. Default true (se activa al montar). */
  active?: boolean;
  /** Nº de partículas del estallido. Default 28. */
  particleCount?: number;
  /**
   * A pantalla completa (`fixed inset-0`) en vez de acotarse al contenedor padre.
   * Úsalo cuando el contenido vive en una columna estrecha (max-w) y quieres que el
   * estallido cubra toda la ventana en lugar de recortarse a la columna.
   */
  fullscreen?: boolean;
  className?: string;
}

// Solo tokens: los dos hex que había aquí (#98e4bf, #2EA9A9) eran los extremos del
// degradado verde neón anterior y sobrevivían al cambio de paleta pintando confeti
// de un color que ya no existe en el producto.
const COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--cta))",
  "hsl(var(--cta-gradient-from))",
  "hsl(var(--accent-gold))",
];

interface Particle {
  angle: number;
  distance: number;
  size: number;
  color: string;
  delay: number;
  duration: number;
  drift: number;
}

/**
 * Remate de la pantalla final: capa decorativa a pantalla completa
 * (`pointer-events-none`, se coloca DETRÁS del mensaje de "Listo"). Estallido de
 * partículas teal/CTA que salen del centro, más un anillo de destello que se
 * expande. Hecho 100% con framer-motion + CSS, SIN dependencias nuevas.
 *
 * Las partículas se generan tras el montaje (evita desajuste de hidratación por
 * Math.random). Con prefers-reduced-motion: sin partículas, solo un resplandor
 * teal que aparece con calma.
 */
export default function Celebration({
  active = true,
  particleCount = 28,
  fullscreen = false,
  className,
}: CelebrationProps) {
  const reduce = useReducedMotion();
  const [particles, setParticles] = React.useState<Particle[]>([]);

  React.useEffect(() => {
    if (!active || reduce) return;
    const next: Particle[] = Array.from({ length: particleCount }, () => ({
      angle: Math.random() * Math.PI * 2,
      distance: 120 + Math.random() * 200,
      size: 5 + Math.random() * 8,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      delay: Math.random() * 0.15,
      duration: 1 + Math.random() * 0.9,
      drift: (Math.random() - 0.5) * 60,
    }));
    setParticles(next);
  }, [active, reduce, particleCount]);

  if (!active) return null;

  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none z-0 overflow-hidden",
        fullscreen ? "fixed inset-0" : "absolute inset-0",
        className,
      )}
    >
      {/* Resplandor central (siempre, también en modo reducido). */}
      <motion.div
        className="absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
        style={{ backgroundImage: "radial-gradient(circle, hsl(var(--primary) / 0.35), transparent 70%)" }}
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: reduce ? 0.5 : [0, 0.7, 0.4], scale: reduce ? 1 : [0.6, 1.15, 1] }}
        transition={{ duration: reduce ? 0.6 : 1.4, ease: "easeOut" }}
      />

      {!reduce && (
        <>
          {/* Anillo de destello que se expande. */}
          <motion.div
            className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border-2"
            style={{ borderColor: "hsl(var(--primary) / 0.5)" }}
            initial={{ opacity: 0.8, scale: 0.2 }}
            animate={{ opacity: 0, scale: 4 }}
            transition={{ duration: 1, ease: "easeOut" }}
          />

          {/* Partículas. */}
          <div className="absolute left-1/2 top-1/2 h-0 w-0">
            {particles.map((p, i) => (
              <motion.span
                key={i}
                className="absolute rounded-full"
                style={{ width: p.size, height: p.size, backgroundColor: p.color }}
                initial={{ x: 0, y: 0, opacity: 0, scale: 0 }}
                animate={{
                  x: Math.cos(p.angle) * p.distance + p.drift,
                  y: Math.sin(p.angle) * p.distance,
                  opacity: [0, 1, 1, 0],
                  scale: [0, 1, 0.9, 0.4],
                }}
                transition={{ duration: p.duration, delay: p.delay, ease: [0.16, 1, 0.3, 1] }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
