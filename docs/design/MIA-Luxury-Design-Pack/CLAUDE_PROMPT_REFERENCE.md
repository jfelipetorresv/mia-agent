# Copiar y Pegar en Claude: Instrucciones de Rediseño de MIA

Si vas a abrir un nuevo chat con **Claude Code** o cualquier agente de IA para que implemente el diseño en el código, puedes **copiar y pegar el siguiente bloque de texto**. Esto le dará todo el contexto de inmediato y evitará que cometa errores con las rutas de los archivos o la paleta de colores.

---

### 📋 Prompt para Claude:

```markdown
Por favor, implementa el rediseño unificado "MIA Modern & Luxury UI" en el frontend Next.js de este repositorio.

Sigue rigurosamente estas especificaciones técnicas que se encuentran en el paquete de diseño local:
1. Lee la guía técnica detallada en:
   [HOW_TO_REPLICATE_STYLE.md](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/MIA-Luxury-Design-Pack/HOW_TO_REPLICATE_STYLE.md)
2. Aplica la paleta de colores (Teal Profundo y Azul Oxígeno) y los tokens de relieve neumórfico (`shadow-neu-raised` y `shadow-neu-sunken`) en modo claro y modo oscuro según las variables CSS definidas en esa guía.
3. Asegúrate de modificar los siguientes componentes clave en el frontend para reflejar la consistencia visual:
   - `frontend/app/globals.css`: Inyectar variables de color de tema claro/oscuro y el efecto de fondo animado `.bg-mesh-living` con textura de ruido.
   - `frontend/tailwind.config.ts`: Extender las sombras neumórficas y la animación de levitación `animate-float`.
   - `frontend/components/ui/card.tsx` y `button.tsx`: Modificar las variantes por defecto para aplicar los relieves y efectos táctiles activos (`active:shadow-neu-sunken`).
   - `frontend/app/page.tsx` (Dashboard de Asuntos): Aplicar el diseño de Bento Grid neumórfico claro/oscuro con hover 3D y el Empty State del Prisma SVG 3D flotando con `animate-float`.
   - `frontend/app/_components/Sidebar.tsx`: Integrar los botones de navegación con relieve y estados de selección.

Puedes ver la referencia visual de cómo deben quedar las pantallas en la carpeta de imágenes:
[assets/](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/MIA-Luxury-Design-Pack/assets)
- Onboarding (Bienvenida): `onboarding_light.jpg` y `onboarding_dark.jpg`
- Dashboard de Asuntos: `matters_light.jpg` y `matters_dark.jpg`
- Command Center Modal (Ctrl+K): `command_center_light.jpg` y `command_center_dark.jpg`
- Dashboard Overview Analítico: `dashboard_overview_light.jpg` y `dashboard_overview_dark.jpg`

No modifiques la lógica jurídica ni de seguridad del backend, enfócate 100% en la fidelidad estética y portabilidad del frontend.
```
