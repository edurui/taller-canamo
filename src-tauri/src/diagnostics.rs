//! Explicit local support command. Uses a new disposable synthetic database;
//! never reads the workshop's database and never connects to an external service.
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{path::Path, time::Duration};
use taller_canamo::{
    backend::Backend,
    desktop_files::prepare_pdf,
    export::{atomic_download, atomic_export, DownloadChunk},
};

pub fn run(report: &Path) -> Result<(), String> {
    let result = diagnose();
    let value = match &result {
        Ok(details) => json!({"ok": true, "details": details, "platform": std::env::consts::OS}),
        Err(error) => json!({"ok": false, "error": error, "platform": std::env::consts::OS}),
    };
    atomic_export(
        report,
        &serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    result.map(|_| ())
}

fn checked(backend: &Backend, action: &str, params: Value) -> Result<Value, String> {
    let response = backend.call(action.into(), params)?;
    if response["ok"] != true {
        return Err(format!(
            "{action}: {}",
            response["error"]["message"]
                .as_str()
                .unwrap_or("Error del servicio")
        ));
    }
    Ok(response["result"].clone())
}

fn diagnose() -> Result<Value, String> {
    let directory = tempfile::Builder::new()
        .prefix("canamo-diagnostico-espacios-á-")
        .tempdir()
        .map_err(|e| e.to_string())?;
    let backend = Backend::start(directory.path()).map_err(|e| e.to_string())?;
    let bootstrap =
        backend.call_with_timeout("bootstrap".into(), json!({}), Duration::from_secs(30))?;
    if bootstrap["ok"] != true || bootstrap["result"]["version"] != env!("CARGO_PKG_VERSION") {
        return Err("Las versiones de interfaz y servicio no coinciden".into());
    }
    checked(&backend, "demo.load", json!({}))?;
    let invoices = checked(&backend, "documents.list", json!({}))?;
    let id = invoices["items"][0]["id"]
        .as_str()
        .ok_or("No se ha creado la factura sintética")?;
    let export = checked(&backend, "documents.pdf", json!({"identifier": id}))?;
    let bytes = STANDARD
        .decode(export["content"].as_str().ok_or("Falta el PDF")?)
        .map_err(|e| e.to_string())?;
    if !bytes.starts_with(b"%PDF-") {
        return Err("El servicio no ha generado un PDF válido".into());
    }
    let parsed = prepare_pdf(
        directory.path(),
        export["name"].as_str().unwrap_or("factura.pdf"),
        export["content"].as_str().unwrap(),
    )?;
    checked(&backend, "fiscal.check", json!({}))?;
    let backup = checked(
        &backend,
        "backup.create",
        json!({"password":"clave-sintetica-del-diagnostico"}),
    )?;
    let capability = backup["capability"]
        .as_str()
        .ok_or("Falta permiso temporal de copia")?;
    atomic_download(
        &directory.path().join("copia exportada.canamo"),
        backup["bytes"].as_u64().ok_or("Falta tamaño de copia")?,
        backup["sha256"].as_str().ok_or("Falta huella de copia")?,
        |offset, length| {
            let reply = backend.call(
                "backup.download_chunk".into(),
                json!({"capability":capability,"offset":offset,"length":length}),
            )?;
            DownloadChunk::from_reply(&reply)
        },
    )?;
    checked(
        &backend,
        "backup.release_download",
        json!({"capability":capability}),
    )?;
    backend.shutdown()?;
    let reopened = Backend::start(directory.path()).map_err(|e| e.to_string())?;
    let historic = checked(&reopened, "documents.get", json!({"identifier": id}))?;
    if historic["id"] != id {
        return Err("No se conserva la factura tras reabrir".into());
    }
    reopened.shutdown()?;
    Ok(
        json!({"version": env!("CARGO_PKG_VERSION"), "sidecar": "junto al ejecutable", "synthetic_invoice": true, "pdf_bytes": bytes.len(), "pdf_pages":parsed.pages, "streaming_backup_verified":true, "reopened_history": true, "shutdown_acknowledged": true, "external_validation": false}),
    )
}
