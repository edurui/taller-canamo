# Estado verificado · 6 de octubre de 2026

**Migración del Access real implementada y ensayada localmente con conservación explícita
de datos desconocidos y conflictos.** Versión 0.9.1 de desarrollo: no apta todavía para
emitir facturas operativas. Quedan conflictos históricos que requieren evidencia humana
y las comprobaciones externas, sin atribuirles resultados locales. La revisión previa
de interfaz está documentada en
`reports/MEJORAS-INTERFAZ-2026-09-29.md`; la entrega del 23/09 es evidencia histórica.

## Access real · 06/10/2026

Informe actual: `reports/ACCESS-REAL-2026-10-06.md` y anexos. Los dos MDB existen y se
leyeron en modo read-only; sus SHA-256 permanecen iguales. Se recuperaron fórmulas de
informes y 12/11 módulos VBA, pero no su vigencia por periodo ni redondeo/impresión
histórica suficiente para reconstruir importes. No se impone 21 % ni calendario legal.

- Lector corregido para contadores internos obsoletos, con conteos efectivos/metadatos
  visibles. Fixture MDB real que reproduce discrepancia de contador.
- Migración SQLite 8: fechas/importes históricos desconocidos NULL, estados explícitos,
  precisión raw y procedencia. Facturación nueva mantiene restricciones. PDF/listado/UI
  muestran «No consta», sin deuda, pagos ni agregados financieros inventados.
- Perfil sugerido sobre columnas reales, relación postal y modo parcial. Cabeceras
  idénticas consolidadas, identidades huérfanas recuperadas por clave compuesta, conflictos
  agrupados, decisiones por fila y originales completos. No se inventan propietarios.
- Ensayos limpios A/B y comprobación final C: **1.595 clientes, 1.290 vehículos, 5.133
  históricos, 19.335 líneas**; 27.621 filas raw conservadas, conciliación sin diferencias,
  series/cola fiscal intactas. A y C revertidos, B conservado para inspección; no operativo.
- Pendientes explícitos: 18 clientes, 222 referencias de vehículos, 70 candidatos de
  histórico y 326 líneas no atribuibles; 38 históricos importados con fecha conflictiva
  y 45 sin fecha. No presentarlos como resueltos ni como datos perdidos.
- Búsqueda comprobada para los 1.595 códigos de cliente y 1.290 matrículas importados;
  seis comprobaciones de PDF, dashboard/reportes, auditoría e integridad SQLite/FK.

Verificación actual: **496 pytest correctas, 208,45 s**; **47 pruebas dirigidas Access/
contratos correctas, 37,24 s**; pip check, ambos typechecks y Vite correctos;
**41 E2E correctas**, 141,260 s (incluida accesibilidad). Servicio empaquetado final con
9 grupos funcionales correctos, 18 pruebas Rust correctas, check/build Tauri Linux y
diagnóstico correctos, **8/8 comprobaciones de ventana Tauri/WebKit real**, incluido
selector GTK, con datos sintéticos. Véase `reports/ACCESS-DESKTOP-2026-10-06.md`.

Git ahora sí tiene `main` en `a67f8d24c03ab439820bfc11198629d909878e13`. Se preservó
el cambio previo del lector y el diff inicial; los cambios de esta sesión quedan locales,
sin commit, staging ni push. No hay bases ni certificados trackeados/staged ni PII real
en las adiciones revisadas. Los apartados fechados de septiembre son evidencia anterior,
no describen el esquema ni los artefactos reconstruidos actuales.

## Revisión de Git · 29/09/2026

El usuario ha inicializado Git y configurado `origin`. En esta revisión local, rama `main`
sin commits ni archivos en el índice. `.gitignore` excluye artefactos de compilación/pruebas,
datos privados y certificados, conservando fuentes, locks, licencias fuente e informes
redactados. Comprobadas las reglas con Git y la inclusión de las 279 fuentes del inventario
de empaquetado. Los artefactos de `reports/` referenciados abajo permanecen locales;
sus resúmenes Markdown sí se incluyen. Detalle en `reports/REVISION-GITIGNORE-2026-09-29.md`.
Las menciones anteriores a la ausencia de `.git` describen el entorno de esas fechas.

## Ajustes posteriores de alineación · 29/09/2026

