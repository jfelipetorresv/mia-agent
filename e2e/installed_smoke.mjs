// Inspección de la WebView REAL de Mia instalada, sin crear usuarios ni datos.
// Abrir la app solo para esta prueba con WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
// --remote-debugging-port=9231 --remote-debugging-address=127.0.0.1
// Fuente: https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/debug-visual-studio-code
// Después cerrar esa instancia y abrir normalmente, sin puerto de depuración.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const cdp = process.env.MIA_INSTALLED_CDP || "http://127.0.0.1:9231";
assert.equal(new URL(cdp).hostname, "127.0.0.1", "La inspección debe ser local");
const browser = await chromium.connectOverCDP(cdp);
try {
  let page;
  const deadline = Date.now() + 120000;
  while (!page && Date.now() < deadline) {
    page = browser.contexts().flatMap((context) => context.pages())
      .find((candidate) => candidate.url().startsWith("http://localhost:3100/"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.ok(page, "La ventana instalada debe haber llegado al frontend real");
  await page.waitForLoadState("domcontentloaded");
  await page.getByRole("button", { name: "Empezar ahora", exact: true })
    .or(page.getByRole("link", { name: "Crear mi despacho", exact: true }))
    .first().waitFor({ timeout: 30000 });
  const bridge = await page.evaluate(async () => {
    const responses = {};
    for (const path of ["runtime/health", "maintenance/status"]) {
      const response = await fetch(`http://mia-shell.localhost/${path}`, {
        method: "POST", headers: { "Content-Type": "text/plain" }, body: "{}",
        signal: AbortSignal.timeout(15000),
      });
      responses[path] = await response.json();
    }
    return responses;
  });
  assert.equal(bridge["runtime/health"].ok, true, "Puente nativo de estado");
  assert.equal(bridge["maintenance/status"].ok, true, "Puente nativo de protección");
  assert.notEqual(bridge["runtime/health"].data?.stage, "runtime-error");
  const response = await fetch("http://127.0.0.1:8000/health", { signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200);
  const health = await response.json();
  assert.equal(health.status, "ok");
  assert.equal(health.db, true);
  assert.ok(health.pgvector);
  assert.equal(health.checkpointer, true);
  assert.equal(health.provenance_ready, true);
  assert.ok(health.migrations_expected > 0);
  assert.equal(health.migrations_applied, health.migrations_expected);
  const output = new URL("../output/playwright/", import.meta.url);
  mkdirSync(output, { recursive: true });
  await page.screenshot({ path: fileURLToPath(new URL("mia-installed-0.3.1.png", output)), fullPage: true });
  const result = {
    expected_version: "0.3.1", passed: true, url: page.url(), title: await page.title(),
    native_runtime_bridge: true, native_protection_bridge: true,
    runtime_notice_stage: bridge["runtime/health"].data?.stage ?? null,
    protection_recovery_key_created: bridge["maintenance/status"].data?.recovery_key_created,
    checkpointer: health.checkpointer, migrations_applied: health.migrations_applied,
    migrations_expected: health.migrations_expected,
    onboarding_visible: true, created_user: false,
  };
  writeFileSync(new URL("mia-installed-0.3.1.json", output), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally {
  await browser.close(); // disconnect CDP; la cáscara se cierra de forma ordenada aparte
}
