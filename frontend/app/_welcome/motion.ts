/**
 * Lenguaje de movimiento de la bienvenida cinematográfica de MIA.
 *
 * Estos valores ya NO viven aquí: se extrajeron a `lib/motion.ts` para que el
 * resto del producto pueda usar la MISMA curva y la MISMA cadencia sin importar
 * la bienvenida. Este archivo se conserva como puerta de entrada de
 * `app/_welcome/*` (nueve archivos lo importan como "./motion") y para que
 * `useReducedMotion` siga estando junto a las variantes.
 *
 * La superficie de exportación es EXACTAMENTE la de antes; no hay ningún cambio
 * de comportamiento en la bienvenida. Si hay que tocar la curva o el stagger,
 * se toca en `lib/motion.ts` y cambia en los dos sitios a la vez.
 */

// Guard de accesibilidad. Se re-exporta desde aquí (y no desde `lib/motion.ts`)
// a propósito: es código de framer-motion en tiempo de ejecución, y `lib/motion.ts`
// debe quedar libre de dependencias para que el producto lo importe barato.
export { useReducedMotion } from "framer-motion";

export {
  MIA_EASE,
  MIA_EASE_CSS,
  STEP_DURATION,
  POP_SPRING,
  stepVariants,
  stepVariantsReduced,
  staggerContainer,
  staggerItem,
  staggerItemReduced,
} from "@/lib/motion";
