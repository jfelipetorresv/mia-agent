/** @type {import('next').NextConfig} */
const nextConfig = {
  // Fase 1 instalador (frente B): standalone genera .next/standalone/server.js con el
  // subconjunto mínimo de node_modules, para empaquetar el frontend sin exigir `npm install`
  // completo en la máquina del abogado. No afecta `next dev` (solo cambia la salida de `next build`).
  output: "standalone",
  // Cabeceras de seguridad en TODAS las páginas (auditoría 2026-07):
  // - frame-ancestors/X-Frame-Options: nadie puede embeber la app en un iframe
  //   (clickjacking sobre los botones Aprobar/Rechazar).
  // - nosniff: el navegador no reinterpreta tipos de contenido.
  // - Referrer-Policy: las URLs internas no viajan a sitios externos.
  // - Permissions-Policy: la app no usa cámara/micrófono/geolocalización; se apagan.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
