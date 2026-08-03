"""
create_vault_scaffold.py
Mia — vault governance scaffold creator

Crea la estructura completa de un vault de Obsidian con gobierno Mia desde las plantillas
en mia/specs/vault-scaffold/. El vault resultante tiene AGENTS.md, MAPA.md, protocolo
de memoria, estructura de carpetas y archivos semilla — listo desde el día 1.

Uso:
    python create_vault_scaffold.py --tipo despacho --nombre "Lexia Abogados" \
        --ruta "D:/Vaults/Lexia-Vault" --materias "seguros,fiscal,PASC,arbitraje"

    python create_vault_scaffold.py --tipo abogado --nombre "María García" \
        --ruta "C:/Users/mgarcia/Vaults/Maria-OS" \
        --materias "seguros,responsabilidad civil" --rol "Abogada litigante"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Literal

# Windows: forzar UTF-8 en stdout para manejar caracteres especiales
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
MIA_ROOT = SCRIPT_DIR.parent  # mia/
SPECS_DIR = MIA_ROOT / "specs" / "vault-scaffold"


# ---------------------------------------------------------------------------
# Estructura de carpetas por tipo de vault
# ---------------------------------------------------------------------------

ESTRUCTURA_DESPACHO = {
    "carpetas_contenido": [
        "Jurisprudencia",
        "Doctrina",
        "Normativa",
        "Modelos-y-plantillas",
        "Procedimientos-internos",
        "Criterios-y-notas",
        "00-perfil-despacho",
        "_templates",
    ],
    "carpeta_perfil": "00-perfil-despacho",
    "carpeta_operacion": "01-operacion",
    "secciones_mapa": [
        ("Jurisprudencia", "Sentencias, ratio decidendi, precedentes de referencia"),
        ("Doctrina", "Autores, artículos, posiciones doctrinales"),
        ("Normativa", "Leyes, decretos, artículos clave anotados"),
        ("Modelos y plantillas", "Modelos de escritos, cláusulas, checklists"),
        ("Procedimientos internos", "Flujos del despacho, SOPs, guías de calidad"),
        ("Criterios y notas", "Criterios propios, aprendizajes de casos cerrados (anonimizados)"),
    ],
    "filas_enrutamiento": [
        ("Investigar jurisprudencia", "`Jurisprudencia\\`"),
        ("Buscar doctrina o autores", "`Doctrina\\`"),
        ("Consultar norma o artículo", "`Normativa\\`"),
        ("Usar o crear un modelo de escrito", "`Modelos-y-plantillas\\`"),
        ("Seguir un procedimiento del despacho", "`Procedimientos-internos\\`"),
        ("Recuperar criterio o aprendizaje", "`Criterios-y-notas\\`"),
    ],
    "guia_rapida": (
        "¿Jurisprudencia?        → Jurisprudencia\\\n"
        "¿Doctrina?              → Doctrina\\\n"
        "¿Norma o decreto?       → Normativa\\\n"
        "¿Modelo de escrito?     → Modelos-y-plantillas\\\n"
        "¿Flujo del despacho?    → Procedimientos-internos\\\n"
        "¿Criterio/aprendizaje?  → Criterios-y-notas\\\n"
        "¿No sé dónde va?        → inbox\\ (con frontmatter mínimo)"
    ),
}

ESTRUCTURA_ABOGADO = {
    "carpetas_contenido": [
        "00-perfil",
        "01-operacion",
        "02-juridico",
        # inbox y archivo se crean siempre por separado — no duplicar aquí
    ],
    "carpetas_opcionales": [
        "03-casos",
        "04-contenido",
        "05-personal",
        "06-bitacora",
    ],
    "carpeta_perfil": "00-perfil",
    "carpeta_operacion": "01-operacion",
    "secciones_mapa": [
        ("00-perfil", "Quién es el abogado: rol, materias, voz, preferencias"),
        ("01-operacion", "Cómo trabaja: reglas propias, protocolo de memoria"),
        ("02-juridico", "Conocimiento jurídico de trabajo (cuaderno personal)"),
    ],
    "filas_enrutamiento": [
        ("Consulta jurídica de trabajo", "`02-juridico\\`"),
        ("Preferencias o estilo del abogado", "`00-perfil\\`"),
        ("Regla de operación o flujo", "`01-operacion\\`"),
    ],
    "guia_rapida": (
        "¿Perfil o voz?          → 00-perfil\\\n"
        "¿Regla de trabajo?      → 01-operacion\\\n"
        "¿Conocimiento jurídico? → 02-juridico\\\n"
        "¿No sé dónde va?        → inbox\\ (con frontmatter mínimo)"
    ),
}


# ---------------------------------------------------------------------------
# Lectura de plantillas
# ---------------------------------------------------------------------------

def _read_template(name: str) -> str:
    path = SPECS_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Plantilla no encontrada: {path}\n"
            "Asegúrate de que mia/specs/vault-scaffold/ esté completo."
        )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Generación de contenido
# ---------------------------------------------------------------------------

def _build_agents_md(
    *,
    nombre: str,
    ruta: str,
    organizacion: str,
    materias: str,
    tipo: Literal["despacho", "abogado"],
    rol: str,
    estructura: dict,
    fecha: str,
) -> str:
    """Genera el AGENTS.md instanciado desde la plantilla."""
    template = _read_template("AGENTS-template.md")

    # Carpetas para la sección §1 (excluye inbox/archivo que se listan por separado)
    carpetas_del_tipo = [
        c for c in estructura["carpetas_contenido"]
        if c not in ("inbox", "archivo")
    ]
    carpetas_str = "\n".join(f"  {c}\\" for c in carpetas_del_tipo)
    carpetas_str += "\n  inbox\\\n  archivo\\"

    # Filas de enrutamiento para §3
    # La plantilla tiene un bloque genérico con {{FILA_TAREA_N}} que reemplazamos en bloque
    filas = "\n".join(
        f"| {tarea} | {destino} | — |"
        for tarea, destino in estructura["filas_enrutamiento"]
    )
    # Reemplazar todo el bloque de filas genéricas de la plantilla
    import re as _re
    result = (
        template
        .replace("{{NOMBRE_VAULT}}", nombre)
        .replace("{{RUTA_VAULT}}", ruta)
        .replace("{{ORGANIZACION}}", organizacion)
        .replace("{{MATERIAS}}", materias)
        .replace("{{ROL}}", rol)
        .replace("{{CARPETAS_PRINCIPALES}}", carpetas_str)
        .replace("{{CARPETA_PERFIL}}", estructura["carpeta_perfil"])
        .replace("{{FECHA_HOY}}", fecha)
        .replace("{{NOMBRE_RESPONSABLE}}", nombre)
    )
    # Reemplazar el bloque completo de filas de enrutamiento (3 filas genéricas en la plantilla)
    result = _re.sub(
        r"\| \{\{FILA_TAREA_\d+\}\} \| \{\{DESTINO_\d+\}\} \| — \|\n?",
        "",
        result,
    )
    # Insertar las filas reales donde estaba la primera fila genérica
    # (ya eliminadas arriba; insertar antes de la fila de Guardar información)
    result = result.replace(
        "| Guardar información nueva |",
        filas + "\n| Guardar información nueva |",
    )
    return result


def _build_mapa_md(
    *,
    nombre: str,
    estructura: dict,
    fecha: str,
) -> str:
    """Genera el MAPA.md construyendo el contenido directamente (más fiable que regex sobre plantilla)."""
    # Construir directamente en vez de parsear la plantilla con regex
    # (la plantilla sirve como referencia visual; el contenido real se genera aquí)
    mapa = f"""---
