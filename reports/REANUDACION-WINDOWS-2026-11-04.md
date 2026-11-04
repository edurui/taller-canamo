# Reanudar Windows sin recompilar · 04/11/2026

Solicitud del usuario: evitar repetir los 33 minutos del build cuando solo falla
una comprobación posterior; corregir la causa con alcance mínimo.

## Evidencia conservada

Build original: [41802145854](https://github.com/edurui/taller-canamo/actions/runs/41802145854),
commit `0e4b4d05a5ec497d1a090fce0b7edfb4cb21c61b`, Windows 2025 x64, Python 3.13.17,
Node 22.22.2 y Rust 1.98.1. Calidad/formato, preflight, 843 pytest, 166 E2E,
16 Rust, nueve comprobaciones del servicio empaquetado y diagnóstico staged pasan.
NSIS termina correctamente; su instalación sale con código cero. Falla después
la comparación de hashes, antes de ejecutar diagnóstico instalado y WebView2.

Artefacto GitHub `13309318446`, ZIP SHA-256
`67ea76823da60670ce2443d72aedfc1c53f1c1953673271c4c6ff727fde36d78`.
Descargado fuera del repositorio, hash y CRC comprobados.

Instalador de 284.692.183 bytes, SHA-256
`674cb06eb0e1b1f4a2c48d7ac588b1e0b52834fe41f1cb7681422379d3c8f3e2`.
Se conserva sin modificación ni reconstrucción.

## Causa y corrección limitada a las pruebas

El [bundler oficial de Tauri](https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle.rs)
cambia `__TAURI_BUNDLE_TYPE_VAR_UNK` por `__TAURI_BUNDLE_TYPE_VAR_NSS` al empaquetar
NSIS y restaura el ejecutable previo. Se ha contrastado con tauri-utils 2.9.3
instalado y con el payload real, extraído sin ejecutar mediante 7zip:

- App: 10.707.456 bytes. Staged `fb2ae5496e4ecfeeca249427e399737e1af6348cd13be042cc0541099d76b874`;
  dentro de NSIS `bce1e862486733fcb59d46c6e3e0cfa30bd73cdf9d3adf1f54181daed74e7495`.
- Marcador único en offset 7.965.890. Revertir solo NSS -> UNK **en memoria**
  produce exactamente el SHA staged. No se ignoran otras regiones del EXE.
- Servicio: 285.333.598 bytes, SHA idéntico al manifiesto
  `0c995f1b40cb8f2486af112c23b5436038f5c756e5110187a083c83c31a54b44`.

`artifact-integrity.ps1` valida tamaño, entrada única y SHA. Solo para el nombre
de la app permite ese marcador único, exigiendo igualdad completa del hash
normalizado. Conserva hash real y modo de comparación en el informe; no modifica
el archivo. Instalador/servicio requieren igualdad exacta. El instalador se
comprueba antes de ejecutarlo y los bytes se vuelven a verificar tras el diagnóstico.

La guarda `verify_windows_artifact.py --through-build` exige build completo,
seis comprobaciones de calidad, baterías sin fallos/omisiones/reintentos,
diagnósticos empaquetado/staged, identidad del commit, hash del instalador y
todas las fuentes de ejecución coincidentes. Marca explícitamente instalación
y UI como pendientes. Su modo predeterminado sigue exigiendo el diagnóstico
instalado anterior. La misma guarda real ha validado localmente **206 entradas**.

El workflow registrado admite `build_run_id` y `build_source_sha`: con cualquiera
de ellos omite el job de build y llama al workflow corto del mismo commit. Se
repite instalación, diagnóstico, ventana y limpieza sobre el instalador conservado.
Un dato incompleto falla sin activar accidentalmente una compilación completa.

## Comprobaciones de la corrección

Ubuntu, Python 3.13.2 y PowerShell portátil 7.6.9 oficial (archivo verificado contra
SHA del proveedor); ninguna instalación global ni dependencia de la app añadida.

```text
pwsh -NoProfile -File src-tauri/tests/test-artifact-integrity.ps1
python -m pytest tests/test_verify_windows_artifact.py tests/test_build_desktop.py tests/test_source_checkout.py -q
python scripts/quality.py --report reports/calidad-windows-2026-11-04/resume-quality
actionlint -shellcheck= .github/workflows/windows-build.yml .github/workflows/windows-verify-installer.yml
```

Resultados: **9 controles PowerShell**, incluidos siete rechazos de alteraciones,
**49 pytest**, seis controles de calidad y actionlint 1.7.12 correctos. Se ejecutó
además el helper PowerShell real sobre ambos ejecutables extraídos del NSIS;
prueba en `installer-payload-integrity.json`. No equivale a ejecutar Windows.
Un primer comando pytest tenía un nombre de archivo incorrecto: no ejecutó casos;
se corrigió y se ejecutaron los 49, sin ocultar fallos de pruebas.

Evidencias locales: `reports/calidad-windows-2026-11-04/`, log original
`windows-build-first.log`, `resume-guard-tests.xml`, `resume-quality/result.json`,
`installer-payload-integrity.json` y `reports/windows-reused-artifact.json`.
No se repiten las baterías de la app porque sus fuentes y artefactos no cambiaron.

Estado al preparar la reanudación: instalación diagnosticada y UI nativa pendientes.
No se han tocado datos reales ni flags fiscales. Certificado, expediente, corte
de Access y ensayo en equipo/impresora del taller siguen siendo pasos externos.
