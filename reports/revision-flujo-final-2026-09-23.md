# Revisión de requisitos y flujo diario — 23/09/2026

## Alcance y entorno

Contraste de `PROMPT_MAESTRO_TALLER_CANAMO.md` §§6–10 y 12–15 con código,
pruebas y evidencias actuales. La revisión comenzó en lectura. Integración autorizó
corregir los defectos reproducidos de kilómetros, paginación, búsqueda y país.

Ubuntu Linux 6.8.0-139 x86_64, Python 3.13.2, Node 22.22.2, Chromium de
Playwright 1.63.0. Cada prueba creó SQLite y archivos sintéticos en su directorio
temporal. No se abrió una base operativa ni `private-reference/`, se enviaron
mensajes reales ni se contactó con AEAT.

## Matriz de contraste

"Evidencia anterior" identifica pruebas existentes inspeccionadas, sin repetirlas
en esta revisión. La batería conjunta y el paquete definitivo los ejecuta integración
después de congelar las fuentes.

| Requisito | Código / prueba / evidencia | Estado de esta revisión |
|---|---|---|
| §6: buscador desde un carácter, normalización, alternativas, teclado y respuestas obsoletas | `contacts.py::search`, `core.tsx::CustomerSearch`; `test_workflows.py`, `e2e/editor-regressions.spec.ts`, `e2e/daily-workflow.spec.ts` | Implementado; las pruebas anteriores cubren signos, matrícula y respuestas antiguas. |
| §6: exactas y prefijos antes de coincidencias parciales en todos los identificadores | `contacts.py::search`; nuevos `tests/test_contacts_search.py` y `e2e/customer-history.spec.ts` | **Corregido y ejecutado**: código antiguo, NIF, teléfonos, nombre y matrícula; normalización de separadores NIF/teléfono. |
| §6: rendimiento declarado | `scripts/benchmark_search.py`; `reports/search-priority-benchmark-2026-09-23.json` | Nueva medición: 15.000 clientes, 30.000 vehículos, 15 muestras por consulta; p95 máximo **117,084 ms**, solo servicio/SQLite. No mide renderizado ni garantiza cualquier equipo. |
| §6: tres entradas principales, extras ocultables, claro/oscuro, letra, teclado, ventanas | `app.tsx`, `core.tsx`, `settings.tsx`, `web/style.css`; `e2e/accessibility.spec.ts` y flujo sin extras de `daily-workflow` | Implementado con evidencia anterior de navegador a 1024×768 y 1366×768. Escalas físicas Windows 100/125/150 % pendientes de ejecución externa. |
| §7: contacto sin NIF/email/matrícula, datos de dirección y país | `contacts.py::save_customer`, `people.tsx::CustomerForm`; pruebas nuevas de país/CP y alta E2E | **Corregido y ejecutado**: país visible, código de dos letras, CP extranjero conservado. Facturación internacional sigue rechazada expresamente y sin consumir número. Nombre de facturación completo explicado en el formulario; no se añadió un segundo nombre ambiguo. |
| §7: varios vehículos, titularidad, VIN/km/ITV/revisión, factura sin vehículo | `contacts.py`, `people.tsx`, `documents.py`; `test_integrity_regressions.py`, `e2e/ownership-rectification.spec.ts`, `daily-workflow` | Implementado. Nueva regresión confirma km de ficha → nueva factura → emisión → PDF y persistencia del km original después de editar el vehículo. |
| §7: km escritos a mano protegidos de respuestas antiguas | `documents.tsx::selectCustomer`; nueva E2E con respuesta real retenida y liberada | **Corregido y ejecutado**: una respuesta de 52.000 km no sustituye 53.001 km escritos durante su espera; una selección distinta también invalida la respuesta. |
| §7: alta de vehículo desde la factura y conservación de su km | `documents.tsx` callback de `VehicleForm`, `people.tsx`; quinta E2E nueva | **Corregido y ejecutado**: tras el alta se usa la selección con guarda. Se bloquea cerrar el alta mientras se guarda; una respuesta de km posterior no pisa el campo escrito al volver a la factura. |
| §7: histórico por cliente/vehículo accesible completo | `people.tsx::CustomerPage`, `VehiclePage`; `documents.py::list`; nueva E2E de 51 documentos | **Corregido y ejecutado**: paginación del historial de cliente y reinicio de página al cambiar filtro de vehículo. No se perdían filas en SQLite; faltaba poder abrirlas desde la ficha. |
| §7: borradores, guardado, revisión, numeración, snapshots, cobros, rectificativas y conversión | `documents.py`, `money.py`, `documents.tsx`; `test_workflows.py`, `test_integrity_regressions.py`, `test_document_relations_audit.py`, `test_rectification_tax.py`, `test_historical_payments.py`, `e2e/editor-regressions.spec.ts` | Implementado; evidencia anterior de transacciones, concurrencia, reintentos, snapshots e identidades. Las nuevas inicializaciones de km solo afectan a nuevas selecciones; abrir documentos hidrata su `payload`, incluidos origen/referencia. |
| §7: configuración con efecto real y series anuales/continuas | `settings.py`, `settings.tsx`, `documents.tsx`, `pdf.py`; `test_billing_settings.py`, `test_workflows.py::test_used_series_cannot_reset` | Implementado; defaults/vencimiento/tarifa/IVA/pago/serie y protección de series usadas tienen pruebas. No se reejecutaron las pruebas verdes ajenas al cambio de contactos. |
| §8: PDF A4, paginación, texto seleccionable, logo/marca, rectificación, vista previa e impresión | `pdf.py`, `app.py::pdf`, `core.tsx::PdfPreview`, `src-tauri/src/desktop_files.rs`; `test_pdf_layout.py`, `reports/pdf-layout/`, `reports/pdf-escritorio-2026-09-23.md` | Implementado y con evidencia anterior. Nueva E2E extrae texto real mediante pypdf y comprueba km. Integración revisa fuentes Unicode/PDF. Papel e impresión física Windows no acreditados. |
| §9: presupuesto → orden → factura, aceptación, estados, proveedor/stock e informes | `documents.py`, `catalogue.py`, `reporting.py`, interfaces correspondientes; `e2e/operations.spec.ts`, `test_reporting.py`, `reports/informes-operativos-2026-09-23.md` | Implementado y ejecutado anteriormente: una familia de conversión/consumo, movimientos idempotentes, devolución/recuento, caja separada de ajustes y saldo histórico desconocido. |
| §9: exportación utilizable y portable | `reporting.py`, `reports.tsx`, descarga por capability; `test_reporting.py`, `reports/copias-streaming-2026-09-23.md` | Implementado: JSON/tablas/CSV/recursos con hashes y procedencia; no contiene certificados ni claves ni se presenta como backup operativo. Exportación grande probada anteriormente. |
| §10: agenda completa, recurrencias/excepciones, fechas y DST | `agenda.py`, `calendar.tsx`; `test_agenda_occurrences.py`, `e2e/agenda.spec.ts`, `reports/agenda-2026-09-23.md` | Implementado y ejecutado anteriormente: mover/redimensionar con confirmación, formulario accesible, ocurrencia/serie, días mensuales inexistentes, Madrid y navegador en otra zona. |
| §10: avisos persistentes, posponer/reinicio, bandeja y autoinicio | `agenda.py`, `app.tsx`, `src-tauri/src/main.rs`, `notifications.rs`; pruebas de notificaciones y agenda | Backend/navegador ejecutados; soporte nativo presente. Windows, sonido, bandeja y autoinicio físicos requieren la aceptación externa declarada. No se promete avisar con proceso detenido. |
| §12: Access y alternativa intermedia, original preservado, mapeo, simulación, reimportación, conciliación/reversión | `access*.py`, `imports.tsx`, lector Java y herramientas; `test_access_imports.py`, `test_access_adversarial.py`, `e2e/access-import.spec.ts`, `reports/access-2026-09-23.md` | Implementado y probado con MDB/ACCDB sintéticos reales y CSV difícil. Ceros, claves compuestas, campos no mapeados, 15.001 registros, actividad posterior y cobro desconocido están cubiertos. Mapeo del MDB operativo y corte real requieren el archivo aportado. |
| §13: copia consistente, cifrado/segunda ubicación/retención, restore/rollback, traslado y numeración protegida | `backups.py`; `test_restore_recovery.py`, `test_backup_streaming.py`, `e2e/backup-streaming.spec.ts`, `reports/copias-streaming-2026-09-23.md` | Implementado y ejecutado anteriormente: fallos por etapas, interrupción, ZIP hostil, streaming, validación antes de migrar y no rebobinar números/cadena. 2 GiB sintéticos comprobados; no se midió 8 GiB completo ni USB/DPAPI físico Windows. |
| §14: automatizaciones, mensajes preparados, voz/OCR, consulta de histórico, revisión humana y núcleo sin modelos | `assistance.py`, `assistant.tsx`; pruebas `test_assistance*`, `e2e/assistance.spec.ts`, `reports/asistencia-ui-2026-09-23.md` | Implementado con motores locales reales y pruebas anteriores. Mensajes se preparan sin enviarse. Ollama tiene adaptador validado por contrato; no se acredita calidad de un LLM instalado. |
| §15: pruebas reales de dominio, SQLite, IPC, navegador, escritorio, a11y y seguridad | `tests/`, `e2e/`, pruebas Rust, informes de hitos y escritorio | Existe cobertura concreta; esta revisión añade regresiones sobre defectos observados. Pendientes batería conjunta/paquete final en integración y aceptación física Windows. No se usa el informe antiguo de 88 pruebas como resultado actual. |

