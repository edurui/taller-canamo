# Revisión de entrega Windows · 04/11/2026

## Decisión de esta revisión y alcance

No entregar todavía el instalador del 27/10 como aplicación operativa. Se han
consultado las fuentes, cambios locales, registros originales de GitHub y bytes
conservados; las afirmaciones antiguas no sustituyen esta revisión. No se han
abierto ni modificado bases reales, certificados o copias del taller.

**Revisión local cerrada con correcciones y pruebas correctas. Entrega operativa
pendiente de un instalador nuevo comprobado en Windows y de la puesta en marcha
real.** No se ha generado un EXE Windows nuevo en esta sesión ni publicado código.

Entorno: Ubuntu Linux x86_64, Node 22.22.2, npm 10.9.7, Python 3.13.2 del entorno `.venv`. Los resultados
automáticos se conservan en `reports/revision-entrega-2026-11-04/` (fuera de Git).

## Hallazgos comprobados

- El run [40579253295](https://github.com/edurui/taller-canamo/actions/runs/40579253295)
  de `10bb9372544dfb581e77e9b652c85becc116a559` falló al crear la sesión WebDriver.
  Los pasos de construcción e instalación pasaron. La lectura actual de GitHub
  confirma la evidencia anterior; no acredita una ventana nativa funcional.
- SHA-256 del instalador local, recalculado:
  `fe4924812fe0f4b72890b642398b1238ae0ddc052c7b26074c04c827e32863f9`,
  284.628.510 bytes. Coincide con el manifiesto. Política `release_candidate`.
- La auditoría inicial `npm audit --json` detectó alertas en Vite 7.3.6 y source-map-js 1.2.1.
  Son herramientas de desarrollo/construcción, no un servidor Vite publicado
  por la aplicación instalada. Quedan corregidas para la nueva construcción.
- La auditoría inicial `uvx pip-audit --no-deps --disable-pip -r requirements-dev.lock` detectó avisos
  en Pillow 12.3.0, certifi 2026.7.22, pypdf 6.19.0 y setuptools 84.0.0.
  El contador bruto incluye entradas duplicadas; no equivale a fallos explotados
  en el taller. Pillow y certifi forman parte de las dependencias empaquetadas.
- RustSec: cero resultados en la categoría `vulnerabilities`, nueve avisos
  `unmaintained` y dos `unsound`. Estos últimos son `glib::VariantStrIter`
  (RUSTSEC-2024-0429) y `tokio::io::unix::AsyncFd` (RUSTSEC-2026-0386).
  El árbol de dependencias Windows no incluye glib; la API señalada de Tokio
  está condicionada a Unix en la fuente instalada. No se utilizan esas API
  directamente en el puente del proyecto. Se conservan los avisos; no se
  presenta el lock multiplataforma como exento de todos ellos ni se fuerza una
  actualización mayor de GTK para una entrega exclusivamente Windows.
- El manifiesto de construcción no incluía `web/style.css`. Un control sintético
  cambió el CSS y comprobó que `build_input_hashes()` no detectaba la diferencia.
  El verificador de reutilización heredado tampoco exigía esa entrada.
- El workflow completo comprobaba la ventana del ejecutable de compilación tras
  desinstalar el instalado. Debe comprobar el ejecutable instalado y conservar
  sus hashes, con limpieza limitada a la instalación temporal de la prueba.
- Revisión visual de las nueve páginas de tres PDF sintéticos: se encontraron
  cabeceras de tabla repetidas dentro de las páginas 1 y 2 y una variación lateral
  de alineación al partir un concepto. El test nuevo reprodujo el fallo antes de
  la corrección (`pdf-negative-control.log`). `InvoiceLinesTable` fuerza que cada
  continuación empiece en otra página y conserva la alineación, incluso al partir
  un concepto mayor que una página. Pasan 14 pruebas dirigidas de PDF; comprueban
  texto íntegro, precios exactos, una sola cabecera por página, totales y snapshots
  emitidos conservados. No se regeneraron documentos del taller.

## Correcciones y comprobaciones de esta revisión

Actualizaciones limitadas y resueltas con hashes: Vite 7.3.7, source-map-js 1.2.2,
Pillow 13.0.0, certifi 2026.10.18, pypdf 6.21.4 y setuptools 84.1.0. Los demás
paquetes conservan sus versiones. Se instalaron mediante `npm ci` y
`python -m pip install --require-hashes -r requirements-dev.lock`. Las cuatro
ruedas Python nuevas para Windows/Python 3.13 se descargaron y sus hashes coinciden
con el lock; eso no se presenta como ejecución en Windows.

La batería base ejecutó 827 pytest (125,357 s), ambos typechecks, build y 166 E2E
(484,235 s), sin fallos, omisiones o reintentos ni cambios de fuentes. Contiene
las ocho pruebas de reutilización que ya estaban sin versionar al empezar.
La revisión de React contrastó las guardas de respuestas obsoletas de búsqueda,
el bloqueo del guardado y las E2E del flujo directo con/sin vehículo y extras.
No se hizo una refactorización de interfaz sin un defecto demostrado.

Antes de la batería integrada final pasaron 25 controles de construcción/evidencia,
14 pruebas de PDF y 18 Rust (`cargo test --locked --no-default-features --lib`).
El parser de evidencias también validó los informes reales de la batería base,
y el rechazo de evidencia inválida permanece activo con `python -O`.
La sintaxis YAML de ambos workflows se comprobó localmente; no equivale a su
ejecución ni a validar PowerShell/NSIS en Windows.

El primer empaquetado Linux terminó sus nueve comprobaciones funcionales, pero
el constructor lo rechazó al detectar la corrección de `backend/taller/pdf.py`
durante la ejecución. Se conserva el fallo en `sidecar-build.log` y se repite
desde las fuentes finales; ese primer binario no se acepta como resultado final.

La segunda construcción (`sidecar-build-final.log`) terminó con código 0 y entradas
estables. Sus nueve comprobaciones funcionales reales pasaron: PDF/cadena local,
SaxonC/EN16931, OCR/voz, ACCDB/Jackcess/JRE, licencias, copia cifrada por bloques,
ZIP portable, cierre/reapertura y rechazo de expediente fiscal inválido. Arranque
16,7554 s y reapertura 16,4039 s en esta máquina; no son tiempos del PC del taller.
Servicio **Linux**, 336.112.808 bytes, SHA-256
`9318c2f6309dc8fbc34d3df87208f3618a5f7bf034b40e948aa59dc42e140288`.
El manifiesto v2 contiene 1.803 entradas. No se trata de un EXE Windows.

El primer intento integrado posterior a los cambios (`final/`) ejecutó correctamente
841 pytest y 166 E2E, ambos typechecks, build y pip check. Se rechazó como evidencia
de revisión única: `prepare_licenses.py`, del empaquetado concurrente, cambió
`backend/taller/legal/manifest.json`. El rechazo se conserva; no se desactiva la
guarda ni se cuenta ese intento como una batería integrada aprobada.

La repetición definitiva (`final-stable/result.json`) pasó de 08:41:01 a 08:49:43
del 04/11/2026 (Europe/Madrid): **841 pytest, 166 E2E**, pip check, ambos typechecks
y build, todos con código 0. Cero errores, fallos, omitidas, flaky o reintentos.
Los 287 archivos de la huella de verificación permanecieron estables. Pytest tardó
111,366 s (112,095 s de comando) y Playwright 391,125 s (394,325 s de comando).
El recorrido incluye los controles de accesibilidad Axe de las pantallas probadas;
no se presenta como certificación completa de accesibilidad. También se contrastaron
de nuevo las 1.803 entradas del servicio empaquetado: ninguna cambió.

Se renderizaron con Poppler y revisaron visualmente las nueve páginas nuevas
de factura corta, factura larga y rectificativa (`pdf-final/`). Mantienen textos
seleccionables, avisos de prueba, márgenes, numeración, cantidades y totales;
una sola cabecera de tabla por página. Falta la impresora física.

## Comandos y evidencias reproducibles

Ejecutados desde la raíz del proyecto. Los informes JSON/XML y logs completos se
conservan en `reports/revision-entrega-2026-11-04/`; los datos de los casos son sintéticos.

| Comprobación | Comando | Evidencia |
|---|---|---|
| Integración base | `.venv/bin/python scripts/verify.py --report reports/revision-entrega-2026-11-04/baseline` | `baseline/result.json`, `pytest.xml`, `e2e-results.json` y logs |
| Integración final estable | `.venv/bin/python scripts/verify.py --report reports/revision-entrega-2026-11-04/final-stable` | `final-stable/result.json`, XML, JSON de navegador y logs |
| Inventario y reutilización | `.venv/bin/python -m pytest tests/test_build_desktop.py tests/test_verify_windows_artifact.py` | `build-guards.log`, `build-guards.xml`: 25 casos correctos |
| PDF | `.venv/bin/python -m pytest tests/test_pdf_layout.py tests/test_workflows.py::test_pdf_is_generated_from_demo` | `pdf-fixed.log`, `pdf-fixed.xml`: 14 casos correctos; control negativo anterior guardado |
| Puente Rust | `PATH="$HOME/.cargo/bin:$PATH" CANAMO_TEST_PYTHON="$PWD/.venv/bin/python" cargo test --manifest-path src-tauri/Cargo.toml --locked --no-default-features --lib` | `rust-tests.log`: 18 casos correctos |
| Servicio congelado | `PATH="$HOME/.cargo/bin:$PATH" .venv/bin/python scripts/build_desktop.py --sidecar-only` | `sidecar-build-final.log`, `sidecar-artifact.json`, `sidecar-functional.json`: código 0 |
| Seguridad npm | `npm audit --json` | `npm-audit-final.json`: cero avisos |
| Seguridad Python | `uvx pip-audit --no-deps --disable-pip -r requirements-dev.lock -f json` | `python-audit-final.json`: 41 dependencias, cero avisos |
| Seguridad Rust | `RUST_LOG=error build/audit-tools/bin/cargo-audit audit --file src-tauri/Cargo.lock --json` | `cargo-audit-final.json`: clasificación y alcance descritos arriba |

Las nueve páginas de `pdf-final/` fueron renderizadas con Poppler e inspeccionadas;
los archivos HTML/Chromium de las E2E no se presentan como prueba de WebView2.
Las auditorías corresponden a las bases de avisos consultadas el 04/11/2026, no a
una garantía de ausencia de cualquier vulnerabilidad futura o desconocida.

## Paquete local de fuentes revisadas

`build/entrega/taller-canamo-0.9.1-fuentes-revision-2026-11-04.zip`: 340 archivos,
2.447.794 bytes; CRC y SHA-256 de cada entrada verificados por
`.venv/bin/python scripts/package_source.py --output build/entrega/taller-canamo-0.9.1-fuentes-revision-2026-11-04.zip`.
SHA-256 del ZIP: `c72d57b30c5b365cf74cbdfe988ab3c4448c17811a4d5a6b4d307701f0522452`.
Incluye fuentes, locks, pruebas y documentación; excluye datos privados, certificados,
informes y motores generados. El presente informe se conserva por separado. Es un
paquete para reconstrucción y revisión técnica, **no un instalador para el taller**.

Tras cerrar la documentación y empaquetar, `final-stable/final-evidence-check.json`
confirma que los archivos verificados no cambiaron y que los parsers de aceptación
reconocen los 841 casos Python y 166 casos de navegador completos. `git diff --check`
también terminó correctamente. Los cambios locales anteriores se conservaron y
revisaron; no se hizo reset, commit ni push.

## Trabajo y criterio de cierre

- [x] Terminar batería base sin cambios de fuentes durante la ejecución.
- [x] Resolver y fijar solamente las dependencias con corrección de seguridad.
- [x] Corregir cobertura del manifiesto y comprobar su rechazo ante cambios.
- [x] Corregir comprobación del ejecutable instalado y revisar herramientas previas.
- [x] Repetir Python, ambos typechecks, build, E2E/Axe y auditorías tras los cambios.
- [x] Verificar el servicio empaquetado Linux con las nuevas dependencias.
- [x] Actualizar estado, aceptación y relevo con resultados y límites.
- [ ] Construir y comprobar el candidato nuevo en Windows real.

## Límites externos

Esta máquina es Linux, sin sesión Windows conectada. No se acredita Windows con
Wine, typecheck MSVC ni E2E en Chromium. Publicar las correcciones en el repositorio
existente para ejecutar GitHub Actions requiere respetar `CODEX_PROMPT.md`:
«No publiques ni fuerces pushes». No se ha realizado push, despliegue ni envío de
datos privados. El cambio de dependencias requiere un nuevo instalador; el workflow
de reutilización no debe aceptar el viejo como si incorporase las correcciones.

Siguiente acción concreta, cuando se autorice la publicación: crear una rama de
revisión en el repositorio existente `edurui/taller-canamo`, publicar únicamente
fuentes/documentación revisadas y ejecutar `windows-build.yml` con
`release_candidate=true`. Exigir éxito del build, hashes, instalación, servicio
y recorrido nativo; revisar `reports/desktop/result.json` y la captura de la ventana.
Descargar el NSIS y sus informes, verificar SHA-256 y sustituir el instalador de
ensayo solo después de aceptar esa evidencia. No publicar una release ni activar
producción como parte de ese paso. El workflow no incluye bases ni certificados.

Siguen siendo necesarios el ensayo en el PC Windows del taller (incluida impresión
física), el certificado autorizado y expediente de esta versión, la confirmación
de identidad/serie y un corte acordado desde Access. No se cambia ningún flag para
simularlos. La AEAT explica que la declaración responsable corresponde al productor
y que no hay homologación externa previa que sustituya esa responsabilidad:
[FAQ oficial](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/certificacion-sistemas-informaticos-declaracion-responsable.html), consultada el 04/11/2026.

Referencias técnicas consultadas: [WebDriver y WebView2](https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/webdriver),
[Vite 7.3.7](https://github.com/vitejs/vite/releases/tag/v7.3.7),
[Pillow 13](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html),
[pypdf 6.21.4](https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html),
[certifi 2026.10.18](https://github.com/certifi/python-certifi/releases/tag/2026.10.18).
