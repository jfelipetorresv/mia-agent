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
    <span className="inline-flex items-center gap-3.5 group">
      <span className="relative h-11 w-11 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-950 to-black border border-white/30 shadow-[0_6px_20px_rgba(0,0,0,0.3),_inset_0_1px_1px_rgba(255,255,255,0.4)] flex items-center justify-center p-2 overflow-hidden transition-transform duration-300 group-hover:scale-105 shrink-0">
        <svg viewBox="0 0 100 100" className="w-full h-full filter drop-shadow-[0_0_6px_rgba(255,255,255,0.6)]">
          <defs>
            <linearGradient id="silverGradBM" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="50%" stopColor="#cbd5e1" />
              <stop offset="100%" stopColor="#64748b" />
            </linearGradient>
          </defs>
          <ellipse cx="50" cy="50" rx="42" ry="16" fill="none" stroke="url(#silverGradBM)" strokeWidth="4" transform="rotate(-20 50 50)" />
          <circle cx="50" cy="50" r="14" fill="#ffffff" opacity="0.85" />
          <path d="M 50 15 L 75 50 L 50 85 L 25 50 Z" fill="none" stroke="url(#silverGradBM)" strokeWidth="5" strokeLinejoin="round" />
          <path d="M 25 50 L 75 50 M 50 15 L 50 85" stroke="#ffffff" strokeWidth="2" opacity="0.9" />
        </svg>
      </span>
      <span className="flex flex-col">
        <span className="font-serif font-extrabold text-xl tracking-[0.15em] leading-none text-slate-900">
          MIA
        </span>
        <span className="text-[8.5px] uppercase tracking-[0.25em] font-extrabold text-slate-500 leading-tight mt-0.5">
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
