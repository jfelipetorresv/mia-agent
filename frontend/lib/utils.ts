import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * twMerge configurado a la medida del tema (tailwind.config.ts).
 *
 * La escala tipográfica semántica (`theme.fontSize`: display/title/section/
 * body/label/meta) reutiliza el prefijo `text-`, el MISMO que Tailwind usa
 * para el COLOR del texto. twMerge sin configurar no conoce esos seis roles
 * y por defecto los clasifica como color: `cn("text-body", "text-muted-
 * foreground")` colapsaba a SOLO "text-muted-foreground" — el tamaño
 * (15px/24/400) desaparecía EN SILENCIO, sin error ni warning. No es
 * hipotético: components/ui/card.tsx (CardDescription) combina exactamente
 * ese par hoy. Se registran los seis roles como miembros del grupo
 * `font-size` para que twMerge los distinga del color y deje de tratarlos
 * como si compitieran por el mismo lugar.
 *
 * `rounded-*` (radios) y `shadow-*` (elevaciones) del mismo tema NO
 * necesitan este ajuste: Tailwind no sobrecarga esos prefijos con una
 * segunda dimensión (no existe "rounded-color"), así que el validador por
 * defecto de twMerge ya los agrupa y prioriza bien (verificado: rounded-lg
 * + rounded-sm → rounded-sm; shadow-flat + shadow-raised → shadow-raised).
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        { text: ["display", "title", "section", "body", "label", "meta"] },
      ],
    },
  },
});

/** Une clases condicionales y resuelve conflictos de Tailwind. Base del design system. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
