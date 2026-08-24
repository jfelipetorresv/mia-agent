"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Plus, Moon, Sun, Monitor } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { NAV_ITEMS } from "./nav";
import { clearToken } from "@/lib/api";
import { setTheme } from "@/lib/theme";

/** Buscador de comandos global (Ctrl/Cmd+K): navegación + acciones rápidas. */
export default function CommandPalette() {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const pathname = usePathname() || "/";

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const onAuthPage = pathname.startsWith("/login") || pathname.startsWith("/register");
  if (onAuthPage) return null;

  function run(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Busca o escribe un comando…" />
      <CommandList>
        <CommandEmpty>Nada por aquí. Prueba con otra palabra.</CommandEmpty>
        <CommandGroup heading="Ir a">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <CommandItem key={item.href} value={item.label} onSelect={() => run(() => router.push(item.href))}>
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>
        <CommandGroup heading="Acciones">
          <CommandItem value="Nuevo caso" onSelect={() => run(() => router.push("/casos?nuevo=1"))}>
            <Plus className="h-4 w-4" />
            <span>Nuevo caso</span>
            <CommandShortcut>N</CommandShortcut>
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Apariencia">
          <CommandItem value="Tema claro" onSelect={() => run(() => setTheme("light"))}>
            <Sun className="h-4 w-4" />
            <span>Tema claro</span>
          </CommandItem>
          <CommandItem value="Tema oscuro" onSelect={() => run(() => setTheme("dark"))}>
            <Moon className="h-4 w-4" />
            <span>Tema oscuro</span>
          </CommandItem>
          <CommandItem value="Tema del sistema" onSelect={() => run(() => setTheme("system"))}>
            <Monitor className="h-4 w-4" />
            <span>Tema del sistema</span>
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Sesión">
          <CommandItem
            value="Cerrar sesión"
            onSelect={() =>
              run(() => {
                clearToken();
                router.replace("/login");
              })
            }
          >
            <LogOut className="h-4 w-4" />
            <span>Cerrar sesión</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
