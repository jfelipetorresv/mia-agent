// Herramienta puntual (sesión 54): captura el ESCRITORIO y un ASUNTO reales de MIA
// con el rediseño de Antigravity (Neumorfismo Pro + Mesh Vivo) bajo 4 paletas,
// cambiando SOLO el token --primary de globals.css (se restaura al final con git).
import { chromium } from "playwright";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GLOBALS = path.join(RAIZ, "frontend", "app", "globals.css");
const SCRATCH = process.argv[2];
const seed = JSON.parse(readFileSync(path.join(SCRATCH, "seed.json"), "utf-8"));
const DESTINO = path.join(SCRATCH, "paletas");
mkdirSync(DESTINO, { recursive: true });

const original = readFileSync(GLOBALS, "utf-8");
const LIGHT = "--primary: 180 100% 25%;";
const DARK = "--primary: 180 55% 52%;";

const paletas = [
  { id: "A-teal-actual", light: null, dark: null },
  { id: "B-gris-azul", light: "--primary: 211 38% 42%;", dark: "--primary: 211 42% 62%;" },
  { id: "C-azul-profundo", light: "--primary: 214 65% 33%;", dark: "--primary: 214 55% 60%;" },
  { id: "D-indigo", light: "--primary: 245 48% 50%;", dark: "--primary: 245 60% 68%;" },
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript((t) => localStorage.setItem("mia_token", t), seed.token);
const page = await ctx.newPage();

try {
  for (const p of paletas) {
    let css = original;
    if (p.light) css = css.replace(LIGHT, p.light).replace(DARK, p.dark);
    writeFileSync(GLOBALS, css, "utf-8");
    await new Promise((r) => setTimeout(r, 4500)); // HMR de next dev

    await page.goto("http://localhost:3100/", { waitUntil: "networkidle" });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(DESTINO, `${p.id}-escritorio.png`) });

    await page.goto(`http://localhost:3100/asuntos/${seed.asunto_con_borrador}`, { waitUntil: "networkidle" });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(DESTINO, `${p.id}-asunto.png`) });
    console.log(`${p.id}: 2 capturas`);
  }
} finally {
  writeFileSync(GLOBALS, original, "utf-8");
  execSync("git checkout -- frontend/app/globals.css", { cwd: RAIZ });
  await browser.close();
  console.log("globals.css restaurado");
}
