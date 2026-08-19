// E2E del recorrido de primera vez (F3, specs/todo/03-f3-recorrido-completo.md):
// /register → /activar (auto-salto en dev) → /onboarding (7 pasos) → crear asunto →
// subir expediente fijo (3 .txt, 252 fragmentos) → pregunta → borrador → aprobar →
// «## aprendido». Cronometrado wall-clock por paso, screenshot por paso.
//
// Requiere: DB 55432 + LiteLLM 4000 + backend 8000 + frontend 3100 arriba, y el
// expediente generado (e2e/generar_expediente.py). El reloj arranca al abrir la app
// con los servicios ya arriba (definición exacta de la spec). El tiempo se REPORTA,
// no es umbral: lo que aprueba o reprueba es llegar al borrador aprobado.
//
// Uso:  node e2e/recorrido_primera_vez.mjs --corrida 1
// Salida: validation/screenshots/corrida-N/*.png + tiempos.json ; exit 0/1.

import { chromium } from "playwright";
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE = process.env.MIA_E2E_BASE ?? "http://localhost:3100";
const corrida = process.argv[includeFlag("--corrida") + 1] ?? "1";
const DESTINO = path.join(RAIZ, "validation", "screenshots", `corrida-${corrida}`);
const EXPEDIENTE = path.join(RAIZ, "e2e", "expediente");
const MIA_DATA = path.join(RAIZ, "mia-data");

function includeFlag(f) {
  const i = process.argv.indexOf(f);
  return i === -1 ? process.argv.length : i;
}

const manifiesto = JSON.parse(readFileSync(path.join(EXPEDIENTE, "manifiesto.json"), "utf-8"));
const stamp = Date.now();
const email = `e2e-${stamp}@mia.test`;
const password = "RecorridoE2E.2026";

mkdirSync(DESTINO, { recursive: true });

const marcas = [];
let t0 = 0;
let nPaso = 0;
let page;

async function paso(nombre, fn) {
  const inicio = Date.now();
  await fn();
  nPaso += 1;
  const archivo = `${String(nPaso).padStart(2, "0")}-${nombre}.png`;
  await page.screenshot({ path: path.join(DESTINO, archivo), fullPage: false });
  const seg = (Date.now() - inicio) / 1000;
  marcas.push({ paso: nombre, segundos: Number(seg.toFixed(1)), acumulado: Number(((Date.now() - t0) / 1000).toFixed(1)) });
  console.log(`  [${marcas.at(-1).acumulado}s] ${nombre} (${seg.toFixed(1)}s)`);
}

