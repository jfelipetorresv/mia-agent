"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * FEEDBACK TÁCTIL: `active:scale-[0.98]`.
 * Un botón que no se hunde al pulsarlo se siente muerto — el abogado duda de si
 * el clic entró y vuelve a pulsar. El 2 % de reducción es el mínimo que se
 * percibe sin parecer un juguete. Se anima SOLO `transform` (nunca layout), y
 * por eso `transition-colors` se amplía para incluirlo: sin esa propiedad en la
 * lista, el hundimiento sería un salto seco en vez de un gesto.
 * `motion-reduce:active:scale-100` lo desactiva para quien pide que nada se
 * mueva; no basta con la regla global de `globals.css`, que solo acorta la
 * duración (el movimiento seguiría ocurriendo, instantáneo).
 * La curva y la duración salen de los tokens: `transitionTimingFunction.DEFAULT`
 * ya es MIA_EASE, así que no hace falta declararlas aquí.
 *
 * TIPOGRAFÍA: `type-control` (globals.css), que es `@apply text-label` — el
 * peldaño 13/18/500 que la propia escala asigna al botón. Antes era
 * `text-sm font-medium` (14/500), justo lo que la regla de la escala prohíbe
 * ("se escribe `text-title`, nunca `text-lg font-medium`"): la primitiva más
 * usada del producto ignoraba el vocabulario que este mismo sistema declara.
 * No se escribe `text-label` aquí directamente porque tailwind-merge no conoce
 * la escala y la trataría como un COLOR, borrándola en cuanto alguien pase
 * `className="text-muted-foreground"` — el motivo largo está en globals.css.
 */
const buttonVariants = cva(
  "type-control inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md transition-[color,background-color,border-color,box-shadow,opacity,transform] active:scale-[0.98] motion-reduce:active:scale-100 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      /**
       * ELEVACIÓN: `shadow-flat`, nunca `shadow-sm`.
       * El sistema declara DOS niveles (`shadow-flat` / `shadow-raised`) y deja
       * `shadow-sm/md/lg/xl/2xl` fuera del vocabulario; estas cuatro variantes
       * seguían usando `shadow-sm`, así que la primitiva más usada desmentía la
       * regla en su propio archivo. Un botón relleno no necesita sombra: su
       * afordancia la dan el color macizo y el hundimiento al pulsar. Se
       * escribe el nivel en vez de borrar la clase para que la elección quede
       * declarada y no parezca un olvido.
       */
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-neu-raised active:shadow-neu-sunken",
        cta: "bg-gradient-cta text-cta-foreground shadow-neu-raised hover:opacity-95 active:shadow-neu-sunken",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-neu-raised active:shadow-neu-sunken",
        success: "bg-success text-success-foreground hover:bg-success/90 shadow-neu-raised active:shadow-neu-sunken",
        outline: "border border-border/20 bg-card/60 backdrop-blur-sm hover:bg-accent hover:text-accent-foreground shadow-neu-raised active:shadow-neu-sunken",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80 shadow-neu-raised active:shadow-neu-sunken",
        ghost: "hover:bg-accent hover:text-accent-foreground active:shadow-neu-sunken",
        link: "text-primary underline-offset-4 hover:underline",
      },
      /**
       * TAMAÑOS: la jerarquía la dan la altura y el aire, no una tipografía por
       * peldaño. `default`, `sm` e `icon` se quedan en `type-control` (13/18).
       * `lg` conserva sus 16 px de siempre, pero ahora los pide por su nombre
       * (`text-section`, 16/24/600) en vez de con el `text-base` crudo que la
       * escala no reconoce; así el CTA de portada no encoge y el archivo deja
       * de mezclar vocabulario del sistema con utilidades sueltas.
       */
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-6 text-section",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
