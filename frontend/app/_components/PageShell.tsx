import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * EL CONTENEDOR DE UNA PANTALLA
 * =============================
 *
 * Convivían TRES anchos de contenido sin ninguna regla que dijera cuándo va
 * cada uno (`max-w-5xl`, `max-w-3xl`, `max-w-2xl`) y dos escalas de padding.
 * Al navegar Panel → Asuntos → Chat el contenido saltaba de ancho tres veces:
 * la aplicación se sentía inestable aunque cada pantalla, por separado,
 * estuviera bien.
 *
 * Aquí hay UN ancho de lectura y una excepción que hay que DECLARAR:
 *
 *   reading  (defecto)  max-w-3xl  → texto, formularios, listas, detalle.
 *                        Es el ancho al que se lee cómodo un párrafo.
 *   wide                 max-w-5xl → SOLO rejillas de cifras y tablas anchas,
 *                        donde el ancho lo pide el dato, no la prosa.
 *   full                 sin tope  → lienzos a pantalla completa (chat).
 *
 * Si una pantalla necesita `wide`, lo escribe y se ve en el código. Antes la
 * excepción era invisible porque todo era excepción.
 *
 * `min-h-[100dvh]` y NUNCA `h-screen`: en móvil `100vh` incluye la barra del
 * navegador que luego se retrae, así que `h-screen` corta el contenido y crea
 * un scroll fantasma. `dvh` mide el alto que de verdad hay.
 */
export type PageShellProps = {
  children: ReactNode;
  /** Título de la pantalla. Se compone como el único `h1` de la página. */
  title?: ReactNode;
  /** Una o dos líneas bajo el título, en el idioma del oficio. */
  subtitle?: ReactNode;
  /** Controles principales de la pantalla, a la derecha del título. */
  actions?: ReactNode;
  /** Ancho de contenido. `reading` por defecto; `wide` es excepción declarada. */
  width?: "reading" | "wide" | "full";
  /** Clases para el contenedor interior (el que lleva el ancho). */
  className?: string;
  /** Clases para el lienzo exterior (fondos, capas). */
  outerClassName?: string;
};

const WIDTHS = {
  reading: "max-w-3xl",
  wide: "max-w-5xl",
  full: "max-w-none",
} as const;

export function PageShell({
  children,
  title,
  subtitle,
  actions,
  width = "reading",
  className,
  outerClassName,
}: PageShellProps) {
  const hasHeader = Boolean(title || subtitle || actions);

  return (
    <div className={cn("min-h-[100dvh] px-6 py-10 md:px-8", outerClassName)}>
      <div className={cn("mx-auto w-full", WIDTHS[width], className)}>
        {hasHeader ? (
          // `mb-block` = --space-block (1.5rem): el aire entre la cabecera y el
          // contenido. La app entera era densidad de cabina (gap-2 ×183 contra
          // gap-6 ×4); las superficies de lectura necesitan respirar.
          <header className="mb-block flex items-start justify-between gap-4">
            <div className="min-w-0">
              {title ? <h1 className="text-pretty text-display">{title}</h1> : null}
              {subtitle ? (
                <p className="mt-2 text-pretty text-body text-muted-foreground">{subtitle}</p>
              ) : null}
            </div>
            {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
          </header>
        ) : null}
        {children}
      </div>
    </div>
  );
}
