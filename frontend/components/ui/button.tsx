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
        default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-flat",
        /**
         * CTA principal de marca: degradado verde Lexia + texto casi negro.
         *
         * CONTRASTE VERIFICADO contra su fondo REAL (el degradado), no contra
         * blanco. Medido con la fórmula de luminancia relativa de WCAG 2.1
         * sobre los valores resueltos de los tokens
         * (--cta-foreground #0A0A0A sobre --cta-gradient-from #98E4BF →
         * --cta-gradient-to #00F5A2):
         *
         *   reposo   extremo claro 13.37:1 · medio 13.14:1 · extremo verde 13.75:1
         *   hover:opacity-90 en tema claro   peor caso 10.81:1
         *   hover:opacity-90 en tema oscuro  peor caso 10.73:1
         *
         * Peor caso global 10.73:1 → cumple AA (4.5:1) y AAA (7:1) con holgura.
         * `hover:opacity-90` compone TODO el botón (texto incluido) contra el
         * fondo de la página, por eso se midió también compuesto y en los dos
         * temas: bajar la opacidad del conjunto sí puede romper un contraste.
         *
         * OJO AL ERROR YA COMETIDO EN ESTE REPO: medir el VERDE contra BLANCO
         * da 1.44:1 y hace pensar que el CTA está roto. Es una medición sin
         * sentido — el verde es el fondo del botón, no su texto, y ese botón
         * nunca se pinta sobre blanco. Lo que se mide es texto sobre degradado.
         */
        cta: "bg-gradient-cta text-cta-foreground shadow-flat hover:opacity-90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-flat",
        success: "bg-success text-success-foreground hover:bg-success/90 shadow-flat",
        outline: "border border-input bg-transparent hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
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
