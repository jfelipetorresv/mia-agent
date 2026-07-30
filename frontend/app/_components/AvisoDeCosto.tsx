"use client";

import { Wallet, X } from "lucide-react";

/**
 * Aviso de costo: la suscripción no alcanzó y el turno se resolvió con crédito de pago.
 *
 * Por qué existe: MIA se vende corriendo sobre la suscripción que el abogado YA paga, y la
 * cadena de respaldo puede acudir a crédito cuando esa suscripción se queda corta. Eso es
 * deliberado; lo que no puede pasar es que ocurra en silencio. En el piloto con un expediente
 * real la suscripción expiró tres veces, el turno se resolvió con tarjeta y nada en pantalla
 * lo mencionó. Un cargo que el abogado no esperaba es un cargo que no autorizó.
 *
 * El texto lo arma el backend (`aviso_cambio_de_motor`): aquí no se redacta nada, solo se
 * muestra. Así hay UNA sola redacción que auditar (§G: sin jerga, sin nombres de motor).
 */
export type AvisoDeCostoData = {
  message: string;
  sugerencia?: string;
  veces?: number;
};

// Cuando el aviso llega en una pantalla que va a navegar enseguida (la revisión del
// borrador vuelve al asunto), se deja en depósito para que la pantalla de destino lo
// pinte. Sin esto, el único turno que se paga con crédito al aprobar se avisaría en una
// pantalla que desaparece a los 900 ms.
const DEPOSITO = "mia:aviso_de_costo";

export function depositarAvisoDeCosto(aviso: AvisoDeCostoData): void {
  try {
    window.sessionStorage.setItem(DEPOSITO, JSON.stringify(aviso));
  } catch {
    // Sin sessionStorage el aviso se pierde; nunca puede tumbar la pantalla.
  }
}

export function recogerAvisoDeCosto(): AvisoDeCostoData | null {
  try {
    const raw = window.sessionStorage.getItem(DEPOSITO);
    if (!raw) return null;
    window.sessionStorage.removeItem(DEPOSITO);
    const aviso = JSON.parse(raw) as AvisoDeCostoData;
    return aviso && aviso.message ? aviso : null;
  } catch {
    return null;
  }
}

export default function AvisoDeCosto({
  aviso,
  onDismiss,
}: {
  aviso: AvisoDeCostoData | null;
  onDismiss: () => void;
}) {
  if (!aviso) return null;
  return (
    <div
      role="status"
      className="mb-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-foreground"
    >
      <div className="flex items-start gap-3">
        <Wallet className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="flex-1 space-y-1">
          <p>{aviso.message}</p>
          {aviso.sugerencia ? (
            <p className="text-muted-foreground">{aviso.sugerencia}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Cerrar aviso"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-warning/20 hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
