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
use std::sync::atomic::{AtomicBool, Ordering};
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
    #[serde(default)]
    maintenance: Option<SetupCfg>,
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
        if let Some(m) = &mut self.maintenance {
            for c in m.cmd.iter_mut() {
                *c = ex(c);
            }
            m.cwd = ex(&m.cwd);
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
    /// Config + app_dir del motor de modelos, RETENIDOS para poder re-lanzarlo
    /// en caliente (comando `restart_litellm`). Se rellena al inicio de
    /// `orchestrate` (antes de que `cfg` se consuma). `None` = no hay bloque
    /// litellm en el config (dev, 3 servicios) → el reinicio no aplica.
    litellm: Mutex<Option<(LiteLlmCfg, Option<String>)>>,
    /// Comando local privilegiado (backup/llave). Solo lo invoca Tauri; no HTTP.
    maintenance: Mutex<Option<(SetupCfg, Option<String>)>>,
    /// Serializa exportación/confirmación/backup invocados desde la interfaz.
    maintenance_running: AtomicBool,
    /// Serializa un reinicio de litellm en curso (evita dos reinicios a la vez).
    restarting: AtomicBool,
}

const SUPERVISOR_INTERVAL: Duration = Duration::from_secs(5);
const SUPERVISOR_FAILURES_BEFORE_RESTART: u8 = 3;
const SUPERVISOR_MAX_RESTARTS: u8 = 3;
const SUPERVISOR_WINDOW: Duration = Duration::from_secs(60 * 60);

struct RestartTracker {
    attempts: u8,
    window_started: Instant,
    consecutive_failures: u8,
    blocked: bool,
    alerted: bool,
}

impl RestartTracker {
    fn new() -> Self {
        Self {
            attempts: 0,
            window_started: Instant::now(),
            consecutive_failures: 0,
            blocked: false,
            alerted: false,
        }
    }

    fn healthy(&mut self) {
        self.consecutive_failures = 0;
        self.alerted = false;
    }

    fn failed(&mut self) -> bool {
        self.refresh_window();
        if self.blocked {
            return false;
        }
        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
        self.consecutive_failures >= SUPERVISOR_FAILURES_BEFORE_RESTART
    }

    fn allow_restart(&mut self) -> bool {
        self.refresh_window();
        if self.attempts >= SUPERVISOR_MAX_RESTARTS {
            self.blocked = true;
            return false;
        }
        self.attempts += 1;
        self.consecutive_failures = 0;
        true
    }

    fn alert_once(&mut self) -> bool {
        if self.alerted {
            return false;
        }
        self.alerted = true;
        true
    }

    fn refresh_window(&mut self) {
        if self.window_started.elapsed() >= SUPERVISOR_WINDOW {
            self.window_started = Instant::now();
            self.attempts = 0;
            self.consecutive_failures = 0;
            self.blocked = false;
            self.alerted = false;
        }
    }
}

