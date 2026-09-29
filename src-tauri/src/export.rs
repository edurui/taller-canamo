use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{self, Write},
    path::Path,
};

pub const DOWNLOAD_CHUNK_BYTES: usize = 1024 * 1024;
pub const MAX_DOWNLOAD_BYTES: u64 = 16 * 1024 * 1024 * 1024;

pub struct DownloadChunk {
    offset: u64,
    total_bytes: u64,
    eof: bool,
    bytes: Vec<u8>,
    sha256: String,
}

impl DownloadChunk {
    pub fn from_reply(reply: &Value) -> Result<Self, String> {
        if reply["ok"] != true {
            return Err(reply["error"]["message"]
                .as_str()
                .unwrap_or("No se ha podido leer la copia.")
                .to_owned());
        }
        let value = &reply["result"];
        let invalid = || "El servicio ha devuelto un fragmento de copia no válido.".to_owned();
        let content = value["content"].as_str().ok_or_else(invalid)?;
        if content.len() > DOWNLOAD_CHUNK_BYTES.div_ceil(3) * 4 {
            return Err(invalid());
        }
        let bytes = STANDARD.decode(content).map_err(|_| invalid())?;
        if bytes.len() as u64 != value["bytes"].as_u64().ok_or_else(invalid)? {
            return Err(invalid());
        }
        Ok(Self {
            offset: value["offset"].as_u64().ok_or_else(invalid)?,
            total_bytes: value["total_bytes"].as_u64().ok_or_else(invalid)?,
            eof: value["eof"].as_bool().ok_or_else(invalid)?,
            sha256: value["sha256"].as_str().ok_or_else(invalid)?.to_owned(),
            bytes,
        })
    }
}

pub fn validate_download(capability: &str, bytes: u64, sha256: &str) -> Result<(), String> {
    if !(20..=256).contains(&capability.len())
        || !capability
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-_".contains(&byte))
    {
        return Err("El permiso temporal de descarga no es válido.".into());
    }
    if bytes == 0
        || bytes > MAX_DOWNLOAD_BYTES
        || sha256.len() != 64
        || !sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("El tamaño o la huella de la descarga no son válidos.".into());
    }
    Ok(())
}

/// Holds at most one decoded block and one RPC reply. Any read, order, size,
/// hash, write or rename error drops the private partial without changing the
/// previous destination. The server owns the capability; no path crosses RPC.
pub fn atomic_download(
    path: &Path,
    total_bytes: u64,
    sha256: &str,
    mut fetch: impl FnMut(u64, usize) -> Result<DownloadChunk, String>,
) -> Result<(), String> {
    if total_bytes == 0
        || total_bytes > MAX_DOWNLOAD_BYTES
        || sha256.len() != 64
        || !sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("El tamaño o la huella de la descarga no son válidos.".into());
    }
    atomic_export_with(path, |file| {
        let mut position = 0u64;
        let mut digest = Sha256::new();
        while position < total_bytes {
            let length = (total_bytes - position).min(DOWNLOAD_CHUNK_BYTES as u64) as usize;
            let chunk = fetch(position, length).map_err(io::Error::other)?;
            let next = position + chunk.bytes.len() as u64;
            if chunk.offset != position || chunk.total_bytes != total_bytes || chunk.bytes.is_empty()
                || chunk.bytes.len() > length || chunk.eof != (next == total_bytes)
                || !format!("{:x}", Sha256::digest(&chunk.bytes)).eq_ignore_ascii_case(&chunk.sha256)
            {
                return Err(io::Error::other("La copia contiene un fragmento incompleto, fuera de orden o con huella distinta. El destino anterior se conserva."));
            }
            digest.update(&chunk.bytes);
            file.write_all(&chunk.bytes)?;
            position = next;
        }
        if !format!("{:x}", digest.finalize()).eq_ignore_ascii_case(sha256) {
            return Err(io::Error::other("La huella completa de la copia no coincide. El destino anterior se conserva."));
        }
        Ok(())
    }).map_err(|error| format!("No se ha guardado la copia: {error}"))
}

/// Write beside the destination, flush, then replace in one filesystem operation.
/// A failed write leaves the previous document intact, including disk-full errors.
pub fn atomic_export(path: &Path, content: &[u8]) -> io::Result<()> {
    atomic_export_with(path, |file| file.write_all(content))
}

fn atomic_export_with(
    path: &Path,
    write: impl FnOnce(&mut File) -> io::Result<()>,
) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("Falta la carpeta de destino"))?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    write(temporary.as_file_mut())?;
    temporary.as_file().sync_all()?;
    temporary.persist(path).map_err(|error| error.error)?;
    Ok(())
}

