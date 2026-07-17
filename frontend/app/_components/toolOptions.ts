// Mia · lista compartida de "Herramientas" (Bloque C · C2).
// Extraído de onboarding/page.tsx y MiDespachoSection.tsx: antes cada pantalla tenía su
// propia copia de esta lista, y una podía quedar desactualizada frente a la otra (p. ej.
// una decía "Próximamente" de algo que la otra ya sabía que funcionaba). Ahora ambas
// importan de aquí — un solo lugar, una sola verdad.
//
// IMPORTANTE: estos checkboxes NO activan nada por sí mismos. Solo registran, como
// preferencia/contexto, qué herramientas usa el despacho (viajan a
// `memory.tools_that_survived` y quedan en el SOUL.md / resumen del perfil). La
// activación real de cada integración ocurre en Conexiones (dentro de Configuración) o,
// para Telegram, en la guía de activación paso a paso — nunca aquí.
export type ToolOption = { name: string; description: string; comingSoon?: boolean };

export const TOOL_OPTIONS: ToolOption[] = [
  { name: "Correo", description: "Mia vigila tus correos urgentes y te avisa." },
  { name: "Calendario", description: "Mia te recuerda tus eventos y audiencias próximas." },
  { name: "Gestor documental", description: "Mia consulta los documentos del despacho para responder." },
  {
    name: "Mensajería (Telegram)",
    description:
      "Habla con Mia desde tu celular, por texto o por voz. Se activa después con una guía corta de pasos, no aquí.",
  },
  {
    name: "Carpetas en la nube (OneDrive/Google Drive)",
    description: "Mia conoce las carpetas donde guardas tu trabajo.",
  },
  {
    name: "Notas del despacho",
    description: "Mia guarda y consulta tus notas. Se activa en Conexiones, dentro de Configuración.",
  },
];
