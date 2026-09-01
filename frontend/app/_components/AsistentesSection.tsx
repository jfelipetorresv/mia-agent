"use client";

// Agent Hub · "Ayudantes externos" — programas de terceros instalados en el equipo del
// abogado que Mia puede llamar para una tarea puntual. Activar aquí SOLO decide qué
// ayudantes existen para el despacho; el mensaje del abogado en el chat decide si algo
// sale y qué sale (invocación explícita, nunca automática). Ver backend/gateway/hub_gate.py.
// §G: nunca jerga técnica — el abogado ve nombres en español, nunca "CLI"/"binario"/"tenant".

import { useCallback, useEffect, useState } from "react";
import type { ComponentType } from "react";
import { Bot, FileText, Globe, Monitor, Search, Zap } from "lucide-react";
import { apiGet, apiSend, plainMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConnectorCard, EmptyHint } from "@/app/_components/PanelUI";

type Agente = {
  id: string;
  nombre: string;
  // Marca comercial del programa (excepción §G, decisión de Pipe 2026-08-24): se
  // muestra en letra pequeña bajo el nombre por función, para que el abogado sepa
  // qué instalar. El nombre principal sigue siendo funcional y en español.
  marca?: string;
  instalado: boolean;
  habilitado: boolean;
  listo?: boolean;
  razon?: string;
};

type AgentsResponse = {
  agentes: Agente[];
  bloqueado_por_politica?: boolean;
  aviso_consentimiento?: string;
};

// Icono por id (id público neutro, ver backend/gateway/agent_hub.py::CONNECTORS). Un id
// nuevo que el backend agregue mañana cae al ícono genérico, nunca rompe la pantalla.
const AGENT_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  investigacion: Search,
  documentos: FileText,
  automatizacion: Zap,
  escritorio: Monitor,
  navegacion: Globe,
};

function agentIcon(id: string): ComponentType<{ className?: string }> {
  return AGENT_ICONS[id] || Bot;
}

// Línea de marca en letra pequeña (excepción §G, decisión de Pipe 2026-08-24). Le dice
// al abogado con qué programa funciona el ayudante y, si falta, que hay que instalarlo.
// La razón honesta de «no listo» sigue diciendo lo suyo aparte.
function lineaMarca(agente: Agente): string {
  if (!agente.marca) return "";
  if (!agente.instalado) {
    return `Funciona con ${agente.marca}: hay que instalarlo para activar este ayudante.`;
  }
  if (agente.listo) {
    return `Funciona con ${agente.marca}, ya instalado en tu equipo.`;
  }
  return `Funciona con ${agente.marca}.`;
}

function estadoTexto(agente: Agente): string {
  if (agente.habilitado) {
    return agente.listo ? "Activado · listo para usar" : "Activado · no está listo en este equipo";
  }
  if (agente.listo) return "Desactivado";
  return agente.razon || "Desactivado · no está listo en este equipo";
}

