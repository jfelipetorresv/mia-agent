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

import type { ComponentType, CSSProperties, ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
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
 * EL ICONO EN BAJO RELIEVE
 * ========================
 *
 * El vocabulario del sistema esculpe el contenedor del icono HACIA ADENTRO
 * mientras la tarjeta que lo contiene emerge: es ese contraste (relieve fuera,
 * bajo relieve dentro) el que da la profundidad, no la sombra por sí sola. Se
 * escribía a mano en cada pantalla con seis recetas distintas de fondo y radio.
 *
 * `rounded-xl` (12px) y no el radio de tarjeta: un chip de 40px con radio de
 * SUPERFICIE se lee como una tarjeta diminuta dentro de otra tarjeta.
 *
 * `tone` distingue el icono que ACOMPAÑA (`muted`, el defecto), el que señala
 * algo que pide acción (`cta`) y el que avisa (`warning`). No hay más: el color
 * de un icono es semántica, no decoración.
 */
export function NeuIcon({
  icon: Icon,
  tone = "muted",
  size = "md",
  className,
}: {
  icon: ComponentType<{ className?: string }>;
  tone?: "muted" | "primary" | "cta" | "warning";
  size?: "sm" | "md";
  className?: string;
}) {
  const tones = {
    muted: "text-muted-foreground",
    primary: "text-primary",
    cta: "text-cta-strong",
    warning: "text-warning",
  } as const;

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-xl bg-muted/50 shadow-neu-sunken",
        size === "sm" ? "h-9 w-9" : "h-10 w-10",
        tones[tone],
        className
      )}
    >
      <Icon className={size === "sm" ? "h-4 w-4" : "h-[1.125rem] w-[1.125rem]"} />
    </span>
  );
}

/**
 * UNA CELDA DEL PANEL (bento)
 * ===========================
 *
 * El Panel dejó de ser una lista vertical de secciones para ser una rejilla de
 * tarjetas: cada bloque de contenido vive DENTRO de su propia superficie, con
 * su cabecera de icono en bajo relieve. Antes cada sección repetía a mano el
 * par «cabecera + tarjetas sueltas debajo», que a rejilla no se traduce (los
 * bloques quedaban con alturas y fondos distintos en la misma fila).
 *
 * `emphasis` es la jerarquía dominante: la celda que el abogado tiene que mirar
 * primero (lo que espera su decisión) se eleva y se tiñe. Una sola por pantalla.
 */
