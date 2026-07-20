import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * CABECERA DE SECCIÓN — una sola convención
 * =========================================
 *
 * Convivían dos formas de encabezar una sección, en conflicto:
 *   A) `<h2 class="text-base font-semibold tracking-tight">` con icono y pista
 *      (la del Panel y Configuración).
 *   B) `<h2 class="text-lg font-medium">` suelto, sin icono, en seis pantallas.
 *
 * Dos tamaños, dos pesos y dos anatomías para el mismo papel. Este componente
 * es la única forma a partir de ahora: quien necesite el caso B simplemente
 * omite `icon`.
 *
 * NIVELES: `h2` (rol `title`, 20px) para las secciones de una pantalla; `h3`
 * (rol `section`, 16px) para subsecciones dentro de una sección. Nunca se baja
 * al tamaño del cuerpo: era el defecto raíz de "no se siente fácil" — el título
 * y el párrafo medían lo mismo, así que nada guiaba el ojo.
 */
export type SectionTitleProps = {
  /** Icono de lucide. Opcional: sin él se obtiene la cabecera desnuda. */
  icon?: ComponentType<{ className?: string }>;
  title: string;
  /** Una línea que explica la sección en el idioma del oficio. */
  hint?: string;
  /** Controles alineados a la derecha del título (botones, filtros). */
  actions?: ReactNode;
  /** Jerarquía. `h2` = sección de pantalla (defecto); `h3` = subsección. */
  level?: "h2" | "h3";
  className?: string;
};

export function SectionTitle({
  icon: Icon,
  title,
  hint,
  actions,
  level = "h2",
  className = "mb-4",
}: SectionTitleProps) {
  const Heading = level;
  const isSub = level === "h3";

  return (
    <div className={cn("flex items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <Heading
          className={cn(
            "flex items-center gap-2 text-pretty",
            // `text-title` / `text-section` ya traen tamaño, peso, interlineado y
            // tracking del sistema. No se les añade font-* encima.
            isSub ? "text-section" : "text-title"
          )}
        >
          {Icon ? (
            <Icon
              className={cn(
                "shrink-0 text-primary",
                isSub ? "h-4 w-4" : "h-[1.125rem] w-[1.125rem]"
              )}
            />
          ) : null}
          {title}
        </Heading>
        {hint ? <p className="mt-1 text-pretty text-body text-muted-foreground">{hint}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
