"use client";

// Mia · sección "Conexiones" de Configuración — antes vivía en el Panel (dashboard).
// Agrupa lo que Mia puede usar para ayudar: espacio de notas (Obsidian), dictado por
// voz, calendario y correo, motor de IA y memoria ampliada (avanzado).

import { useEffect, useState } from "react";
import { BookOpen, Layers, Mail, Mic, NotebookPen, Settings2 } from "lucide-react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConnectorCard, fmt } from "@/app/_components/PanelUI";
import ConnectedSystemsSection from "@/app/_components/ConnectedSystemsSection";
import MailboxSectionLoader from "@/app/_components/MailboxSectionLoader";
import FolderPicker from "@/app/_components/FolderPicker";

type MotorPolicy = {
  politica: string;
  nombre: string;
  opciones: { id: string; nombre: string }[];
  // CP-NLM: estado de la consulta a NotebookLM (presente desde el backend actual).
  allow_notebooklm?: boolean;
  notebooklm_notebook?: string;
  notebooklm_disponible?: boolean;
};

type ObsidianStatus = { installed: boolean; vault_configured: boolean; vault_path?: string | null; message: string };

// CP-NLM · estado de instalación/conexión del CLI de NotebookLM
type NbStatus = {
  estado: "no_instalado" | "instalando" | "instalado_sin_conectar" | "conectando" | "conectado" | "error";
  instalado: boolean;
  autenticado: boolean;
  listo: boolean;
  mensaje: string;
  progreso: { fase: string; porcentaje: number | null } | null;
};

type SpeechProgress = {
  fase: string;
  descargado_mb: number;
  total_mb: number | null;
  porcentaje: number | null;
};
type SpeechStatus = {
  estado: "instalado" | "no_instalado" | "descargando" | "error";
  listo: boolean;
  mensaje: string;
  progreso: SpeechProgress | null;
};

type Connectors = {
  knowledge_base?: { active?: boolean; last_sync?: string | null; chunks?: number };
  external_store?: { active?: boolean; vectors_count?: number };
};

