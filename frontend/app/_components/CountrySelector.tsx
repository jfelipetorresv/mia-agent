"use client";

// Mia · CountrySelector — extraído de onboarding/page.tsx (Bloque C · C2: Perfil del
// despacho editable y unificado). Antes vivía inline en el onboarding (COUNTRY_OPTIONS +
// JurisdictionCheckboxes); ahora es compartido para que "Mi despacho" (memoria/page.tsx)
// edite la jurisdicción con EXACTAMENTE el mismo componente y la misma lista de países —
// cero divergencia entre la entrevista inicial y la edición posterior.
//
// Los 21 países de habla hispana en orden alfabético. El abogado elige su jurisdicción;
// MIA es agnóstica y no destaca ningún país ni promete conocimiento profundo de ninguno.
//
// ── 2026-07-20 · LA LISTA YA NO PROMETE SOLA ─────────────────────────────────────────
// Defecto corregido: las 21 casillas se veían todas iguales, así que un despacho chileno
// marcaba "Chile" y salía creyendo que Mia traía el derecho chileno adentro. No traía
// nada — caía al modo general sin que nadie se lo dijera. La lista de 21 NO es un catálogo
// de capacidades: es una comodidad para no escribir el país a mano. Ahora el componente
// PREGUNTA al servidor (`GET /api/jurisdictions`, que deriva la verdad de los paquetes
// realmente instalados) y marca solo los países para los que Mia sí viene preparada.
//
// QUÉ SE PUEDE PROMETER — verificado leyendo el paquete `co`, el único instalado hoy:
//   SÍ  · corpus_sources.json  → cuáles son las fuentes oficiales de ese país
//   SÍ  · citation_style.json  → cómo se citan allí las normas y las sentencias
//   SÍ  · doc_markers.json     → cómo se parten sus documentos al leerlos
//   NO  · holidays.json        → PROVISIONAL (`_complete: false`, faltan los festivos
//         trasladables y los de base pascual) y el resolutor de plazos ni siquiera está
//         cableado a él. PROHIBIDO decirle al abogado que Mia ya sabe sus festivos
//         judiciales o que le calcula plazos: hoy sería mentira con consecuencia procesal.
//   NO  · term_catalog.json    → PROVISIONAL, dos entradas. Mismo veto.
//   NO  · recess.json          → vacío.
//   NO  · id_formats/pii_hints → el anonimizador aplica TODOS los paquetes SIEMPRE, sin
//         mirar el país del despacho (decisión: secreto profesional > precisión). No es
//         un beneficio de elegir un país, así que no se anuncia como tal.
// Si alguien completa y verifica festivos o términos, ESE es el momento de ampliar el
// texto de abajo — no antes.
import { useEffect, useMemo, useState } from "react";
import { apiGetSoft } from "@/lib/api";
import { cn } from "@/lib/utils";

export const COUNTRY_OPTIONS: { code: string; name: string }[] = [
  { code: "ar", name: "Argentina" },
  { code: "bo", name: "Bolivia" },
  { code: "cl", name: "Chile" },
  { code: "co", name: "Colombia" },
  { code: "cr", name: "Costa Rica" },
  { code: "cu", name: "Cuba" },
  { code: "ec", name: "Ecuador" },
  { code: "sv", name: "El Salvador" },
  { code: "es", name: "España" },
  { code: "gt", name: "Guatemala" },
  { code: "gq", name: "Guinea Ecuatorial" },
  { code: "hn", name: "Honduras" },
  { code: "mx", name: "México" },
  { code: "ni", name: "Nicaragua" },
  { code: "pa", name: "Panamá" },
  { code: "py", name: "Paraguay" },
  { code: "pe", name: "Perú" },
  { code: "pr", name: "Puerto Rico" },
  { code: "do", name: "República Dominicana" },
  { code: "uy", name: "Uruguay" },
  { code: "ve", name: "Venezuela" },
];

export const COUNTRY_NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  COUNTRY_OPTIONS.map((c) => [c.code, c.name]),
);

