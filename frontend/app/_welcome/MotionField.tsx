"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  MIA_EASE,
  STEP_DURATION,
  stepVariants,
  stepVariantsReduced,
  staggerContainer,
  staggerItem,
  staggerItemReduced,
  useReducedMotion,
} from "./motion";

/**
 * Helpers de movimiento compartidos para las pantallas de la bienvenida.
 * Las pantallas solo importan estos wrappers; no tocan framer-motion directo.
 */

export interface StepTransitionProps {
  /** Clave única del paso actual. Al cambiar, dispara la transición. */
  stepKey: React.Key;
  /** >= 0 avanzar, < 0 retroceder. Controla la dirección del deslizamiento. */
  direction?: number;
  children: React.ReactNode;
  className?: string;
}

/**
 * Transición direccional entre pasos con AnimatePresence mode="wait":
 * el paso saliente se va y luego entra el nuevo (x:±24, opacidad, ~0.35s,
 * ease de marca). Respeta prefers-reduced-motion (solo cross-fade).
 *
 * Uso: envolver el contenido del paso y cambiar `stepKey` al navegar.
 */
export function StepTransition({ stepKey, direction = 1, children, className }: StepTransitionProps) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence mode="wait" custom={direction} initial={false}>
      <motion.div
        key={stepKey}
        custom={direction}
        variants={reduce ? stepVariantsReduced : stepVariants}
        initial="enter"
        animate="center"
        exit="exit"
        transition={{ duration: reduce ? 0.2 : STEP_DURATION, ease: MIA_EASE }}
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

export interface StaggerProps {
  children: React.ReactNode;
  className?: string;
  /**
   * Elemento a renderizar. Por defecto `"div"`. Usa `"form"` cuando los campos
   * viven en un formulario: así el propio `<form>` ES el contenedor de stagger y
   * sus campos (hijos DIRECTOS) se escalonan. Si en su lugar se anida un `<form>`
   * plano dentro del Stagger, el `staggerChildren` no alcanza a esos campos y
   * todos entran a la vez.
   */
  as?: "div" | "form";
  /** Manejador de envío (solo aplica con `as="form"`). */
  onSubmit?: React.FormEventHandler<HTMLFormElement>;
}

/**
 * Contenedor que escalona la entrada de sus hijos `<StaggerItem>`.
 * Reemplaza los `animationDelay` inline manuales del onboarding actual.
 */
export function Stagger({ children, className, as = "div", onSubmit }: StaggerProps) {
  // Cast a ElementType: evita el error de "unión de tipos demasiado compleja" al
  // alternar entre motion.form y motion.div en el mismo JSX.
  const Comp = (as === "form" ? motion.form : motion.div) as React.ElementType;
  return (
    <Comp
      variants={staggerContainer}
      initial="hidden"
      animate="show"
      className={className}
      onSubmit={onSubmit}
    >
      {children}
    </Comp>
  );
}

/** Hijo animado del `<Stagger>`: sube y aparece con el ease de marca. */
export function StaggerItem({ children, className }: StaggerProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div variants={reduce ? staggerItemReduced : staggerItem} className={className}>
      {children}
    </motion.div>
  );
}
