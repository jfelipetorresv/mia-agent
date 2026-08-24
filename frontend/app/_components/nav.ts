import {
  MessagesSquare,
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
 * D3 · «Casos»: Asuntos y Proyectos eran la MISMA tabla con dos pestañas; ahora
 * son un solo ítem. La raíz `/`, `/asuntos/...` y `/proyectos/...` redirigen a
 * `/casos` (alias de compatibilidad) — por eso el match cubre las cuatro formas.
 */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Panel", icon: Gauge, match: (p) => p.startsWith("/dashboard") },
  { href: "/chat", label: "Conversar", icon: MessagesSquare, match: (p) => p.startsWith("/chat") },
  {
    href: "/casos",
    label: "Casos",
    icon: FolderKanban,
    match: (p) =>
      p === "/" || p.startsWith("/casos") || p.startsWith("/asuntos") || p.startsWith("/proyectos"),
  },
  { href: "/memoria", label: "Conocimiento", icon: BookOpen, match: (p) => p.startsWith("/memoria") },
  { href: "/personas", label: "Agentes jurídicos", icon: Users, match: (p) => p.startsWith("/personas") },
  { href: "/configurar", label: "Configuración", icon: Settings2, match: (p) => p.startsWith("/configurar") },
];
