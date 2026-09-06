import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
const base = process.env.MIA_UI_TEST_URL || 'http://localhost:3111';
const out = new URL('../output/playwright/', import.meta.url);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const results = [];
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'authorization,content-type', 'access-control-allow-methods': 'GET,POST,PUT,OPTIONS' };
async function scenario(name, overrides, test, options = {}) {
  if (process.env.MIA_UI_SCENARIO && name !== process.env.MIA_UI_SCENARIO) return;
  const context = await browser.newContext({viewport:{width:1000,height:1100}});
  await context.addInitScript(() => { localStorage.setItem('mia_token','synthetic'); localStorage.setItem('mia-theme','light'); });
  const page = await context.newPage();
  const writes = [];
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const status = { instalado:true, hay_usuario:true, onboarding_completo:false,
    faltan_llaves:{busqueda:true,respaldo:true,openrouter:true},
    motor_detectado:{claude:true,codex:true,ollama:false}, politica:'codex', ...overrides };
  await page.route('http://mia-shell.localhost/**', r => r.fulfill({headers,json:{ok:false}}));
  await page.route('http://localhost:8000/**', async r => {
    const req = r.request(), path = new URL(req.url()).pathname;
    if(req.method()==='OPTIONS') return r.fulfill({status:204,headers});
    if(path==='/api/welcome/status') return r.fulfill({headers,json:status});
    if(path==='/api/auth/me') return r.fulfill({headers,json:{name:'Prueba',tenant_id:'synthetic'}});
    if(path==='/api/onboarding/status') return r.fulfill({headers,json:{completed:false}});
    if(path==='/api/welcome/keys/test') return r.fulfill({headers,json:{ok:true}});
    if(req.method()==='POST'||req.method()==='PUT') {
      writes.push({path,body:req.postDataJSON()});
      if(path==='/settings/model-policy' && options.failPolicy) return r.fulfill({status:503,headers,json:{detail:'No pude guardar la conexión de prueba.'}});
      if(path==='/api/welcome/keys') return r.fulfill({headers,json:{guardado:{},mensaje:'Guardado',aviso:options.notice || null}});
    }
    return r.fulfill({headers,json:{}});
  });
  try {
    await page.goto(base+'/activar',{waitUntil:'domcontentloaded',timeout:180000});
    await page.getByRole('radio',{name:/Mis suscripciones/}).waitFor();
    await test(page,writes);
    assert.deepEqual(errors,[], 'Sin errores de render');
    results.push({name,passed:true});
  } finally { await context.close(); }
}
try {
  await scenario('Codex detectado, sin claves',{},async(p,w)=>{
    assert.equal(await p.getByLabel('Conexión preferida').inputValue(),'codex');
    assert.equal(await p.locator('input').count(),0);
    assert.equal(await p.getByRole('button',{name:'Continuar',exact:true}).isEnabled(),true);
    await p.screenshot({path:fileURLToPath(new URL('activation-subscriptions.png',out)),fullPage:true});
    await p.getByRole('button',{name:'Continuar',exact:true}).click();
    await p.waitForURL('**/onboarding');
    assert.deepEqual(w,[{path:'/settings/model-policy',body:{politica:'codex'}}]);
  });
  await scenario('Claude detectado, sin claves',{motor_detectado:{claude:true,codex:false,ollama:false},politica:'quality_adaptive'},async(p,w)=>{
    await p.getByRole('button',{name:'Continuar',exact:true}).click(); await p.waitForURL('**/onboarding');
    assert.equal(w[0].body.politica,'quality_adaptive'); assert.equal(w.length,1);
  });
  await scenario('Ninguna suscripción disponible',{motor_detectado:{claude:false,codex:false,ollama:false}},async(p)=>{
    await p.getByRole('radio',{name:/Mis suscripciones/}).click();
    assert.equal(await p.getByRole('button',{name:'Continuar',exact:true}).isDisabled(),true);
  });
  await scenario('API existente no vuelve a pedir clave',{politica:'nube',faltan_llaves:{busqueda:true,respaldo:false,openrouter:true}},async(p,w)=>{
    assert.equal(await p.getByLabel('Clave API',{exact:true}).getAttribute('type'),'password');
    await p.getByRole('button',{name:'Continuar',exact:true}).click(); await p.waitForURL('**/onboarding');
    assert.deepEqual(w,[{path:'/settings/model-policy',body:{politica:'nube'}}]);
  });
  await scenario('API ausente bloquea solo esa conexión',{politica:'nube'},async(p)=>{
    assert.equal(await p.getByRole('button',{name:'Continuar',exact:true}).isDisabled(),true);
    await p.getByRole('radio',{name:/Mis suscripciones/}).click();
    assert.equal(await p.getByRole('button',{name:'Continuar',exact:true}).isDisabled(),false);
  });
  await scenario('Voyage opcional y clave oculta',{},async(p)=>{
    await p.getByRole('button',{name:'Búsqueda documental avanzada (opcional)',exact:true}).click();
    assert.equal(await p.getByLabel('Clave API de Voyage AI').getAttribute('type'),'password');
    assert.equal(await p.getByRole('button',{name:'Continuar',exact:true}).isDisabled(),false);
  });
  await scenario('Error de guardado conserva pantalla',{},async(p,w)=>{
    await p.getByRole('button',{name:'Continuar',exact:true}).click();
    await p.getByRole('alert').filter({hasText:'No pude guardar la conexión de prueba.'}).waitFor();
    assert.ok(p.url().endsWith('/activar')); assert.equal(w.length,1);
  },{failPolicy:true});
  await scenario('Aviso de reinicio persiste elección sin bucle',{politica:'nube'},async(p,w)=>{
    await p.getByLabel('Clave API',{exact:true}).fill('synthetic-key-not-a-secret');
    await p.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent==='Continuar')?.disabled);
    await p.getByRole('button',{name:'Continuar',exact:true}).click();
    await p.getByRole('alert').filter({hasText:'Reabre Mia para activar esta cuenta.'}).waitFor();
    assert.equal(w.length,2); assert.equal(w[1].body.politica,'nube');
    assert.equal(await p.getByRole('radio').count(),0,'El aviso es una pantalla terminal, sin cambios descartados');
    await p.getByRole('button',{name:'Continuar',exact:true}).click(); await p.waitForURL('**/onboarding');
    assert.equal(w.length,2);
  },{notice:'Reabre Mia para activar esta cuenta.'});
  writeFileSync(new URL('activation-simplified.json',out),JSON.stringify({synthetic:true,results},null,2));
  console.log(JSON.stringify(results));
} finally { await browser.close(); }
