"use client";

// Mia · Panel del despacho.
//
// LA DECISIÓN DE 2026-07-09 SIGUE EN PIE, CORREGIDA EN SU EJECUCIÓN: el Panel
// muestra SOLO lo accionable del día. Lo que se hizo mal fue leer "solo lo
// accionable" como "quitar cosas", cuando significa "traer lo accionable, esté
// donde esté". El resultado era un Panel vacío que conservaba dos rejillas de
// totales (que NO son accionables) mientras dejaba fuera el recorrido de puesta
// a punto, el resumen del día de cada asunto y la salud de las guías — que son
// exactamente lo que el abogado tiene que decidir. Aquí se invierte:
//
//   1 · lo que exige una decisión suya    (borradores, día de los asuntos)
//   2 · lo que Mia le sugiere o le falta  (puesta a punto, guías, consejos)
//   3 · lo informativo                    (el mes, en una sola rejilla)
//
// BLOQUE 2 DEL REDISEÑO (2026-08-19): esa misma jerarquía deja de expresarse
// como una COLUMNA de seis secciones —que obligaba a bajar dos pantallas para
// enterarse de que había un borrador esperando— y pasa a una REJILLA bento:
//
//   · fila superior     cifras del mes, tarjetas compactas
//   · columna principal lo que pide su decisión (celda dominante) y su día
//   · columna lateral   recordatorios, puesta a punto y guías
//
// No cambia ni una fuente de datos ni un estado: es re-composición visual. Lo
// que cambia es qué se ve primero, que era el defecto de la pantalla.
//
// Los formularios (tarifa, tope, conexiones, carpetas) siguen viviendo en
// Configuración: aquí solo se avisa y se enlaza, nunca se edita.
//
// TODAS las fuentes se leen con `apiGetSoft`: si una falla, su tarjeta se
// degrada sola y las demás siguen en pie. El Panel no tiene pantalla en blanco.
//
// Y "degradarse" aquí significa DECIR QUE NO SE PUDO, jamás rellenar. El
// respaldo de cada fuente es `null` —una ausencia reconocible—, nunca `{}` ni
// `[]`: un objeto vacío se pinta como ceros y una lista vacía se lee como "no
// tienes nada pendiente". Las dos son afirmaciones sobre el trabajo del
// despacho, y el abogado puede decidir sobre ellas. Tres estados, siempre
// distinguibles en pantalla: cargando (esqueleto) · dato real, aunque sea un
// cero de verdad · no disponible ahora mismo.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
  Folder,
  Layers,
  ListChecks,
  MessageSquare,
  Sparkles,
  Wallet,
} from "lucide-react";
import {
  ApiError,
  apiGetSoft,
  apiSend,
  getBudget,
  getMatterDaily,
  getPlaybookHealth,
  getSetupStatus,
  type BudgetStatus,
  type DailyBriefing,
  type PlaybookHealth,
  type SetupStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageShell } from "@/app/_components/PageShell";
import { EmptyHint, NeuIcon, PanelCard, StatCard, fmtHora } from "@/app/_components/PanelUI";
import { staggerStyle } from "@/lib/motion";

/**
 * Resumen del despacho. Se declaran los campos que el Panel USA de verdad; el
 * servidor manda bastante más (salud interna de Mia, motores disponibles, caché)
 * y eso pertenece a Configuración, no aquí.
 */
type Stats = {
  matters_active?: number;
  documents_indexed?: number;
  proposals_pending?: number;
  value?: {
    hours_saved?: number;
    net_usd?: number;
    drafts_approved?: number;
    consultations?: number;
    draft_minutes?: number;
    turn_minutes?: number;
  };
  scheduler_jobs?: { label: string; next_run: string | null; last_run: string | null }[];
  connectors?: { models?: string[] };
};

type Reminder = { id: string; text: string; due_at: string; is_procedural: boolean };

// CP-V2 · recomendaciones del auto-diagnóstico semanal (GET /api/dreams/prescriptions).
type Prescription = {
  id: string;
  category: string;
  headline: string;
  prescription: string;
  evidence: string[];
  dollar_impact: number | null;
  time_impact_mins: number | null;
  status: "new" | "recurring";
  age_days: number;
};

type Matter = {
  id: string;
  name: string;
  status?: string;
  kind?: string;
  pending_review?: boolean;
};

/** Un asunto con su resumen del día, ya filtrado a lo que pide decisión. */
type DailyRow = { matter: Matter; briefing: DailyBriefing };

/**
 * Tope de asuntos a los que se les pide el resumen del día.
 *
 * Es la ÚNICA llamada del Panel con costo real: el servidor lee el expediente
 * en disco, un asunto por petición. Con el tope, un despacho con 200 asuntos
 * hace 5 peticiones, no 200. Cuando haga falta ver más, el sitio es la pantalla
 * de Asuntos, no el Panel.
 */
const DAILY_MAX = 5;

/**
 * Cuántos asuntos y proyectos caben en la celda grande del Panel.
 *
 * No es un límite de datos —la lista ya llegó entera en la misma petición—
 * sino de LECTURA: seis filas es lo que se recorre de un vistazo. Lo que queda
 * fuera se dice con números y se enlaza a Asuntos y Proyectos, que es su sitio.
 */
const MATTERS_MAX = 6;

/**
 * Rejilla que se adapta al número REAL de tarjetas.
 *
 * El defecto que corrige: había dos rejillas declaradas `sm:grid-cols-4` con
 * dos hijos, así que desde 640px de ancho el Panel pintaba dos celdas vacías,
 * dos veces. Media pantalla en blanco no era falta de datos: era una rejilla
 * pidiendo cuatro columnas para dos cosas. Las clases van literales para que
 * el compilador de Tailwind las encuentre al escanear el archivo.
 *
 * El hueco es `gap-block` (--space-block): la rejilla del Panel y la separación
 * entre sus celdas salen del mismo token, no de un `gap-4` suelto.
 */
