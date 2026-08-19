# Guía de Réplica Estética: MIA Premium & Luxury UI

Esta guía contiene los pasos exactos, clases utilitarias, variables de diseño y mejores prácticas para replicar o montar la nueva identidad visual de **MIA (Legal Intelligence)** en cualquier proyecto frontend basado en **React / Next.js, Tailwind CSS y Framer Motion**.

---

## 🎨 1. Sistema de Colores y Tokens (Tailwind & CSS Variables)

Para lograr el efecto neumórfico tridimensional limpio (tanto en modo claro como oscuro) sin ensuciar la interfaz, debes registrar las siguientes variables CSS en tu archivo de estilos globales (generalmente `globals.css` o `app.css`).

### Configuración en `frontend/app/globals.css`

```css
@layer base {
  :root {
    /* Fondo claro neumórfico (acero/crema suave) */
    --background: 210 25% 97%; /* #F4F6F9 */
    --foreground: 220 30% 10%; /* Azul oscuro de contraste */
    --card: 0 0% 100%;
    
    --primary: 188 100% 28%; /* Teal principal de MIA */
    --cta: 188 100% 32%; /* Teal vibrante para botones de acción */
    --border: 210 20% 90%;
    
    /* Sombras Neumórficas Claras (Efecto de Relieve y Bajo Relieve) */
    --neu-raised: 
      6px 6px 14px hsl(210 20% 88%), 
      -6px -6px 14px hsl(0 0% 100%), 
      inset 0 1px 0 hsl(188 100% 28% / 0.03);
    
    --neu-sunken: 
      inset 4px 4px 8px hsl(210 20% 88%), 
      inset -4px -4px 8px hsl(0 0% 100%);
  }

  .dark {
    /* Fondo oscuro de lujo (espacial profundo) */
    --background: 200 15% 4%; /* #07090b */
    --foreground: 200 15% 90%;
    --card: 200 15% 7%; /* Tarjetas oscuras */
    
    --primary: 188 75% 48%; /* Teal brillante */
    --cta: 188 90% 50%; /* Teal de acción brillante */
    --border: 200 15% 12%;
    
    /* Sombras Neumórficas Oscuras (Brillos en volumen y sombras profundas) */
    --neu-raised: 
      8px 8px 20px hsl(0 0% 0% / 0.6), 
      -8px -8px 20px hsl(200 15% 10% / 0.35), 
      inset 0 1px 1px hsl(188 75% 48% / 0.15);
    
    --neu-sunken: 
      inset 6px 6px 12px hsl(0 0% 0% / 0.7), 
      inset -6px -6px 12px hsl(200 15% 10% / 0.2);
  }
}
```

---

## 🛠️ 2. Clases Utilitarias en `tailwind.config.ts`

Extiende tu configuración de Tailwind CSS para incluir las utilidades de sombreado y animaciones de levitación.

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  theme: {
    extend: {
      boxShadow: {
        // Enlaza las variables CSS del paso anterior
        "neu-raised": "var(--neu-raised)",
        "neu-sunken": "var(--neu-sunken)",
      },
      animation: {
        // Levitación suave en bucle para elementos e ilustraciones 3D
        "float": "float 6s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px) rotate(0deg)" },
          "50%": { transform: "translateY(-12px) rotate(2deg)" },
        },
      },
    },
  },
};
export default config;
```

---

## 🌊 3. Creación del Fondo Vivo (Living Background)

Para evitar los colores planos aburridos, la interfaz de MIA utiliza un gradiente dinámico y una textura de ruido analógico sutil (grano).

1. **Mesh Gradient Animado:** Añade un fondo con degradados de movimiento lento en tu CSS.
2. **Textura de Ruido (Noise Overlay):** Superpone un SVG en línea como máscara repetitiva.

### Código para `globals.css`
```css
.bg-mesh-living {
  background-color: hsl(var(--background));
  background-image: 
    radial-gradient(at 0% 0%, hsla(188, 100%, 30%, 0.08) 0px, transparent 50%),
    radial-gradient(at 100% 0%, hsla(210, 40%, 80%, 0.12) 0px, transparent 50%),
    radial-gradient(at 50% 100%, hsla(188, 70%, 40%, 0.06) 0px, transparent 50%);
  background-attachment: fixed;
  position: relative;
}

/* Capa de grano analógico táctil */
.bg-mesh-living::before {
  content: "";
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.035; /* 3.5% en claro - ajusta a 0.045 en oscuro */
  pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
}
```

---

## 🏛️ 4. Guía de Construcción por Componentes

### A. Las Tarjetas del Dashboard (`Card`)
Las tarjetas neumórficas **no deben tener bordes duros** en el tema claro. Deben emerger del fondo usando la sombra de relieve y transformarse fluidamente en hover:

```tsx
export const MatterCard = ({ title, status, description }) => {
  return (
    <div className="rounded-2xl bg-card/80 backdrop-blur-md p-6 shadow-neu-raised border border-border/10 transition-all duration-300 hover:-translate-y-1 hover:shadow-[var(--neu-raised),_0_12px_24px_rgba(14,116,144,0.12)]">
      <div className="flex items-center gap-3">
        {/* El contenedor del icono se esculpe hacia adentro */}
        <div className="p-3 rounded-xl bg-slate-100 shadow-neu-sunken dark:bg-slate-900/50">
          <FolderIcon className="h-6 w-6 text-primary" />
        </div>
        <h3 className="font-bold text-lg">{title}</h3>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{description}</p>
    </div>
  );
};
```

### B. Los Botones Físicos (`Button`)
Los botones neumórficos deben reaccionar al clic simulando que se presionan físicamente dentro de la pantalla (de relieve a bajo relieve):

```tsx
// CSS o clase de Tailwind
const buttonClass = "px-6 py-3 rounded-full font-semibold shadow-neu-raised transition-all active:shadow-neu-sunken hover:scale-[1.01]";
```

---

## 🗂️ 5. Estructura de esta Carpeta de Recursos

Para que repliques el diseño de forma local, esta carpeta contiene los siguientes recursos:

* 📁 **[`assets/`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/MIA-Luxury-Design-Pack/assets)**: Carpeta local con todos los renders en alta definición del Onboarding, Dashboard, Chat Split-Screen, Command Center y las opciones del Logotipo de Lujo.
* 🌐 **[`MIA_Interactive_UI_Preview.html`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/MIA-Luxury-Design-Pack/MIA_Interactive_UI_Preview.html)**: Prototipo funcional interactivo en HTML con estilos Tailwind CSS integrados para que pruebes los flows de navegación del Modelo Claro.
* 🛡️ **[`MIA_Logo_Options.html`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/MIA-Luxury-Design-Pack/MIA_Logo_Options.html)**: Caja de arena interactiva que renderiza vectorialmente las 5 opciones de isotipo basadas en el octaedro de cristal.
