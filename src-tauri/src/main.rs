#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod diagnostics;

use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use taller_canamo::{
    backend::Backend,
    desktop_files::{self, PdfAction},
    export::{atomic_download, atomic_export, suggested_name, validate_download, DownloadChunk},
    notifications,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};
use tauri_plugin_autostart::ManagerExt;

#[derive(Default)]
struct DesktopState {
    dirty: AtomicBool,
    closing: AtomicBool,
    stopped: AtomicBool,
    exporting: AtomicBool,
}

struct ExportGuard<'a>(&'a AtomicBool);
impl Drop for ExportGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

#[tauri::command]
async fn rpc(
    app: tauri::AppHandle,
    action: String,
    params: Option<Value>,
) -> Result<Value, String> {
    if action == "app.shutdown" {
        return Err("Usa Salir en el icono de la bandeja para cerrar de forma segura.".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        app.state::<Backend>()
            .call(action, params.unwrap_or_else(|| json!({})))
    })
    .await
    .map_err(|_| "Fallo del servicio nativo".to_owned())?
}

#[tauri::command]
fn set_document_dirty(app: tauri::AppHandle, dirty: bool) {
    app.state::<DesktopState>()
        .dirty
        .store(dirty, Ordering::SeqCst);
}

#[tauri::command]
fn startup_status(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch()
        .is_enabled()
        .map_err(|_| "No se puede consultar el inicio de sesión.".to_owned())
}

#[tauri::command]
fn set_startup(app: tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    let result = if enabled {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    };
    result.map_err(|_| {
        "No se puede cambiar el inicio de sesión. Revisa los permisos de tu usuario.".to_owned()
    })?;
    startup_status(app)
}

#[tauri::command]
async fn test_notification(app: tauri::AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        notifications::show(
            &app.config().identifier,
            "Talleres El Cáñamo",
            "Aviso de prueba. Los recordatorios se conservan también dentro de la aplicación.",
            true,
        )
    })
    .await
    .map_err(|_| "No se ha podido solicitar el aviso".to_owned())?
}

#[tauri::command]
async fn save_export(
    app: tauri::AppHandle,
    name: String,
    content: Option<String>,
    capability: Option<String>,
    bytes: Option<u64>,
    sha256: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<DesktopState>();
        if state.exporting.swap(true, Ordering::SeqCst) {
            return Err("Ya hay un guardado en curso. Espera a que termine.".into());
        }
        let _guard = ExportGuard(&state.exporting);
        if let Some(capability) = capability {
            let backend = app.state::<Backend>();
            let result = (|| {
                let bytes = bytes.ok_or_else(|| "Falta el tamaño de la descarga.".to_owned())?;
                let sha256 = sha256.ok_or_else(|| "Falta la huella de la descarga.".to_owned())?;
                validate_download(&capability, bytes, &sha256)?;
                let Some(path) = rfd::FileDialog::new().set_file_name(suggested_name(&name)).save_file() else {
                    return Ok(json!({"saved": false}));
                };
                atomic_download(&path, bytes, &sha256, |offset, length| {
                    let reply = backend.call("backup.download_chunk".into(), json!({"capability": capability, "offset": offset, "length": length}))?;
                    DownloadChunk::from_reply(&reply)
                })?;
                Ok(json!({"saved": true, "bytes": bytes, "sha256": sha256}))
            })();
            // Revoking the handle never removes the durable local backup.
            // This runs after save, cancellation, malformed metadata or failure.
            let _ = backend.call("backup.release_download".into(), json!({"capability": capability}));
            result
        } else {
            let content = content.ok_or_else(|| "Falta el contenido del archivo.".to_owned())?;
            if content.len() > 280_000_000 { return Err("Archivo demasiado grande; usa descarga por fragmentos.".into()); }
            let bytes = STANDARD.decode(content).map_err(|_| "Archivo no válido".to_owned())?;
            match rfd::FileDialog::new().set_file_name(suggested_name(&name)).save_file() {
                Some(path) => {
                    atomic_export(&path, &bytes).map_err(|_| "No se ha podido guardar el archivo. El archivo anterior se conserva; revisa espacio libre y permisos o elige otra carpeta.".to_owned())?;
                    Ok(json!({"saved": true}))
                }
                None => Ok(json!({"saved": false})),
            }
        }
    }).await.map_err(|_| "Fallo al guardar".to_owned())?
}

#[tauri::command]
async fn open_external(url: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || desktop_files::open_external(&url))
        .await
        .map_err(|_| "No se ha podido solicitar la apertura del borrador.".to_owned())?
}

#[tauri::command]
async fn handle_pdf(
    app: tauri::AppHandle,
    name: String,
    content: String,
    action: String,
) -> Result<Value, String> {
    let action = PdfAction::parse(&action)?;
    let cache = app
        .path()
        .app_cache_dir()
        .map_err(|_| "No se puede obtener la carpeta temporal del usuario.".to_owned())?;
    tauri::async_runtime::spawn_blocking(move || {
        let pdf = desktop_files::prepare_pdf(&cache, &name, &content)?;
        desktop_files::request_pdf(&pdf, action)?;
        Ok(json!({"requested": true, "pages": pdf.pages, "action": if action == PdfAction::Print { "print" } else { "open" }}))
    }).await.map_err(|_| "No se ha podido preparar el PDF.".to_owned())?
}

fn show_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn message(title: &str, text: &str) {
    rfd::MessageDialog::new()
        .set_title(title)
        .set_description(text)
        .set_level(rfd::MessageLevel::Warning)
        .set_buttons(rfd::MessageButtons::Ok)
        .show();
}