## Defectos reproducidos y corregidos

1. **Nueva factura de vehículo preseleccionado con 0 km.** La ficha transmitía solo
   el identificador, y el editor inicializaba el kilometraje a cero. Ahora recibe el
   km de la ficha ya cargada, sin una respuesta tardía que sustituya la edición.
   Documento existente conserva el kilometraje de su propio `payload`.
2. **Kilometraje manual sustituido tras la carga.** Una respuesta tardía devolvía
   52.000 km después de escribir 53.001. La carga por identificador verifica la
   selección y una revisión del campo antes de aplicar su dato; los errores son visibles.
3. **Historial del cliente limitado a sus primeras 50 filas sin paginador.** La
   segunda página ahora es accesible, y cambiar el vehículo vuelve a la primera.
4. **Resultado parcial por delante de código/NIF/teléfono exacto.** Se comprobó
   `001` devolviendo `1001` antes de `001`, así como variantes NIF/teléfono y la
   matrícula prefija superando un código exacto. El ranking se aplica antes del
   límite; conserva ceros y comparte la normalización entre vehículos de un cliente.
5. **País invisible y CP extranjero rechazado al crear un contacto.** La edición
   ya soportaba el campo en datos pero el formulario no lo ofrecía y el backend
   exigía siempre cinco cifras. Se conserva país/CP sin imponer NIF ni email para
   crear una ficha; emitir una factura internacional continúa bloqueado.
