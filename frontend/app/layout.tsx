import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "./_components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mia — tu asistente jurídica",
  description: "Agente legal cognitivo para el despacho.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className={`${inter.className} text-gray-900`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="min-w-0 flex-1 bg-white">{children}</main>
        </div>
      </body>
    </html>
  );
}
