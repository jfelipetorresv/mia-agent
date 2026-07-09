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

/// Windows: no abrir ventana de consola al lanzar procesos hijos.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

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

#[derive(Debug, Clone, Deserialize)]
struct OrchCfg {
    #[serde(default)]
    app_dir: Option<String>,
    db: DbCfg,
    backend: BackendCfg,
    frontend: FrontendCfg,
}

// ---------------------------------------------------------------------------
// Estado que la cáscara "posee" y debe apagar al salir
// ---------------------------------------------------------------------------

#[derive(Default)]
struct Owned {
    db_owned: bool,
    db_pg_bin: String,
    db_data_dir: String,
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
    /// "db" | "backend" | "frontend" | "ready" | "error"
    stage: String,
    /// Texto en español llano listo para pintar.
    text: String,
}

// ---------------------------------------------------------------------------
// Logging simple a desktop/logs/mia-shell.log
// ---------------------------------------------------------------------------

fn log_line(log_dir: &Path, msg: &str) {
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

/// GET a una URL; true si responde con status 2xx.
async fn http_ok(client: &reqwest::Client, url: &str) -> bool {
    match client
        .get(url)
        .timeout(Duration::from_secs(4))
        .send()
        .await
    {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
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

    // --- a) Base de datos ------------------------------------------------
    emit(&app, "db", "Encendiendo la base de datos del despacho…");
    if port_open(cfg.db.port) {
        log_line(
            &log_dir,
            &format!("DB: puerto {} ya responde — ya estaba encendida, no la apagaré.", cfg.db.port),
        );
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

    // --- b) Backend ------------------------------------------------------
    if closing(shared) {
        return Err("la ventana se cerró durante el arranque".into());
    }
    emit(&app, "backend", "Despertando a Mia…");
    if port_open(cfg.backend.port) {
        // Puerto tomado: adoptar solo si responde salud (con margen por si el
        // servicio ajeno está terminando de arrancar); si nunca responde, es
        // un extraño ocupando el puerto — avisar ya, no lanzar un competidor.
        let mut adopted = false;
        for _ in 0..5 {
            if http_ok(&client, &cfg.backend.health_url).await {
                adopted = true;
                break;
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
            &format!("Backend: puerto {} ya responde — lo adopto, no lo apagaré.", cfg.backend.port),
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
        log_line(&log_dir, &format!("Backend: lanzado (PID {pid}). Esperando su salud…"));
        // Polling del health cada 2s, timeout 180s (puede tardar en importar),
        // con latido visible y falla rápida si el proceso muere.
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            if http_ok(&client, &cfg.backend.health_url).await {
                break;
            }
            if let Some(status) = child_died(shared, "backend") {
                log_line(&log_dir, &format!("ERROR técnico: el backend terminó solo ({status})."));
                return Err("Mia no pudo despertar".into());
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
        log_line(&log_dir, "Backend: salud OK.");
    }

    // --- c) Frontend -----------------------------------------------------
    if closing(shared) {
        return Err("la ventana se cerró durante el arranque".into());
    }
    emit(&app, "frontend", "Preparando tu pantalla…");
    if port_open(cfg.frontend.port) {
        let mut adopted = false;
        for _ in 0..5 {
            if http_ok(&client, &cfg.frontend.url).await {
                adopted = true;
                break;
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
            &format!("Frontend: puerto {} ya responde — lo adopto, no lo apagaré.", cfg.frontend.port),
        );
    } else {
        log_line(&log_dir, "Frontend: lo enciendo.");
        let (prog, rest) = cfg
            .frontend
            .cmd
            .split_first()
            .ok_or("no pude preparar la pantalla")?;
        let child = Command::new(prog)
            .args(rest)
            .current_dir(&cfg.frontend.cwd)
            .creation_flags(CREATE_NO_WINDOW)
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
        log_line(&log_dir, &format!("Frontend: lanzado (PID {pid}). Esperando 200…"));
        let wait_start = Instant::now();
        let deadline = wait_start + Duration::from_secs(180);
        loop {
            if http_ok(&client, &cfg.frontend.url).await {
                break;
            }
            if let Some(status) = child_died(shared, "frontend") {
                log_line(&log_dir, &format!("ERROR técnico: el frontend terminó solo ({status})."));
                return Err("la pantalla no pudo prepararse".into());
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
        log_line(&log_dir, "Frontend: 200 OK.");
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

    // Matar árboles de procesos hijos (npm/node, python) por PID.
    for (name, pid) in [("frontend", o.frontend_pid), ("backend", o.backend_pid)] {
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
                        Ok(cfg) => {
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
