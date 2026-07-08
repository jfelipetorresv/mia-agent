"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, Search, Scale } from "lucide-react";
import { clearToken } from "@/lib/api";
import { NAV_ITEMS } from "./nav";
import ThemeToggle from "./ThemeToggle";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

function BrandMark() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <Scale className="h-4 w-4" />
      </div>
      <span className="text-lg font-semibold tracking-tight">Mia</span>
    </div>
  );
}

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
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
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

export default function Sidebar() {
  const path = usePathname() || "/";
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  if (path.startsWith("/login") || path.startsWith("/register")) return null;

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <>
      {/* Desktop */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/50 md:flex">
        <div className="px-5 py-5">
          <BrandMark />
        </div>
        <div className="px-3">
          <button
            onClick={openCommandPalette}
            className="flex w-full items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent"
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
        <div className="flex flex-col gap-1 border-t border-border p-3">
          <ThemeToggle />
          <Button variant="ghost" size="sm" className="w-full justify-start gap-2 text-muted-foreground" onClick={logout}>
            <LogOut className="h-4 w-4" />
            <span>Cerrar sesión</span>
          </Button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card/80 px-4 py-3 backdrop-blur md:hidden">
        <BrandMark />
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
            <DialogContent className="left-0 top-0 h-full max-w-[17rem] translate-x-0 translate-y-0 rounded-none border-r sm:rounded-none">
              <DialogTitle className="sr-only">Menú de navegación</DialogTitle>
              <div className="flex h-full flex-col">
                <div className="pb-4">
                  <BrandMark />
                </div>
                <div className="flex-1 overflow-y-auto">
                  <NavLinks onNavigate={() => setMobileOpen(false)} />
                </div>
                <div className="flex flex-col gap-1 border-t border-border pt-3">
                  <ThemeToggle />
                  <Button variant="ghost" size="sm" className="w-full justify-start gap-2 text-muted-foreground" onClick={logout}>
                    <LogOut className="h-4 w-4" />
                    <span>Cerrar sesión</span>
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </header>
    </>
  );
}
