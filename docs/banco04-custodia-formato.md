# Banco 0.4 — Formato de la custodia (para quien implementa el cargador)

Protocolo: **banco04-v1.2** (`docs/banco-calidad-04-protocolo.md`, §2.3, §8.6 y §10.2 ítems 2-3).

Este documento explica cómo leer la custodia. No describe el contenido de los casos, de las claves ni de las
mutaciones, y nadie que implemente 0.4 necesita verlo. El cargador (`backend/mia/eval/banco04/custodia.py`) descifra
**solo cuando el propósito es medir**: siembra y juicio del Bloque 0, y comparación del Bloque 7. Ante cualquier
discrepancia falla cerrado.

## 1. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Manifiesto de hashes y esquemas (único archivo en el repo) | `backend/mia/eval/banco04/custodia_manifest.json` |
| Carpeta de custodia | la indica la variable de entorno `MIA_BANCO04_CUSTODIA`, que fija el director al medir. Queda fuera del repo, fuera de los `MIA_HOME` del productor y fuera de los directorios de trabajo |
| Llave protegida | `<custodia>/llave.dpapi` |
| Artefactos cifrados | `<custodia>/<archivo>`, con el nombre que da `artefactos[].archivo` del manifiesto |

El cargador **no lleva ninguna ruta por defecto**. Si la variable no existe, o la carpeta o un archivo falta, se
detiene con error.

## 2. Artefactos

En `artefactos[]` del manifiesto hay 13 entradas, con `id`, `tipo`, `archivo`, `sha256_claro`, `sha256_cifrado`,
`bytes_claro`, `formato_claro` y `esquema`.

| `tipo` | ids | esquema |
|---|---|---|
| `caso` | `V1` … `V4` | `banco04-caso/v1` |
| `clave` | `clave-V1` … `clave-V4` | `banco04-clave/v1` |
| `mutaciones_ajuste` | `mut-ajuste` | `banco04-mutaciones/v1` |
| `mutaciones_reservadas` | `mut-reservado` | `banco04-mutaciones/v1` |
| `semilla` | `semilla` | `banco04-semilla/v1` |
| `generador` | `gen-casos`, `gen-mutaciones` | ninguno: código Python que regenera el relleno determinista; no hace falta para cargar |

Los esquemas JSON completos (draft 2020-12) van en `esquemas` del propio manifiesto. Valida contra ellos, no contra
una copia.

## 3. Cómo se descifra

1. **Llave.** Lee `llave.dpapi` y pásala a `CryptUnprotectData` de Windows DPAPI, en el ámbito del usuario actual, sin
   entropía adicional y con `CRYPTPROTECT_UI_FORBIDDEN`. Se obtienen 32 bytes, la llave AES-256. Antes, comprueba que el
   sha256 del blob coincide con `cifrado.llave.sha256_blob_dpapi`. Solo descifra el mismo usuario de Windows en la misma
   máquina.
2. **Por artefacto:**
   - `raw` = bytes del archivo. Exige `sha256(raw) == sha256_cifrado`.
   - `nonce = raw[:12]` y `ct_tag = raw[12:]`; el tag GCM ocupa los 16 bytes finales.
   - `claro = AESGCM(llave).decrypt(nonce, ct_tag, aad)`, con `aad = ("banco04-v1.2|" + id).encode("utf-8")`. Si
     cambian el id o el contenido, falla la autenticación.
   - Exige `sha256(claro) == sha256_claro`.
   - Si hay esquema: `obj = json.loads(claro)`. Exige además que la reserialización canónica dé los mismos bytes:
     `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") == claro`, sin BOM ni
     salto final.
   - Valida `obj` contra `esquemas[esquema]` y contra las `invariantes_semanticas` del manifiesto.
3. **Al terminar** la siembra o el juicio, borra lo descifrado (§2.3). No escribas el claro bajo el repo ni bajo
   `MIA_HOME`.

