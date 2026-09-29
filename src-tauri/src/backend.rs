use crate::process::ManagedChild;
use serde_json::{json, Value};
use std::{
    io::{self, BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicU8, Ordering},
        mpsc, Arc, Mutex,
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

const RUNNING: u8 = 0;
const STOPPING: u8 = 1;
const FAILED: u8 = 2;
const STOPPED: u8 = 3;
const MAX_LINE: u64 = 300_000_000;
pub const RPC_TIMEOUT: Duration = Duration::from_secs(180);
const ARCHIVE_TIMEOUT: Duration = Duration::from_secs(30 * 60);
const JOB_WAITING: u8 = 0;
const JOB_ACTIVE: u8 = 1;
const JOB_CANCELLED: u8 = 2;
const BUSY: &str = "El servicio sigue ocupado con una operación anterior. Esta petición no se ha ejecutado; espera a que termine antes de repetirla.";
const UNAVAILABLE: &str = "El servicio no está disponible. Reinicia la aplicación y revisa el historial antes de repetir una emisión.";
const TIMED_OUT: &str = "El servicio ha agotado el tiempo de espera y se ha detenido. El resultado puede haberse guardado: reinicia y revisa el historial antes de repetir la operación.";

struct Job {
    action: String,
    params: Value,
    deadline: Instant,
    reply: mpsc::Sender<Result<Value, String>>,
    phase: Arc<AtomicU8>,
}

fn action_timeout(action: &str) -> Duration {
    match action {
        "backup.create"
        | "backup.prepare_transfer"
        | "backup.upload_finish"
        | "backup.restore"
        | "data.export"
        | "import.run"
        | "import.execute"
        | "import.rollback"
        | "app.shutdown" => ARCHIVE_TIMEOUT,
        _ => RPC_TIMEOUT,
    }
}

pub struct Backend {
    jobs: mpsc::SyncSender<Job>,
    child: Arc<Mutex<ManagedChild>>,
    state: Arc<AtomicU8>,
    worker: Mutex<Option<JoinHandle<()>>>,
}

pub fn sidecar_path(executable: &Path) -> io::Result<PathBuf> {
    let folder = executable
        .parent()
        .ok_or_else(|| io::Error::other("Falta la carpeta de instalación"))?;
    let sidecar = folder.join(if cfg!(windows) {
        "canamo-service.exe"
    } else {
        "canamo-service"
    });
    if !sidecar.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            "No se encuentra canamo-service junto a la aplicación. Reinstala el paquete completo.",
        ));
    }
    Ok(sidecar)
}

impl Backend {
    pub fn start(data: &Path) -> io::Result<Self> {
        let mut command = Command::new(sidecar_path(&std::env::current_exe()?)?);
        command.arg("--data").arg(data);
        Self::from_command(command)
    }

