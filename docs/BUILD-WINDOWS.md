# Construir, instalar y comprobar Windows

Estado a 2026-09-23: Tauri compila y se ha ejecutado con su servicio PyInstaller en Linux.
El código Win32 de procesos, notificaciones y ShellExecute pasa comprobación de tipos para MSVC.
**No se ha ejecutado todavía un build, instalador, WebView2 o notificación en Windows.**
Evidencia y límites: `reports/escritorio-final-2026-09-23.md`.

## Construcción en un Windows 11 x64 de desarrollo

Instalar Python 3.13, Node 22.22.2, un JDK Temurin 17 o posterior, Rust mediante rustup y Microsoft C++ Build Tools con
«Desarrollo de escritorio con C++». Rust 1.98.1 está fijado en `src-tauri/rust-toolchain.toml`.
Las dependencias se fijan en `requirements-dev.lock`, `package-lock.json` y `src-tauri/Cargo.lock`.
El equipo donde se instala la aplicación terminada no necesita estas herramientas.

Por defecto se incorpora `release-policy.json` con edición `development`. Para preparar
explícitamente un **candidato Windows**, ejecutar el mismo build completo añadiendo
`--release-candidate`. El script incorpora una política temporal `release_candidate` antes
de construir y probar el sidecar, sin cambiar el archivo fuente. Se rechaza esa opción en
Linux y junto a `--sidecar-only`.

La condición de candidato no habilita emisión real: siguen siendo obligatorios la identidad
del productor, certificado, cadena, ensayos autorizados y expediente verificable. Primero se
construye el candidato; luego se ensayan y documentan **esos mismos bytes**. El expediente
debe identificar su SHA-256. No se recompila después de generar el expediente: cualquier
reconstrucción o cambio del ejecutable requiere repetir la comprobación del artefacto. Esta
sesión no construye un candidato Windows ni genera evidencias positivas ficticias.

Después de los ensayos reales, el mantenedor puede comprobar e instalar el expediente ya
existente con el servicio de **ese mismo candidato**:

```powershell
.\canamo-service.exe --data 'C:\ruta\datos-del-usuario' --verify-release-evidence
.\canamo-service.exe --data 'C:\ruta\datos-del-usuario' --install-release-evidence 'C:\ruta\expediente'
```

La primera orden es de solo lectura; la segunda valida y copia únicamente las evidencias
referenciadas, conserva el expediente previo y no activa producción. Ambas rechazan pruebas
ausentes o incompatibles. Requisitos y secuencia completa: `docs/FISCAL-LIBERACION-2026-09-23.md`.

