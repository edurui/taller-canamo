# Instalación con datos iniciales · 04/11/2026

## Alcance

Un instalador privado local con el NSIS verificado del build `41802145854` sin
alteraciones, más una copia inicial completa. El único acompañamiento para el usuario
es un manual PDF de 24 páginas con 46 enlaces internos comprobados. Datos y entregables
privados fuera del repositorio; no se publican bases, certificados ni datos de clientes.

El script de restauración usa el protocolo existente del servicio, valida la copia y
los recuentos y mueve la carpeta provisional sólo después del cierre correcto.
Conserva cualquier base existente; rechaza una carpeta existente sin base reconocible.
Preserva todas las barreras de recuperación y fiscales. No cambia frontend/backend.

## Comprobaciones locales

- SQLite en lectura y backup online; restauración independiente: 33 tablas, 36 recursos,
  integridad/FK y origen intacto. 1.598 clientes, 1.292 vehículos, 5.145 históricos.
- PowerShell sobre el servicio Linux empaquetado: carga sintética, rechazo de destino
  existente y limpieza de preparación tras un fallo de validación correctos. Esta
  comprobación local no se presenta como ejecución Windows.
- `python -m pytest tests/test_private_installer.py -q`: cinco correctas.
- `python -m pytest tests/test_verify_windows_artifact.py tests/test_backup_streaming.py
  tests/test_source_checkout.py -q`: 53 correctas.
- `python scripts/quality.py --report reports/calidad-windows-2026-11-04/initial-data-quality`:
  Prettier, ESLint, Ruff lint/formato, rustfmt y Clippy correctos.
- `actionlint` de los dos workflows: correcto.
- Compilador oficial NSIS 3.11 con SHA-256 verificado frente al asset de tauri-apps.
  Compilación local mediante un prefijo Wine independiente; primer intento detectó
  separadores de ruta no válidos y se corrigió antes de iniciar Windows.
- PDF: 24 páginas renderizadas e inspeccionadas, 46 enlaces con destino existente.

## Ensayo Windows

Preparado `initial_data=true` en el workflow ya registrado, junto con el run/SHA de
construcción original. Descarga y vuelve a contrastar la identidad del instalador;
omite build y baterías generales ya aprobadas. Crea exclusivamente datos ficticios
en una cuenta desechable. Verifica instalación, recuentos/contenido, binarios intactos,
reinstalación que conserva altas posteriores y rechazo de carga incompleta.

Primer run `41815198573`: descarga/identidad correctas; falla en preparación del paquete
porque el contexto de SQLite no cerraba la conexión antes de borrar el temporal.
Se corrigen ambos lectores con `closing` y se añade una regresión que exige el cierre.
El script PowerShell usa los módulos de su propio host, aislando herencia de PowerShell 7
al invocar Windows PowerShell 5.1.

Run `41815703256`: empaquetado e instalación/carga inicial correctos; recuentos y
contenido restaurado coinciden. Falló el lector del test porque Python entrecomillaba
`/D=...` y NSIS utilizaba su destino predeterminado. El guion se corrige con la misma
sintaxis especial sin comillas que ya emplea `verify-installed.ps1`; sin cambios en
la aplicación o el instalador privado. Run `41815633009` cancelado al detectar que
GitHub había rechazado la actualización previa de rama. Ensayo final correcto: run `41816215691`, fuente `276ab1d`, job `126527517202`.
Se verifican los cuatro controles completos, incluido el contenido de cinco tablas
de la demo, binarios intactos, conservación de cada archivo de datos tras añadir
un cliente y reinstalar, y rechazo sin sustitución ante carpetas existentes o
validación posterior a restauración fallida. Build omitido; mismas 206 entradas.
Evidencia local: `calidad-windows-2026-11-04/initial-data-success/`.

Batería local final: 58 pruebas dirigidas y seis controles de calidad correctos.
Extraído el envoltorio privado: instalador original, copia inicial y script de carga
coinciden con sus fuentes. Carpeta de entrega contiene sólo EXE y manual PDF.

## Límite operativo real

La importación inicial no completa la activación fiscal ni el corte de Access. El
adaptador VERI*FACTU está implementado, pero faltan prueba autenticada y expediente.
La app actual sólo permite facturas nuevas de prueba hasta superar sus controles.
El usuario ha confirmado autónomo/Access sin VERI*FACTU. El usuario confirma que no tiene
el certificado en este ordenador; queda bloqueada únicamente la comprobación que
necesita ese acceso y los pasos de activación dependientes. La copia tampoco contiene
nombre fiscal/NIF del titular ni una numeración nueva acordada: no se inventan.
