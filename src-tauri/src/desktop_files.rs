//! User-requested document handling. The WebView supplies bytes, never a path,
//! program, shell command, printer name or arbitrary URL scheme.
use crate::export::{atomic_export, suggested_name};
use base64::{engine::general_purpose::STANDARD, Engine};
use lopdf::{Document, LoadOptions, Object};
use sha2::{Digest, Sha256};
use std::{
    ffi::OsStr,
    io::Read,
    path::{Path, PathBuf},
    time::{Duration, SystemTime},
};

pub const MAX_PDF_BYTES: usize = 32 * 1024 * 1024;
const MAX_PDF_PAGES: usize = 2000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PdfAction {
    Open,
    Print,
}

impl PdfAction {
    pub fn parse(action: &str) -> Result<Self, String> {
        match action {
            "open" => Ok(Self::Open),
            "print" => Ok(Self::Print),
            _ => Err("Acción de PDF no válida.".into()),
        }
    }
}

#[derive(Debug)]
pub struct PreparedPdf {
    pub path: PathBuf,
    pub pages: usize,
}

/// Accept the invoice/report subset produced by the local service. Active
/// actions and attachments have no role in that subset and are rejected before
/// handing the file to another application. This is not a general PDF sanitizer.
fn validate_pdf(bytes: &[u8]) -> Result<usize, String> {
    if bytes.len() > MAX_PDF_BYTES {
        return Err("El PDF supera 32 MiB. Guárdalo para revisarlo con tu lector.".into());
    }
    let end = bytes
        .iter()
        .rposition(|byte| !byte.is_ascii_whitespace())
        .map(|position| &bytes[..=position])
        .unwrap_or_default();
    if !bytes.starts_with(b"%PDF-") || !end.ends_with(b"%%EOF") {
        return Err("El contenido recibido no es un PDF completo.".into());
    }
    let document = Document::load_mem_with_options(
        bytes,
        LoadOptions {
            strict: true,
            max_decompressed_size: Some(16 * 1024 * 1024),
            ..Default::default()
        },
    )
    .map_err(|_| "No se puede validar la estructura del PDF.".to_owned())?;
    if document.is_encrypted() || document.was_encrypted() {
        return Err("No se permite abrir desde aquí un PDF cifrado.".into());
    }
    if document.objects.len() > 100_000 || document.catalog().is_err() {
        return Err("La estructura del PDF no es válida para esta vista previa.".into());
    }
    let pages = document.page_iter().take(MAX_PDF_PAGES + 1).count();
    if pages == 0 || pages > MAX_PDF_PAGES {
        return Err("El PDF debe tener entre 1 y 2.000 páginas.".into());
    }
    let mut pending: Vec<(&Object, usize)> = document
        .objects
        .values()
        .map(|object| (object, 0))
        .collect();
    let mut visited = 0usize;
    while let Some((object, depth)) = pending.pop() {
        visited += 1;
        if depth > 64 || visited > 1_000_000 {
            return Err("El PDF contiene una estructura demasiado compleja.".into());
        }
        let dictionary = match object {
            Object::Array(items) => {
                pending.extend(items.iter().map(|item| (item, depth + 1)));
                continue;
            }
            Object::Dictionary(dictionary) => dictionary,
            Object::Stream(stream) => &stream.dict,
            // Indirect objects are already visited exactly once from objects.
            _ => continue,
        };
        for (key, value) in dictionary.iter() {
            if matches!(
                key.as_slice(),
                b"JavaScript"
                    | b"JS"
                    | b"OpenAction"
                    | b"AA"
                    | b"EmbeddedFiles"
                    | b"XFA"
                    | b"RichMedia"
                    | b"RichMediaContent"
                    | b"3DD"
            ) || (key.as_slice() == b"S"
                && matches!(
                    value.as_name().ok(),
                    Some(
                        b"JavaScript"
                            | b"Launch"
                            | b"GoToR"
                            | b"GoToE"
                            | b"SubmitForm"
                            | b"ImportData"
                            | b"URI"
                            | b"Rendition"
                            | b"Movie"
                            | b"Sound"
                    )
                ))
                || (key.as_slice() == b"Type" && value.as_name().ok() == Some(b"EmbeddedFile"))
            {
                return Err(
                    "El PDF contiene acciones o adjuntos que no se admiten en una factura.".into(),
                );
            }
            pending.push((value, depth + 1));
        }
    }
    Ok(pages)
}