fn request_exit(app: &tauri::AppHandle) {
    let state = app.state::<DesktopState>();
    if state.exporting.load(Ordering::SeqCst) {
        show_window(app);
        std::thread::spawn(|| {
            message(
                "Guardado en curso",
                "Espera a que termine el guardado del archivo o cancela el diálogo antes de salir.",
            )
        });
        return;
    }
    if state.dirty.load(Ordering::SeqCst) {
        show_window(app);
        std::thread::spawn(|| {
            message("Cambios pendientes", "Hay cambios sin guardar. Guarda el borrador o descarta los cambios desde la aplicación antes de salir.")
        });
        return;
    }
    if state.closing.swap(true, Ordering::SeqCst) {
        return;
    }
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_enabled(false);
    }
    let app = app.clone();
    std::thread::spawn(move || match app.state::<Backend>().shutdown() {
        Ok(()) => {
            app.state::<DesktopState>()
                .stopped
                .store(true, Ordering::SeqCst);
            app.exit(0);
        }
        Err(error) => {
            app.state::<DesktopState>()
                .closing
                .store(false, Ordering::SeqCst);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_enabled(true);
            }
            show_window(&app);
            message("No se ha completado el cierre", &error);
        }
    });
}

fn start_reminders(app: tauri::AppHandle) {
    std::thread::spawn(move || loop {
        if app.state::<DesktopState>().stopped.load(Ordering::SeqCst) {
            break;
        }
        if app.state::<DesktopState>().closing.load(Ordering::SeqCst) {
            std::thread::sleep(Duration::from_secs(1));
            continue;
        }
        let backend = app.state::<Backend>();
        if !backend.is_running() {
            // A failed shutdown can return to RUNNING after showing its error.
            // Keep the poller alive across that transition.
            std::thread::sleep(Duration::from_secs(1));
            continue;
        }
        let _ = (|| -> Result<(), String> {
            let config = backend.call("settings.get".into(), json!({}))?;
            let agenda = &config["result"]["agenda"];
            if agenda["desktop_notifications"] != true {
                return Ok(());
            }
            let response = backend.call(
                "notifications.list".into(),
                json!({"only_undelivered": true}),
            )?;
            let Some(items) = response["result"]
                .as_array()
                .filter(|items| !items.is_empty())
            else {
                return Ok(());
            };
            let body = if items.len() == 1 {
                items[0]["message"]
                    .as_str()
                    .unwrap_or("Tienes un aviso pendiente en la agenda.")
                    .to_owned()
            } else {
                format!("Tienes {} avisos pendientes. Abre la aplicación para revisarlos o posponerlos.", items.len())
            };
            // OS acceptance does not prove visibility (e.g. Windows focus assist).
            notifications::show(
                &app.config().identifier,
                "Talleres El Cáñamo · Agenda",
                &body,
                agenda["sound"] == true,
            )?;
            let ids: Vec<&Value> = items.iter().map(|item| &item["id"]).collect();
            backend.call(
                "notifications.mark".into(),
                json!({"identifiers": ids, "action": "delivered"}),
            )?;
            Ok(())
        })();
        // Failure retains reminders for the next poll; never log personal data.
        std::thread::sleep(Duration::from_secs(20));
    });
}

fn main() {
    let mut arguments = std::env::args_os().skip(1);
    if arguments.next().as_deref() == Some(std::ffi::OsStr::new("--diagnose-sidecar")) {
        let Some(report) = arguments.next() else {
            std::process::exit(2)
        };
        let result = diagnostics::run(std::path::Path::new(&report));
        std::process::exit(if result.is_ok() { 0 } else { 1 });
    }
    let result = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show_window(app)))
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec!["--background"])))
        .manage(DesktopState::default())
        .setup(|app| {
            let data = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&data)?;
            let backend = Backend::start(&data)?;
            let bootstrap = backend.call_with_timeout("bootstrap".into(), json!({}), Duration::from_secs(30))?;
            if bootstrap["ok"] != true || bootstrap["result"]["version"] != env!("CARGO_PKG_VERSION") {
                return Err("La versión del servicio no coincide con la aplicación. Reinstala el paquete completo sin borrar tus datos.".into());
            }
            app.manage(backend);
            let open = MenuItem::with_id(app, "open", "Abrir Talleres El Cáñamo", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Salir y guardar copia", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().ok_or("Falta el icono de la aplicación")?.clone())
                .tooltip("Talleres El Cáñamo · Los avisos siguen activos")
                .menu(&menu).show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_window(app),
                    "quit" => request_exit(app),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if matches!(event, TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. }) {
                        show_window(tray.app_handle());
                    }
                }).build(app)?;
            if std::env::args().any(|arg| arg == "--background") {
                if let Some(window) = app.get_webview_window("main") { window.hide()?; }
            }
            start_reminders(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![rpc, save_export, handle_pdf, open_external, test_notification, set_document_dirty, startup_status, set_startup])
        .build(tauri::generate_context!());
    match result {
        Ok(app) => app.run(|app, event| match event {
            tauri::RunEvent::ExitRequested { api, .. } => {
                if !app.state::<DesktopState>().stopped.load(Ordering::SeqCst) {
                    api.prevent_exit();
                    request_exit(app);
                }
            }
            tauri::RunEvent::Exit => {
                if let Some(backend) = app.try_state::<Backend>() { backend.abort(); }
            }
            _ => {}
        }),
        Err(error) => message("No se puede abrir Talleres El Cáñamo", &format!("{error}\n\nTus datos se conservan en la carpeta del usuario. Revisa la instalación completa.")),
    }
}
