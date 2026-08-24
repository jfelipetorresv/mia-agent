// Alias de compatibilidad: «Asuntos» y «Proyectos» se fusionaron en «Casos» (D3).
// La lista única vive en /casos; este alias evita un 404 en enlaces guardados.
import { redirect } from "next/navigation";

export default function ProyectosAlias() {
  redirect("/casos");
}
