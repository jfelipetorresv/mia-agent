"use client";

/**
 * LA NOTA DE MIA
 * ==============
 *
 * Pipe, 2026-08-19: «notas explicativas donde corresponda, vanguardistas y
 * amigables». El abogado no es técnico y no tiene por qué deducir para qué
 * sirve una pantalla por el nombre de su pestaña. Esta es la pieza que lo
 * dice, con la voz de Mia, en el sitio donde hace falta.
 *
 * POR QUÉ NO ES UN TOOLTIP. Un tooltip esconde la explicación detrás de un
 * gesto que solo hace quien ya sabe que ahí hay algo. La nota es VISIBLE desde
 * el primer segundo, discreta (no compite con el contenido) y CERRABLE: quien
 * ya la leyó la aparta y no vuelve a verla — el cierre se recuerda en este
 * equipo (`localStorage`), no en el servidor, porque es una preferencia de
 * lectura, no un dato del despacho.
 *
 * ANATOMÍA (vocabulario del pack Luxury, sin inventar recetas nuevas):
 *   · superficie `Card` del sistema, teñida de teal suave
 *   · icono en bajo relieve (`NeuIcon`), que es el contraste que da profundidad
 *   · título de UNA línea + cuerpo de 1 a 3 líneas · nunca un párrafo largo
 *
 * CÓMO SE USA (queda lista para toda la app, no solo para Conocimiento):
 *
 *   <NotaMia
 *     id="conocimiento-criterios"
 *     icon={BookOpen}
 *     titulo="Aquí guardo cómo piensa tu despacho"
 *   >
 *     Cada vez que trabajamos un asunto anoto el criterio que aplicaste...
 *   </NotaMia>
 *
 * `id` es obligatorio y debe ser estable: es la llave con la que se recuerda
 * que esta nota concreta ya se cerró. Cambiarlo hace reaparecer la nota (eso
 * es lo deseable cuando el texto cambia de fondo).
 *
 * ACCESIBILIDAD: el aspa es un <button> real con nombre accesible propio (dice
 * qué nota cierra, no solo «cerrar»), llega por tabulación y muestra el anillo
 * de foco del sistema. La nota se anuncia como región con su propio título.
 */

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { X } from "lucide-react";
import { Card } from "@/components/ui/card";
import { NeuIcon } from "./PanelUI";
import { cn } from "@/lib/utils";

const PREFIJO = "mia.nota.";

function llave(id: string): string {
  return `${PREFIJO}${id}.cerrada`;
}

export function NotaMia({
  id,
  icon,
  titulo,
  children,
  cerrable = true,
  className,
}: {
  /** Identificador estable de ESTA nota; con él se recuerda que ya se cerró. */
  id: string;
  icon: ComponentType<{ className?: string }>;
  /** Una línea. Si necesita dos, es que son dos notas. */
  titulo: string;
  /** El cuerpo: de una a tres líneas, en la voz de Mia. */
  children: ReactNode;
  cerrable?: boolean;
  className?: string;
}) {
  // `null` = todavía no se sabe (no se ha leído el navegador). No se pinta nada
  // en ese estado: pintarla y esconderla después produce un parpadeo, y pintar
  // en el servidor lo que depende de localStorage rompe la hidratación.
  const [visible, setVisible] = useState<boolean | null>(null);

  useEffect(() => {
    if (!cerrable) {
      setVisible(true);
      return;
    }
    try {
      setVisible(window.localStorage.getItem(llave(id)) !== "1");
    } catch {
      // Navegador sin almacenamiento (modo privado, política del equipo): la
      // nota se muestra igual. Explicar vale más que recordar el cierre.
      setVisible(true);
    }
  }, [id, cerrable]);

  function cerrar() {
    setVisible(false);
    try {
      window.localStorage.setItem(llave(id), "1");
    } catch {
      /* si no se puede recordar, al menos se cierra en esta visita */
    }
  }

  if (visible !== true) return null;

  return (
    <Card
      role="note"
      aria-label={titulo}
      padding="sm"
      className={cn(
        "animate-fade-in border-primary/20 bg-primary/5 backdrop-blur-md",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <NeuIcon icon={icon} tone="primary" size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-pretty text-section">{titulo}</p>
          <div className="mt-1 text-pretty text-body text-muted-foreground">{children}</div>
        </div>
        {cerrable ? (
          <button
            type="button"
            onClick={cerrar}
            aria-label={`Cerrar la nota «${titulo}»`}
            className="-mr-1 -mt-1 shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </Card>
  );
}

export default NotaMia;
