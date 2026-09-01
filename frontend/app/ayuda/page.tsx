"use client";

/**
 * EL MANUAL DE MIA · pantalla propia
 * ==================================
 *
 * Pipe, bitácora 2026-08-19 (punto 15): «qué hace cada sección de MIA debe ser
 * su propia pestaña con manual para dummies». Hasta hoy vivía plegado dentro de
 * Configuración → «Primeros pasos», en un acordeón con tres frases por sección:
 * el abogado que abre Mia por primera vez no encuentra ahí un manual, y de
 * hecho no llegaba a abrirlo.
 *
 * QUÉ CAMBIA. El contenido sale del MISMO sitio de antes (`MIA_SECTIONS` en el
 * backend, ahora ampliado con «cuándo sirve» y «cómo se usa»), así que la ayuda
 * y el recorrido de configuración no pueden decir cosas distintas de la misma
 * pantalla. Lo que se añade aquí es el formato: los pasos numerados y un botón
 * que lleva a la pantalla de la que habla — leer sobre algo y tener que buscarlo
 * después en el menú es media ayuda.
 *
 * POR QUÉ ES UN ACORDEÓN (corrección de Pipe, 2026-09-01). Antes las ocho
 * secciones se mostraban abiertas a la vez: 3.034 px de alto, ocho bloques
 * idénticos apilados. Pipe lo describió como «muy densa y difícil». La
 * información no sobraba; sobraba tenerla toda desplegada. Ahora el abogado ve
 * las ocho de un vistazo —el mapa completo de la casa cabe sin desplazarse— y
 * abre la que le interesa; al abrir una, se cierra la anterior. La primera nace
 * abierta para que la pantalla nunca se vea como una lista muerta.
 *
 * DISEÑO. Rediseño Luxury: `<Card>` del sistema (neumorfismo por token, jamás
 * una tarjeta dibujada a mano) y tokens semánticos — nunca un color literal.
 * Sigue el tema que eligió el abogado, claro u oscuro.
 *
 * ACCESIBILIDAD. Cada cabecera es un `<button>` real con `aria-expanded` y
 * `aria-controls`: se abre con Enter o Espacio y el lector de pantalla anuncia
 * si la sección está abierta. Quien no usa ratón recorre las ocho con Tab.
 *
 * SIN JERGA. No aparece «HITL», «tenant», «pgvector» ni el nombre de un
 * endpoint: el abogado lee «caso», «revisar borrador», «lo que Mia aprendió».
 */

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, LifeBuoy } from "lucide-react";
import { apiGet } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageShell } from "@/app/_components/PageShell";
import { NotaMia } from "@/app/_components/NotaMia";

type Seccion = {
  titulo: string;
  que_es: string;
  para_que: string;
  /** A dónde lleva el botón de la tarjeta. Puede faltar en datos antiguos. */
  ruta?: string;
  /** En qué momento del trabajo real sirve. */
  cuando?: string;
  /** Los pasos concretos, en el orden en que se hacen. */
  como?: string[];
};

export default function AyudaPage() {
  const [secciones, setSecciones] = useState<Seccion[] | null>(null);
  const [error, setError] = useState("");
  // Cuál está abierta. La primera nace abierta: una lista toda cerrada parece
  // una pantalla vacía y obliga a un clic para ver que aquí hay algo.
  const [abierta, setAbierta] = useState(0);
  const baseId = useId();

  useEffect(() => {
    let vivo = true;
    apiGet<{ secciones: Seccion[] }>("/api/setup/manual")
      .then((res) => {
        if (vivo) setSecciones(res.secciones || []);
      })
      .catch(() => {
        // Un manual que no carga no puede dejar la pantalla en blanco sin decir
        // por qué: el abogado que vino a buscar ayuda merece saber qué pasó.
        if (vivo) setError("No pude cargar el manual en este momento. Intenta de nuevo.");
      });
    return () => {
      vivo = false;
    };
  }, []);

  return (
    <PageShell
      title="Cómo funciona Mia"
      subtitle="Qué hace cada parte, cuándo te sirve y cómo se usa."
    >
      <NotaMia id="ayuda-manual" icon={LifeBuoy} titulo="Léelo en el orden que quieras">
        No hace falta configurarlo todo para empezar. Abre un caso, súbeme el expediente y
        pregúntame; lo demás se conecta cuando lo necesites. Toca cualquier sección para ver
        cuándo te sirve y cómo se usa.
      </NotaMia>

      {error ? (
        <Card padding="sm" className="mt-block border-destructive/30 bg-destructive/5">
          <p className="text-body text-destructive">{error}</p>
        </Card>
      ) : null}

      {secciones === null && !error ? (
        <Card padding="md" className="mt-block space-y-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </Card>
      ) : null}

      {secciones !== null && secciones.length > 0 ? (
        <Card padding="none" className="mt-block overflow-hidden">
          {secciones.map((s, i) => {
            const abierto = abierta === i;
            const idPanel = `${baseId}-panel-${i}`;
            const idBoton = `${baseId}-boton-${i}`;
            return (
              <div
                key={s.titulo}
                className={i > 0 ? "border-t border-border/60" : undefined}
              >
                <h2>
                  <button
                    type="button"
                    id={idBoton}
                    aria-expanded={abierto}
                    aria-controls={idPanel}
                    // Cerrar la que ya está abierta la dejaría sin ninguna abierta;
                    // eso devuelve la pantalla al estado de lista muerta, así que
                    // tocar la abierta no la cierra: solo se cambia de sección.
                    onClick={() => setAbierta(i)}
                    className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                  >
                    <ChevronDown
                      aria-hidden="true"
                      className={`h-4 w-4 shrink-0 text-primary transition-transform ${
                        abierto ? "rotate-0" : "-rotate-90"
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-section">{s.titulo}</span>
                      {!abierto ? (
                        <span className="mt-0.5 block truncate text-body text-muted-foreground">
                          {s.que_es}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </h2>

                <div
                  id={idPanel}
                  role="region"
                  aria-labelledby={idBoton}
                  hidden={!abierto}
                  className="space-y-3 px-5 pb-5 pl-12"
                >
                  <p className="text-body text-muted-foreground">{s.que_es}</p>
                  <p className="text-body text-muted-foreground">{s.para_que}</p>

                  {s.cuando ? (
                    <p className="text-body">
                      <span className="font-medium text-foreground">Cuándo te sirve: </span>
                      <span className="text-muted-foreground">{s.cuando}</span>
                    </p>
                  ) : null}

                  {s.como && s.como.length > 0 ? (
                    <div>
                      <p className="text-body font-medium text-foreground">Cómo se usa</p>
                      <ol className="mt-1.5 space-y-1.5">
                        {s.como.map((paso, j) => (
                          <li key={j} className="flex gap-2.5 text-body text-muted-foreground">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                              {j + 1}
                            </span>
                            <span>{paso}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}

                  {s.ruta ? (
                    <div>
                      <Button asChild size="sm" variant="outline" className="gap-1.5">
                        <Link href={s.ruta}>
                          Ir a {s.titulo}
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </Card>
      ) : null}
    </PageShell>
  );
}
