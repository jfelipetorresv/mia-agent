// D3 · «Casos»: la raíz redirige a la lista única de casos. La señal ?nuevo=1
// (buscador Ctrl+K y enlaces guardados) viaja con la redirección para que el
// diálogo de creación se abra igual que antes.
import { redirect } from "next/navigation";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  redirect(sp.nuevo === "1" ? "/casos?nuevo=1" : "/casos");
}
