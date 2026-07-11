//! Mia — cáscara orquestadora de escritorio.
//!
//! Al abrir la app, este módulo enciende en orden la base de datos portable,
//! el backend y el frontend; muestra una pantalla de arranque en español llano;
//! y al cerrar apaga con orden SOLO lo que esta cáscara arrancó (no toca lo que
//! ya estaba encendido). Toda la configuración vive en `orchestration.json`.

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write as _;
use std::net::{SocketAddr, TcpStream};
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, RunEvent};
use windows_sys::Win32::Foundation::HANDLE;
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

mod db_check;
mod identity;

use db_check::PgReadyOutcome;
use identity::Identity;

/// Windows: no abrir ventana de consola al lanzar procesos hijos.
pub(crate) const CREATE_NO_WINDOW: u32 = 0x0800_0000;

// ---------------------------------------------------------------------------
// Job Object — red de seguridad anti-huérfanos
//
// El apagado ordenado vive en `shutdown()`, pero ese camino solo corre en el
// cierre normal de la ventana. Si la cáscara muere de forma anormal (crash,
// taskkill, cierre de sesión o apagado de Windows), el SO cierra este handle
// y KILL_ON_JOB_CLOSE mata a los procesos que la cáscara lanzó (backend y
// frontend, con sus árboles). La DB NO se asigna al job: pg_ctl termina solo
// y dejar postgres vivo tras una muerte anormal es benigno (se re-adopta).
// ---------------------------------------------------------------------------

struct Job(HANDLE);
// HANDLE es un puntero crudo; el handle del job es válido desde cualquier hilo.
unsafe impl Send for Job {}
unsafe impl Sync for Job {}

impl Job {
    fn new() -> Option<Job> {
        unsafe {
            let h = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if h.is_null() {
                return None;
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                h,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const core::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == 0 {
                return None;
            }
            Some(Job(h))
        }
    }

    /// Mete al proceso (y a los hijos que cree de ahí en adelante) en el job.
    fn assign(&self, child: &Child) -> bool {
        unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle() as HANDLE) != 0 }
    }
}

// ---------------------------------------------------------------------------
// Configuración (orchestration.json)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
struct DbCfg {
    pg_bin: String,
    data_dir: String,
    port: u16,
}

#[derive(Debug, Clone, Deserialize)]
struct BackendCfg {
    cmd: Vec<String>,
    cwd: String,
    #[serde(default)]
    env: HashMap<String, String>,
    health_url: String,
    port: u16,
}

#[derive(Debug, Clone, Deserialize)]
struct FrontendCfg {
    cmd: Vec<String>,
    cwd: String,
    url: String,
    port: u16,
}

/// Paso de PRIMER ARRANQUE (opcional). Si está presente y falta CUALQUIERA de:
/// el marcador `<app_dir>/.mia-setup-complete` (el bootstrap lo escribe SOLO
/// al terminar TODO con éxito), `<db.data_dir>/PG_VERSION`, o —con `app_dir`
/// configurado— `<app_dir>/.env`, la cáscara lo corre ANTES que todo para
/// dejar MIA preparada sola (carpeta de datos, .env semilla, initdb,
/// migraciones). Sin `app_dir` el marcador y el `.env` no se pueden mirar: el
/// gatillo se reduce a `PG_VERSION` (comportamiento de siempre). El triple
/// gatillo existe porque un setup interrumpido justo después de escribir
/// `.env`+`PG_VERSION` (p.ej. falla a media migración) antes NUNCA se
/// re-ejecutaba y dejaba la instalación rota para siempre; el bootstrap es
/// idempotente y resiliente a estados a medias, así que basta con volver a
/// llamarlo. El bootstrap real es Python (`mia-backend.exe --first-run
/// ...`); la cáscara solo decide CUÁNDO llamarlo y muestra el progreso.
#[derive(Debug, Clone, Deserialize)]
struct SetupCfg {
    cmd: Vec<String>,
    cwd: String,
}

/// Motor de modelos LiteLLM (opcional). 4º servicio, entre la DB y el backend.
/// Mismo patrón tri-estado que el backend: puerto libre → lanzar y esperar la
/// salud (liveliness); puerto ocupado → adoptar SOLO con identidad (GET
/// `/v1/models` con `Authorization: Bearer <LITELLM_MASTER_KEY>` del `.env`).
#[derive(Debug, Clone, Deserialize)]
struct LiteLlmCfg {
    cmd: Vec<String>,
    cwd: String,
    #[serde(default)]
    env: HashMap<String, String>,
    health_url: String,
    port: u16,
}

#[derive(Debug, Clone, Deserialize)]
struct OrchCfg {
    #[serde(default)]
    app_dir: Option<String>,
    #[serde(default)]
    setup: Option<SetupCfg>,
    db: DbCfg,
    #[serde(default)]
    litellm: Option<LiteLlmCfg>,
    backend: BackendCfg,
    frontend: FrontendCfg,
}

