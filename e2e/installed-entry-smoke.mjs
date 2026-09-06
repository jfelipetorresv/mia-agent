// Comprueba la instalación real sin abrir asuntos ni cambiar conexiones.
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
const version='0.3.2';
const browser=await chromium.connectOverCDP('http://127.0.0.1:9231');
try {
 const page=browser.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://localhost:3100'));
 assert.ok(page,'Ventana real de Mia');
 await page.waitForLoadState('domcontentloaded');
 const bridge=await page.evaluate(async()=>{
   const result={};
   for(const p of ['runtime/health','maintenance/status']){
     const r=await fetch('http://mia-shell.localhost/'+p,{method:'POST',headers:{'Content-Type':'text/plain'},body:'{}',signal:AbortSignal.timeout(15000)});
     result[p]=await r.json();
   }
   return result;
 });
 assert.equal(bridge['runtime/health'].ok,true);assert.equal(bridge['maintenance/status'].ok,true);
 const health=await (await fetch('http://127.0.0.1:8000/health',{signal:AbortSignal.timeout(15000)})).json();
 assert.equal(health.status,'ok');assert.equal(health.db,true);assert.equal(health.checkpointer,true);
 assert.equal(health.migrations_applied,health.migrations_expected);
 const signedIn=await page.evaluate(()=>Boolean(localStorage.getItem('mia_token')));
 let activationVisible=false;
 if(signedIn){
   await page.goto('http://localhost:3100/activar',{waitUntil:'domcontentloaded',timeout:60000});
   await page.getByRole('radio',{name:/Mis suscripciones/}).waitFor({timeout:30000});
   activationVisible=true;
   assert.equal(await page.getByRole('radio',{name:/Calidad jurídica adaptativa/}).count(),0);
 }
 const out=new URL('../output/playwright/',import.meta.url);mkdirSync(out,{recursive:true});
 await page.screenshot({path:fileURLToPath(new URL(`mia-installed-${version}.png`,out)),fullPage:true});
 const result={version,passed:true,native_bridges:true,health:true,migrations:health.migrations_applied,activationVisible,changed_connections:false,opened_matters:false,created_user:false};
 writeFileSync(new URL(`mia-installed-${version}.json`,out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
