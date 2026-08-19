## Checkpoint anterior: CP-Z1b — La voz instalada en el producto (2026-07-03)

### Qué cambió (lenguaje simple)

- El dictado por voz ya se instala DESDE LA PANTALLA: tarjeta nueva "Dictado
  por voz" en el Panel de control (sección Conectores) con botón "Instalar
  dictado por voz", confirmación explícita en ámbar, barra de avance de la
  descarga (~700 MB) y mensajes del servidor en llano. Ya no hace falta que un
  administrador corra un script.
- El recorrido "Configura a Mia" tiene el paso 7 "Dictado por voz" (detección
  automática + guía explicativa; "Ir al paso" lleva al Panel).
- El chat del asunto ya tiene el BOTÓN DE MICRÓFONO: dictas, Mia transcribe en
  el servidor del despacho (la voz nunca sale de ahí) e inserta el texto en el
  campo sin borrar lo escrito. Este botón lo construyó Claude Code — Cursor
  hace la revisión visual (capa 3), no la construcción.

### Endpoints para la UI (ya construida — revisar, no construir)

- **`GET /api/speech/status`** → `{estado, listo, mensaje, progreso}` donde
  `estado` ∈ instalado | no_instalado | descargando | error; `progreso` (solo
  descargando) = `{fase, descargado_mb, total_mb, porcentaje}` (total/porcentaje
  pueden ser null si el servidor de descarga no anuncia el tamaño).
- **`POST /api/speech/install`** body `{"confirmar": true}` → `{status, message}`.
  Sin confirmación → 400 con `detail` en llano (mostrarlo tal cual).
- **`POST /api/speech/transcribe`** (de CP-Z1): multipart `audio` WAV PCM16 16k
  + `pulir`; responde `{text, cleaned_text, duration_seconds, message}`.

### Qué revisar visualmente (Cursor — capa 3)

1. **`frontend/app/dashboard/page.tsx` · tarjeta "Dictado por voz"**: estados
   Inactivo / Instalando… (barra `role="progressbar"` con MB) / Instalado;
   confirmación `role="alertdialog"` antes de descargar; Cancelar no descarga;
   tras un error el botón reaparece con el mensaje en ámbar; el refresco es
   automático cada 2 s SOLO mientras descarga.
2. **`frontend/app/configurar/page.tsx`**: el paso 7 "Dictado por voz" se pinta
   con su guía expandible (el contenido viene del servidor — no requirió cambios
   en esta página; verificar que el acordeón y el progreso "N de 7" se vean bien).
3. **Micrófono** (`frontend/app/_components/MicButton.tsx`,
   `frontend/lib/useDictation.ts`, `frontend/lib/wav.ts`, integrado en
   `frontend/app/asuntos/[id]/page.tsx`): estados inactivo → grabando (pulso
   rojo + "Dictando… toca para terminar") → transcribiendo (spinner "Mia está
   escribiendo tu dictado…"); `aria-pressed` alterna; el permiso de micrófono se
   pide solo al primer clic; los errores del backend (400/413/429/503) y el
   aviso "No se escuchó voz en la grabación." salen en ámbar bajo el campo;
   PROBAR CON MICRÓFONO REAL dictando en español (lo único que la verificación
   automatizada no pudo cubrir).

### Comportamiento esperado

- Instalar desde la tarjeta: confirmar → "Empecé a descargar…" → barra avanza →
  la tarjeta pasa sola a "Instalado" (verificado en vivo con descarga real).
- Dictar un clip corto → el texto aparece en el campo en ~1-3 s, agregado al
  final de lo ya escrito. Un clip en silencio → aviso honesto en ámbar.
- Ningún texto visible trae jerga técnica.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_speech_stt.py` extendido 41 → **57/57** (instalador:
  consent-first, single-flight, progreso, retry limpio, tar malicioso rechazado,
  idempotencia — sin descargar los pesos reales); `test_setup_wizard.py`
  **30/30** (7 pasos); regresión completa **ALL PASS (51 suites)**; `npm run
  build` verde ×2; verificación EN VIVO por navegador: tarjeta en sus 3 estados,
  confirmación/cancelar, instalación real (descarga del detector de voz desde
  internet), paso 7 del wizard, botón de micrófono con aria correcta, y POST
  multipart navegador→API con WAV real (CORS OK).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 29.
- Capa 3 (Cursor): PENDIENTE — revisar lo listado arriba (en especial dictar
  con micrófono real).

---

