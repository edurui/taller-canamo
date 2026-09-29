# Escritorio integrado: verificación final — 23/09/2026

Versión 0.9.1 de desarrollo, Ubuntu x64, Python 3.13.2, Rust 1.98.1, Tauri 2.11.6,
WebKitGTK/WebKitWebDriver 2.52.6 y tauri-driver 2.0.6. No hay Windows ni impresora física.
Este informe reemplaza como estado actual los hitos de `escritorio-2026-09-23.md` y
`pdf-escritorio-2026-09-23.md`, que se conservan como evidencia histórica.

## Comandos y resultados

| Comprobación | Resultado | Evidencia |
|---|---|---|
| `.venv/bin/python scripts/build_desktop.py --sidecar-only`, con Rust en PATH | Código 0; PyInstaller completo y verificador funcional real | `sidecar-build-final-2026-09-23.txt`, `sidecar-artifact.json`, `sidecar-functional.json` |
| `cargo test --locked --no-default-features --lib` | 18 correctas, 2,00 s | `rust-final-2026-09-23.txt` |
| `cargo build --locked` con SDK GTK/WebKit privado | Código 0, 6,34 s, binario Tauri Linux enlazado con interfaz final | `tauri-final-build-2026-09-23.txt` |
| `taller-canamo --diagnose-sidecar RUTA-INFORME` | Código 0; PDF, copia por bloques, cierre/reapertura | `linux-final-packaged-sidecar.json` |
| Smoke Tauri/WebKit con PDF y selector GTK real | Código 0, 8 comprobaciones correctas | `desktop-final/result.json`, `desktop-final-recheck-2026-09-23.txt` |
| Comprobación de tipos Win32/COM/notificaciones del código Rust | Código 0; no enlaza/ejecuta Windows | `rust-pdf-windows-typecheck-2026-09-23.txt` |
| Orquestación del constructor Windows con comandos simulados | 2 regresiones correctas, incluidas en las 438 finales; no acredita build Windows | `tests/test_build_desktop.py` |

Comando nativo final ejecutado desde la raíz:

```bash
.venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --driver /home/eruizgarcia/.cargo/bin/tauri-driver \
  --native-driver /tmp/canamo-linux-sdk/usr/bin/WebKitWebDriver \
  --xvfb /tmp/canamo-linux-sdk/usr/bin/Xvfb \
  --test-document-handlers --test-save-dialog --output reports/desktop-final
```

El selector se ejercita con xdotool, portal GTK real, Xvfb/bus D-Bus y directorios de usuario
privados de esta prueba. No usa datos ni servicios de sesión de un taller. Los drivers y
receptores son herramientas de ensayo; no se incluyen en el instalador.

## Qué ha funcionado realmente

El servicio empaquetado incorpora SaxonC/EN16931, Vosk/RapidOCR/ONNX, Jackcess/JRE, esquemas,
modelos, fuentes PDF y licencias. El verificador ejecuta esos motores, no solo comprueba
que sus módulos se importan. Lee un ACCDB real sintético, genera PDF con TTF embebida,
valida B2B, reconoce voz/imagen, descarga copia cifrada y portable por bloques, verifica
sus hashes y reabre la misma factura. La CLI de liberación rechaza evidencias inexistentes
sin escribir SQLite ni activar producción. Arranque **3,7801 s**, reapertura **3,7687 s**
en este equipo; no se extrapolan a extracción/antivirus en Windows.

La ventana Tauri final crea demo mediante IPC real, busca matrícula y teléfono, abre ficha
con Enter, genera PDF y ejecuta los botones Abrir/Imprimir. Solo los programas receptores
`xdg-open`/`lpr` se sustituyen: prueban rutas/bytes/errores, sin abrir lector externo ni
imprimir papel. PDF falso, verbo arbitrario y URL ajena se rechazan antes de invocar programa.

El botón Crear y guardar copia abrió el **selector GTK real**. Se comprobó Cancelar, que
conserva la copia local, y después sustituir un destino temporal existente. El archivo previo
seguía intacto antes de confirmar. Se guardaron **3.762.699 bytes cifrados**, varios bloques;
SHA-256 `dc56fc36dee8dfe1d8de498f220606af4d196dcff6887b8ace2382b5cf5e79b5`, idéntico a la
copia retenida por el servicio. La segunda instancia terminó conservando la sesión original.

El primer intento nativo falló porque Ctrl+L seleccionaba el nombre sin su extensión y el
harness escribió `.canamo.canamo`; estaba leyendo luego el destino anterior. La captura
`desktop-final-initial-selector/native-save-dialog.png` lo demuestra. Se corrigió el
harness con selección completa Ctrl+A, conservando la aserción de cabecera cifrada y todas
las comprobaciones de tamaño/hash. No se cambió el producto ni se debilitó el test. Se
conservan resultado, captura y log de ambos intentos.

Se corrigió también el constructor Windows: su variable de informe reutilizaba el nombre
del diagnóstico y sobrescribía `windows-staged-sidecar.json`, sin crear el inventario final.
Ahora las rutas son distintas; las regresiones de orquestación lo verifican y comprueban
que cambios de fuentes invalidan una aceptación anterior. La preparación de licencias crea
`reports/` en un checkout limpio. Estas correcciones no equivalen a un instalador ejecutado.

## Artefactos actuales

| Archivo | Bytes | SHA-256 |
|---|---:|---|
| `src-tauri/target/debug/taller-canamo` | 306.457.272 | `0f46f81b6889f3f380254e82eddd92c82aff9a30d6fb2ce99eefc2c53cb5dc27` |
| `src-tauri/binaries/canamo-service-x86_64-unknown-linux-gnu` | 335.881.824 | `530b9f46c6931fd6da14e9c2c944e75761aebc0f048a94dd05c9112e071e21c0` |
| `src-tauri/target/debug/canamo-service` | 335.881.824 | misma huella que el servicio anterior |

Son ejecutables **Linux de desarrollo**, no un instalador Windows. El servicio tiene
política `development`; ni él ni esta evidencia autorizan producción. El hito anterior se
conserva con nombres `sidecar-hito1-*`, sin atribuirle las correcciones finales.

## Límites restantes

No se han ejecutado NSIS/WebView2/DPAPI/Job Object/notificaciones/impresión física en Windows.
El workflow y la guía `docs/BUILD-WINDOWS.md` están preparados; no se ha publicado ningún
remoto ni ejecutado un runner externo. WebView2 puede necesitar Internet al instalarse.

Cargo Audit mantiene seis avisos de falta de mantenimiento y uno de GLib 0.18.5
(RUSTSEC-2024-0429). GLib pertenece a GTK de Linux y no aparece en el árbol Windows MSVC;
se conservan ambos árboles. No se ignoran avisos ni se declara el Linux libre de esa
limitación. Detalles y fuentes primarias en `seguridad-dependencias-2026-09-23.md`.