// Los pasos del onboarding usan dos familias de campos: <Input>/<Textarea> normales
// (se rellenan) y <TagInput> (se escribe y se confirma con Enter para crear el chip).
async function llenarInputs(valores) {
  const inputs = page.locator("main input:visible");
  for (let i = 0; i < valores.length; i++) await inputs.nth(i).fill(valores[i]);
}
async function llenarTags(valores) {
  const inputs = page.locator("main input:visible");
  for (let i = 0; i < valores.length; i++) {
    const campo = inputs.nth(i);
    await campo.click();
    await campo.pressSequentially(valores[i]);
    await campo.press("Enter");
  }
}
// Las preguntas abiertas del bloque criterio pueden ser <Textarea> o <TagInput>
// («Escribe y presiona Enter»): se acepta cualquiera de las dos formas.
async function llenarLibre(valor) {
  const ta = page.locator("main textarea:visible");
  if (await ta.count()) {
    await ta.first().fill(valor);
  } else {
    await llenarTags([valor]);
  }
}
async function siguiente() {
  await page.getByRole("button", { name: "Siguiente" }).click();
}

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await ctx.newPage();
  page.setDefaultTimeout(30_000);

  t0 = Date.now(); // los servicios ya están arriba: aquí arranca el reloj de la spec

  await paso("registro-formulario", async () => {
    await page.goto(`${BASE}/register`);
    await page.locator("#firm").fill("Despacho E2E Primera Vez");
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(password);
  });

  await paso("registro-enviado", async () => {
    await page.getByRole("button", { name: "Crear mi despacho" }).click();
    await page.waitForURL("**/activar", { timeout: 30_000 });
  });

  await paso("activar-auto-salto", async () => {
    // En dev /activar consulta /api/welcome/status y salta solo a /onboarding.
    await page.waitForURL("**/onboarding", { timeout: 30_000 });
    await page.getByRole("button", { name: "Empecemos" }).click();
    await page.getByRole("button", { name: "Siguiente" }).waitFor();
  });

  await paso("onboarding-p1-identidad", async () => {
    await llenarInputs(["Despacho E2E Primera Vez", "Abogada de Prueba"]);
    await siguiente();
  });

  await paso("onboarding-p2-sede", async () => {
    await llenarInputs(["Colombia", "Bogotá"]);
    await siguiente();
  });

  await paso("onboarding-p3-jurisdiccion", async () => {
    // La casilla real es sr-only bajo la ficha (regla 77): se clickea la FICHA.
    await page.locator("label").filter({ hasText: "Colombia" }).first().click();
    await siguiente();
  });

  await paso("onboarding-p4-clientes", async () => {
    await llenarTags(["Empresas de construcción", "Controversias contractuales"]);
    await siguiente();
  });

  await paso("onboarding-p5-criterio", async () => {
    await llenarTags(["Todo escrito que salga del despacho", "Organizar y clasificar documentos"]);
    await siguiente();
  });

  await paso("onboarding-p6-limites", async () => {
    await llenarLibre("Nunca afirmar nada sin respaldo en el expediente");
    await siguiente();
  });

  await paso("onboarding-p7-terminado", async () => {
    await llenarLibre("Cuando cada afirmación tiene fuente verificada y el formato es radicable");
    await page.getByRole("button", { name: "Finalizar" }).click();
    await page.getByRole("button", { name: "Entrar a Mia" }).click();
    await page.waitForURL(`${BASE}/`, { timeout: 30_000 });
  });

  let asuntoUrl = "";
  await paso("crear-asunto", async () => {
    await page.goto(`${BASE}/?nuevo=1`);
    await page.locator("#matter-name").fill("Reclamación contratista — término");
    await page.getByRole("button", { name: "Crear asunto" }).click();
    await page.waitForURL("**/asuntos/**", { timeout: 30_000 });
    asuntoUrl = page.url();
  });

  await paso("subir-expediente", async () => {
    const archivos = manifiesto.documentos.map((d) => path.join(EXPEDIENTE, d.nombre));
    await page.locator('input[type="file"]').setInputFiles(archivos);
    // La ingesta es sincrónica (extracción → chunks → embeddings): el resumen verde
    // «N documentos agregados» ya significa indexado. Expediente grande = minutos.
    await page.getByText(/documentos? agregados?/).first().waitFor({ timeout: 15 * 60_000 });
  });

  await paso("pregunta-enviada", async () => {
    await page.locator('textarea[placeholder^="Escribe tu consulta"]').fill(manifiesto.pregunta);
    await page.locator('[aria-label="Enviar"]').click();
  });

  await paso("borrador-listo", async () => {
    // El caso voluminoso bajo suscripción puede agotar el timeout del motor primario
    // y saltar a la cadena de respaldo: el turno completo supera los 25 min.
    await page.getByText("Tienes un borrador listo").first().waitFor({ timeout: 40 * 60_000 });
  });

  await paso("revisar-borrador", async () => {
    // DEFECTO UI-A corregido (585f332, 2026-08-07): la fila de acciones envuelve y el
    // aside ya no intercepta el clic. El clic real ES la aserción — sin rodeo: si el
    // botón vuelve a quedar tapado, este paso debe FALLAR, no esquivarlo.
    await page.getByRole("button", { name: "Revisar borrador" }).click({ timeout: 15_000 });
    await page.waitForURL("**/revisar", { timeout: 30_000 });
    await page.getByRole("button", { name: "Aprobar" }).waitFor();
  });

  await paso("aprobar", async () => {
    // Gate de citas: si hay citas marcadas, «Aprobar» exige el checkbox.
    const gate = page.locator("#citas-verificadas");
    if (await gate.count()) await gate.check();
    await page.getByRole("button", { name: "Aprobar", exact: true }).click();
    // Aprobar reanuda el grafo y su cierre corre sincrónico antes del 200: minutos.
    await page.waitForURL(/confirmed=true/, { timeout: 10 * 60_000 });
  });

  const totalSeg = Number(((Date.now() - t0) / 1000).toFixed(1));

  // «## aprendido»: tarea de fondo fail-soft que usa el modelo — se sondea con
  // reintentos y se REPORTA; no tumba la corrida (nacería como gate intermitente).
  let aprendido = "no poblado (fondo fail-soft)";
  const soulNuevo = () => {
    const souls = readdirSync(MIA_DATA).filter((f) => /^soul_[0-9a-f-]+\.md$/.test(f));
    let mejor = null;
    for (const f of souls) {
      const st = statSync(path.join(MIA_DATA, f));
      if (st.mtimeMs > stamp && (!mejor || st.mtimeMs > mejor.m)) mejor = { f, m: st.mtimeMs };
    }
    return mejor?.f;
  };
  for (let i = 0; i < 18; i++) {
    const f = soulNuevo();
    if (f) {
      const cuerpo = readFileSync(path.join(MIA_DATA, f), "utf-8");
      const seccion = cuerpo.split("## aprendido")[1] ?? "";
      if (/^- .+/m.test(seccion)) {
        aprendido = `poblado (${f})`;
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 10_000));
  }

  const informe = {
    corrida: Number(corrida),
    fecha: new Date().toISOString(),
    email,
    asunto: asuntoUrl,
    total_segundos: totalSeg,
    aprendido,
    pasos: marcas,
  };
  writeFileSync(path.join(DESTINO, "tiempos.json"), JSON.stringify(informe, null, 2), "utf-8");
  console.log(`CORRIDA ${corrida} VERDE — total ${totalSeg}s — ## aprendido: ${aprendido}`);
  await browser.close();
}

main().catch(async (e) => {
  console.error(`CORRIDA ${corrida} ROJA en el paso ${nPaso + 1}: ${e.message}`);
  try {
    await page?.screenshot({ path: path.join(DESTINO, `${String(nPaso + 1).padStart(2, "0")}-FALLO.png`) });
  } catch {}
  process.exit(1);
});