6. **Variante del alta de vehículo dentro del editor.** El callback guardaba el
   identificador y omitía el kilometraje. Se reutilizó la selección protegida.
   La regresión prueba un alta con 82.000 km y otra con respuesta de 83.000 km
   demorada mientras el usuario escribe 83.007; esos 83.007 se guardan.

### Otras rutas de selección de vehículo revisadas al cerrar

| Ruta | Conservación del dato |
|---|---|
| Buscador global o ficha de titular → ficha de cliente → nueva factura | La ficha ya cargada pasa `vehicleId` y `vehicleKilometres`; no hay una carga posterior que sustituya una edición manual. |
| Buscador dentro del editor | Carga por identificador; revisa cliente, vehículo y revisión del campo antes de aplicar la respuesta. |
| Select de vehículo en el editor | Aplica los km del vehículo elegido de forma síncrona e invalida cargas anteriores mediante la revisión del campo. |
| Alta de vehículo dentro del editor | Reutiliza la ruta con guarda; no permite cerrar el formulario durante el guardado pendiente. |
| Alta de cliente dentro del editor, sin vehículo | Selecciona explícitamente el cliente sin vehículo y km cero. |
| Abrir borrador/emitida, conversión o rectificativa existente | `hydrate` recibe el kilometraje guardado en el `payload`; no dispara una selección ni lo sustituye por el dato actual de la ficha. `convert`/`rectify` conservan el dato de origen en backend. |

