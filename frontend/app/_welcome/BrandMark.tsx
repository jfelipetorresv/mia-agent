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
    <span className="inline-flex items-center gap-3 group">
      <span className="relative h-10 w-10 rounded-2xl bg-gradient-to-br from-white via-slate-50 to-slate-100 border border-amber-300/40 shadow-[0_6px_16px_rgba(13,122,130,0.15),_inset_0_1px_2px_rgba(255,255,255,1)] flex items-center justify-center p-2 overflow-hidden transition-transform duration-300 group-hover:scale-105 shrink-0">
        <span className="absolute inset-0 bg-gradient-to-tr from-teal-500/15 via-amber-400/10 to-transparent"></span>
        <svg viewBox="0 0 100 100" className="w-full h-full filter drop-shadow-[0_2px_4px_rgba(13,122,130,0.3)]">
          <defs>
            <linearGradient id="logoGoldBM" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#c5a059" />
              <stop offset="50%" stopColor="#e5c887" />
              <stop offset="100%" stopColor="#9a7632" />
            </linearGradient>
            <linearGradient id="logoTealBM" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0d7a82" />
              <stop offset="100%" stopColor="#00e5ff" />
            </linearGradient>
          </defs>
          <path d="M 20 75 L 20 25 L 50 55 L 80 25 L 80 75" fill="none" stroke="url(#logoTealBM)" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M 20 25 L 50 55 L 80 25" fill="none" stroke="url(#logoGoldBM)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="50" cy="55" r="4" fill="#00e5ff" />
        </svg>
      </span>
      <span className="flex flex-col">
        <span className="font-serif font-extrabold text-xl tracking-widest leading-none bg-gradient-to-r from-amber-700 via-amber-600 to-slate-900 bg-clip-text text-transparent">
          MIA
        </span>
        <span className="text-[9px] uppercase tracking-widest font-extrabold text-teal-800 leading-tight mt-0.5">
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