Campos con textos de ayuda alineados por arriba en el estilo común; se conserva la
alineación inferior de acciones explícitas. Menú lateral de Configuración sticky con
altura adaptable, desplazamiento interior y foco visible; cambiar de sección desde abajo
muestra su comienzo. Separación de 1rem entre botón y aviso en Asistencia. Corregida también
la semántica accesible del logo provisional. Sin cambios de backend ni datos reales.

Verificación: 38 E2E correctas (103,138 s); después del último atributo del logo, ocho E2E
de interfaz/accesibilidad correctas. Ambos typechecks y build correctos, Tauri Linux final
recompilado (4,32 s) y siete comprobaciones nativas correctas. Medidas de alineación,
ventana de 380 px de alto, letra de 20 px hasta 320 px de ancho y Axe documentados en
`reports/AJUSTES-ALINEACION-2026-09-29.md`. Windows sigue pendiente. Los hashes actuales
están en `reports/ui-alignment-2026-09-29/artifacts.json`; los de la primera revisión quedan
como evidencia de aquella versión.

## Revisión de interfaz · 29/09/2026

- Controles comunes de texto, número, selección, texto largo, sugerencias y fecha en toda
  la interfaz; calendario en castellano con elección de año/mes/día, teclado y límites.
  Selectores y calendarios ocupan la pantalla en móvil. Archivos, casillas y rango siguen
  siendo controles nativos. La edición manual de fechas conserva el formato del sistema.
- Modales y paneles con entrada/salida breve, preferencia de movimiento reducido, pila de
  foco/inert y cierre seguro. Cerrar el dictado libera el micrófono al iniciar la salida.
- El buscador conserva la lista durante la siguiente consulta, sin desmontarla por tecla;
  las opciones antiguas no son seleccionables hasta recibir el resultado vigente.
- Espaciado de ficha/Resumen, fila vehículo/km/alta, botones PDF sin saltos, tarjetas de
  vehículo y proporciones del icono Configuración corregidos.
- Borradores con líneas reordenables por arrastre, botones y teclado; cantidades/importes,
  guardado, reapertura y orden del PDF verificados. Las facturas emitidas siguen protegidas.
- Configuración destaca Normal/Grande/Muy grande (16/18/20 px), vista previa reversible y
  persistencia tras reiniciar. Comprobado hasta 320 px sin desbordamiento horizontal en los
  recorridos ensayados; no cambia el tamaño de impresión A4.

| Comprobación actual | Resultado | Evidencia en `reports/ui-2026-09-29/` |
|---|---|---|
| `.venv/bin/python -m pytest` | 438 correctas, 77,06 s; ejecutadas al inicio, backend sin cambios posteriores | `baseline-pytest.log` |
| `npm run typecheck` y `npm run typecheck:e2e` | Ambos código 0 | `typecheck.log`, `typecheck-e2e.log` |
| `npm run build` | Código 0; Vite 1,13 s | `build-final.log` |
| `npm run test:e2e` | 38 correctas, 0 fallos/omitidas/flaky; 178,012 s | `e2e-final-results.json`, `e2e-final.log` |
| Axe y revisión visual | Sin infracciones en los recorridos automatizados; claro/oscuro, teclado, móvil y letra grande | Capturas y adjuntos en `reports/e2e/` |
| `npm ls --depth=0` y `python -m pip check` | Ambos código 0, sin incompatibilidades | Logs de dependencias |
| `cargo +1.98.1 build --locked` | Código 0; Tauri Linux con interfaz actual, 2 min 41 s | `tauri-build-final.log` |
| Tauri/WebKit real | 7 comprobaciones correctas, datos sintéticos e IPC real | `desktop/result.json` |

No se han cambiado el backend, el esquema SQLite ni los locks. El smoke nativo espera
ahora a que termine su servicio antes de eliminar los datos temporales; se conservan los
intentos fallidos y su diagnóstico. Apertura/impresión usan receptores de prueba: **no es
impresión física**. Windows/WebView2 no están disponibles y siguen pendientes. Las huellas
de esta revisión se conservan en `reports/ui-2026-09-29/artifacts.json`.

## Verificación base · 23/09/2026

Los siguientes resultados corresponden a la revisión anterior. Sus tiempos, hashes y ZIP
no describen los nuevos archivos de interfaz; se conservan como evidencia fechada.

Entorno Ubuntu Linux x86_64, Python 3.13.2 en `.venv`, Node 22.22.2/npm 10.9.7 y Rust 1.98.1.
Sin directorio `.git`. Datos sintéticos y SQLite temporal; no se han abierto bases operativas,
publicado repositorios, enviado datos a AEAT ni mensajes a clientes. Las referencias privadas
no se usan en pruebas ni se incluyen en el ZIP de fuentes.

