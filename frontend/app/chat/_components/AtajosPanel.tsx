"use client";

/**
 * TUS ATAJOS · la pantalla donde el abogado manda sobre los botones del chat
 * =========================================================================
 *
 * Pipe, bitácora 2026-08-19 (punto 18): «los atajos deberían poder
 * editarse/agregarse/quitarse». Hasta ahora se derivaban solos de las guías
 * activas y de los ayudantes del despacho, y esa derivación es lo bueno del
 * invento: aparecen sin que nadie configure nada. Lo que faltaba era la otra
 * mitad — poder decir «este siempre», «este no», «este se llama así» y «este
 * me lo escribo yo».
 *
 * POR QUÉ VIVE AQUÍ Y NO EN UNA PESTAÑA DE CONFIGURACIÓN. El abogado descubre
 * los atajos en la conversación vacía; es ahí donde se le ocurre que sobra uno
 * o que falta otro. Obligarle a recordar el impulso hasta llegar a otra
 * pantalla es la forma más segura de que no lo haga nunca. El control se abre
 * al lado de los propios atajos y los cambios se ven al cerrarlo.
 *
 * EL CUPO, DICHO EN VOZ ALTA. En la fila caben seis cómodamente. La regla es
 * que lo fijado NUNCA se descarta: si el abogado fija ocho, se muestran los
 * ocho y la fila crece — pero entonces no entra ningún atajo automático, y eso
 * se le dice con el número exacto en vez de dejar que lo deduzca. El conteo
 * viene del backend (`GET /api/atajos/catalogo`), no de una cuenta a ojo aquí.
 *
 * SIN JERGA (CLAUDE.md §G). En pantalla no aparece «guía derivada», «persona»,
 * ni el nombre de ningún endpoint: aparece «lo preparo yo a partir de tus
 * guías» y «lo escribiste tú».
 */

import { useCallback, useEffect, useState } from "react";
import {
  Pin,
  PinOff,
  Eye,
  EyeOff,
  Pencil,
  Plus,
  Trash2,
  RotateCcw,
  Wand2,
  UserRound,
  Sparkles,
  Check,
  X,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiSend, plainMessage } from "@/lib/api";
import { NotaMia } from "@/app/_components/NotaMia";
import { cn } from "@/lib/utils";

export type AtajoCatalogo = {
  clave: string;
  kind: "guia" | "agente" | "propio";
  id: string;
  label: string;
  texto: string;
  label_original: string;
  oculto: boolean;
  fijado: boolean;
  renombrado: boolean;
  en_conversacion: boolean;
};

type Cupo = {
  maximo: number;
  fijados: number;
  mostrados: number;
  automaticos: number;
  desbordado: boolean;
};

const ORIGEN: Record<AtajoCatalogo["kind"], string> = {
  guia: "Lo preparo yo a partir de una de tus guías",
  agente: "Lo preparo yo a partir de uno de tus ayudantes",
  propio: "Lo escribiste tú",
};

function IconoDe({ kind }: { kind: AtajoCatalogo["kind"] }) {
  const Icon = kind === "agente" ? UserRound : kind === "propio" ? Sparkles : Wand2;
  return <Icon className="h-4 w-4 shrink-0 text-primary" />;
}

/**
 * Una fila de la lista. Vive FUERA del componente de la pantalla a propósito:
 * definida dentro, React la trataría como un tipo distinto en cada render y
 * desmontaría la fila entera con cada tecla — el campo de renombrar perdía el
 * foco letra a letra.
 */
