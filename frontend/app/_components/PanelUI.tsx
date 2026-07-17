"use client";

// Piezas visuales compartidas entre el Panel (dashboard) y Configuración — antes
// vivían duplicadas dentro de dashboard/page.tsx; se extraen aquí para que ambas
// pantallas se vean consistentes sin repetir código (reestructuración CP-D1).

import type { ComponentType, ReactNode } from "react";

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

export function SectionTitle({
  icon: Icon,
  title,
  hint,
  className = "mb-4",
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
        <Icon className="h-4 w-4 text-primary" />
        {title}
      </h2>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function StatCard({
  icon: Icon,
  label,
  value,
  suffix = "",
  delay = 0,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value?: number;
  suffix?: string;
  delay?: number;
}) {
  return (
    <div
      className="card-depth animate-slide-up rounded-xl border border-border bg-card p-4 transition-all duration-200 hover:-translate-y-0.5"
      style={{ animationDelay: `${delay * 45}ms`, animationFillMode: "backwards" }}
    >
      <Icon className="mb-2 h-4 w-4 text-primary" />
      <div className="text-2xl font-semibold tracking-tight">{value ?? 0}{suffix}</div>
      <div className="mt-0.5 text-sm text-muted-foreground">{label}</div>
    </div>
  );
}

export function EmptyHint({
  icon: Icon,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-dashed border-border bg-card/50 px-4 py-4">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

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
    <div className="card-depth rounded-xl border border-border bg-card p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
              active ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
            }`}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-medium">
              {title}
              {active ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  Activo
                </span>
              ) : null}
            </div>
            {subtitle ? <div className="mt-0.5 truncate text-sm text-muted-foreground">{subtitle}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}
