// Alias de compatibilidad: «Asuntos» y «Proyectos» se fusionaron en «Casos» (D3).
// Nunca existió una lista en /asuntos (vivía en la raíz), pero el alias evita un
// 404 para cualquier enlace guardado con esta forma.
import { redirect } from "next/navigation";

export default function AsuntosAlias() {
  redirect("/casos");
}
