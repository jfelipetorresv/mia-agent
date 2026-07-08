export type Theme = "light" | "dark" | "system";

const KEY = "mia-theme";

/** Aplica el tema al <html> (añade/quita la clase `dark`). */
export function applyTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", dark);
}

/** Lee el tema guardado (o "system" por defecto). */
export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  const t = window.localStorage.getItem(KEY);
  return t === "light" || t === "dark" || t === "system" ? t : "system";
}

/** Guarda y aplica el tema. */
export function setTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  if (theme === "system") window.localStorage.removeItem(KEY);
  else window.localStorage.setItem(KEY, theme);
  applyTheme(theme);
}