pub fn suggested_name(name: &str) -> String {
    let filename = name.rsplit(['/', '\\']).next().unwrap_or("");
    let filename: String = filename
        .chars()
        .filter(|ch| !ch.is_control() && !"<>:\"|?*".contains(*ch))
        .take(180)
        .collect();
    let filename = filename.trim_matches([' ', '.']);
    if filename.is_empty() {
        "documento.pdf".to_owned()
    } else {
        filename.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_write_never_truncates_existing_export() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("factura.pdf");
        std::fs::write(&path, b"factura original").unwrap();
        let result = atomic_export_with(&path, |file| {
            file.write_all(b"incompleto")?;
            Err(io::Error::other("fallo de disco simulado"))
        });
        assert!(result.is_err());
        assert_eq!(std::fs::read(&path).unwrap(), b"factura original");
        assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 1);
    }

    #[test]
    fn replacement_failure_keeps_destination() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("carpeta");
        std::fs::create_dir(&path).unwrap();
        std::fs::write(path.join("conservar"), b"contenido").unwrap();
        assert!(atomic_export(&path, b"archivo").is_err());
        assert_eq!(std::fs::read(path.join("conservar")).unwrap(), b"contenido");
        assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 1);
    }

    #[test]
    fn completed_export_replaces_existing_file() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("factura.pdf");
        std::fs::write(&path, b"anterior").unwrap();
        atomic_export(&path, b"nueva factura completa").unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"nueva factura completa");
    }

    #[test]
    fn suggestion_contains_no_path_or_control_characters() {
        assert_eq!(suggested_name("C:\\privado\\factura.pdf"), "factura.pdf");
        assert_eq!(suggested_name("../.\n"), "documento.pdf");
    }

    fn block(bytes: &[u8], offset: u64, total: u64) -> DownloadChunk {
        DownloadChunk {
            offset,
            total_bytes: total,
            eof: offset + bytes.len() as u64 == total,
            sha256: format!("{:x}", Sha256::digest(bytes)),
            bytes: bytes.to_vec(),
        }
    }

    #[test]
    fn streaming_copy_verifies_every_block_and_the_complete_file_before_replacing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("copia existente.canamo");
        std::fs::write(&path, b"original").unwrap();
        let content = vec![7u8; DOWNLOAD_CHUNK_BYTES * 3 + 61];
        let hash = format!("{:x}", Sha256::digest(&content));
        let mut requested = Vec::new();
        atomic_download(&path, content.len() as u64, &hash, |offset, length| {
            requested.push((offset, length));
            let bytes = &content[offset as usize..offset as usize + length];
            let reply = serde_json::json!({"ok": true, "result": {
                "content": STANDARD.encode(bytes), "offset": offset, "bytes": bytes.len(),
                "total_bytes": content.len(), "eof": offset as usize + length == content.len(),
                "sha256": format!("{:x}", Sha256::digest(bytes))
            }});
            DownloadChunk::from_reply(&reply)
        })
        .unwrap();
        assert_eq!(requested.len(), 4);
        assert!(requested
            .iter()
            .all(|(_, length)| *length <= DOWNLOAD_CHUNK_BYTES));
        assert_eq!(std::fs::read(path).unwrap(), content);
        assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 1);
    }

    #[test]
    fn streaming_failure_never_truncates_and_removes_its_partial() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("copia.canamo");
        let content = vec![1u8; DOWNLOAD_CHUNK_BYTES + 3];
        let hash = format!("{:x}", Sha256::digest(&content));
        for fault in [
            "offset",
            "size",
            "eof",
            "empty",
            "block-hash",
            "global-hash",
            "read-error",
        ] {
            std::fs::write(&path, b"anterior completa").unwrap();
            let global_hash = if fault == "global-hash" {
                "0".repeat(64)
            } else {
                hash.clone()
            };
            let result = atomic_download(
                &path,
                content.len() as u64,
                &global_hash,
                |offset, length| {
                    if offset > 0 && fault == "read-error" {
                        return Err("cancelado en la prueba".into());
                    }
                    let mut chunk = block(
                        &content[offset as usize..offset as usize + length],
                        offset,
                        content.len() as u64,
                    );
                    if offset > 0 {
                        match fault {
                            "offset" => chunk.offset -= 1,
                            "size" => chunk.total_bytes += 1,
                            "eof" => chunk.eof = false,
                            "empty" => chunk.bytes.clear(),
                            "block-hash" => chunk.bytes[0] = 2,
                            _ => {}
                        }
                    }
                    Ok(chunk)
                },
            );
            assert!(result.is_err(), "{fault}");
            assert_eq!(std::fs::read(&path).unwrap(), b"anterior completa");
            assert_eq!(
                std::fs::read_dir(directory.path()).unwrap().count(),
                1,
                "{fault}"
            );
        }
        let oversized = serde_json::json!({"ok": true, "result": {"content": "A".repeat(DOWNLOAD_CHUNK_BYTES.div_ceil(3) * 4 + 4)}});
        assert!(DownloadChunk::from_reply(&oversized).is_err());
    }
}
