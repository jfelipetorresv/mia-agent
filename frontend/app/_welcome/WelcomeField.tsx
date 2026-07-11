"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { staggerItem, staggerItemReduced, useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

export interface WelcomeFieldProps {
  /** Rótulo del campo/pregunta (español llano). Opcional. */
  label?: React.ReactNode;
  /**
   * `id` del control al que apunta el rótulo. Cuando se pasa junto a `label`, el
   * rótulo se renderiza como un `<label htmlFor>` REAL (nombre accesible asociado),
   * en vez de un `<span>` decorativo. La pantalla debe darle al control ese mismo `id`.
   */
  htmlFor?: string;
  /** Texto de ayuda bajo el rótulo. Opcional. */
  hint?: React.ReactNode;
  /** El control en sí (Input, TagInput, ToolsChecklist, botones…). */
  children: React.ReactNode;
  className?: string;
}

/**
 * Envoltura de un campo o pregunta dentro de un `<Stagger>`: entra escalonada
 * con el resto de elementos del paso (sube + aparece). Da estructura consistente
 * a rótulo + ayuda + control en toda la bienvenida. Respeta reduced-motion.
 *
 * Debe usarse como hijo de `<Stagger>` para heredar el escalonado; si se usa
 * suelto igual anima su propia entrada.
 */
export default function WelcomeField({ label, htmlFor, hint, children, className }: WelcomeFieldProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      variants={reduce ? staggerItemReduced : staggerItem}
      className={cn("flex flex-col gap-1.5", className)}
    >
      {label &&
        (htmlFor ? (
          <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
            {label}
          </label>
        ) : (
          <span className="text-sm font-medium text-foreground">{label}</span>
        ))}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      {children}
    </motion.div>
  );
}
