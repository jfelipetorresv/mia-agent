// Respuestas sintéticas: no usa datos del despacho ni llama proveedores.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const base = process.env.MIA_UI_TEST_URL || "http://localhost:3111";
const output = new URL("../output/playwright/", import.meta.url);
mkdirSync(output, { recursive: true });
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
    const requests = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let releaseFirst;
    const firstHeld = new Promise((resolve) => { releaseFirst = resolve; });
    let releaseHistory;
    const historyHeld = new Promise((resolve) => { releaseHistory = resolve; });
    const headers = { "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization,content-type",
      "access-control-allow-methods": "GET,POST,OPTIONS" };
    await page.route("http://mia-shell.localhost/**", (route) => route.fulfill({
      json: { ok: true, data: route.request().url().endsWith("/runtime/health")
        ? null : { recovery_key_saved: true } }, headers,
    }));
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      if (path.endsWith("/chat/stream")) {
        requests.push(request.postDataJSON());
        const number = requests.length;
        if (number === 1) {
          await firstHeld;
          if (theme === "dark") return route.fulfill({ status: 409, headers,
            json: { detail: "La solicitud sigue en curso. Reintenta para recuperar su respuesta." } });
          // La respuesta pudo guardarse antes de perderse la conexión.
          return route.abort("failed");
        }
        return route.fulfill({ headers, contentType: "text/event-stream",
          body: `event: reply\ndata: ${JSON.stringify({
            conversation_id: "synthetic-conversation", cached: number === 2,
            message: number === 2 ? "Respuesta recuperada sin repetir la solicitud." : "Respuesta al nuevo envío intencional.",
          })}\n\n` });
      }
      let json = {};
      if (path.endsWith("/auth/me")) json = { name: "Prueba", tenant_id: "synthetic" };
      else if (path.endsWith("/onboarding/status")) json = { completed: true };
      else if (path.endsWith("/atajos")) json = { atajos: [] };
      else if (path.endsWith("/conversations")) json = [{ id: "other", title: "Otro hilo sintético" }];
      else if (path.endsWith("/messages")) {
        await historyHeld;
        json = [{ role: "assistant", content: "Historial de otro hilo." }];
      }
      return route.fulfill({ headers, json });
    });
    await page.goto(`${base}/chat`);
    const input = page.getByPlaceholder("Escribe tu consulta a Mia…");
    await input.fill("Mensaje sintético para reintentar");
    const sent = page.waitForRequest((r) => r.url().endsWith("/chat/stream"));
    // Dos eventos en el mismo ciclo, antes de que React pueda renderizar disabled.
    await input.evaluate((el) => {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    await sent;
    assert.equal(await page.getByRole("button", { name: "Nueva conversación", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("button", { name: "Otro hilo sintético" }).isDisabled(), true);
    releaseFirst();
    const retry = page.getByRole("button", { name: "Reintentar mensaje", exact: true });
    await retry.waitFor();
    assert.equal(requests.length, 1, "El doble Enter no duplica la petición");
    assert.equal(await input.isDisabled(), true, "No mezcla una consulta nueva con un hilo aún incierto");
    assert.equal(await page.getByRole("button", { name: "Enviar", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("button", { name: "Nueva conversación", exact: true }).isDisabled(), false);
    await page.screenshot({ path: fileURLToPath(new URL(`chat-reintento-${theme}.png`, output)), fullPage: true });
    await retry.click();
    await page.waitForFunction(() => document.body.innerText.includes("Respuesta recuperada"));
    assert.equal(await page.getByRole("button", { name: "Nueva conversación", exact: true }).isDisabled(), true,
      "El typewriter mantiene bloqueado el hilo tras cerrar SSE");
    await page.getByText("Respuesta recuperada sin repetir la solicitud.", { exact: true }).waitFor();
    await page.waitForFunction(() => ![...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Nueva conversación")?.disabled);
    assert.equal(requests.length, 2);
    assert.deepEqual(requests[1], requests[0], "Reintento conserva ID y payload incluso en conversación nueva");
    assert.match(requests[0].request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    assert.equal(requests[0].conversation_id, null);
    assert.equal(await page.getByText("Mensaje sintético para reintentar", { exact: true }).count(), 1);
    await page.screenshot({ path: fileURLToPath(new URL(`chat-recuperado-${theme}.png`, output)), fullPage: true });
    await input.fill("Mensaje sintético para reintentar");
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
    await page.getByText("Respuesta al nuevo envío intencional.", { exact: true }).waitFor();
    assert.notEqual(requests[2].request_id, requests[0].request_id);
    assert.equal(requests[2].conversation_id, "synthetic-conversation");
    assert.equal(await page.getByText("Mensaje sintético para reintentar", { exact: true }).count(), 2);
    // Un reply terminal válido gana aunque luego se corte la conexión. El segundo
    // terminal no debe reemplazarlo ni crear un reintento de trabajo ya entregado.
    await page.evaluate(() => {
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        if (!String(args[0]).endsWith("/chat/stream")) return originalFetch(...args);
        window.fetch = originalFetch;
        return new Response(new ReadableStream({
          start(controller) {
            const reply = (message) => `event: reply\ndata: ${JSON.stringify({ message, conversation_id: "synthetic-conversation" })}\n\n`;
            controller.enqueue(new TextEncoder().encode(reply("Respuesta válida antes del corte.") + reply("TERMINAL DUPLICADO")));
            setTimeout(() => controller.error(new Error("corte sintético después del reply")), 150);
          },
        }), { headers: { "content-type": "text/event-stream" } });
      };
    });
    await input.fill("Prueba de corte tardío");
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
    await page.getByText("Respuesta válida antes del corte.", { exact: true }).waitFor();
    assert.equal(await retry.count(), 0);
    assert.equal(await page.getByText("TERMINAL DUPLICADO", { exact: true }).count(), 0);
    await page.getByRole("button", { name: "Otro hilo sintético" }).click();
    await input.fill("No debe enviarse durante la carga");
    await input.press("Enter");
    assert.equal(await page.getByRole("button", { name: "Enviar", exact: true }).isDisabled(), true);
    releaseHistory();
    await page.getByText("Historial de otro hilo.", { exact: true }).waitFor();
    assert.equal(requests.length, 3);
    assert.equal(await page.getByText("Respuesta recuperada sin repetir la solicitud.", { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => JSON.stringify(localStorage).includes("Mensaje sintético")), false);
    assert.deepEqual(errors, []);
    results.push({ theme, passed: true, requests: requests.length,
      checks: ["double-enter-single-request", "stable-retry-id-and-payload", "uuid-v4",
        "null-conversation-retry", "no-duplicate-user", "new-intent-new-id",
        "uncertain-attempt-blocks-new-message", "typewriter-lock", "history-load-lock",
        "reply-survives-late-disconnect", "duplicate-terminal-ignored", "no-sensitive-localstorage", "no-pageerrors"],
      screenshots: [`chat-reintento-${theme}.png`, `chat-recuperado-${theme}.png`],
    });
    await context.close();
  }
  writeFileSync(new URL("chat-idempotency.json", output), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
} finally {
  await browser.close();
}
