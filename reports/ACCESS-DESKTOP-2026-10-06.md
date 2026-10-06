# Escritorio Linux tras la revisión Access · 06/10/2026

**Artefacto Linux de desarrollo reconstruido y probado con las fuentes finales.**
El servicio empaquetado, el diagnóstico del ejecutable y las ocho comprobaciones de
escritorio real finalizaron correctamente. Las pruebas usan exclusivamente talleres
y archivos sintéticos. No se han utilizado
los MDB reales en la ventana ni se han enviado documentos a AEAT o clientes.

## Entorno y preparación

Ubuntu 24.04 x86_64, Python 3.13.2, Rust 1.98.1, PyInstaller 6.22.3,
tauri-driver 2.0.6, GTK 3.24.41 y WebKitGTK/WebKitWebDriver 2.52.6.
Las versiones e inventarios exactos están en `reports/access-real-verification/`.

El SDK temporal anterior ya no existía. Se descargaron 90 paquetes de los repositorios
oficiales Ubuntu mediante `apt-get download`, y se extrajeron con `dpkg-deb` bajo
`/tmp/canamo-access-linux-sdk/root`, sin sudo ni instalación/configuración global.
Las rutas de los archivos pkg-config y los enlaces privados a bibliotecas ya instaladas
se ajustaron únicamente dentro del SDK. Inventario con versión, tamaño y SHA-256 de
cada paquete: `sdk-packages.json`.

## Resultados verificados

| Comando | Resultado | Evidencia |
|---|---|---|
| `cargo +1.98.1 test --locked --no-default-features --lib` | 18 correctos, 0 omitidos; 2,02 s | `cargo-test.log` |
| `cargo +1.98.1 check --locked` | Código 0; 44,58 s tras regenerar caché Tauri | `cargo-check-after-clean.log` |
| Primer `build_desktop.py --sidecar-only` | Motores/copia/ACCDB correctos; **artefacto rechazado por cambio de fuentes** | `sidecar-build.log`, `sidecar-preliminary-functional.json` |
| Segundo `build_desktop.py --sidecar-only` | Código 0; 9 grupos funcionales correctos, fuentes estables | `sidecar-build-final.log`, `final-sidecar-artifact.json`, `final-sidecar-functional.json` |
| `cargo +1.98.1 build --locked`, SDK corregido | Código 0; 2 min 13 s | `cargo-build-sdk-corrected.log` |
| Build incremental con sidecar final | Código 0; 4,45 s; servicio instalado junto al ejecutable con SHA idéntico | `cargo-build-final.log` |
| `taller-canamo --diagnose-sidecar` | Código 0, `ok: true`; PDF, copia por bloques y reapertura | `packaged-sidecar.json` |
| `desktop_smoke.py`, ventana real y selector GTK | Código 0; **8 comprobaciones correctas** | `desktop/result.json`, `desktop-smoke.log` |

Se conservan los intentos intermedios y sus causas:

- El primer `cargo check` encontró permisos Tauri generados con una ruta antigua del
  repositorio inexistente. Se limpiaron los artefactos Cargo de Tauri, sus plugins y la
  aplicación; el segundo check pasó sin cambiar fuentes.
- El primer enlace Tauri no encontró bibliotecas porque el SDK privado tenía `libdir`
  absoluto y enlaces relativos a runtimes ya instalados en el host. Se corrigieron los
  archivos/enlaces del SDK privado y se repitió la compilación.
- Un build web intermedio detectó que los contadores de conciliación podían ser nulos
  según el contrato TypeScript. El contrato se corrigió manteniendo nulos sólo los
  importes desconocidos; el build web definitivo lo ejecutó el agente principal.
- Mientras terminaba el primer empaquetado se corrigieron casos límite del importador.
  El constructor detectó que sus huellas de entrada habían cambiado y rechazó el
  artefacto pese a que el verificador funcional había pasado. Se inició una nueva
  construcción con las fuentes congeladas. Ese primer ejecutable no se acepta como
  entrega final.

## Comandos reproducibles

La variable `sdk` se refiere sólo al SDK privado de esta prueba:

