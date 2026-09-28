// Real Chromium, synthetic authenticated APIs only: no installed DB or model calls.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.MIA_UI_TEST_URL || 'http://localhost:3111';
const authSwitchOnly = process.env.MIA_RECOVERY_AUTH_SWITCH_ONLY === '1';
const lateCallbacksOnly = process.env.MIA_RECOVERY_LATE_CALLBACKS_ONLY === '1';
const httpOnly = process.env.MIA_RECOVERY_HTTP_ONLY === '1';
const unauthorizedOnly = process.env.MIA_RECOVERY_401_ONLY === '1';
const prefetchOnly = process.env.MIA_RECOVERY_PREFETCH_ONLY === '1';
const resultsName = prefetchOnly ? 'chat-recovery-prefetch-results.json' : unauthorizedOnly ? 'chat-recovery-401-results.json' : lateCallbacksOnly ? 'chat-recovery-late-callback-results.json' : httpOnly ? 'chat-recovery-http-results.json' : authSwitchOnly ? 'chat-recovery-auth-switch-results.json' : 'chat-recovery-results.json';
const output = new URL('../output/playwright/', import.meta.url);
mkdirSync(output, { recursive: true });
const tid = '11111111-1111-4111-8111-111111111111';
const uid = '22222222-2222-4222-8222-222222222222';
const other = '33333333-3333-4333-8333-333333333333';
const rid = '44444444-4444-4444-8444-444444444444';
const cid = '55555555-5555-4555-8555-555555555555';
const key = `mia.chat.pending:${tid}:${uid}`;
const reply = 'Respuesta sintética recuperada sin otra inferencia.';
const marker = { request_id: rid, conversation_id: null };
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'authorization,content-type',
  'access-control-allow-methods': 'GET,POST,OPTIONS' };