Referencia mínima (Python, `cryptography` ya está en el `.venv`):

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
raw = (custodia / e["archivo"]).read_bytes()
assert sha256(raw).hexdigest() == e["sha256_cifrado"]
claro = AESGCM(llave).decrypt(raw[:12], raw[12:], f"banco04-v1.2|{e['id']}".encode())
assert sha256(claro).hexdigest() == e["sha256_claro"]
```

DPAPI se llama con `ctypes` (`crypt32.CryptUnprotectData` y luego `kernel32.LocalFree` sobre el buffer de salida).
También sirve `win32crypt.CryptUnprotectData` si `pywin32` está instalado.

## 4. Cómo se usa cada artefacto

**`caso`, que se convierte en `GoldenCase`:**
- `id`, `title`, `message`, `profile`, `synthetic` (siempre `true`) y `expect_reaches_draft` pasan tal cual;
- cada `documents[]` se convierte en `GoldenCaseDoc(filename, tuple(chunks))`;
- `rubric` va vacío;
- `recall_markers` va vacío **a propósito**: sembrar el caso no debe delatar qué está enterrado.

`jurisdicciones` no es un campo de `GoldenCase`. El runner lo lleva a `tenant_settings.config['jurisdictions']` del
despacho efímero: `[]` es un despacho sin ordenamiento (`generic`) y `["co"]` es el pack `co`.

**`clave`:**
- Los índices de fragmento empiezan en 0 (`base_indice_fragmento = 0`) y se cuentan dentro del documento.
- `posicion_global` usa el orden de `orden_documentos`.
- `hechos_materiales[].fragmentos` lista **todos** los fragmentos que contienen el hecho. Con esa lista se decide la
  disponibilidad del §7.2: un hecho está disponible si uno de esos fragmentos entró al prompt.
- `marcadores_auxiliares` alimenta `recall_markers_signal`, que es solo una señal auxiliar (§5.2).
- `puntos_materiales[].tipo` ∈ {`conclusion`, `laguna_real`, `conflicto`, `excepcion`}.
- El esquema sirve también para las claves de los 13 casos existentes (`case_id` libre), que todavía no están
  escritas.

**`mutaciones_*`.** Cada `items[]` es una salida completa que debe recorrer el mismo circuito que la medición real.
- **Material:** `material.mensaje_abogado`; `material.documentos`, que es el expediente completo; `material.mapa_doc`,
  que traduce `[doc n]` a documento y fragmento; `material.fuentes_corpus`, todas ficticias; y `aviso_alcance`, que va
  aparte.
- **Texto juzgado:** `salida.diagnostico` y `salida.borrador`, en bruto, con sus títulos, viñetas y tablas markdown.
- **Verdad de referencia** en `verdad[]`:
  - `clase` ∈ {`defecto`, `control`};
  - `campo` dice en qué texto está;
  - `inicio` y `fin` son posiciones de carácter en ese texto (code points, base 0, fin exclusivo), con
    `salida[campo][inicio:fin] == literal`;
  - `estado_esperado` y `estados_aceptables` dan el estado; `subtipo_esperado` el subtipo;
  - las cláusulas falsas breves (`categoria = C12`) traen además `oracion` y `proporcion_en_oracion`.
- **Regla de detección:** está escrita en `regla_de_deteccion`. Se resuelve sobre la unidad común tras la
  adjudicación.
- **Uso:** el conjunto `ajuste` sirve para depurar los prompts. El `reservado` se usa **una sola vez**, con prompts,
  esquemas y validador ya congelados (§8.6). Después de usarlo deja de ser reservado.
- **Ninguna salida mutada entra a la medición.**

**`semilla`.** `hmac_key_hex` contiene 32 bytes para HMAC-SHA256. Con ella se generan los ids de candidato y el orden
barajado, y se eligen el 15 % de la pasada 2 de Codex y el 10 % de estabilidad.

## 5. Desviaciones y pendientes declarados

- **Mutaciones sobre salidas sintéticas.** §8.6 pide plantar los defectos en salidas reales de la tanda piloto de
  0.3.3, que no existían cuando se construyó la custodia. Las salidas base son sintéticas, escritas por el autor
  independiente sobre mini-expedientes propios. Los mini-expedientes del ajuste y del reservado son disjuntos entre sí y
  con V1-V4. Decide el director.
- **Claves de los 13 casos existentes: pendientes.** El esquema `banco04-clave/v1` las admite.
- **Límite de la custodia.** DPAPI de usuario no protege frente a procesos del mismo usuario de Windows. Los hashes
  delatan una alteración, no una lectura (§2.3).
