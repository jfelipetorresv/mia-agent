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

  React.useEffect(() => {
    setThemeState(getStoredTheme());
  }, []);

  function choose(t: Theme) {
    setTheme(t);
    setThemeState(t);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size={compact ? "icon" : "sm"} className={cn(!compact && "w-full justify-start gap-2")}>
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
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
