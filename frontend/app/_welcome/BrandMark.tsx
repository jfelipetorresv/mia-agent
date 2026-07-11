"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

type BrandSize = "sm" | "md" | "lg" | "xl";

/**
 * Escalas del wordmark. `sm` reproduce EXACTAMENTE el logotipo actual de la
 * sidebar (text-xl, tracking 0.3em) para que el refactor no cambie su look.
 * `xl` emula la pantalla de arranque de escritorio (~72px, tracking 0.14–0.16em).
 */
const SIZE: Record<BrandSize, { text: string; tracking: string; halo: string }> = {
  sm: { text: "text-xl", tracking: "tracking-[0.3em]", halo: "blur-lg" },
  md: { text: "text-3xl", tracking: "tracking-[0.28em]", halo: "blur-xl" },
  lg: { text: "text-5xl", tracking: "tracking-[0.2em]", halo: "blur-2xl" },
  xl: { text: "text-7xl", tracking: "tracking-[0.16em]", halo: "blur-3xl" },
};

export interface BrandMarkProps {
  /** Tamaño del wordmark. `sm` = idéntico al de la sidebar. Default `md`. */
  size?: BrandSize;
  /** Halo teal que "respira" detrás del wordmark (presencia viva de Mia). */
  breathing?: boolean;
  /** Resplandor estático tipo splash de escritorio (text-shadow teal). */
  glow?: boolean;
  /** Si se pasa, el wordmark enlaza a esa ruta (como en la sidebar → "/"). */
  href?: string;
  className?: string;
}

/**
 * Wordmark compartido "MIA" — la M y la A en el color de texto del tema y la I
 * en teal de marca (#2EA9A9). Componente único reutilizable en sidebar, splash
 * web y toda la bienvenida. Solo anima opacity/scale del halo (accesible).
 */
export default function BrandMark({
  size = "md",
  breathing = false,
  glow = false,
  href,
  className,
}: BrandMarkProps) {
  const reduce = useReducedMotion();
  const s = SIZE[size];

  const word = (
    <span className="relative inline-flex items-center justify-center">
      {breathing && (
        <motion.span
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-0 -z-10 rounded-full bg-primary/30",
            s.halo
          )}
          initial={false}
          animate={
            reduce
              ? { opacity: 0.4, scale: 1 }
              : { opacity: [0.35, 0.7, 0.35], scale: [1, 1.12, 1] }
          }
          transition={
            reduce
              ? { duration: 0 }
              : { duration: 2.4, ease: "easeInOut", repeat: Infinity }
          }
        />
      )}
      <span
        className={cn(
          "relative select-none font-light uppercase leading-none text-foreground",
          s.text,
          s.tracking,
          glow && "[text-shadow:0_0_34px_rgba(0,128,128,0.45)]"
        )}
      >
        M<span className="font-semibold text-[#2EA9A9]">I</span>A
      </span>
    </span>
  );

  if (href) {
    return (
      <Link href={href} className={cn("inline-flex items-center", className)} aria-label="MIA">
        {word}
      </Link>
    );
  }
  return <span className={cn("inline-flex items-center", className)}>{word}</span>;
}
