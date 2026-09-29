> Hito histórico. Estado integrado final: [escritorio-final-2026-09-23.md](escritorio-final-2026-09-23.md).

# PDF nativo y guardado por fragmentos · 23 de septiembre de 2026

## Código implementado

- `src-tauri/src/desktop_files.rs`: PDF base64 limitado a 32 MiB, estructura comprobada
  con lopdf 0.45.0 (lock real), 1–2.000 páginas, rechazo de cifrado/acciones/adjuntos,
  caché del usuario con nombre seguro y SHA-256. Directorio 0700 y archivo 0600 en Linux.
  Reutiliza una copia idéntica para admitir lectores Windows que mantienen abierto el archivo.
- Windows: `ShellExecuteW`, COM inicializado en un hilo STA, verbos fijos `open`/`print`,
  argumento UTF-16 y errores de asociación propagados. Linux: argumentos separados para
  `xdg-open`/`lpr`, manejo de errores y plazo de impresión. No hay ejecución de una cadena shell.
- `PdfPreview` muestra Guardar PDF, Abrir en lector e Imprimir, espera la respuesta y presenta
  el resultado/error. Indica el uso de la impresora predeterminada. La aceptación de una
  solicitud no se presenta como impresión física confirmada.
- `open_external` restringe exactamente HTTPS `wa.me`, teléfono y query `text` codificada.
  Rechaza otro host/esquema/puerto/credenciales/fragmento/parámetro. Lo invoca el botón que
  abre el borrador; no manda mensajes.
- `export.rs` y `save_export`: permiso temporal opaco, lectura de un bloque de hasta 1 MiB,
  verificación de offset/tamaño/EOF/SHA por bloque y SHA global, archivo temporal privado,
  flush y sustitución atómica. Cancelación del diálogo/error revocan el permiso. Los archivos
  pequeños conservan el contrato base64. Se bloquea otra exportación o salir mientras guarda.
- `backend.rs`: 30 minutos para operaciones que pueden recorrer copias grandes; 180 segundos
  para las ordinarias. Una petición que caduca aún en cola se cancela mediante CAS sin matar
  una copia activa. Si ya se envió y caduca, sigue deteniéndose el servicio sin reintento.
- Windows workflow crea `.venv`, usa sus dependencias con hashes y ese intérprete en E2E,
  construye el frontend antes de probarlo y archiva los manuales. No se ha ejecutado el workflow.

## Evidencia ejecutada

| Comando / recorrido | Resultado | Evidencia |
| --- | --- | --- |
| `cargo test --locked --no-default-features --lib` | 18 correctos, código 0 | `rust-pdf-streaming-2026-09-23.txt` |
| `cargo check --locked --no-default-features --features native-notifications --lib --target x86_64-pc-windows-msvc` | Código 0; tipos Win32/COM/ShellExecute, sin enlazar ni ejecutar | `rust-pdf-windows-typecheck-2026-09-23.txt` |
| `cargo check --locked`, `cargo build --locked`, `cargo clippy --locked --all-targets -- -D warnings` con SDK Linux local | Código 0 | Salida de herramientas de esta sesión |
| `npm run typecheck` | Código 0 tras PdfPreview | Salida de herramientas de esta sesión |
| Ventana Tauri / WebKit real → botones PDF → Rust → receptores locales | Correcto; captura inspeccionada | `desktop-pdf/result.json`, `native-window.png`, `document-handler-invocations.json` |
| `scripts/verify_sidecar.py --source-check` | Correcto, explícitamente `packaged:false` | `sidecar-verifier-source-check.json` |

Las pruebas Rust cubren el PDF falso/activo/truncado, cache bajo nombre hostil/symlink,
URL restringida, argumento literal con metacaracteres, fallo/timeout del receptor de impresión,
fragmentos fuera de orden/manipulados/truncados, hash final incorrecto, lectura cancelada y
conservación del destino previo. La integración Rust arranca el servicio Python real, crea
una copia cifrada, la descarga mediante capability, verifica el archivo, revoca el permiso,
comprueba su rechazo posterior y espera el acuse de cierre. La regresión de cola comprueba
que una mutación caducada no se ejecuta después de terminar la petición activa.

El smoke nativo utiliza el servicio PyInstaller del primer hito junto al ejecutable Tauri
recompilado y el `dist` integrado vigente en esa ejecución. Acredita el puente y la interfaz
PDF, pero **no acredita aún** el PDF/backend nuevo ni los modelos/JRE añadidos después de ese
primer sidecar. La reconstrucción integrada del servicio queda registrada separadamente.

## Reproducción Linux de la prueba nativa

