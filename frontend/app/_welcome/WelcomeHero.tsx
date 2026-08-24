"use client";

import * as React from "react";
import { Search, SlidersHorizontal, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Stagger, StaggerItem } from "./MotionField";
import { useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

/**
 * Portada cinematográfica de bienvenida — el render canónico del pack
 * (docs/design/MIA-Luxury-Design-Pack/assets/onboarding_light.jpg y
 * onboarding_dark.jpg) llevado a producto. Es la PRIMERA pantalla que ve el
 * abogado recién instalado (encargo de Pipe, 2026-08-24).
 *
 * Decisión de composición (documentada porque el encargo pedía elegir con
 * criterio): los JPG del pack traen la escena COMPLETA con el título, los tres
 * pasos y el CTA ya quemados en la imagen — y con los subtextos en inglés
 * ("Create an account"…), que el copy del producto no puede heredar. Usarlos
 * como fondo entero duplicaría el título y fijaría texto no accesible y en
 * otro idioma. Por eso el texto se compone en HTML (tokens del tema, AA,
 * lector de pantalla) y de la imagen se usa SOLO la franja central de la
 * escena — el cristal con sus anillos giroscópicos — recortada de los mismos
 * JPG a `public/welcome/hero_light.jpg` / `hero_dark.jpg` (~27/50 KB). La
 * franja se funde con el fondo vivo (`bg-mesh-living`) mediante una máscara
 * radial, y levita con `animate-float`, como en el render.
 *
 * Los tres puntos del pie NO son un carrusel decorativo: reflejan las tres
 * etapas REALES que la propia portada anuncia (Regístrate → Personaliza →
 * Explora); la portada pertenece a la primera, por eso el primer punto está
 * activo. Hoy solo existe esta lámina de presentación; si algún día se añaden
 * más, los puntos pasan a navegar entre ellas.
 */
export interface WelcomeHeroProps {
  /** «Empezar ahora»: avanza al siguiente paso real del viaje (crear el despacho). */
  onStart: () => void;
  /** «Omitir»: salta la presentación y deja al abogado donde el flujo aterriza hoy. */
  onSkip: () => void;
  className?: string;
}

const PASOS = [
  { icon: UserRound, title: "Regístrate", hint: "Crea tu cuenta" },
  { icon: SlidersHorizontal, title: "Personaliza", hint: "Ajusta tus preferencias" },
  { icon: Search, title: "Explora", hint: "Haz tu primera consulta" },
];

// Máscara radial que funde los bordes del recorte con el fondo vivo del lienzo.
const FEATHER_MASK =
  "radial-gradient(ellipse 58% 58% at 50% 50%, black 38%, transparent 78%)";

export default function WelcomeHero({ onStart, onSkip, className }: WelcomeHeroProps) {
  const reduce = useReducedMotion();

  return (
    <Stagger className={cn("flex flex-col items-center gap-2 text-center", className)}>
      {/* Titular del render: «Bienvenido a» en el ÚNICO dorado permitido del
          producto (--accent-gold, reservado a esta portada) y «Mia.» en el
          color de texto del tema. */}
      <StaggerItem className="space-y-2">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-6xl">
          <span className="text-accent-gold">Bienvenido a</span>{" "}
          <span className="text-foreground">Mia.</span>
        </h1>
        <p className="text-xl text-muted-foreground sm:text-2xl">Tu asistente jurídica</p>
      </StaggerItem>

      {/* Pieza central 3D: el cristal con anillos giroscópicos del pack, una
          imagen por tema. Decorativa (alt vacío): el texto ya lo dice todo. */}
      <StaggerItem>
        <div
          className={cn("select-none", !reduce && "animate-float")}
          style={{ WebkitMaskImage: FEATHER_MASK, maskImage: FEATHER_MASK }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/welcome/hero_light.jpg"
            alt=""
            width={633}
            height={380}
            draggable={false}
            className="block h-auto w-[19rem] max-w-full sm:w-[30rem] dark:hidden"
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/welcome/hero_dark.jpg"
            alt=""
            width={633}
            height={380}
            draggable={false}
            className="hidden h-auto w-[19rem] max-w-full sm:w-[30rem] dark:block"
          />
        </div>
      </StaggerItem>

      {/* Fila de los tres pasos del viaje, como los anuncia el render. */}
      <StaggerItem>
        <div className="flex flex-wrap items-start justify-center gap-x-10 gap-y-5">
          {PASOS.map((paso) => {
            const Icon = paso.icon;
            return (
              <div key={paso.title} className="flex items-center gap-3 text-left">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-card/70 shadow-neu-sunken">
                  <Icon className="h-5 w-5 text-primary" aria-hidden />
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold uppercase tracking-wider text-foreground">
                    {paso.title}
                  </span>
                  <span className="text-xs text-muted-foreground">{paso.hint}</span>
                </span>
              </div>
            );
          })}
        </div>
      </StaggerItem>

      {/* CTA píldora teal del pack + salida secundaria. */}
      <StaggerItem className="mt-4 flex flex-col items-center gap-3">
        <Button
          variant="cta"
          size="lg"
          onClick={onStart}
          className="rounded-full px-10 uppercase tracking-wide"
        >
          Empezar ahora
        </Button>
        <button
          type="button"
          onClick={onSkip}
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          Omitir
        </button>
      </StaggerItem>

      {/* Etapas del viaje (puntos del render): esta portada es la etapa 1 de 3. */}
      <StaggerItem>
        <div
          className="mt-2 flex items-center justify-center gap-2"
          role="img"
          aria-label="Etapa 1 de 3: Regístrate. Siguen Personaliza y Explora."
        >
          <span aria-hidden className="h-1.5 w-6 rounded-full bg-primary" />
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
        </div>
      </StaggerItem>
    </Stagger>
  );
}
