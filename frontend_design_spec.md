# Especificación Técnica de Diseño: "MIA Onboarding, Dashboard & Command Center Unificados"

> [!IMPORTANT]
> **REGLA DE ORO ESTÉTICA OBLIGATORIA (MASTER SYSTEM):** 
> Toda la aplicación MIA debe responder de forma estricta y coherente a la integración de tres piezas canónicas:
> 1. **Onboarding Principal:** Estilo de lujo espacial con titular dorado, escultura 3D de cristal y botón píldora Azul Teal (`mia_onboarding_unified_1785902705160.jpg`).
> 2. **Dashboard de Asuntos:** Layout Neumórfico Pro con barra lateral de navegación, buscador incrustado, filtros y tarjetas Bento (`Revisión Contrato Suministro TechCorp S.A.` con badge `Borrador por revisar`, `Demanda Laboral v. López`, `Constitución Novatech`, `Acuerdo Confidencialidad XY`, `Litigio Patente Z`).
> 3. **MIA Command Center Modal:** Ventana modal flotante con cabecera `M MIA COMMAND CENTER`, buscador destacado y acciones rápidas (`Nuevo asunto`, `Buscar jurisprudencia`, `Revisar citas`, `Redactar documento`).
> 4. **Logotipo Maestro de Marca (Opción A):** Isotipo 3D del Octaedro de Cristal Prismático rodeado por el Anillo Orbital en Plata Liquid/Titanium sobre fondo negro profundo y tipografía `MIA - Legal Intelligence` en platino monocromático.

Este documento es la **fuente de verdad** para que cualquier desarrollador o agente de IA (como Claude Code o Gemini) implemente y aplique la nueva interfaz visual unificada en el frontend.

---

## 🎨 1. Sistema de Tokens y Paleta Unificada

El diseño está unificado bajo una paleta de **Teal Profundo y Azul Oxígeno**, combinados con una escala de grises suaves que forman los relieves tridimensionales.

### Variables en `frontend/app/globals.css`
```css
:root {
  /* Fondo claro neumórfico */
  --background: 210 25% 97%; /* #F4F6F9 */
  --foreground: 220 30% 10%; /* Azul oscuro de contraste */
  --card: 0 0% 100%;
  
  --primary: 188 100% 28%; /* Teal principal */
  --cta: 188 100% 32%; /* Teal vibrante para acciones */
  --border: 210 20% 90%;
  
  /* Sombras Neumórficas Claras (Relieve e Incrustado) */
  --neu-raised: 
    6px 6px 14px hsl(210 20% 88%), 
    -6px -6px 14px hsl(0 0% 100%), 
    inset 0 1px 0 hsl(188 100% 28% / 0.03);
  --neu-sunken: 
    inset 4px 4px 8px hsl(210 20% 88%), 
    inset -4px -4px 8px hsl(0 0% 100%);
}

.dark {
  /* Fondo oscuro y profundo */
  --background: 200 15% 4%; /* #07090b */
  --foreground: 200 15% 90%;
  --card: 200 15% 7%; /* Tarjetas oscuras */
  
  --primary: 188 75% 48%; /* Teal brillante */
  --cta: 188 90% 50%; /* Teal de acción */
  --border: 200 15% 12%;
  
  /* Sombras Neumórficas Oscuras */
  --neu-raised: 
    8px 8px 20px hsl(0 0% 0% / 0.6), 
    -8px -8px 20px hsl(200 15% 10% / 0.35), 
    inset 0 1px 1px hsl(188 75% 48% / 0.15);
  --neu-sunken: 
    inset 6px 6px 12px hsl(0 0% 0% / 0.7), 
    inset -6px -6px 12px hsl(200 15% 10% / 0.2);
}
```

---

## 🛠️ 2. Clases Utilitarias Registradas en Tailwind
Cualquier agente debe usar estas clases exclusivas para dar estilo a las superficies:

- `shadow-neu-raised`: Aplica el relieve tridimensional (efecto de tarjeta que sale del fondo).
- `shadow-neu-sunken`: Aplica el efecto incrustado (para inputs, cajas de búsqueda e iconos activos).
- `animate-float`: Animación de levitación 3D suave (para ilustraciones u orbes).
- `bg-mesh-living`: Fondo vivo animado con mesh gradient y textura de ruido analógica sutil.

---

## 🏛️ 3. Reglas de Estilo por Componente

### A. Tarjetas y Paneles (`Card`)
Las tarjetas **no deben tener bordes duros** en el tema claro. Deben fusionarse con el fondo usando sombras:
```tsx
// Estructura ideal de Tarjeta Neumórfica
<div className="rounded-lg bg-card/85 backdrop-blur-sm p-6 shadow-neu-raised border border-border/10 transition-all duration-300 hover:-translate-y-1 hover:shadow-[var(--neu-raised),_0_12px_24px_hsl(var(--primary)/0.12)]">
  {/* Contenido */}
</div>
```

### B. Campos de Texto (`Input`, `Textarea`)
Deben dar la sensación de estar esculpidos hacia adentro (incrustados):
```tsx
<input className="w-full bg-secondary/30 rounded-md px-4 py-2 border border-border/20 shadow-neu-sunken focus:ring-1 focus:ring-primary/40 outline-none" />
```

### C. Botones y Pestañas (`Button`, `Tabs`)
- **Estado normal:** Relieve suave (`shadow-neu-raised`).
- **Estado hover:** Elevación de 1px.
- **Estado activo/click (Active):** Se convierte en incrustado (`active:shadow-neu-sunken` o `data-[state=active]:shadow-neu-sunken`), dando la sensación física de presionar un botón real.

---

## 📂 4. Archivos Clave a Refactorizar

Para completar la transición completa al 100% de la UI, se deben actualizar los siguientes archivos:

1. **[`frontend/components/ui/card.tsx`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/mia/frontend/components/ui/card.tsx):** Cambiar `border` y `shadow-sm` por `shadow-neu-raised` y `border-border/10`.
2. **[`frontend/components/ui/button.tsx`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/mia/frontend/components/ui/button.tsx):** Añadir la variante neumórfica que aplique `shadow-neu-raised` en reposo y `active:shadow-neu-sunken` en click.
3. **[`frontend/app/_components/Sidebar.tsx`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/mia/frontend/app/_components/Sidebar.tsx):** Unificar los botones de navegación con la paleta de Teal, aplicando `shadow-neu-sunken` sobre el botón activo del menú.
4. **[`frontend/app/chat/page.tsx` o `frontend/app/asuntos/[id]/page.tsx`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/mia/frontend/app/asuntos/[id]/page.tsx):** Aplicar la estructura de pantalla dividida con bordes suavizados y sombras neumórficas, y colocar el pipeline de progreso de IA con los tres estados unificados.
