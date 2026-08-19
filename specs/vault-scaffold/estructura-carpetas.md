# Estructura de carpetas — vaults Mia

> Guía de referencia para el script `create_vault_scaffold.py`. Define qué carpetas existen, para qué sirven, cuáles son obligatorias y cuáles son opcionales según el rol del dueño del vault.

---

## Carpetas obligatorias (todo vault)

Estas carpetas existen en **todos** los vaults sin excepción. Son la infraestructura mínima que hace legible el vault a cualquier LLM.

| Carpeta | Propósito |
|---|---|
| `inbox\` | Aterrizaje temporal de lo nuevo sin clasificar. Zona de cuarentena. |
| `archivo\` | Notas deprecadas. Nada se borra; se archiva aquí con fecha y razón. |

## Archivos obligatorios (raíz del vault)

| Archivo | Propósito |
|---|---|
| `AGENTS.md` | Reglas de juego — el LLM lo lee primero siempre |
| `MAPA.md` | Hub de navegación — índice vivo de todas las notas estructurales |
| `log.md` | Línea de tiempo append-only: ingestas, curadurías, consultas importantes |

---

## Carpetas de contenido — por tipo de vault

### Vault de despacho (base de conocimiento compartida)

Usado por: `create_vault_scaffold.py` con `tipo="despacho"`.

| Carpeta | Propósito | Obligatoria |
|---|---|---|
| `Jurisprudencia\` | Sentencias, ratio decidendi, precedentes | Sí (despacho) |
| `Doctrina\` | Autores, artículos, posiciones doctrinales | Sí (despacho) |
| `Normativa\` | Leyes, decretos, artículos clave anotados | Sí (despacho) |
| `Modelos-y-plantillas\` | Modelos de escritos, cláusulas, checklists | Sí (despacho) |
| `Procedimientos-internos\` | Flujos del despacho, SOPs, guías de calidad | Sí (despacho) |
| `Criterios-y-notas\` | Criterios propios, notas de estrategia, aprendizajes (anonimizados) | Sí (despacho) |
| `00-perfil-despacho\` | Identidad del despacho y aprendizajes acumulativos de Mia | Sí (despacho) |
| `_templates\` | Plantillas internas (prefijo `_` → ignoradas por sync) | Sí (despacho) |

### Vault personal de abogado (segundo cerebro individual)

Usado por: `create_vault_scaffold.py` con `tipo="abogado"`.

| Carpeta | Propósito | Obligatoria |
|---|---|---|
| `00-perfil\` | Quién es el abogado: rol, materias, cómo trabaja, preferencias | Sí |
| `01-operacion\` | Cómo trabaja: sus reglas propias, su protocolo de memoria | Sí |
| `02-juridico\` | Su conocimiento jurídico de trabajo (cuaderno, no corpus central) | Sí (litigante) |
| `03-casos\` | Una nota por caso activo (solo vault 100% local, sin remoto) | Opcional |
| `04-contenido\` | Si produce contenido o formación | Opcional |
| `05-personal\` | Si pidió ámbito personal | Opcional |
| `06-bitacora\` | Artefactos recurrentes de rutinas automatizadas | Opcional |

---

## Convenciones de nomenclatura

- Carpetas con prefijo numérico (`00-`, `01-`) → orden de lectura sugerido para el LLM.
- Archivos con prefijo `_` → ignorados por `obsidian_sync.py` (no se indexan en Mia).
- Carpetas con prefijo `.` → ignoradas por `obsidian_sync.py` (`.obsidian\`, `.git\`).
- Nombres en español, sin espacios, con guiones: `Modelos-y-plantillas`, `Procedimientos-internos`.

---

## Regla de corpus

El conocimiento jurídico **reutilizable y verificado** (argumentos, jurisprudencia citada, plantillas aprobadas) no se fragmenta en vaults personales. Se propone al corpus central del despacho. Los vaults personales son cuadernos de trabajo, no bibliotecas.

---

## Qué NO va en ninguna carpeta

- Expedientes de clientes activos con datos identificables.
- Secretos (API keys, contraseñas, tokens).
- Transcripts completos de conversaciones.
- Documentación técnica de repositorios de código (vive en el repo).

---

*Guía de estructura · Mia vault framework v1*
