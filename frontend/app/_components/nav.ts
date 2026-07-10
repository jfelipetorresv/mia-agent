import { MessagesSquare, LayoutGrid, BookOpen, Gauge, Users, Settings2, type LucideIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (p: string) => boolean;
};

/** Fuente única de navegación — la usan el Sidebar y el buscador (Ctrl+K). */
export const NAV_ITEMS: NavItem[] = [
  { href: "/chat", label: "Conversar", icon: MessagesSquare, match: (p) => p.startsWith("/chat") },
  { href: "/", label: "Asuntos", icon: LayoutGrid, match: (p) => p === "/" || p.startsWith("/asuntos") },
  { href: "/memoria", label: "Conocimiento", icon: BookOpen, match: (p) => p.startsWith("/memoria") },
  { href: "/dashboard", label: "Panel", icon: Gauge, match: (p) => p.startsWith("/dashboard") },
  { href: "/personas", label: "Personas jurídicas", icon: Users, match: (p) => p.startsWith("/personas") },
  { href: "/configurar", label: "Configuración", icon: Settings2, match: (p) => p.startsWith("/configurar") },
];