Desde PowerShell, en la raíz del proyecto:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
npm ci
npx playwright install chromium
.\.venv\Scripts\python.exe scripts\build_desktop.py
```

El script prepara el lector Access y su JRE con URLs/hashes fijados, los modelos locales y
el inventario de licencias. Después ejecuta pytest, typecheck de aplicación y E2E, build web,
E2E de navegador, PyInstaller, pruebas Rust y `tauri build -- --locked`. El build web precede
a las pruebas de navegador incluso en un checkout sin `dist`. `scripts/verify_sidecar.py`
ejecuta en el servicio empaquetado lectura ACCDB, OCR/voz, validación SaxonC/EN16931, licencias,
PDF, copia cifrada por fragmentos y reapertura; registra tiempos de arranque y de cada acción.
Tras empaquetar, el ejecutable Tauri repite el diagnóstico de PDF/copia/cierre en una base
temporal. Cualquier error interrumpe la construcción. Conserva toda la salida del comando.
El instalador incluye Jackcess/JRE, los modelos pequeños y las bibliotecas nativas SaxonC,
Vosk y ONNX Runtime. El cliente final no instala Java ni descarga modelos para las funciones incluidas.
También incorpora las fuentes DejaVu 2.37 con sus licencias; el verificador exige fuente
TrueType incrustada en el PDF y comprueba que la CLI rechaza un expediente inexistente.

Resultados esperados, aún pendientes de generarse en Windows:

- `src-tauri/target/release/bundle/nsis/*-setup.exe`: instalador NSIS por usuario, en castellano.
- `src-tauri/target/release/taller-canamo.exe` y `canamo-service.exe`: aplicación y servicio junto a ella.
- `reports/windows-staged-sidecar.json`: diagnóstico del conjunto generado.
- `reports/windows-artifacts.json`: tamaño, target, versión de Python y SHA-256 de cada artefacto.
- `reports/sidecar-functional.json`: motores realmente ejecutados y tiempos del servicio empaquetado.

`externalBin` recibe `src-tauri/binaries/canamo-service-x86_64-pc-windows-msvc.exe`.
Tauri quita el sufijo del target al copiarlo junto al ejecutable principal. El puente busca solo
ese archivo junto al ejecutable: no usa PATH, directorio de trabajo ni un Python del cliente.
La prueba del instalador comprueba expresamente esta ubicación después de instalar.

El instalador obtiene WebView2 mediante el bootstrapper oficial si hace falta. **Puede necesitar
Internet durante la instalación.** Después, el trabajo local funciona sin red. No se ha firmado
el instalador: la firma requiere un certificado legítimo y una revisión de distribución; no se
indica desactivar SmartScreen ni antivirus.

## Verificar el instalador en un entorno Windows limpio

Usar una cuenta o VM desechable; nunca el PC operativo ni los datos de Access del taller.
Tras copiar la carpeta del proyecto y el instalador:

```powershell
.\src-tauri\tests\verify-installed.ps1 -Installer 'C:\ruta\Talleres-setup.exe'
```

Esta prueba instala con NSIS en una ruta temporal con espacios y tildes, comprueba ambos EXE,
ejecuta el diagnóstico con base sintética temporal, verifica cierre sin servicio residual y
desinstala. Rechaza ejecutar si ya encuentra otra instalación de desarrollo. Requiere PowerShell,
pero no Python, Node ni Rust en el equipo de prueba. Guarda `reports/windows-installed-sidecar.json`.
Este diagnóstico no abre la interfaz; la siguiente prueba verifica el WebView real.

En una cuenta **desechable de desarrollo/pruebas**, instalar herramientas de automatización:

```powershell
cargo +1.98.1 install tauri-driver --version 2.0.6 --locked
cargo +1.98.1 install --git https://github.com/chippers/msedgedriver-tool --rev 8c4b34f51b45f5cf08013366d703de464ab871d1 --locked
msedgedriver-tool
.\.venv\Scripts\python.exe src-tauri\tests\desktop_smoke.py --application src-tauri\target\release\taller-canamo.exe --native-driver .\msedgedriver.exe --isolated-windows-account
```

El descargador recomendado por Tauri selecciona Edge Driver correspondiente al WebView2
instalado y descarga de Microsoft. Los drivers son exclusivos de pruebas y no se empaquetan.
El smoke crea una demo desde los botones de Tauri, busca matrícula, comprueba el teléfono,
abre la ficha con Enter, pide un PDF al servicio y comprueba la segunda instancia.
Guarda `reports/desktop/result.json`, log y captura. En Windows utiliza la carpeta del usuario de
pruebas: de ahí la exigencia de una cuenta desechable y la opción explícita.

Comprobaciones físicas/manuales restantes, que no sustituye el smoke:

1. Instalar sin Node/Python/Rust, abrir desde el menú Inicio, cerrar a bandeja, volver a abrir.
2. Crear/guardar un borrador. Editarlo, cerrar ventana, reabrir: conserva el editor. Intentar
   «Salir y guardar copia» con cambios: muestra la ventana y pide guardar/descartar; no sale.
3. Salir sin cambios. La copia debe terminar y ambos procesos desaparecer. Probar carpeta de
   copias no disponible: debe mostrar el error y permitir resolverlo.
4. Crear aviso, activar notificaciones, probar aviso y sonido, ocultar ventana, esperar, posponer,
   reiniciar aplicación. Desactivar notificaciones en Windows: quedan pendientes dentro de la app.
5. Activar inicio al iniciar sesión, reiniciar Windows y comprobar icono de bandeja; desactivarlo
   y comprobar que se respeta. Sin proceso o con el PC apagado no hay avisos inmediatos.
6. Forzar cierre del proceso principal durante una operación con **datos sintéticos**. El Job
   Object debe eliminar también los hijos PyInstaller. Al abrir, revisar historial antes de repetir.
7. Actualizar/reinstalar desde el mismo identificador, revisar base, snapshots, numeración, PDFs
   y copias; guardar exportación sobre un archivo existente y comprobar cancelación/error de disco.
8. Vista previa → «Abrir en lector» → «Imprimir», con PDF sintético y una impresora de pruebas
   seleccionada por el encargado. Probar también ausencia de aplicación PDF/impresora y cancelación.
   Windows puede carecer de un verbo `print` en su lector: el error ofrece abrirlo e imprimir desde allí.
   La respuesta de la aplicación confirma la solicitud aceptada, no una hoja impresa.
9. WebView2/PDF/impresora real, escalas 100/125/150 %, permisos de usuario normal y notificaciones
   con concentración activada. Registrar versión de Windows y resultados sin dar por vista una alerta
   solo porque la API la haya aceptado.

## Ciclo de vida y datos

X oculta la ventana y conserva el editor. El icono ofrece Abrir y Salir; el servicio y el sondeo de
recordatorios siguen funcionando con la ventana oculta. Los avisos atrasados se agrupan en un único
aviso por sondeo, siguen pendientes de lectura dentro de la app y se marcan entregados después de
la aceptación de la API del sistema. Windows puede ocultarlos según su configuración.

Salir solicita `app.shutdown`, espera su confirmación y la salida del servicio. Python termina el
protocolo después del acuse y no duplica la copia final. Los RPC ordinarios tienen un plazo de
180 segundos; las copias/restauraciones/traslados/exportaciones portables, importaciones con copia
y cierre tienen hasta 30 minutos. Si caduca una petición aún en cola se cancela solo esa petición;
no interrumpe la copia en curso. Si caduca una petición ya enviada se detiene el árbol auxiliar
y las operaciones pendientes no se ejecutan más tarde.
El resultado de una operación ya enviada puede ser incierto: se exige revisar el historial al
reabrir antes de repetir; el puente no reintenta escrituras automáticamente.

El identificador es `es.tallereselcanamo.desktop.dev`. Los datos usan `app_local_data_dir()`, fuera
del ejecutable (en Windows, la carpeta local del usuario). Reinstalar no autoriza borrar esa carpeta.
Cambiar el identificador requiere un plan de traslado; esta edición de desarrollo conserva las
barreras de facturación de pruebas.

## PDF, enlaces y exportaciones

«Abrir en lector» e «Imprimir» validan un PDF completo con `lopdf 0.45.0`, máximo 32 MiB y
2.000 páginas; rechazan acciones activas y adjuntos. Escriben una copia con SHA-256 y nombre
seguro en la caché del usuario. Los archivos de esa caché mayores de siete días se retiran
al preparar otro PDF. En Windows se invoca `ShellExecuteW` con los verbos fijos `open` o
`print`; Linux utiliza argumentos directos para `xdg-open`/`lpr`. Se usa la aplicación e
impresora predeterminadas del sistema; no hay un ajuste de impresora ficticio en la aplicación.

El botón de WhatsApp permite exclusivamente `https://wa.me/<teléfono>?text=<borrador>` tras
la acción del usuario. Rechaza otros hosts/esquemas/parámetros; no envía mensajes por sí mismo.
Las pruebas automáticas no abren WhatsApp.

Las copias y exportaciones grandes se guardan con un permiso temporal opaco y bloques de 1 MiB.
El diálogo elige destino antes de leer, se verifican orden/tamaño/EOF/huellas por bloque y
huella completa, y solo entonces se sustituye atómicamente el destino. Un error conserva el
archivo anterior y retira el parcial. Cancelar el diálogo revoca el permiso. La aplicación
impide salir o abrir otro guardado mientras uno está en curso.

## Verificación disponible en Linux

En un equipo Ubuntu con los prerrequisitos oficiales Tauri y el entorno Python de desarrollo:

```bash
PATH="$HOME/.cargo/bin:$PATH" .venv/bin/python scripts/build_desktop.py --sidecar-only
cd src-tauri
cargo test --locked --no-default-features --lib
cargo check --locked
cargo build --locked
cd ..
src-tauri/target/debug/taller-canamo --diagnose-sidecar "$PWD/reports/linux-packaged-sidecar.json"
cargo +1.98.1 install tauri-driver --version 2.0.6 --locked
.venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --native-driver /usr/bin/WebKitWebDriver --xvfb /usr/bin/Xvfb \
  --test-document-handlers
```

GTK/WebKit, WebKitWebDriver y Xvfb son dependencias del desarrollo Linux. En esta sesión se
extrajeron los paquetes oficiales Ubuntu en `/tmp/canamo-linux-sdk` porque sudo requiere contraseña;
no se instalaron globalmente. El informe documenta las variables de compilación utilizadas.
`--test-document-handlers` sustituye exclusivamente en la sesión privada de pruebas los
receptores `xdg-open` y `lpr`. Verifica botones/IPC/parser/caché/errores, sin abrir un lector,
un navegador ni enviar trabajos a una impresora. La captura muestra el visor PDF real del WebView.

## Workflow preparado

`.github/workflows/windows-build.yml` es manual, usa acciones fijadas por SHA y los locks,
compila, instala/diagnostica y ejecuta el smoke de escritorio con WebView2. No publica releases.
**No se ha ejecutado:** no hay un remoto/runner autorizado disponible. Publicar el proyecto o
activar un runner requiere autorización independiente. Ninguna prueba envía facturas a AEAT.

## Fuentes oficiales consultadas el 2026-09-23

- [Prerrequisitos Tauri](https://v2.tauri.app/start/prerequisites/).
- [Sidecars y convención del target](https://v2.tauri.app/develop/sidecar/).
- [Instalador Windows](https://v2.tauri.app/distribute/windows-installer/).
- [Instancia única](https://v2.tauri.app/plugin/single-instance/) y [bandeja](https://v2.tauri.app/learn/system-tray/).
- [Inicio de sesión](https://v2.tauri.app/plugin/autostart/).
- [Pruebas WebDriver](https://v2.tauri.app/develop/tests/webdriver/manual-setup/).
- [Job Objects Win32](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
- [Bloqueos de notificaciones Windows](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotifier.setting).
- [ShellExecuteW y significado de su resultado](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutew).
- [xdg-open](https://portland.freedesktop.org/doc/xdg-open.html) y [CUPS lpr](https://www.cups.org/doc/man-lpr.html).
- [lopdf, opciones de carga](https://docs.rs/lopdf/latest/lopdf/struct.LoadOptions.html) y [aviso de recursión corregido](https://rustsec.org/advisories/RUSTSEC-2026-0187).
