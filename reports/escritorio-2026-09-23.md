> Hito histórico. Estado integrado final: [escritorio-final-2026-09-23.md](escritorio-final-2026-09-23.md).

# Escritorio: evidencia de 2026-09-23

Este informe cubre el puente, servicio empaquetado y Tauri. No declara producción fiscal ni
Windows probado. El trabajo general continúa en otros módulos; reconstruir el sidecar después
de integrar sus cambios, antes de entregar un artefacto actualizado.

## Entorno

Ubuntu 24.04.5 x86_64; Python 3.13.2 del entorno virtual del proyecto; Node 22.22.2;
Rust 1.98.1 / Cargo resuelto de rustup oficial; Tauri 2.11.6; tauri-driver 2.0.6;
WebKitGTK/WebKitWebDriver 2.52.6. No hay un equipo/runner Windows disponible.

Rust se instaló para el usuario sin modificar PATH ni instrucciones globales. Sudo sin contraseña
no está disponible. Los paquetes de desarrollo GTK/WebKit/AppIndicator, WebKitWebDriver y Xvfb
se descargaron desde los repositorios oficiales de Ubuntu con `apt-get --download-only` y se
extrajeron bajo `/tmp/canamo-linux-sdk`; no se instalaron en el sistema. Los .pc privados apuntan
a esa extracción y los .so de desarrollo al runtime que ya estaba instalado.

## Cambios verificados

- Lock Rust real y toolchain fijado; biblioteca del puente verificable sin depender de un WebView.
- Instancia única registrada antes del arranque del servicio; segunda apertura muestra la ventana.
- Sidecar resuelto junto al ejecutable con el nombre sin triple del target; comprobación de versión
  al arrancar. Sin shell arbitraria expuesta al frontend, sin Python externo ni servidor HTTP nativo.
- Cola acotada y espera de RPC de 180 s. Una espera agotada cancela el árbol de procesos e impide
  ejecutar después una mutación que quedase en cola. No se reintentan escrituras automáticamente.
- Windows: Job Object con KILL_ON_JOB_CLOSE, arranque suspendido, asociación al job y reanudación
  mediante API Win32 oficial. Incluye el proceso hijo que crea PyInstaller onefile. El código Win32
  compila por tipos; **no se ha ejecutado en Windows**.
- Cierre con acuse de `app.shutdown`; error de copia conserva el servicio para poder resolverlo.
  Python termina tras vaciar la respuesta y no duplica la copia en finally. Proceso y worker se
  recogen; reapertura comprobada con datos temporales.
- X oculta la ventana; bandeja con Abrir y Salir. Protección de editor sucio mediante
  `set_document_dirty`; ventana deshabilitada mientras se completa el cierre. El aviso del sistema
  se solicita desde Rust aunque el WebView esté oculto; pendientes agrupados; sonido configurable.
- Windows consulta ToastNotifier.Setting y propaga errores de Show. Se evitó el plugin de
  notificaciones después de comprobar en su fuente que devolvía Granted y descartaba errores.
  La aceptación de Show no significa que el usuario haya visto una alerta.
- Inicio al iniciar sesión opcional mediante plugin Autostart y comandos limitados; no se activa
  automáticamente. El argumento --background deja la ventana en la bandeja.
- Guardado nativo por archivo temporal en la misma carpeta, sync y reemplazo; error durante
  escritura o reemplazo conserva el destino anterior. Cancelar devuelve saved:false.
- PyInstaller incluye tzdata y los esquemas AEAT; script Windows ejecuta las verificaciones y
  genera huellas. Workflow manual con acciones fijadas, locks, instalador, diagnóstico instalado
  y prueba de UI con WebView2. No se ha ejecutado/publicado el workflow.

## Comandos y resultados

Los comandos Cargo se ejecutaron desde `src-tauri` (usa rust-toolchain.toml). Para compilar GUI en
este entorno se añadieron exclusivamente al proceso:

```bash
export PKG_CONFIG_PATH=/tmp/canamo-linux-sdk/usr/lib/x86_64-linux-gnu/pkgconfig:/tmp/canamo-linux-sdk/usr/share/pkgconfig
export LIBRARY_PATH=/tmp/canamo-linux-sdk/usr/lib/x86_64-linux-gnu
```

