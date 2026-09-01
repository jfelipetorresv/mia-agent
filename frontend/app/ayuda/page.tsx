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
 * pantalla. Lo que se añade aquí es el formato: una tarjeta por sección, los
 * pasos numerados y un botón que lleva a la pantalla de la que habla — leer
 * sobre algo y tener que buscarlo después en el menú es media ayuda.
 *
 * DISEÑO. Rediseño Luxury: `<Card>` del sistema (neumorfismo por token, jamás
 * una tarjeta dibujada a mano) y tokens semánticos — nunca un color literal.
 * Sigue el tema que eligió el abogado, claro u oscuro.
 *
 * SIN JERGA. No aparece «HITL», «tenant», «pgvector» ni el nombre de un
 * endpoint: el abogado lee «caso», «revisar borrador», «lo que Mia aprendió».
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, LifeBuoy } from "lucide-react";
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
        pregúntame; lo demás se conecta cuando lo necesites. Aquí tienes cada pieza explicada
        y el botón que te lleva a ella.
      </NotaMia>

      {error ? (
        <Card padding="sm" className="mt-block border-destructive/30 bg-destructive/5">
          <p className="text-body text-destructive">{error}</p>
        </Card>
      ) : null}

      <div className="mt-block space-y-block">
        {secciones === null && !error
          ? [0, 1, 2].map((i) => (
              <Card key={i} padding="md" className="space-y-3">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </Card>
            ))
          : (secciones || []).map((s) => (
              <Card key={s.titulo} padding="md" className="space-y-3">
                <div className="flex items-start gap-3">
                  <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <h2 className="text-section">{s.titulo}</h2>
                    <p className="mt-1 text-body text-muted-foreground">{s.que_es}</p>
                  </div>
                </div>

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
                      {s.como.map((paso, i) => (
                        <li key={i} className="flex gap-2.5 text-body text-muted-foreground">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                            {i + 1}
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
              </Card>
            ))}
      </div>
    </PageShell>
  );
}