Comando: `.venv/bin/python scripts/verify.py --report reports/final-verification-2026-09-23`.
Informe `result.json`: **passed=true**, seis códigos 0 y **ningún cambio de fuentes** durante
la ejecución. Se registran 220 huellas y las de `dist`.

| Comprobación | Resultado exacto | Evidencia |
|---|---|---|
| `python -m pip check` | Sin incompatibilidades; 0,161 s | `final-verification-2026-09-23/python-dependencies.log` |
| `python -m pytest` | **438 correctas**, 0 fallos/errores/omitidas; 40,26 s de pytest | `final-verification-2026-09-23/pytest.xml` y log |
| `npm run typecheck` | Código 0; 2,524 s | `final-verification-2026-09-23/typescript.log` |
| `npm run typecheck:e2e` | Código 0; 1,090 s | log correspondiente |
| `npm run build` | Código 0; 4,374 s; Vite y TypeScript | `final-verification-2026-09-23/vite.log` |
| `npm run test:e2e` | **32 correctas**, 0 fallos/omitidas/flaky; 55,3 s de Playwright | `final-verification-2026-09-23/e2e-results.json`, log y `reports/e2e/html/` |
| `cargo test --locked --no-default-features --lib` | **18 correctas**, 2,00 s | `rust-final-2026-09-23.txt` |
| Build Tauri Linux final | Código 0, ejecutable enlazado; 6,34 s | `tauri-final-build-2026-09-23.txt` |
| Servicio PyInstaller completo | Motores reales Saxon/Vosk/RapidOCR/JRE, PDF, licencias, copia/portable y reapertura correctos | `sidecar-functional.json`, `sidecar-artifact.json` |
| Tauri/WebKit real final | **8 comprobaciones correctas**; búsqueda/ficha/PDF/instancia y selector GTK real | `desktop-final/result.json`, `escritorio-final-2026-09-23.md` |
| Tipos Win32/COM/notificaciones | Código 0; no ejecución ni enlace Windows | `rust-pdf-windows-typecheck-2026-09-23.txt` |

Los tiempos del comando contenedor se conservan también: pytest 40,592 s y E2E 56,186 s.
Los mensajes de color de Node quedan en el log; no son errores de tests. Las pruebas con
transportes simulados están identificadas y nunca producen evidencia de aceptación AEAT.

## Implementación y comprobaciones complementarias

- Flujo directo sin orden/presupuesto/stock obligatorio. Borradores, numeración, cálculos
  decimales, cobros, snapshots y titularidad con histórico; E2E sin vehículo y extras ocultos.
- Revisión final corrigió paginación de ficha a partir de 50 documentos, km iniciales y
  respuestas tardías, alta de vehículo desde factura, país/CP extranjero y ranking exacto
  por código/NIF/teléfono. `reports/revision-flujo-final-2026-09-23.md` contiene la matriz.
- Búsqueda: 15.000 clientes/30.000 vehículos, 15 muestras por consulta; p95 máximo
  **117,084 ms**, solo servicio. `reports/search-priority-benchmark-2026-09-23.json`.
- PDF Unicode con DejaVu embebida, A4 de 1/7/1 páginas inspeccionadas, precisión,
  rectificativas, datos históricos ausentes y caché inmutable. Carácter sin glifo detiene
  emisión antes de numerar. `reports/pdf-unicode-2026-09-23.md`.
- Agenda con recurrencias/excepciones, Madrid/DST, arrastre/duración, teclado y avisos;
  stock/proveedores/conversiones/informes/exportaciones; OCR/dictado reales, propuestas
  cancelables y revisión humana. Los 32 E2E recorren estos módulos con backend real.
- Copias AES-GCM/ZIP por bloques, límites explícitos 8 GiB descomprimidos/9 GiB de archivo/
  50.000 entradas, prevalidación ZIP/ZIP64, restauración con recuperación y traslado protegido.
  Ensayo real con original sintético compresible de **2 GiB** y SHA exactos; no acredita
  todos los máximos ni un MDB de ese tamaño. `reports/backup-capacity-2026-09-23.json`.
- Selector GTK real: copia cifrada de **3.762.699 bytes**, cancelación, sustitución y SHA
  idéntico a copia local. El primer intento fallido del harness se conserva y explica.