name: MAPA
tipo: gobierno
area: transversal
estado: activo
fecha-revision: "{fecha}"
tags: [gobierno, navegación, índice]
relacionados:
  - "[[AGENTS]] (las reglas; este archivo es la navegación)"
---

# MAPA.md — Hub de navegación de {nombre}

> Leer después de `AGENTS.md` y antes de entrar a cualquier carpeta. Este es el índice vivo del vault — se actualiza cada vez que se agrega una nota estructural. Si `MAPA.md` está desactualizado, el vault está sucio.

---

## Estado del vault

| Métrica | Valor |
|---|---|
| Última curaduría | *(pendiente)* |
| Notas en inbox | 0 |
| Total notas estructurales | 0 |
| Última ingesta | *(vacío)* |

---

## Secciones del vault

"""
    for seccion, descripcion in estructura["secciones_mapa"]:
        mapa += f"### {seccion} — {descripcion}\n\n"
        mapa += "| Nota | Resumen |\n|---|---|\n| *(vacío — primera ingesta vía agente)* | |\n\n---\n\n"

    mapa += f"""## Archivos de gobierno

| Archivo | Rol |
|---|---|
| [[AGENTS]] | Reglas de juego — leer primero siempre |
| [[MAPA]] | Este archivo — índice vivo |

