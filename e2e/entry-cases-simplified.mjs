import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
const base=process.env.MIA_UI_TEST_URL || 'http://localhost:3111';
const out=new URL('../output/playwright/',import.meta.url);mkdirSync(out,{recursive:true});
const browser=await chromium.launch();const results=[];
try {
 for(const theme of ['light','dark']) {
  const c=await browser.newContext({viewport:{width:theme==='light'?1200:390,height:900}});
  await c.addInitScript(t=>{localStorage.setItem('mia_token','synthetic');localStorage.setItem('mia-theme',t)},theme);
  const p=await c.newPage();let complete=false;const writes=[];const errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  const headers={'access-control-allow-origin':'*','access-control-allow-headers':'authorization,content-type','access-control-allow-methods':'GET,POST,OPTIONS'};
  await p.route('http://mia-shell.localhost/**',r=>r.fulfill({headers,json:{ok:true,data:{recovery_key_saved:true}}}));
  await p.route('http://localhost:8000/**',async r=>{
    const q=r.request(),path=new URL(q.url()).pathname;
    if(q.method()==='OPTIONS')return r.fulfill({status:204,headers});
    let json={};
    if(path==='/api/auth/me')json={name:'Prueba',tenant_id:'synthetic'};
    if(path==='/api/onboarding/status')json={completed:complete};
    if(path==='/api/onboarding/complete'){writes.push(q.postDataJSON());complete=true;json={completed:true};}
    if(path==='/api/matters'&&q.method()==='GET')json=[];
    if(path==='/api/atajos')json={atajos:[]};
    if(path==='/api/matters'&&q.method()==='POST')return r.fulfill({status:503,headers,json:{detail:'Fallo sintético de guardado'}});
    return r.fulfill({headers,json});
  });
  await p.goto(base+'/onboarding',{waitUntil:'domcontentloaded',timeout:180000});
  await p.getByRole('button',{name:'Crear mi primer caso',exact:true}).waitFor();
  assert.equal(await p.locator('input').count(),0,'Sin entrevista obligatoria');
  await p.getByText('Tu espacio está listo.',{exact:true}).last().waitFor();
  await p.screenshot({path:fileURLToPath(new URL(`entry-${theme}.png`,out)),fullPage:true});
  await p.getByRole('button',{name:'Crear mi primer caso',exact:true}).click();
  await p.getByRole('dialog',{name:'Nuevo caso'}).waitFor({timeout:120000});
  assert.deepEqual(writes,[{responses:{}}]);
  assert.equal(await p.getByRole('radio').count(),0,'No hay modos de entrega');
  const name=p.getByLabel('Nombre',{exact:true});await name.fill('Caso sintético');
  await p.screenshot({path:fileURLToPath(new URL(`new-case-${theme}.png`,out)),fullPage:true});
  const request=p.waitForRequest(q=>q.method()==='POST'&&new URL(q.url()).pathname==='/api/matters');
  await p.getByRole('button',{name:'Crear caso',exact:true}).click();
  assert.deepEqual((await request).postDataJSON(),{name:'Caso sintético',description:''});
  await p.getByRole('alert').filter({hasText:'No se pudo crear el caso.'}).waitFor();
  assert.equal(await name.inputValue(),'Caso sintético','Conserva contexto ante error');
  assert.deepEqual(errors,[]);results.push({theme,passed:true});await c.close();
 }
 writeFileSync(new URL('entry-cases-simplified.json',out),JSON.stringify({synthetic:true,results},null,2));console.log(JSON.stringify(results));
} finally {await browser.close();}

