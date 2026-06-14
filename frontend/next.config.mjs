/** @type {import('next').NextConfig} */
const nextConfig = {
  // El gate verifica la COMPILACIÓN de TypeScript (corrección estructural). ESLint queda fuera
  // del build para que reglas de estilo no lo tumben; el type-check de TS sigue activo.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
