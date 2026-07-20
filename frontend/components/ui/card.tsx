import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * LA TARJETA DEL PRODUCTO
 * =======================
 *
 * Esta primitiva estaba HUÉRFANA: la importaba un solo archivo de todo el
 * frontend, mientras el resto dibujaba tarjetas a mano — 23 combinaciones
 * distintas de radio + borde + fondo + sombra, y TRES elevaciones diferentes
 * (sin sombra ×41, `shadow-sm` ×5, `card-depth` ×5) para el mismo objeto
 * semántico. El abogado veía el mismo tipo de dato con tres profundidades
 * distintas según la pantalla.
 *
 * Aquí quedan las tres formas legítimas, construidas sobre los tokens:
 *
 *   flat    superficie normal: borde hairline, SIN sombra.   ← por defecto
 *   raised  solo cuando la elevación comunica jerarquía real (algo flota
 *           por encima de lo demás: menús, resultados destacados).
 *   dashed  contenedor de un vacío: "aquí todavía no hay nada".
 *
 * POR QUÉ `flat` ES EL DEFECTO: es lo que ya era mayoría en el producto (41 de
 * 51 tarjetas). Una tarjeta se eleva solo si la elevación significa algo; si
 * todo flota, nada destaca.
 *
 * POR QUÉ `padding` ES `none` POR DEFECTO: la API compuesta
 * (CardHeader / CardContent / CardFooter) ya trae su propio padding. Si la raíz
 * añadiera relleno por su cuenta, cada tarjeta compuesta quedaría con doble
 * margen interior. `sm` y `md` son para la tarjeta simple, sin subcomponentes.
 */
const cardVariants = cva(
  // `rounded-lg` = 14px = el radio de SUPERFICIE del sistema (--radius). Las
  // tarjetas nunca usan otro radio: es el ancla del SHAPE CONSISTENCY LOCK.
  "rounded-lg bg-card text-card-foreground",
  {
    variants: {
      variant: {
        flat: "border border-border shadow-flat",
        raised: "border border-border shadow-raised",
        dashed: "border border-dashed border-border bg-card/50 shadow-flat",
      },
      padding: {
        none: "",
        sm: "p-4",
        md: "p-5",
      },
      /**
       * Realce al pasar el ratón. Solo para tarjetas que SON un objetivo
       * (llevan a algún sitio o se pueden accionar). Una tarjeta meramente
       * informativa no debe reaccionar: promete una acción que no existe.
       * `transform` es lo único que se anima (nunca layout).
       */
      interactive: {
        true: "transition-transform duration-200 hover:-translate-y-0.5",
        false: "",
      },
    },
    defaultVariants: { variant: "flat", padding: "none", interactive: false },
  }
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, interactive, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(cardVariants({ variant, padding, interactive }), className)}
      {...props}
    />
  )
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

// Rol tipográfico `section` (16/600, tipografía de despliegue): el título de una
// tarjeta es un h3 del sistema, y un h3 NUNCA comparte tamaño con el cuerpo.
const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("text-section leading-none", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("text-body text-muted-foreground", className)} {...props} />
  )
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  )
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  )
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent, cardVariants };
