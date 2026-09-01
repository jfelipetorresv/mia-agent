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
  GripVertical,
  ArrowUp,
  ArrowDown,
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
  /** Posición guardada. Solo decide entre los fijados; menor primero. */
  orden: number;
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
 * EL ORDEN DE LOS FIJADOS · se arrastra, y también se mueve con el teclado.
 *
 * Solo aparecen aquí los fijados, porque el orden solo decide entre ellos: los
 * automáticos los reparte Mia con lo que sobra del cupo, y prometer que se
 * pueden ordenar sería prometer algo que no se cumple.
 *
 * Arrastrar NO es la única forma de hacerlo, a propósito. El arrastre no existe
 * para quien navega con teclado ni funciona bien con el dedo, así que cada fila
 * trae además sus flechas y ambas rutas guardan exactamente lo mismo. El orden
 * se guarda al soltar (o al pulsar la flecha), no hay botón de confirmar.
 */
function OrdenFijados({
  fijados,
  guardando,
  onReordenar,
}: {
  fijados: AtajoCatalogo[];
  guardando: boolean;
  onReordenar: (claves: string[]) => void;
}) {
  const [arrastrando, setArrastrando] = useState<number | null>(null);

  if (fijados.length < 2) return null;

  const mover = (desde: number, hasta: number) => {
    if (hasta < 0 || hasta >= fijados.length || desde === hasta) return;
    const copia = fijados.slice();
    const [item] = copia.splice(desde, 1);
    copia.splice(hasta, 0, item);
    onReordenar(copia.map((a) => a.clave));
  };

  return (
    <div className="space-y-2">
      <p className="text-section">El orden en que los pongo</p>
      <p className="text-body text-muted-foreground">
        Arrástralos, o muévelos con las flechas. Este orden vale para los que fijaste; los
        que propongo yo van después, con el sitio que sobre.
      </p>
      <ul className={cn("space-y-1.5", guardando && "pointer-events-none opacity-60")}>
        {fijados.map((a, i) => (
          <li
            key={a.clave}
            draggable
            onDragStart={() => setArrastrando(i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (arrastrando !== null) mover(arrastrando, i);
              setArrastrando(null);
            }}
            onDragEnd={() => setArrastrando(null)}
            className={cn(
              "flex items-center gap-2 rounded-lg border border-border/10 bg-card shadow-neu-raised px-3 py-2",
              arrastrando === i && "opacity-50"
            )}
          >
            <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-muted-foreground" />
            <span className="w-5 shrink-0 text-body text-muted-foreground">{i + 1}</span>
            <IconoDe kind={a.kind} />
            <span className="min-w-0 flex-1 truncate text-body">{a.label}</span>
            <Button
              size="sm"
              variant="ghost"
              disabled={i === 0}
              onClick={() => mover(i, i - 1)}
              title="Subirlo un puesto"
              aria-label={`Subir ${a.label} un puesto`}
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={i === fijados.length - 1}
              onClick={() => mover(i, i + 1)}
              title="Bajarlo un puesto"
              aria-label={`Bajar ${a.label} un puesto`}
            >
              <ArrowDown className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
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

  // El orden que ve el abogado es el MISMO criterio con el que Mia arma la fila: primero
  // `orden`, y a igualdad, el nombre. Si esta pantalla ordenara distinto, arrastrar aquí
  // movería una lista que no es la que se muestra en la conversación.
  const fijados = atajos
    .filter((a) => a.fijado && !a.oculto)
    .slice()
    .sort((x, y) => (x.orden || 0) - (y.orden || 0) || x.label.localeCompare(y.label));

  function reordenar(claves: string[]) {
    // Optimista: la lista se reacomoda al soltar y luego se confirma contra el servidor.
    // Si la llamada falla, `cargar()` del manejador devuelve el orden real: nunca queda una
    // pantalla mostrando un orden que no se guardó.
    setAtajos((prev) =>
      prev.map((a) => {
        const i = claves.indexOf(a.clave);
        return i === -1 ? a : { ...a, orden: i + 1 };
      })
    );
    return accion("orden", () => apiSend("PUT", "/api/atajos/orden", { claves }));
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

        <OrdenFijados
          fijados={fijados}
          guardando={ocupado === "orden"}
          onReordenar={(claves) => void reordenar(claves)}
        />

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
