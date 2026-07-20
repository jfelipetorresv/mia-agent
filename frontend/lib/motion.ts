import type { CSSProperties } from "react";
import type { Variants } from "framer-motion";

/**
 * LENGUAJE DE MOVIMIENTO ÚNICO DE MIA
 * ===================================
 *
 * Hasta ahora convivían DOS lenguajes de movimiento en paralelo:
 *
 *   Sistema A — la bienvenida (`app/_welcome/*`): framer-motion, curva
 *     MIA_EASE, stagger declarativo y respeto de `prefers-reduced-motion`.
 *     Es la referencia de calidad del producto según su propio dueño.
 *   Sistema B — todo lo demás: keyframes de Tailwind y stagger calculado
 *     A MANO en estilos en línea, con CUATRO cadencias distintas
 *     (`i * 40`, `i * 45`, `delay * 45`, `180 + i * 70`). Cruzar de la
 *     bienvenida al producto se sentía como cambiar de aplicación.
 *
 * Este archivo es la fuente ÚNICA de los dos sistemas. `app/_welcome/motion.ts`
 * ahora re-exporta desde aquí, así que la bienvenida y el producto no pueden
 * volver a separarse: si alguien cambia la curva, cambia en los dos sitios.
 *
 * Por qué vive en `lib/` y no en `app/_welcome/`: para que el producto pueda
 * importar la cadencia sin arrastrar la bienvenida.
 *
 * DEPENDENCIAS EN TIEMPO DE EJECUCIÓN: NINGUNA. Los dos `import type` se borran
 * al compilar, así que una pantalla que solo quiera `staggerStyle()` NO mete
 * framer-motion en su paquete. Por eso `useReducedMotion` (que sí es código de
 * framer-motion) se queda en `app/_welcome/motion.ts` y no se re-exporta aquí.
 */

/* ────────────────────────────────────────────────────────────────────────────
 * La curva
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * Curva de marca: un "ease out" suave que arranca rápido y ASIENTA despacio.
 * Es la misma en la bienvenida, en las animaciones de Tailwind
 * (`tailwind.config.ts`) y en `--ease-mia` de `globals.css`. Un solo movimiento
 * en todo el viaje.
 */
export const MIA_EASE = [0.22, 1, 0.36, 1] as const;

/** La misma curva para CSS (estilos en línea, `transition`, `animation`). */
export const MIA_EASE_CSS = "cubic-bezier(0.22, 1, 0.36, 1)";

/** Duración de un cambio de paso del viaje de bienvenida, en segundos. */
export const STEP_DURATION = 0.35;

/** Spring corto y satisfactorio para micro-remates (checks, ✓ de validación). */
export const POP_SPRING = { type: "spring", stiffness: 500, damping: 18, mass: 0.6 } as const;

/* ────────────────────────────────────────────────────────────────────────────
 * Stagger por índice, para animaciones CSS (el producto)
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * Cadencia única del escalonado, en milisegundos.
 *
 * 45 ms no es un número nuevo: era ya la cadencia mayoritaria del producto
 * (StatCard del Panel, tarjetas de Asuntos, recomendaciones). Se adoptan los
 * 45 ms y se retiran las otras tres cadencias. Por debajo de ~30 ms el
 * escalonado no se percibe; por encima de ~60 ms la lista se siente lenta.
 */
export const STAGGER_STEP_MS = 45;

/**
 * Tope de peldaños. Sin tope, una lista de 40 elementos termina con el último
 * entrando 1,8 s tarde: eso ya no es jerarquía, es espera. A partir del peldaño
 * 8 todos entran a la vez.
 */
export const STAGGER_MAX_STEPS = 8;

export type StaggerOptions = {
  /** Milisegundos por peldaño. Por defecto `STAGGER_STEP_MS` (45). */
  step?: number;
  /** Retraso fijo antes del primer elemento, en ms. Por defecto 0. */
  base?: number;
  /** Peldaño máximo antes de aplanar. Por defecto `STAGGER_MAX_STEPS` (8). */
  maxSteps?: number;
};

/** Retraso en milisegundos que le toca al elemento `index` de una lista. */
export function staggerDelayMs(index: number, options: StaggerOptions = {}): number {
  const { step = STAGGER_STEP_MS, base = 0, maxSteps = STAGGER_MAX_STEPS } = options;
  const safeIndex = Number.isFinite(index) && index > 0 ? Math.floor(index) : 0;
  return base + Math.min(safeIndex, maxSteps) * step;
}

/**
 * Estilo en línea para escalonar la entrada del elemento `index`.
 *
 * Sustituye a los `style={{ animationDelay: `${i * 45}ms` }}` escritos a mano.
 * Se usa junto a una clase de animación de Tailwind:
 *
 *     <div className="animate-slide-up" style={staggerStyle(i)}>
 *
 * `animationFillMode: "backwards"` es obligatorio, no decorativo: sin él el
 * elemento se ve en su estado final durante todo el retraso y luego SALTA al
 * inicio de la animación — justo el parpadeo que el escalonado quiere evitar.
 *
 * ACCESIBILIDAD: no hace falta comprobar `prefers-reduced-motion` aquí. El
 * bloque `@media (prefers-reduced-motion: reduce)` de `globals.css` declara
 * `animation-delay: 0ms !important`, y `!important` de hoja de estilos gana a
 * un estilo en línea sin `!important`. Quien pide que nada se mueva ve la lista
 * completa de inmediato, sin cascada.
 */
export function staggerStyle(index: number, options: StaggerOptions = {}): CSSProperties {
  return {
    animationDelay: `${staggerDelayMs(index, options)}ms`,
    animationFillMode: "backwards",
  };
}

/* ────────────────────────────────────────────────────────────────────────────
 * Variantes de framer-motion (la bienvenida)
 * ──────────────────────────────────────────────────────────────────────────── */

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