La revisión literal de callbacks/puntos de entrada de los módulos contrastados no
detectó un botón que devolviera un éxito ficticio. Esto no equivale a haber pulsado
cada control y combinación posible en cada plataforma.

## Ejecución de esta revisión

| Comando | Resultado / evidencia |
|---|---|
| `PLAYWRIGHT_JSON_OUTPUT_FILE=reports/customer-history-before-2026-09-23.json npx playwright test e2e/customer-history.spec.ts --reporter=list,json --output=reports/customer-history-before-artifacts --timeout=20000` | Rojo: km 0 y ausencia de paginador. El tercer fallo inicial era un nombre de selector incorrecto en la nueva prueba; se corrigió antes de comprobar la carrera. |
| `PLAYWRIGHT_JSON_OUTPUT_FILE=reports/customer-km-race-before-2026-09-23.json npx playwright test e2e/customer-history.spec.ts --grep 'respuesta tardía' --reporter=list,json --output=reports/customer-km-race-before-artifacts --timeout=20000` | Rojo real: esperaba 53.001 y recibió 52.000; captura/traza conservadas. |
| `.venv/bin/python -m pytest tests/test_contacts_search.py -q --tb=short --junitxml=reports/contacts-search-before-2026-09-23.xml` | 8 fallos / 2 correctas antes de corregir prioridad, separadores y CP extranjero. |
| `.venv/bin/python -m pytest tests/test_contacts_search.py tests/test_workflows.py -q --tb=short --junitxml=reports/contacts-search-after-2026-09-23.xml` | **40 correctas**, 1,69 s, salida 0. |
| Primera ejecución dirigida del alta desde editor, `reports/customer-vehicle-create-before-2026-09-23.json` | Falló el selector del test: `getByLabel` exacto incluía el asterisco de campo obligatorio. Se cambió a rol/nombre accesible. Este fallo no se presenta como una reproducción funcional. |
| `npm run typecheck:e2e` y `npm run build` | Salida 0; build incluye `npm run typecheck` real. Artefacto final de esta subtarea: `dist/assets/index-ZPCYpBTO.js`. |
| `PLAYWRIGHT_JSON_OUTPUT_FILE=reports/customer-history-after-2026-09-23.json npx playwright test e2e/customer-history.spec.ts --reporter=list,json --output=reports/customer-history-after-artifacts` | **5 correctas**, 5,5 s, salida 0. Backend/SQLite reales; se retienen respuestas HTTP reales para comprobar las carreras. |
| `.venv/bin/python scripts/benchmark_search.py --report reports/search-priority-benchmark-2026-09-23.json` | Salida 0; datos y percentiles declarados en la matriz. Equipo compartido, sin inferir tiempos Windows. |

Los resultados de esta revisión son un hito dirigido. Las evidencias de la batería
conjunta y del sidecar reconstruido deben corresponder a las fuentes congeladas por
integración; no se atribuyen a este informe hasta ejecutarse.

Estado al cierre: fuentes de esta subtarea congeladas y cedidas a integración;
ningún otro defecto funcional reproducido queda pendiente en esta revisión acotada.