pub fn prepare_pdf(cache: &Path, name: &str, content: &str) -> Result<PreparedPdf, String> {
    if content.len() > MAX_PDF_BYTES.div_ceil(3) * 4 {
        return Err("El PDF supera 32 MiB. Guárdalo para revisarlo con tu lector.".into());
    }
    let bytes = STANDARD
        .decode(content)
        .map_err(|_| "El PDF recibido no tiene una codificación válida.".to_owned())?;
    let pages = validate_pdf(&bytes)?;
    let directory = cache.join("pdf-preview");
    std::fs::create_dir_all(&directory)
        .map_err(|_| "No se puede crear la carpeta temporal de PDF.".to_owned())?;
    let metadata = std::fs::symlink_metadata(&directory)
        .map_err(|_| "No se puede comprobar la carpeta temporal de PDF.".to_owned())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("La carpeta temporal de PDF no es una carpeta local válida.".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700))
            .map_err(|_| "No se pueden proteger los permisos del PDF temporal.".to_owned())?;
    }
    // Avoid the \?\ prefix in the ShellExecute Windows document argument.
    // app_cache_dir is already absolute; tests must follow that same contract.
    if !directory.is_absolute() {
        return Err("La carpeta temporal de PDF debe ser absoluta.".into());
    }
    let safe_name = suggested_name(name);
    let stem = safe_name.strip_suffix(".pdf").unwrap_or(&safe_name);
    let stem: String = stem.chars().take(50).collect();
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let path = directory.join(format!("pdf-{digest}-{stem}.pdf"));
    // Reuse identical immutable bytes: Windows viewers may hold an existing PDF
    // without sharing deletion, so replacing it would prevent a second print.
    let valid_cache = (|| -> std::io::Result<bool> {
        let metadata = std::fs::symlink_metadata(&path)?;
        if !metadata.is_file() || metadata.len() != bytes.len() as u64 {
            return Ok(false);
        }
        let mut reader = std::fs::File::open(&path)?.take(MAX_PDF_BYTES as u64 + 1);
        let mut hash = Sha256::new();
        let mut buffer = [0u8; 64 * 1024];
        loop {
            let read = reader.read(&mut buffer)?;
            if read == 0 {
                break;
            }
            hash.update(&buffer[..read]);
        }
        Ok(format!("{:x}", hash.finalize()) == digest)
    })()
    .unwrap_or(false);
    if !valid_cache {
        atomic_export(&path, &bytes).map_err(|_| {
            "No se puede preparar el PDF. Revisa espacio libre y permisos.".to_owned()
        })?;
    }
    // Leave a viewer enough time to reopen its file. Only our own regular cache
    // files older than seven days are eligible; never follow a link or recurse.
    if let Ok(entries) = std::fs::read_dir(&directory) {
        for entry in entries.flatten() {
            let candidate = entry.path();
            if candidate == path
                || !entry.file_name().to_string_lossy().starts_with("pdf-")
                || candidate.extension().and_then(|value| value.to_str()) != Some("pdf")
            {
                continue;
            }
            if let Ok(metadata) = std::fs::symlink_metadata(&candidate) {
                if metadata.is_file()
                    && metadata
                        .modified()
                        .ok()
                        .and_then(|time| SystemTime::now().duration_since(time).ok())
                        .is_some_and(|age| age > Duration::from_secs(7 * 24 * 3600))
                {
                    let _ = std::fs::remove_file(candidate);
                }
            }
        }
    }
    Ok(PreparedPdf { path, pages })
}

