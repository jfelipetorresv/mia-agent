"use client";

// Mia · CountrySelector — extraído de onboarding/page.tsx (Bloque C · C2: Perfil del
// despacho editable y unificado). Antes vivía inline en el onboarding (COUNTRY_OPTIONS +
// JurisdictionCheckboxes); ahora es compartido para que "Mi despacho" (memoria/page.tsx)
// edite la jurisdicción con EXACTAMENTE el mismo componente y la misma lista de países —
// cero divergencia entre la entrevista inicial y la edición posterior.
//
// Los 21 países de habla hispana (Colombia primero, resto alfabético) con paquete jurídico
// instalado marcados con la insignia "Conocimiento jurídico profundo"; los demás se pueden
// elegir igual — quedan en el perfil sin prometer nada (mismo criterio que el onboarding).
import { cn } from "@/lib/utils";

export const COUNTRY_OPTIONS: { code: string; name: string }[] = [
  { code: "co", name: "Colombia" },
  { code: "ar", name: "Argentina" },
  { code: "bo", name: "Bolivia" },
  { code: "cl", name: "Chile" },
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

export function CountrySelector({
  packCodes,
  value,
  onChange,
}: {
  packCodes: Set<string>;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  function toggle(code: string, checked: boolean) {
    if (checked) onChange([...value, code]);
    else onChange(value.filter((v) => v !== code));
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {COUNTRY_OPTIONS.map((option) => {
        const checked = value.includes(option.code);
        const hasPack = packCodes.has(option.code);
        return (
          <label
            key={option.code}
            className={cn(
              "flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-sm transition-colors",
              checked ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-primary/25",
            )}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => toggle(option.code, e.target.checked)}
              className="h-4 w-4 shrink-0 rounded border-input accent-[hsl(var(--primary))]"
            />
            <span className="min-w-0">
              <span className="block">{option.name}</span>
              {hasPack ? (
                <span className="mt-0.5 block text-xs text-primary">Conocimiento jurídico profundo</span>
              ) : null}
            </span>
          </label>
        );
      })}
    </div>
  );
}