    /// Also used by integration tests with a real JSONL subprocess.
    pub fn from_command(mut command: Command) -> io::Result<Self> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut process = ManagedChild::spawn(&mut command)?;
        let mut input = process
            .child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("Falta stdin"))?;
        let output = process
            .child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("Falta stdout"))?;
        let child = Arc::new(Mutex::new(process));
        let state = Arc::new(AtomicU8::new(RUNNING));
        let (jobs, queue) = mpsc::sync_channel::<Job>(32);
        let worker_state = state.clone();
        let worker_child = child.clone();
        let worker = std::thread::spawn(move || {
            let mut reader = BufReader::new(output);
            let mut counter = 0_u64;
            for job in queue {
                // Do not execute queued mutations after the caller has timed out.
                if worker_state.load(Ordering::SeqCst) >= FAILED || Instant::now() >= job.deadline {
                    let _ = job.reply.send(Err(UNAVAILABLE.into()));
                    continue;
                }
                if job
                    .phase
                    .compare_exchange(JOB_WAITING, JOB_ACTIVE, Ordering::SeqCst, Ordering::SeqCst)
                    .is_err()
                {
                    let _ = job.reply.send(Err(BUSY.into()));
                    continue;
                }
                counter += 1;
                let request = json!({"id": counter, "action": job.action, "params": job.params});
                let result = (|| -> Result<Value, String> {
                    writeln!(input, "{request}")
                        .and_then(|_| input.flush())
                        .map_err(|_| UNAVAILABLE.to_owned())?;
                    let mut line = String::new();
                    reader
                        .by_ref()
                        .take(MAX_LINE + 1)
                        .read_line(&mut line)
                        .map_err(|_| "Respuesta no legible del servicio".to_owned())?;
                    if line.is_empty() || line.len() as u64 > MAX_LINE || !line.ends_with('\n') {
                        return Err(
                            "El servicio se ha cerrado o la respuesta está incompleta".into()
                        );
                    }
                    let value: Value = serde_json::from_str(&line)
                        .map_err(|_| "Respuesta JSON no válida".to_owned())?;
                    if value["id"].as_u64() != Some(counter) || !value["ok"].is_boolean() {
                        return Err("Respuesta fuera de secuencia o incompleta".into());
                    }
                    Ok(value)
                })();
                let failed = result.is_err();
                let shutdown = job.action == "app.shutdown"
                    && result.as_ref().is_ok_and(|response| response["ok"] == true);
                if failed {
                    worker_state.store(FAILED, Ordering::SeqCst);
                }
                let _ = job.reply.send(result);
                if failed || shutdown {
                    break;
                }
            }
            drop(input); // EOF lets Python run its finally cleanup if needed.
            if worker_state.load(Ordering::SeqCst) == FAILED {
                if let Ok(mut child) = worker_child.lock() {
                    let _ = child.terminate();
                }
            }
        });
        Ok(Self {
            jobs,
            child,
            state,
            worker: Mutex::new(Some(worker)),
        })
    }

    pub fn call(&self, action: String, params: Value) -> Result<Value, String> {
        let timeout = action_timeout(&action);
        self.call_with_timeout(action, params, timeout)
    }

    pub fn call_with_timeout(
        &self,
        action: String,
        params: Value,
        timeout: Duration,
    ) -> Result<Value, String> {
        if self.state.load(Ordering::SeqCst) != RUNNING {
            return Err(UNAVAILABLE.into());
        }
        self.request(action, params, timeout)
    }

    fn request(&self, action: String, params: Value, timeout: Duration) -> Result<Value, String> {
        let (send, receive) = mpsc::channel();
        let phase = Arc::new(AtomicU8::new(JOB_WAITING));
        self.jobs
            .try_send(Job {
                action,
                params,
                deadline: Instant::now() + timeout,
                reply: send,
                phase: phase.clone(),
            })
            .map_err(|error| match error {
                mpsc::TrySendError::Full(_) => {
                    "El servicio está ocupado. Espera antes de volver a intentarlo.".to_owned()
                }
                mpsc::TrySendError::Disconnected(_) => UNAVAILABLE.to_owned(),
            })?;
        match receive.recv_timeout(timeout) {
            Ok(result) => result,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                // A background refresh queued behind a large backup must not
                // kill that backup. Claim cancellation atomically before the
                // worker can send the queued operation to Python.
                if phase
                    .compare_exchange(
                        JOB_WAITING,
                        JOB_CANCELLED,
                        Ordering::SeqCst,
                        Ordering::SeqCst,
                    )
                    .is_ok()
                {
                    return Err(BUSY.into());
                }
                self.abort();
                Err(TIMED_OUT.into())
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                self.abort();
                Err(UNAVAILABLE.into())
            }
        }
    }

    /// Ask Python to finish its backup and return a positive acknowledgement.
    /// A business error keeps the service available so the user can resolve it.
    pub fn shutdown(&self) -> Result<(), String> {
        if self
            .state
            .compare_exchange(RUNNING, STOPPING, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            self.abort();
            return Ok(());
        }
        match self.request("app.shutdown".into(), json!({}), ARCHIVE_TIMEOUT) {
            Ok(response) if response["ok"] == true => {
                let deadline = Instant::now() + Duration::from_secs(10);
                loop {
                    let exited = self
                        .child
                        .lock()
                        .map_err(|_| UNAVAILABLE.to_owned())?
                        .child
                        .try_wait()
                        .map_err(|_| UNAVAILABLE.to_owned())?
                        .is_some();
                    if exited {
                        break;
                    }
                    if Instant::now() >= deadline {
                        self.abort();
                        return Err("El servicio no ha finalizado correctamente. Revisa la última copia al volver a abrir.".into());
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
                self.state.store(STOPPED, Ordering::SeqCst);
                self.join_worker();
                Ok(())
            }
            Ok(response) => {
                self.state.store(RUNNING, Ordering::SeqCst);
                Err(response["error"]["message"]
                    .as_str()
                    .unwrap_or(
                        "No se ha completado la copia al salir. Revisa las copias antes de cerrar.",
                    )
                    .to_owned())
            }
            Err(error) => {
                self.abort();
                Err(error)
            }
        }
    }

    pub fn abort(&self) {
        if self
            .state
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |state| {
                (state != STOPPED).then_some(FAILED)
            })
            .is_err()
        {
            return;
        }
        if let Ok(mut child) = self.child.lock() {
            let _ = child.terminate();
        }
    }

    fn join_worker(&self) {
        if let Ok(mut worker) = self.worker.lock() {
            if let Some(worker) = worker.take() {
                let _ = worker.join();
            }
        }
    }

    pub fn is_running(&self) -> bool {
        self.state.load(Ordering::SeqCst) == RUNNING
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        if self.state.load(Ordering::SeqCst) != STOPPED {
            self.abort();
        }
        // Worker can still wait on its channel; don't join while owning jobs.
        // Process ownership and EOF already guarantee teardown of its I/O.
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn python() -> PathBuf {
        if let Some(path) = std::env::var_os("CANAMO_TEST_PYTHON") {
            return PathBuf::from(path);
        }
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(if cfg!(windows) {
            "../.venv/Scripts/python.exe"
        } else {
            "../.venv/bin/python"
        });
        if path.is_file() {
            path
        } else {
            PathBuf::from(if cfg!(windows) { "python" } else { "python3" })
        }
    }

    fn stub(code: &str) -> Backend {
        let mut command = Command::new(python());
        command.arg("-u").arg("-c").arg(code);
        Backend::from_command(command).unwrap()
    }

    #[test]
    fn real_python_service_roundtrip_and_acknowledged_shutdown() {
        let directory = tempfile::tempdir().unwrap();
        let mut command = Command::new(python());
        command
            .arg("-m")
            .arg("taller.stdio")
            .arg("--data")
            .arg(directory.path())
            .arg("--no-background")
            .env(
                "PYTHONPATH",
                Path::new(env!("CARGO_MANIFEST_DIR")).join("../backend"),
            );
        let backend = Backend::from_command(command).unwrap();
        let response = backend.call("bootstrap".into(), json!({})).unwrap();
        assert_eq!(response["result"]["version"], env!("CARGO_PKG_VERSION"));
        let backup = backend
            .call(
                "backup.create".into(),
                json!({"password": "clave-sintetica-para-prueba"}),
            )
            .unwrap();
        assert_eq!(backup["ok"], true);
        let manifest = &backup["result"];
        let capability = manifest["capability"].as_str().unwrap();
        let download = directory.path().join("exportado.canamo");
        crate::export::atomic_download(
            &download,
            manifest["bytes"].as_u64().unwrap(),
            manifest["sha256"].as_str().unwrap(),
            |offset, length| {
                let reply = backend.call(
                    "backup.download_chunk".into(),
                    json!({"capability": capability, "offset": offset, "length": length}),
                )?;
                crate::export::DownloadChunk::from_reply(&reply)
            },
        )
        .unwrap();
        assert_eq!(
            std::fs::metadata(download).unwrap().len(),
            manifest["bytes"].as_u64().unwrap()
        );
        assert_eq!(
            backend
                .call(
                    "backup.release_download".into(),
                    json!({"capability": capability})
                )
                .unwrap()["ok"],
            true
        );
        assert_eq!(
            backend
                .call(
                    "backup.download_chunk".into(),
                    json!({"capability": capability, "offset": 0})
                )
                .unwrap()["ok"],
            false
        );
        backend.shutdown().unwrap();
        assert!(backend
            .child
            .lock()
            .unwrap()
            .child
            .try_wait()
            .unwrap()
            .is_some());
        assert!(backend.call("bootstrap".into(), json!({})).is_err());
    }

    #[test]
    fn malformed_reply_stops_service_instead_of_desynchronizing() {
        let backend = stub("import sys\nsys.stdin.readline()\nprint('{\"id\":999,\"ok\":true}',flush=True)\nsys.stdin.read()\n");
        assert!(backend
            .call("bootstrap".into(), json!({}))
            .unwrap_err()
            .contains("secuencia"));
        assert!(backend.call("documents.publish".into(), json!({})).is_err());
        backend.abort();
        assert!(backend
            .child
            .lock()
            .unwrap()
            .child
            .try_wait()
            .unwrap()
            .is_some());
    }

    #[test]
    fn crashed_sidecar_returns_error_without_hanging() {
        let backend = stub("import sys\nsys.stdin.readline()\nsys.exit(4)\n");
        assert!(backend
            .call_with_timeout("bootstrap".into(), json!({}), Duration::from_secs(5))
            .is_err());
        assert!(!backend.is_running());
    }

    #[test]
    fn timeout_terminates_process_and_never_runs_queued_mutation() {
        let directory = tempfile::tempdir().unwrap();
        let started = directory.path().join("started");
        let mutation = directory.path().join("must-not-exist");
        let source = format!("import sys,time,json,pathlib\nfor line in sys.stdin:\n r=json.loads(line)\n if r['action']=='hang':\n  pathlib.Path({}).write_text('started')\n  time.sleep(30)\n else:\n  pathlib.Path({}).write_text('executed')\n print(json.dumps({{'id':r['id'],'ok':True,'result':{{}}}}),flush=True)\n", serde_json::to_string(&started.to_string_lossy()).unwrap(), serde_json::to_string(&mutation.to_string_lossy()).unwrap());
        let backend = Arc::new(stub(&source));
        let caller = backend.clone();
        let hanging = std::thread::spawn(move || {
            caller.call_with_timeout("hang".into(), json!({}), Duration::from_secs(2))
        });
        let deadline = Instant::now() + Duration::from_secs(1);
        while !started.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(started.exists());
        let queued = backend.call_with_timeout(
            "documents.publish".into(),
            json!({}),
            Duration::from_secs(5),
        );
        assert!(hanging.join().unwrap().unwrap_err().contains("resultado"));
        assert!(queued.is_err());
        assert!(!mutation.exists());
        assert!(backend
            .child
            .lock()
            .unwrap()
            .child
            .try_wait()
            .unwrap()
            .is_some());
    }

    #[test]
    fn backup_error_keeps_service_available_until_fixed() {
        let backend = stub("import sys,json\nshutdowns=0\nfor line in sys.stdin:\n r=json.loads(line)\n if r['action']=='app.shutdown':\n  shutdowns+=1\n  if shutdowns==1:\n   print(json.dumps({'id':r['id'],'ok':False,'error':{'message':'Disco ausente'}}),flush=True)\n   continue\n print(json.dumps({'id':r['id'],'ok':True,'result':{}}),flush=True)\n if shutdowns>1: break\n");
        assert_eq!(backend.shutdown().unwrap_err(), "Disco ausente");
        assert!(backend.call("bootstrap".into(), json!({})).unwrap()["ok"] == true);
        backend.shutdown().unwrap();
    }

    #[test]
    fn expired_queued_mutation_does_not_interrupt_the_active_operation() {
        let directory = tempfile::tempdir().unwrap();
        let started = directory.path().join("started");
        let mutation = directory.path().join("must-not-exist");
        let source = format!("import sys,time,json,pathlib\nfor line in sys.stdin:\n r=json.loads(line)\n if r['action']=='slow':\n  pathlib.Path({}).write_text('started')\n  time.sleep(0.3)\n if r['action']=='documents.publish':\n  pathlib.Path({}).write_text('executed')\n print(json.dumps({{'id':r['id'],'ok':True,'result':{{}}}}),flush=True)\n", serde_json::to_string(&started.to_string_lossy()).unwrap(), serde_json::to_string(&mutation.to_string_lossy()).unwrap());
        let backend = Arc::new(stub(&source));
        let caller = backend.clone();
        let active = std::thread::spawn(move || {
            caller.call_with_timeout("slow".into(), json!({}), Duration::from_secs(3))
        });
        let deadline = Instant::now() + Duration::from_secs(2);
        while !started.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(5));
        }
        assert!(started.exists());
        let error = backend
            .call_with_timeout(
                "documents.publish".into(),
                json!({}),
                Duration::from_millis(25),
            )
            .unwrap_err();
        assert!(error.contains("no se ha ejecutado"));
        assert!(active.join().unwrap().unwrap()["ok"] == true);
        assert!(backend.call("bootstrap".into(), json!({})).unwrap()["ok"] == true);
        assert!(!mutation.exists());
        assert!(backend.is_running());
        assert!(action_timeout("backup.create") > RPC_TIMEOUT);
        assert_eq!(action_timeout("backup.download_chunk"), RPC_TIMEOUT);
    }

    #[test]
    fn sidecar_is_resolved_only_beside_installed_executable() {
        let directory = tempfile::tempdir().unwrap();
        let app = directory.path().join("Talleres El Cáñamo.exe");
        assert!(sidecar_path(&app).is_err());
        let expected = directory.path().join(if cfg!(windows) {
            "canamo-service.exe"
        } else {
            "canamo-service"
        });
        std::fs::write(&expected, b"fixture").unwrap();
        assert_eq!(sidecar_path(&app).unwrap(), expected);
    }
}