// "generic" no es un país: es el modo general con el que ya trabaja el resolutor cuando no
// hay material de una jurisdicción. Se descarta al leer la respuesta del servidor para que
// nunca se pinte como si fuera una casilla más.
const GENERIC_CODE = "generic";

// El aviso que llevan las casillas de los países para los que Mia sí viene preparada.
// Se exporta para que el gate pueda comprobar el texto exacto que ve el abogado.
export const PREPARED_BADGE = "Ya vengo preparada";
// Qué significa esa insignia, en una frase y sin jerga. Es el techo de lo prometible:
// saber DÓNDE buscar y CÓMO se cita — no "conocer el derecho" de ese país.
const PREPARED_MEANING =
  "sé cuáles son sus fuentes oficiales y cómo se citan allí las normas y las sentencias";

type JurisdictionOption = { code?: unknown; name?: unknown; verified?: unknown };

// Tres estados, a propósito. "unknown" NO es lo mismo que "ninguno": si la consulta falla,
// Mia se calla en vez de afirmar que no viene preparada para ningún país (§ ningún dato
// sin fuente). Y en ningún caso se bloquea la selección — el alta sigue igual.
type Availability =
  | { status: "loading" }
  | { status: "ready"; prepared: Set<string> }
  | { status: "unknown" };

/** Países con material propio, según el servidor. Nunca lanza y nunca bloquea: ante
 *  cualquier fallo devuelve "unknown" y el selector sigue funcionando entero. */
function usePreparedCountries(): Availability {
  const [availability, setAvailability] = useState<Availability>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    // apiGetSoft nunca lanza: devuelve el respaldo (null) ante cualquier fallo. El
    // respaldo es null y NO [] a propósito — un [] se leería como "no hay ningún país
    // preparado", que es una afirmación falsa nacida de una petición que no respondió.
    apiGetSoft<{ jurisdictions?: JurisdictionOption[] } | null>("/api/jurisdictions", null)
      .then((res) => {
        if (!alive) return;
        const list = res && Array.isArray(res.jurisdictions) ? res.jurisdictions : null;
        if (!list) {
          setAvailability({ status: "unknown" });
          return;
        }
        const prepared = new Set(
          list
            .map((o) => String(o?.code ?? "").trim().toLowerCase())
            .filter((code) => code && code !== GENERIC_CODE),
        );
        setAvailability({ status: "ready", prepared });
      })
      .catch(() => {
        if (alive) setAvailability({ status: "unknown" });
      });
    return () => {
      alive = false;
    };
  }, []);

  return availability;
}

/** "Chile", "Chile y Perú", "Chile, Perú y México" — enumeración en español llano. */
function enumerar(nombres: string[]): string {
  if (nombres.length <= 1) return nombres[0] ?? "";
  return `${nombres.slice(0, -1).join(", ")} y ${nombres[nombres.length - 1]}`;
}

