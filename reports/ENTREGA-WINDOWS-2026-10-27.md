# Reanudación y entrega Windows · 27/10/2026

## Resultado comprobado hasta ahora

El build [40579253295](https://github.com/edurui/taller-canamo/actions/runs/40579253295),
commit `10bb9372544dfb581e77e9b652c85becc116a559`, produjo el instalador NSIS x64.
Pasaron construcción, servicio congelado, 819 pytest, 166 E2E, instalación y
diagnóstico del servicio instalado. El job terminó fallido exclusivamente al
conectar WebDriver con la ventana Tauri (timeout de 40 segundos en POST /session).
No se interpreta ese fallo de automatización como una ventana verificada.

Instalador conservado sin reconstruir, 284.628.510 bytes, SHA-256:
`fe4924812fe0f4b72890b642398b1238ae0ddc052c7b26074c04c827e32863f9`.
El servicio candidato conserva la política `release_candidate`; no se habilitó
producción ni se alteró ningún requisito fiscal.

## Verificación del candidato conservado

`scripts/verify_windows_artifact.py` exige identidad del run y commit, pasos de
build/instalación correctos, baterías sin fallos/omitidos/flaky, política coincidente,
hash/tamaño del instalador y fuentes intactas. Se ejecutó sobre los artefactos reales
en una copia local con checkout Windows (`core.autocrlf=true`): **124 entradas
versionadas coinciden**. Este control se ejecutó en Linux y no abre el EXE.

Ocho pruebas sintéticas de la guarda correctas: aceptación para repetir únicamente
la prueba nativa y rechazo de instalador alterado, fallo Python, navegador omitido,
fuente cambiada, paso fallido ajeno a WebDriver, otro commit y otra política. En
todos los rechazos se retira una aceptación anterior. No son ensayos Windows.

El harness preparado inicia el EXE instalado y conecta Edge Driver al WebView2
que realmente abre, con puerto de depuración limitado a ese proceso de pruebas.
Es el procedimiento de conexión a una instancia existente documentado por
[Microsoft](https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/webdriver).
No se habilita depuración en la instalación de entrega. El workflow de repetición
conserva y compara los mismos bytes; no recompila ni sustituye pruebas por mocks.
Su ejecución requiere publicar las herramientas de prueba en el repositorio
existente; se solicitó la autorización exigida por CODEX_PROMPT.md.

## Datos y comprobaciones locales

Comparación nueva, de solo lectura: 22 tablas idénticas entre el ensayo persistente
y la restauración; integridad SQLite y claves foráneas correctas en ambas bases.
Coinciden los hashes de la copia cifrada y del MDB original con los informes previos.
Totales: 1.598 clientes, 1.292 vehículos y 5.145 históricos. Se conservan los conflictos
pendientes y no se preparó un traslado definitivo. Datos y contraseña fuera de Git.

`python scripts/verify.py --report reports/reanudacion-2026-10-27`, usando `.venv`:
pip check correcto, 819 pytest correctas (55,95 s), typecheck de aplicación y de
E2E correctos, build Vite correcto y 166 E2E correctas (243,485 s), cero fallos,
omitidas o flaky. Fuentes intactas durante la batería. Los comandos, tiempos,
hashes y límites se conservan en `reports/reanudacion-2026-10-27/`. Las ocho pruebas
de la guarda están en `tests/test_verify_windows_artifact.py` y pasaron después
de la batería completa; no se presentan como ejecutadas dentro de sus 819 casos.

## Límites de la entrega de ensayo

Paquete local preparado en
`~/Entregas/Taller-Canamo-0.9.1-ensayo-Windows-2026-10-27.zip`, con ocho archivos:
EXE, copia cifrada, guía, muestra de impresión, informes de datos/restauración,
estado del instalador y `SHA256SUMS.txt`. CRC del ZIP y SHA-256 de cada entrada
comprobados. La contraseña se conserva fuera del paquete. No se publicó el ZIP,
el instalador ni los datos del taller. La guía identifica explícitamente la prueba
nativa pendiente; no se ha creado una aceptación ficticia.

Fuentes actualizadas sin datos privados en
`build/entrega/taller-canamo-0.9.1-fuentes-reanudacion-2026-10-27.zip`, verificadas
por CRC y hashes individuales. No se ha realizado commit ni push en esta reanudación.

La restauración de los datos reales se verificó en Linux. Falta ensayarla en el PC
Windows del taller, junto con impresión física, reinicio y avisos del equipo.
El candidato no está firmado digitalmente. No se ha ejecutado aceptación AEAT
con el certificado del titular ni se ha completado la liberación fiscal.
La copia en otro equipo mantiene `transfer_required`: consulta y borradores,
emisión bloqueada. Access sigue siendo el sistema operativo hasta el corte acordado.