Entorno: Linux x86_64, Rust 1.98.1, tauri-driver 2.0.6, WebKitWebDriver/Xvfb de paquetes
oficiales Ubuntu extraídos en `/tmp/canamo-linux-sdk`. No se instalaron globalmente.

```bash
cd src-tauri
PKG_CONFIG_PATH=/tmp/canamo-linux-sdk/usr/lib/x86_64-linux-gnu/pkgconfig:/tmp/canamo-linux-sdk/usr/share/pkgconfig \
LIBRARY_PATH=/tmp/canamo-linux-sdk/usr/lib/x86_64-linux-gnu \
  /home/eruizgarcia/.cargo/bin/cargo build --locked
cd ..
.venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --driver /home/eruizgarcia/.cargo/bin/tauri-driver \
  --native-driver /tmp/canamo-linux-sdk/usr/bin/WebKitWebDriver \
  --xvfb /tmp/canamo-linux-sdk/usr/bin/Xvfb \
  --test-document-handlers --output reports/desktop-pdf
```

La opción crea una sesión D-Bus/XDG/Xvfb y receptores locales `xdg-open`/`lpr` que solo
registran ruta, tamaño y hash del PDF sintético. No llama al navegador ni a una cola de
impresión del usuario. Comprueba que abrir la vista previa no lanza programas y que el botón
Imprimir muestra el error del receptor cuando se fuerza un código de salida no cero.

## Comprobador del paquete

`scripts/verify_sidecar.py --executable <canamo-service> --output <informe.json>` recorre
demostración/PDF/cadena fiscal, ejemplo oficial CEN y generación UBL con SaxonC, audio Vosk
e imagen RapidOCR/ONNX mediante trabajos asíncronos, bootstrap mientras el motor trabaja,
ACCDB sintético real leído con JRE/Jackcess, licencias, copia cifrada y reapertura. Registra
arranque/reapertura y tiempo de cada llamada. El builder exige este recorrido después de
PyInstaller e incluye todos los recursos correspondientes.

## Límites verificados

### Avisos de dependencias Rust

La auditoría guardada en `reports/cargo-audit-final-2026-09-23.json` informa de cero
avisos de la categoría `vulnerabilities` y **siete advertencias**, que no se han ignorado:
seis dependencias sin mantenimiento (`proc-macro-error` y cinco crates `unic-*`) y el aviso
de seguridad de memoria de GLib 0.18.5, RUSTSEC-2024-0429. No es una auditoría sin avisos.

`cargo tree --locked --target x86_64-pc-windows-msvc -i glib` devuelve un árbol vacío,
conservado en `reports/glib-windows-tree-2026-09-23.txt`. El árbol Linux correspondiente sí
incluye GLib a través de GTK 3, WebKit y la bandeja. La búsqueda en los módulos propios y
los módulos principales de Tauri/GTK usados no encontró llamadas a `VariantStrIter`; esa
búsqueda no demuestra que ninguna ruta indirecta pueda alcanzarlo.

El [aviso oficial](https://rustsec.org/advisories/RUSTSEC-2024-0429.html) describe escritura
a través de una referencia inmutable en ese iterador y fija versiones corregidas desde
0.20.0. La [corrección de gtk-rs](https://github.com/gtk-rs/gtk-rs-core/pull/1343) está publicada.
GTK 0.18, requerido por esta versión de Tauri en Linux, exige GLib 0.18; cambiar solo la
versión de GLib no es compatible. Se conserva el aviso y su alcance: el paquete Windows
resuelto no incorpora este crate; las pruebas de desarrollo Linux sí usan una versión
afectada. No se presenta el ejecutable Linux como una entrega liberada sin esta limitación.

No hay Windows disponible: no se acredita instalador, asociaciones PDF ni impresora Windows.
No se ha abierto WhatsApp, enviado mensaje ni realizado impresión física. La prueba nativa
de receptores no equivale a ejecutar el lector o CUPS real. El diálogo nativo de guardado y
su sustitución sobre un archivo de usuario se deben comprobar en la cuenta Windows sintética
de aceptación. El lector de PDF es una comprobación de las facturas generadas por el servicio,
no un saneador general de documentos PDF arbitrarios.

Fuentes oficiales: [ShellExecuteW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutew),
[xdg-open](https://portland.freedesktop.org/doc/xdg-open.html), [CUPS lpr](https://www.cups.org/doc/man-lpr.html),
[LoadOptions de lopdf](https://docs.rs/lopdf/latest/lopdf/struct.LoadOptions.html) y
[aviso RustSec corregido antes de 0.45.0](https://rustsec.org/advisories/RUSTSEC-2026-0187).
