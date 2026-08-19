"use client";

// Piezas visuales compartidas entre el Panel (dashboard) y Configuración — antes
// vivían duplicadas dentro de dashboard/page.tsx; se extraen aquí para que ambas
// pantallas se vean consistentes sin repetir código (reestructuración CP-D1).
//
// CAPA 2 DEL REDISEÑO: las tres recetas de tarjeta escritas a mano que había
// aquí (StatCard, EmptyHint, ConnectorCard) pasan a la primitiva `Card`, y la
// cabecera de sección pasa al componente `SectionTitle` único. Estos cuatro
// componentes cubren el Panel y Configuración de un golpe, así que las dos
// pantallas se corrigen por HERENCIA, sin reescribir ninguna de las dos.

import type { ComponentType, ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { staggerStyle } from "@/lib/motion";

// La cabecera de sección ahora vive en su propio archivo (era una de las dos
// convenciones en conflicto del producto). Se re-exporta desde aquí porque ocho
// archivos la importan como "@/app/_components/PanelUI" y su ruta no cambia.
export { SectionTitle } from "./SectionTitle";
export type { SectionTitleProps } from "./SectionTitle";

export function fmt(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

// Para los recordatorios la HORA importa ("mañana a las 9" no es "mañana").
export function fmtHora(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

/**
 * Una cifra del despacho con su etiqueta.
 *
 * UN CERO NO ES UNA AUSENCIA. Esta tarjeta pintaba `value ?? 0`, así que una
 * fuente caída se leía exactamente igual que un mes sin actividad: "0
 * borradores aprobados" es una AFIRMACIÓN sobre el trabajo del abogado, y una
 * afirmación falsa sobre su trabajo es el peor defecto que puede tener esta
 * pantalla — puede decidir sobre ella. Ahora la tarjeta distingue:
 *
 *   · cargando       → lo dice la pantalla que la contiene (su esqueleto),
 *                      porque quien sabe si la petición sigue en vuelo es ella
 *   · dato real      → la cifra, aunque sea un cero de verdad
 *   · no disponible  → `undefined`/`null`: se dice que no se pudo consultar,
 *                      NO se rellena con un número
 *
 * `nums` (tabular-nums) no es cosmético: sin él los dígitos tienen anchos
 * distintos, así que al actualizarse una cifra BAILA y dos cifras en columna no
 * se pueden comparar de un vistazo. Un número que se lee como dato lleva
 * tabular-nums siempre.
 *
 * La cifra usa el rol `title` (20/600) y no el `display` (30/600): `display`
 * está reservado al único h1 de la pantalla. Cuatro cifras al tamaño del
 * titular aplanarían la jerarquía en vez de crearla. La diferencia con la
 * etiqueta (`label`, 13/500) la da el peso y el color, no la escala bruta.
 */
export function StatCard({
  icon: Icon,
  label,
  value,
  suffix = "",
  delay = 0,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  /** La cifra. `undefined`/`null` = no se pudo consultar; NUNCA se pinta como 0. */
  value?: number | null;
  suffix?: string;
  delay?: number;
}) {
  return (
    <Card
      padding="sm"
      interactive
      className="animate-slide-up"
      // Cadencia única del producto (45 ms por peldaño). Antes este retraso se
      // calculaba a mano aquí y en otros cuatro sitios, con cuatro cadencias
      // distintas.
      style={staggerStyle(delay)}
    >
      <Icon className="mb-2 h-4 w-4 text-primary" />
      {value == null || !Number.isFinite(value) ? (
        <>
          {/* La raya ocupa el sitio de la cifra para que la rejilla no salte,
              pero no se anuncia: quien no ve la pantalla oye la etiqueta y el
              motivo, que es lo que informa. */}
          <div className="text-title text-muted-foreground" aria-hidden>
            —
          </div>
          <div className="mt-1 text-label text-muted-foreground">{label}</div>
          <div className="mt-1 text-meta text-muted-foreground">Sin dato ahora mismo</div>
        </>
      ) : (
        <>
          <div className="text-title nums">
            {value}
            {suffix}
          </div>
          <div className="mt-1 text-label text-muted-foreground">{label}</div>
        </>
      )}
    </Card>
  );
}

/**
 * "Aquí todavía no hay nada, y esto es lo que puedes hacer."
 * El borde discontinuo es lo que distingue un vacío de un dato: la tarjeta
 * `dashed` del sistema existe exactamente para esto.
 */
export function EmptyHint({
  icon: Icon,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <Card variant="dashed" padding="sm" className="flex items-start gap-3">
      {/* Sin modificador de opacidad (antes `text-muted-foreground/60`): la
          opacidad sobre tokens de texto es justo lo que hundía el contraste por
          debajo del mínimo legible. */}
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <p className="text-pretty text-body text-muted-foreground">{children}</p>
    </Card>
  );
}

/**
 * Una fuente o un ayudante que Mia puede usar, con su estado y sus controles.
 */
export function ConnectorCard({
  icon: Icon,
  title,
  subtitle,
  active,
  actions,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  active?: boolean;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Card padding="md">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {/* `rounded-md` (10px) = radio de CONTROL. Antes era `rounded-lg`, que
              ahora vale 14px: el radio de una SUPERFICIE. Un chip de 36px con
              radio de tarjeta se lee como una tarjeta diminuta. */}
          <span
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
              active ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
            }`}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {/* Rol `section` (16/600): el nombre de un conector es un h3 del
                  sistema y no puede medir lo mismo que su descripción. */}
              <span className="truncate text-section">{title}</span>
              {active ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-meta font-medium text-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  Activo
                </span>
              ) : null}
            </div>
            {subtitle ? <div className="mt-0.5 truncate text-body text-muted-foreground">{subtitle}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
      </div>
      {children}
    </Card>
  );
}
