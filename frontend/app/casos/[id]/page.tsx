"use client";

// D3 · «Casos»: ficha ÚNICA del caso. Asuntos y Proyectos siempre fueron la misma
// tabla (matters, columna kind — migración 028); aquí se despacha al espacio de
// trabajo correcto según cómo trabaja Mia en este caso:
//   kind='asunto'   → CasoConBorrador (borrador + aprobación del abogado)
//   kind='proyecto' → CasoDirecto (respuesta directa, sin parada de aprobación)
// El control para cambiar el modo vive dentro de cada espacio (ModoDeTrabajo);
// cuando el backend confirma el cambio, este despachador re-monta el otro espacio
// sin salir de la página.

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";
import { Button } from "@/components/ui/button";
import CasoConBorrador from "./CasoConBorrador";
import CasoDirecto from "./CasoDirecto";
import type { CaseKind } from "./_components/ModoDeTrabajo";

export default function CasoPage({ params }: { params: Promise<{ id: string }> }) {
  const matterId = use(params).id;
  const router = useRouter();
  const [kind, setKind] = useState<CaseKind | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    apiGet<{ kind?: string }>(`/api/matters/${matterId}`)
      .then((m) => setKind(m.kind === "proyecto" ? "proyecto" : "asunto"))
      .catch(() => setNotFound(true));
  }, [matterId]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-md px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">No pude abrir este caso.</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/casos")}>
          Volver a los casos
        </Button>
      </div>
    );
  }

  if (kind === null) {
    return (
      <div className="flex h-[100dvh] items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    );
  }

  // key={kind}: al cambiar el modo se re-monta el espacio de trabajo desde cero
  // (estados internos incluidos) — es otro flujo, no una variación del mismo.
  return kind === "proyecto" ? (
    <CasoDirecto key={kind} matterId={matterId} onKindChange={setKind} />
  ) : (
    <CasoConBorrador key={kind} matterId={matterId} onKindChange={setKind} />
  );
}
