import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import "./globals.css";
import Sidebar from "./_components/Sidebar";
import AuthGate from "./_components/AuthGate";
import OnboardingGate from "./_components/OnboardingGate";
import CommandPalette from "./_components/CommandPalette";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
// Serif humanista para el texto jurídico (borradores, documentos): evoca lo impreso.
const newsreader = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
  style: ["normal", "italic"],
  adjustFontFallback: false,
});

export const metadata: Metadata = {
  title: "Mia — tu asistente jurídica",
  description: "Agente legal cognitivo para el despacho.",
};

// Evita el parpadeo de tema (FOUC): fija la clase antes del primer pintado.
const themeScript = `(function(){try{var t=localStorage.getItem('mia-theme');var d=t?t==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={cn(inter.variable, newsreader.variable)} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground">
        <AuthGate>
          <OnboardingGate />
          <CommandPalette />
          <div className="flex min-h-screen flex-col md:flex-row">
            <Sidebar />
            <main className="min-w-0 flex-1 bg-background">{children}</main>
          </div>
        </AuthGate>
      </body>
    </html>
  );
}