export default function AsistentesSection() {
  const [agentes, setAgentes] = useState<Agente[] | null>(null);
  const [bloqueado, setBloqueado] = useState(false);
  const [aviso, setAviso] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await apiGet<AgentsResponse>("/settings/agents");
      setAgentes(data.agentes || []);
      setBloqueado(Boolean(data.bloqueado_por_politica));
      setAviso(data.aviso_consentimiento || "");
    } catch (err) {
      setAgentes(null);
      setError(plainMessage(err, "No se pudieron cargar los ayudantes externos."));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Serializado a propósito (§ instrucciones): mientras `busy` no sea null, TODAS las
  // filas quedan deshabilitadas, no solo la que está en curso — dos activaciones/
  // desactivaciones a la vez pueden pisarse en la configuración guardada del despacho.
  async function toggle(agente: Agente) {
    setBusy(agente.id);
    setMsg("");
    try {
      const accion = agente.habilitado ? "disable" : "enable";
      await apiSend<{ id: string; nombre: string; habilitado: boolean }>(
        "POST",
        `/settings/agents/${agente.id}/${accion}`,
      );
      await load();
    } catch (err) {
      setMsg(plainMessage(err, `No se pudo actualizar «${agente.nombre}».`));
    } finally {
      setBusy(null);
    }
  }

  if (!loaded) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
    );
  }

  if (error) {
    return <p role="alert" className="text-sm text-warning">{error}</p>;
  }

  return (
    <div className="space-y-4">
      {/* El título y la frase de entrada los pone SectionTitle desde la página
          (patrón del resto de secciones); aquí solo va lo que hay que explicar. */}
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>
          Activar un ayudante aquí solo decide que ese ayudante existe para tu despacho. Cómo
          Mia lo usa depende del modo de delegación en Ajustes: puede proponerte ayuda y
          pedirte autorización, hacerlo de forma autónoma, o llamarlo solo cuando tú lo
          nombras en el mensaje (por ejemplo: «usa el asistente de navegación web para buscar
          el estado del proceso»).
        </p>
        <p>
          Lo único que sale hacia ese ayudante es el texto que tú autorizas (o el de tu
          mensaje si lo pediste explícitamente) — nunca tus documentos, los hechos del
          expediente, tu perfil ni el historial de la conversación. Ten en cuenta que es un
          programa de un tercero y normalmente se conecta a internet por su cuenta, fuera del
          control de Mia.
        </p>
        <p>
          Esto acaba de activarse y todavía no lo hemos probado en una tarea real: es posible
          que algún ayudante no responda como se espera la primera vez. Si eso pasa, Mia te lo
          va a decir con claridad y tu trabajo no se pierde ni se detiene.
        </p>
      </div>

      {aviso ? (
        <p className="rounded-lg border border-dashed border-border bg-card/40 backdrop-blur-md shadow-neu-raised px-3 py-2 text-sm text-muted-foreground">
          {aviso}
        </p>
      ) : null}

      {bloqueado ? (
        <p role="status" className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">
          Tu despacho tiene activada la política «Todo en mi equipo»: por ahora ningún ayudante
          va a salir de este computador, así actives el interruptor. Es una decisión que ya
          tomó tu despacho, no una falla. Puedes dejar tus ayudantes listos para cuando decidan
          cambiar esa política.
        </p>
      ) : null}

      {msg ? <p role="alert" className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{msg}</p> : null}

      {!agentes?.length ? (
        <EmptyHint icon={Bot}>
          Todavía no hay ayudantes externos disponibles para tu despacho.
        </EmptyHint>
      ) : (
        <ul className="space-y-3">
          {agentes.map((agente) => (
            <li key={agente.id}>
              <ConnectorCard
                icon={agentIcon(agente.id)}
                title={agente.nombre}
                subtitle={estadoTexto(agente)}
                active={agente.habilitado}
                actions={
                  <Button
                    size="sm"
                    variant={agente.habilitado ? "outline" : "default"}
                    onClick={() => toggle(agente)}
                    disabled={busy !== null || (!agente.habilitado && agente.listo === false)}
                  >
                    {busy === agente.id ? "Guardando…" : agente.habilitado ? "Desactivar" : "Activar"}
                  </Button>
                }
              >
                {lineaMarca(agente) ? (
                  <p className="text-xs text-muted-foreground">{lineaMarca(agente)}</p>
                ) : null}
                {/* P3 · `Badge` es un <div>: dentro de un <p> el navegador CIERRA el
                    párrafo antes de él, así que el HTML del servidor y el del cliente
                    dejaban de coincidir (aviso de hidratación en /configurar#conexiones)
                    y la razón honesta se salía del renglón. El contenedor pasa a <div>
                    y el texto conserva su propio <span>. */}
                {!agente.listo ? (
                  <div className="flex items-start gap-2 text-body text-muted-foreground">
                    <Badge variant="outline" className="shrink-0">No listo</Badge>
                    <span className="text-pretty">
                      {agente.razon || "Mia no pudo confirmar cómo invocarlo en este equipo."}
                    </span>
                  </div>
                ) : !agente.instalado ? (
                  <div className="flex items-start gap-2 text-body text-muted-foreground">
                    <Badge variant="outline" className="shrink-0">No instalado</Badge>
                    <span className="text-pretty">
                      No está en este equipo. Cuando el programa esté instalado, Mia
                      confirmará cómo invocarlo y podrás activarlo.
                    </span>
                  </div>
                ) : null}
              </ConnectorCard>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