impl OrchCfg {
    /// Expande los tokens `${exe_dir}` (carpeta del ejecutable de la cáscara) y
    /// `${local_app_data}` (%LOCALAPPDATA%) en TODOS los campos string del
    /// config —rutas, vectores `cmd`, `cwd`, valores de `env`, URLs— en un
    /// ÚNICO punto post-parse. Así el JSON del instalador es estático (F4/NSIS
    /// no templa nada) y la cáscara lo aterriza a la máquina concreta al
    /// cargarlo. Los puertos son numéricos y no llevan token.
    fn expand_tokens(&mut self, exe_dir: &str, local_app_data: &str) {
        let ex = |s: &str| -> String {
            s.replace("${exe_dir}", exe_dir)
                .replace("${local_app_data}", local_app_data)
        };
        if let Some(a) = &self.app_dir {
            self.app_dir = Some(ex(a));
        }
        if let Some(s) = &mut self.setup {
            for c in s.cmd.iter_mut() {
                *c = ex(c);
            }
            s.cwd = ex(&s.cwd);
        }
        self.db.pg_bin = ex(&self.db.pg_bin);
        self.db.data_dir = ex(&self.db.data_dir);
        if let Some(l) = &mut self.litellm {
            for c in l.cmd.iter_mut() {
                *c = ex(c);
            }
            l.cwd = ex(&l.cwd);
            for v in l.env.values_mut() {
                *v = ex(v);
            }
            l.health_url = ex(&l.health_url);
        }
        for c in self.backend.cmd.iter_mut() {
            *c = ex(c);
        }
        self.backend.cwd = ex(&self.backend.cwd);
        for v in self.backend.env.values_mut() {
            *v = ex(v);
        }
        self.backend.health_url = ex(&self.backend.health_url);
        for c in self.frontend.cmd.iter_mut() {
            *c = ex(c);
        }
        self.frontend.cwd = ex(&self.frontend.cwd);
        self.frontend.url = ex(&self.frontend.url);
    }
}

// ---------------------------------------------------------------------------
// Estado que la cáscara "posee" y debe apagar al salir
// ---------------------------------------------------------------------------

#[derive(Default)]
struct Owned {
    db_owned: bool,
    db_pg_bin: String,
    db_data_dir: String,
    litellm_pid: Option<u32>,
    litellm_child: Option<Child>,
    backend_pid: Option<u32>,
    backend_child: Option<Child>,
    frontend_pid: Option<u32>,
    frontend_child: Option<Child>,
    cleaned: bool,
}

struct Shared {
    owned: Mutex<Owned>,
    log_dir: PathBuf,
    job: Option<Job>,
}

// ---------------------------------------------------------------------------
// Evento de progreso hacia la pantalla de arranque
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
struct Progress {
    /// "setup" | "db" | "litellm" | "backend" | "frontend" | "ready" | "error"
    stage: String,
    /// Texto en español llano listo para pintar.
    text: String,
}

// ---------------------------------------------------------------------------
// Logging simple a desktop/logs/mia-shell.log
// ---------------------------------------------------------------------------

pub(crate) fn log_line(log_dir: &Path, msg: &str) {
    let ts = chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f");
    let line = format!("[{ts}] {msg}\n");
    // Consola (útil en dev) + archivo.
    print!("{line}");
    let _ = fs::create_dir_all(log_dir);
    if let Ok(mut f) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("mia-shell.log"))
    {
        let _ = f.write_all(line.as_bytes());
    }
}

// ---------------------------------------------------------------------------
// Localización del orchestration.json
//   1) junto al ejecutable, 2) en el cwd, 3) fallback dev en desktop/
// ---------------------------------------------------------------------------

fn push_candidates(cands: &mut Vec<PathBuf>, start: &Path) {
    let mut cur: Option<PathBuf> = Some(start.to_path_buf());
    let mut depth = 0;
    while let Some(dir) = cur {
        cands.push(dir.join("orchestration.json"));
        cands.push(dir.join("desktop").join("orchestration.json"));
        depth += 1;
        if depth > 6 {
            break;
        }
        cur = dir.parent().map(|p| p.to_path_buf());
    }
}

fn find_config() -> Option<PathBuf> {
    let mut cands: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            push_candidates(&mut cands, d);
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        push_candidates(&mut cands, &cwd);
    }
    cands.into_iter().find(|p| p.exists())
}

// ---------------------------------------------------------------------------
// Utilidades de red y procesos
// ---------------------------------------------------------------------------

/// ¿Hay algo escuchando en 127.0.0.1:port?
fn port_open(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(600)).is_ok()
}

fn emit(app: &AppHandle, stage: &str, text: &str) {
    let _ = app.emit(
        "mia://progress",
        Progress {
            stage: stage.to_string(),
            text: text.to_string(),
        },
    );
}

/// Archivo para redirigir stdout/stderr de un proceso hijo (para diagnóstico).
/// Append: no borrar el diagnóstico del arranque anterior.
fn child_log(log_dir: &Path, name: &str) -> Stdio {
    let _ = fs::create_dir_all(log_dir);
    match OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join(format!("{name}.out.log")))
    {
        Ok(f) => Stdio::from(f),
        Err(_) => Stdio::null(),
    }
}

/// Registra un hijo recién lanzado como "propio". Si el usuario ya cerró la
/// ventana (shutdown corrió antes de que alcanzáramos a registrarlo), lo
/// matamos aquí mismo y abortamos el arranque — sin esto quedaría huérfano.
fn register_child(shared: &Shared, which: &str, child: Child) -> Result<u32, String> {
    let pid = child.id();
    let mut o = shared.owned.lock().unwrap();
    if o.cleaned {
        drop(o);
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        return Err("la ventana se cerró durante el arranque".into());
    }
    match which {
        "litellm" => {
            o.litellm_pid = Some(pid);
            o.litellm_child = Some(child);
        }
        "backend" => {
            o.backend_pid = Some(pid);
            o.backend_child = Some(child);
        }
        _ => {
            o.frontend_pid = Some(pid);
            o.frontend_child = Some(child);
        }
    }
    Ok(pid)
}

