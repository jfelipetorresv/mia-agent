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
const ICON_SIZE: Record<BrandSize, { box: string; text: string; subtitle: string }> = {
  sm: { box: "h-9 w-9 p-1.5 rounded-xl", text: "text-base", subtitle: "text-[7.5px]" },
  md: { box: "h-11 w-11 p-2 rounded-2xl", text: "text-xl", subtitle: "text-[8.5px]" },
  lg: { box: "h-14 w-14 p-2.5 rounded-2xl", text: "text-3xl", subtitle: "text-[10px]" },
  xl: { box: "h-20 w-20 p-3.5 rounded-3xl", text: "text-5xl", subtitle: "text-[12px]" },
};

export interface BrandMarkProps {
  /** Tamaño del logotipo. Default `md`. */
  size?: BrandSize;
  /** Halo que respira suavemente. */
  breathing?: boolean;
  /** Resplandor plateado. */
  glow?: boolean;
  /** Enlace a ruta. */
  href?: string;
  className?: string;
}

export default function BrandMark({
  size = "md",
  breathing = false,
  glow = false,
  href,
  className,
}: BrandMarkProps) {
  const s = ICON_SIZE[size];

  const word = (
    <span className="inline-flex items-center gap-3 group">
      {/* Emblem Octaedro de Cristal 3D Monocromo (Opción A) */}
      <span className={cn("relative bg-gradient-to-br from-slate-900 via-slate-950 to-black border border-white/30 shadow-[0_6px_20px_rgba(0,0,0,0.4),_inset_0_1px_1px_rgba(255,255,255,0.4)] flex items-center justify-center overflow-hidden transition-transform duration-300 group-hover:scale-105 shrink-0", s.box)}>
        <svg viewBox="0 0 100 100" className="w-full h-full filter drop-shadow-[0_0_6px_rgba(255,255,255,0.6)]">
          <defs>
            <linearGradient id={`silverGradBM_${size}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="50%" stopColor="#cbd5e1" />
              <stop offset="100%" stopColor="#64748b" />
            </linearGradient>
          </defs>
          <ellipse cx="50" cy="50" rx="42" ry="16" fill="none" stroke={`url(#silverGradBM_${size})`} strokeWidth="4" transform="rotate(-20 50 50)" />
          <circle cx="50" cy="50" r="14" fill="#ffffff" opacity="0.85" />
          <path d="M 50 15 L 75 50 L 50 85 L 25 50 Z" fill="none" stroke={`url(#silverGradBM_${size})`} strokeWidth="5" strokeLinejoin="round" />
          <path d="M 25 50 L 75 50 M 50 15 L 50 85" stroke="#ffffff" strokeWidth="2" opacity="0.9" />
        </svg>
      </span>

      <span className="flex flex-col">
        <span className={cn("font-serif font-extrabold tracking-[0.15em] leading-none text-foreground", s.text)}>
          MIA
        </span>
        <span className={cn("uppercase tracking-[0.25em] font-extrabold text-muted-foreground leading-tight mt-0.5", s.subtitle)}>
          Legal Intelligence
        </span>
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