/// Exactly the URL shape built by MessageButton. No alternate hosts, ports,
/// userinfo, fragments, arbitrary query keys, control characters or raw shell
/// metacharacters are accepted. Percent escapes represent only the draft text.
pub fn validate_external_url(url: &str) -> Result<(), String> {
    let invalid =
        || "Solo se permite abrir un borrador en https://wa.me con un teléfono válido.".to_owned();
    if url.len() > 32_000 || !url.is_ascii() {
        return Err(invalid());
    }
    let path = url.strip_prefix("https://wa.me/").ok_or_else(invalid)?;
    let (phone, text) = path
        .split_once("?text=")
        .map_or((path, None), |(phone, text)| (phone, Some(text)));
    if !(9..=15).contains(&phone.len()) || !phone.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(invalid());
    }
    if let Some(text) = text {
        let mut bytes = text.bytes();
        let mut decoded = Vec::with_capacity(text.len());
        while let Some(byte) = bytes.next() {
            if byte == b'%' {
                let high = bytes.next().and_then(|byte| (byte as char).to_digit(16));
                let low = bytes.next().and_then(|byte| (byte as char).to_digit(16));
                let (Some(high), Some(low)) = (high, low) else {
                    return Err(invalid());
                };
                decoded.push((high * 16 + low) as u8);
            } else if byte.is_ascii_alphanumeric() || b"-_.!~*'()".contains(&byte) {
                decoded.push(byte);
            } else {
                return Err(invalid());
            }
        }
        let decoded = std::str::from_utf8(&decoded).map_err(|_| invalid())?;
        if decoded
            .chars()
            .any(|ch| ch == '\0' || (ch.is_control() && !matches!(ch, '\n' | '\r' | '\t')))
        {
            return Err(invalid());
        }
    }
    Ok(())
}

pub fn open_external(url: &str) -> Result<(), String> {
    validate_external_url(url)?;
    platform_request(OsStr::new(url), PdfAction::Open)
}

pub fn request_pdf(pdf: &PreparedPdf, action: PdfAction) -> Result<(), String> {
    platform_request(pdf.path.as_os_str(), action)
}

#[cfg(windows)]
fn platform_request(target: &OsStr, action: PdfAction) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::{
        System::Com::{
            CoInitializeEx, CoUninitialize, COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE,
        },
        UI::Shell::ShellExecuteW,
    };
    let target: Vec<u16> = target.encode_wide().chain(Some(0)).collect();
    if target[..target.len() - 1].contains(&0) {
        return Err("Destino no válido.".into());
    }
    let verb: Vec<u16> = match action {
        PdfAction::Open => "open",
        PdfAction::Print => "print",
    }
    .encode_utf16()
    .chain(Some(0))
    .collect();
    // A fresh thread avoids conflicting COM apartment settings from a runtime
    // worker. ShellExecute accepts the file association request, not the print
    // result. The target is a validated URL or our own absolute cached PDF.
    std::thread::spawn(move || {
        unsafe {
            let initialized = CoInitializeEx(std::ptr::null(), (COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) as u32);
            if initialized < 0 {
                return Err("No se puede iniciar el controlador de documentos de Windows.".into());
            }
            let result = ShellExecuteW(std::ptr::null_mut(), verb.as_ptr(), target.as_ptr(), std::ptr::null(), std::ptr::null(), 1) as isize;
            CoUninitialize();
            if result > 32 {
                Ok(())
            } else if action == PdfAction::Print {
                Err("Windows no ha aceptado la impresión. Revisa la impresora predeterminada y abre el PDF en tu lector para imprimirlo desde allí.".into())
            } else {
                Err("Windows no ha podido abrir el documento o enlace. Revisa la aplicación predeterminada.".into())
            }
        }
    }).join().map_err(|_| "Fallo del controlador de documentos de Windows.".to_owned())?
}

