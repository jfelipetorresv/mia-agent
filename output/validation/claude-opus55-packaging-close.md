# Opus5.5 high: cierre de distribución

Modelo confirmado: claude-opus-5-5. Solo lectura.

# Dictamen: APTO de artefacto para distribución de Mia 0.3.3 Core/Compact

No encuentro ningún blocker concreto ni incoherencias en la evidencia. Este dictamen solo coteja la evidencia que produjeron otros agentes: no ejecuté pruebas, no calculé hashes, no edité nada y no leí `.env` ni secretos.

## Matriz

| Requisito | Estado | Fuente |
|---|---|---|
| Commit `46edec77…` limpio al build | **PASS** | `build_installer.ps1:80-84` detiene el build si el checkout no está limpio, y el build terminó con `exit_code 0`. El component manifest indica `source_dirty:false` y el commit 46edec7. `:152-156` rechaza los payloads que no coinciden con el commit. |
| Versión 0.3.3 | **PASS** | Coincide en el release manifest, el executor, los checks independientes y el chat. |
| `reused_payloads:false` | **PASS** | Manifest `false` y executor `skip_payloads:false`. |
| Core/Compact | **PASS** | `backend_profile:core`, `webview_profile:compact`, OCR y voz en `false`. |
| first_run real sintético | **PASS** | 308 324 ms. El script solo registra el tiempo si el proceso sale con código 0 y existe `.mia-setup-complete`, con un tope de 900 s (`:260-273`). Se hace sobre `pgdata` temporal y `MIA_APP_DIR` temporal. Después borra su directorio (`:278`), así que solo queda la cifra. Eso es coherente con cómo está escrito el script. |
| Hash, tamaño y copia en Downloads | **PASS** (según root) | SHA-256 `81ba4492…6cc6` y 175 139 638 bytes coinciden en el manifest, el executor, los checks independientes y `release-delivery.json` (Downloads). El tamaño queda por debajo del objetivo de 335 MB. |
| Migraciones | **PASS** | `migrations_matched: 64`. Lo corroboré contando los archivos: `backend/mia/db/migrations/*.sql` tiene 64 (del 003 al 067, sin 001, 002 ni 061). |
| Módulos requeridos | **PASS** | Los 5 módulos están listados con `status: passed`. |
| PG | **PASS indirecto** | `postgres_payload_copy PASS` (1680 archivos), `vector.dll` exigido en `:118` y first_run completado. No hay hash propio del payload `pgsql`. |
| `.env*` privados ausentes | **PASS con reserva** | Solo lo respalda `private_payload_paths: []` de root, y el JSON no dice el alcance: si fue recursivo, si incluyó archivos ocultos ni sobre qué carpeta raíz. No pude corroborarlo porque mi Glob no recorre rutas ocultas (no encuentra `.next/BUILD_ID`, que sí existe). |
| Primera corrida roja preservada | **PASS** | `installer-partial-20260928.json` sigue ahí (2d08474, `failed_frontend_smoke`, first_run y NSIS sin alcanzar) junto con su log original. |
| Segunda corrida con exit 0 | **PASS** | Tiene su propio log `-retry.log`, `exit_code 0` y 15 697 s de duración. |

## Coherencias comprobadas

- **Línea temporal.** El build empezó a las 01:38Z y el backend quedó listo a las 02:35Z, en línea con los 53:54 reportados. El build terminó a las 05:59:54Z, un segundo después de que se creara el manifest (05:59:53Z). El chat final es de las 06:04Z.
- **Backend y LiteLLM pesan exactamente lo mismo que en la corrida roja.** Esto no indica que se reutilizaran: el manifest del backend lleva el commit nuevo y `built_at` 02:35Z, y 46edec7 no toca el backend.
- **El frontend tiene un archivo menos (de 2269 a 2268, 147 bytes menos).** Es compatible con que el fix sacó los logs fuera del payload, aunque no está demostrado.
- **El chat final se hizo sobre el frontend reconstruido.** Su `build_id` es `5LcY-wC9py0kxtdXm9igs`, igual al `.next/BUILD_ID` actual y distinto del de la corrida previa (`4jB2…`).

## Reservas (ninguna bloquea)

1. **Alcance del escaneo de privacidad.** Conviene añadir al JSON de root qué raíces se escanearon y que el escaneo fue recursivo e incluyó ocultos. Es la única comprobación del cierre que se apoya en un resultado vacío sin alcance declarado.
2. **`Cargo.toml` salió como modificado un momento después del build.** Su contenido normalizado es idéntico al de HEAD y la comprobación de limpieza se hace al inicio del build, así que no afecta al resultado.
3. **Avisos del build.** Hubo un timeout al cerrar el proceso hijo de PyInstaller y un mensaje del linker. El executor los revisó y el first_run terminó bien, así que no bloquean.
4. **`docs/empaquetado-033-2026-09-28.md` no recoge la reconstrucción final.** Termina diciendo "aún requiere reconstrucción". Es un desfase del documento, no de la evidencia.
5. **El directorio TEMP de evidencia contiene `app\.env` y `pgdata`.** No están dentro del instalador distribuido y no los leí. Lo menciono solo para que no se interprete como una fuga.

## Pendiente de prueba (límites del APTO)

- Instalación nativa de `Mia_0.3.3_x64-setup.exe`, con `installed: false`.
- WebView2 real dentro de la app instalada. El chat se validó en Edge con APIs sintéticas: 14/14 PASS.
- Backend real con la base de datos instalada, proveedores y modelos reales, y calidad jurídica.
- La causa del timeout original de 20 s sigue sin conocerse.
- Los perfiles con OCR, voz o completo no están validados, y sigue pendiente la reserva sobre la lectura BOM del manifiesto de capacidades.

**Conclusión:** el instalador cumple lo necesario para entregarse como archivo, construido desde un commit limpio sin reutilizar payloads. No es una aceptación de la app instalada ni de su uso con modelos reales.