"use client";

// Formato del texto que escribe Mia. El motor responde en Markdown; sin esto el
// abogado ve asteriscos y almohadillas en pantalla. Parser propio por líneas:
// cero dependencias nuevas y cero dangerouslySetInnerHTML — al emitir JSX no hay
// forma de inyectar HTML, así que el riesgo de contenido malicioso queda
// descartado por construcción.
//
// Regla de streaming (SSE): el texto llega a medias. Un delimitador ABIERTO
// (un "**" cuya pareja todavía no ha llegado) se pinta como texto normal y solo
// se convierte en formato cuando llega su cierre. Nunca rompe ni parpadea.

import { cloneElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";

// El resaltado de [VERIFICAR…] vive AQUÍ y en ningún otro lado: es la señal de
// "esto lo confirmas tú" del gate de citas y tiene que verse idéntica en el
// borrador, en la sala de estrategia y en la conversación.
const VERIFICAR_CLASS = "rounded bg-warning/20 px-1 font-sans text-sm font-medium text-warning";
const VERIFICAR_RE = /^\[VERIFICAR[^\]]*\]/;

/**
 * Resuelve el formato dentro de una línea: **negrita**, *cursiva*, `código` y
 * la marca [VERIFICAR…]. Es la única función de formato en línea del producto.
 */
export function renderInline(text: string, keyBase = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  let buffer = "";
  let key = 0;
  let i = 0;

  function flush() {
    if (buffer) {
      out.push(buffer);
      buffer = "";
    }
  }

  while (i < text.length) {
    const ch = text[i];

    // [VERIFICAR…] — sin corchete de cierre todavía, es texto normal.
    if (ch === "[") {
      const marca = VERIFICAR_RE.exec(text.slice(i));
      if (marca) {
        flush();
        out.push(
          <mark key={`${keyBase}-v${key++}`} title="Verificar antes de presentar" className={VERIFICAR_CLASS}>
            {marca[0]}
          </mark>,
        );
        i += marca[0].length;
        continue;
      }
    }

    if (ch === "*" && text[i + 1] === "*") {
      const close = text.indexOf("**", i + 2);
      if (close > i + 2) {
        flush();
        out.push(
          <strong key={`${keyBase}-b${key}`} className="font-semibold text-foreground">
            {renderInline(text.slice(i + 2, close), `${keyBase}-b${key}`)}
          </strong>,
        );
        key++;
        i = close + 2;
        continue;
      }
      buffer += "**";
      i += 2;
      continue;
    }

    if (ch === "*") {
      const close = text.indexOf("*", i + 1);
      if (close > i + 1) {
        flush();
        out.push(
          <em key={`${keyBase}-e${key}`}>{renderInline(text.slice(i + 1, close), `${keyBase}-e${key}`)}</em>,
        );
        key++;
        i = close + 1;
        continue;
      }
      buffer += "*";
      i += 1;
      continue;
    }

    if (ch === "`") {
      const close = text.indexOf("`", i + 1);
      if (close > i + 1) {
        flush();
        out.push(
          <code key={`${keyBase}-c${key++}`} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
            {text.slice(i + 1, close)}
          </code>,
        );
        i = close + 1;
        continue;
      }
      buffer += "`";
      i += 1;
      continue;
    }

    buffer += ch;
    i += 1;
  }

  flush();
  return out;
}

const HEADING_CLASS: Record<number, string> = {
  1: "font-sans text-lg font-semibold tracking-tight text-foreground",
  2: "font-sans text-base font-semibold tracking-tight text-foreground",
  3: "font-sans text-sm font-semibold tracking-tight text-foreground",
};

const HEADING_RE = /^(#{1,3})\s+(.*)$/;
const BULLET_RE = /^(\s*)[-*]\s+(.+)$/;
const NUMBERED_RE = /^(\s*)(\d+)[.)]\s+(.+)$/;
const QUOTE_RE = /^>\s?(.*)$/;
const RULE_RE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;

type ListKind = "bullet" | "number";