#[cfg(target_os = "linux")]
fn platform_request(target: &OsStr, action: PdfAction) -> Result<(), String> {
    let program = match action {
        PdfAction::Open => "xdg-open",
        PdfAction::Print => "lpr",
    };
    run_handler(OsStr::new(program), target, action, Duration::from_secs(15))
}

#[cfg(target_os = "linux")]
fn run_handler(
    program: &OsStr,
    target: &OsStr,
    action: PdfAction,
    timeout: Duration,
) -> Result<(), String> {
    use std::process::{Command, Stdio};
    let mut child = Command::new(program).arg(target)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .spawn().map_err(|_| match action {
            PdfAction::Open => "No se puede iniciar el lector. Revisa xdg-open y la aplicación predeterminada.",
            PdfAction::Print => "No se puede iniciar la impresión. Revisa CUPS/lpr y la impresora predeterminada, o abre el PDF en tu lector.",
        }.to_owned())?;
    let started = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(_)) | Err(_) => return Err(match action {
                PdfAction::Open => "El sistema no ha podido abrir el documento o enlace. Revisa la aplicación predeterminada.",
                PdfAction::Print => "El sistema no ha confirmado la impresión. Revisa la cola y la impresora predeterminada antes de repetir.",
            }.into()),
            Ok(None) => {}
        }
        // Some viewers keep xdg-open alive for the life of their window. The
        // request has been launched; reap it later without blocking the WebView.
        if action == PdfAction::Open && started.elapsed() >= Duration::from_secs(2) {
            std::thread::spawn(move || {
                let _ = child.wait();
            });
            return Ok(());
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Err("No se ha confirmado la impresión a tiempo. Revisa la cola antes de repetir para evitar duplicados.".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

#[cfg(not(any(windows, target_os = "linux")))]
fn platform_request(_target: &OsStr, _action: PdfAction) -> Result<(), String> {
    Err("La apertura e impresión nativas están disponibles en Windows y Linux.".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use lopdf::dictionary;

    fn pdf(action: Option<&str>) -> Vec<u8> {
        let mut document = Document::with_version("1.7");
        let pages = document.new_object_id();
        let page = document.add_object(dictionary! { "Type" => "Page", "Parent" => pages,
        "MediaBox" => vec![0.into(), 0.into(), 595.into(), 842.into()] });
        document.objects.insert(
            pages,
            dictionary! { "Type" => "Pages", "Kids" => vec![page.into()], "Count" => 1 }.into(),
        );
        let mut catalog = dictionary! { "Type" => "Catalog", "Pages" => pages };
        if let Some(action) = action {
            catalog.set(
                "OpenAction",
                dictionary! { "S" => action, "JS" => Object::string_literal("alert(1)") },
            );
        }
        let root = document.add_object(catalog);
        document.trailer.set("Root", root);
        let mut bytes = Vec::new();
        document.save_to(&mut bytes).unwrap();
        bytes
    }

    #[test]
    fn cache_contains_real_pdf_and_cannot_escape_into_a_supplied_path() {
        let cache = tempfile::tempdir().unwrap();
        let bytes = pdf(None);
        let content = STANDARD.encode(&bytes);
        let first = prepare_pdf(cache.path(), "../../CON.exe", &content).unwrap();
        assert_eq!(first.pages, 1);
        assert_eq!(
            first.path.parent().unwrap(),
            cache.path().join("pdf-preview")
        );
        assert_eq!(first.path.extension().unwrap(), "pdf");
        assert_eq!(std::fs::read(&first.path).unwrap(), bytes);
        let again = prepare_pdf(cache.path(), "../../CON.exe", &content).unwrap();
        assert_eq!(again.path, first.path);
        assert_eq!(
            std::fs::read_dir(first.path.parent().unwrap())
                .unwrap()
                .count(),
            1
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                std::fs::metadata(first.path.parent().unwrap())
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o700
            );
            assert_eq!(
                std::fs::metadata(first.path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
    }

    #[test]
    fn invalid_and_active_pdf_never_reach_the_cache() {
        let cache = tempfile::tempdir().unwrap();
        for bytes in [
            b"%PDF-1.7\nnot a PDF\n%%EOF".to_vec(),
            pdf(Some("JavaScript")),
            b"MZ binary".to_vec(),
        ] {
            assert!(prepare_pdf(cache.path(), "factura.pdf", &STANDARD.encode(bytes)).is_err());
        }
        assert!(!cache.path().join("pdf-preview").exists());
        let mut truncated = pdf(None);
        truncated.truncate(truncated.len() - 8);
        assert!(validate_pdf(&truncated).is_err());
        assert!(PdfAction::parse("runas").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn linked_cache_directory_cannot_overwrite_an_external_file() {
        let cache = tempfile::tempdir().unwrap();
        let external = tempfile::tempdir().unwrap();
        std::os::unix::fs::symlink(external.path(), cache.path().join("pdf-preview")).unwrap();
        assert!(prepare_pdf(cache.path(), "factura.pdf", &STANDARD.encode(pdf(None))).is_err());
        assert_eq!(std::fs::read_dir(external.path()).unwrap().count(), 0);
    }

    #[test]
    fn only_whatsapp_drafts_are_allowed_without_ever_opening_a_browser() {
        for valid in [
            "https://wa.me/34612000001",
            "https://wa.me/34612000001?text=Hola%20C%C3%A1%C3%B1amo%0A(12%2C50%20%E2%82%AC)!",
            "https://wa.me/34612000001?text=",
        ] {
            assert!(validate_external_url(valid).is_ok(), "{valid}");
        }
        for invalid in [
            "https://wa.me.evil.test/34612000001",
            "https://wa.me@evil.test/34612000001",
            "http://wa.me/34612000001",
            "file:///tmp/test.pdf",
            "https://wa.me:443/34612000001",
            "https://wa.me/34612000001#test",
            "https://wa.me/34612000001?text=hola&next=https://example.test",
            "https://wa.me/34612000001?text=%00",
            "https://wa.me/34612000001?text=%C3",
            "https://wa.me/34612000001?text=%",
            "https://wa.me/34612000001?text=$(pwd)",
            "https://wa.me/123",
            "https://wa.me/34612000001/../../test",
        ] {
            assert!(validate_external_url(invalid).is_err(), "{invalid}");
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn handler_is_a_direct_argument_and_print_rejection_and_timeout_are_reported() {
        use std::os::unix::fs::PermissionsExt;
        let cache = tempfile::tempdir().unwrap();
        let handler = cache.path().join("fake-lpr");
        let capture = cache.path().join("argument.txt");
        // Test-only receiver: no CUPS, real printer, browser or network request.
        std::fs::write(
            &handler,
            format!("#!/bin/sh\nprintf '%s' \"$1\" > '{}'\n", capture.display()),
        )
        .unwrap();
        std::fs::set_permissions(&handler, std::fs::Permissions::from_mode(0o700)).unwrap();
        let target = cache.path().join("$(not-a-command); acentos á.pdf");
        run_handler(
            handler.as_os_str(),
            target.as_os_str(),
            PdfAction::Print,
            Duration::from_secs(1),
        )
        .unwrap();
        assert_eq!(
            std::fs::read_to_string(capture).unwrap(),
            target.to_string_lossy()
        );
        std::fs::write(&handler, "#!/bin/sh\nexit 2\n").unwrap();
        assert!(run_handler(
            handler.as_os_str(),
            target.as_os_str(),
            PdfAction::Print,
            Duration::from_secs(1)
        )
        .is_err());
        std::fs::write(&handler, "#!/bin/sh\nexec sleep 10\n").unwrap();
        let error = run_handler(
            handler.as_os_str(),
            target.as_os_str(),
            PdfAction::Print,
            Duration::from_millis(25),
        )
        .unwrap_err();
        assert!(error.contains("duplicados"));
    }
}
