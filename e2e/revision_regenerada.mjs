// Regresión de UI con respuestas sintéticas: no llama modelos ni usa expedientes.
// Ejecutar contra el build de producción: node e2e/revision_regenerada.mjs
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const base = process.env.MIA_UI_TEST_URL || "http://localhost:3100";
const output = new URL("../output/playwright/", import.meta.url);
mkdirSync(output, { recursive: true });
const oldHash = "a".repeat(64);
const newHash = "b".repeat(64);
const original = "BORRADOR ORIGINAL. Texto sintético de revisión.";
const replacement = "BORRADOR ACTUALIZADO. Incluye únicamente la selección revisada.";
const verification = { citas: 0, marcadas: 0, anotadas: 0, omitidas: 0, quemadas: 0,
  respaldadas: 0, detalle: [], gate_llm: { veredicto: "apto", detalle: "" } };
const browser = await chromium.launch();
const results = [];
try {
  for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript((mode) => {
      localStorage.setItem("mia_token", "synthetic-ui-test");
      localStorage.setItem("mia-theme", mode);
    }, theme);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    const approvals = [];
    await page.route("http://mia-shell.localhost/**", (route) => route.fulfill({
      json: { ok: true, data: route.request().url().endsWith("/runtime/health")
        ? null : { recovery_key_saved: true } },
      headers: { "access-control-allow-origin": "*" },
    }));
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      const headers = { "access-control-allow-origin": "*",
        "access-control-allow-headers": "authorization,content-type",
        "access-control-allow-methods": "GET,POST,OPTIONS" };
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      if (pathname.endsWith("/draft/approve")) {
        approvals.push(request.postDataJSON());
        if (approvals.length === 1) await held;
        const receipt = approvals.length === 1
          ? { draft: replacement, draft_hash: newHash, verification, final_ready: false,
              final_status: "awaiting_review", awaiting_review: true,
              message: "Actualicé el borrador con tu selección. Revisa esta nueva versión antes de aprobarla." }
          : { final_ready: true, final_status: "approved", decision_saved: true };
        return route.fulfill({ headers, contentType: "text/event-stream",
          body: `event: done\ndata: ${JSON.stringify(receipt)}\n\n` });
      }
      let json = {};
      if (pathname.endsWith("/auth/me")) json = { name: "Prueba", tenant_id: "synthetic" };
      else if (pathname.endsWith("/onboarding/status")) json = { completed: true };
      else if (pathname.endsWith("/draft")) json = {
        draft: original, draft_hash: oldHash, verification, final_ready: false,
        argumentos: [{ id: "A1", tesis: "Argumento principal" }, { id: "A2", tesis: "Argumento secundario" }],
      };
      else if (pathname.includes("/matters/")) json = { jurisdictions: [], title: "Asunto sintético" };
      return route.fulfill({ headers, json });
    });
    await page.goto(`${base}/casos/00000000-0000-0000-0000-000000000001/revisar`);
    await page.getByText(original, { exact: true }).waitFor();
    await page.getByRole("button", { name: "Editar", exact: true }).click();
    await page.locator("#arg-A2").uncheck();
    await page.locator("#revision-humana").check();
    await page.getByRole("button", { name: "Aprobar", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#arg-A2")?.disabled);
    assert.equal(await page.getByRole("textbox", { name: "Tu versión del borrador" }).isDisabled(), true);
    assert.equal(await page.locator("#revision-humana").isDisabled(), true);
    release();
    await page.getByText(replacement, { exact: true }).waitFor();
    assert.equal(await page.locator("#revision-humana").isChecked(), false);
    assert.equal(await page.getByRole("button", { name: "Aprobar", exact: true }).isDisabled(), true);
    assert.equal(await page.getByText(original, { exact: true }).count(), 0);
    assert.equal(await page.locator("#arg-A2").isChecked(), false);
    await page.addScriptTag({ path: fileURLToPath(new URL("../frontend/node_modules/axe-core/axe.min.js", import.meta.url)) });
    const accessibility = await page.evaluate(async () => {
      const result = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } });
      return result.violations.map((v) => ({ id: v.id, impact: v.impact, targets: v.nodes.map((n) => n.target) }));
    });
    writeFileSync(new URL(`revision-accesibilidad-${theme}.json`, output), JSON.stringify(accessibility, null, 2));
    assert.deepEqual(accessibility, [], "Accesibilidad de la revisión");
    await page.screenshot({ path: fileURLToPath(new URL(`revision-regenerada-${theme}.png`, output)), fullPage: true });
    await page.locator("#revision-humana").check();
    await page.getByRole("button", { name: "Aprobar", exact: true }).click();
    await page.waitForFunction(() => document.body.innerText.includes("Tu decisión quedó guardada"));
    assert.equal(approvals.length, 2);
    assert.equal(approvals[0].draft_hash, oldHash);
    assert.equal(approvals[1].draft_hash, newHash);
    assert.deepEqual(approvals[1].argument_selection, { include: ["A1"], exclude: ["A2"] });
    assert.deepEqual(errors, []);
    results.push({ theme, status: "passed", checks: "version,hash,attestation,inflight-lock,selection,pageerrors" });
    await context.close();
  }
  writeFileSync(new URL("revision-regenerada.json", output), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
} finally {
  await browser.close();
}