/// ¿El hijo registrado murió solo? (fallar rápido en vez de esperar 180 s).
fn child_died(shared: &Shared, which: &str) -> Option<String> {
    let mut o = shared.owned.lock().unwrap();
    let child = match which {
        "litellm" => o.litellm_child.as_mut(),
        "backend" => o.backend_child.as_mut(),
        _ => o.frontend_child.as_mut(),
    }?;
    match child.try_wait() {
        Ok(Some(status)) => Some(format!("{status}")),
        _ => None,
    }
}

/// ¿Ya corrió el apagado? (abortar etapas pendientes del arranque).
fn closing(shared: &Shared) -> bool {
    shared.owned.lock().unwrap().cleaned
}

/// Parser .env mínimo: busca `KEY=VALUE` (ignora líneas vacías y comentarios
/// `#`). Devuelve el valor sin comillas envolventes. Se usa para leer
/// `LITELLM_MASTER_KEY` del `.env` del `app_dir` y poder confirmar la
/// identidad del motor de modelos antes de adoptarlo.
fn read_dotenv_value(env_path: &Path, key: &str) -> Option<String> {
    let content = fs::read_to_string(env_path).ok()?;
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((k, v)) = line.split_once('=') {
            if k.trim() == key {
                let v = v.trim().trim_matches('"').trim_matches('\'');
                return Some(v.to_string());
            }
        }
    }
    None
}

/// Última línea NO vacía de un archivo de texto (el stdout del setup). El
/// bootstrap Python garantiza que su última línea es un mensaje en español
/// llano listo para mostrarle al abogado.
fn last_nonempty_line(path: &Path) -> Option<String> {
    let content = fs::read_to_string(path).ok()?;
    content
        .lines()
        .rev()
        .map(|l| l.trim())
        .find(|l| !l.is_empty())
        .map(|l| l.to_string())
}

/// Corre el paso de PRIMER ARRANQUE (bootstrap Python) y espera a que termine.
/// stdout/stderr van a un archivo fresco para poder mostrar la última línea en
/// llano si falla. El proceso entra al Job Object (red anti-huérfanos) y recibe
/// `MIA_APP_DIR` cuando hay `app_dir` configurado. Timeout: 15 minutos.
async fn run_setup(
    setup: &SetupCfg,
    app_dir: &Option<String>,
    shared: &Shared,
) -> Result<(), String> {
    let log_dir = shared.log_dir.clone();
    let (prog, rest) = setup
        .cmd
        .split_first()
        .ok_or("Mia no pudo prepararse por primera vez")?;

    // stdout/stderr a un archivo FRESCO (truncado) de esta corrida: así la
    // última línea no vacía pertenece siempre a este intento de setup.
    let _ = fs::create_dir_all(&log_dir);
    let setup_log = log_dir.join("setup.out.log");
    let out: Stdio = match fs::File::create(&setup_log) {
        Ok(f) => Stdio::from(f),
        Err(_) => Stdio::null(),
    };
    let err: Stdio = match OpenOptions::new().append(true).open(&setup_log) {
        Ok(f) => Stdio::from(f),
        Err(_) => Stdio::null(),
    };

    let mut command = Command::new(prog);
    command
        .args(rest)
        .current_dir(&setup.cwd)
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(out)
        .stderr(err);
    if let Some(dir) = app_dir {
        command.env("MIA_APP_DIR", dir);
        log_line(&log_dir, &format!("Setup: MIA_APP_DIR={dir}"));
    }

    let mut child = command.spawn().map_err(|e| {
        log_line(&log_dir, &format!("ERROR técnico: spawn setup: {e}"));
        "Mia no pudo prepararse por primera vez".to_string()
    })?;
    if let Some(job) = &shared.job {
        if !job.assign(&child) {
            log_line(&log_dir, "AVISO: no pude asignar el setup al Job Object.");
        }
    }
    let pid = child.id();
    log_line(&log_dir, &format!("Setup: lanzado (PID {pid}). Timeout 15 min."));

    let deadline = Instant::now() + Duration::from_secs(15 * 60);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {}
            Err(e) => {
                log_line(&log_dir, &format!("ERROR técnico: try_wait setup: {e}"));
                return Err("Mia no pudo prepararse por primera vez".into());
            }
        }
        if closing(shared) {
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .status();
            return Err("la ventana se cerró durante el arranque".into());
        }
        if Instant::now() > deadline {
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .status();
            log_line(&log_dir, "ERROR: el setup superó el timeout de 15 min.");
            return Err("la preparación de Mia tardó demasiado — vuelve a abrirla o avísale a soporte".into());
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    };

    if !status.success() {
        let last = last_nonempty_line(&setup_log)
            .unwrap_or_else(|| "no se pudo preparar Mia por primera vez".to_string());
        log_line(
            &log_dir,
            &format!("ERROR: el setup terminó con error ({status}). Última línea: {last}"),
        );
        return Err(last);
    }
    log_line(&log_dir, "Setup: preparación completada.");
    Ok(())
}

// ---------------------------------------------------------------------------
// Secuencia de arranque
// ---------------------------------------------------------------------------