---

## Inbox y archivo

- **`inbox\\`** — zona de cuarentena. Si tiene ≥ 10 notas, curar antes de seguir ingiriendo.
- **`archivo\\`** — notas deprecadas. Nunca se borran, se mueven aquí con `estado: archivado` y razón.

---

## Guía rápida de enrutamiento

```
{estructura["guia_rapida"]}
```

---

## Historial de curadurías

| Fecha | Quién | Acciones |
|---|---|---|
| *(primera curaduría pendiente)* | | |

---

*Última actualización: {fecha} · Mantener este mapa actualizado es responsabilidad del agente que escribe en el vault.*
"""
    return mapa


def _build_log_md(nombre: str, fecha: str) -> str:
    return f"""# log.md — Línea de tiempo del vault

> Append-only. Una línea por evento: ingesta, curaduría, consulta importante. El agente escribe aquí después de cada acción sustantiva en el vault.

| Fecha | Tipo | Descripción |
|---|---|---|
| {fecha} | scaffold | Vault creado por `create_vault_scaffold.py` · instancia: {nombre} |
"""


def _build_identidad_md(
    *,
    nombre: str,
    materias: str,
    tipo: Literal["despacho", "abogado"],
    rol: str,
    fecha: str,
) -> str:
    if tipo == "despacho":
        return f"""---
tipo: perfil
area: identidad-despacho
fecha: {fecha}
fuente: onboarding Mia
estado: borrador
---

# Identidad del despacho — {nombre}

> Quién es el despacho. Mia lee este archivo antes de cualquier escrito para calibrar el contexto. Editar con aprobación del responsable.

## Nombre
{nombre}

## Áreas de práctica
{materias}

## Cómo trabaja el despacho
*(completar en onboarding: flujos principales, herramientas, preferencias de estilo)*

## Qué espera de Mia
*(completar con el primer uso: qué tareas delega, qué aprueba siempre, qué nunca delega)*

## Notas de adaptación
*(Mia agrega aquí aprendizajes del despacho con aprobación del responsable)*
"""
    else:
        return f"""---
tipo: perfil
area: perfil-abogado
fecha: {fecha}
fuente: onboarding Mia
estado: borrador
---

# Perfil — {nombre}

> Quién es {nombre}. Mia lee este archivo antes de cualquier tarea para calibrar contexto y estilo. Solo se modifica con instrucción directa del dueño.

## Nombre y rol
{nombre} — {rol}

## Materias de trabajo
{materias}

## Cómo trabaja
*(completar: preferencias de comunicación, nivel de detalle esperado, qué delega a Mia)*

## Cómo hablarle
*(completar: directo, formal, con advertencias primero, etc.)*
"""


def _build_aprendizajes_md(nombre: str, fecha: str) -> str:
    return f"""---
tipo: perfil
area: aprendizajes-mia
fecha: {fecha}
fuente: sistema
estado: activo
---

# Aprendizajes acumulativos — {nombre}

> Log append-only. Mia agrega aquí con aprobación del dueño del vault.
> Cada entrada: fecha + señal + aprendizaje + qué cambia en el comportamiento de Mia.

## Formato de entrada
```
### YYYY-MM-DD — [tipo de señal]
**Señal:** descripción de lo que hizo el abogado/despacho
**Aprendizaje:** qué aprendió Mia de esa señal
**Impacto:** cómo cambia el comportamiento de Mia en adelante
```

---

