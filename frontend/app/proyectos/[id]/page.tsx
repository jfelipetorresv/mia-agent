// Alias de compatibilidad: la ficha del caso vive ahora en /casos/[id] (D3).
// Los enlaces guardados a /proyectos/... siguen funcionando — no se rompe nada.
import { redirect } from "next/navigation";

export default async function ProyectoAlias({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/casos/${id}`);
}