function gridFor(count: number): string {
  if (count <= 1) return "grid gap-block";
  if (count === 2) return "grid gap-block sm:grid-cols-2";
  if (count === 3) return "grid gap-block sm:grid-cols-3";
  return "grid gap-block sm:grid-cols-2 xl:grid-cols-4";
}

/** El rótulo del tipo de fila, en el idioma del oficio (nunca el `kind` crudo). */
function tipoDe(m: Matter): string {
  return m.kind === "proyecto" ? "Proyecto" : "Asunto";
}

/**
 * Una fila DENTRO de una celda del Panel.
 *
 * En una rejilla bento el contenido de una tarjeta no puede ser otra tarjeta
 * elevada: dos relieves anidados compiten y la celda pierde su borde. La fila
 * interior se esculpe hacia adentro (bajo relieve), que es el otro término del
 * mismo vocabulario, y así la celda sigue siendo la única superficie que flota.
 */
const FILA = "rounded-xl bg-muted/40 px-4 py-3 shadow-neu-sunken";

/** Redondea a dos decimales SIN convertir a texto, para que `StatCard` la alinee. */
function money(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * A dónde lleva una fila del Panel.
 *
 * El Panel pide `kind=todos`, así que sus listas traen ASUNTOS y PROYECTOS
 * mezclados — son dos espacios distintos, con pantallas distintas y con
 * promesas distintas ("todo termina en un borrador que tú apruebas" es del
 * asunto, no del proyecto). El destino se decide por el tipo real de la fila y
 * no por el sitio donde está escrito el enlace, que es lo que mandaba un
 * proyecto a la pantalla de asuntos. Lo desconocido cae en Asuntos, que es el
 * mismo criterio conservador del servidor cuando no reconoce un `kind`.
 */
function rutaDe(m: Matter): string {
  return m.kind === "proyecto" ? `/proyectos/${m.id}` : `/asuntos/${m.id}`;
}

/** El borrador se revisa DENTRO del asunto; un proyecto no tiene esa pantalla,
 *  así que se abre el proyecto en vez de mandar al abogado a una ruta ajena. */
function rutaRevisar(m: Matter): string {
  return m.kind === "proyecto" ? `/proyectos/${m.id}` : `/asuntos/${m.id}/revisar`;
}

/**
 * ¿Esta etiqueta está escrita para el abogado o es un identificador interno?
 *
 * El filtro anterior descartaba solo lo que llevara guion bajo: una lista negra
 * por puntuación, no una traducción, que dejaba pasar un `syncDrive` a la
 * pantalla. Se cierra al criterio contrario —ante la duda NO se muestra—
 * añadiendo el camelCase, el resto de la puntuación de código y la palabra
 * suelta en minúsculas (`backup`, `cleanup`), que es como se ven los nombres de
 * proceso y no como se escribe un rótulo para una persona.
 */
function etiquetaLegible(label?: string): boolean {
  const t = (label || "").trim();
  if (!t) return false;
  if (/[_:./\\]/.test(t)) return false; // puntuación de código
  if (/[a-z][A-Z]/.test(t)) return false; // camelCase
  if (!/\s/.test(t) && t === t.toLowerCase()) return false; // una sola palabra en minúsculas
  return true;
}

/**
 * Esqueleto con la FORMA FINAL de la pantalla, no un cuadro genérico.
 *
 * Un rectángulo que no se parece a lo que va a llegar produce un salto de
 * layout al cargar. Estas piezas ocupan el sitio de la fila de cifras, de la
 * columna principal y de la lateral, que es la rejilla que aparece después.
 */
function PanelSkeleton() {
  return (
    <div className="space-y-block">
      <div className="grid gap-block sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
      <div className="grid gap-block lg:grid-cols-3">
        <div className="space-y-block lg:col-span-2">
          <Skeleton className="h-56 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
        <div className="space-y-block">
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-32 w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [loaded, setLoaded] = useState(false);
  // `null` = las cifras del despacho NO llegaron. Antes el estado arrancaba y se
  // quedaba en `{}`, indistinguible de un despacho sin actividad.
  const [s, setS] = useState<Stats | null>(null);
  // Igual para la lista de asuntos y proyectos: si no respondió, el Panel no
  // puede afirmar "nada espera tu decisión".
  const [mattersOk, setMattersOk] = useState(true);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [reminderMsg, setReminderMsg] = useState("");
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [health, setHealth] = useState<PlaybookHealth | null>(null);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [prescriptionsLoaded, setPrescriptionsLoaded] = useState(false);
  const [expandedRx, setExpandedRx] = useState<string | null>(null);
  const [rxMsg, setRxMsg] = useState("");
  const [rxBusy, setRxBusy] = useState<string | null>(null);
  // La lista completa que YA se pide (misma petición, mismo dato): alimenta la
  // tarjeta grande "Tus asuntos y proyectos". Antes solo se guardaba el filtro
  // de los que tenían borrador, así que el resto del dato llegaba y se tiraba.
  const [allMatters, setAllMatters] = useState<Matter[]>([]);
  const [pendingMatters, setPendingMatters] = useState<Matter[]>([]);
  const [dailyRows, setDailyRows] = useState<DailyRow[]>([]);
  const [dailyLoaded, setDailyLoaded] = useState(false);
  // Cuántos había ANTES del recorte y cuántos no respondieron. Sin estos dos
  // números el Panel no puede decir qué está dejando fuera, y aquí un recorte
  // en silencio está prohibido: si se ven los primeros N de M, se dice con
  // números.
  const [dailyTotal, setDailyTotal] = useState(0);
  const [dailySinRespuesta, setDailySinRespuesta] = useState(0);

  // `useCallback` porque también se llama al decidir una recomendación, y porque
  // así puede declararse como dependencia del efecto sin reactivarlo en cada
  // render (era el aviso de dependencias que arrastraba esta pantalla).
  const loadPrescriptions = useCallback(async () => {
    const data = await apiGetSoft<{ prescriptions?: Prescription[] }>(
      "/api/dreams/prescriptions",
      {},
    );
    setPrescriptions(data.prescriptions || []);
    setPrescriptionsLoaded(true);
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // Primera tanda: todo lo que decide la FORMA de la pantalla, en paralelo.
      // Ninguna puede lanzar (apiGetSoft), así que `Promise.all` nunca se rompe
      // por una fuente caída.
      const [stats, setupStatus, healthSummary, budgetStatus, matters] = await Promise.all([
        // Respaldo `null`, NO `{}`: con `{}` cada cifra caía en `?? 0` y el
        // Panel le afirmaba al abogado "0 borradores aprobados · 0 horas
        // ahorradas · USD 0.00" cuando lo único cierto era que el servidor de
        // cifras no había respondido.
        apiGetSoft<Stats | null>("/api/dashboard/stats", null),
        getSetupStatus(),
        getPlaybookHealth(),
        getBudget(),
        // `kind=todos`: sin el parámetro el servidor devuelve solo los asuntos y
        // los PROYECTOS con algo esperando quedaban invisibles en el Panel.
        // Respaldo `null` por lo mismo: una lista vacía se leería como "no
        // tienes nada pendiente", que es una afirmación, no una ausencia.
        apiGetSoft<Matter[] | null>("/api/matters?kind=todos", null),
      ]);
      if (cancelled) return;

      const list = matters || [];
      setS(stats);
      setMattersOk(matters !== null);
      setSetup(setupStatus);
      setHealth(healthSummary);
      setBudget(budgetStatus);
      setAllMatters(list);
      setPendingMatters(list.filter((m) => m.pending_review));
      setLoaded(true);

      // Segunda tanda: entra cuando llegue, sin retrasar la primera pintura.
      apiGetSoft<Reminder[]>("/api/assistant/reminders", []).then((r) => {
        if (!cancelled) setReminders(r || []);
      });
      loadPrescriptions();

      // Tercera: el resumen del día de los asuntos y proyectos activos, acotado.
      // Se guarda cuántos candidatos había antes del recorte (`dailyTotal`) y
      // cuántos de los consultados no respondieron (`dailySinRespuesta`): son
      // los dos números con los que la sección declara después qué deja fuera.
      const candidatos = list.filter((m) => m.status === "active");
      setDailyTotal(candidatos.length);
      const briefings = await Promise.all(
        candidatos.slice(0, DAILY_MAX).map(async (matter) => ({
          matter,
          briefing: await getMatterDaily(matter.id),
        })),
      );
      if (cancelled) return;
      setDailySinRespuesta(briefings.filter((row) => row.briefing === null).length);
      setDailyRows(
        briefings.filter(
          (row): row is DailyRow => row.briefing !== null && row.briefing.requieren_decision > 0,
        ),
      );
      setDailyLoaded(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [loadPrescriptions]);

  async function decidePrescription(id: string, action: "accept" | "dismiss") {
    setRxMsg("");
    setRxBusy(id);
    try {
      await apiSend("POST", `/api/dreams/prescriptions/${id}/decision`, { action });
      setPrescriptions((items) => items.filter((p) => p.id !== id));
      if (expandedRx === id) setExpandedRx(null);
    } catch (err: unknown) {
      const msg = err instanceof ApiError && !err.message.startsWith("Error ") ? err.message : "";
      setRxMsg(msg || "No se pudo registrar tu decisión. Intenta de nuevo.");
      await loadPrescriptions();
    } finally {
      setRxBusy(null);
    }
  }

  async function cancelReminder(id: string) {
    // Solo se quita de la lista si el servidor CONFIRMÓ la cancelación — un
    // recordatorio ligado a un plazo jamás debe "desaparecer" sin cancelarse.
    setReminderMsg("");
    try {
      await apiSend("POST", `/api/assistant/reminders/${id}/cancel`);
      setReminders((rs) => rs.filter((r) => r.id !== id));
    } catch {
      setReminderMsg("No se pudo cancelar el recordatorio. Intenta de nuevo.");
    }
  }

  // ── Lo que se sabe y lo que NO se pudo saber ──────────────────────────────
  // `null` significa "esa fuente no respondió", que NO es lo mismo que cero. El
  // Panel no convierte lo uno en lo otro en ningún sitio.
  const cifrasOk = s !== null;
  const propuestas = s?.proposals_pending ?? null;
  const activos = s?.matters_active ?? null;

  // Las dos colas que piden decisión del abogado. `null` = no respondió ninguna
  // de las dos fuentes; `parcial` = respondió una sola, así que el número que
  // se puede dar es un MÍNIMO y se dice como mínimo ("al menos N"), nunca como
  // el total.
  const decisiones =
    !mattersOk && propuestas === null ? null : pendingMatters.length + (propuestas ?? 0);
  const decisionesParcial = decisiones !== null && (!mattersOk || propuestas === null);
  const hayDecisiones = (decisiones ?? 0) > 0;

  // Subtítulo del encabezado, armado solo con lo que de verdad llegó.
  const subActivos =
    activos === null
      ? "No pude consultar cuántos asuntos tienes abiertos"
      : `${activos} ${activos === 1 ? "asunto activo" : "asuntos activos"}`;
  const subDecisiones =
    decisiones === null
      ? "no pude ver qué espera tu decisión"
      : hayDecisiones
        ? `${decisionesParcial ? "al menos " : ""}${decisiones} ${
            decisiones === 1 ? "decisión esperando" : "decisiones esperando"
          }`
        : decisionesParcial
          ? "no pude ver todo lo pendiente"
          : "nada espera tu decisión";

  // Los borradores esperando pueden ser de un proyecto: el botón de salida y el
  // rótulo tienen que llevar al sitio correcto, no siempre a Asuntos.
  const pendientesSoloProyectos =
    pendingMatters.length > 0 && pendingMatters.every((m) => m.kind === "proyecto");

  // Puesta a punto: solo lo que falta. Los pasos que el abogado OMITIÓ no se
  // insisten, y la sección entera desaparece cuando Mia ya está lista.
  const pasosPendientes = (setup?.pasos || []).filter((p) => p.estado === "pendiente");
  const setupCompleto = setup ? setup.completados >= setup.total : false;
  const mostrarSetup = Boolean(setup) && !setupCompleto && pasosPendientes.length > 0;

  // Guías: solo se habla de ellas cuando hay algo que verificar.
  const guiasPorRevisar = (health?.revisar || 0) + (health?.sin_revisar || 0);

  // Tareas que Mia corre sola. Se descartan las que el servidor aún no traduce
  // (ver `etiquetaLegible`): al abogado no se le enseña el nombre técnico de un
  // proceso, y una tarea sin nombre legible no aporta.
  const tareas = (s?.scheduler_jobs || []).filter((j) => etiquetaLegible(j.label));
  const proximaTarea = tareas
    .map((j) => j.next_run)
    .filter((d): d is string => Boolean(d))
    .sort()[0];

  // Tarjetas del mes: la del gasto solo existe si el dato llegó. Sin dato NO se
  // pinta un 0 — una cifra plausible es peor que una ausencia.
  const tarjetasMes = 3 + (budget ? 1 : 0);

  // Recorte de la lista del día: qué se dejó fuera por el tope y qué no
  // respondió. La sección aparece también cuando lo único que hay que contar es
  // eso — callarlo sería el recorte en silencio que aquí está prohibido.
  const dailyRecorte = Math.max(0, dailyTotal - DAILY_MAX);
  const dailyRevisados = Math.min(dailyTotal, DAILY_MAX);
  const mostrarDia =
    dailyLoaded && (dailyRows.length > 0 || dailyRecorte > 0 || dailySinRespuesta > 0);

  // Las filas de la lista principal. Se muestran las primeras seis —el resto
  // vive en Asuntos y en Proyectos, que es su sitio— y el recorte se dice con
  // números, nunca en silencio.
  const mattersVisibles = allMatters.slice(0, MATTERS_MAX);
  const mattersRecorte = Math.max(0, allMatters.length - MATTERS_MAX);

  return (
    <>
      {/* El lavado de marca va en una capa FIJA por detrás de todo: aplicado al
          contenedor con scroll, el degradado se iba con el contenido y la
          pantalla se destiñía al bajar. `pointer-events-none` para que no se
          coma ni un clic; `aria-hidden` porque no dice nada. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 bg-aurora" />

      <PageShell
        width="full"
        className="max-w-[1200px]"
        title="Panel del despacho"
        subtitle={loaded ? `${subActivos} · ${subDecisiones}` : "Reuniendo lo de hoy…"}
      >
        {!loaded ? (
          <PanelSkeleton />
        ) : (
          <>
            {/* ── Tope de gasto alcanzado ─────────────────────────────────
                Va lo primero, fuera de la rejilla y a todo el ancho, porque no
                es un aviso: mientras siga así, Mia no trabaja. */}
            {budget?.over_budget ? (
              <Card
                variant="raised"
                padding="md"
                className="mb-block animate-slide-up border-warning/30 bg-warning/10"
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div className="min-w-0">
                    <p className="text-body font-medium text-warning">
                      Se alcanzó el tope de gasto de este mes; los turnos están en pausa.
                    </p>
                    <Link
                      href="/configurar#valor"
                      className="mt-1.5 inline-block text-body font-medium text-warning underline underline-offset-2"
                    >
                      Ajustar el tope en Configuración
                    </Link>
                  </div>
                </div>
              </Card>
            ) : null}

            {/* ── LA REJILLA ──────────────────────────────────────────────
                Dos tercios de área principal y un tercio de carril lateral: las
                cifras del mes arriba, la lista de trabajo debajo, y a la derecha
                lo que espera una decisión y lo que Mia recuerda.

                LA USABILIDAD MANDA SOBRE LA MAQUETA. En la referencia el primer
                renglón es todo métrica; aquí el primer renglón de la derecha
                —a la misma altura que las cifras, o sea lo primero que el ojo
                encuentra— es "Para tu decisión", porque una métrica no se
                acciona y un borrador esperando sí. La rejilla es la misma; lo
                que cambia es qué ocupa el sitio de honor.

                `items-start` para que una celda alta no estire a su vecina; por
                debajo de `lg` la rejilla se apila y el orden del documento es el
                orden de importancia. */}
            <div className="grid items-start gap-block lg:grid-cols-3">
              {/* ── Área principal ────────────────────────────────────── */}
              <div className="flex flex-col gap-block lg:col-span-2">
                {/* Las cifras del mes. Se leen de un vistazo y sin decidir nada;
                    antes cerraban el Panel, a dos pantallas de scroll. */}
                <section aria-labelledby="panel-mes">
                  <h2 id="panel-mes" className="mb-3 text-section">
                    Lo que llevas este mes
                  </h2>

                  {/* Si las cifras no llegaron se dice UNA vez arriba, en llano
                      y sin alarma, y cada tarjeta queda marcada "sin dato". Lo
                      que no se hace nunca es rellenar con ceros: "0 borradores
                      aprobados" es una afirmación sobre el mes del abogado, no
                      una ausencia. */}
                  {!cifrasOk ? (
                    <p className="mb-3 text-pretty text-body text-muted-foreground">
                      No pude consultar las cifras de este mes ahora mismo. Vuelve a abrir el Panel
                      en un momento; lo que hayas hecho está guardado.
                    </p>
                  ) : null}

                  <div className={gridFor(tarjetasMes)}>
                    {/* HONESTIDAD DE MÉTRICAS (regla operativa §18: «toda métrica con
                        nombre evaluativo declara qué mide literalmente; la etiqueta es
                        parte de la métrica»). Las tres primeras etiquetas prometían más
                        de lo que el servidor cuenta, y la definición literal de cada una
                        está congelada en `validation/registro-metricas.json`:

                        · «Borradores aprobados» → el servidor NO sabe si los aprobaste:
                          cuenta los turnos del mes cuyo texto final es un escrito largo
                          (≥3.000 caracteres) y que no rechazaste. Ahora dice lo que mide.
                        · «Consultas resueltas» → «resuelta» es un juicio sobre el
                          resultado que nadie comprueba; lo que se cuenta es que Mia las
                          atendió y tú no las rechazaste.
                        · «Horas ahorradas» ya se declaraba estimada, pero sin decir según
                          qué. La base del cálculo va ahora en la propia tarjeta. */}
                    <StatCard
                      icon={CheckCircle2}
                      label="Escritos que Mia preparó"
                      value={s?.value?.drafts_approved}
                      nota="Textos largos que no rechazaste"
                      delay={0}
                    />
                    <StatCard
                      icon={Clock}
                      label="Horas ahorradas (estimado)"
                      value={s?.value?.hours_saved}
                      nota={
                        s?.value?.draft_minutes != null && s?.value?.turn_minutes != null
                          ? `Estimado: ${s.value.draft_minutes} min por escrito y ${s.value.turn_minutes} min por consulta`
                          : "Estimado según los minutos que configuraste por escrito y por consulta"
                      }
                      delay={1}
                    />
                    <StatCard
                      icon={MessageSquare}
                      label="Consultas atendidas"
                      value={s?.value?.consultations}
                      nota="Preguntas que Mia respondió y no rechazaste"
                      delay={2}
                    />
                    {budget ? (
                      <StatCard
                        icon={Wallet}
                        label="Gasto de IA del mes (USD)"
                        value={money(budget.spent_this_month_usd)}
                        nota="No incluye la indexación de documentos"
                        delay={3}
                      />
                    ) : null}
                  </div>

                  {/* La línea de apoyo de las cifras: qué significan en dinero y
                      dónde se ajusta el cálculo. Va debajo y visible, no
                      escondida tras un icono de ayuda. */}
                  <p className="mt-3 text-pretty text-body text-muted-foreground">
                    {s?.value?.net_usd != null
                      ? `Valor neto estimado: USD ${s.value.net_usd.toFixed(2)} — es una estimación: las horas ahorradas por tu tarifa, menos el gasto de IA del mes.`
                      : "Valor neto estimado: sin medir todavía, no pude consultar las cifras del mes."}
                    {budget?.unlimited ? " No tienes un tope de gasto fijado." : null}
                    {!budget?.unlimited && budget?.remaining_usd != null
                      ? ` Te quedan USD ${budget.remaining_usd.toFixed(2)} del tope de este mes.`
                      : null}{" "}
                    <Link
                      href="/configurar#valor"
                      className="font-medium text-primary underline underline-offset-2 hover:text-cta-strong"
                    >
                      Ajustar el cálculo
                    </Link>
                  </p>
                </section>

                {/* ── Tu trabajo abierto ──────────────────────────────────
                    La celda grande de la maqueta. No es una fuente nueva: es la
                    MISMA lista que el Panel ya pedía y de la que solo se quedaba
                    con el filtro de los borradores. Cada fila es un enlace
                    entero —objetivo de clic generoso, no un texto de 3 mm— y
                    lleva su icono en bajo relieve, su tipo en el idioma del
                    oficio y su distintivo a la derecha. */}
                <PanelCard
                  icon={Folder}
                  title="Tu trabajo abierto"
                  hint="Tus asuntos y proyectos. Abre cualquiera para ver su expediente."
                  tone="primary"
                  className="animate-slide-up"
                  actions={
                    allMatters.length > 0 ? (
                      <Button asChild size="sm" variant="ghost" className="gap-1.5">
                        <Link href="/">
                          Ver todos
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    ) : null
                  }
                >
                  {!mattersOk ? (
                    <p className="text-pretty text-body text-muted-foreground">
                      No pude consultar tus asuntos y proyectos ahora mismo. Vuelve a abrir el Panel
                      en un momento.
                    </p>
                  ) : allMatters.length === 0 ? (
                    <EmptyHint icon={Folder}>
                      Todavía no tienes asuntos ni proyectos abiertos. Crea el primero y Mia empieza
                      a leer su expediente.{" "}
                      <Link
                        href="/"
                        className="font-medium text-primary underline underline-offset-2"
                      >
                        Crear mi primer asunto
                      </Link>
                    </EmptyHint>
                  ) : (
                    <>
                      <ul className="space-y-2">
                        {mattersVisibles.map((m, i) => (
                          <li key={m.id}>
                            <Link
                              href={rutaDe(m)}
                              className={`group flex items-center gap-3 py-3.5 transition-colors hover:bg-muted/70 ${FILA}`}
                              style={staggerStyle(i)}
                            >
                              <NeuIcon
                                icon={m.kind === "proyecto" ? Layers : Folder}
                                tone={m.pending_review ? "cta" : "primary"}
                                size="sm"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-body font-medium text-foreground group-hover:text-primary">
                                  {m.name}
                                </span>
                                <span className="mt-0.5 block truncate text-body text-muted-foreground">
                                  {tipoDe(m)}
                                  {m.status === "active" ? " · en curso" : null}
                                </span>
                              </span>
                              {m.pending_review ? (
                                <Badge className="shrink-0 border-cta/30 bg-cta/15 text-cta-strong">
                                  Borrador para revisar
                                </Badge>
                              ) : null}
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                            </Link>
                          </li>
                        ))}
                      </ul>
                      {mattersRecorte > 0 ? (
                        <p className="mt-3 text-pretty text-body text-muted-foreground">
                          Se muestran {mattersVisibles.length} de {allMatters.length}. Los ves todos
                          en{" "}
                          <Link
                            href="/"
                            className="font-medium text-primary underline underline-offset-2"
                          >
                            Asuntos
                          </Link>{" "}
                          y{" "}
                          <Link
                            href="/proyectos"
                            className="font-medium text-primary underline underline-offset-2"
                          >
                            Proyectos
                          </Link>
                          .
                        </p>
                      ) : null}
                    </>
                  )}
                </PanelCard>

                {/* ── Recomendaciones de Mia ──────────────────────────── */}
                <PanelCard
                  icon={Sparkles}
                  title="Recomendaciones de Mia"
                  hint="Del diagnóstico semanal, con evidencia real de la actividad del despacho."
                  tone="primary"
                  className="animate-slide-up"
                  style={staggerStyle(2)}
                >
                  {rxMsg ? (
                    <p
                      role="alert"
                      className="mb-3 rounded-md bg-warning/10 px-3 py-2 text-body text-warning"
                    >
                      {rxMsg}
                    </p>
                  ) : null}
                  {!prescriptionsLoaded ? (
                    <Skeleton className="h-24 w-full rounded-lg" />
                  ) : prescriptions.length === 0 ? (
                    <EmptyHint icon={Sparkles}>
                      Mia aún no tiene recomendaciones — necesita más actividad para hablar con
                      evidencia. Sigue trabajando con ella y aquí aparecerán.
                    </EmptyHint>
                  ) : (
                    <ul className="space-y-3">
                      {prescriptions.map((p) => {
                        const expanded = expandedRx === p.id;
                        return (
                          <li key={p.id} className={FILA}>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-section">{p.headline}</span>
                                {p.status === "recurring" && p.age_days > 0 ? (
                                  <Badge variant="warning" className="bg-warning/15 text-warning">
                                    Recurrente · {p.age_days} {p.age_days === 1 ? "día" : "días"}
                                  </Badge>
                                ) : null}
                              </div>
                              <p className="mt-2 text-pretty text-body text-muted-foreground">
                                {p.prescription}
                              </p>
                              {p.dollar_impact != null || p.time_impact_mins != null ? (
                                <p className="mt-2 text-body font-medium text-primary">
                                  {p.dollar_impact != null
                                    ? `Impacto estimado: USD ${p.dollar_impact.toFixed(0)}/mes`
                                    : null}
                                  {p.dollar_impact != null && p.time_impact_mins != null
                                    ? " · "
                                    : null}
                                  {p.time_impact_mins != null
                                    ? `${p.time_impact_mins} min/mes ahorrables`
                                    : null}
                                </p>
                              ) : null}
                            </div>
                            {p.evidence?.length ? (
                              <div className="mt-3">
                                <button
                                  type="button"
                                  aria-expanded={expanded}
                                  onClick={() => setExpandedRx(expanded ? null : p.id)}
                                  className="text-body font-medium text-muted-foreground underline underline-offset-2 transition-colors hover:text-foreground"
                                >
                                  {expanded ? "Ocultar en qué me baso" : "Ver en qué me baso"}
                                </button>
                                {expanded ? (
                                  <ul className="mt-2 animate-fade-in space-y-1 rounded-md bg-background/60 px-3 py-2 text-body text-muted-foreground">
                                    {p.evidence.map((line, j) => (
                                      <li key={j}>· {line}</li>
                                    ))}
                                  </ul>
                                ) : null}
                              </div>
                            ) : null}
                            <div className="mt-4 flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                onClick={() => decidePrescription(p.id, "accept")}
                                disabled={rxBusy === p.id}
                              >
                                Lo haré
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => decidePrescription(p.id, "dismiss")}
                                disabled={rxBusy === p.id}
                              >
                                Descartar
                              </Button>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </PanelCard>
              </div>

              {/* ── Carril lateral ────────────────────────────────────────
                  Lo que espera una decisión suya y lo que Mia le recuerda. */}
              <aside className="flex flex-col gap-block">
                {/* Para tu decisión · SIEMPRE presente y en el sitio de honor.
                    Antes desaparecía entera cuando no había nada, y ese hueco
                    era buena parte de la sensación de vacío: "no hay nada
                    pendiente" es una respuesta, no una ausencia. */}
                <PanelCard
                  icon={hayDecisiones ? ListChecks : CheckCircle2}
                  title="Para tu decisión"
                  hint={
                    hayDecisiones
                      ? "Lo único de este panel que no avanza sin ti."
                      : undefined
                  }
                  tone={hayDecisiones ? "cta" : "muted"}
                  emphasis
                  className="animate-slide-up"
                >
                  {/* "Nada espera tu decisión" solo se afirma cuando se pudo
                      comprobar. Si alguna fuente no respondió, se dice eso: es
                      la diferencia entre un despacho al día y un Panel ciego. */}
                  {decisiones === 0 && !decisionesParcial ? (
                    <p className="text-pretty text-body text-muted-foreground">
                      Nada espera tu decisión hoy. Cuando Mia deje un borrador listo o tenga una
                      sugerencia para tu despacho, aparecerá aquí.
                    </p>
                  ) : null}

                  {decisiones === null || decisionesParcial ? (
                    <p className="text-pretty text-body text-muted-foreground">
                      {decisiones === null
                        ? "No pude consultar qué espera tu decisión ahora mismo."
                        : "No pude consultar una parte de lo pendiente, así que esta lista puede estar incompleta."}{" "}
                      Vuelve a abrir el Panel en un momento.
                    </p>
                  ) : null}

                  {pendingMatters.length > 0 ? (
                    <>
                      <p className="text-pretty text-body text-muted-foreground">
                        {pendingMatters.length === 1
                          ? "Tienes un borrador esperando tu revisión:"
                          : `Tienes ${pendingMatters.length} borradores esperando tu revisión:`}
                      </p>
                      <ul className="mt-3 space-y-2">
                        {pendingMatters.slice(0, 5).map((m) => (
                          <li key={m.id}>
                            <Link
                              href={rutaRevisar(m)}
                              className={`group flex items-center gap-3 py-3.5 text-body font-medium text-foreground transition-colors hover:bg-muted/70 hover:text-primary ${FILA}`}
                            >
                              <span className="min-w-0 flex-1">
                                <span className="block truncate">{m.name}</span>
                                <span className="mt-0.5 block text-body font-normal text-muted-foreground">
                                  Revisar el borrador
                                </span>
                              </span>
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                            </Link>
                          </li>
                        ))}
                      </ul>
                      {pendingMatters.length > 5 ? (
                        <p className="mt-2 text-body text-muted-foreground">
                          Se muestran los primeros 5 de {pendingMatters.length}.
                        </p>
                      ) : null}
                    </>
                  ) : null}

                  {(propuestas ?? 0) > 0 ? (
                    <p
                      className={`${pendingMatters.length > 0 ? "mt-3" : ""} text-pretty text-body text-muted-foreground`}
                    >
                      {pendingMatters.length > 0 ? "Además, " : ""}Mia tiene {propuestas}{" "}
                      {propuestas === 1 ? "sugerencia de mejora" : "sugerencias de mejora"} para tu
                      aprobación en{" "}
                      <Link
                        href="/memoria"
                        className="font-medium text-foreground underline underline-offset-2 hover:text-primary"
                      >
                        Conocimiento
                      </Link>
                      .
                    </p>
                  ) : null}

                  {pendingMatters.length > 0 ? (
                    <Button asChild variant="cta" size="sm" className="mt-4 gap-1.5">
                      <Link href={pendientesSoloProyectos ? "/proyectos" : "/"}>
                        {pendientesSoloProyectos ? "Ver proyectos" : "Ver asuntos"}
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  ) : null}
                </PanelCard>

                {/* Recordatorios · las fechas del despacho. */}
                <PanelCard
                  icon={CalendarClock}
                  title="Recordatorios"
                  hint="Lo que pediste que Mia no dejara pasar."
                  tone="primary"
                  className="animate-slide-up"
                  style={staggerStyle(1)}
                >
                  {reminderMsg ? (
                    <p className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-body text-warning">
                      {reminderMsg}
                    </p>
                  ) : null}
                  {reminders.length === 0 ? (
                    <EmptyHint icon={BellRing}>
                      No tienes recordatorios pendientes. Pídelos en{" "}
                      <Link
                        href="/chat"
                        className="font-medium text-primary underline underline-offset-2"
                      >
                        el chat
                      </Link>
                      : «recuérdame presentar la contestación mañana a las 9».
                    </EmptyHint>
                  ) : (
                    <ul className="space-y-2">
                      {reminders.map((r, i) => (
                        <li
                          key={r.id}
                          className={`flex items-start gap-3 ${FILA}`}
                          style={staggerStyle(i)}
                        >
                          <NeuIcon
                            icon={BellRing}
                            tone={r.is_procedural ? "warning" : "primary"}
                            size="sm"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="text-pretty text-body font-medium">{r.text}</div>
                            <div className="mt-0.5 text-pretty text-body text-muted-foreground">
                              Para el {fmtHora(r.due_at)}
                              {r.is_procedural ? (
                                <span className="ml-1.5 font-medium text-warning">
                                  · plazo procesal: confirma tú la fecha
                                </span>
                              ) : null}
                            </div>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="-ml-2 mt-1"
                              onClick={() => cancelReminder(r.id)}
                            >
                              Cancelar
                            </Button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </PanelCard>

                {/* Al día en tu trabajo · Este resumen ya existía, pero enterrado
                    tras un botón DENTRO de cada asunto: el abogado tenía que
                    entrar uno por uno para enterarse. Sale del expediente y no
                    pasa por ningún modelo, así que ninguna línea de aquí es una
                    afirmación generada.

                    El rótulo dice "tu trabajo" y no "tus asuntos" porque la lista
                    trae asuntos Y proyectos: llamarlos a todos asuntos borraría
                    justo la distinción que el producto sostiene. */}
                {mostrarDia ? (
                  <PanelCard
                    icon={ListChecks}
                    title="Al día en tu trabajo"
                    hint="Lo que quedó abierto y espera algo tuyo."
                    tone="primary"
                    className="animate-slide-up"
                    style={staggerStyle(2)}
                  >
                    <ul className="space-y-3">
                      {dailyRows.map((row) => (
                        <li key={row.matter.id} className={FILA}>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <Link
                              href={rutaDe(row.matter)}
                              className="group flex min-w-0 items-center gap-1.5 text-body font-medium hover:text-primary"
                            >
                              <span className="truncate">{row.matter.name}</span>
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                            </Link>
                            <Badge variant="warning" className="bg-warning/15 text-warning">
                              {row.briefing.requieren_decision}{" "}
                              {row.briefing.requieren_decision === 1 ? "pendiente" : "pendientes"}
                            </Badge>
                          </div>
                          <ul className="mt-2 space-y-1.5">
                            {row.briefing.items
                              .filter((it) => it.requiere_decision)
                              .slice(0, 4)
                              .map((it) => (
                                <li
                                  key={it.ref}
                                  className="text-pretty text-body text-muted-foreground"
                                >
                                  · {it.texto}
                                </li>
                              ))}
                          </ul>
                        </li>
                      ))}
                    </ul>

                    {/* Cuando el tope dejó fuera trabajo pero nada de lo revisado
                        pedía algo, la celda seguiría teniendo que existir: si no,
                        el recorte desaparecería con ella. */}
                    {dailyRows.length === 0 ? (
                      <p className="text-pretty text-body text-muted-foreground">
                        De lo que alcancé a mirar, nada espera algo tuyo.
                      </p>
                    ) : null}

                    {/* EL RECORTE SE DICE CON NÚMEROS. Antes esta línea se
                        condicionaba a `matters_active`, que el servidor cuenta
                        solo sobre asuntos, mientras la lista recortada eran
                        asuntos + proyectos: con 3 asuntos y 4 proyectos activos
                        el Panel mostraba 5 y ocultaba 2 sin decir nada. Ahora la
                        condición y la cifra salen de la MISMA lista recortada. */}
                    {dailyRecorte > 0 ? (
                      <p className="mt-3 text-pretty text-body text-muted-foreground">
                        Tienes {dailyTotal} asuntos y proyectos abiertos: aquí se miran los{" "}
                        {dailyRevisados} más recientes y quedan {dailyRecorte} sin mirar.
                      </p>
                    ) : null}

                    {dailySinRespuesta > 0 ? (
                      <p className="mt-2 text-pretty text-body text-muted-foreground">
                        De los {dailyRevisados} que miré,{" "}
                        {dailySinRespuesta === 1
                          ? "1 no respondió ahora mismo"
                          : `${dailySinRespuesta} no respondieron ahora mismo`}
                        , así que puede faltar algo en esta lista.
                      </p>
                    ) : null}
                  </PanelCard>
                ) : null}

                {/* Termina de preparar a Mia · El servidor ya redacta el título,
                    el detalle y el enlace de cada paso en lenguaje llano: aquí no
                    se inventa ni una palabra, se pinta lo que manda. Desaparece
                    sola al terminar. */}
                {mostrarSetup ? (
                  <PanelCard
                    icon={Compass}
                    title="Termina de preparar a Mia"
                    hint={setup?.mensaje}
                    tone="primary"
                    className="animate-slide-up"
                    style={staggerStyle(3)}
                  >
                    <ul className="space-y-2">
                      {pasosPendientes.map((paso) => (
                        <li key={paso.id} className={FILA}>
                          <div className="min-w-0">
                            <div className="text-body font-medium">{paso.titulo}</div>
                            <p className="mt-0.5 text-pretty text-body text-muted-foreground">
                              {paso.detalle}
                            </p>
                          </div>
                          {paso.enlace ? (
                            <Button asChild size="sm" variant="secondary" className="mt-3 gap-1.5">
                              <Link href={paso.enlace}>
                                Ir al paso
                                <ArrowRight className="h-3.5 w-3.5" />
                              </Link>
                            </Button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-pretty text-body text-muted-foreground">
                      Todo es opcional y puedes retomarlo cuando quieras desde{" "}
                      <Link
                        href="/configurar"
                        className="font-medium text-primary underline underline-offset-2"
                      >
                        Configuración
                      </Link>
                      .
                    </p>
                  </PanelCard>
                ) : null}

                {/* Tus guías de trabajo · Solo aparece si hay algo que verificar:
                    es la regla de la casa (ninguna cita sin verificación)
                    convertida en tarjeta. */}
                {guiasPorRevisar > 0 ? (
                  <PanelCard
                    icon={BookOpen}
                    title="Tus guías de trabajo"
                    tone="primary"
                    className="animate-slide-up"
                    style={staggerStyle(4)}
                  >
                    <p className="text-pretty text-body">
                      {health?.revisar ? (
                        <>
                          <span className="font-medium">
                            {health.revisar} {health.revisar === 1 ? "guía" : "guías"}
                          </span>{" "}
                          {health.revisar === 1 ? "tiene" : "tienen"} citas por verificar
                          {health?.sin_revisar ? " y " : "."}
                        </>
                      ) : null}
                      {health?.sin_revisar ? (
                        <>
                          <span className="font-medium">
                            {health.sin_revisar} {health.sin_revisar === 1 ? "guía" : "guías"}
                          </span>{" "}
                          {health.sin_revisar === 1 ? "no se ha revisado" : "no se han revisado"}{" "}
                          nunca.
                        </>
                      ) : null}
                    </p>
                    <p className="mt-1 text-pretty text-body text-muted-foreground">
                      Mia no usa una cita que no haya podido comprobar: revisarlas mejora lo que
                      redacta.
                    </p>
                    <Button asChild size="sm" variant="secondary" className="mt-4 gap-1.5">
                      <Link href="/memoria">
                        Revisar mis guías
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  </PanelCard>
                ) : null}

                {/* Lo que Mia hace sola, en una línea discreta al pie del carril:
                    es tranquilizador saber que hay algo corriendo, pero no es
                    trabajo del abogado y no merece una celda propia. */}
                {tareas.length > 0 ? (
                  <p className="px-1 text-pretty text-meta text-muted-foreground">
                    Mia trabaja en segundo plano: {tareas.length}{" "}
                    {tareas.length === 1 ? "tarea programada" : "tareas programadas"}
                    {proximaTarea ? ` · la próxima, el ${fmtHora(proximaTarea)}` : null}.
                  </p>
                ) : null}
              </aside>
            </div>
          </>
        )}
      </PageShell>
    </>
  );
}