- Access nativo MDB/ACCDB con Jackcess/JRE, diagnóstico/perfiles/mapeo/staging/simulación/
  lotes/reanudación/conciliación/rollback. Bases sintéticas reales y 15.001 clientes sin
  truncamiento. Guía y límites: `docs/IMPORTACION-ACCESS.md`.
- VERI*FACTU: XSD/hash/QR, cola/esperas/Consulta, subsanación y rectificación de cuota;
  certificado y huella TLS coherentes; candidato Windows con expediente verificable.
  `App.tick` procesa ambos modos remotos con los gates intactos. No autoriza producción.
- Guion `verify_aeat_authorized.py`: comprobación local por defecto y ejecución explícita
  de IDs revisados mediante el candidato real. **15 pruebas locales**, incluidas en 438.
  Procedimiento completo: `docs/FISCAL-ENSAYO-AUTORIZADO-2026-09-23.md`.
- B2B separado: UBL2.1 + XSD/EN16931 real, originales recibidos, estados/exportación;
  1.000 documentos B2B validados en 2,701 s, copia 2,862 s. No equivale a entrega remota
  ni a 1.000 registros fiscales. `reports/b2b-batch-benchmark-2026-09-23.json`.
- Axe sin infracciones en los recorridos comprobados; capturas claro/oscuro/texto grande,
  1024×768/1366×768 y PDF revisadas. No certifica accesibilidad completa. Los selectores
  de fecha de esa revisión eran nativos. La revisión del 29/09 añade el calendario propio;
  quedan por comprobar locale de entrada manual y escalas Windows.
- npm/Python: ninguna vulnerabilidad conocida detectada. Cargo: cero categoría vulnerabilities,
  **seis advertencias de mantenimiento y una GLib insegura**, conservadas; GLib ausente del
  árbol Windows. `reports/seguridad-dependencias-2026-09-23.md`.
- Licencias: 620 dependencias y ZIP de 1.361 archivos verificado; excepción de aviso MIT
  ausente del binario opcional de construcción LZMA documentada. No se distribuye ese
  binario como biblioteca ejecutable del instalador.

TypeScript tiene `strict:true`, pero conserva contratos `Row/any`; no se afirma tipado íntegro.
`check_ts_syntax.cjs` no se utiliza como sustituto de typecheck/E2E. Los informes anteriores
(88/147/274/371 casos) se conservan como hitos y no sustituyen esta batería final.

## Artefactos y documentación

- Ejecutable Tauri Linux: `src-tauri/target/debug/taller-canamo`.
- Servicio Linux completo: `src-tauri/binaries/canamo-service-x86_64-unknown-linux-gnu`,
  también junto al ejecutable Tauri. Arranque/reapertura 3,7801/3,7687 s en este equipo.
- ZIP de fuentes y licencias del 23/09 en `build/entrega/`; inventario histórico en
  `reports/artefactos-entrega-2026-09-23.json`. Ese ZIP no incorpora la interfaz del 29/09;
  construir el candidato Windows desde las fuentes actuales, no desde ese archivo anterior.
- `LEEME.md`, `docs/BUILD-WINDOWS.md`, guías de Access/copias/asistencia/fiscalidad y
  `CONTINUAR.md`. El manifiesto heredado se preserva en `docs/MANIFEST-HEREDADO-SHA256.json`.

## Dependencias externas reales

1. **Windows 11/WebView2 e impresora**: construir NSIS e instalar/actualizar/reinstalar;
   ejecutar DPAPI, Job Object, bandeja/notificaciones, escalas y papel. No existe instalador
   Windows generado aquí. Scripts/workflow preparados, sin remoto ni runner ejecutado.
2. **Certificado e identidad/representación legítimos**: ejecutar la batería autenticada
   AEAT pruebas con el candidato, conservar acuses/consultas y completar el expediente
   revisado del productor. No se sustituye por mocks ni por instalar un certificado.
3. **MDB/ACCDB original**: identificar su esquema concreto, mapearlo, resolver incidencias,
   conciliar y ensayar el corte. El importador ya está desarrollado.
4. **Contrato público B2B**: perfil/endpoint definitivo no localizado en las fuentes
   oficiales revisadas; dependencia acreditada en `docs/B2B-FUENTES-2026-09-23.md`.

No queda un defecto funcional reproducido sin corregir en los recorridos ejecutados.
Las dependencias externas impiden aprobar aún su uso operativo; no implican métodos vacíos
ni tareas de programación trasladadas al usuario como si fueran configuración.
