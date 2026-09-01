"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, Search } from "lucide-react";
import { clearToken } from "@/lib/api";
import { NAV_ITEMS } from "./nav";
import ThemeToggle from "./ThemeToggle";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
// Wordmark compartido (infra visual F3). size="sm" reproduce exactamente el
// logotipo previo de la sidebar; href="/" conserva el enlace a inicio.
import BrandMark from "@/app/_welcome/BrandMark";

function openCommandPalette() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname() || "/";
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((l) => {
        const active = l.match(path);
        const Icon = l.icon;
        return (
          <Link
            key={l.href}
            href={l.href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200",
              active
                ? "shadow-neu-sunken bg-primary/15 text-primary font-semibold"
                : "text-muted-foreground hover:shadow-neu-raised hover:bg-accent/40 hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span>{l.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * EL PIE DE LA BARRA · lo que es de la cuenta, no de la navegación.
 *
 * Pipe, bitácora 2026-08-19 (punto 15b): «Apariencia y Cerrar sesión perdidos
 * abajo». Eran dos botones fantasma idénticos pegados al final de la lista de
 * secciones, sin nada que dijera que pertenecen a otra categoría: se leían como
 * dos entradas más del menú, y las dos últimas, que es donde menos se mira.
 *
 * Lo que cambia es la JERARQUÍA, no las funciones: un rótulo que los agrupa y
 * los separa de la navegación, y el cierre de sesión en color de advertencia —
 * es la única acción del menú que te saca de donde estás, y debe verse distinta
 * de cambiar el tema. Ambos siguen siendo los mismos dos controles de siempre.
 */
function PieDeCuenta({ onLogout, className }: { onLogout: () => void; className?: string }) {
  return (
    <div className={cn("border-t border-border p-3", className)}>
      <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
        Tu cuenta
      </p>
      <div className="flex flex-col gap-1">
        <ThemeToggle />
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          onClick={onLogout}
        >
          <LogOut className="h-4 w-4" />
          <span>Cerrar sesión</span>
        </Button>
      </div>
    </div>
  );
}

export default function Sidebar() {
  const path = usePathname() || "/";
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  if (
    path.startsWith("/login") ||
    path.startsWith("/register") ||
    path.startsWith("/activar") ||
    path.startsWith("/onboarding")
  )
    return null;

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <>
      {/* Desktop — la barra sigue el tema elegido por el abogado (decisión de Pipe
          2026-08-24; anula la anterior de identidad de marca "siempre oscura"):
          los tokens (fondo, bordes, texto) resuelven según el tema activo. */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border/10 bg-background/90 backdrop-blur-md md:flex">
        <div className="px-5 py-5">
          <BrandMark size="sm" href="/" />
        </div>
        <div className="px-3">
          <button
            onClick={openCommandPalette}
            className="flex w-full items-center gap-2 rounded-md border border-border/20 bg-secondary/30 shadow-neu-sunken px-3 py-2 text-sm text-muted-foreground transition-all hover:bg-accent/40"
          >
            <Search className="h-4 w-4" />
            <span>Buscar…</span>
            <kbd className="ml-auto rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium">
              Ctrl K
            </kbd>
          </button>
        </div>
        <div className="mt-4 flex-1 overflow-y-auto px-3">
          <NavLinks />
        </div>
        <PieDeCuenta onLogout={logout} />
      </aside>

      {/* Mobile top bar — sigue el tema elegido, igual que el sidebar de escritorio
          (decisión de Pipe 2026-08-24). */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-background px-4 py-3 md:hidden">
        <BrandMark size="sm" href="/" />
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={openCommandPalette} aria-label="Buscar">
            <Search className="h-4 w-4" />
          </Button>
          <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Menú">
                <Menu className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="left-0 top-0 h-full max-w-[17rem] translate-x-0 translate-y-0 rounded-none border-r bg-background duration-200 data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left sm:rounded-none">
              <DialogTitle className="sr-only">Menú de navegación</DialogTitle>
              <div className="flex h-full flex-col">
                <div className="pb-4">
                  <BrandMark size="sm" href="/" />
                </div>
                <div className="flex-1 overflow-y-auto">
                  <NavLinks onNavigate={() => setMobileOpen(false)} />
                </div>
                <PieDeCuenta onLogout={logout} className="pt-3" />
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </header>
    </>
  );
}
