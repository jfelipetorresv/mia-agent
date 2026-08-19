import {
  MessagesSquare,
  LayoutGrid,
  FolderKanban,
  BookOpen,
  Gauge,
  Users,
  Settings2,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (p: string) => boolean;
};

/**
 * Fuente única de navegación — la usan el Sidebar y el buscador (Ctrl+K).
 *
 * EL PANEL VA PRIMERO. Era el 5.º de 7 mientras es la pantalla que responde
 * «¿qué me toca hoy?»: el abogado entraba y tenía que ir a buscarla. Al ser
 * fuente única, mover el elemento aquí reordena el Sidebar y el buscador de
 * un golpe. El aterrizaje después de entrar se decide en `login/page.tsx`.
 *
 * Lo que NO se toca todavía: la ruta raíz `/` sigue siendo Asuntos. Cambiarla
 * obliga a revisar los nueve archivos que enlazan a `/` y es un cambio aparte.
 */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Panel", icon: Gauge, match: (p) => p.startsWith("/dashboard") },
  { href: "/chat", label: "Conversar", icon: MessagesSquare, match: (p) => p.startsWith("/chat") },
  { href: "/", label: "Asuntos", icon: LayoutGrid, match: (p) => p === "/" || p.startsWith("/asuntos") },
  { href: "/proyectos", label: "Proyectos", icon: FolderKanban, match: (p) => p.startsWith("/proyectos") },
  { href: "/memoria", label: "Conocimiento", icon: BookOpen, match: (p) => p.startsWith("/memoria") },
  { href: "/personas", label: "Agentes jurídicos", icon: Users, match: (p) => p.startsWith("/personas") },
  { href: "/configurar", label: "Configuración", icon: Settings2, match: (p) => p.startsWith("/configurar") },
];