| Comando | Resultado ejecutado | Evidencia |
|---|---|---|
| `cargo generate-lockfile` | 0; resolución real de dependencias | `src-tauri/Cargo.lock` |
| `cargo test --locked --no-default-features --lib` | 0; 10 pruebas | `rust-services-2026-09-23.txt` |
| `cargo check --locked` | 0; Tauri/GTK/WebKit completos | `tauri-linux-check-2026-09-23.txt` |
| `cargo build --locked` | 0; binario Linux enlazado | `tauri-linux-build-2026-09-23.txt` |
| `cargo clippy --locked --all-targets -- -D warnings` | 0 | `tauri-clippy-2026-09-23.txt` |
| `cargo check --locked --no-default-features --features native-notifications --lib --target x86_64-pc-windows-msvc` | 0; procesos Win32 y WinRT comprobados por tipos, sin enlazar | `rust-windows-typecheck-2026-09-23.txt` |
| `.venv/bin/python -m pytest` tras cambiar stdio | 0; 147 pruebas en esa instantánea | `pytest-desktop-2026-09-23.txt` |
| `.venv/bin/python scripts/build_desktop.py --sidecar-only` | 0; PyInstaller ejecutable Linux e IPC comprobados | `sidecar-build-2026-09-23.txt`, `sidecar-artifact.json` |
| `src-tauri/target/debug/taller-canamo --diagnose-sidecar "$PWD/reports/linux-packaged-sidecar.json"` | 0; emisión sintética, PDF, cierre y reapertura del mismo histórico | `linux-packaged-sidecar.json` |

Las pruebas Rust incluyen proceso Python real, caída del sidecar, respuesta con identificador
incorrecto, timeout con otra escritura en cola, copia final fallida/reintento y preservación del
archivo durante fallo de disco/reemplazo. Los tres tests nuevos de `tests/test_stdio_lifecycle.py`
verifican acuse, ausencia de copia duplicada, servicio disponible tras error y salida sin esperar EOF.
El total Python es una ejecución fechada; consultar el informe final general para la integración posterior.

## Escritorio real y captura

Prueba en el repositorio: `src-tauri/tests/desktop_smoke.py`. Solo usa la biblioteca estándar
Python y los drivers nativos; el cliente Windows final no los recibe. Comando en este entorno:

```bash
.venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --driver /home/eruizgarcia/.cargo/bin/tauri-driver \
  --native-driver /tmp/canamo-linux-sdk/usr/bin/WebKitWebDriver \
  --xvfb /tmp/canamo-linux-sdk/usr/bin/Xvfb
```

El script ejecuta Tauri sobre un Xvfb propio, bus D-Bus propio y carpetas de usuario temporales.
No hay mocks de RPC. Crea demo desde la interfaz; busca `0826lfg`, comprueba `612 000 001`, abre
la ficha con Enter, obtiene PDF real y verifica que una segunda instancia termina manteniendo
la primera. `reports/desktop/result.json` contiene el resultado; `native-window.png` muestra la
ficha sintética; `desktop-run-2026-09-23.txt` conserva la ejecución.

Durante el ajuste del harness se detectaron dos fallos de sincronización, resueltos: escribir
antes de cerrar el diálogo de demo y eliminar el temporal mientras los servicios D-Bus seguían
activos. Se espera el cierre del diálogo y se controla el bus desde el propio script. No se
modificaron validaciones del producto para pasar estas comprobaciones.

## Artefactos realmente generados

- `src-tauri/target/debug/taller-canamo`: ELF Linux de desarrollo con símbolos, **no instalador Windows**.
- `src-tauri/binaries/canamo-service-x86_64-unknown-linux-gnu`: servicio PyInstaller Linux,
  33.182.456 bytes, SHA-256 `27584b86d001466334c373cb45b1526105a64a1703ba90abdd65f689e2538997`.
- `src-tauri/target/debug/canamo-service`: copia realizada por Tauri para ejecutar el conjunto.
- Captura nativa e informes referidos arriba. Todos los datos de demostración son ficticios.

El binario PyInstaller corresponde al primer build de esta sesión. Otros agentes siguen editando
backend/dependencias/PDF. **No etiquetarlo como paquete final del código integrado**; ejecutar de
nuevo el constructor al estabilizar esa integración. El script actualizado incorpora hashes de
fuentes y dependencias del entorno en los nuevos manifiestos.

## Verificación externa pendiente

No se ha compilado/enlazado Windows, creado NSIS, instalado en un Windows limpio, comprobado
visualmente un toast/sonido en Windows, probado inicio de sesión/reinicio, impresora, DPAPI,
actualización/reinstalación o caída forzada con Job Object en ejecución. La prueba Linux de UI
no verifica todas las interacciones de bandeja ni un guardado con diálogo Windows. Esas pruebas
tienen pasos concretos en `docs/BUILD-WINDOWS.md`, scripts completos y gates preparados en el
workflow; no se consideran ejecutadas por estar escritas.

## Fuentes

Consultadas el 2026-09-23: [sidecars Tauri](https://v2.tauri.app/develop/sidecar/),
[instancia única](https://v2.tauri.app/plugin/single-instance/),
[bandeja](https://v2.tauri.app/learn/system-tray/),
[WebDriver nativo](https://v2.tauri.app/develop/tests/webdriver/manual-setup/),
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[Thread32First](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-thread32first),
[ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread),
[ToastNotifier.Setting](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotifier.setting)
y [reemplazo con tempfile](https://docs.rs/tempfile/latest/tempfile/struct.NamedTempFile.html#method.persist).