export default function MiaMarkdown({
  text,
  className,
  trailing,
}: {
  text: string;
  className?: string;
  /** Cursor de escritura durante el streaming; se pega al último párrafo. */
  trailing?: ReactNode;
}) {
  const blocks: ReactNode[] = [];
  let key = 0;

  let listItems: ReactNode[] = [];
  let listKind: ListKind | null = null;
  let listStart = 1;
  let quoteLines: string[] = [];
  let paraLines: string[] = [];
  // Índice del último párrafo emitido: ahí va el cursor de escritura.
  let lastParaIndex = -1;

  function flushList() {
    if (listItems.length === 0) return;
    const items = listItems;
    listItems = [];
    if (listKind === "number") {
      blocks.push(
        <ol key={`ol-${key++}`} start={listStart} className="list-decimal space-y-1 pl-5">
          {items}
        </ol>,
      );
    } else {
      blocks.push(
        <ul key={`ul-${key++}`} className="list-disc space-y-1 pl-5">
          {items}
        </ul>,
      );
    }
    listKind = null;
  }

  function flushQuote() {
    if (quoteLines.length === 0) return;
    const lines = quoteLines;
    quoteLines = [];
    blocks.push(
      <blockquote
        key={`q-${key++}`}
        className="border-l-2 border-primary/40 pl-3 italic text-muted-foreground"
      >
        {lines.map((line, n) => (
          <span key={n} className="block">
            {renderInline(line, `q${key}-${n}`)}
          </span>
        ))}
      </blockquote>,
    );
  }

  function flushParagraph() {
    if (paraLines.length === 0) return;
    const lines = paraLines;
    paraLines = [];
    lastParaIndex = blocks.length;
    blocks.push(
      <p key={`p-${key++}`}>
        {lines.map((line, n) => (
          <span key={n}>
            {n > 0 ? <br /> : null}
            {renderInline(line, `p${key}-${n}`)}
          </span>
        ))}
      </p>,
    );
  }

  function flushAll() {
    flushParagraph();
    flushList();
    flushQuote();
  }

  // Tolerante: si el texto llega vacío o con basura, se pinta lo que haya y no
  // se rompe la pantalla.
  const source = typeof text === "string" ? text : "";

  for (const raw of source.split("\n")) {
    const line = raw.replace(/\s+$/, "");

    if (line.trim() === "") {
      flushAll();
      continue;
    }

    if (RULE_RE.test(line)) {
      flushAll();
      blocks.push(<hr key={`hr-${key++}`} className="border-border" />);
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const Tag = (level === 1 ? "h2" : level === 2 ? "h3" : "h4") as "h2" | "h3" | "h4";
      blocks.push(
        <Tag key={`h-${key++}`} className={HEADING_CLASS[level]}>
          {renderInline(heading[2], `h${key}`)}
        </Tag>,
      );
      continue;
    }

    const quote = QUOTE_RE.exec(line);
    if (quote) {
      flushParagraph();
      flushList();
      quoteLines.push(quote[1]);
      continue;
    }

    const numbered = NUMBERED_RE.exec(line);
    if (numbered) {
      flushParagraph();
      flushQuote();
      if (listKind !== "number") {
        flushList();
        listKind = "number";
        listStart = Number(numbered[2]) || 1;
      }
      listItems.push(
        <li key={`li-${key}-${listItems.length}`} className={numbered[1].length >= 2 ? "ml-4" : undefined}>
          {renderInline(numbered[3], `li${key}-${listItems.length}`)}
        </li>,
      );
      continue;
    }

    const bullet = BULLET_RE.exec(line);
    if (bullet) {
      flushParagraph();
      flushQuote();
      if (listKind !== "bullet") {
        flushList();
        listKind = "bullet";
      }
      listItems.push(
        <li key={`li-${key}-${listItems.length}`} className={bullet[1].length >= 2 ? "ml-4" : undefined}>
          {renderInline(bullet[2], `li${key}-${listItems.length}`)}
        </li>,
      );
      continue;
    }

    flushList();
    flushQuote();
    paraLines.push(line);
  }

  flushAll();

  // El cursor de escritura se pega al último párrafo para que no salte de línea.
  if (trailing) {
    const last = lastParaIndex >= 0 && lastParaIndex === blocks.length - 1 ? blocks[lastParaIndex] : null;
    if (isValidElement(last)) {
      const para = last as ReactElement<{ children?: ReactNode }>;
      blocks[lastParaIndex] = cloneElement(para, undefined, para.props.children, trailing);
    } else {
      blocks.push(<span key="trailing">{trailing}</span>);
    }
  }

  return <div className={className ?? "space-y-3"}>{blocks}</div>;
}
