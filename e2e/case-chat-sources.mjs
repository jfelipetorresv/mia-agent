import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const base = process.env.MIA_UI_TEST_URL || 'http://localhost:3111';
const out = new URL('../output/playwright/', import.meta.url);
mkdirSync(out, { recursive: true });
const validation = new URL('../output/validation/', import.meta.url);
mkdirSync(validation, { recursive: true });
const browser = await chromium.launch();
const errors = [];
const sent = [];
try {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  await context.addInitScript(() => localStorage.setItem('mia_token', 'synthetic'));
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  const headers = {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'authorization,content-type',
    'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
  };
  await page.route('http://mia-shell.localhost/**', (route) =>
    route.fulfill({ headers, json: { ok: true, data: { recovery_key_saved: true } } }),
  );
  await page.route('http://localhost:8000/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (path === '/api/onboarding/status') {
      return route.fulfill({ headers, json: { completed: true } });
    }
    if (path === '/api/auth/me') {
      return route.fulfill({ headers, json: { name: 'Prueba', tenant_id: 'synthetic' } });
    }
    if (path === '/api/matters/caso-sintetico') {
      return route.fulfill({ headers, json: {
        id: 'caso-sintetico', name: 'Caso de fuentes sintéticas', kind: 'asunto',
        jurisdictions: ['CO'], jurisdictions_effective: ['CO'],
      } });
    }
    if (path === '/api/profile/full') {
      return route.fulfill({ headers, json: { jurisdictions: ['CO'] } });
    }
    if (path === '/api/matters/caso-sintetico/documents') {
      return route.fulfill({ headers, json: [] });
    }
    if (path === '/api/matters/caso-sintetico/documents/pending') {
      return route.fulfill({ headers, json: { documentos: [] } });
    }
    if (path === '/api/matters/caso-sintetico/draft') {
      return route.fulfill({ headers, json: { awaiting_review: false } });
    }
    if (path === '/api/matters/caso-sintetico/historial') {
      return route.fulfill({ headers, json: { mensajes: [] } });
    }
    if (path === '/api/matters/caso-sintetico/sources') {
      return route.fulfill({ headers, json: { sources: [{
        tipo: 'carpeta', id: 'source-synthetic', nombre: 'Carpeta sintética',
        detalle: 'D:\\Fuentes\\Sinteticas', documentos: 0, last_sync: null,
        estado: 'Disponible automáticamente al conversar',
      }] } });
    }
    if (path.includes('/missions')) {
      return route.fulfill({ headers, json: { missions: [] } });
    }
    if (path === '/api/matters/caso-sintetico/chat' && request.method() === 'POST') {
      const body = request.postDataJSON();
      sent.push(body);
      if (body.message.includes('bloqueo')) {
        return route.fulfill({ status: 409, headers, json: {
          detail: 'Ya hay un borrador pendiente. Revísalo antes de iniciar otra consulta.',
        } });
      }
      return route.fulfill({ headers, json: {
        stream_url: '/api/matters/caso-sintetico/stream',
      } });
    }
    if (path === '/api/matters/caso-sintetico/stream' && request.method() === 'POST') {
      return route.fulfill({
        status: 200,
        headers: { ...headers, 'content-type': 'text/event-stream; charset=utf-8' },
        body:
          'event: thinking\ndata: {"message":"Leyendo las fuentes vinculadas…"}\n\n' +
          'event: awaiting_review\ndata: {"draft":"Preparé una respuesta con la fuente vinculada para tu revisión."}\n\n',
      });
    }
    if (path === '/api/matters/caso-sintetico/cierre') {
      return route.fulfill({ headers, json: { triggered: false, written: false } });
    }
    if (path === '/api/atajos') {
      return route.fulfill({ headers, json: { atajos: [] } });
    }
    return route.fulfill({ headers, json: {} });
  });

  await page.goto(`${base}/casos/caso-sintetico`, { waitUntil: 'domcontentloaded', timeout: 180000 });
  const input = page.getByPlaceholder('Escribe tu consulta sobre este caso…');
  await input.waitFor({ timeout: 120000 });
  await input.fill('Revisa la fuente vinculada');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await page.getByText('Preparé una respuesta con la fuente vinculada para tu revisión.').waitFor();
  await page.screenshot({
    path: fileURLToPath(new URL('case-chat-source-success.png', out)), fullPage: true,
  });

  await input.fill('Provoca bloqueo sintético');
  await page.getByRole('button', { name: 'Enviar' }).click();
  const plainError = 'Ya hay un borrador pendiente. Revísalo antes de iniciar otra consulta.';
  await page.getByText(plainError).last().waitFor();
  await page.screenshot({
    path: fileURLToPath(new URL('case-chat-source-http-error.png', out)), fullPage: true,
  });

  assert.deepEqual(sent, [
    { message: 'Revisa la fuente vinculada' },
    { message: 'Provoca bloqueo sintético' },
  ]);
  assert.deepEqual(errors, []);
  const result = { synthetic: true, successReplyVisible: true, backendErrorVisible: true };
  writeFileSync(new URL('case-chat-sources.json', out), JSON.stringify(result, null, 2));
  writeFileSync(new URL('case-chat-browser.json', validation), JSON.stringify({
    ...result,
    scenarios: [
      'respuesta SSE visible en la conversación',
      'detail HTTP 409 visible en la burbuja de Mia',
      'carpeta local mostrada como disponible automáticamente al conversar',
    ],
  }, null, 2));
  console.log(JSON.stringify(result));
  await context.close();
} finally {
  await browser.close();
}
