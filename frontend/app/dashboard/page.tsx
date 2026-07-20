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
  BarChart3,
  BellRing,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
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
import { EmptyHint, SectionTitle, StatCard, fmtHora } from "@/app/_components/PanelUI";
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
 * Rejilla que se adapta al número REAL de tarjetas.
 *
 * El defecto que corrige: había dos rejillas declaradas `sm:grid-cols-4` con
 * dos hijos, así que desde 640px de ancho el Panel pintaba dos celdas vacías,
 * dos veces. Media pantalla en blanco no era falta de datos: era una rejilla
 * pidiendo cuatro columnas para dos cosas. Las clases van literales para que
 * el compilador de Tailwind las encuentre al escanear el archivo.
 */
function gridFor(count: number): string {
  if (count <= 1) return "grid gap-4";
  if (count === 2) return "grid gap-4 sm:grid-cols-2";
  if (count === 3) return "grid gap-4 sm:grid-cols-2 lg:grid-cols-3";
  return "grid gap-4 sm:grid-cols-2 lg:grid-cols-4";
}

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
 * layout al cargar. Estas piezas ocupan el sitio del bloque de decisión, de dos
 * listas y de la rejilla del mes, que es lo que de verdad aparece después.
 */
function PanelSkeleton() {
  return (
    <div className="space-y-section">
      <Skeleton className="h-28 w-full rounded-lg" />
      <div className="space-y-4">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-7 w-56" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
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

  return (
    <>
      {/* El lavado de marca va en una capa FIJA por detrás de todo: aplicado al
          contenedor con scroll, el degradado se iba con el contenido y la
          pantalla se destiñía al bajar. `pointer-events-none` para que no se
          coma ni un clic; `aria-hidden` porque no dice nada. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 bg-aurora" />

      <PageShell
        width="wide"
        title="Panel del despacho"
        subtitle={loaded ? `${subActivos} · ${subDecisiones}` : "Reuniendo lo de hoy…"}
      >
        {!loaded ? (
          <PanelSkeleton />
        ) : (
          <>
            {/* ── Tope de gasto alcanzado ─────────────────────────────────
                Va lo primero porque no es un aviso: mientras siga así, Mia
                no trabaja. */}
            {budget?.over_budget ? (
              <Card
                variant="raised"
                padding="md"
                className="mb-section animate-slide-up border-warning/30 bg-warning/10"
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

            {/* ── 1 · Para tu decisión ────────────────────────────────────
                SIEMPRE presente. Antes desaparecía entera cuando no había
                nada, y ese hueco era buena parte de la sensación de vacío:
                "no hay nada pendiente" es una respuesta, no una ausencia. */}
            <Card
              variant="raised"
              padding="md"
              className={`animate-slide-up ${hayDecisiones ? "border-cta/30 bg-cta/5" : ""}`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
                    hayDecisiones ? "bg-cta/15 text-cta-strong" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {hayDecisiones ? (
                    <ListChecks className="h-4 w-4" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                </span>

                <div className="min-w-0 flex-1">
                  <h2 className="text-section">Para tu decisión</h2>

                  {/* "Nada espera tu decisión" solo se afirma cuando se pudo
                      comprobar. Si alguna fuente no respondió, se dice eso: es
                      la diferencia entre un despacho al día y un Panel ciego. */}
                  {decisiones === 0 && !decisionesParcial ? (
                    <p className="mt-1 text-pretty text-body text-muted-foreground">
                      Nada espera tu decisión hoy. Cuando Mia deje un borrador listo o tenga una
                      sugerencia para tu despacho, aparecerá aquí.
                    </p>
                  ) : null}

                  {decisiones === null || decisionesParcial ? (
                    <p className="mt-1 text-pretty text-body text-muted-foreground">
                      {decisiones === null
                        ? "No pude consultar qué espera tu decisión ahora mismo."
                        : "No pude consultar una parte de lo pendiente, así que esta lista puede estar incompleta."}{" "}
                      Vuelve a abrir el Panel en un momento.
                    </p>
                  ) : null}

                  {pendingMatters.length > 0 ? (
                    <>
                      <p className="mt-1 text-body text-muted-foreground">
                        {pendingMatters.length === 1
                          ? "Tienes un borrador esperando tu revisión:"
                          : `Tienes ${pendingMatters.length} borradores esperando tu revisión:`}
                      </p>
                      <ul className="mt-2 space-y-1.5">
                        {pendingMatters.slice(0, 5).map((m) => (
                          <li key={m.id}>
                            <Link
                              href={rutaRevisar(m)}
                              className="group flex items-center gap-1.5 text-body font-medium text-foreground hover:text-primary"
                            >
                              {m.name}
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                            </Link>
                          </li>
                        ))}
                      </ul>
                      {pendingMatters.length > 5 ? (
                        <p className="mt-1.5 text-meta text-muted-foreground">
                          Se muestran los primeros 5 de {pendingMatters.length}.
                        </p>
                      ) : null}
                    </>
                  ) : null}

                  {(propuestas ?? 0) > 0 ? (
                    <p
                      className={`${pendingMatters.length > 0 ? "mt-3" : "mt-1"} text-body text-muted-foreground`}
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
                </div>
              </div>
            </Card>

            {/* ── 2 · Al día en tu trabajo ────────────────────────────────
                Este resumen ya existía, pero enterrado tras un botón DENTRO
                de cada asunto: el abogado tenía que entrar uno por uno para
                enterarse. Sale del expediente y no pasa por ningún modelo,
                así que ninguna línea de aquí es una afirmación generada.

                El rótulo dice "tu trabajo" y no "tus asuntos" porque la lista
                trae asuntos Y proyectos: llamarlos a todos asuntos borraría
                justo la distinción que el producto sostiene. */}
            {mostrarDia ? (
              <section className="mt-section">
                <SectionTitle
                  icon={CalendarClock}
                  title="Al día en tu trabajo"
                  hint="Lo que quedó abierto en tus asuntos y proyectos y espera algo tuyo."
                />
                <ul className="space-y-3">
                  {dailyRows.map((row, i) => (
                    <li key={row.matter.id}>
                      <Card padding="md" className="animate-slide-up" style={staggerStyle(i)}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Link
                            href={rutaDe(row.matter)}
                            className="group flex min-w-0 items-center gap-1.5 text-section hover:text-primary"
                          >
                            <span className="truncate">{row.matter.name}</span>
                            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                          </Link>
                          <Badge variant="warning" className="bg-warning/15 text-warning">
                            {row.briefing.requieren_decision}{" "}
                            {row.briefing.requieren_decision === 1 ? "pendiente" : "pendientes"}
                          </Badge>
                        </div>
                        <ul className="mt-3 space-y-1.5">
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
                      </Card>
                    </li>
                  ))}
                </ul>

                {/* Cuando el tope dejó fuera trabajo pero nada de lo revisado
                    pedía algo, la sección seguiría teniendo que existir: si no,
                    el recorte desaparecería con ella. */}
                {dailyRows.length === 0 ? (
                  <p className="text-pretty text-body text-muted-foreground">
                    De lo que alcancé a mirar, nada espera algo tuyo.
                  </p>
                ) : null}

                {/* EL RECORTE SE DICE CON NÚMEROS. Antes esta línea se
                    condicionaba a `matters_active`, que el servidor cuenta solo
                    sobre asuntos, mientras la lista recortada eran asuntos +
                    proyectos: con 3 asuntos y 4 proyectos activos el Panel
                    mostraba 5 y ocultaba 2 sin decir nada. Ahora la condición y
                    la cifra salen de la MISMA lista que se recortó. */}
                {dailyRecorte > 0 ? (
                  <p className="mt-3 text-pretty text-meta text-muted-foreground">
                    Tienes {dailyTotal} asuntos y proyectos abiertos: aquí se miran los{" "}
                    {dailyRevisados} más recientes y quedan {dailyRecorte} sin mirar. Los ves todos
                    en{" "}
                    <Link href="/" className="font-medium hover:underline">
                      Asuntos
                    </Link>{" "}
                    y{" "}
                    <Link href="/proyectos" className="font-medium hover:underline">
                      Proyectos
                    </Link>
                    .
                  </p>
                ) : null}

                {dailySinRespuesta > 0 ? (
                  <p className="mt-2 text-pretty text-meta text-muted-foreground">
                    De los {dailyRevisados} que miré,{" "}
                    {dailySinRespuesta === 1
                      ? "1 no respondió ahora mismo"
                      : `${dailySinRespuesta} no respondieron ahora mismo`}
                    , así que puede faltar algo en esta lista.
                  </p>
                ) : null}
              </section>
            ) : null}

            {/* ── 3 · Recordatorios ───────────────────────────────────── */}
            <section className="mt-section">
              <SectionTitle icon={BellRing} title="Recordatorios" />
              {reminderMsg ? (
                <p className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-body text-warning">
                  {reminderMsg}
                </p>
              ) : null}
              {reminders.length === 0 ? (
                <EmptyHint icon={BellRing}>
                  No tienes recordatorios pendientes. Pídelos en el chat: «recuérdame presentar la
                  contestación mañana a las 9».
                </EmptyHint>
              ) : (
                <ul className="space-y-2">
                  {reminders.map((r, i) => (
                    <li key={r.id}>
                      <Card
                        padding="sm"
                        className="flex animate-slide-up items-center justify-between gap-3"
                        style={staggerStyle(i)}
                      >
                        <div className="min-w-0">
                          <div className="truncate text-body font-medium">{r.text}</div>
                          <div className="mt-0.5 text-body text-muted-foreground">
                            Para el {fmtHora(r.due_at)}
                            {r.is_procedural ? (
                              <span className="ml-1.5 font-medium text-warning">
                                · plazo procesal: confirma tú la fecha
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="shrink-0"
                          onClick={() => cancelReminder(r.id)}
                        >
                          Cancelar
                        </Button>
                      </Card>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* ── 4 · Termina de preparar a Mia ───────────────────────────
                El servidor ya redacta el título, el detalle y el enlace de
                cada paso en lenguaje llano: aquí no se inventa ni una
                palabra, se pinta lo que manda. Desaparece sola al terminar. */}
            {mostrarSetup ? (
              <section className="mt-section">
                <SectionTitle
                  icon={Compass}
                  title="Termina de preparar a Mia"
                  hint={setup?.mensaje}
                />
                <ul className="space-y-2">
                  {pasosPendientes.map((paso, i) => (
                    <li key={paso.id}>
                      <Card
                        padding="sm"
                        className="flex animate-slide-up flex-wrap items-center justify-between gap-3"
                        style={staggerStyle(i)}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="text-body font-medium">{paso.titulo}</div>
                          <p className="mt-0.5 text-pretty text-body text-muted-foreground">
                            {paso.detalle}
                          </p>
                        </div>
                        {paso.enlace ? (
                          <Button asChild size="sm" variant="secondary" className="shrink-0 gap-1.5">
                            <Link href={paso.enlace}>
                              Ir al paso
                              <ArrowRight className="h-3.5 w-3.5" />
                            </Link>
                          </Button>
                        ) : null}
                      </Card>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-meta text-muted-foreground">
                  Todo es opcional y puedes retomarlo cuando quieras desde{" "}
                  <Link href="/configurar" className="font-medium hover:underline">
                    Configuración
                  </Link>
                  .
                </p>
              </section>
            ) : null}

            {/* ── 5 · Tus guías de trabajo ────────────────────────────────
                Solo aparece si hay algo que verificar: es la regla de la casa
                (ninguna cita sin verificación) convertida en tarjeta. */}
            {guiasPorRevisar > 0 ? (
              <section className="mt-section">
                <SectionTitle icon={BookOpen} title="Tus guías de trabajo" />
                <Card padding="md" className="animate-slide-up">
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
                        {health.sin_revisar === 1 ? "no se ha revisado" : "no se han revisado"} nunca.
                      </>
                    ) : null}
                  </p>
                  <p className="mt-1 text-body text-muted-foreground">
                    Mia no usa una cita que no haya podido comprobar: revisarlas mejora lo que
                    redacta.
                  </p>
                  <Button asChild size="sm" variant="secondary" className="mt-4 gap-1.5">
                    <Link href="/memoria">
                      Revisar mis guías
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </Button>
                </Card>
              </section>
            ) : null}

            {/* ── 6 · Recomendaciones de Mia ──────────────────────────── */}
            <section className="mt-section">
              <SectionTitle
                icon={Sparkles}
                title="Recomendaciones de Mia"
                hint="Del diagnóstico semanal, con evidencia real de la actividad del despacho."
              />
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
                  evidencia.
                </EmptyHint>
              ) : (
                <ul className="space-y-3">
                  {prescriptions.map((p, i) => {
                    const expanded = expandedRx === p.id;
                    return (
                      <li key={p.id}>
                        <Card padding="md" className="animate-slide-up" style={staggerStyle(i)}>
                          <div className="flex flex-wrap items-start justify-between gap-3">
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
                          </div>
                          {p.evidence?.length ? (
                            <div className="mt-3">
                              <button
                                type="button"
                                aria-expanded={expanded}
                                onClick={() => setExpandedRx(expanded ? null : p.id)}
                                className="text-label text-muted-foreground transition-colors hover:text-foreground"
                              >
                                {expanded ? "Ocultar evidencia" : "Ver evidencia"}
                              </button>
                              {expanded ? (
                                <ul className="mt-2 animate-fade-in space-y-1 rounded-md bg-muted/60 px-3 py-2 text-body text-muted-foreground">
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
                        </Card>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {/* ── 7 · Este mes (lo informativo, al final) ─────────────────
                Se retiró la rejilla "En el despacho": "asuntos activos" ya se
                dice en el encabezado y "documentos" es un total, no algo del
                mes — mezclarlo aquí le haría leer al abogado una cifra
                mensual que no lo es. Queda UNA rejilla, llena de verdad. */}
            <section className="mt-section">
              <SectionTitle icon={BarChart3} title="Este mes" />

              {/* Si las cifras no llegaron se dice UNA vez arriba, en llano y
                  sin alarma, y cada tarjeta queda marcada "sin dato". Lo que no
                  se hace nunca es rellenar con ceros: "0 borradores aprobados"
                  es una afirmación sobre el mes del abogado, no una ausencia. */}
              {!cifrasOk ? (
                <p className="mb-3 text-pretty text-body text-muted-foreground">
                  No pude consultar las cifras de este mes ahora mismo. Vuelve a abrir el Panel en
                  un momento; lo que hayas hecho está guardado.
                </p>
              ) : null}

              <div className={gridFor(tarjetasMes)}>
                <StatCard
                  icon={CheckCircle2}
                  label="Borradores aprobados"
                  value={s?.value?.drafts_approved}
                  delay={0}
                />
                <StatCard
                  icon={Clock}
                  label="Horas ahorradas (estimado)"
                  value={s?.value?.hours_saved}
                  delay={1}
                />
                <StatCard
                  icon={MessageSquare}
                  label="Consultas resueltas"
                  value={s?.value?.consultations}
                  delay={2}
                />
                {budget ? (
                  <StatCard
                    icon={Wallet}
                    label="Gasto de IA del mes (USD)"
                    value={money(budget.spent_this_month_usd)}
                    delay={3}
                  />
                ) : null}
              </div>

              <p className="mt-3 text-pretty text-body text-muted-foreground">
                {s?.value?.net_usd != null
                  ? `Valor neto estimado: USD ${s.value.net_usd.toFixed(2)}.`
                  : "Valor neto estimado: sin dato ahora mismo."}
                {budget?.unlimited ? " No tienes un tope de gasto fijado." : null}
                {!budget?.unlimited && budget?.remaining_usd != null
                  ? ` Te quedan USD ${budget.remaining_usd.toFixed(2)} del tope de este mes.`
                  : null}{" "}
                <Link href="/configurar#valor" className="font-medium text-primary hover:underline">
                  Ajustar el cálculo en Configuración
                </Link>
              </p>

              {/* Lo que Mia hace sola, en una línea discreta: es tranquilizador
                  saber que hay algo corriendo, pero no es trabajo del abogado. */}
              {tareas.length > 0 ? (
                <p className="mt-2 text-meta text-muted-foreground">
                  Mia trabaja en segundo plano: {tareas.length}{" "}
                  {tareas.length === 1 ? "tarea programada" : "tareas programadas"}
                  {proximaTarea ? ` · la próxima, el ${fmtHora(proximaTarea)}` : null}.
                </p>
              ) : null}
            </section>
          </>
        )}
      </PageShell>
    </>
  );
}
