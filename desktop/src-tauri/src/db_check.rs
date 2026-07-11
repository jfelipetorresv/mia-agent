//! Validación de que el puerto de la base de datos es Postgres de verdad.
//!
//! La adopción por puerto abierto (¿alguien escucha en 127.0.0.1:port?) no
//! basta: cualquier programa puede estar ocupando ese puerto. Antes de
//! adoptar, corremos `pg_isready.exe` — vive en el mismo `pg_bin` que
//! `pg_ctl.exe` en `orchestration.json` — contra host/puerto:
//!
//!   - exit 0 ("accepting connections")  → es Postgres, seguro adoptar.
//!   - exit 1 ("rejecting connections")  → es Postgres arrancando; se
//!     reintenta dentro del deadline.
//!   - cualquier otro resultado (exit 2 "no response", etc.) → se trata
//!     igual: se reintenta hasta el deadline, por si es un falso negativo
//!     transitorio; si nunca confirma, se declara ocupado por un extraño y
//!     NO se adopta.
//!   - el binario `pg_isready.exe` no se pudo ejecutar (instalación rota,
//!     ruta de `pg_bin` incorrecta) → esto NUNCA se confunde con "puerto
//!     ocupado por un extraño": si ningún intento del deadline logró
//!     siquiera correr el binario, el diagnóstico real es una instalación
//!     dañada, no un puerto disputado, y "reinicia el equipo" sería un
//!     consejo inútil. Se distingue con `PgReadyOutcome`.
//!
//! Mantiene el estilo del resto de la cáscara: sin pánicos, todo registrado
//! en `mia-shell.log`. `Command::status()` es bloqueante (hasta 3s por
//! intento); se ejecuta dentro de `spawn_blocking` para no congelar el
//! runtime async mientras corre.

use std::os::windows::process::CommandExt;
use std::path::Path;
use std::process::Command;
use std::time::{Duration, Instant};

use crate::CREATE_NO_WINDOW;

/// Resultado final de `wait_pg_isready`: distingue "puerto ocupado por un
/// extraño que nunca aceptó conexiones" de "no pude ni ejecutar la
/// herramienta" (instalación rota) — cada uno necesita un mensaje distinto
/// para el abogado.
pub enum PgReadyOutcome {
    /// `pg_isready` confirmó "accepting connections".
    Ready,
    /// `pg_isready` corrió al menos una vez pero nunca confirmó dentro del
    /// deadline (puerto ocupado por otro programa).
    PortBusy,
    /// `pg_isready.exe` no pudo ejecutarse en NINGÚN intento del deadline
    /// (instalación de Mia dañada, no un problema de puerto).
    ToolMissing,
}

/// Corre `pg_isready.exe -h 127.0.0.1 -p <port>` una vez (bloqueante).
/// `Some(true)` = exit 0 ("accepting connections"). `Some(false)` = corrió
/// pero no confirmó (exit 1/2/otro). `None` = el binario no pudo ejecutarse.
fn pg_isready_once(pg_bin: &str, port: u16) -> Option<bool> {
    let exe = Path::new(pg_bin).join("pg_isready.exe");
    match Command::new(&exe)
        .args(["-h", "127.0.0.1", "-p", &port.to_string(), "-t", "3"])
        .creation_flags(CREATE_NO_WINDOW)
        .status()
    {
        Ok(status) => Some(status.success()),
        Err(_) => None,
    }
}

/// Reintenta `pg_isready` hasta `deadline_secs` segundos. Cada intento
/// bloqueante corre en `spawn_blocking` para no congelar el runtime async
/// mientras `Command::status()` espera (hasta 3s por intento).
///
/// Devuelve `PgReadyOutcome::Ready` en cuanto confirme "accepting
/// connections"; `PortBusy` si el deadline se cumple pero `pg_isready` sí
/// corrió alguna vez (puerto ocupado por otro programa); `ToolMissing` si
/// NINGÚN intento logró ejecutar el binario (instalación rota).
pub async fn wait_pg_isready(
    log_dir: &Path,
    pg_bin: &str,
    port: u16,
    deadline_secs: u64,
) -> PgReadyOutcome {
    let deadline = Instant::now() + Duration::from_secs(deadline_secs);
    let mut ever_ran = false;
    loop {
        let pg_bin_owned = pg_bin.to_string();
        let outcome = tauri::async_runtime::spawn_blocking(move || pg_isready_once(&pg_bin_owned, port))
            .await
            .unwrap_or(None);
        match outcome {
            Some(true) => return PgReadyOutcome::Ready,
            Some(false) => {
                ever_ran = true;
                crate::log_line(
                    log_dir,
                    &format!("DB: pg_isready aún no confirma Postgres en el puerto {port} (¿arrancando?) — reintento."),
                );
            }
            None => {
                crate::log_line(
                    log_dir,
                    &format!("AVISO: no pude ejecutar pg_isready.exe en '{pg_bin}' — reintento."),
                );
            }
        }
        if Instant::now() > deadline {
            return if ever_ran {
                PgReadyOutcome::PortBusy
            } else {
                PgReadyOutcome::ToolMissing
            };
        }
        tokio::time::sleep(Duration::from_millis(1500)).await;
    }
}