export default function ConexionesSection({
  connectors,
  onChanged,
}: {
  connectors: Connectors;
  onChanged: () => void;
}) {
  const c = connectors || {};
  const [vaultPath, setVaultPath] = useState("");
  const [pineconeKey, setPineconeKey] = useState("");
  const [pineconeIndex, setPineconeIndex] = useState("");
  const [status, setStatus] = useState("");
  const [policy, setPolicy] = useState<MotorPolicy | null>(null);
  const [policyMsg, setPolicyMsg] = useState("");
  const [obsidian, setObsidian] = useState<ObsidianStatus | null>(null);
  const [vaultPickerOpen, setVaultPickerOpen] = useState(false);
  const [installConfirm, setInstallConfirm] = useState(false);
  const [installBusy, setInstallBusy] = useState(false);
  const [speech, setSpeech] = useState<SpeechStatus | null>(null);
  const [speechConfirm, setSpeechConfirm] = useState(false);
  const [speechBusy, setSpeechBusy] = useState(false);
  const [speechMsg, setSpeechMsg] = useState("");
  // CP-NLM · consulta a NotebookLM
  const [nbNotebook, setNbNotebook] = useState("");
  const [nbBusy, setNbBusy] = useState(false);
  const [nbMsg, setNbMsg] = useState("");
  const [nbStatus, setNbStatus] = useState<NbStatus | null>(null);
  const [nbList, setNbList] = useState<{ id: string; titulo: string }[]>([]);
  const [nbInstallConfirm, setNbInstallConfirm] = useState(false);

  useEffect(() => {
    apiGet<MotorPolicy>("/settings/model-policy")
      .then((p) => {
        setPolicy(p);
        setNbNotebook(p.notebooklm_notebook || "");
      })
      .catch(() => setPolicyMsg("No se pudo cargar el motor de IA. Recarga la página."));
    apiGet<ObsidianStatus>("/api/obsidian/status").then(setObsidian).catch(() => setObsidian(null));
    apiGet<SpeechStatus>("/api/speech/status").then(setSpeech).catch(() => setSpeech(null));
    refreshNbStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // CP-NLM: mientras NotebookLM instala o conecta, refresca solo cada 2.5 s.
  useEffect(() => {
    if (nbStatus?.estado !== "instalando" && nbStatus?.estado !== "conectando") return;
    const t = setInterval(refreshNbStatus, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nbStatus?.estado]);

  // Mientras el componente de voz descarga, la tarjeta se refresca sola cada 2 s
  // (SOLO durante la descarga; el intervalo se limpia al terminar).
  useEffect(() => {
    if (speech?.estado !== "descargando") return;
    let enVuelo = false;
    const t = setInterval(() => {
      if (enVuelo) return;
      enVuelo = true;
      apiGet<SpeechStatus>("/api/speech/status")
        .then((st) => {
          setSpeech(st);
          if (st.estado !== "descargando") setSpeechMsg("");
        })
        .catch(() => {})
        .finally(() => {
          enVuelo = false;
        });
    }, 2000);
    return () => clearInterval(t);
  }, [speech?.estado]);

  async function changePolicy(id: string) {
    setPolicyMsg("");
    try {
      const res = await apiSend<MotorPolicy>("PUT", "/settings/model-policy", { politica: id });
      setPolicy(res);
      setPolicyMsg(`Listo: Mia trabajará con "${res.nombre}".`);
    } catch {
      setPolicyMsg("No se pudo cambiar el motor. Intenta de nuevo.");
    }
  }

  // CP-NLM: refresca el estado de instalación/conexión; si ya está conectado, trae la
  // lista de notebooks para el selector.
  async function refreshNbStatus() {
    try {
      const st = await apiGet<NbStatus>("/api/notebooklm/status");
      setNbStatus(st);
      if (st.estado === "conectado") {
        apiGet<{ notebooks: { id: string; titulo: string }[] }>("/api/notebooklm/notebooks")
          .then((r) => setNbList(r.notebooks || []))
          .catch(() => {});
      }
    } catch {
      setNbStatus(null);
    }
  }

  async function installNb() {
    setNbBusy(true);
    setNbMsg("");
    try {
      await apiSend("POST", "/api/notebooklm/install", { confirmar: true });
      await refreshNbStatus();
    } catch {
      setNbMsg("No se pudo iniciar la instalación. Intenta de nuevo.");
    } finally {
      setNbBusy(false);
      setNbInstallConfirm(false);
    }
  }

  async function connectNb() {
    setNbBusy(true);
    setNbMsg("");
    try {
      await apiSend("POST", "/api/notebooklm/connect", {});
      await refreshNbStatus();
    } catch {
      setNbMsg("No se pudo abrir el inicio de sesión. Intenta de nuevo.");
    } finally {
      setNbBusy(false);
    }
  }

  async function confirmConnectNb() {
    setNbBusy(true);
    try {
      await apiSend("POST", "/api/notebooklm/connect/confirm", {});
      await refreshNbStatus();
    } catch {
      setNbMsg("No se pudo confirmar. Intenta de nuevo.");
    } finally {
      setNbBusy(false);
    }
  }

  // CP-NLM: guarda el opt-in de NotebookLM + el notebook. Envía SIEMPRE la política
  // actual (el PUT la exige) junto a los campos de NotebookLM, en una sola escritura.
  async function saveNotebookLM(enabled: boolean) {
    if (!policy) return;
    setNbBusy(true);
    setNbMsg("");
    try {
      const res = await apiSend<MotorPolicy>("PUT", "/settings/model-policy", {
        politica: policy.politica,
        allow_notebooklm: enabled,
        notebooklm_notebook: nbNotebook.trim(),
      });
      setPolicy(res);
      setNbNotebook(res.notebooklm_notebook || "");
      setNbMsg(
        enabled
          ? "Activado. Mia podrá consultar tu NotebookLM durante la investigación."
          : "Desactivado. Mia no consultará tu NotebookLM.",
      );
    } catch {
      setNbMsg("No se pudo guardar. Intenta de nuevo.");
    } finally {
      setNbBusy(false);
    }
  }

  async function syncObsidian() {
    setStatus("Sincronizando...");
    try {
      const res = await apiSend<{ chunks_indexed: number }>("POST", "/api/connectors/obsidian/sync", {
        vault_path: vaultPath || null,
      });
      setStatus(`${res.chunks_indexed} documentos sincronizados`);
      onChanged();
    } catch {
      setStatus("No se pudo sincronizar tu espacio de notas.");
    }
  }

  async function installObsidian() {
    setInstallBusy(true);
    setStatus("Instalando Obsidian… puede tardar unos minutos.");
    try {
      const res = await apiSend<{ installed: boolean; message: string }>(
        "POST", "/api/obsidian/install", { confirmar: true },
      );
      setStatus(res.message);
      apiGet<ObsidianStatus>("/api/obsidian/status").then(setObsidian).catch(() => {});
    } catch (e) {
      setStatus(e instanceof Error && e.message && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo instalar Obsidian en este momento. Intenta de nuevo más tarde.");
    } finally {
      setInstallBusy(false);
      setInstallConfirm(false);
    }
  }

  async function installSpeech() {
    setSpeechBusy(true);
    setSpeechMsg("");
    try {
      const res = await apiSend<{ status: string; message: string }>(
        "POST", "/api/speech/install", { confirmar: true },
      );
      setSpeechMsg(res.message);
      apiGet<SpeechStatus>("/api/speech/status").then(setSpeech).catch(() => {});
    } catch (e) {
      setSpeechMsg(e instanceof ApiError && !e.message.startsWith("Error ")
        ? e.message
        : "No se pudo iniciar la instalación del dictado. Intenta de nuevo.");
    } finally {
      setSpeechBusy(false);
      setSpeechConfirm(false);
    }
  }

  async function connectPinecone() {
    setStatus("Conectando...");
    try {
      const res = await apiSend<{ status: string; vectors_count: number }>("POST", "/api/connectors/pinecone/configure", {
        api_key: pineconeKey,
        index_name: pineconeIndex,
      });
      setStatus(res.status === "active" ? `${res.vectors_count} documentos disponibles` : "No se pudo activar");
      onChanged();
    } catch {
      setStatus("No se pudo conectar la memoria ampliada.");
    }
  }

  return (
    <div className="space-y-4">
      {/* Espacio de notas (Obsidian) */}
      <ConnectorCard
        icon={NotebookPen}
        title="Tu espacio de notas"
        active={Boolean(c.knowledge_base?.active)}
        subtitle={
          c.knowledge_base?.active
            ? `Activo · última sincronización ${fmt(c.knowledge_base.last_sync)}`
            : "Inactivo"
        }
        actions={
          <>
            {obsidian && !obsidian.installed ? (
              <Button variant="outline" size="sm" onClick={() => setInstallConfirm(true)} disabled={installBusy}>
                Instalar Obsidian
              </Button>
            ) : null}
            <Button size="sm" onClick={syncObsidian}>
              Sincronizar
            </Button>
          </>
        }
      >
        {obsidian ? <p className="mb-3 text-sm text-muted-foreground">{obsidian.message}</p> : null}
        {installConfirm ? (
          <div
            role="alertdialog"
            aria-label="Confirmar instalación de Obsidian"
            className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 animate-fade-in"
          >
            <p className="text-sm text-warning">
              Esta acción descarga e instala el programa Obsidian en este equipo. ¿Quieres continuar?
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={installObsidian} disabled={installBusy}>
                {installBusy ? "Instalando…" : "Sí, instalar"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setInstallConfirm(false)} disabled={installBusy}>
                Cancelar
              </Button>
            </div>
          </div>
        ) : null}
        <Label htmlFor="vault-path" className="mb-1.5 block text-sm text-muted-foreground">
          Ubicación de tu espacio de notas
        </Label>
        <div className="flex items-center gap-2">
          <Input
            id="vault-path"
            value={vaultPath}
            onChange={(e) => setVaultPath(e.target.value)}
            placeholder="Ej.: D:\Notas del despacho"
          />
          <Button type="button" variant="outline" size="sm" onClick={() => setVaultPickerOpen(true)} className="shrink-0">
            Elegir carpeta…
          </Button>
        </div>
      </ConnectorCard>

      <FolderPicker
        open={vaultPickerOpen}
        onOpenChange={setVaultPickerOpen}
        onPicked={(path) => setVaultPath(path)}
        title="Elegir carpeta de tu espacio de notas"
        description="Navega hasta la carpeta donde guardas tus notas de Obsidian."
      />

      {/* Dictado por voz */}
      <ConnectorCard
        icon={Mic}
        title="Dictado por voz"
        active={Boolean(speech?.listo)}
        subtitle={
          speech?.listo
            ? "Instalado · dicta con el micrófono desde el chat de tus asuntos"
            : speech?.estado === "descargando"
              ? "Instalando…"
              : "Inactivo"
        }
        actions={
          speech && !speech.listo && speech.estado !== "descargando" ? (
            <Button variant="outline" size="sm" onClick={() => setSpeechConfirm(true)} disabled={speechBusy}>
              Instalar dictado por voz
            </Button>
          ) : null
        }
      >
        {speech ? <p className="mb-3 text-sm text-muted-foreground">{speech.mensaje}</p> : null}
        {speech?.estado === "descargando" && speech.progreso ? (
          <div className="mb-3">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={speech.progreso.porcentaje ?? undefined}
              aria-label="Avance de la descarga del dictado por voz"
              className="h-2 w-full overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${speech.progreso.porcentaje ?? 5}%` }}
              />
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {speech.progreso.total_mb
                ? `${speech.progreso.descargado_mb} de ${speech.progreso.total_mb} MB`
                : `${speech.progreso.descargado_mb} MB descargados`}
            </p>
          </div>
        ) : null}
        {speechConfirm ? (
          <div
            role="alertdialog"
            aria-label="Confirmar instalación del dictado por voz"
            className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 animate-fade-in"
          >
            <p className="text-sm text-warning">
              Esta acción descarga el componente de dictado por voz (~700 MB) en el servidor de Mia.
              Puede tardar varios minutos. Tu voz nunca saldrá del servidor del despacho. ¿Quieres continuar?
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={installSpeech} disabled={speechBusy}>
                {speechBusy ? "Iniciando…" : "Sí, instalar"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSpeechConfirm(false)} disabled={speechBusy}>
                Cancelar
              </Button>
            </div>
          </div>
        ) : null}
        {speechMsg ? <p className="text-sm text-warning">{speechMsg}</p> : null}
      </ConnectorCard>

      {/* Sistemas conectados (CP-E6) — una tarjeta por sistema */}
      <ConnectedSystemsSection />

      {/* Calendario y correo */}
      <ConnectorCard icon={Mail} title="Calendario y correo" subtitle="Microsoft 365 o Google Workspace">
        <p className="mb-3 text-sm text-muted-foreground">
          Conecta tu cuenta para que Mia avise de eventos y correos urgentes.
        </p>
        <MailboxSectionLoader />
      </ConnectorCard>

      {/* Motor de IA */}
      <ConnectorCard icon={Settings2} title="Motor de IA" subtitle="Con qué trabaja Mia. Puedes cambiarlo cuando quieras.">
        <select
          value={policy?.politica || ""}
          onChange={(e) => changePolicy(e.target.value)}
          aria-label="Motor de IA"
          className="h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
        >
          {(policy?.opciones || []).map((o) => (
            <option key={o.id} value={o.id}>{o.nombre}</option>
          ))}
        </select>
        {policyMsg ? <p className="mt-2 text-sm text-muted-foreground">{policyMsg}</p> : null}
      </ConnectorCard>

      {/* Consultar mi NotebookLM (CP-NLM) */}
      {(() => {
        const disponible = policy ? policy.notebooklm_disponible !== false : true;
        const enabled = Boolean(policy?.allow_notebooklm);
        const estado = nbStatus?.estado;
        const conectado = estado === "conectado";
        return (
          <ConnectorCard
            icon={BookOpen}
            title="Consultar mi NotebookLM"
            active={enabled && conectado && disponible}
            subtitle={
              !disponible
                ? "No disponible con el motor “Todo en mi equipo”"
                : conectado
                  ? enabled
                    ? "Activo · Mia consulta tu NotebookLM al investigar"
                    : "Conectado · falta activarlo"
                  : "Sin configurar"
            }
          >
            <p className="mb-3 text-sm text-muted-foreground">
              Deja que Mia consulte lo que tú cargaste en tu propio NotebookLM mientras
              investiga un asunto.
            </p>
            <div
              role="note"
              className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
            >
              Ten en cuenta: cada pregunta que Mia le haga a NotebookLM <strong>viaja a
              Google</strong>. Úsalo solo si te queda claro. Lo que traiga NotebookLM entra
              como pista sin verificar, no como fuente citada.
            </div>

            {!disponible ? (
              <p className="text-sm text-muted-foreground">
                Está desactivado porque tu motor de IA es “Todo en mi equipo” (nada sale de
                tu computador). Cambia el motor de IA arriba si quieres usar esta función.
              </p>
            ) : estado === "instalando" ? (
              <div className="mb-1">
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={nbStatus?.progreso?.porcentaje ?? undefined}
                  aria-label="Avance de la instalación de NotebookLM"
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${nbStatus?.progreso?.porcentaje ?? 10}%` }}
                  />
                </div>
                <p className="mt-1.5 text-sm text-muted-foreground">{nbStatus?.mensaje}</p>
              </div>
            ) : !nbStatus?.instalado ? (
              // No instalado (o error de instalación): botón instalar, consent-first.
              <>
                <p className="mb-3 text-sm text-muted-foreground">{nbStatus?.mensaje}</p>
                {nbInstallConfirm ? (
                  <div
                    role="alertdialog"
                    aria-label="Confirmar instalación de NotebookLM"
                    className="rounded-lg border border-warning/30 bg-warning/10 p-3 animate-fade-in"
                  >
                    <p className="text-sm text-warning">
                      Esta acción descarga e instala NotebookLM (unos cientos de MB) en este
                      equipo. ¿Quieres continuar?
                    </p>
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" onClick={installNb} disabled={nbBusy}>
                        {nbBusy ? "Instalando…" : "Sí, instalar"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setNbInstallConfirm(false)} disabled={nbBusy}>
                        Cancelar
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => setNbInstallConfirm(true)} disabled={nbBusy}>
                    Instalar NotebookLM
                  </Button>
                )}
              </>
            ) : estado === "conectando" ? (
              // Login en curso: se abrió el navegador; el abogado confirma al terminar.
              <>
                <p className="mb-3 text-sm text-muted-foreground">{nbStatus?.mensaje}</p>
                <Button size="sm" onClick={confirmConnectNb} disabled={nbBusy}>
                  {nbBusy ? "Guardando…" : "Ya inicié sesión"}
                </Button>
              </>
            ) : !nbStatus?.autenticado ? (
              // Instalado sin conectar (o error de login): botón conectar cuenta.
              <>
                <p className="mb-3 text-sm text-muted-foreground">{nbStatus?.mensaje}</p>
                <Button variant="outline" size="sm" onClick={connectNb} disabled={nbBusy}>
                  Conectar mi cuenta de Google
                </Button>
              </>
            ) : (
              // Conectado: elegir notebook + activar.
              <>
                <Label htmlFor="nb-notebook" className="mb-1.5 block text-sm text-muted-foreground">
                  Notebook a consultar
                </Label>
                <div className="mb-3 flex items-center gap-2">
                  {nbList.length > 0 ? (
                    <select
                      id="nb-notebook"
                      value={nbNotebook}
                      onChange={(e) => setNbNotebook(e.target.value)}
                      aria-label="Notebook a consultar"
                      className="h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <option value="">— Elige un notebook —</option>
                      {nbList.map((n) => (
                        <option key={n.id} value={n.id}>{n.titulo}</option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      id="nb-notebook"
                      value={nbNotebook}
                      onChange={(e) => setNbNotebook(e.target.value)}
                      placeholder="Pega aquí el id de tu notebook"
                      disabled={nbBusy}
                    />
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => saveNotebookLM(enabled)}
                    disabled={nbBusy}
                  >
                    Guardar
                  </Button>
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary"
                    checked={enabled}
                    disabled={nbBusy}
                    onChange={(e) => saveNotebookLM(e.target.checked)}
                    aria-label="Permitir que Mia consulte mi NotebookLM"
                  />
                  Permitir que Mia consulte mi NotebookLM
                </label>
              </>
            )}
            {nbMsg ? <p className="mt-2 text-sm text-muted-foreground">{nbMsg}</p> : null}
          </ConnectorCard>
        );
      })()}

      {/* Memoria ampliada (avanzado) — plegada: casi nadie la necesita el día 1. */}
      <details className="group rounded-xl border border-border bg-card shadow-sm">
        <summary className="flex cursor-pointer items-center gap-3 px-5 py-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Layers className="h-4 w-4" />
          </span>
          <span className="flex-1">
            Memoria ampliada
            <span className="ml-2 text-xs font-normal text-muted-foreground">(opcional, avanzado)</span>
          </span>
          <span className="text-xs text-muted-foreground">
            {c.external_store?.active ? `Activa · ${c.external_store.vectors_count || 0} documentos` : "Inactiva"}
          </span>
        </summary>
        <div className="border-t border-border px-5 py-4">
          <p className="mb-3 text-sm text-muted-foreground">
            Un almacén adicional para despachos con miles de documentos. Si no sabes qué es, no lo necesitas.
          </p>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
            <Input
              type="password"
              autoComplete="off"
              value={pineconeKey}
              onChange={(e) => setPineconeKey(e.target.value)}
              placeholder="Clave de acceso"
              aria-label="Clave de acceso"
            />
            <Input
              value={pineconeIndex}
              onChange={(e) => setPineconeIndex(e.target.value)}
              placeholder="Nombre de tu colección de documentos"
              aria-label="Nombre de tu colección de documentos"
            />
            <Button onClick={connectPinecone}>Conectar</Button>
          </div>
        </div>
      </details>

      {status ? <p role="status" className="text-sm text-muted-foreground animate-fade-in">{status}</p> : null}
    </div>
  );
}
