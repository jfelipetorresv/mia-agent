# Protocolo de memoria — ciclo de vida de la información

> Este protocolo define qué se guarda, dónde, cuándo y cómo se mantiene sano un segundo cerebro gestionado por Mia. Aplica a todo agente que escriba en cualquier vault provisionado bajo el framework de Mia. No depende de quién sea el dueño del vault.

---

## 1. Las tres memorias (no se mezclan)

Cada ecosistema con Mia tiene exactamente tres tipos de memoria. Mezclarlas es la causa raíz de la mayoría de inconsistencias.

| Memoria | Dónde vive | Qué guarda | Quién manda |
|---|---|---|---|
| **Canónica** | El vault de Obsidian (`OBSIDIAN_VAULT_PATH`) | Conocimiento reutilizable: jurisprudencia, normativa, plantillas, procedimientos, criterios, perfiles, aprendizajes | El vault. Si contradice la memoria de herramienta, **gana el vault** |
| **De herramienta/sesión** | Memorias internas de Mia, Claude Code, Cursor, etc. | Atajos operativos de esa herramienta en esa instalación (cómo reiniciar X, quirks del entorno, config local) | Cada herramienta. Es caché — si contradice el vault, se actualiza |
| **De repositorio** | `APRENDIZAJES.md`, `docs\`, `HANDOFF.md` en cada repo de código | Errores resueltos, decisiones de arquitectura, traspasos entre herramientas | El repo. Nunca se duplica en el vault |

### Criterio de frontera
- ¿El dato sirve a cualquier LLM en cualquier herramienta? → **vault**
- ¿Solo sirve a una herramienta en esta instalación? → **memoria de herramienta**
- ¿Es sobre el código de un proyecto? → **repo** (vive en `APRENDIZAJES.md` del repo)

---

## 2. Captura

- **En el momento, no al final de la sesión.** Un hallazgo no capturado en el momento se pierde.
- Destino obvio → carpeta correcta directamente. Duda → `inbox\` con frontmatter mínimo.
- Al cierre de una sesión larga: destilar **máximo una nota** con decisiones + próximos pasos. Nunca volcar el transcript completo al vault.
- Fuente siempre declarada en el frontmatter (`fuente:`). Fecha siempre absoluta (`YYYY-MM-DD`).

---

## 3. Clasificación — dónde va cada cosa

| El dato es… | Va en |
|---|---|
| Conocimiento jurídico reutilizable (norma, sentencia, argumento, lección de caso) | Carpeta correspondiente del vault según estructura del vault |
| Preferencia de trabajo, estilo o criterio del dueño del vault | `{{CARPETA_PERFIL}}/aprendizajes.md` |
| Regla de operación nueva o corrección a cómo trabaja el agente | `{{CARPETA_OPERACION}}/reglas-operativas.md` del vault (editar, no crear paralelo) |
| Plantilla o modelo de documento | Carpeta de plantillas del vault |
| Procedimiento interno del despacho | Carpeta de procedimientos del vault |
| Decisión de negocio o hito de un proyecto de software | `APRENDIZAJES.md` o `docs\` del repo correspondiente — **no en el vault** |
| API keys, contraseñas, tokens | `.env` fuera del vault y del repo — **jamás en notas** |
| No sé | `inbox\` |

---

## 4. Consolidación (curaduría)

Cadencia sugerida: **semanal**, o cuando `inbox\` supere 10 notas. Cualquier agente puede ejecutarla si el dueño la solicita.

Pasos en orden:

1. **Vaciar inbox:** clasificar cada nota según §3. Fusionar con notas existentes si ya hay una del tema (nunca duplicar).
2. **Resolver contradicciones:** presentar ambas versiones al dueño, aplicar su decisión, eliminar la sección `## Contradicción detectada`.
3. **Reparar wikilinks rotos** en notas tocadas.
4. **Actualizar `MAPA.md`** si aparecieron o murieron notas estructurales.
5. **Archivar** lo que perdió vigencia: mover a `archivo\` con `estado: archivado`, `fecha_archivo: YYYY-MM-DD` y razón.
6. **Reportar** al dueño en máximo 4 líneas: qué se clasificó, qué se resolvió, qué quedó pendiente, algún riesgo detectado.

---

## 5. Qué NUNCA se guarda en el vault

- Nombres de clientes reales, radicados de expedientes activos, cuantías de casos en curso.
- Secretos: API keys, contraseñas, tokens (van en `.env`, jamás en notas).
- Transcripts completos de conversaciones — solo destilados.
- Documentación técnica de repositorios de código (vive en el repo).
- Datos de terceros no públicos sin consentimiento.

---

## 6. Ingesta de fuentes externas (PDFs, correos, documentos)

1. El archivo fuente **no** se copia al vault; se destila a nota `.md` con `fuente:` apuntando a la ubicación original.
2. Excepción: material para el corpus jurídico central del despacho sigue el pipeline del corpus, no este protocolo.
3. Lotes grandes (carpetas de documentos): proponer al dueño un plan de ingesta antes de procesar — qué se destila, qué se ignora, dónde queda.

---

## 7. Aprendizaje acumulativo de Mia

Mia actualiza el vault progresivamente basándose en señales de uso (ver `AGENTS.md §6`). Este proceso sigue las mismas reglas de captura y clasificación de este protocolo. La diferencia con una ingesta manual es que Mia **propone** la nota y el dueño la **aprueba** antes de que quede en el vault.

El archivo `{{CARPETA_PERFIL}}/aprendizajes.md` es el registro vivo de este aprendizaje. Nunca se reemplaza — solo se agrega (append).

---

*Protocolo de memoria · Mia vault framework v1 · Genérico — aplica a cualquier vault provisionado por Mia*
