//! EarningsPulse desktop shell.
//!
//! On launch it picks a free local port and a random token, starts the bundled
//! Python engine (`engine/earningspulse-engine` inside the app's resources), and
//! tells the interface where to find it. The engine is stopped when the app quits.

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Manager, RunEvent};

#[derive(Clone, Serialize)]
struct EngineInfo {
    url: String,
    token: String,
    data_dir: String,
    default_data_dir: String,
    log_file: String,
}

struct Engine {
    info: EngineInfo,
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn engine_info(state: tauri::State<'_, Engine>) -> EngineInfo {
    state.info.clone()
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn random_token() -> String {
    let mut bytes = [0u8; 24];
    getrandom::getrandom(&mut bytes).expect("random token");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Default home of the app's data: ~/Library/Application Support/EarningsPulse on macOS.
fn default_data_dir() -> PathBuf {
    dirs::data_dir().unwrap_or_else(std::env::temp_dir).join("EarningsPulse")
}

/// Small pointer file in the default folder that records a location the user chose.
fn location_file() -> PathBuf {
    default_data_dir().join("location.json")
}

/// Where filings, models and settings live: the user's chosen folder, if set and present.
fn data_dir() -> PathBuf {
    if let Ok(text) = std::fs::read_to_string(location_file()) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
            if let Some(p) = v.get("data_dir").and_then(|p| p.as_str()) {
                let p = PathBuf::from(p);
                if p.is_dir() {
                    return p;
                }
            }
        }
    }
    default_data_dir()
}

/// Remember a new data folder (already populated by the engine) and restart onto it.
#[tauri::command]
fn use_data_dir(app: tauri::AppHandle, path: String) -> Result<(), String> {
    let p = PathBuf::from(&path);
    if !p.is_dir() {
        return Err(format!("Folder not found: {path}"));
    }
    std::fs::create_dir_all(default_data_dir()).map_err(|e| e.to_string())?;
    let body = if p == default_data_dir() {
        serde_json::json!({})
    } else {
        serde_json::json!({ "data_dir": path })
    };
    std::fs::write(location_file(), body.to_string()).map_err(|e| e.to_string())?;
    stop_engine(&app);
    app.restart();
}

fn stop_engine(app: &tauri::AppHandle) {
    if let Some(engine) = app.try_state::<Engine>() {
        if let Some(mut child) = engine.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// The command that starts the engine. Release builds use the bundled binary;
/// `EARNINGSPULSE_ENGINE_CMD` overrides it for development (e.g. "python3 -m earnings_sentiment.server").
fn engine_command(app: &tauri::AppHandle) -> Command {
    if let Ok(cmd) = std::env::var("EARNINGSPULSE_ENGINE_CMD") {
        let mut parts = cmd.split_whitespace();
        let mut c = Command::new(parts.next().unwrap_or("python3"));
        c.args(parts);
        return c;
    }
    let exe = if cfg!(windows) { "earningspulse-engine.exe" } else { "earningspulse-engine" };
    let path = app
        .path()
        .resource_dir()
        .map(|d| d.join("engine").join(exe))
        .unwrap_or_else(|_| PathBuf::from(exe));
    Command::new(path)
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![engine_info, use_data_dir])
        .setup(|app| {
            let port = free_port();
            let token = random_token();
            let dir = data_dir();
            let logs = dir.join("logs");
            std::fs::create_dir_all(&logs).ok();
            let log_path = logs.join("engine.log");
            let log = std::fs::File::create(&log_path).ok();

            let mut cmd = engine_command(app.handle());
            cmd.arg("--port")
                .arg(port.to_string())
                .env("EARNINGSPULSE_TOKEN", &token)
                .env("EARNINGSPULSE_DATA_DIR", &dir)
                .env("EARNINGSPULSE_WATCH_PARENT", "1")
                .stdin(Stdio::null());
            match log.as_ref().and_then(|f| f.try_clone().ok()) {
                Some(f) => {
                    cmd.stdout(Stdio::from(f));
                    if let Some(f2) = log.as_ref().and_then(|f| f.try_clone().ok()) {
                        cmd.stderr(Stdio::from(f2));
                    }
                }
                None => {
                    cmd.stdout(Stdio::null()).stderr(Stdio::null());
                }
            }
            let child = cmd.spawn().map_err(|e| {
                eprintln!("Could not start the EarningsPulse engine: {e}");
                e
            }).ok();

            app.manage(Engine {
                info: EngineInfo {
                    url: format!("http://127.0.0.1:{port}"),
                    token,
                    data_dir: dir.display().to_string(),
                    default_data_dir: default_data_dir().display().to_string(),
                    log_file: log_path.display().to_string(),
                },
                child: Mutex::new(child),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building EarningsPulse");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            // Never leave the engine running after the app quits
            stop_engine(handle);
        }
    });
}
