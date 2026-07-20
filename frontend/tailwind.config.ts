import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        // CTA de marca: VERDE vibrante (--cta = 160 100% 42% en claro, 48% en
        // oscuro), NO terracota. El comentario anterior contradecía el valor real
        // y describía un color que nunca existió en el producto.
        // Usar con moderación: es el único llamado a la acción destacado.
        cta: {
          DEFAULT: "hsl(var(--cta))",
          foreground: "hsl(var(--cta-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      /* ------------------------------------------------------------------
       * ESCALA TIPOGRÁFICA SEMÁNTICA — seis roles, no trece tamaños.
       * Se escribe `text-title`, nunca `text-lg font-medium`.
       *
       *   display  30/36  600  Archivo   → un solo h1 por pantalla
       *   title    20/28  600  Archivo   → cabecera de pantalla / h2
       *   section  16/24  600  Archivo   → h3 (NUNCA comparte tamaño con body)
       *   body     15/24  400  Hind      → párrafo, celda, descripción
       *   label    13/18  500  Hind      → etiqueta de campo, botón, pestaña
       *   meta     12/16  400  Hind      → sello de tiempo, pie, contador
       *
       * La familia (Archivo vs Hind) la enlaza globals.css con un selector de
       * clase en @layer base, porque la API `fontSize` de Tailwind no acepta
       * font-family. Poner `font-serif` encima sigue ganando (utilities > base),
       * que es lo que queremos para el texto jurídico (Newsreader).
       *
       * Regla dura: h3 nunca comparte tamaño con el cuerpo. section (16) vs
       * body (15) parece poco, pero la jerarquía real la dan peso + familia
       * + color, no la escala bruta.
       * ------------------------------------------------------------------ */
      fontSize: {
        display: ["1.875rem", { lineHeight: "2.25rem", fontWeight: "600", letterSpacing: "-0.02em" }],
        title: ["1.25rem", { lineHeight: "1.75rem", fontWeight: "600", letterSpacing: "-0.01em" }],
        section: ["1rem", { lineHeight: "1.5rem", fontWeight: "600", letterSpacing: "-0.005em" }],
        body: ["0.9375rem", { lineHeight: "1.5rem", fontWeight: "400" }],
        label: ["0.8125rem", { lineHeight: "1.125rem", fontWeight: "500" }],
        meta: ["0.75rem", { lineHeight: "1rem", fontWeight: "400" }],
      },
      /* ------------------------------------------------------------------
       * RADIOS — TRES valores reales:
       *   sm  6px  → inputs, insignias, chips
       *   md 10px  → controles (botones, selects, ítems de lista)
       *   lg 14px  → superficies (tarjetas, paneles, diálogos)
       *   full     → SOLO avatares y píldoras de estado
       *
       * xl / 2xl / 3xl son ALIAS EN MIGRACIÓN, no niveles del sistema.
       * Antes `rounded-lg` y `rounded-xl` renderizaban idéntico (12px) y sumaban
       * 207 usos: el código insinuaba dos jerarquías que el ojo no veía. No se
       * borran todavía porque hay 146 usos vivos y romperlos de golpe tumbaría
       * pantallas; se vacían por migración en la capa 3 y entonces sí se
       * eliminan de este tema. NO USAR xl/2xl/3xl en código nuevo.
       * DEFAULT (`rounded`, 22 usos) pasa de 4px a 6px = alias de sm.
       * ------------------------------------------------------------------ */
      borderRadius: {
        DEFAULT: "0.375rem", // 6px — alias de sm (en migración)
        sm: "0.375rem", // 6px  · inputs, insignias
        md: "0.625rem", // 10px · controles
        lg: "var(--radius)", // 14px · superficies
        xl: "var(--radius)", // ALIAS de lg (en migración)
        "2xl": "1.125rem", // 18px · alias en migración
        "3xl": "1.375rem", // 22px · alias en migración
      },
      /* ELEVACIÓN — DOS niveles y nada más.
       * `shadow-flat`   → borde hairline, sin sombra (el defecto del producto).
       * `shadow-raised` → profundidad de tarjeta, tintada al fondo (no negro puro).
       * shadow-sm / md / lg / xl / 2xl SALEN DEL VOCABULARIO: si algo necesita
       * "más sombra" es que necesita más espacio o un borde, no más sombra. */
      boxShadow: {
        flat: "var(--elev-flat)",
        raised: "var(--elev-raised)",
      },
      /* ESPACIADO — respiración. La app entera era densidad de cabina
       * (gap-2 ×183 contra gap-6 ×4). `gap-block` separa bloques dentro de una
       * sección; `gap-section` / `py-section` separan secciones entre sí.
       * gap-1 queda reservado a grupos icono+texto. */
      spacing: {
        block: "var(--space-block)", // 1.5rem
        section: "var(--space-section)", // 3rem
      },
      /* Curva única de movimiento del producto: la misma MIA_EASE de la
       * bienvenida (app/_welcome/motion.ts). Antes convivían tres curvas y
       * cruzar de la bienvenida al producto se sentía como cambiar de app. */
      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.22, 1, 0.36, 1)",
        mia: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Entrada de mensajes del chat: sube + asienta (calma, no espectáculo).
        "message-in": {
          from: { opacity: "0", transform: "translateY(10px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        // Cursor de escritura de Mia (typewriter).
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        // Halo respirando del avatar de Mia mientras piensa.
        "pulse-soft": {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "0.7", transform: "scale(1.12)" },
        },
      },
      /* Todas las animaciones comparten MIA_EASE = cubic-bezier(0.22, 1, 0.36, 1),
       * la curva de la bienvenida (app/_welcome/motion.ts:12). Excepciones
       * justificadas: `blink` es step-end (un cursor no acelera) y `pulse-soft`
       * es ease-in-out porque respira (simétrica de ida y vuelta).
       * Las dos animaciones infinitas quedan neutralizadas por el bloque
       * @media (prefers-reduced-motion: reduce) de globals.css. */
      animation: {
        "accordion-down": "accordion-down 0.2s cubic-bezier(0.22, 1, 0.36, 1)",
        "accordion-up": "accordion-up 0.2s cubic-bezier(0.22, 1, 0.36, 1)",
        "fade-in": "fade-in 0.2s cubic-bezier(0.22, 1, 0.36, 1)",
        "slide-up": "slide-up 0.25s cubic-bezier(0.22, 1, 0.36, 1)",
        "message-in": "message-in 0.3s cubic-bezier(0.22, 1, 0.36, 1)",
        blink: "blink 1s step-end infinite",
        "pulse-soft": "pulse-soft 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
