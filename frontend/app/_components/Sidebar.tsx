"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Asuntos", match: (p: string) => p === "/" || p.startsWith("/asuntos") },
  { href: "/memoria", label: "Conocimiento", match: (p: string) => p.startsWith("/memoria") },
  { href: "/dashboard", label: "Panel de control", match: (p: string) => p.startsWith("/dashboard") },
];

export default function Sidebar() {
  const path = usePathname() || "/";
  const router = useRouter();
  if (path.startsWith("/login") || path.startsWith("/register")) return null;
  return (
    <aside className="flex w-[220px] shrink-0 flex-col border-r border-gray-200 bg-[#f8f9fa]">
      <div className="px-6 py-6 text-2xl font-semibold tracking-tight text-gray-900">Mia</div>
      <nav className="flex flex-col gap-1 px-3">
        {LINKS.map((l) => {
          const active = l.match(path);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`border-l-2 px-3 py-2 text-sm font-medium transition-colors ${
                active ? "border-gray-900 bg-gray-100 text-gray-900" : "border-transparent text-gray-600 hover:bg-gray-100"
              }`}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto p-3">
        <button
          onClick={() => {
            clearToken();
            router.replace("/login");
          }}
          className="w-full px-3 py-2 text-left text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
        >
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
