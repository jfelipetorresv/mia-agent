import type { Variants } from "framer-motion";

// Re-exportamos el guard de accesibilidad para que las pantallas lo importen
// desde un solo lugar junto a las variantes.
export { useReducedMotion } from "framer-motion";

/**
 * Lenguaje de movimiento compartido de la bienvenida cinematográfica de MIA.
 * Todo anima SOLO transform/opacity (sin layout thrash). Curva de marca:
 * un ease "out" suave y elegante, el mismo en todo el viaje.
 */
export const MIA_EASE = [0.22, 1, 0.36, 1] as const;
export const STEP_DURATION = 0.35;

/**
 * Transición direccional entre pasos del viaje.
 * `direction` >= 0 = avanzar (entra desde la derecha, sale hacia la izquierda);
 * < 0 = retroceder (espejo). Se pasa como `custom` a AnimatePresence.
 */
export const stepVariants: Variants = {
  enter: (direction: number) => ({ x: direction >= 0 ? 24 : -24, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (direction: number) => ({ x: direction >= 0 ? -24 : 24, opacity: 0 }),
};

/** Variante estática equivalente para `prefers-reduced-motion` (solo opacidad). */
export const stepVariantsReduced: Variants = {
  enter: { opacity: 0 },
  center: { opacity: 1 },
  exit: { opacity: 0 },
};

/** Contenedor que escalona la entrada de sus hijos (reemplaza los delays manuales). */
export const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.06 } },
};

/** Hijo del stagger: sube y aparece. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: MIA_EASE } },
};

/** Hijo del stagger en modo reducido: solo opacidad. */
export const staggerItemReduced: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.3 } },
};

/** Spring corto y satisfactorio para micro-remates (checks, ✓ de validación). */
export const POP_SPRING = { type: "spring", stiffness: 500, damping: 18, mass: 0.6 } as const;
