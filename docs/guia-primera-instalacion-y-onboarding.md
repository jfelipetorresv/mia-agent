# Primera instalación y prueba de Mia

Estado: instalador interno de prueba. No usar todavía con expedientes reales ni distribuir a terceros.

## Antes de empezar

- Usa una cuenta de Windows de prueba o un equipo donde no importe crear datos locales de Mia.
- Ten una conexión a internet: el instalador incluye el componente de Windows necesario, pero la activación de los modelos requiere tus credenciales configuradas en el primer arranque.
- El instalador actual no está firmado. Windows puede mostrar una advertencia; es esperable en esta fase interna y debe resolverse antes de cualquier distribución externa.

## Instalar

1. Abre `Mia_0.1.0_x64-setup.exe` con doble clic.
2. Elige la instalación para tu usuario y termina el asistente.
3. Abre Mia desde el acceso que crea el instalador. En el primer arranque puede tardar varios minutos mientras prepara su espacio local. No cierres la ventana durante esa preparación.

Mia instala sus datos de prueba en tu perfil de Windows. Desinstalar el programa no debe asumirse como una forma de borrar esos datos: antes de una prueba destructiva, pide que preparemos una limpieza controlada.

## Onboarding que debes completar

1. Registra una cuenta de prueba.
2. Responde las siete pantallas: nombre del despacho, ciudad y país, jurisdicción, clientes y asuntos, límites de autonomía, prohibiciones y criterio de cierre de un escrito.
3. En "Configuración", revisa el recorrido guiado. Lo que no quieras conectar hoy puede dejarse para después y retomarse luego.

## Prueba mínima aceptable

1. Crea un asunto de prueba, sin información real de clientes.
2. Sube un documento ficticio o público.
3. Pregunta cuál es el problema principal y espera el borrador.
4. Revisa que aparezcan las alertas de verificación y aprueba o rechaza el borrador.

La prueba queda aprobada si Mia llega desde registro hasta borrador sin mostrar errores técnicos, si conserva el perfil del despacho y si permite revisar el resultado antes de cerrarlo. Cualquier dato jurídico real o una cita exige después la verificación independiente habitual; esta prueba valida el producto, no una conclusión legal.

## Artefacto validado

- Archivo: `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`.
- Integridad SHA-256: `80748B644C7828577093EE2BF15E09AA5E22F2699760474556F2A33BD5BFF89E`.
- Fecha de generación: 2026-08-12.