export function PanelCard({
  icon,
  title,
  hint,
  tone = "muted",
  emphasis = false,
  actions,
  className,
  style,
  children,
}: {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  tone?: "muted" | "primary" | "cta" | "warning";
  emphasis?: boolean;
  actions?: ReactNode;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <Card
      variant="raised"
      padding="md"
      className={cn(
        "flex h-full flex-col bg-card/80 backdrop-blur-md",
        emphasis && "border-cta/30 bg-cta/5",
        className
      )}
      style={style}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {icon ? <NeuIcon icon={icon} tone={tone} size="sm" /> : null}
          <div className="min-w-0">
            <h2 className={cn("text-pretty", emphasis ? "text-title" : "text-section")}>{title}</h2>
            {hint ? (
              <p className="mt-1 text-pretty text-body text-muted-foreground">{hint}</p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      <div className="mt-4 min-w-0 flex-1">{children}</div>
    </Card>
  );
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
  sinMedir,
  nota,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  /** La cifra. `undefined`/`null` = no se pudo consultar; NUNCA se pinta como 0. */
  value?: number | null;
  suffix?: string;
  delay?: number;
  /**
   * ESTADO «NO MEDIBLE» (regla operativa §18 · la etiqueta es parte de la métrica).
   *
   * `value == null` tiene DOS causas que el abogado no puede distinguir y que no
   * significan lo mismo: «no pude consultarlo ahora» (fallo momentáneo, vuelve a
   * abrir) y «esto todavía no se ha medido» (el proceso que produce el dato no ha
   * corrido nunca). La segunda se declara con su RAZÓN, porque sin ella la única
   * salida honesta era una raya muda — y la deshonesta, un 0 que afirma algo falso
   * sobre el trabajo del despacho. Un cero REAL sigue pintándose como 0.
   */
  sinMedir?: string;
  /** Base del cálculo cuando la cifra es una estimación («estimado según X»). */
  nota?: string;
}) {
  return (
    <Card
      padding="sm"
      // SIN `interactive`: la tarjeta se levantaba al pasar el ratón y no lleva
      // a ningún sitio. Una superficie que reacciona promete una acción, y aquí
      // no había ninguna — el enlace de detalle vive bajo la rejilla, escrito.
      className="h-full animate-slide-up bg-card/80 backdrop-blur-md"
      // Cadencia única del producto (45 ms por peldaño). Antes este retraso se
      // calculaba a mano aquí y en otros cuatro sitios, con cuatro cadencias
      // distintas.
      style={staggerStyle(delay)}
    >
      {/* El icono baja a bajo relieve (vocabulario del sistema): la tarjeta
          emerge y su icono se hunde. Antes era un glifo suelto sobre el fondo. */}
      <NeuIcon icon={Icon} tone="primary" size="sm" className="mb-3" />
      {value == null || !Number.isFinite(value) ? (
        <>
          {/* La raya ocupa el sitio de la cifra para que la rejilla no salte,
              pero no se anuncia: quien no ve la pantalla oye la etiqueta y el
              motivo, que es lo que informa. */}
          <div className="text-title text-muted-foreground" aria-hidden>
            —
          </div>
          <div className="mt-1 text-label text-muted-foreground">{label}</div>
          <div className="mt-1 text-pretty text-meta text-muted-foreground">
            {sinMedir ? `Sin medir todavía · ${sinMedir}` : "Sin dato ahora mismo"}
          </div>
        </>
      ) : (
        <>
          <div className="text-title nums">
            {value}
            {suffix}
          </div>
          <div className="mt-1 text-pretty text-label text-muted-foreground">{label}</div>
          {nota ? (
            <div className="mt-1 text-pretty text-meta text-muted-foreground">{nota}</div>
          ) : null}
        </>
      )}
    </Card>
  );
}

/**
 * LA MISMA REGLA DE `StatCard`, EN FORMATO DE BARRA (regla operativa §18 · null ≠ cero).
 *
 * Conocimiento no muestra tarjetas de cifra: muestra barras de progreso con su rótulo
 * («40 % consolidado», «La aprobaste el 80 % de las veces»). Eran dos cifras escritas a
 * mano con `|| 0`, que es exactamente el patrón que convierte «todavía no se ha medido»
 * en una afirmación falsa sobre el trabajo del despacho: una guía que Mia nunca usó se
 * leía como «la aprobaste el 0 % de las veces», que es un reproche inventado.
 *
 * Aquí la barra desaparece cuando no hay dato y queda el estado declarado con su razón,
 * en la misma redacción de `StatCard` («Sin medir todavía · …»). `label` se pasa como
 * literal a propósito: es lo que `execution/test_registro_metricas.py` inventaria para
 * exigir que cada cifra visible tenga su definición en `validation/registro-metricas.json`.
 * Por eso el porcentaje se inserta EN el rótulo, sustituyendo su «%»: la etiqueta que se
 * registra («La aprobaste el % de las veces») es la misma frase que el abogado lee, sin
 * partirla en trozos que ningún inventario podría cotejar.
 */
export function MetricaBarra({
  label,
  /** Fracción 0..1. `null`/`undefined`/no finito = no medido; NUNCA se pinta como 0 %. */
  fraccion,
  sinMedir,
  sufijo,
  bloque = false,
  className,
}: {
  label: string;
  fraccion?: number | null;
  sinMedir: string;
  /** Texto que acompaña a la cifra cuando SÍ hay dato (p. ej. «· Mia la usó 4 veces»). */
  sufijo?: ReactNode;
  /** `true` = barra a todo el ancho con el rótulo debajo (pie de tarjeta). */
  bloque?: boolean;
  className?: string;
}) {
  const medido = fraccion != null && Number.isFinite(fraccion);
  if (!medido) {
    return (
      <div className={cn("text-pretty text-meta text-muted-foreground", className)}>
        {label} · Sin medir todavía · {sinMedir}
      </div>
    );
  }
  const pct = Math.round(Math.max(0, Math.min(1, fraccion as number)) * 100);
  const barra = (
    <div
      className={cn(
        "h-1.5 rounded-full bg-muted shadow-neu-sunken",
        bloque ? "w-full" : "w-24 shrink-0"
      )}
    >
      <div
        className="h-1.5 rounded-full bg-primary transition-all duration-200"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
  const rotulo = (
    <span className={cn("text-pretty text-meta nums text-muted-foreground", bloque && "mt-1.5 block")}>
      {label.replace("%", `${pct} %`)}
      {sufijo}
    </span>
  );
  if (bloque) {
    return (
      <div className={className}>
        {barra}
        {rotulo}
      </div>
    );
  }
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {barra}
      {rotulo}
    </div>
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
