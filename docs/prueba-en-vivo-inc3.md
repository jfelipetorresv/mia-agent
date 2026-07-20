# Probar en vivo el incremento 3 de MIA

> **Qué es esto.** La "capa 3": encender MIA de verdad en tu máquina y ver los 4 entregables
> del incremento 3 funcionando con tus propios ojos. Las capas 1 (que el código compila y
> tiene sentido) y 2 (revisión independiente) **ya pasaron**; falta esta, la única que no puede
> hacer un revisor: probarlo vivo.
>
> Máquina: Windows 11 · PowerShell · Modo B (nativo). Rama actual: `feat/fase1-inc1-cleanup-scaffolding`.
> Todo se hace dentro de `D:\Inteligencia Artificial\Mia-Super Agent`.

---

## 1 · Encender

Abre **PowerShell** y ejecuta cada bloque en orden. Cada comando lleva una línea de qué hace.

**1. Encender la base de datos de MIA** (la instancia portable, puerto 55432 — sin ella todo da error).
Pega esto **como una sola línea** (no lo cortes en varios renglones o PowerShell da error de "Token inesperado"):
```powershell
& "D:\Inteligencia Artificial\Mia-Super Agent\tools\postgres16-portable\pgsql\bin\pg_ctl.exe" -D "D:\Inteligencia Artificial\Mia-Super Agent\tools\pgdata-portable" -o "-p 55432" -l "D:\Inteligencia Artificial\Mia-Super Agent\tools\pgdata-portable\server.log" start
```
Usa la carpeta de binarios `postgres16-portable` (la que **sí** funciona), no la `-full`. Si dice
"another server might be running" es que ya estaba encendida — perfecto, sigue. Para comprobar que
acepta conexiones de verdad: `& "D:\Inteligencia Artificial\Mia-Super Agent\tools\postgres16-portable\pgsql\bin\pg_isready.exe" -h 127.0.0.1 -p 55432` (debe decir "accepting connections").

**2. Aplicar las novedades de la base (solo la primera vez que pruebes esta rama).** Esto instala
en tu base los cambios 045 y 046 que trae el incremento 3 (procedencia de documentos y la "duda"
del clasificador). Es **idempotente**: puedes correrlo sin miedo, no borra nada.
```powershell
& "D:\Inteligencia Artificial\Mia-Super Agent\mia\scripts\setup_db.ps1"
```
Al final imprime el resultado del **gate de seguridad `test_rls`** (ver punto 4 de "Probar").
> Si se queja de "pgvector no esta instalada": es una **falsa alarma conocida** — ese chequeo mira
> por error el PostgreSQL del sistema (puerto 5432), no el de MIA (55432). Ver "Si algo falla".

**3. Abrir MIA** (enciende cerebro + pantalla y abre el navegador solo en `http://localhost:3100`).
La vía recomendada es **doble-clic en `Abrir Mia.cmd`** (en la carpeta `mia`): así MIA queda
corriendo en TU sesión y no se apaga sola. Equivale a ejecutar:
```powershell
& "D:\Inteligencia Artificial\Mia-Super Agent\mia\scripts\start_all.ps1"
```
> Importante: si MIA la enciende un asistente desde otra sesión (p. ej. Claude Code), los
> servicios pueden morir cuando esa sesión termina. Para trabajar, ábrela tú con el doble-clic.
Deja abiertas las ventanas negras (puedes minimizarlas). El **DurableWorker** —el motor que
procesa la ingesta de documentos en segundo plano— **arranca solo dentro del cerebro de MIA**;
no hay que encender nada aparte.

**4. Verificar que la base quedó al día** (opcional pero recomendado). Abre en el navegador:
`http://127.0.0.1:8000/health` y busca **`"provenance_ready": true`**. Si dice `true`, los cambios
045/046 entraron bien.

---

## 2 · Probar los 4 entregables

Todo pasa **dentro de un asunto**: entra a un asunto (o crea uno) y súbele documentos.

**A. Procedencia + folio (la cita nunca se inventa).**
- Qué hacer: sube un documento al asunto y espera a que MIA lo ingiera.
- ✓ Bien: cuando MIA cita algo del documento, el extracto queda anclado a su **folio/página real**;
  lo que el documento dice se marca como *documento* y lo que MIA infiere queda sujeto al gate de citas.
- ✗ Mal: una cita sin folio, o un folio/página que no corresponde al documento.

**B. Botones del día ("Arrancar el día" / "Cerrar por hoy").**
- Qué hacer: en la vista del asunto verás los botones **Arrancar el día** y **Cerrar por hoy**.
  Pulsa "Arrancar el día" para ver el resumen priorizado (lo que requiere tu decisión, arriba).
  Trabaja un rato y pulsa "Cerrar por hoy".
- ✓ Bien: el cierre **destila lo que tú decidiste** en la sesión y lo guarda en el diario del
  expediente y en el bloque "Pendiente de tu decisión". Además, cuando la conversación se **llena
  (~65%)**, el cierre se dispara **solo**.
