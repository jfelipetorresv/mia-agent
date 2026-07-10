"use client";

import * as React from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { getStoredTheme, setTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Theme; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
  { value: "system", label: "Del sistema", icon: Monitor },
];

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [theme, setThemeState] = React.useState<Theme>("system");
  // El ícono se decide por el tema RESUELTO en <html>, no por el modificador
  // Tailwind `dark:` — este control vive dentro de la barra lateral, que fuerza
  // su propio scope `.dark` fijo por identidad de marca, así que `dark:` ya no
  // refleja el tema real del sitio y hay que leerlo directamente del DOM.
  const [isDark, setIsDark] = React.useState(false);

  const syncIsDark = React.useCallback(() => {
    if (typeof document !== "undefined") {
      setIsDark(document.documentElement.classList.contains("dark"));
    }
  }, []);

  React.useEffect(() => {
    setThemeState(getStoredTheme());
    syncIsDark();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", syncIsDark);
    return () => mq.removeEventListener("change", syncIsDark);
  }, [syncIsDark]);

  function choose(t: Theme) {
    setTheme(t);
    setThemeState(t);
    syncIsDark();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size={compact ? "icon" : "sm"} className={cn(!compact && "w-full justify-start gap-2")}>
          {isDark ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          {!compact && <span>Apariencia</span>}
          <span className="sr-only">Cambiar apariencia</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {OPTIONS.map((o) => {
          const Icon = o.icon;
          return (
            <DropdownMenuItem key={o.value} onClick={() => choose(o.value)}>
              <Icon className="h-4 w-4" />
              <span>{o.label}</span>
              {theme === o.value && <span className="ml-auto text-xs text-muted-foreground">•</span>}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