```bash
sdk=/tmp/canamo-access-linux-sdk/root
PATH="$HOME/.cargo/bin:$PATH" .venv/bin/python scripts/build_desktop.py --sidecar-only
PATH="$HOME/.cargo/bin:$PATH" \
  PKG_CONFIG_PATH="$sdk/usr/lib/x86_64-linux-gnu/pkgconfig/:$sdk/usr/share/pkgconfig/" \
  LIBRARY_PATH="$sdk/usr/lib/x86_64-linux-gnu" \
  cargo +1.98.1 build --locked --manifest-path src-tauri/Cargo.toml
```

## Servicio y escritorio realmente ejecutados

El verificador del servicio empaquetado ejercitó SaxonC/XSD/EN16931, Vosk en castellano,
RapidOCR/ONNX, lectura ACCDB sintética con JRE/Jackcess y rechazo de vínculo externo,
PDF con TrueType, avisos de licencias, copia cifrada y exportación portable por bloques,
cierre/reapertura y rechazo de un expediente fiscal ausente. Su arranque medido fue
14,6181 s y su reapertura 10,7933 s en esta ejecución con otras verificaciones concurrentes.
No son medidas de Windows ni equivalen a latencia del buscador.

El diagnóstico invocado a través del ejecutable Tauri utilizó el servicio **situado junto
a ese ejecutable**, generó un PDF sintético de una página y 49.276 bytes, verificó copia
por bloques, acuse de cierre y reapertura del historial. No usó el Python de desarrollo
como sustituto del servicio empaquetado.

El smoke nativo verificó ventana/API Tauri, carga de demo por IPC, búsqueda de matrícula
normalizada y teléfono con Enter, PDF del servicio, botones Abrir/Imprimir y error visible,
rechazo de PDF/verbo/URL no permitidos, selector GTK de copia e instancia única.
Los receptores `xdg-open`/`lpr` eran programas de ensayo locales: **no hubo impresión física**.

El selector GTK real conservó el destino anterior hasta la confirmación, verificó que
Cancelar conserva la copia local y guardó una copia cifrada de **3.763.730 bytes**. Su
SHA-256 `957fd80e21bee4b71a0defa57755eb514f82af1eb2da7681b809517e7ce59ab4`
coincide con la copia retenida por el servicio. La ventana final fue capturada e
inspeccionada con datos sintéticos. Los avisos del portal sobre asociación de la ventana
y el cierre de Xvfb/D-Bus quedan en el log; no impidieron las aserciones de guardado.

Comando del smoke final, tras el build anterior:

```bash
env -u GIO_MODULE_DIR -u GTK_EXE_PREFIX -u GTK_IM_MODULE_FILE \
  -u GTK_PATH -u GTK_MODULES -u GSETTINGS_SCHEMA_DIR \
  LD_LIBRARY_PATH="$sdk/usr/lib/x86_64-linux-gnu" \
  PATH="$HOME/.cargo/bin:$sdk/usr/bin:/usr/bin:$PATH" \
  .venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --driver "$HOME/.cargo/bin/tauri-driver" \
  --native-driver "$sdk/usr/bin/WebKitWebDriver" --xvfb "$sdk/usr/bin/Xvfb" \
  --test-document-handlers --test-save-dialog \
  --output reports/access-real-verification/desktop
```

## Artefactos finales

| Ruta | Bytes | SHA-256 |
|---|---:|---|
| `src-tauri/target/debug/taller-canamo` | 306.468.496 | `d4af7eb5c609ae3711e0c7c6ca12453567fe0a9e52ffd60b67dc227b89de1dbb` |
| `src-tauri/binaries/canamo-service-x86_64-unknown-linux-gnu` | 335.903.736 | `01cdbc27e4ef596d1f9a4e4deeaeb6e520e486b37b2c02f474139bff63f33502` |
| `src-tauri/target/debug/canamo-service` | 335.903.736 | Misma huella que el servicio anterior |

Tras el smoke se volvieron a comprobar las huellas del servicio contra su manifiesto,
las fuentes de entrada contra el inventario del constructor, los assets web contra la
captura previa al último build y ambos ejecutables contra las huellas registradas al
iniciar la prueba nativa. Todo coincide. Resumen mecánico:
`reports/access-real-verification/desktop-verification-summary.json`.

El servicio incorpora política `development`. Las pruebas locales de esquemas y motores
no autorizan facturación operativa, no son un ensayo autenticado de AEAT y no acreditan
instalador Windows, WebView2, DPAPI, notificaciones de Windows ni impresión física.