- ✗ Mal: el cierre guarda la conversación entera en crudo, o inventa decisiones que no tomaste,
  o no guarda nada cuando sí hubo decisiones.

**C. Clasificador de metadata (tipo / parte / radicado).**
- Qué hacer: sube un documento y mira la ficha que MIA le arma.
- ✓ Bien: MIA rellena **tipo, parte y radicado** cuando está segura. Lo que **duda** no lo escribe:
  aparece en el botón **Documentos por confirmar**, donde lo confirmas **campo por campo**.
- ✗ Mal: MIA rellena con seguridad un dato que en realidad no tenía claro, o no ofrece confirmar
  lo dudoso. (Si tiene clara la ficha de todo, dirá "Nada por confirmar" — eso es correcto.)

**D. Gate crítico `test_rls` (regla dura del repo: si falla, NO se sigue).**
- Qué hacer: ya corrió al final del paso 2; para correrlo suelto:
```powershell
& "D:\Inteligencia Artificial\Mia-Super Agent\mia\.venv\Scripts\python.exe" `
  "D:\Inteligencia Artificial\Mia-Super Agent\mia\execution\test_rls.py"
```
- ✓ Bien: termina con `RESULT: X/X checks PASS` (todos OK).
- ✗ Mal: cualquier `[FAIL]`. **Detente y avísame**: es aislamiento entre despachos, no se avanza
  con esto en rojo.

---

## 3 · Si algo falla (trampas conocidas del entorno)

- **"PoolTimeout" o la pantalla no carga datos** → la base portable no está encendida o no es la
  correcta. Debe escuchar el **puerto 55432**. El **5432** es otro PostgreSQL del sistema con una
  base `mia` vacía que confunde: ignóralo.
- **La base "arranca" pero las conexiones mueren (error `0xC0000142`)** → arrancaste con la carpeta
  de binarios **`postgres16-portable-full`**. Esa engaña: el puerto aparece encendido pero por
  dentro no responde. Usa siempre **`postgres16-portable`** (sin `-full`), como en el paso 1.
- **`setup_db.ps1` dice que falta pgvector** → falsa alarma: su chequeo previo mira el PostgreSQL
  del sistema (5432), no el de MIA. Las migraciones sí van al 55432. Si te bloquea, avísame y lo
  aplicamos por otra vía.
- **`ChunkLoadError: Loading chunk app/layout failed`** en el navegador → el caché de compilación
  quedó desfasado (pasa si se editaron archivos del frontend con el servidor caído, o si se
  relanzó MIA varias veces). Solución: cierra MIA, **borra la carpeta `frontend\.next`**, vuelve a
  abrirla y haz **Ctrl+Shift+R** en el navegador (tu navegador guarda los archivos viejos).
  > OJO: justo después de borrar `.next`, la **primera** carga recompila TODO y puede tardar
  > **~1 minuto**. Durante esa espera el navegador puede mostrar ese mismo `ChunkLoadError` (se
  > cansa de esperar). No refresques en bucle: espera a que el log diga `✓ Compiled / in ...s` y
  > recién ahí refresca — a partir de ahí carga en menos de un segundo.
- **"Conectar carpeta" no hace nada / "no se pudo vincular"** → casi siempre es que el **cerebro
  (8000) está apagado**: el explorador de carpetas recorre tu disco *a través* del servidor local
  de MIA. No es un fallo del programa ni una limitación del navegador; enciende MIA y reintenta.
  (Leer las carpetas tampoco necesita el Motor de IA, solo MIA corriendo e internet.)
- **La API no arranca / "pins alterados"** → el gate `check_env_pins.py` (protección del entorno)
  aborta si algo del `.venv` cambió de versión. Avísame el número que reporta.
- **El chat muestra un error genérico aunque el backend responda** → si hay otra herramienta
  recompilando el frontend en paralelo, corta la respuesta larga. No es bug de producción; reintenta
  con las ventanas de MIA a solas.
- **La ventana del "Motor de IA" (litellm) da error al abrir** → no importa para esta prueba: los 4
  entregables del inc.3 no dependen de ese motor. Puedes cerrarla y seguir con las otras dos ventanas.

---

## Comandos que NO pude verificar con total certeza

- **El chequeo de pgvector dentro de `setup_db.ps1`** apunta al PostgreSQL del sistema (5432), no al
  portable (55432): puede dar una falsa alarma que **frene** la aplicación de migraciones. Las
  migraciones en sí van bien al 55432; si el chequeo bloquea, hay que aplicar 045/046 por otra vía
  (verificar en el momento).
- **Que las migraciones 045/046 no estén ya aplicadas** en tu base portable: no lo pude comprobar sin
  encenderla. El indicador fiable es `"provenance_ready": true` en `http://127.0.0.1:8000/health`
  (paso 4). Si ya está en `true`, puedes saltarte el paso 2.
