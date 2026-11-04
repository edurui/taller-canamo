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

## Primera ejecución corta y ajuste de WebView2

Run [41808916261](https://github.com/edurui/taller-canamo/actions/runs/41808916261),
commit de pruebas `6e5b184`: **build omitido**; 09:36:57–09:40:22 UTC, 3 min 25 s.
Pasan guardia de 206 entradas, driver Microsoft 156.0.4314.50, instalación,
integridad, PDF, reapertura y cierre del servicio instalado. Falla únicamente
la espera del puerto CDP de WebView2, antes de crear la sesión WebDriver.
No se atribuye aceptación de UI. ZIP de evidencia `13311840401`, SHA-256
`222a359c343b522d29c9f70438841cb752bd2e4f667d2f945aa711e02a4b918e`.

Los logs muestran app, servicio y WebView2 vivos, pero la variable de depuración
no permite conectar. Microsoft explica en [WebView2 #5640](https://github.com/MicrosoftEdge/WebView2Feedback/issues/5640)
que desde Runtime 150 los hosts elevados ignoran variables de usuario y políticas
HKCU para estos argumentos; admiten API del host o política HKLM. Se prueba esta
hipótesis sin recompilar: opción explícita `--ci-webview-policy`, rechazada fuera
de GitHub Windows, establece solo `AdditionalBrowserArguments/taller-canamo.exe`
en HKLM con el puerto local de ensayo. Conserva/restaura el valor anterior incluso
si falla la prueba y guarda evidencia de elevación/puerto/restauración. No usa
comodín, no cambia versión de WebView2 ni flags/protecciones de la aplicación.
El entorno de producción y el instalador permanecen intactos.

La captura previa al cierre se conserva con otro nombre que la captura posterior
del workflow; antes se sobreescribía y perdía el estado de la ventana fallida.
Se cubre también la respuesta GitHub `steps:null` de un job omitido, sin aceptar
jobs fallidos adicionales. **57 pruebas dirigidas correctas** (incluidas seis de
aislamiento/restauración de la política), Ruff y actionlint correctos; plantilla
YAML formateada. Los nueve controles PS se adelantan también al build completo.

## Cierre verificado

Run [41810156535](https://github.com/edurui/taller-canamo/actions/runs/41810156535),
job `126507120553`, commit de pruebas `8ca30f2719bb2f001f1f2708d900573bb67ed20e`:
**success**, 09:49:53–09:51:47 UTC, **1 min 54 s**. Job `build` omitido. No se
han repetido las baterías ni la compilación del instalador de `0e4b4d0`.

- Integridad, 206 entradas y evidencias originales correctas; mismo SHA del NSIS.
- Instalación con espacios/tildes, factura sintética, PDF, copia por bloques,
  reapertura de histórico, cierre y desinstalación correctos.
- **Cinco controles nativos**: ventana Tauri/buscador, demo desde UI/IPC real,
  matrícula normalizada/teléfono/ficha con Enter, PDF PyInstaller desde WebView,
  segunda instancia finalizada conservando la sesión original.
- Arranque **16,673 s**. `native-window.png` revisada: ficha demo, buscador,
  teléfono y vehículo legibles, aviso de edición de pruebas visible.
- WebView2 y driver Microsoft **156.0.4314.50**. El informe confirma host elevado,
  política específica y restauración (`original_value_present=false`, `restored=true`).
  El ajuste del entorno resuelve la conexión; ningún cambio en bytes de la app.

Evidencia GitHub `13312037113`, ZIP SHA-256
`c1f7904f869cceeadb47de3e03455145b396772d175616b5e3ed6b9081a5610c`.
Descargada, CRC/hash contrastados, en `calidad-windows-2026-11-04/resume-success/`.
Los hashes reales de app/servicio coinciden entre informe instalado y nativo.
`windows-reused-artifact.json` describe el punto previo (build, gates pendientes);
su aceptación posterior se acredita con los informes instalado/nativo y el run
correcto, no alterando retrospectivamente ese documento.

La publicación por Git tuvo errores SSH/HTTP 500 intermitentes. El conector creó
el árbol y la API el commit con identidad personal noreply; ambos hashes coinciden
exactamente con Git local. Actualización fast-forward con SHA anterior esperado,
sin force push ni modificación de `main`. Un dispatch HTTP 500 se reintentó solo
tras comprobar que no había creado un run; la petición posterior fue correcta.

Límites: Windows Server 2025 con herramientas de desarrollo en el runner; no se
ha probado aún un Windows 11 limpio del taller ni impresora, escalas, reinicio o
notificaciones físicas. La prueba nativa no usa los receptores de impresión Linux.
El NSIS no tiene firma digital (directorio de seguridad PE vacío). Se mantienen
las barreras fiscales; faltan certificado/expediente legítimos y corte/serie del taller.
El paquete puede entregarse para **ensayo**, no para emitir facturas operativas.


## Paquete preparado

Entrega nueva: `~/Entregas/Taller-Canamo-0.9.1-ensayo-2026-11-04/` y ZIP homónimo.
Contiene el instalador original, LEEME-PRIMERO.txt, PRUEBAS-Y-LIMITES.txt,
SHA256SUMS.txt y evidencias de hashes/instalación/ventana. Once archivos, sin datos
reales, certificados ni contraseñas; CRC y SHA de todos los archivos del ZIP
comprobados. ZIP de 284.821.615 bytes, SHA-256
`fa7243c596cf78e174bab570dcf61c7a7f02969737d2532ec25ae09d86e1447d`.
Se preserva el candidato previo y la entrega privada del 27/10.
Registro local: `calidad-windows-2026-11-04/delivery.json`.

ZIP de fuentes actualizado: `build/entrega/taller-canamo-0.9.1-fuentes-calidad-2026-11-04.zip`, 347 archivos, 2493947 bytes,
SHA-256 `c0a93fd9d6d1fcfbd11753a68409e0555e2ef644879f234d8677427370c735b2`; CRC y hashes internos correctos.
Las actualizaciones finales de estado/checklist son documentales y no requieren
repetir el build ni atribuirle un commit de aplicación distinto.