async fn orchestrate(app: AppHandle, cfg: OrchCfg, shared: &Shared) -> Result<(), String> {
    let log_dir = shared.log_dir.clone();
    let started = Instant::now();
    log_line(&log_dir, "=== Arranque de Mia (cáscara) ===");

    let client = reqwest::Client::builder().no_proxy().build().map_err(|e| {
        log_line(&log_dir, &format!("ERROR técnico: cliente HTTP: {e}"));
        "no pude preparar el arranque".to_string()
    })?;

    // --- 0) Primer arranque (setup, opcional) ----------------------------
    // Solo si el bloque `setup` existe Y falta CUALQUIERA de: el marcador
    // `<app_dir>/.mia-setup-complete` (el bootstrap lo escribe SOLO al
    // terminar TODO con éxito), el cluster (`<data_dir>/PG_VERSION`), o —con
    // app_dir configurado— el `.env` semilla. Sin app_dir, el marcador y el
    // .env no se pueden mirar: el gatillo se reduce a PG_VERSION
    // (comportamiento de siempre). Este triple gatillo evita que un setup
    // interrumpido justo después de escribir .env+PG_VERSION (p.ej. falla a
    // media migración) deje la instalación rota para siempre sin volver a
    // re-ejecutarse; el bootstrap es idempotente y resiliente a estados a
    // medias, así que volver a llamarlo es seguro.
    if let Some(setup) = &cfg.setup {
        let marker_missing = cfg
            .app_dir
            .as_ref()
            .map(|d| !Path::new(d).join(".mia-setup-complete").exists())
            .unwrap_or(false);
        let pg_version_missing = !Path::new(&cfg.db.data_dir).join("PG_VERSION").exists();
        let env_missing = cfg
            .app_dir
            .as_ref()
            .map(|d| !Path::new(d).join(".env").exists())
            .unwrap_or(false);
        if marker_missing || pg_version_missing || env_missing {
            if closing(shared) {
                return Err("la ventana se cerró durante el arranque".into());
            }
            emit(
                &app,
                "setup",
                "Preparando Mia por primera vez, puede tardar unos minutos…",
            );
            log_line(
                &log_dir,
                &format!("Setup: primer arranque (marcador falta={marker_missing}, PG_VERSION falta={pg_version_missing}, .env falta={env_missing}) — preparo Mia."),
            );
            run_setup(setup, &cfg.app_dir, shared).await?;
        } else {
            log_line(&log_dir, "Setup: ya preparado (marcador, PG_VERSION y .env presentes) — omito.");
        }
    }

    // --- a) Base de datos ------------------------------------------------
    emit(&app, "db", "Encendiendo la base de datos del despacho…");
    if port_open(cfg.db.port) {
        // El puerto abierto no basta: puede ser cualquier programa. Antes de
        // adoptar, exigimos que pg_isready.exe confirme el protocolo Postgres
        // ("accepting connections", exit 0). Si Postgres apenas está
        // arrancando (exit 1, "rejecting connections") reintentamos dentro
        // del mismo deadline de 60s que usa un arranque en frío.
        log_line(
            &log_dir,
            &format!("DB: puerto {} abierto — validando con pg_isready que sea Postgres antes de adoptar.", cfg.db.port),
        );
        match db_check::wait_pg_isready(&log_dir, &cfg.db.pg_bin, cfg.db.port, 60).await {
            PgReadyOutcome::Ready => {
                log_line(
                    &log_dir,
                    &format!("DB: pg_isready confirma Postgres en el puerto {} — la adopto, no la apagaré.", cfg.db.port),
                );
            }
            PgReadyOutcome::PortBusy => {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: puerto {} abierto pero pg_isready nunca confirmó Postgres dentro del deadline.", cfg.db.port),
                );
                return Err("otro programa está ocupando el lugar de la base de datos de Mia — reinicia el equipo".into());
            }
            PgReadyOutcome::ToolMissing => {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: pg_isready.exe nunca pudo ejecutarse en '{}' (instalación dañada).", cfg.db.pg_bin),
                );
                return Err("no encuentro las herramientas de la base de datos de Mia — reinstala Mia o avísale a soporte".into());
            }
        }
    } else {
        log_line(&log_dir, &format!("DB: puerto {} libre — la enciendo.", cfg.db.port));
        let pg_ctl = Path::new(&cfg.db.pg_bin).join("pg_ctl.exe");
        let status = Command::new(&pg_ctl)
            .args(["-D", &cfg.db.data_dir, "-w", "-t", "60", "start"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(child_log(&log_dir, "db"))
            .stderr(child_log(&log_dir, "db"))
            .status()
            .map_err(|e| {
                log_line(&log_dir, &format!("ERROR técnico: pg_ctl: {e}"));
                "la base de datos no encendió".to_string()
            })?;
        if !status.success() {
            return Err("la base de datos no encendió".into());
        }
        // Registrar la propiedad YA, antes del wait: si el usuario cierra la
        // ventana durante la espera, shutdown() debe saber que la DB es nuestra.
        {
            let mut o = shared.owned.lock().unwrap();
            if o.cleaned {
                drop(o);
                let _ = Command::new(&pg_ctl)
                    .args(["-D", &cfg.db.data_dir, "stop", "-m", "fast"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .status();
                return Err("la ventana se cerró durante el arranque".into());
            }
            o.db_owned = true;
            o.db_pg_bin = cfg.db.pg_bin.clone();
            o.db_data_dir = cfg.db.data_dir.clone();
        }
        // Confirmar que quedó escuchando.
        let deadline = Instant::now() + Duration::from_secs(60);
        while !port_open(cfg.db.port) {
            if Instant::now() > deadline {
                return Err("la base de datos no respondió a tiempo".into());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        log_line(&log_dir, "DB: encendida por la cáscara (la apagaré al salir).");
    }

    // --- a2) Motor de modelos (LiteLLM) — opcional, entre DB y backend ----
    // Solo si el bloque `litellm` está en el config (dev sin él = 3 servicios,
    // comportamiento intacto). Mismo patrón tri-estado que el backend: puerto
    // libre → lanzar hijo propio (basta liveliness); puerto ocupado → adoptar
    // SOLO con identidad (GET /v1/models + Bearer <LITELLM_MASTER_KEY> del
    // .env). Nunca adoptar por un simple 200 (lección voicebox).
    if let Some(litellm) = &cfg.litellm {
        if closing(shared) {
            return Err("la ventana se cerró durante el arranque".into());
        }
        emit(&app, "litellm", "Encendiendo el motor de modelos…");
        if port_open(litellm.port) {
            // Puerto ocupado: exigir identidad. La master key vive en el .env
            // del app_dir; sin app_dir / sin .env / sin la key NO se adopta.
            let master_key = cfg
                .app_dir
                .as_ref()
                .map(|d| Path::new(d).join(".env"))
                .and_then(|p| read_dotenv_value(&p, "LITELLM_MASTER_KEY"))
                .filter(|k| !k.is_empty());
            let master_key = match master_key {
                Some(k) => k,
                None => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: puerto {} ocupado y no hay LITELLM_MASTER_KEY en el .env (o falta app_dir/.env) — no puedo confirmar que sea el motor de modelos de Mia.", litellm.port),
                    );
                    return Err(format!(
                        "El puerto {} está ocupado por otra aplicación — ciérrala o reinicia el equipo",
                        litellm.port
                    ));
                }
            };
            let mut adopted = false;
            for _ in 0..5 {
                match identity::litellm_identity(&client, litellm.port, &master_key).await {
                    Identity::Mia => {
                        adopted = true;
                        break;
                    }
                    Identity::NotMia => {
                        log_line(
                            &log_dir,
                            &format!("ERROR técnico: el puerto {} responde pero NO es el motor de modelos de Mia (/v1/models sin los alias claude-haiku y mia-local).", litellm.port),
                        );
                        return Err(format!(
                            "El puerto {} está ocupado por otra aplicación — ciérrala o reinicia el equipo",
                            litellm.port
                        ));
                    }
                    Identity::NoResponse => {}
                }
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
            if !adopted {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: puerto {} ocupado por un proceso que no responde como el motor de modelos de Mia.", litellm.port),
                );
                return Err(format!(
                    "El puerto {} está ocupado por otra aplicación — ciérrala o reinicia el equipo",
                    litellm.port
                ));
            }
            log_line(
                &log_dir,
                &format!("LiteLLM: puerto {} responde y es Mia (/v1/models con alias propios) — lo adopto, no lo apagaré.", litellm.port),
            );
        } else {
            log_line(&log_dir, "LiteLLM: lo enciendo.");
            let (prog, rest) = litellm
                .cmd
                .split_first()
                .ok_or("Mia no pudo encender el motor de modelos")?;
            let mut command = Command::new(prog);
            command
                .args(rest)
                .current_dir(&litellm.cwd)
                .creation_flags(CREATE_NO_WINDOW)
                .stdout(child_log(&log_dir, "litellm"))
                .stderr(child_log(&log_dir, "litellm"));
            for (k, v) in &litellm.env {
                command.env(k, v);
            }
            if let Some(app_dir) = &cfg.app_dir {
                command.env("MIA_APP_DIR", app_dir);
            }
            let child = command.spawn().map_err(|e| {
                log_line(&log_dir, &format!("ERROR técnico: spawn litellm: {e}"));
                "Mia no pudo encender el motor de modelos".to_string()
            })?;
            if let Some(job) = &shared.job {
                if !job.assign(&child) {
                    log_line(&log_dir, "AVISO: no pude asignar litellm al Job Object.");
                }
            }
            let pid = register_child(shared, "litellm", child)?;
            log_line(&log_dir, &format!("LiteLLM: lanzado (PID {pid}). Esperando su salud (liveliness)…"));
            // Hijo propio: basta liveliness (2xx en health_url). Falla rápida
            // si el proceso muere; latido visible tras 8 s.
            let wait_start = Instant::now();
            let deadline = wait_start + Duration::from_secs(180);
            loop {
                // child_died PRIMERO: si el hijo murió y un squatter rápido
                // ya ocupó el puerto, un health-check hecho antes podría leer
                // ese squatter como "vivo" y nunca reportar la muerte real.
                if let Some(status) = child_died(shared, "litellm") {
                    log_line(&log_dir, &format!("ERROR técnico: litellm terminó solo ({status})."));
                    return Err("Mia no pudo encender el motor de modelos".into());
                }
                if let Identity::Mia = identity::litellm_health(&client, &litellm.health_url).await {
                    break;
                }
                if closing(shared) {
                    return Err("la ventana se cerró durante el arranque".into());
                }
                if Instant::now() > deadline {
                    return Err("el motor de modelos tardó demasiado en encender".into());
                }
                let secs = wait_start.elapsed().as_secs();
                if secs >= 8 {
                    emit(&app, "litellm", &format!("Encendiendo el motor de modelos… ({secs} s)"));
                }
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
            log_line(&log_dir, "LiteLLM: salud OK (liveliness).");
        }
    }

    // --- b) Backend ------------------------------------------------------
    if closing(shared) {
        return Err("la ventana se cerró durante el arranque".into());
    }
    emit(&app, "backend", "Despertando a Mia…");
    if port_open(cfg.backend.port) {
        // Puerto tomado: adoptar solo si responde salud Y ES MIA de verdad.
        // Lección real (2026-07-10): en esta máquina el 8000 estuvo ocupado
        // por voicebox-server.exe, una app ajena que respondía 200 — la
        // identidad se valida contra el JSON de /health (ver identity.rs).
        // Margen de reintentos por si MIA está terminando de arrancar; si
        // responde pero NO es MIA, fallar YA (reintentar es inútil).
        let mut adopted = false;
        for _ in 0..5 {
            match identity::backend_identity(&client, &cfg.backend.health_url).await {
                Identity::Mia => {
                    adopted = true;
                    break;
                }
                Identity::NotMia => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: el puerto {} responde 200 pero NO es el backend de MIA (health sin las claves propias db/pgvector/embed_model).", cfg.backend.port),
                    );
                    return Err("otro programa está ocupando el lugar de Mia — ciérralo o reinicia el equipo".into());
                }
                Identity::NoResponse => {}
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        if !adopted {
            log_line(
                &log_dir,
                &format!("ERROR técnico: puerto {} ocupado por un proceso que no responde salud.", cfg.backend.port),
            );
            return Err("otro programa está ocupando el lugar de Mia — reinicia el equipo".into());
        }
        log_line(
            &log_dir,
            &format!("Backend: puerto {} responde y es MIA (health con claves propias) — lo adopto, no lo apagaré.", cfg.backend.port),
        );
    } else {
        log_line(&log_dir, "Backend: lo enciendo.");
        let (prog, rest) = cfg
            .backend
            .cmd
            .split_first()
            .ok_or("Mia no pudo encender su motor")?;
        let mut command = Command::new(prog);
        command
            .args(rest)
            .current_dir(&cfg.backend.cwd)
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(child_log(&log_dir, "backend"))
            .stderr(child_log(&log_dir, "backend"));
        for (k, v) in &cfg.backend.env {
            command.env(k, v);
        }
        if let Some(app_dir) = &cfg.app_dir {
            command.env("MIA_APP_DIR", app_dir);
            log_line(&log_dir, &format!("Backend: MIA_APP_DIR={app_dir}"));
        }
        let child = command.spawn().map_err(|e| {
            log_line(&log_dir, &format!("ERROR técnico: spawn backend: {e}"));
            "Mia no pudo encender su motor".to_string()
        })?;
        if let Some(job) = &shared.job {
            if !job.assign(&child) {
                log_line(&log_dir, "AVISO: no pude asignar el backend al Job Object.");
            }
        }
        let pid = register_child(shared, "backend", child)?;
        log_line(&log_dir, &format!("Backend: lanzado (PID {pid}). Esperando su salud e identidad…"));
        // Polling del health cada 2s, timeout 180s (puede tardar en importar),
        // con latido visible y falla rápida si el proceso muere.
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            // child_died PRIMERO: si el hijo murió y un squatter rápido ya
            // ocupó el puerto, un health-check hecho antes podría leer ese
            // squatter como "vivo" y nunca reportar la muerte real.
            if let Some(status) = child_died(shared, "backend") {
                log_line(&log_dir, &format!("ERROR técnico: el backend terminó solo ({status})."));
                return Err("Mia no pudo despertar".into());
            }
            // Misma exigencia de identidad que al adoptar: si un tercero ganó
            // la carrera por el puerto y responde 200 sin ser MIA, fallar YA.
            match identity::backend_identity(&client, &cfg.backend.health_url).await {
                Identity::Mia => break,
                Identity::NotMia => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: el puerto {} responde 200 pero NO es el backend de MIA (¿un tercero ganó la carrera por el puerto?).", cfg.backend.port),
                    );
                    return Err("otro programa está ocupando el lugar de Mia — ciérralo o reinicia el equipo".into());
                }
                Identity::NoResponse => {}
            }
            if closing(shared) {
                return Err("la ventana se cerró durante el arranque".into());
            }
            if Instant::now() > deadline {
                return Err("Mia tardó demasiado en despertar".into());
            }
            let secs = wait_start.elapsed().as_secs();
            if secs >= 8 {
                emit(
                    &app,
                    "backend",
                    &format!("Despertando a Mia… ({secs} s — la primera vez puede tardar unos minutos)"),
                );
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        log_line(&log_dir, "Backend: salud OK y es MIA (health con claves propias).");
    }

    // --- c) Frontend -----------------------------------------------------
    if closing(shared) {
        return Err("la ventana se cerró durante el arranque".into());
    }
    emit(&app, "frontend", "Preparando tu pantalla…");
    if port_open(cfg.frontend.port) {
        // "Responde 200" NO basta: así se llegó a adoptar el Next.js de OTRO
        // proyecto ("Intelligence Sura") que ocupaba el 3100 en esta máquina,
        // y el abogado vio la app equivocada. La identidad se valida con la
        // huella de cabeceras que frontend/next.config.mjs fija en todas las
        // rutas de MIA (ver identity.rs). Si responde pero NO es MIA, fallar
        // YA — jamás navegar a una app ajena.
        let mut adopted = false;
        for _ in 0..5 {
            match identity::frontend_identity(&client, &cfg.frontend.url).await {
                Identity::Mia => {
                    adopted = true;
                    break;
                }
                Identity::NotMia => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: el puerto {} responde 200 pero NO es la pantalla de MIA (sin la huella de cabeceras propia).", cfg.frontend.port),
                    );
                    return Err("otro programa está ocupando el lugar de la pantalla de Mia — ciérralo o reinicia el equipo".into());
                }
                Identity::NoResponse => {}
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        if !adopted {
            log_line(
                &log_dir,
                &format!("ERROR técnico: puerto {} ocupado por un proceso que no responde.", cfg.frontend.port),
            );
            return Err("otro programa está ocupando el lugar de la pantalla de Mia — reinicia el equipo".into());
        }
        log_line(
            &log_dir,
            &format!("Frontend: puerto {} responde y es MIA (huella de cabeceras) — lo adopto, no lo apagaré.", cfg.frontend.port),
        );
    } else {
        log_line(&log_dir, "Frontend: lo enciendo.");
        let (prog, rest) = cfg
            .frontend
            .cmd
            .split_first()
            .ok_or("no pude preparar la pantalla")?;
        // El server.js del standalone (instalado) toma el puerto de la env
        // PORT y el host de HOSTNAME. Fijamos PORT al puerto configurado y
        // LIMPIAMOS HOSTNAME: si el sistema lo trae seteado (nombre de equipo
        // que resuelve a una IP de VPN), el server escucharía en esa IP y ni
        // localhost ni 127.0.0.1 conectarían (gotcha de build_frontend.ps1).
        // En dev (npm run start -- -p 3100) ambos coinciden en 3100: inocuo.
        let child = Command::new(prog)
            .args(rest)
            .current_dir(&cfg.frontend.cwd)
            .creation_flags(CREATE_NO_WINDOW)
            .env("PORT", cfg.frontend.port.to_string())
            .env_remove("HOSTNAME")
            .stdout(child_log(&log_dir, "frontend"))
            .stderr(child_log(&log_dir, "frontend"))
            .spawn()
            .map_err(|e| {
                log_line(&log_dir, &format!("ERROR técnico: spawn frontend: {e}"));
                "no pude preparar la pantalla".to_string()
            })?;
        if let Some(job) = &shared.job {
            if !job.assign(&child) {
                log_line(&log_dir, "AVISO: no pude asignar el frontend al Job Object.");
            }
        }
        let pid = register_child(shared, "frontend", child)?;
        log_line(&log_dir, &format!("Frontend: lanzado (PID {pid}). Esperando 200 e identidad…"));
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            // child_died PRIMERO: si el hijo murió y un squatter rápido ya
            // ocupó el puerto, un health-check hecho antes podría leer ese
            // squatter como "vivo" y nunca reportar la muerte real.
            if let Some(status) = child_died(shared, "frontend") {
                log_line(&log_dir, &format!("ERROR técnico: el frontend terminó solo ({status})."));
                return Err("la pantalla no pudo prepararse".into());
            }
            // Misma exigencia de identidad que al adoptar: nunca navegar a
            // una app ajena aunque responda 200 en el puerto esperado.
            match identity::frontend_identity(&client, &cfg.frontend.url).await {
                Identity::Mia => break,
                Identity::NotMia => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: el puerto {} responde 200 pero NO es la pantalla de MIA (¿un tercero ganó la carrera por el puerto?).", cfg.frontend.port),
                    );
                    return Err("otro programa está ocupando el lugar de la pantalla de Mia — ciérralo o reinicia el equipo".into());
                }
                Identity::NoResponse => {}
            }
            if closing(shared) {
                return Err("la ventana se cerró durante el arranque".into());
            }
            if Instant::now() > deadline {
                return Err("la pantalla tardó demasiado en prepararse".into());
            }
            let secs = wait_start.elapsed().as_secs();
            if secs >= 8 {
                emit(&app, "frontend", &format!("Preparando tu pantalla… ({secs} s)"));
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        log_line(&log_dir, "Frontend: 200 OK y es MIA (huella de cabeceras).");
    }

    // --- d) Navegar a la app ---------------------------------------------
    emit(&app, "ready", "Listo. Entrando a Mia…");
    let secs = started.elapsed().as_secs();
    log_line(&log_dir, &format!("Todo listo en {secs}s. Navegando a {}.", cfg.frontend.url));
    if let Some(win) = app.get_webview_window("main") {
        match tauri::Url::parse(&cfg.frontend.url) {
            Ok(url) => {
                if let Err(e) = win.navigate(url) {
                    log_line(&log_dir, &format!("ERROR técnico: navigate: {e}"));
                    return Err("no pude abrir la pantalla de Mia".into());
                }
            }
            Err(e) => {
                log_line(&log_dir, &format!("ERROR técnico: URL inválida: {e}"));
                return Err("no pude abrir la pantalla de Mia".into());
            }
        }
    } else {
        return Err("no pude abrir la pantalla de Mia".into());
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Apagado ordenado — solo lo que la cáscara arrancó
// ---------------------------------------------------------------------------

fn shutdown(app: &AppHandle) {
    let shared = app.state::<Shared>();
    let log_dir = shared.log_dir.clone();
    let mut o = match shared.owned.lock() {
        Ok(g) => g,
        Err(p) => p.into_inner(),
    };
    if o.cleaned {
        return;
    }
    o.cleaned = true;
    log_line(&log_dir, "=== Cierre: apagando lo que arrancó la cáscara ===");

    // Matar árboles de procesos hijos (npm/node, python) por PID, en orden
    // INVERSO al arranque: frontend → backend → litellm → db.
    for (name, pid) in [
        ("frontend", o.frontend_pid),
        ("backend", o.backend_pid),
        ("litellm", o.litellm_pid),
    ] {
        if let Some(pid) = pid {
            let res = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .status();
            log_line(&log_dir, &format!("Cierre: taskkill {name} (PID {pid}) -> {res:?}"));
        }
    }

    // Apagar la DB SOLO si la encendió esta cáscara.
    if o.db_owned {
        let pg_ctl = Path::new(&o.db_pg_bin).join("pg_ctl.exe");
        let res = Command::new(&pg_ctl)
            .args(["-D", &o.db_data_dir, "stop", "-m", "fast"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        log_line(&log_dir, &format!("Cierre: pg_ctl stop -m fast -> {res:?}"));
    } else {
        log_line(&log_dir, "Cierre: la DB no era mía — la dejo encendida.");
    }
    log_line(&log_dir, "=== Cierre completo ===");
}

// ---------------------------------------------------------------------------
// Entrada
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Guard de instancia única — DEBE ser el primer plugin del builder
        // (los plugins corren en el orden en que se registran). Si ya hay una
        // cáscara abierta, esta segunda invocación nunca llega a `.setup()`
        // (el plugin la mata antes): no toca la DB/backend/frontend ya
        // encendidos por la primera. La primera instancia recibe el aviso y
        // trae su ventana al frente.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .setup(|app| {
            // Localizar y cargar la configuración.
            let cfg_path = find_config();
            let log_dir = cfg_path
                .as_ref()
                .and_then(|p| p.parent())
                .map(|d| d.join("logs"))
                .unwrap_or_else(|| PathBuf::from("logs"));

            let job = Job::new();
            if job.is_none() {
                log_line(&log_dir, "AVISO: sin Job Object — el apagado dependerá solo del cierre normal.");
            }
            app.manage(Shared {
                owned: Mutex::new(Owned::default()),
                log_dir: log_dir.clone(),
                job,
            });

            let handle = app.handle().clone();

            match cfg_path {
                None => {
                    log_line(&log_dir, "ERROR: no encontré orchestration.json.");
                    emit(
                        &handle,
                        "error",
                        "Algo no encendió bien: no encuentro la configuración del sistema — cierra y vuelve a abrir; si persiste, contacta a soporte.",
                    );
                }
                Some(path) => {
                    log_line(&log_dir, &format!("Config: {}", path.display()));
                    match fs::read_to_string(&path)
                        .map_err(|e| e.to_string())
                        .and_then(|s| serde_json::from_str::<OrchCfg>(&s).map_err(|e| e.to_string()))
                    {
                        Err(e) => {
                            log_line(&log_dir, &format!("ERROR leyendo config: {e}"));
                            emit(
                                &handle,
                                "error",
                                "Algo no encendió bien: la configuración del sistema está dañada — cierra y vuelve a abrir; si persiste, contacta a soporte.",
                            );
                        }
                        Ok(mut cfg) => {
                            // Punto ÚNICO de expansión de tokens: ${exe_dir}
                            // (carpeta del ejecutable de la cáscara) y
                            // ${local_app_data} (%LOCALAPPDATA%). El JSON del
                            // instalador es estático; aquí se aterriza a la máquina.
                            let exe_dir = std::env::current_exe()
                                .ok()
                                .and_then(|p| p.parent().map(|d| d.to_string_lossy().into_owned()))
                                .unwrap_or_default();
                            let local_app_data =
                                std::env::var("LOCALAPPDATA").unwrap_or_default();
                            if exe_dir.is_empty() || local_app_data.is_empty() {
                                // Si no podemos resolver alguno de los dos,
                                // sustituirlo por cadena vacía dejaría rutas
                                // sin sentido (p. ej. "/Mia" a secas) que
                                // fallarían más adelante con un error críptico.
                                // Abortamos aquí mismo, en llano.
                                log_line(
                                    &log_dir,
                                    &format!(
                                        "ERROR: no pude resolver las carpetas de instalación (exe_dir vacío={}, local_app_data vacío={}).",
                                        exe_dir.is_empty(),
                                        local_app_data.is_empty()
                                    ),
                                );
                                emit(
                                    &handle,
                                    "error",
                                    "MIA no pudo determinar sus carpetas de instalación — cierra y vuelve a abrir; si persiste, contacta a soporte.",
                                );
                            } else {
                                cfg.expand_tokens(&exe_dir, &local_app_data);
                                log_line(
                                    &log_dir,
                                    &format!("Config: tokens expandidos (exe_dir={exe_dir}, local_app_data={local_app_data})."),
                                );
                                let handle2 = handle.clone();
                                tauri::async_runtime::spawn(async move {
                                    // Pequeña espera para que la pantalla de arranque
                                    // enganche el listener de eventos antes del primer emit.
                                    tokio::time::sleep(Duration::from_millis(700)).await;
                                    let shared = handle2.state::<Shared>();
                                    if let Err(e) = orchestrate(handle2.clone(), cfg, &shared).await {
                                        log_line(&shared.log_dir, &format!("ERROR de arranque: {e}"));
                                        emit(
                                            &handle2,
                                            "error",
                                            &format!(
                                                "Algo no encendió bien: {e} — cierra y vuelve a abrir; si persiste, contacta a soporte."
                                            ),
                                        );
                                    }
                                });
                            }
                        }
                    }
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error al iniciar la cáscara de Mia")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                shutdown(app_handle);
            }
        });
}
