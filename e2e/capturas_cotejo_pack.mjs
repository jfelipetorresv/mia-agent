// Cierra el hueco del cotejo visual contra MIA-Luxury-Design-Pack (sesión 63).
//
// POR QUÉ EXISTE: el pack define tres pantallas —centro de mando, Casos y onboarding—
// en claro y oscuro. La corrida del 2026-09-01 capturó el centro de mando pero NO
// visitó /casos ni el recorrido de primera vez, así que dos de los tres pares del pack
// quedaron sin contraparte. Este script toma exactamente esas cuatro capturas.
//
// Requiere: DB 55432 + backend 8000 + frontend 3100 arriba, y el despacho de prueba
// sembrado (execution/seed_despacho_demo.py --json), cuyo JSON se pasa por --seed.
//
//   node e2e/capturas_cotejo_pack.mjs --seed <ruta-al-seed.json>
//
// Salida: validation/screenshots/1[5-8]_<fecha>_*.png + cotejo-veredicto.json
// Navega por localhost, NUNCA por 127.0.0.1: con la segunda la sesión no resuelve y
// toda pantalla sale en el spinner de carga (trampa de la sesión 62).

import { chromium } from "playwright";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE = "http://localhost:3100";
const API = "http://localhost:8000";
const DESTINO = path.join(RAIZ, "validation", "screenshots");
const FECHA = new Date().toISOString().slice(0, 10);

const iSeed = process.argv.indexOf("--seed");
if (iSeed === -1) {
  console.error("falta --seed <ruta-al-json de seed_despacho_demo.py --json>");
  process.exit(1);
}
const seed = JSON.parse(readFileSync(process.argv[iSeed + 1], "utf-8"));
mkdirSync(DESTINO, { recursive: true });

// Un tenant recién registrado y SIN entrevista: es la única forma de que /onboarding
// se muestre de verdad en vez de redirigir al escritorio.
async function tenantVirgen() {
  const stamp = Date.now();
  const r = await fetch(`${API}/api/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: `cotejo-${stamp}@mia.test`,
      password: "CotejoPack.2026",
      firm_name: "Despacho de cotejo",
    }),
  });
  if (!r.ok) throw new Error(`register ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return j.token ?? j.access_token;
}

const browser = await chromium.launch();
const veredicto = [];
let n = 14; // continúa la numeración de la corrida del 2026-09-01

async function capturar({ ruta, tema, token, nombre, espera = 2500 }) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: tema,
  });
  await ctx.addInitScript(
    ([t, tema]) => {
      // Solo localStorage: tocar document.documentElement aquí corre ANTES de que el
      // documento exista y siembra un error en cada página (trampa de la sesión 62).
      try {
        localStorage.setItem("mia_token", t);
        localStorage.setItem("mia-theme", tema);
      } catch {}
    },
    [token, tema]
  );
  const page = await ctx.newPage();
  const errores = [];
  page.on("console", (m) => m.type() === "error" && errores.push(m.text()));
  page.on("requestfailed", (r) => {
    // Conserva la causa operativa sin guardar query strings (pueden contener tokens o
    // mensajes del abogado) en el artefacto de validación.
    let destino = r.url();
    try {
      const u = new URL(r.url());
      destino = `${u.origin}${u.pathname}`;
    } catch {}
    errores.push(`REQ ${r.method()} ${destino}: ${r.failure()?.errorText || "falló"}`);
  });
  page.on("pageerror", (e) => errores.push(`PAGE ${e.message}`));

  await page.goto(`${BASE}${ruta}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(espera);

  n += 1;
  const archivo = `${String(n).padStart(2, "0")}_${FECHA}_${nombre}-${tema}.png`;
  await page.screenshot({ path: path.join(DESTINO, archivo), fullPage: false });

  const url_final = new URL(page.url()).pathname;
  const cargando = await page.evaluate(() =>
    /cargando|spinner/i.test(document.body.innerText.slice(0, 400))
  );
  veredicto.push({
    ruta,
    tema,
    url_final,
    redirigido: url_final !== ruta,
    en_spinner: cargando,
    errores: errores.length,
    detalle_error: errores.slice(0, 10),
    captura: archivo,
  });
  console.log(
    `${archivo}  ruta=${ruta} → ${url_final}` +
      (url_final !== ruta ? "  [REDIRIGIDO]" : "") +
      (cargando ? "  [SPINNER]" : "")
  );
  await ctx.close();
}

try {
  for (const tema of ["light", "dark"]) {
    await capturar({ ruta: "/casos", tema, token: seed.token, nombre: "casos" });
  }
  for (const tema of ["light", "dark"]) {
    const token = await tenantVirgen();
    await capturar({ ruta: "/onboarding", tema, token, nombre: "onboarding" });
  }
} finally {
  writeFileSync(
    path.join(DESTINO, "cotejo-veredicto.json"),
    JSON.stringify(veredicto, null, 2),
    "utf-8"
  );
  await browser.close();
}

const malas = veredicto.filter((v) => v.redirigido || v.en_spinner);
if (malas.length) {
  console.log(`\nATENCION: ${malas.length} captura(s) NO muestran la pantalla pedida.`);
  process.exit(1);
}
console.log("\n4 capturas tomadas, ninguna redirigida ni en spinner.");
