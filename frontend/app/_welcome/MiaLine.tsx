"use client";

import * as React from "react";
import { useReducedMotion } from "./motion";
import { cn } from "@/lib/utils";

export interface MiaLineProps {
  /** Texto que Mia "escribe". */
  text: string;
  /** Milisegundos por carácter. Default 28. */
  speed?: number;
  /** Retraso antes de empezar a escribir (ms). Default 200. */
  startDelay?: number;
  /** Se llama cuando termina de escribir. */
  onDone?: () => void;
  className?: string;
}

/**
 * Texto de bienvenida "en voz de Mia" con efecto máquina de escribir + cursor
 * teal parpadeante (reusa el keyframe `blink` existente vía `animate-blink`).
 * Coherente con el motion-language del chat. Con prefers-reduced-motion muestra
 * el texto completo de inmediato (sin cursor animado).
 */
export default function MiaLine({ text, speed = 28, startDelay = 200, onDone, className }: MiaLineProps) {
  const reduce = useReducedMotion();
  const [count, setCount] = React.useState(reduce ? text.length : 0);
  const doneRef = React.useRef(false);

  React.useEffect(() => {
    if (reduce) {
      onDone?.();
      return;
    }
    doneRef.current = false;
    setCount(0);
    let i = 0;
    let interval: ReturnType<typeof setInterval>;
    const start = setTimeout(() => {
      interval = setInterval(() => {
        i += 1;
        setCount(i);
        if (i >= text.length) {
          clearInterval(interval);
          if (!doneRef.current) {
            doneRef.current = true;
            onDone?.();
          }
        }
      }, speed);
    }, startDelay);

    return () => {
      clearTimeout(start);
      clearInterval(interval);
    };
    // onDone intencionalmente fuera de deps para no reiniciar el tecleo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, speed, startDelay, reduce]);

  const done = count >= text.length;

  // Reserva de altura: se apilan (grid, misma celda) el texto COMPLETO invisible y
  // el texto que se va escribiendo. Así el bloque ocupa desde el inicio la altura
  // final —incluidos enunciados que envuelven a 2+ líneas— y el input enfocado no
  // salta cuando el efecto máquina de escribir crece carácter a carácter.
  return (
    <p className={cn("grid font-display text-foreground", className)} aria-label={text}>
      <span aria-hidden className="invisible col-start-1 row-start-1">
        {text}
      </span>
      <span aria-hidden className="col-start-1 row-start-1">
        {text.slice(0, count)}
        {!reduce && !done && (
          <span className="ml-0.5 inline-block animate-blink text-primary">|</span>
        )}
      </span>
    </p>
  );
}