function FilaAtajo({
  a,
  enEdicion,
  trabajando,
  nombreEdit,
  textoEdit,
  onNombre,
  onTexto,
  onGuardar,
  onCancelar,
  onEditar,
  onFijar,
  onOcultar,
  onRestablecer,
}: {
  a: AtajoCatalogo;
  enEdicion: boolean;
  trabajando: boolean;
  nombreEdit: string;
  textoEdit: string;
  onNombre: (v: string) => void;
  onTexto: (v: string) => void;
  onGuardar: () => void;
  onCancelar: () => void;
  onEditar: () => void;
  onFijar: () => void;
  onOcultar: () => void;
  onRestablecer: () => void;
}) {
  return (
    <Card
      padding="sm"
      className={cn(
        "transition-opacity",
        a.oculto && "opacity-60",
        trabajando && "pointer-events-none opacity-50"
      )}
    >
      {enEdicion ? (
        <div className="space-y-2">
          <Input
            value={nombreEdit}
            onChange={(e) => onNombre(e.target.value)}
            maxLength={48}
            aria-label="Nombre del atajo"
            placeholder="Cómo quieres que se llame"
          />
          {a.kind === "propio" ? (
            <Textarea
              value={textoEdit}
              onChange={(e) => onTexto(e.target.value)}
              maxLength={2000}
              rows={3}
              aria-label="Lo que me pides con este atajo"
              placeholder="Lo que quieres pedirme al pulsarlo"
            />
          ) : (
            <p className="text-body text-muted-foreground">
              Aquí cambias solo el nombre que ves. Lo que me pides sale de tu{" "}
              {a.kind === "agente" ? "ayudante" : "guía"} y se edita allí.
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={onGuardar} className="gap-1.5">
              <Check className="h-3.5 w-3.5" />
              Guardar
            </Button>
            <Button size="sm" variant="ghost" onClick={onCancelar} className="gap-1.5">
              <X className="h-3.5 w-3.5" />
              Cancelar
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3">
          <IconoDe kind={a.kind} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-section">{a.label}</p>
            <p className="mt-0.5 line-clamp-2 text-body text-muted-foreground">{a.texto}</p>
            <p className="mt-1 text-body text-muted-foreground">
              {ORIGEN[a.kind]}
              {a.renombrado ? ` · lo renombraste (antes: ${a.label_original})` : ""}
              {a.oculto
                ? " · oculto"
                : a.fijado
                  ? " · fijado, aparece siempre"
                  : a.en_conversacion
                    ? " · se está mostrando"
                    : " · ahora mismo no cabe"}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={onFijar}
              title={a.fijado ? "Dejar de fijarlo" : "Fijarlo para que aparezca siempre"}
              aria-label={
                a.fijado
                  ? `Dejar de fijar ${a.label}`
                  : `Fijar ${a.label} para que aparezca siempre`
              }
            >
              {a.fijado ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onOcultar}
              title={a.oculto ? "Volver a mostrarlo" : "Ocultarlo"}
              aria-label={a.oculto ? `Volver a mostrar ${a.label}` : `Ocultar ${a.label}`}
            >
              {a.oculto ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onEditar}
              title={a.kind === "propio" ? "Editarlo" : "Cambiarle el nombre"}
              aria-label={
                a.kind === "propio" ? `Editar ${a.label}` : `Cambiar el nombre de ${a.label}`
              }
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onRestablecer}
              title={
                a.kind === "propio"
                  ? "Borrarlo"
                  : "Dejarlo como yo lo propongo (nombre original, sin fijar, sin ocultar)"
              }
              aria-label={
                a.kind === "propio"
                  ? `Borrar ${a.label}`
                  : `Dejar ${a.label} como Mia lo propone`
              }
            >
              {a.kind === "propio" ? (
                <Trash2 className="h-4 w-4" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

/**
 * El aviso del cupo. Nunca dice «se descartaron atajos»: dice exactamente qué
 * está pasando con los números reales del despacho.
 */
function AvisoCupo({ cupo }: { cupo: Cupo }) {
  if (cupo.desbordado) {
    return (
      <p className="text-body text-warning">
        Fijaste {cupo.fijados} atajos y en la fila caben {cupo.maximo} sin apretarse. Los
        muestro todos —lo que fijas no lo quito nunca—, así que la fila se hará más larga. Y
        mientras tengas {cupo.maximo} o más fijados, no entra ninguno de los que propongo yo.
      </p>
    );
  }
  if (cupo.fijados >= cupo.maximo) {
    return (
      <p className="text-body text-muted-foreground">
        Tienes {cupo.fijados} atajos fijados y en la fila caben {cupo.maximo}: el sitio está
        justo lleno con los tuyos, así que ahora mismo no entra ninguno de los que propongo yo.
      </p>
    );
  }
  return (
    <p className="text-body text-muted-foreground">
      En la fila caben {cupo.maximo}. Tienes {cupo.fijados} fijados y yo relleno los{" "}
      {cupo.maximo - cupo.fijados} que quedan con lo que más usas.
    </p>
  );
}

export function AtajosPanel({
  open,
  onOpenChange,
  onCambio,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Se llama tras cada cambio guardado, para que el chat recargue su fila. */
  onCambio?: () => void;
}) {
  const [atajos, setAtajos] = useState<AtajoCatalogo[]>([]);
  const [cupo, setCupo] = useState<Cupo | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);

  // Edición en línea del atajo que se está renombrando (o reescribiendo, si es propio).
  const [editando, setEditando] = useState<string | null>(null);
  const [nombreEdit, setNombreEdit] = useState("");
  const [textoEdit, setTextoEdit] = useState("");

  // Alta de un atajo propio.
  const [creando, setCreando] = useState(false);
  const [nombreNuevo, setNombreNuevo] = useState("");
  const [textoNuevo, setTextoNuevo] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const res = await apiGet<{ atajos: AtajoCatalogo[]; cupo: Cupo }>("/api/atajos/catalogo");
      setAtajos(res.atajos || []);
      setCupo(res.cupo);
    } catch (e) {
      setError(plainMessage(e, "No pude cargar tus atajos. Intenta de nuevo."));
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (open) void cargar();
  }, [open, cargar]);

  async function accion(clave: string, fn: () => Promise<unknown>) {
    setOcupado(clave);
    setError("");
    try {
      await fn();
      await cargar();
      onCambio?.();
    } catch (e) {
      setError(plainMessage(e, "No pude guardar el cambio. Intenta de nuevo."));
    } finally {
      setOcupado(null);
    }
  }

  const ruta = (clave: string) => `/api/atajos/${encodeURIComponent(clave)}`;

  function fijar(a: AtajoCatalogo) {
    return accion(a.clave, () => apiSend("PATCH", ruta(a.clave), { fijado: !a.fijado }));
  }

  function ocultar(a: AtajoCatalogo) {
    return accion(a.clave, () => apiSend("PATCH", ruta(a.clave), { oculto: !a.oculto }));
  }

  function restablecer(a: AtajoCatalogo) {
    return accion(a.clave, () => apiSend("DELETE", ruta(a.clave)));
  }

  function abrirEdicion(a: AtajoCatalogo) {
    setEditando(a.clave);
    setNombreEdit(a.label);
    setTextoEdit(a.texto);
    setError("");
  }

  function guardarEdicion(a: AtajoCatalogo) {
    const nombre = nombreEdit.trim();
    const texto = textoEdit.trim();
    if (!nombre) {
      setError("Ponle un nombre al atajo para poder reconocerlo.");
      return;
    }
    return accion(a.clave, async () => {
      if (a.kind === "propio") {
        await apiSend("PUT", ruta(a.clave), { label: nombre, texto });
      } else {
        await apiSend("PATCH", ruta(a.clave), { label: nombre });
      }
      setEditando(null);
    });
  }

  async function crear() {
    const nombre = nombreNuevo.trim();
    const texto = textoNuevo.trim();
    if (!nombre || !texto) {
      setError("Un atajo tuyo necesita un nombre y lo que quieres pedirme al pulsarlo.");
      return;
    }
    await accion("nuevo", async () => {
      await apiSend("POST", "/api/atajos", { label: nombre, texto });
      setNombreNuevo("");
      setTextoNuevo("");
      setCreando(false);
    });
  }

  const propios = atajos.filter((a) => a.kind === "propio");
  const derivados = atajos.filter((a) => a.kind !== "propio");

  const fila = (a: AtajoCatalogo) => (
    <FilaAtajo
      key={a.clave}
      a={a}
      enEdicion={editando === a.clave}
      trabajando={ocupado === a.clave}
      nombreEdit={nombreEdit}
      textoEdit={textoEdit}
      onNombre={setNombreEdit}
      onTexto={setTextoEdit}
      onGuardar={() => void guardarEdicion(a)}
      onCancelar={() => setEditando(null)}
      onEditar={() => abrirEdicion(a)}
      onFijar={() => void fijar(a)}
      onOcultar={() => void ocultar(a)}
      onRestablecer={() => void restablecer(a)}
    />
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Tus atajos</DialogTitle>
          <DialogDescription>
            Los botones que te ofrezco al abrir una conversación nueva.
          </DialogDescription>
        </DialogHeader>

        <NotaMia id="atajos-como-funcionan" icon={Wand2} titulo="Los propongo yo; mandas tú">
          Miro tus guías y tus ayudantes y armo estos botones sola, sin que configures nada.
          Aquí puedes fijar el que quieras tener siempre a mano, apartar el que te estorbe,
          cambiarle el nombre o escribir uno tuyo. Al pulsarlo escribo el texto en tu cuadro de
          mensaje: lo revisas y decides si me lo envías.
        </NotaMia>

        {cupo ? <AvisoCupo cupo={cupo} /> : null}

        {error ? (
          <Card padding="sm" className="border-destructive/30 bg-destructive/5">
            <p className="text-body text-destructive">{error}</p>
          </Card>
        ) : null}

        {/* Los tuyos */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-section">Los tuyos</p>
            {!creando ? (
              <Button size="sm" variant="outline" onClick={() => setCreando(true)} className="gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                Escribir un atajo
              </Button>
            ) : null}
          </div>

          {creando ? (
            <Card padding="sm" className="space-y-2">
              <Input
                value={nombreNuevo}
                onChange={(e) => setNombreNuevo(e.target.value)}
                maxLength={48}
                aria-label="Nombre del atajo nuevo"
                placeholder="Cómo se va a llamar el botón"
              />
              <Textarea
                value={textoNuevo}
                onChange={(e) => setTextoNuevo(e.target.value)}
                maxLength={2000}
                rows={3}
                aria-label="Lo que me pides con el atajo nuevo"
                placeholder="Lo que quieres pedirme cuando lo pulses"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => void crear()}
                  disabled={ocupado === "nuevo"}
                  className="gap-1.5"
                >
                  <Check className="h-3.5 w-3.5" />
                  Guardar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setCreando(false);
                    setError("");
                  }}
                  className="gap-1.5"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancelar
                </Button>
              </div>
            </Card>
          ) : null}

          {propios.length === 0 && !creando ? (
            <Card padding="sm" variant="dashed">
              <p className="text-body text-muted-foreground">
                Todavía no has escrito ninguno. Los tuyos aparecen siempre de primeros.
              </p>
            </Card>
          ) : (
            propios.map(fila)
          )}
        </div>

        {/* Los que propone Mia */}
        <div className="space-y-2">
          <p className="text-section">Los que preparo yo</p>
          {cargando && derivados.length === 0 ? (
            <Card padding="sm" variant="dashed">
              <p className="text-body text-muted-foreground">Un momento, los estoy reuniendo…</p>
            </Card>
          ) : derivados.length === 0 ? (
            <Card padding="sm" variant="dashed">
              <p className="text-body text-muted-foreground">
                Aún no tengo de dónde sacarlos: salen de tus guías activas y de tus ayudantes.
                En cuanto tengas alguno, aparecen aquí solos.
              </p>
            </Card>
          ) : (
            derivados.map(fila)
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default AtajosPanel;
