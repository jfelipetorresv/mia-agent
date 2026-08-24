"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet, apiSend, plainMessage, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  WelcomeShell,
  WelcomeHero,
  StepTransition,
  Stagger,
  WelcomeField,
  MiaLine,
} from "@/app/_welcome";

type AuthResponse = { token: string; tenant_id: string };

// La portada se muestra una sola vez por sesión de navegación: si el abogado la
// omite (o vuelve a /login desde el registro), no se le vuelve a interponer.
const HERO_VISTO_KEY = "mia-portada-vista";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Portada cinematográfica de bienvenida (pack de diseño, encargo de Pipe
  // 2026-08-24): la primera pantalla del abogado recién instalado es el hero,
  // no el formulario de entrada. "Primera vez" = este equipo aún no tiene
  // ningún despacho creado (`hay_usuario` de /api/welcome/status, endpoint
  // público). Si el estado no se puede consultar o ya hay usuario, se muestra
  // el formulario de siempre: la portada jamás bloquea la entrada.
  const [hero, setHero] = useState<"comprobando" | "mostrar" | "no">(() => {
    if (typeof window !== "undefined" && sessionStorage.getItem(HERO_VISTO_KEY)) return "no";
    return "comprobando";
  });

  useEffect(() => {
    if (hero !== "comprobando") return;
    let cancelled = false;
    (async () => {
      try {
        const st = await apiGet<{ hay_usuario: boolean }>("/api/welcome/status");
        if (!cancelled) setHero(st.hay_usuario ? "no" : "mostrar");
      } catch {
        if (!cancelled) setHero("no");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hero]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await apiSend<AuthResponse>("POST", "/api/auth/login", { email, password });
      setToken(res.token);
      // Se aterriza en el PANEL, no en Asuntos: es la pantalla que responde
      // «¿qué me toca hoy?» y por eso también encabeza la navegación.
      //
      // El despacho que aún no terminó su perfil NO se queda aquí: `OnboardingGate`
      // (montado en el layout raíz) consulta el estado del onboarding en cada ruta
      // que no sea /login, /register, /onboarding ni /activar, y reemplaza el
      // destino por /onboarding si falta. /dashboard queda gobernado por esa misma
      // regla, igual que lo estaba "/" — por eso el cambio de destino no altera en
      // nada el viaje de la primera vez.
      router.replace("/dashboard");
    } catch (err: unknown) {
      // Solo se muestran mensajes que VIENEN del backend (ApiError, en llano);
      // un error de red del navegador ("Failed to fetch") jamás llega a pantalla.
      const msg = plainMessage(err, "");
      const generic = !msg || msg === "Credenciales invalidas" || msg === "Sesión expirada";
      setError(generic ? "El correo o la contraseña no coinciden." : msg);
    } finally {
      setLoading(false);
    }
  }

  // Mientras se decide si toca la portada, el lienzo vivo sin contenido: es un
  // instante y evita el destello formulario→portada.
  if (hero === "comprobando") {
    return <WelcomeShell width="sm">{null}</WelcomeShell>;
  }

  // Primera vez en este equipo: la portada del pack como primera pantalla.
  // «Empezar ahora» avanza al paso real siguiente (crear el despacho);
  // «Omitir» salta solo la presentación y deja el formulario de entrada,
  // que es donde el flujo aterrizaba hasta hoy (el registro no se puentea).
  if (hero === "mostrar") {
    return (
      // hideBrand: el render canónico no lleva el wordmark arriba — la marca ya
      // vive en el anillo del cristal («MIA — Legal intelligence»).
      <WelcomeShell width="lg" hideBrand>
        <StepTransition stepKey="portada" direction={1}>
          <WelcomeHero
            onStart={() => {
              sessionStorage.setItem(HERO_VISTO_KEY, "1");
              router.push("/register");
            }}
            onSkip={() => {
              sessionStorage.setItem(HERO_VISTO_KEY, "1");
              setHero("no");
            }}
          />
        </StepTransition>
      </WelcomeShell>
    );
  }

  return (
    // Regreso al despacho: mismo lienzo cinematográfico, versión compacta y SIN
    // la constelación de progreso del viaje (esto no es la primera vez).
    <WelcomeShell
      width="sm"
      footer={
        <span>
          ¿Aún no tienes tu espacio?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Crear mi despacho
          </Link>
        </span>
      }
    >
      <StepTransition stepKey="entrar" direction={1}>
        {/* El propio <form> es el contenedor de stagger (as="form"): los campos,
            hijos DIRECTOS, entran escalonados en vez de todos a la vez. */}
        <Stagger as="form" onSubmit={submit} className="space-y-6">
          <WelcomeField>
            <div className="space-y-2 text-center">
              <MiaLine text="Qué bueno verte otra vez." className="text-xl sm:text-2xl" />
              <p className="text-sm text-muted-foreground">
                Entra al espacio de tu despacho.
              </p>
            </div>
          </WelcomeField>

          <WelcomeField label="Tu correo" htmlFor="email">
            <Input
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="email"
              placeholder="tu@despacho.com"
              autoFocus
              required
            />
          </WelcomeField>

          <WelcomeField label="Tu contraseña" htmlFor="password">
            <Input
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              required
            />
          </WelcomeField>

          {error ? (
            <WelcomeField>
              <p
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {error}
              </p>
            </WelcomeField>
          ) : null}

          <WelcomeField>
            <Button
              type="submit"
              disabled={loading}
              variant="cta"
              size="lg"
              className="w-full"
            >
              {loading ? "Entrando…" : "Entrar"}
            </Button>
          </WelcomeField>
        </Stagger>
      </StepTransition>
    </WelcomeShell>
  );
}
