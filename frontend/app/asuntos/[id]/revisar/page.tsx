// Alias de compatibilidad: la revisión del borrador vive ahora en
// /casos/[id]/revisar (D3). Los enlaces guardados siguen funcionando.
import { redirect } from "next/navigation";

export default async function RevisarAlias({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/casos/${id}/revisar`);
}