console.log('Launching synthetic recovery browser');
const browser = await chromium.launch({ timeout: 30000, channel: process.env.MIA_BROWSER_CHANNEL || undefined });
console.log('Browser ready');
const results = [];
async function bounded(operation, label) {
  let timer;
  try { return await Promise.race([operation, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label} exceeded 60 seconds`)), 60000); })]); }
  finally { clearTimeout(timer); }
}
async function setup(options = {}) {
  console.log('Scenario setup', Object.keys(options));
  const state = { posts: [], postAuth: [], gets: [], errors: [], consoleErrors: [], status: 'completed', identity: uid, ...options };
  const context = await bounded(browser.newContext({ viewport: { width: 1440, height: 1000 } }), 'newContext');
  console.log('Context ready');
  context.setDefaultTimeout(15000);
  context.setDefaultNavigationTimeout(120000);
  await context.addInitScript(({ key, saved, noLocks, failStorage }) => {
    if (location.protocol !== 'http:' && location.protocol !== 'https:') return;
    if (!localStorage.getItem('mia_token')) localStorage.setItem('mia_token', 'synthetic-recovery');
    localStorage.setItem('mia-theme', 'light');
    if (!sessionStorage.getItem('recovery-seeded')) {
      if (saved !== undefined) localStorage.setItem(key, saved);
      sessionStorage.setItem('recovery-seeded', 'yes');
    }
    if (noLocks) Object.defineProperty(navigator, 'locks', { value: undefined, configurable: true });
    if (failStorage) {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (name, value) {
        if (name === key) throw new DOMException('Synthetic quota failure', 'QuotaExceededError');
        return original.call(this, name, value);
      };
    }
  }, { key, saved: options.saved, noLocks: options.noLocks, failStorage: options.failStorage });
  await context.route('http://mia-shell.localhost/**', route => route.fulfill({ headers,
    json: { ok: true, data: route.request().url().endsWith('/runtime/health') ? null : { recovery_key_saved: true } } }));
  await context.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'OPTIONS') return route.fulfill({ headers, status: 204 });
    if (path.endsWith('/chat/stream')) {
      state.posts.push(request.postDataJSON());
      state.postAuth.push(request.headers().authorization);
      if (state.postStatus) return route.fulfill({ headers, status: state.postStatus, json: { detail: 'Rechazo sintético antes de responder.' } });
      if (state.normalReply) return route.fulfill({ headers, contentType: 'text/event-stream',
        body: `event: reply\ndata: ${JSON.stringify({ conversation_id: cid, request_id: state.posts.at(-1).request_id, message: reply, cached: false })}\n\n` });
      return route.abort('failed');
    }
    if (path.includes('/chat/requests/')) {
      state.gets.push(path);
      state.onRecovery?.();
      if (state.recoveryHeld) await state.recoveryHeld;
      return route.fulfill({ headers, json: { request_id: rid, status: state.status,
        ...(state.status === 'completed' ? { response: { conversation_id: cid, reply } } : {}) } });
    }
    if (path.endsWith('/messages')) {
      state.onMessages?.();
      if (state.messagesHeld) await state.messagesHeld;
      if (state.historyFailure) return route.fulfill({ headers, status: 503, json: { detail: 'Historial temporalmente no disponible.' } });
      return route.fulfill({ headers, json: [{ role: 'user', content: 'Mensaje sintético privado.' }, { role: 'assistant', content: reply }] });
    }
    let json = {};
    if (path.endsWith('/chat/identity')) json = { tenant_id: tid, user_id: state.identity };
    else if (path.endsWith('/auth/me')) json = { name: 'Prueba sintética', tenant_id: tid };
    else if (path.endsWith('/onboarding/status')) json = { completed: true };
    else if (path.endsWith('/atajos')) json = { atajos: [] };
    else if (path.endsWith('/conversations')) json = state.conversationRows || [];
    return route.fulfill({ headers, json });
  });
  context.on('page', page => {
    page.on('pageerror', err => state.errors.push(err.message));
    page.on('console', msg => { if (msg.type() === 'error') state.consoleErrors.push(msg.text()); });
  });
  console.log('Routes ready');
  const page = await bounded(context.newPage(), 'newPage');
  console.log('Navigate chat');
  await page.goto(`${base}/chat`);
  const input = page.getByPlaceholder('Escribe tu consulta a Mia…');
  await input.waitFor();
  return { context, page, input, state };
}
async function waitEnabled(page) { await page.waitForFunction(() => !document.querySelector('textarea')?.disabled); }
async function send(page, input) {
  await waitEnabled(page);
  await input.fill('Mensaje sintético privado.');
  await page.getByRole('button', { name: 'Enviar', exact: true }).click();
}
async function saved(page) { return page.evaluate(k => localStorage.getItem(k), key); }
async function done(name, s) {
  assert.deepEqual(s.state.errors, [], 'No JavaScript runtime errors');
  console.log('PASS', name);
  results.push({ name, posts: s.state.posts.length, recoveryGets: s.state.gets.length,
    pageErrors: s.state.errors, consoleErrors: s.state.consoleErrors });
  await s.page.screenshot({ path: fileURLToPath(new URL(`chat-recovery-${name}.png`, output)), fullPage: true, animations: 'disabled', timeout: 30000 });
  await s.context.close();
}
try {
  if (!authSwitchOnly && !lateCallbacksOnly && !prefetchOnly) {
  {
    const s = await setup();
    await send(s.page, s.input);
    await s.page.getByText('El envío quedó pendiente.', { exact: false }).waitFor();
    const stored = JSON.parse(await saved(s.page));
    assert.deepEqual(Object.keys(stored).sort(), ['conversation_id', 'request_id']);
    assert.equal(JSON.stringify(stored).includes('Mensaje'), false);
    await s.page.reload();
    await s.page.getByText(reply, { exact: true }).waitFor();
    await waitEnabled(s.page);
    assert.equal(s.state.posts.length, 1);
    assert.equal(await s.page.getByText(reply, { exact: true }).count(), 1);
    assert.equal(await saved(s.page), null);
    await done('lost-sse-reload', s);
  }
  for (const status of ['running', 'uncertain']) {
    const s = await setup({ saved: JSON.stringify(marker), status });
    await s.page.getByRole('button', { name: 'Comprobar envío', exact: true }).click();
    await s.page.waitForFunction(() => ![...document.querySelectorAll('button')].find(b => b.textContent === 'Comprobar envío')?.disabled);
    assert.equal(s.state.posts.length, 0);
    assert.equal(await s.input.isDisabled(), true);
    assert.deepEqual(JSON.parse(await saved(s.page)), marker);
    await done(status, s);
  }
  {
    const s = await setup({ status: 'running' });
    const second = await s.context.newPage();
    await second.goto(`${base}/chat`);
    await waitEnabled(second);
    await second.getByPlaceholder('Escribe tu consulta a Mia…').fill('Segundo envío privado.');
    await send(s.page, s.input);
    await s.page.getByText('El envío quedó pendiente.', { exact: false }).waitFor();
    const before = await saved(s.page);
    await second.getByPlaceholder('Escribe tu consulta a Mia…').evaluate(el => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
    assert.equal(await saved(second), before);
    assert.equal(s.state.posts.length, 1);
    await second.reload();
    await second.getByRole('button', { name: 'Comprobar envío', exact: true }).waitFor();
    assert.equal(s.state.posts.length, 1);
    await done('two-tabs', s);
  }
  {
    const s = await setup({ saved: JSON.stringify(marker), identity: other });
    await waitEnabled(s.page);
    assert.equal(s.state.gets.length, 0);
    assert.equal(s.state.posts.length, 0);
    assert.deepEqual(JSON.parse(await saved(s.page)), marker);
    await done('other-user', s);
  }
  {
    const s = await setup({ saved: '{broken' });
    const discard = s.page.getByRole('button', { name: 'Descartar registro ilegible', exact: true });
    await discard.waitFor();
    assert.equal(await s.input.isDisabled(), true);
    await discard.click();
    await waitEnabled(s.page);
    assert.equal(await saved(s.page), null);
    assert.equal(s.state.posts.length, 0);
    await done('corrupt-discard', s);
  }
  {
    const s = await setup({ saved: '{broken' });
    const discard = s.page.getByRole('button', { name: 'Descartar registro ilegible', exact: true });
    await discard.waitFor();
    // Another writer replaces the value before this view processes its storage event.
    await s.page.evaluate(({ key, marker }) => localStorage.setItem(key, JSON.stringify(marker)), { key, marker });
    await discard.click();
    await s.page.getByText('Este registro corresponde a otro envío.', { exact: false }).waitFor();
    assert.deepEqual(JSON.parse(await saved(s.page)), marker);
    assert.equal(s.state.posts.length, 0);
    await done('corrupt-replaced', s);
  }
  {
    const s = await setup({ noLocks: true });
    await send(s.page, s.input);
    await s.page.getByText('No se envió el mensaje.', { exact: false }).waitFor();
    assert.equal(s.state.posts.length, 0);
    assert.equal(await saved(s.page), null);
    await done('no-web-locks', s);
  }
  {
    const s = await setup({ failStorage: true });
    await send(s.page, s.input);
    await s.page.getByText('No se envió el mensaje.', { exact: false }).waitFor();
    assert.equal(s.state.posts.length, 0);
    assert.equal(await saved(s.page), null);
    await done('storage-failure', s);
  }
  {
    const s = await setup({ saved: JSON.stringify(marker), historyFailure: true });
    await s.page.getByText(reply, { exact: true }).waitFor();
    await waitEnabled(s.page);
    assert.equal(s.state.posts.length, 0);
    assert.equal(await s.page.getByText(reply, { exact: true }).count(), 1);
    assert.equal(await saved(s.page), null);
    await done('history-fallback', s);
  }
  {
    const s = await setup({ normalReply: true });
    await send(s.page, s.input);
    await s.page.getByText(reply, { exact: true }).waitFor();
    await s.page.waitForFunction(() => ![...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Nueva conversación')?.disabled);
    assert.equal(s.state.posts.length, 1);
    assert.equal(await s.page.getByText(reply, { exact: true }).count(), 1);
    assert.equal(await saved(s.page), null);
    await done('normal-typewriter', s);
  }
  {
    const s = await setup({ normalReply: true });
    await send(s.page, s.input);
    await s.page.waitForFunction(() => document.body.innerText.includes('Respuesta sint') &&
      !document.body.innerText.includes('Respuesta sintética recuperada sin otra inferencia.'));
    assert.notEqual(await saved(s.page), null, 'Keep recovery marker while animation is incomplete');
    await s.page.reload();
    await s.page.getByText(reply, { exact: true }).waitFor();
    await waitEnabled(s.page);
    assert.equal(s.state.posts.length, 1);
    assert.equal(await s.page.getByText(reply, { exact: true }).count(), 1);
    assert.equal(await saved(s.page), null);
    await done('reload-typewriter', s);
  }
  }
  if (authSwitchOnly) {
    if (!httpOnly) {
    const s = await setup({ status: 'running' });
    await waitEnabled(s.page);
    await s.input.fill('Borrador privado de la primera cuenta.');
    const second = await s.context.newPage();
    await second.goto(`${base}/chat`);
    await waitEnabled(second);
    s.state.identity = other;
    await Promise.all([
      s.page.evaluate(() => new Promise(resolve => window.addEventListener('storage', function seen(e) {
        if (e.key === 'mia_token') { window.removeEventListener('storage', seen); resolve(true); }
      }))),
      second.evaluate(() => localStorage.setItem('mia_token', 'synthetic-second-account')),
    ]);
    await s.page.getByPlaceholder('Escribe tu consulta a Mia…').evaluate(el => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
    // Wait one UI cycle and the network route, without issuing any extra request.
    await s.page.waitForTimeout(500);
    const evidence = { posts: s.state.posts, authorization: s.state.postAuth,
      previousUserMarker: await saved(s.page), currentUserMarker: await s.page.evaluate(k => localStorage.getItem(k), `mia.chat.pending:${tid}:${other}`) };
    writeFileSync(new URL('chat-recovery-auth-switch.json', output), JSON.stringify(evidence, null, 2));
    assert.equal(s.state.posts.length, 0, 'Switching account in another tab must not send the prior account draft');
    await done('auth-switch', s);
    {
      const immediate = await setup();
      await waitEnabled(immediate.page);
      await immediate.input.fill('Borrador privado de la primera cuenta.');
      await immediate.input.evaluate(el => {
        localStorage.setItem('mia_token', 'synthetic-second-account');
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      });
      await immediate.page.getByText('La sesión cambió.', { exact: false }).waitFor();
      assert.equal(immediate.state.posts.length, 0);
      assert.equal(await saved(immediate.page), null);
      await done('auth-switch-before-storage-event', immediate);
    }
    {
      let release, observed;
      const recoveryHeld = new Promise(resolve => { release = resolve; });
      const requested = new Promise(resolve => { observed = resolve; });
      const delayed = await setup({ saved: JSON.stringify(marker), recoveryHeld, onRecovery: observed });
      await requested;
      await delayed.page.evaluate(() => localStorage.setItem('mia_token', 'synthetic-second-account'));
      release();
      await delayed.page.waitForTimeout(500);
      assert.equal(await delayed.page.getByText(reply, { exact: true }).count(), 0, 'Never display previous account recovery after a token swap');
      assert.deepEqual(JSON.parse(await saved(delayed.page)), marker);
      assert.equal(delayed.state.posts.length, 0);
      await done('auth-switch-during-recovery', delayed);
    }
    }
    for (const postStatus of (unauthorizedOnly ? [401] : [402, 422, 409, 502])) {
      const rejected = await setup({ postStatus });
      await send(rejected.page, rejected.input);
      if (postStatus === 401) {
        await rejected.page.waitForURL('**/login');
        assert.equal(await saved(rejected.page), null, 'Definitive HTTP 401 must not leave a nonexistent pending request');
      } else if ([402, 422].includes(postStatus)) {
        await rejected.page.getByText('Rechazo sintético antes de responder.', { exact: true }).waitFor();
        await waitEnabled(rejected.page);
        assert.equal(await rejected.input.inputValue(), 'Mensaje sintético privado.');
        assert.equal(await saved(rejected.page), null);
      } else {
        await rejected.page.getByText('El envío quedó pendiente.', { exact: false }).waitFor();
        assert.notEqual(await saved(rejected.page), null);
        assert.equal(await rejected.input.isDisabled(), true);
      }
      assert.equal(rejected.state.gets.length, 0);
      assert.equal(rejected.state.posts.length, 1);
      await done(`http-${postStatus}`, rejected);
    }
  }
  if (lateCallbacksOnly) {
    let release, observed;
    const messagesHeld = new Promise(resolve => { release = resolve; });
    const requested = new Promise(resolve => { observed = resolve; });
    const s = await setup({ messagesHeld, onMessages: observed,
      conversationRows: [{ id: cid, title: 'Conversación privada anterior', updated_at: '2026-09-28T12:00:00Z' }] });
    await waitEnabled(s.page);
    const second = await s.context.newPage();
    await second.goto(`${base}/chat`);
    await waitEnabled(second);
    await s.page.getByRole('button', { name: 'Conversación privada anterior', exact: true }).click();
    await requested;
    await second.evaluate(() => localStorage.setItem('mia_token', 'synthetic-second-account'));
    await s.page.getByText('La sesión cambió.', { exact: false }).waitFor();
    release();
    await s.page.waitForTimeout(500);
    assert.equal(await s.page.getByText(reply, { exact: true }).count(), 0);
    assert.equal(await s.page.getByText('Mensaje sintético privado.', { exact: true }).count(), 0);
    assert.equal(await s.page.getByRole('button', { name: 'Conversación privada anterior', exact: true }).count(), 0);
    assert.equal(s.state.posts.length, 0);
    await done('late-open-conversation', s);
  }
  if (prefetchOnly) {
    for (const replacement of [false, true]) {
      const s = await setup();
      await waitEnabled(s.page);
      await s.page.evaluate(({ key, marker, replacement }) => {
        const original = navigator.locks.request.bind(navigator.locks);
        let injected = false;
        navigator.locks.request = async function (name, ...args) {
          const result = await original(name, ...args);
          if (name === `${key}:lock` && result === true && !injected) {
            injected = true;
            window.__prefetchReserved = JSON.parse(localStorage.getItem(key));
            localStorage.setItem('mia_token', 'synthetic-second-account');
            if (replacement) localStorage.setItem(key, JSON.stringify(marker));
          }
          return result;
        };
      }, { key, marker, replacement });
      await send(s.page, s.input);
      await s.page.getByText('La sesión cambió.', { exact: false }).waitFor();
      const reserved = await s.page.evaluate(() => window.__prefetchReserved);
      assert.equal(await s.page.getByText('Mia está pensando…', { exact: true }).count(), 0, 'Session change must clear the stale thinking status');
      assert.ok(reserved?.request_id, 'The test changed identity only after a durable marker existed');
      assert.notEqual(reserved.request_id, marker.request_id);
      assert.equal(s.state.posts.length, 0, 'No network POST when identity changes between reservation and fetch');
      assert.equal(s.state.gets.length, 0);
      if (replacement) assert.deepEqual(JSON.parse(await saved(s.page)), marker, 'Preserve a different request marker');
      else assert.equal(await saved(s.page), null, 'Remove own marker when no request was sent');
      await done(replacement ? 'prefetch-preserve-renewed-marker' : 'prefetch-remove-own-marker', s);
    }
  }
  writeFileSync(new URL(resultsName, output), JSON.stringify({ browser: process.env.MIA_BROWSER_CHANNEL || 'chromium-headless-shell', passed: results.length, results }, null, 2));
  console.log(JSON.stringify({ passed: results.length, results }, null, 2));
} catch (error) {
  writeFileSync(new URL(resultsName, output), JSON.stringify({ passed: results.length, results, error: String(error.stack) }, null, 2));
  throw error;
} finally { await browser.close(); }