// ---------------------------------------------------------------------------
// Evento de progreso hacia la pantalla de arranque
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
struct Progress {
    /// "setup" | "db" | "maintenance" | "litellm" | "backend" | "frontend" | "ready" | "error"
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
    log_line(
        &log_dir,
        &format!("Setup: lanzado (PID {pid}). Timeout 15 min."),
    );

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
            return Err(
                "la preparación de Mia tardó demasiado — vuelve a abrirla o avísale a soporte"
                    .into(),
            );
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
// Arranque del motor de modelos (LiteLLM) — reutilizable
// ---------------------------------------------------------------------------

/// Lanza el proceso de LiteLLM (el puerto debe estar YA libre), lo mete al Job
/// Object, lo registra como hijo propio (reemplazando pid/child en `Owned`) y
/// ESPERA a su salud (liveliness). Devuelve el pid. Lo usan tanto el arranque
/// en frío (`orchestrate`, puerto libre) como el reinicio en caliente
/// (`restart_litellm`): así la lógica de lanzamiento + Job + espera vive en un
/// solo lugar y no puede divergir.
async fn spawn_litellm(
    app: &AppHandle,
    client: &reqwest::Client,
    shared: &Shared,
    litellm: &LiteLlmCfg,
    app_dir: &Option<String>,
) -> Result<u32, String> {
    let log_dir = shared.log_dir.clone();
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
    if let Some(app_dir) = app_dir {
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
    log_line(
        &log_dir,
        &format!("LiteLLM: lanzado (PID {pid}). Esperando su salud (liveliness)…"),
    );
    // Hijo propio: basta liveliness (2xx en health_url). Falla rápida si el
    // proceso muere; latido visible tras 8 s.
    let wait_start = Instant::now();
    let deadline = wait_start + Duration::from_secs(180);
    loop {
        // child_died PRIMERO: si el hijo murió y un squatter rápido ya ocupó el
        // puerto, un health-check hecho antes podría leer ese squatter como
        // "vivo" y nunca reportar la muerte real.
        if let Some(status) = child_died(shared, "litellm") {
            log_line(
                &log_dir,
                &format!("ERROR técnico: litellm terminó solo ({status})."),
            );
            return Err("Mia no pudo encender el motor de modelos".into());
        }
        if let Identity::Mia = identity::litellm_health(client, &litellm.health_url).await {
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
            emit(
                app,
                "litellm",
                &format!("Encendiendo el motor de modelos… ({secs} s)"),
            );
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
    log_line(&log_dir, "LiteLLM: salud OK (liveliness).");
    Ok(pid)
}

// ---------------------------------------------------------------------------
// Reinicio en caliente del motor de modelos (comando Tauri) — Riesgo #60
// ---------------------------------------------------------------------------

/// Guard que limpia el flag `restarting` en TODOS los caminos de retorno del
/// reinicio (early-return, `?`, panic): pone el flag en `false` al soltarse.
struct RestartGuard<'a>(&'a AtomicBool);
impl Drop for RestartGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

/// Reinicia el proxy LiteLLM que ESTA cáscara arrancó, sin cerrar la app.
///
/// Lo llama el frontend tras guardar una clave DIFERIDA (respaldo/openrouter)
/// que solo el proxy lee al arrancar: en vez de pedirle al abogado "cierra y
/// reabre Mia", se reinicia el motor en caliente para que la clave quede activa
/// de una vez.
///
/// Devuelve `"reiniciado"` si el proxy se reinició, o `"no-aplica"`/`"en-curso"`
/// cuando no procede (cáscara cerrando, litellm adoptado/ajeno, sin bloque
/// retenido, o ya hay un reinicio en curso). NUNCA mata un proxy que no sea
/// nuestro.
#[tauri::command]
async fn restart_litellm(app: AppHandle) -> Result<String, String> {
    let shared = app.state::<Shared>();
    let log_dir = shared.log_dir.clone();

    // (a) NO-APLICA sin tocar nada: cáscara cerrando, sin bloque litellm
    // retenido (dev / 3 servicios), o litellm ADOPTADO (litellm_pid None = no
    // es nuestro proceso; jamás matamos un proxy ajeno).
    if closing(&shared) {
        return Ok("no-aplica".into());
    }
    let retained = shared.litellm.lock().unwrap().clone();
    let (litellm_cfg, app_dir) = match retained {
        Some(v) => v,
        None => {
            log_line(
                &log_dir,
                "LiteLLM: reinicio no aplica (sin bloque litellm retenido).",
            );
            return Ok("no-aplica".into());
        }
    };
    let old_pid = { shared.owned.lock().unwrap().litellm_pid };
    let old_pid = match old_pid {
        Some(p) => p,
        None => {
            log_line(
                &log_dir,
                "LiteLLM: reinicio no aplica (el motor fue adoptado, no es nuestro).",
            );
            return Ok("no-aplica".into());
        }
    };

    // (b) serializar: si ya hay un reinicio en curso, salir sin tocar el flag
    // que otro reinicio ya posee (por eso el guard se crea DESPUÉS de este if).
    if shared.restarting.swap(true, Ordering::SeqCst) {
        log_line(&log_dir, "LiteLLM: ya hay un reinicio en curso — omito.");
        return Ok("en-curso".into());
    }
    let _guard = RestartGuard(&shared.restarting);

    log_line(
        &log_dir,
        &format!("LiteLLM: reiniciando — mato el proxy viejo (PID {old_pid})."),
    );
    // (c) matar el árbol del proxy viejo y hacer reap del Child para no dejar
    // zombie; deja litellm_pid en None hasta que spawn_litellm lo reemplace.
    let _ = Command::new("taskkill")
        .args(["/PID", &old_pid.to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .status();
    {
        let mut o = shared.owned.lock().unwrap();
        if let Some(mut child) = o.litellm_child.take() {
            let _ = child.try_wait();
        }
        o.litellm_pid = None;
    }

    // (d) esperar a que el puerto quede LIBRE antes de re-lanzar (evita que el
    // nuevo proceso choque al hacer bind mientras el viejo aún lo suelta).
    let port = litellm_cfg.port;
    let free_deadline = Instant::now() + Duration::from_secs(10);
    while port_open(port) {
        if Instant::now() > free_deadline {
            log_line(
                &log_dir,
                &format!("ERROR: el puerto {port} no quedó libre tras matar el proxy — abandono el reinicio."),
            );
            return Err("no pude reiniciar el motor de modelos (el puerto siguió ocupado)".into());
        }
        if closing(&shared) {
            return Ok("no-aplica".into());
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
    }

    if closing(&shared) {
        return Ok("no-aplica".into());
    }

    // (e/f) re-lanzar (re-asigna al Job, register_child reemplaza pid/child) y
    // esperar su salud (liveliness) — misma ruta que el arranque en frío.
    let client = reqwest::Client::builder().no_proxy().build().map_err(|e| {
        log_line(
            &log_dir,
            &format!("ERROR técnico: cliente HTTP (reinicio litellm): {e}"),
        );
        "no pude reiniciar el motor de modelos".to_string()
    })?;
    spawn_litellm(&app, &client, &shared, &litellm_cfg, &app_dir).await?;

    log_line(&log_dir, "LiteLLM: reiniciado");
    Ok("reiniciado".into())
    // _guard limpia `restarting` al salir por CUALQUIER camino (aquí, en `?`,
    // o en los early-return de arriba tras crearse).
}

// ---------------------------------------------------------------------------
// Secuencia de arranque
// ---------------------------------------------------------------------------

async fn orchestrate(app: AppHandle, cfg: OrchCfg, shared: &Shared) -> Result<(), String> {
    let log_dir = shared.log_dir.clone();
    let started = Instant::now();
    log_line(&log_dir, "=== Arranque de Mia (cáscara) ===");

    // Retener el bloque litellm + app_dir ANTES de que `cfg` se consuma: sin
    // esto, `restart_litellm` no tendría con qué re-lanzar el motor de modelos
    // en caliente. Si no hay bloque litellm (dev), queda None y el reinicio no
    // aplica.
    if let Some(l) = &cfg.litellm {
        *shared.litellm.lock().unwrap() = Some((l.clone(), cfg.app_dir.clone()));
    }
    *shared.maintenance.lock().unwrap() = cfg.maintenance.clone().map(|m| (m, cfg.app_dir.clone()));

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
            log_line(
                &log_dir,
                "Setup: ya preparado (marcador, PG_VERSION y .env presentes) — omito.",
            );
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
        log_line(
            &log_dir,
            &format!("DB: puerto {} libre — la enciendo.", cfg.db.port),
        );
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
        log_line(
            &log_dir,
            "DB: encendida por la cáscara (la apagaré al salir).",
        );
    }

    // --- a1) Protección y actualizaciones locales -----------------------
    // La DB ya responde y el backend aún no arrancó: es la única ventana
    // segura para respaldar, migrar y cifrar credenciales antiguas sin que
    // una petición concurrente observe un estado intermedio.
    if cfg.maintenance.is_some() {
        if closing(shared) {
            return Err("la ventana se cerró durante el arranque".into());
        }
        emit(&app, "maintenance", "Protegiendo y comprobando tus datos…");
        log_line(
            &log_dir,
            "Maintenance: inicio automático antes de servicios.",
        );
        let result = run_maintenance_action(app.clone(), "startup", vec![]).await?;
        log_line(&log_dir, &format!("Maintenance: {result}"));
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
            // Puerto libre: lanzar hijo propio y esperar su salud. La lógica de
            // lanzamiento + Job + espera vive en spawn_litellm (reutilizada por
            // el reinicio en caliente).
            spawn_litellm(&app, &client, shared, litellm, &cfg.app_dir).await?;
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
                &format!(
                    "ERROR técnico: puerto {} ocupado por un proceso que no responde salud.",
                    cfg.backend.port
                ),
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
            command.env("MIA_API_HOST", "127.0.0.1");
            // Codex por membresía pertenece solo a esta app de escritorio del titular.
            // El backend exige además runtime Tauri, loopback y CORS local.
            command.env("MIA_CODEX_MEMBERSHIP_MODE", "local_individual");
            command.env("MIA_DESKTOP_RUNTIME", "tauri-local-v1");
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
        log_line(
            &log_dir,
            &format!("Backend: lanzado (PID {pid}). Esperando su salud e identidad…"),
        );
        // Polling del health cada 2s, timeout 180s (puede tardar en importar),
        // con latido visible y falla rápida si el proceso muere.
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            // child_died PRIMERO: si el hijo murió y un squatter rápido ya
            // ocupó el puerto, un health-check hecho antes podría leer ese
            // squatter como "vivo" y nunca reportar la muerte real.
            if let Some(status) = child_died(shared, "backend") {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: el backend terminó solo ({status})."),
                );
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
                    &format!(
                        "Despertando a Mia… ({secs} s — la primera vez puede tardar unos minutos)"
                    ),
                );
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        log_line(
            &log_dir,
            "Backend: salud OK y es MIA (health con claves propias).",
        );
    }

    // --- b2) Blindaje del instalador: el esquema debe haber quedado COMPLETO
    // ------------------------------------------------------------------------
    // META D: identity::backend_identity (arriba, sin tocarla) solo exige que
    // /health traiga las claves db/pgvector/embed_model — eso confirma que ES
    // Mia, no que su base de datos terminó de actualizarse. Reutilizamos el
    // mismo health_url ya validado para leer migrations_applied/
    // migrations_expected/checkpointer (backend/mia/api/main.py::health, gap 2
    // de esta ola) y jamás marcar "ready" sobre un esquema a medias — p. ej. si
    // el GRANT de la migración 043 o una migración posterior fallara en
    // silencio.
    if closing(shared) {
        return Err("la ventana se cerró durante el arranque".into());
    }
    let schema_check = client
        .get(&cfg.backend.health_url)
        .timeout(Duration::from_secs(4))
        .send()
        .await;
    let schema_ok = match schema_check {
        Ok(resp) if resp.status().is_success() => match resp.text().await {
            Ok(body) => match serde_json::from_str::<serde_json::Value>(&body) {
                Ok(json) => {
                    let applied = json.get("migrations_applied").and_then(|v| v.as_i64());
                    let expected = json.get("migrations_expected").and_then(|v| v.as_i64());
                    let checkpointer = json.get("checkpointer").and_then(|v| v.as_bool());
                    log_line(
                        &log_dir,
                        &format!(
                            "Backend: verificación de esquema — migrations_applied={applied:?} migrations_expected={expected:?} checkpointer={checkpointer:?}."
                        ),
                    );
                    matches!(checkpointer, Some(true))
                        && applied.is_some()
                        && applied == expected
                }
                Err(e) => {
                    log_line(
                        &log_dir,
                        &format!("ERROR técnico: /health devolvió un cuerpo no-JSON al verificar el esquema: {e}"),
                    );
                    false
                }
            },
            Err(e) => {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: no pude leer el cuerpo de /health al verificar el esquema: {e}"),
                );
                false
            }
        },
        Ok(resp) => {
            log_line(
                &log_dir,
                &format!("ERROR técnico: /health respondió {} al verificar el esquema.", resp.status()),
            );
            false
        }
        Err(e) => {
            log_line(
                &log_dir,
                &format!("ERROR técnico: /health no respondió al verificar el esquema: {e}"),
            );
            false
        }
    };
    if !schema_ok {
        return Err(
            "Mia se instaló pero no terminó de actualizar su base de datos".into(),
        );
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
                &format!(
                    "ERROR técnico: puerto {} ocupado por un proceso que no responde.",
                    cfg.frontend.port
                ),
            );
            return Err(
                "otro programa está ocupando el lugar de la pantalla de Mia — reinicia el equipo"
                    .into(),
            );
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
        // HOSTNAME=127.0.0.1 (loopback): así (a) el server NO hereda un HOSTNAME
        // del sistema que resuelva a una IP de VPN y dejaría a localhost sin
        // conectar (gotcha de build_frontend.ps1), y (b) NO escucha en 0.0.0.0
        // —el default de server.js sin HOSTNAME—, que expondría la pantalla de
        // MIA a toda la LAN/VPN del despacho (seguridad, capa 2 sesión 45). La
        // ventana Tauri navega a localhost:3100, que resuelve a 127.0.0.1: OK.
        let child = Command::new(prog)
            .args(rest)
            .current_dir(&cfg.frontend.cwd)
            .creation_flags(CREATE_NO_WINDOW)
            .env("PORT", cfg.frontend.port.to_string())
            .env("HOSTNAME", "127.0.0.1")
            .stdout(child_log(&log_dir, "frontend"))
            .stderr(child_log(&log_dir, "frontend"))
            .spawn()
            .map_err(|e| {
                log_line(&log_dir, &format!("ERROR técnico: spawn frontend: {e}"));
                "no pude preparar la pantalla".to_string()
            })?;
        if let Some(job) = &shared.job {
            if !job.assign(&child) {
                log_line(
                    &log_dir,
                    "AVISO: no pude asignar el frontend al Job Object.",
                );
            }
        }
        let pid = register_child(shared, "frontend", child)?;
        log_line(
            &log_dir,
            &format!("Frontend: lanzado (PID {pid}). Esperando 200 e identidad…"),
        );
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            // child_died PRIMERO: si el hijo murió y un squatter rápido ya
            // ocupó el puerto, un health-check hecho antes podría leer ese
            // squatter como "vivo" y nunca reportar la muerte real.
            if let Some(status) = child_died(shared, "frontend") {
                log_line(
                    &log_dir,
                    &format!("ERROR técnico: el frontend terminó solo ({status})."),
                );
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
                emit(
                    &app,
                    "frontend",
                    &format!("Preparando tu pantalla… ({secs} s)"),
                );
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        log_line(&log_dir, "Frontend: 200 OK y es MIA (huella de cabeceras).");
    }

    // --- d) Navegar a la app ---------------------------------------------
    emit(&app, "ready", "Listo. Entrando a Mia…");
    let secs = started.elapsed().as_secs();
    log_line(
        &log_dir,
        &format!("Todo listo en {secs}s. Navegando a {}.", cfg.frontend.url),
    );
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

async fn restart_backend_service(
    app: &AppHandle,
    client: &reqwest::Client,
    shared: &Shared,
    cfg: &BackendCfg,
    app_dir: &Option<String>,
) -> Result<(), String> {
    let (prog, rest) = cfg
        .cmd
        .split_first()
        .ok_or("Mia no pudo reencender su servicio")?;
    let mut command = Command::new(prog);
    command
        .args(rest)
        .current_dir(&cfg.cwd)
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(child_log(&shared.log_dir, "backend"))
        .stderr(child_log(&shared.log_dir, "backend"));
    for (k, v) in &cfg.env {
        command.env(k, v);
    }
    if let Some(dir) = app_dir {
        command.env("MIA_APP_DIR", dir);
        command.env("MIA_API_HOST", "127.0.0.1");
        command.env("MIA_CODEX_MEMBERSHIP_MODE", "local_individual");
        command.env("MIA_DESKTOP_RUNTIME", "tauri-local-v1");
    }
    let child = command.spawn().map_err(|e| {
        log_line(
            &shared.log_dir,
            &format!("Supervisor: no pude relanzar backend: {e}"),
        );
        "Mia no pudo recuperar su servicio".to_string()
    })?;
    if let Some(job) = &shared.job {
        let _ = job.assign(&child);
    }
    let pid = register_child(shared, "backend", child)?;
    log_line(
        &shared.log_dir,
        &format!("Supervisor: backend relanzado (PID {pid})."),
    );
    let deadline = Instant::now() + Duration::from_secs(90);
    loop {
        if child_died(shared, "backend").is_some() {
            return Err("el servicio volvió a cerrarse".into());
        }
        if identity::backend_identity(client, &cfg.health_url).await == Identity::Mia {
            emit(
                app,
                "runtime-ok",
                "Mia recuperó su servicio y ya está lista.",
            );
            return Ok(());
        }
        if closing(shared) || Instant::now() >= deadline {
            return Err("el servicio no respondió después de reiniciarlo".into());
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}

async fn restart_frontend_service(
    app: &AppHandle,
    client: &reqwest::Client,
    shared: &Shared,
    cfg: &FrontendCfg,
) -> Result<(), String> {
    let (prog, rest) = cfg
        .cmd
        .split_first()
        .ok_or("Mia no pudo reabrir su pantalla")?;
    let child = Command::new(prog)
        .args(rest)
        .current_dir(&cfg.cwd)
        .creation_flags(CREATE_NO_WINDOW)
        .env("PORT", cfg.port.to_string())
        .env("HOSTNAME", "127.0.0.1")
        .stdout(child_log(&shared.log_dir, "frontend"))
        .stderr(child_log(&shared.log_dir, "frontend"))
        .spawn()
        .map_err(|e| {
            log_line(
                &shared.log_dir,
                &format!("Supervisor: no pude relanzar frontend: {e}"),
            );
            "Mia no pudo recuperar su pantalla".to_string()
        })?;
    if let Some(job) = &shared.job {
        let _ = job.assign(&child);
    }
    let pid = register_child(shared, "frontend", child)?;
    log_line(
        &shared.log_dir,
        &format!("Supervisor: frontend relanzado (PID {pid})."),
    );
    let deadline = Instant::now() + Duration::from_secs(90);
    loop {
        if child_died(shared, "frontend").is_some() {
            return Err("la pantalla volvió a cerrarse".into());
        }
        if identity::frontend_identity(client, &cfg.url).await == Identity::Mia {
            emit(app, "runtime-ok", "Mia recuperó su pantalla.");
            return Ok(());
        }
        if closing(shared) || Instant::now() >= deadline {
            return Err("la pantalla no respondió después de reiniciarla".into());
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}

fn restart_decision(tracker: &mut RestartTracker, identity: Identity, died: bool) -> bool {
    if identity == Identity::Mia && !died {
        tracker.healthy();
        return false;
    }
    if identity == Identity::NotMia {
        tracker.healthy();
        return false;
    }
    died || tracker.failed()
}

async fn supervise_runtime(app: AppHandle, cfg: OrchCfg) {
    let client = match reqwest::Client::builder().build() {
        Ok(client) => client,
        Err(e) => {
            let shared = app.state::<Shared>();
            log_line(
                &shared.log_dir,
                &format!("Supervisor: no pude crear cliente de salud: {e}"),
            );
            return;
        }
    };
    let mut backend = RestartTracker::new();
    let mut frontend = RestartTracker::new();
    let mut litellm = RestartTracker::new();

    loop {
        tokio::time::sleep(SUPERVISOR_INTERVAL).await;
        let shared = app.state::<Shared>();
        if closing(&shared) {
            break;
        }

        // Solo los PID registrados son hijos propios. Un servicio adoptado tiene None.
        if owned_pid(&shared, "backend").is_some() {
            let died = child_died(&shared, "backend").is_some();
            let state = if died {
                Identity::NoResponse
            } else {
                identity::backend_identity(&client, &cfg.backend.health_url).await
            };
            if state == Identity::NotMia {
                if backend.alert_once() {
                    log_line(&shared.log_dir, "Supervisor: el puerto del backend responde como otra aplicación; no lo toco.");
                    emit(&app, "runtime-error", "Otro programa está ocupando el lugar de Mia. Cierra y vuelve a abrir la aplicación.");
                }
            } else if restart_decision(&mut backend, state, died) {
                if !backend.allow_restart() {
                    log_line(
                        &shared.log_dir,
                        "Supervisor: backend cayó 3 veces en una hora; detengo los reintentos.",
                    );
                    emit(&app, "runtime-error", "Mia no pudo recuperarse después de varios intentos. Cierra y vuelve a abrir; si persiste, contacta a soporte.");
                } else {
                    emit(
                        &app,
                        "runtime-warning",
                        "Mia perdió uno de sus servicios. Estoy recuperándolo…",
                    );
                    log_line(&shared.log_dir, "Supervisor: recuperando backend.");
                    if !died {
                        terminate_owned(&shared, "backend");
                    }
                    if wait_port_free(cfg.backend.port, &shared).await {
                        if let Err(e) = restart_backend_service(
                            &app,
                            &client,
                            &shared,
                            &cfg.backend,
                            &cfg.app_dir,
                        )
                        .await
                        {
                            log_line(
                                &shared.log_dir,
                                &format!("Supervisor: backend no se recuperó: {e}"),
                            );
                        }
                    } else {
                        log_line(
                            &shared.log_dir,
                            "Supervisor: puerto backend siguió ocupado; no lanzo otro proceso.",
                        );
                    }
                }
            }
        } else {
            let state = identity::backend_identity(&client, &cfg.backend.health_url).await;
            if state == Identity::Mia {
                backend.healthy();
            } else if backend.failed() && backend.alert_once() {
                log_line(&shared.log_dir, "Supervisor: el backend adoptado dejó de responder; no lo reinicio porque no es un proceso propio.");
                emit(&app, "runtime-error", "Un servicio externo de Mia dejó de responder. Cierra y vuelve a abrir la aplicación.");
            }
        }

        if closing(&shared) {
            break;
        }
        if owned_pid(&shared, "frontend").is_some() {
            let died = child_died(&shared, "frontend").is_some();
            let state = if died {
                Identity::NoResponse
            } else {
                identity::frontend_identity(&client, &cfg.frontend.url).await
            };
            if state == Identity::NotMia {
                if frontend.alert_once() {
                    log_line(&shared.log_dir, "Supervisor: el puerto de la pantalla responde como otra aplicación; no lo toco.");
                    emit(&app, "runtime-error", "Otro programa está ocupando la pantalla de Mia. Cierra y vuelve a abrir la aplicación.");
                }
            } else if restart_decision(&mut frontend, state, died) {
                if !frontend.allow_restart() {
                    log_line(
                        &shared.log_dir,
                        "Supervisor: frontend cayó 3 veces en una hora; detengo los reintentos.",
                    );
                    emit(&app, "runtime-error", "La pantalla de Mia no pudo recuperarse. Cierra y vuelve a abrir la aplicación.");
                } else {
                    emit(
                        &app,
                        "runtime-warning",
                        "La pantalla tuvo una interrupción. Estoy recuperándola…",
                    );
                    log_line(&shared.log_dir, "Supervisor: recuperando frontend.");
                    if !died {
                        terminate_owned(&shared, "frontend");
                    }
                    if wait_port_free(cfg.frontend.port, &shared).await {
                        if let Err(e) =
                            restart_frontend_service(&app, &client, &shared, &cfg.frontend).await
                        {
                            log_line(
                                &shared.log_dir,
                                &format!("Supervisor: frontend no se recuperó: {e}"),
                            );
                        }
                    }
                }
            }
        } else {
            let state = identity::frontend_identity(&client, &cfg.frontend.url).await;
            if state == Identity::Mia {
                frontend.healthy();
            } else if frontend.failed() && frontend.alert_once() {
                log_line(&shared.log_dir, "Supervisor: la pantalla adoptada dejó de responder; no la reinicio porque no es propia.");
                emit(&app, "runtime-error", "La pantalla externa de Mia dejó de responder. Cierra y vuelve a abrir la aplicación.");
            }
        }

        if closing(&shared) {
            break;
        }
        if let Some(lcfg) = &cfg.litellm {
            if owned_pid(&shared, "litellm").is_some() && !shared.restarting.load(Ordering::SeqCst)
            {
                let died = child_died(&shared, "litellm").is_some();
                let state = if died {
                    Identity::NoResponse
                } else {
                    identity::litellm_health(&client, &lcfg.health_url).await
                };
                if restart_decision(&mut litellm, state, died) {
                    if shared
                        .restarting
                        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                        .is_ok()
                    {
                        let _guard = RestartGuard(&shared.restarting);
                        // El reinicio manual pudo completarse entre el primer sondeo y
                        // este turno exclusivo. Revalidar evita matar su proceso nuevo
                        // usando un resultado de salud ya obsoleto.
                        let current_died = child_died(&shared, "litellm").is_some();
                        let current_state = if current_died {
                            Identity::NoResponse
                        } else {
                            identity::litellm_health(&client, &lcfg.health_url).await
                        };
                        if current_state == Identity::Mia && !current_died {
                            litellm.healthy();
                        } else if !litellm.allow_restart() {
                            log_line(&shared.log_dir, "Supervisor: motor de modelos cayó 3 veces en una hora; detengo los reintentos.");
                            emit(&app, "runtime-error", "El motor de Mia no pudo recuperarse. Cierra y vuelve a abrir la aplicación.");
                        } else {
                            emit(
                                &app,
                                "runtime-warning",
                                "El motor de Mia se interrumpió. Estoy recuperándolo…",
                            );
                            if !current_died {
                                terminate_owned(&shared, "litellm");
                            }
                            if wait_port_free(lcfg.port, &shared).await {
                                match spawn_litellm(&app, &client, &shared, lcfg, &cfg.app_dir)
                                    .await
                                {
                                    Ok(_) => emit(
                                        &app,
                                        "runtime-ok",
                                        "El motor de Mia volvió a estar disponible.",
                                    ),
                                    Err(e) => log_line(
                                        &shared.log_dir,
                                        &format!("Supervisor: motor no se recuperó: {e}"),
                                    ),
                                }
                            }
                        }
                    }
                }
            } else if owned_pid(&shared, "litellm").is_none() {
                let state = identity::litellm_health(&client, &lcfg.health_url).await;
                if state == Identity::Mia {
                    litellm.healthy();
                } else if litellm.failed() && litellm.alert_once() {
                    log_line(&shared.log_dir, "Supervisor: el motor adoptado dejó de responder; no lo reinicio porque no es propio.");
                    emit(&app, "runtime-error", "El motor externo de Mia dejó de responder. Cierra y vuelve a abrir la aplicación.");
                }
            }
        }
    }
    let shared = app.state::<Shared>();
    log_line(&shared.log_dir, "Supervisor: detenido por cierre de Mia.");
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
    log_line(
        &log_dir,
        "=== Cierre: apagando lo que arrancó la cáscara ===",
    );

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
            log_line(
                &log_dir,
                &format!("Cierre: taskkill {name} (PID {pid}) -> {res:?}"),
            );
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

fn owned_pid(shared: &Shared, which: &str) -> Option<u32> {
    let o = shared.owned.lock().unwrap();
    match which {
        "litellm" => o.litellm_pid,
        "backend" => o.backend_pid,
        _ => o.frontend_pid,
    }
}

fn terminate_owned(shared: &Shared, which: &str) {
    if let Some(pid) = owned_pid(shared, which) {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
}

async fn wait_port_free(port: u16, shared: &Shared) -> bool {
    for _ in 0..10 {
        if closing(shared) {
            return false;
        }
        if !port_open(port) {
            return true;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    !port_open(port)
}

// ---------------------------------------------------------------------------
// Protección de datos (comandos locales Tauri, nunca expuestos por HTTP)
// ---------------------------------------------------------------------------

async fn run_maintenance_action(
    app: AppHandle,
    action: &'static str,
    extra: Vec<String>,
) -> Result<String, String> {
    let shared = app.state::<Shared>();
    let _guard = if action != "status" {
        if shared.maintenance_running.swap(true, Ordering::SeqCst) {
            return Err("Mia ya está completando otra operación de protección.".into());
        }
        Some(RestartGuard(&shared.maintenance_running))
    } else {
        None
    };
    let retained = shared.maintenance.lock().unwrap().clone();
    let (cfg, app_dir) = retained.ok_or_else(|| {
        "La protección de datos solo está disponible en la aplicación de escritorio.".to_string()
    })?;
    let log_dir = shared.log_dir.clone();

    let output = tauri::async_runtime::spawn_blocking(move || {
        let (program, base_args) = cfg
            .cmd
            .split_first()
            .ok_or_else(|| "El comando de mantenimiento está vacío.".to_string())?;
        let mut command = Command::new(program);
        command
            .args(base_args)
            .arg(action)
            .args(extra)
            .current_dir(&cfg.cwd)
            .creation_flags(CREATE_NO_WINDOW);
        if let Some(dir) = app_dir {
            command.env("MIA_APP_DIR", dir);
        }
        command
            .output()
            .map_err(|_| "Mia no pudo abrir su herramienta de protección.".to_string())
    })
    .await
    .map_err(|_| "La operación de protección se interrumpió.".to_string())??;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let last = stdout
        .lines()
        .rev()
        .find(|line| !line.trim().is_empty())
        .unwrap_or("")
        .trim()
        .to_string();
    if !output.status.success() {
        log_line(
            &log_dir,
            &format!(
                "Maintenance {action}: terminó con error ({}).",
                output.status
            ),
        );
        return Err(if last.starts_with("MIA-MAINTENANCE:") {
            last.trim_start_matches("MIA-MAINTENANCE:")
                .trim()
                .to_string()
        } else {
            "Mia no pudo completar la operación de protección.".to_string()
        });
    }
    Ok(last)
}

#[tauri::command]
async fn maintenance_status(app: AppHandle) -> Result<String, String> {
    let line = run_maintenance_action(app, "status", vec![]).await?;
    line.strip_prefix("MIA-MAINTENANCE-JSON:")
        .map(str::to_string)
        .ok_or_else(|| "Mia no pudo leer el estado de protección.".to_string())
}

#[tauri::command]
async fn maintenance_export_key(app: AppHandle) -> Result<String, String> {
    let documents = std::env::var("USERPROFILE")
        .map(PathBuf::from)
        .map(|p| p.join("Documents"))
        .map_err(|_| "Windows no encontró la carpeta Documentos.".to_string())?;
    let destination = documents.join("Llave-de-recuperacion-Mia.txt");
    run_maintenance_action(
        app,
        "export-key",
        vec![
            "--destination".into(),
            destination.to_string_lossy().into_owned(),
        ],
    )
    .await?;
    Ok("Documentos > Llave-de-recuperacion-Mia.txt".into())
}

#[tauri::command]
async fn maintenance_confirm_key(app: AppHandle) -> Result<String, String> {
    run_maintenance_action(app, "confirm-key", vec![]).await?;
    Ok("confirmada".into())
}

#[tauri::command]
async fn maintenance_create_backup(app: AppHandle) -> Result<String, String> {
    run_maintenance_action(app, "backup", vec![]).await?;
    Ok("creada".into())
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
                litellm: Mutex::new(None),
                maintenance: Mutex::new(None),
                maintenance_running: AtomicBool::new(false),
                restarting: AtomicBool::new(false),
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
                                    let supervisor_cfg = cfg.clone();
                                    if let Err(e) = orchestrate(handle2.clone(), cfg, &shared).await {
                                        log_line(&shared.log_dir, &format!("ERROR de arranque: {e}"));
                                        emit(
                                            &handle2,
                                            "error",
                                            &format!(
                                                "Algo no encendió bien: {e} — cierra y vuelve a abrir; si persiste, contacta a soporte."
                                            ),
                                        );
                                    } else {
                                        drop(shared);
                                        supervise_runtime(handle2.clone(), supervisor_cfg).await;
                                    }
                                });
                            }
                        }
                    }
                }
            }
            Ok(())
        })
        // Comando invocable desde el frontend (window.__TAURI__.core.invoke):
        // reinicia el motor de modelos en caliente tras guardar una clave
        // diferida, sin pedirle al abogado que cierre y reabra Mia.
        .invoke_handler(tauri::generate_handler![
            restart_litellm,
            maintenance_status,
            maintenance_export_key,
            maintenance_confirm_key,
            maintenance_create_backup
        ])
        .build(tauri::generate_context!())
        .expect("error al iniciar la cáscara de Mia")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                shutdown(app_handle);
            }
        });
}

#[cfg(test)]
mod supervisor_tests {
    use super::*;

    #[test]
    fn three_consecutive_failures_are_required() {
        let mut tracker = RestartTracker::new();
        assert!(!tracker.failed());
        assert!(!tracker.failed());
        assert!(tracker.failed());
        tracker.healthy();
        assert!(!tracker.failed());
    }

    #[test]
    fn crash_loop_stops_after_three_restarts() {
        let mut tracker = RestartTracker::new();
        assert!(tracker.allow_restart());
        assert!(tracker.allow_restart());
        assert!(tracker.allow_restart());
        assert!(!tracker.allow_restart());
        assert!(!tracker.failed());
    }

    #[test]
    fn confirmed_identity_resets_health_failures() {
        let mut tracker = RestartTracker::new();
        assert!(!restart_decision(&mut tracker, Identity::NoResponse, false));
        assert!(!restart_decision(&mut tracker, Identity::Mia, false));
        assert!(!restart_decision(&mut tracker, Identity::NoResponse, false));
        assert!(!restart_decision(&mut tracker, Identity::NotMia, false));
        assert!(!restart_decision(&mut tracker, Identity::NoResponse, false));
    }
}
