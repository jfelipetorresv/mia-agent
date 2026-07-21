# F6 — E2E en frío: máquina 100% limpia

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F6". Precede a la Sesión Pipe B (cierre de todo el plan).

## Objetivo
Probar la instalación, primer arranque y recorrido completo en una máquina Windows verdaderamente
limpia (sin nada del entorno de desarrollo), incluyendo actualización y falla a mitad de camino.

## Pasos
1. VM Windows limpia con snapshot (reintentos baratos): instalar el `.exe`, primer arranque,
   recorrido de F3 completo sobre la instancia instalada. Guion de observación con capturas (el
   mismo guion sirve para Sesión Pipe B).
2. **Honesto**: el frío verdadero es semi-manual — provisionar la VM y observar diálogos de
   SmartScreen/Firewall exige un humano al menos una vez. Sin firma Azure Trusted Signing,
   SmartScreen es fricción documentada, no bloqueo.
3. **Más allá de la instalación feliz** (corrección de Codex): probar también la ACTUALIZACIÓN
   (instalar una versión previa → actualizar sin perder datos) y la falla a mitad de camino
   (migración interrumpida → mensaje accionable en lenguaje llano + log útil, nunca una instalación
   a medias silenciosa).

## Archivos críticos
El instalador NSIS producido en F5 (`desktop/src-tauri/target/release/bundle/nsis/`); guion de
observación (nuevo, compartido con Sesión Pipe B).

## Salida medible (copiada del plan maestro)
En VM desde snapshot: instalación → arranque → recorrido → diagnóstico con anclas → borrador
aprobado, sin terminal ni edición de archivos, cronometrado; DOS corridas desde snapshot para
descartar suerte; actualización y falla-a-mitad probadas.

## Gates
Dos corridas independientes desde snapshot con el mismo resultado; prueba de actualización sin
pérdida de datos; prueba de falla a mitad de camino con mensaje accionable (no instalación silenciosa
a medias).

## Nota de ejecución
Requiere preparación de un humano (provisión de VM, diálogos de SmartScreen/Firewall) — no es
100% automatizable por el orquestador. Coordinar con Pipe el turno de VM antes de correr esta fase.