*(sin entradas aún — Mia las agrega con aprobación después de cada sesión significativa)*
"""


def _build_protocolo_memoria_md(
    *,
    nombre: str,
    carpeta_perfil: str,
    carpeta_operacion: str,
    fecha: str,
) -> str:
    """Instancia el protocolo de memoria reemplazando placeholders."""
    template = _read_template("protocolo-memoria.md")
    return (
        template
        .replace("{{CARPETA_PERFIL}}", carpeta_perfil)
        .replace("{{CARPETA_OPERACION}}", carpeta_operacion)
        .replace("{{NOMBRE_VAULT}}", nombre)
    )


# ---------------------------------------------------------------------------
# Creación del vault
# ---------------------------------------------------------------------------

def create_vault(
    *,
    tipo: Literal["despacho", "abogado"],
    nombre: str,
    ruta: str | Path,
    materias: str,
    organizacion: str = "",
    rol: str = "",
    force: bool = False,
) -> Path:
    """
    Crea el scaffold completo de un vault Mia en la ruta indicada.

    Args:
        tipo: "despacho" (vault compartido del despacho) o "abogado" (segundo cerebro personal)
        nombre: Nombre del vault / despacho / abogado
        ruta: Ruta absoluta donde crear el vault
        materias: Materias de trabajo separadas por coma
        organizacion: Nombre del despacho (para vaults de abogado)
        rol: Rol del abogado (solo para tipo="abogado")
        force: Si True, no falla si la carpeta ya existe

    Returns:
        Path al vault creado
    """
    vault_path = Path(ruta).resolve()
    fecha = date.today().isoformat()
    estructura = ESTRUCTURA_DESPACHO if tipo == "despacho" else ESTRUCTURA_ABOGADO

    # Validaciones
    if vault_path.exists() and not force:
        existing_files = list(vault_path.iterdir())
        if existing_files:
            raise ValueError(
                f"La ruta '{vault_path}' ya existe y no está vacía.\n"
                "Usa --force para sobreescribir (solo agrega archivos faltantes, no borra)."
            )
    vault_path.mkdir(parents=True, exist_ok=True)

    org = organizacion or nombre

    print(f"\n[INFO] Creando vault '{nombre}' en {vault_path}...\n")

    # 1. Carpetas de contenido
    for carpeta in estructura["carpetas_contenido"]:
        (vault_path / carpeta).mkdir(exist_ok=True)
        print(f"  [DIR] {carpeta}\\")

    # Carpetas obligatorias de sistema
    (vault_path / "inbox").mkdir(exist_ok=True)
    (vault_path / "archivo").mkdir(exist_ok=True)
    print("  [DIR] inbox\\")
    print("  [DIR] archivo\\")

    # 2. AGENTS.md
    agents_path = vault_path / "AGENTS.md"
    if not agents_path.exists() or force:
        agents_content = _build_agents_md(
            nombre=nombre,
            ruta=str(vault_path),
            organizacion=org,
            materias=materias,
            tipo=tipo,
            rol=rol,
            estructura=estructura,
            fecha=fecha,
        )
        agents_path.write_text(agents_content, encoding="utf-8")
        print("  [OK] AGENTS.md")

    # 3. MAPA.md
    mapa_path = vault_path / "MAPA.md"
    if not mapa_path.exists() or force:
        mapa_content = _build_mapa_md(nombre=nombre, estructura=estructura, fecha=fecha)
        mapa_path.write_text(mapa_content, encoding="utf-8")
        print("  [OK] MAPA.md")

    # 4. log.md
    log_path = vault_path / "log.md"
    if not log_path.exists():
        log_path.write_text(_build_log_md(nombre, fecha), encoding="utf-8")
        print("  [OK] log.md")

    # 5. Perfil / identidad
    carpeta_perfil = estructura["carpeta_perfil"]
    perfil_fname = "identidad.md" if tipo == "despacho" else "perfil.md"
    identidad_path = vault_path / carpeta_perfil / perfil_fname
    if not identidad_path.exists():
        identidad_path.write_text(
            _build_identidad_md(
                nombre=nombre,
                materias=materias,
                tipo=tipo,
                rol=rol,
                fecha=fecha,
            ),
            encoding="utf-8",
        )
        print(f"  [OK] {carpeta_perfil}/{perfil_fname}")

    # 6. aprendizajes.md
    aprendizajes_path = vault_path / carpeta_perfil / "aprendizajes.md"
    if not aprendizajes_path.exists():
        aprendizajes_path.write_text(
            _build_aprendizajes_md(nombre, fecha),
            encoding="utf-8",
        )
        print(f"  [OK] {carpeta_perfil}/aprendizajes.md")

    # 7. 01-operacion/protocolo-memoria.md
    carpeta_op = estructura["carpeta_operacion"]
    op_dir = vault_path / carpeta_op
    op_dir.mkdir(exist_ok=True)
    protocolo_path = op_dir / "protocolo-memoria.md"
    if not protocolo_path.exists():
        protocolo_content = _build_protocolo_memoria_md(
            nombre=nombre,
            carpeta_perfil=carpeta_perfil,
            carpeta_operacion=carpeta_op,
            fecha=fecha,
        )
        protocolo_path.write_text(protocolo_content, encoding="utf-8")
        print(f"  [OK] {carpeta_op}/protocolo-memoria.md")

    # 8. inbox/README.md
    inbox_readme = vault_path / "inbox" / "README.md"
    if not inbox_readme.exists():
        inbox_readme.write_text(
            f"""# inbox -- zona de cuarentena

