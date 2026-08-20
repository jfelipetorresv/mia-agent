"use client";

// Mia · sección "Valor y gasto" de Configuración — antes vivía en el Panel
// (dashboard). Tarifa horaria del cálculo de valor + tope de gasto mensual de IA,
// con sus formularios completos (en el Panel solo queda el número y una alerta).

import { useEffect, useState } from "react";
import { PiggyBank, TrendingUp } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ValueSummary = {
  hours_saved?: number;
  hourly_rate_usd?: number;
  gross_usd?: number;
  cost_usd?: number;
  net_usd?: number;
  drafts_approved?: number;
  consultations?: number;
  is_default_config?: boolean;
};

type BudgetStatus = {
  monthly_budget_usd: number | null;
  spent_this_month_usd: number;
  remaining_usd: number | null;
  over_budget: boolean;
  unlimited: boolean;
};

export default function ValorGastoSection({
  value,
  onChanged,
}: {
  value?: ValueSummary;
  onChanged: () => void;
}) {
  const [rateInput, setRateInput] = useState("");
  const [rateMsg, setRateMsg] = useState("");
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [budgetInput, setBudgetInput] = useState("");
  const [sinLimite, setSinLimite] = useState(true);
  const [budgetMsg, setBudgetMsg] = useState("");
  const [budgetBusy, setBudgetBusy] = useState(false);

  async function loadBudget() {
    try {
      const data = await apiGet<BudgetStatus>("/api/policy/budget");
      setBudget(data);
      setSinLimite(data.unlimited);
      setBudgetInput(data.unlimited || data.monthly_budget_usd == null ? "" : String(data.monthly_budget_usd));
    } catch {
      setBudget(null);
    }
  }

  useEffect(() => {
    loadBudget();
  }, []);

  async function saveBudget() {
    setBudgetMsg("");
    if (!sinLimite) {
      const amount = Number(budgetInput.replace(",", "."));
      if (!budgetInput.trim() || !Number.isFinite(amount) || amount <= 0) {
        setBudgetMsg("Escribe un tope válido en USD.");
        return;
      }
    }
    setBudgetBusy(true);
    try {
      const res = await apiSend<BudgetStatus>("PUT", "/api/policy/budget", {
        monthly_budget_usd: sinLimite ? null : Number(budgetInput.replace(",", ".")),
      });
      setBudget(res);
      setSinLimite(res.unlimited);
      setBudgetInput(res.unlimited || res.monthly_budget_usd == null ? "" : String(res.monthly_budget_usd));
      setBudgetMsg(sinLimite ? "Sin tope de gasto este mes." : "Tope guardado.");
    } catch (err: unknown) {
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setBudgetMsg(msg || "No se pudo guardar el tope. Intenta de nuevo.");
    } finally {
      setBudgetBusy(false);
    }
  }

  async function saveRate() {
    setRateMsg("");
    const rate = Number(rateInput.replace(",", "."));
    if (!rateInput.trim() || !Number.isFinite(rate) || rate <= 0) {
      setRateMsg("Escribe una tarifa válida en USD por hora.");
      return;
    }
    try {
      await apiSend("PUT", "/api/value/settings", { hourly_rate_usd: rate });
      setRateInput("");
      setRateMsg("Tarifa guardada.");
      onChanged();
    } catch (err: unknown) {
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setRateMsg(msg || "No se pudo guardar la tarifa. Intenta de nuevo.");
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="animate-slide-up rounded-xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-1 flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <TrendingUp className="h-4 w-4 text-success" />
          Valor entregado este mes
        </div>
        {/* NO MEDIBLE (regla operativa §18): sin cifras del servidor, `?? 0` pintaba
            «USD 0,00 de valor neto» y «0 borradores» — un cero inventado que afirma
            que Mia no entregó nada este mes. Un cero REAL sí se pinta como 0; lo que
            no se hace es fabricarlo cuando el dato no llegó. */}
        {value == null ? (
          <>
            <div className="mt-2 text-3xl font-semibold tracking-tight text-muted-foreground">
              Sin medir todavía
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              No pude consultar las cifras de este mes ahora mismo. Vuelve a abrir esta
              pantalla en un momento; lo que hayas hecho está guardado.
            </p>
          </>
        ) : (
          <>
            <div className="mt-2 text-3xl font-semibold tracking-tight">
              USD {Number(value.net_usd ?? 0).toFixed(2)}
              <span className="ml-2 text-sm font-normal text-muted-foreground">de valor neto estimado</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {Number(value.hours_saved ?? 0).toFixed(1)} horas ahorradas (estimado) ×
              USD {Number(value.hourly_rate_usd ?? 0).toFixed(0)}/hora =
              USD {Number(value.gross_usd ?? 0).toFixed(2)}, menos
              USD {Number(value.cost_usd ?? 0).toFixed(2)} de gasto de inteligencia artificial.
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Este mes: {value.drafts_approved ?? 0} escritos que Mia preparó y{" "}
              {value.consultations ?? 0} consultas atendidas — son los turnos que no
              rechazaste, contados por el largo de su texto final; Mia no sabe cuáles
              radicaste.
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Es una estimación: las horas salen de los minutos que configuraste por
              escrito y por consulta
              {value.is_default_config ? " (hoy, los valores de fábrica)" : ""}. El gasto
              de IA no incluye la indexación de documentos, así que se queda corto antes
              que inflarse.
            </p>
          </>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Label htmlFor="hourly-rate" className="text-sm text-muted-foreground">
            Tu tarifa horaria (USD):
          </Label>
          <Input
            id="hourly-rate"
            value={rateInput}
            onChange={(e) => setRateInput(e.target.value)}
            placeholder={String(value?.hourly_rate_usd ?? 100)}
            inputMode="decimal"
            className="h-9 w-24"
          />
          <Button size="sm" onClick={saveRate}>
            Guardar
          </Button>
          {rateMsg ? <span className="text-sm text-muted-foreground">{rateMsg}</span> : null}
        </div>
      </div>

      <div className="animate-slide-up rounded-xl border border-border bg-card p-6 shadow-sm" style={{ animationDelay: "60ms", animationFillMode: "backwards" }}>
        <div className="mb-1 flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <PiggyBank className="h-4 w-4 text-cta" />
          Tope de gasto de IA este mes
        </div>
        {budget === null ? (
          <p className="mt-3 text-sm text-muted-foreground">No se pudo cargar el tope de gasto. Recarga la página.</p>
        ) : (
          <>
            <div className="mt-2 text-3xl font-semibold tracking-tight">
              USD {Number(budget.spent_this_month_usd).toFixed(2)}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {budget.unlimited
                  ? "gastados · sin tope este mes"
                  : `de USD ${Number(budget.monthly_budget_usd ?? 0).toFixed(2)}`}
              </span>
            </div>
            {!budget.unlimited && budget.remaining_usd != null ? (
              <p className="mt-1 text-sm text-muted-foreground">
                Restante: USD {Number(budget.remaining_usd).toFixed(2)}
              </p>
            ) : null}
            {budget.over_budget ? (
              <p role="alert" className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
                Se alcanzó el tope; los turnos están en pausa.
              </p>
            ) : null}
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <Label htmlFor="budget-cap" className="mb-1 block text-sm text-muted-foreground">
                    Tope mensual (USD)
                  </Label>
                  <Input
                    id="budget-cap"
                    value={budgetInput}
                    onChange={(e) => setBudgetInput(e.target.value)}
                    disabled={sinLimite || budgetBusy}
                    placeholder="Ej.: 100"
                    inputMode="decimal"
                    className="h-9 w-28"
                  />
                </div>
                <Button size="sm" onClick={saveBudget} disabled={budgetBusy}>
                  {budgetBusy ? "Guardando…" : "Guardar"}
                </Button>
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={sinLimite}
                  onChange={(e) => setSinLimite(e.target.checked)}
                  disabled={budgetBusy}
                  className="h-4 w-4 rounded border-input accent-[hsl(var(--primary))]"
                />
                Sin límite
              </label>
            </div>
            {budgetMsg ? (
              <p
                role={budgetMsg === "Tope guardado." || budgetMsg === "Sin tope de gasto este mes." ? "status" : "alert"}
                className={`mt-3 text-sm ${
                  budgetMsg === "Tope guardado." || budgetMsg === "Sin tope de gasto este mes."
                    ? "text-muted-foreground"
                    : "text-warning"
                }`}
              >
                {budgetMsg}
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
