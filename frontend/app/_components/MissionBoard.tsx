"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { cn } from "@/lib/utils";

type Milestone = {
  id: string;
  seq: number;
  title: string;
  detail: string;
  actor: "mia" | "abogado";
  status: "queued" | "active" | "done";
  is_procedural: boolean;
};

type Mission = {
  id: string;
  matter_id: string;
  title: string;
  objective: string;
  outcome: string;
  status: "active" | "archived";
  progress: { done: number; total: number };
  milestones: Milestone[];
};

function apiMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : fallback;
}

// `compact`: se usa cuando el tablero vive en un espacio angosto (el aside del
// asunto, junto al Diagnóstico) — apila la lista de misiones y el detalle en
// vertical en vez del layout de dos columnas pensado para el ancho completo.
export default function MissionBoard({ matterId, compact = false }: { matterId: string; compact?: boolean }) {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm, setCreateForm] = useState({ title: "", objective: "", outcome: "" });

  const selected = missions.find((m) => m.id === selectedId) ?? missions[0] ?? null;

  const load = useCallback(async () => {
    setMsg("");
    try {
      const res = await apiGet<{ missions: Mission[] }>(`/api/missions?matter_id=${encodeURIComponent(matterId)}`);
      const list = res.missions || [];
      setMissions(list);
      setSelectedId((prev) => (prev && list.some((m) => m.id === prev) ? prev : list[0]?.id ?? null));
    } catch (err) {
      setMissions([]);
      setMsg(apiMessage(err, "No se pudo cargar el plan. Recarga la página."));
    } finally {
      setLoaded(true);
    }
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  async function createMission() {
    setMsg("");
    if (!createForm.title.trim() || !createForm.objective.trim()) {
      setMsg("El título y el objetivo son obligatorios.");
      return;
    }
    setBusy(true);
    try {
      const mission = await apiSend<Mission>("POST", "/api/missions", {
        matter_id: matterId,
        title: createForm.title.trim(),
        objective: createForm.objective.trim(),
        outcome: createForm.outcome.trim(),
        auto_decompose: true,
      });
      setCreating(false);
      setCreateForm({ title: "", objective: "", outcome: "" });
      setMissions((ms) => [mission, ...ms]);
      setSelectedId(mission.id);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo crear la misión. Intenta de nuevo."));
    } finally {
      setBusy(false);
    }
  }

  async function applyMission(mission: Mission) {
    setMissions((ms) => ms.map((m) => (m.id === mission.id ? mission : m)));
  }

  async function updateMission(patch: Partial<{ title: string; objective: string; outcome: string; status: string }>) {
    if (!selected) return;
    setBusy(true);
    setMsg("");
    try {
      const mission = await apiSend<Mission>("PUT", `/api/missions/${selected.id}`, patch);
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo guardar la misión."));
    } finally {
      setBusy(false);
    }
  }

  async function deleteMission() {
    if (!selected) return;
    if (!window.confirm(`¿Eliminar la misión "${selected.title}" y todos sus hitos?`)) return;
    setBusy(true);
    setMsg("");
    try {
      await apiSend("DELETE", `/api/missions/${selected.id}`);
      setMissions((ms) => ms.filter((m) => m.id !== selected.id));
      setSelectedId(null);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo eliminar la misión."));
    } finally {
      setBusy(false);
    }
  }

  async function decompose(replace: boolean) {
    if (!selected) return;
    if (replace && !window.confirm("¿Sustituir los hitos actuales por una nueva propuesta de Mia?")) return;
    setBusy(true);
    setMsg("");
    try {
      const mission = await apiSend<Mission>("POST", `/api/missions/${selected.id}/decompose`, { replace });
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo proponer hitos."));
    } finally {
      setBusy(false);
    }
  }

  async function updateMilestone(milestoneId: string, patch: Record<string, unknown>) {
    if (!selected) return;
    setBusy(true);
    setMsg("");
    try {
      const mission = await apiSend<Mission>(
        "PUT",
        `/api/missions/${selected.id}/milestones/${milestoneId}`,
        patch,
      );
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo actualizar el hito."));
    } finally {
      setBusy(false);
    }
  }

  async function addMilestone(title: string) {
    if (!selected || !title.trim()) return;
    setBusy(true);
    setMsg("");
    try {
      const mission = await apiSend<Mission>("POST", `/api/missions/${selected.id}/milestones`, {
        title: title.trim(),
        actor: "abogado",
      });
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo añadir el hito."));
    } finally {
      setBusy(false);
    }
  }

  async function removeMilestone(milestoneId: string) {
    if (!selected) return;
    setBusy(true);
    setMsg("");
    try {
      const mission = await apiSend<Mission>(
        "DELETE",
        `/api/missions/${selected.id}/milestones/${milestoneId}`,
      );
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo quitar el hito."));
    } finally {
      setBusy(false);
    }
  }

  async function moveMilestone(m: Milestone, direction: -1 | 1) {
    if (!selected) return;
    const sorted = [...selected.milestones].sort((a, b) => a.seq - b.seq);
    const idx = sorted.findIndex((x) => x.id === m.id);
    const swap = sorted[idx + direction];
    if (!swap) return;
    setBusy(true);
    setMsg("");
    try {
      await apiSend<Mission>("PUT", `/api/missions/${selected.id}/milestones/${m.id}`, { seq: swap.seq });
      const mission = await apiSend<Mission>("PUT", `/api/missions/${selected.id}/milestones/${swap.id}`, {
        seq: m.seq,
      });
      await applyMission(mission);
    } catch (err) {
      setMsg(apiMessage(err, "No se pudo reordenar."));
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) {
    return <p className="mt-10 text-center text-sm text-muted-foreground">Cargando plan…</p>;
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Descompón un objetivo grande en hitos concretos. Tú apruebas, editas y marcas el avance — nada se ejecuta solo.
        </p>
        {!creating ? (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 active:scale-[0.98]"
          >
            Nueva misión
          </button>
        ) : null}
      </div>

      {msg ? (
        <p role="alert" className="mb-3 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{msg}</p>
      ) : null}

      {creating ? (
        <div className="mb-4 rounded-xl border border-border bg-muted p-4">
          <h3 className="mb-3 font-medium">Nueva misión</h3>
          <div className="space-y-3">
            <Field label="Título" value={createForm.title} onChange={(v) => setCreateForm({ ...createForm, title: v })} />
            <Field
              label="Objetivo"
              value={createForm.objective}
              onChange={(v) => setCreateForm({ ...createForm, objective: v })}
              multiline
            />
            <Field
              label="Resultado esperado (opcional)"
              value={createForm.outcome}
              onChange={(v) => setCreateForm({ ...createForm, outcome: v })}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Mia propondrá hitos editables al crear — no se ejecuta nada automáticamente.</p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={createMission}
              disabled={busy}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 active:scale-[0.98] disabled:opacity-50"
            >
              {busy ? "Creando…" : "Crear y proponer hitos"}
            </button>
            <button
              type="button"
              onClick={() => { setCreating(false); setCreateForm({ title: "", objective: "", outcome: "" }); }}
              disabled={busy}
              className="rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-[0.98]"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : null}

      {missions.length === 0 && !creating ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          Aún no hay misiones para este caso. Crea una para desglosar el trabajo en hitos.
        </p>
      ) : null}

      {missions.length > 0 ? (
        <div className={cn("flex min-h-0 flex-1 flex-col gap-4", !compact && "lg:flex-row")}>
          <ul className={cn("flex shrink-0 gap-2 overflow-x-auto", !compact && "lg:w-52 lg:flex-col lg:overflow-visible")}>
            {missions.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(m.id)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition active:scale-[0.98] ${
                    (selected?.id === m.id)
                      ? "border-primary bg-muted font-medium"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  <div className="truncate">{m.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {m.progress.done} de {m.progress.total} hitos
                    {m.status === "archived" ? " · archivada" : ""}
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <MissionDetail
              mission={selected}
              busy={busy}
              onUpdateMission={updateMission}
              onDeleteMission={deleteMission}
              onDecompose={decompose}
              onUpdateMilestone={updateMilestone}
              onAddMilestone={addMilestone}
              onRemoveMilestone={removeMilestone}
              onMoveMilestone={moveMilestone}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function MissionDetail({
  mission,
  busy,
  onUpdateMission,
  onDeleteMission,
  onDecompose,
  onUpdateMilestone,
  onAddMilestone,
  onRemoveMilestone,
  onMoveMilestone,
}: {
  mission: Mission;
  busy: boolean;
  onUpdateMission: (patch: Partial<{ title: string; objective: string; outcome: string; status: string }>) => void;
  onDeleteMission: () => void;
  onDecompose: (replace: boolean) => void;
  onUpdateMilestone: (id: string, patch: Record<string, unknown>) => void;
  onAddMilestone: (title: string) => void;
  onRemoveMilestone: (id: string) => void;
  onMoveMilestone: (m: Milestone, direction: -1 | 1) => void;
}) {
  const [editTitle, setEditTitle] = useState(mission.title);
  const [editObjective, setEditObjective] = useState(mission.objective);
  const [editOutcome, setEditOutcome] = useState(mission.outcome || "");
  const [newMilestone, setNewMilestone] = useState("");
  const sorted = [...mission.milestones].sort((a, b) => a.seq - b.seq);
  const pct = mission.progress.total ? Math.round((mission.progress.done / mission.progress.total) * 100) : 0;

  useEffect(() => {
    setEditTitle(mission.title);
    setEditObjective(mission.objective);
    setEditOutcome(mission.outcome || "");
  }, [mission.id, mission.title, mission.objective, mission.outcome]);

  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border p-4">
      <div className="mb-4 space-y-2">
        <input
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={() => {
            if (editTitle.trim() && editTitle !== mission.title) onUpdateMission({ title: editTitle.trim() });
          }}
          className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm font-medium outline-none focus:border-primary"
        />
        <textarea
          value={editObjective}
          onChange={(e) => setEditObjective(e.target.value)}
          onBlur={() => {
            if (editObjective.trim() && editObjective !== mission.objective) {
              onUpdateMission({ objective: editObjective.trim() });
            }
          }}
          rows={2}
          className="w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary"
        />
        {editOutcome || mission.outcome ? (
          <input
            value={editOutcome}
            onChange={(e) => setEditOutcome(e.target.value)}
            onBlur={() => onUpdateMission({ outcome: editOutcome.trim() })}
            placeholder="Resultado esperado (opcional)"
            className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          />
        ) : null}
      </div>

      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
          <span>{mission.progress.done} de {mission.progress.total} hitos</span>
          <span>{pct}%</span>
        </div>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label="Avance de la misión"
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onDecompose(false)}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1 text-xs font-medium transition hover:bg-muted active:scale-[0.98] disabled:opacity-50"
        >
          Proponer más hitos
        </button>
        <button
          type="button"
          onClick={() => onDecompose(true)}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1 text-xs font-medium transition hover:bg-muted active:scale-[0.98] disabled:opacity-50"
        >
          Rehacer propuesta
        </button>
        {mission.status === "active" ? (
          <button
            type="button"
            onClick={() => onUpdateMission({ status: "archived" })}
            disabled={busy}
            className="rounded-lg px-3 py-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-[0.98] disabled:opacity-50"
          >
            Archivar
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onUpdateMission({ status: "active" })}
            disabled={busy}
            className="rounded-lg px-3 py-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-[0.98] disabled:opacity-50"
          >
            Reactivar
          </button>
        )}
        <button
          type="button"
          onClick={onDeleteMission}
          disabled={busy}
          className="rounded-lg px-3 py-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-destructive active:scale-[0.98] disabled:opacity-50"
        >
          Eliminar misión
        </button>
      </div>

      <ul className="space-y-2">
        {sorted.map((m, idx) => (
          <li key={m.id} className="rounded-lg border border-border px-3 py-3">
            <div className="flex flex-wrap items-start gap-2">
              <div className="flex shrink-0 flex-col gap-0.5">
                <button
                  type="button"
                  aria-label="Subir hito"
                  disabled={busy || idx === 0}
                  onClick={() => onMoveMilestone(m, -1)}
                  className="rounded px-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-[0.98] disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label="Bajar hito"
                  disabled={busy || idx === sorted.length - 1}
                  onClick={() => onMoveMilestone(m, 1)}
                  className="rounded px-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-[0.98] disabled:opacity-30"
                >
                  ↓
                </button>
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <input
                  defaultValue={m.title}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v && v !== m.title) onUpdateMilestone(m.id, { title: v });
                  }}
                  className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-medium outline-none focus:border-primary"
                />
                {m.detail ? (
                  <p className="text-xs text-muted-foreground">{m.detail}</p>
                ) : null}
                {m.is_procedural ? (
                  <p className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-xs text-warning">
                    Toca un plazo — confírmalo tú [VERIFICAR]
                  </p>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={m.actor}
                    onChange={(e) => onUpdateMilestone(m.id, { actor: e.target.value })}
                    disabled={busy}
                    className="rounded border border-input bg-card px-2 py-1 text-xs outline-none"
                  >
                    <option value="mia">Mia lo prepara</option>
                    <option value="abogado">Lo haces tú</option>
                  </select>
                  <select
                    value={m.status}
                    onChange={(e) => onUpdateMilestone(m.id, { status: e.target.value })}
                    disabled={busy}
                    className="rounded border border-input bg-card px-2 py-1 text-xs outline-none"
                    aria-label="Estado del hito"
                  >
                    <option value="queued">Pendiente</option>
                    <option value="active">En curso</option>
                    <option value="done">Hecho</option>
                  </select>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onRemoveMilestone(m.id)}
                disabled={busy}
                className="shrink-0 rounded px-2 py-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-destructive active:scale-[0.98] disabled:opacity-50"
              >
                Quitar
              </button>
            </div>
          </li>
        ))}
      </ul>

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (newMilestone.trim()) {
            onAddMilestone(newMilestone);
            setNewMilestone("");
          }
        }}
      >
        <input
          value={newMilestone}
          onChange={(e) => setNewMilestone(e.target.value)}
          placeholder="Añadir hito manual…"
          className="flex-1 rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <button
          type="submit"
          disabled={busy || !newMilestone.trim()}
          className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 active:scale-[0.98] disabled:opacity-50"
        >
          Añadir
        </button>
      </form>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">{label}</label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary"
        />
      )}
    </div>
  );
}