export function CountrySelector({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const availability = usePreparedCountries();
  const prepared = availability.status === "ready" ? availability.prepared : null;

  function toggle(code: string, checked: boolean) {
    if (checked) onChange([...value, code]);
    else onChange(value.filter((v) => v !== code));
  }

  // Lo que el abogado va a obtener CON LO QUE ACABA DE MARCAR. Es la pieza que hace que
  // salga de la pantalla sabiendo qué recibe: la insignia sola sería una promesa vaga.
  function explicacion(): string | null {
    if (availability.status === "loading") return null;
    if (availability.status === "unknown") {
      return "Ahora mismo no puedo comprobar de qué países traigo material cargado. " +
        "Puedes elegir igual y seguimos.";
    }
    const conMaterial = value.filter((c) => availability.prepared.has(c));
    const sinMaterial = value.filter((c) => !availability.prepared.has(c));
    if (conMaterial.length === 0 && sinMaterial.length === 0) {
      // Nada marcado todavía: se explica qué significa la insignia antes de que elija.
      if (availability.prepared.size === 0) return null;
      return `Los países marcados son aquellos para los que ya vengo preparada: ${PREPARED_MEANING}. ` +
        "En los demás trabajo igual, con lo que tú me des.";
    }
    const frases: string[] = [];
    if (conMaterial.length > 0) {
      const nombres = enumerar(conMaterial.map((c) => COUNTRY_NAME_BY_CODE[c] ?? c));
      frases.push(`De ${nombres} ya vengo preparada: ${PREPARED_MEANING}.`);
    }
    if (sinMaterial.length > 0) {
      const nombres = enumerar(sinMaterial.map((c) => COUNTRY_NAME_BY_CODE[c] ?? c));
      frases.push(
        `De ${nombres} no traigo nada cargado de fábrica: trabajaré con las normas, ` +
          "sentencias y documentos que tú me des.",
      );
    }
    return frases.join(" ");
  }

  const mensaje = explicacion();

  // Filtro de escritura. Se ve MIRANDO la pantalla: veintiún países en filas con casilla
  // convertían la única pregunta de contexto en una lista con scroll, y el wizard —que es
  // una pregunta a la vez— perdía su ritmo justo aquí. En fichas caben de un vistazo, y
  // quien ya sabe su país lo escribe y lo tiene delante en dos teclas.
  const [filtro, setFiltro] = useState("");
  const normalizar = (s: string) =>
    s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const visibles = useMemo(() => {
    const q = normalizar(filtro.trim());
    const lista = q
      ? COUNTRY_OPTIONS.filter((o) => normalizar(o.name).includes(q))
      : COUNTRY_OPTIONS;
    // Los que ya están marcados primero: lo elegido no puede desaparecer al filtrar.
    return [...lista].sort((a, b) => {
      const ma = value.includes(a.code) ? 0 : 1;
      const mb = value.includes(b.code) ? 0 : 1;
      return ma - mb;
    });
  }, [filtro, value]);

  return (
    <div className="space-y-3">
      <input
        type="search"
        value={filtro}
        onChange={(e) => setFiltro(e.target.value)}
        placeholder="Escribe para encontrar tu país"
        aria-label="Buscar país"
        className="h-10 w-full rounded-xl border border-input bg-card px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/40"
      />
      <div className="flex flex-wrap gap-2">
        {visibles.map((option) => {
          const checked = value.includes(option.code);
          // La insignia solo se pinta cuando el servidor CONFIRMÓ que hay material. La
          // ausencia de insignia nunca se convierte en un sello de "no tengo nada": los
          // 20 países restantes no llevan marca negativa (esto no es una disculpa).
          const listo = prepared?.has(option.code) ?? false;
          return (
            <label
              key={option.code}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-full border px-3.5 py-2 text-sm transition-colors",
                checked
                  ? "border-primary/50 bg-primary/10 text-foreground"
                  : "border-border bg-card text-muted-foreground hover:border-primary/30 hover:text-foreground",
              )}
            >
              {/* La casilla sigue existiendo (teclado y lectores de pantalla la usan); lo
                  que cambia es que la ficha entera es la superficie visible. */}
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => toggle(option.code, e.target.checked)}
                className="sr-only"
              />
              <span
                aria-hidden
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px]",
                  checked ? "border-primary bg-primary text-primary-foreground" : "border-input",
                )}
              >
                {checked ? "✓" : ""}
              </span>
              <span>{option.name}</span>
              {listo ? (
                <span
                  title={`Ya vengo preparada: ${PREPARED_MEANING}.`}
                  className="shrink-0 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium leading-tight text-primary"
                >
                  {PREPARED_BADGE}
                </span>
              ) : null}
            </label>
          );
        })}
        {visibles.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Ninguno de la lista se llama así. Escríbelo abajo y seguimos igual.
          </p>
        ) : null}
      </div>
      {mensaje ? (
        <p aria-live="polite" className="text-xs leading-relaxed text-muted-foreground">
          {mensaje}
        </p>
      ) : null}
    </div>
  );
}