Lo nuevo sin clasificar aterriza aqui. Cuando haya >= 10 notas, curar antes de seguir ingiriendo.

**Frontmatter minimo para notas de inbox:**
```yaml
---
tipo: inbox
area: <tema>
fecha: YYYY-MM-DD
fuente: <origen>
estado: borrador
---
```

*Creado por Mia scaffold · {fecha}*
""",
            encoding="utf-8",
        )
        print("  [OK] inbox/README.md")

    # 9. Copiar reglas-operativas-base.md como referencia
    rulebase_src = SPECS_DIR / "reglas-operativas-base.md"
    rulebase_dst = op_dir / "reglas-operativas-base.md"
    if rulebase_src.exists() and not rulebase_dst.exists():
        shutil.copy2(rulebase_src, rulebase_dst)
        print(f"  [OK] {carpeta_op}/reglas-operativas-base.md")

    perfil_file = "identidad.md" if tipo == "despacho" else "perfil.md"
    print(f"\n[OK] Vault '{nombre}' creado en {vault_path}")
    print("\nProximos pasos:")
    print(f"   1. Abre '{vault_path}' como vault en Obsidian (Open folder as vault)")
    print(f"   2. Configura OBSIDIAN_VAULT_PATH en .env")
    print(f"   3. Completa los datos en '{carpeta_perfil}/{perfil_file}'")
    print("   4. Edita las filas de enrutamiento en AGENTS.md parrafo 3 segun tus materias")
    print("   5. Corre el primer sync: python execution/init_knowledge_stores.py --skip-vault")

    return vault_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea el scaffold de un vault Mia desde las plantillas de specs/vault-scaffold/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Vault del despacho
  python create_vault_scaffold.py --tipo despacho --nombre "Lexia Abogados" \\
      --ruta "D:/Vaults/Lexia-Vault" --materias "seguros,fiscal,PASC,arbitraje"

  # Segundo cerebro de un abogado
  python create_vault_scaffold.py --tipo abogado --nombre "María García" \\
      --ruta "C:/Users/mgarcia/Vaults/Maria-OS" \\
      --materias "seguros,responsabilidad civil" \\
      --rol "Abogada litigante" --organizacion "Lexia Abogados"
        """,
    )
    parser.add_argument(
        "--tipo",
        choices=["despacho", "abogado"],
        required=True,
        help="Tipo de vault: 'despacho' (base compartida) o 'abogado' (segundo cerebro personal)",
    )
    parser.add_argument("--nombre", required=True, help="Nombre del vault / despacho / abogado")
    parser.add_argument("--ruta", required=True, help="Ruta absoluta donde crear el vault")
    parser.add_argument(
        "--materias",
        required=True,
        help="Materias de trabajo separadas por coma (ej: seguros,fiscal,arbitraje)",
    )
    parser.add_argument(
        "--organizacion",
        default="",
        help="Nombre del despacho (para vaults de abogado)",
    )
    parser.add_argument("--rol", default="", help="Rol del abogado (para tipo=abogado)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="No falla si la carpeta ya existe; agrega archivos faltantes sin borrar",
    )

    args = parser.parse_args()

    try:
        create_vault(
            tipo=args.tipo,
            nombre=args.nombre,
            ruta=args.ruta,
            materias=args.materias,
            organizacion=args.organizacion,
            rol=args.rol,
            force=args.force,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
