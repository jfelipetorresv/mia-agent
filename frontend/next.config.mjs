/** @type {import('next').NextConfig} */
const nextConfig = {
  // El gate verifica la COMPILACIÓN de TypeScript (corrección estructural). ESLint queda fuera
  // del build para que reglas de estilo no lo tumben; el type-check de TS sigue activo.
  eslint: { ignoreDuringBuilds: true },
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
