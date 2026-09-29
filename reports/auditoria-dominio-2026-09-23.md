# Auditoría y correcciones de dominio · 23 de septiembre de 2026

Ámbito de esta revisión: relaciones documentales, emisión y rectificación, trabajos de
asistencia, validación B2B por lote y liberación fiscal/certificado. Entorno Linux x86_64,
Python 3.13.2 y SQLite temporal con datos sintéticos. No se utilizaron datos de
`private-reference/`, certificados reales, servicios autenticados ni AEAT producción.

La revisión parte de `PROMPT_MAESTRO_TALLER_CANAMO.md`, leído íntegramente. Este informe
registra comprobaciones concretas del hito; la batería final conjunta la coordina el agente
raíz después de congelar todos los módulos. Los resultados de distintas baterías se
solapan y **no deben sumarse** para presentar un número total de pruebas independientes.

## Fallos reproducidos y corregidos

| Fallo | Reproducción y efecto | Corrección y regresión |
| --- | --- | --- |
| Anulación de una factura con rectificativas vigentes | Una factura de 121,00 EUR y su rectificativa de −121,00 EUR permitían anular solo la original y dejar el abono vigente. | `void` bloquea con `rectifications_exist` mientras haya rectificativas descendientes en borrador o emitidas; devuelve referencias para revisarlas. Pruebas de eliminación de borrador, anulación del abono, descendientes y concurrencia con dos conexiones. |
| Origen documental modificable o con otra identidad | Un borrador podía apuntar a un presupuesto de otro cliente, y la conversión devolver una factura de una familia incorrecta. | Origen inmutable al editar, identidad común de cliente/vehículo, transiciones permitidas y unicidad por tipo en la familia; misma comprobación al guardar, convertir y emitir. Regresiones de familia antigua incoherente y segunda factura conservan la protección contra duplicar stock. |
| Asistencia bloqueando búsqueda/emisión | Una operación lenta mantenía el bloqueo global durante el motor; una búsqueda concurrente esperó a su finalización en la reproducción controlada. | Trabajos en memoria con `start`, `job_status` y `cancel`; un trabajador activo, idempotencia, TTL de 15 minutos y ocho resultados retenidos. La cancelación descarta el resultado y no crea otro trabajador hasta acabar el anterior. Se conservan métodos síncronos compatibles. Pruebas con motores locales reales y retraso controlado, búsqueda/emisión concurrentes, errores filtrados y ausencia de escrituras SQLite. |
| Compilación repetida del validador B2B durante copias | Diez validaciones independientes de una factura tardaron 2,1061 s en la medida registrada. Cada documento recreaba el contexto Saxon y las reglas. | Contexto por lote, comprobación de hashes al entrar y validación completa XSD/EN16931 de cada XML; no hay aceptación por caché del resultado. Un documento alterado con su hash recalculado se rechaza entre documentos correctos. |
| Marcado de prueba fijo después de una futura liberación legítima | La publicación escribía siempre `test_document: true`, incluso detrás de una ruta de producción aprobada. | El metadato y su auditoría se derivan del entorno después de los controles. Pruebas de lógica pura y rechazo real de emisión al alterar solo la configuración; ningún test presenta una factura de producción como aceptación externa. |
| Liberación dependiente de una constante y límite incorrecto del binario | Una entrega candidata legítima seguía necesitando cambios de código; el hash del servicio compartía el límite de artefactos de 100 MB pese a los motores empaquetados. | Política candidata embebida antes del build Windows completo, comprobaciones reales intactas y herramientas locales de verificación/instalación. SHA por bloques hasta 2 GiB para el servicio; límites de manifiesto y artefactos conservados. Fichero disperso real de 100.000.001 bytes verificado, expediente sintético rechazado por falta de mTLS. |
| Certificado protegido y metadatos podían divergir | Una excepción al actualizar metadatos después de sustituir el archivo podía dejar la clave del certificado nuevo y la huella del anterior; leer la configuración después del transporte podía atribuir otra huella a una petición en curso. | Compensación del archivo ante fallo de metadatos, comparación de huella del PKCS#12 antes de TLS y evidencia tomada del contexto SSL efectivamente cargado. Pruebas con dos PFX sintéticos, carga SSL real, caída simulada entre reemplazo/metadata y rotación durante la petición. No se abre la red ni se persiste evidencia ficticia. |

La validación de caracteres del PDF se añadió también a `Documents.publish` después de
crear los snapshots en memoria y antes de registro fiscal, stock y numeración. La fuente,
su verificación y la regresión de un carácter no representable las implementó el agente
raíz; la llamada se comprobó aquí con las baterías dirigidas indicadas abajo.

En la revisión final, raíz detectó que `App.tick` solo invocaba la cola en `aeat_test`.
Se confirmó por lectura que no existía otro temporizador de producción: STDIO y el servidor
llaman al mismo `tick` cada 30 segundos; la interfaz ofrece un botón manual. Se recomendó
incluir ambos entornos remotos y conservar `send_next`, que aplica el diagnóstico real antes
de reservar la cola. Raíz es propietario de esa corrección y sus regresiones; es posterior
a las baterías de este informe y exige reconstruir el servicio. No se oculta ese cambio
atribuyéndolo a un binario o prueba anterior.

## Contratos integrados

- `documents.get` devuelve `conversion_identity_locked` y `active_rectifications`.
  La interfaz conserva la identidad de las conversiones y explica las rectificativas que
  impiden anular. Se mantienen edición de borradores independientes y trazabilidad.
- `assistant.start(operation, params, idempotency_key)`, `assistant.job_status(identifier)`
  y `assistant.cancel(identifier)` son las acciones para la interfaz. Estados:
  `queued`, `running`, `completed`, `failed`, `cancelled`. Se devuelven únicamente propuestas;
  no se aplica contenido automáticamente a una factura. Cancelar no puede matar una llamada
  nativa en curso, pero descarta su resultado y limita la concurrencia a un trabajador.
- `b2b_xml.validation_session()` conserva un procesador Saxon y esquemas por lote, con
  verificación de recursos al entrar. `check_storage` recorre documentos mediante cursor
  y mantiene las comprobaciones de originales, identidad, hashes, estados y obligaciones.
- `fiscal.readiness()` público no acepta configuración por IPC. Ajustes usa de forma
  privada la configuración candidata y exige el mismo diagnóstico para guardar producción.
  La política por defecto es `development`; el constructor admite candidato únicamente
  Windows x64 MSVC completo. Una constante, una URL QR o un ajuste aislado no autoriza emitir.
- La herramienta de expediente abre SQLite en solo lectura, no inicializa App, no migra,
  no se conecta, no crea resultados positivos y no activa producción. Copia solo artefactos
  referenciados, verifica la copia y conserva el expediente anterior. Un expediente ausente,
  alterado o sin intercambios mTLS de pruebas se rechaza.

## Comandos y evidencia

| Comando | Resultado conservado |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_document_relations_audit.py tests/test_integrity_regressions.py tests/test_rectification_tax.py tests/test_workflows.py --junitxml=reports/pytest-document-relations-corrected-2026-09-23.xml` | 77 correctas; 3,59 s. |
| `.venv/bin/python -m pytest -q tests/test_assistance_jobs.py tests/test_assistance.py tests/test_document_relations_audit.py --junitxml=reports/pytest-assistance-jobs-2026-09-23.xml` | 36 correctas; 4,77 s. |
| `.venv/bin/python -m pytest -q tests/test_b2b.py tests/test_b2b_batch.py tests/test_restore_recovery.py --junitxml=reports/pytest-b2b-batch-2026-09-23.xml` | 60 correctas; 12,54 s. |
| `.venv/bin/python scripts/benchmark_b2b_batch.py --count 1000 --output reports/b2b-batch-benchmark-2026-09-23.json` | 1.000 documentos, 1.000 originales y 1.000 eventos comprobados en 2,7009 s; copia real en 2,8615 s, 1.985.294 bytes. |
| `.venv/bin/python -m pytest -q tests/test_release_candidate.py tests/test_certificate_consistency.py tests/test_fiscal_official.py tests/test_fiscal_workflow.py tests/test_transport_fiscal.py tests/test_document_relations_audit.py tests/test_rectification_tax.py --junitxml=reports/pytest-release-certificate-2026-09-23.xml` | 137 correctas; 6,82 s en la repetición final con el control previo del PDF. Hashes en el JSON adjunto. |
| `.venv/bin/python -m pytest -q tests/test_release_candidate.py tests/test_document_relations_audit.py tests/test_rectification_tax.py --junitxml=reports/pytest-publication-font-gate-2026-09-23.xml` | 50 correctas; 2,34 s, después de insertar el control previo de fuente. |

La medida B2B utiliza 1.000 documentos B2B sintéticos y una factura fiscal como plantilla.
No mide 1.000 registros VERI*FACTU, tiempo universal ni Windows. El archivo JSON de benchmark
conserva plataforma, cantidades y hashes del código usado; la base temporal se eliminó.

Se conservan los fallos iniciales: `pytest-document-relations-2026-09-23.xml`
(creación simultánea de dos App en el fixture), `pytest-release-certificate-initial-2026-09-23.xml`
(nombre de tabla del fixture) y `pytest-release-certificate-cli-initial-2026-09-23.xml`
(ruta de importación del subproceso de desarrollo). Se corrigieron los fixtures y se
repitieron las regresiones manteniendo las aserciones y los validadores.

## Límites y siguiente comprobación externa

- No se han probado DPAPI en Windows, un instalador Windows ni una impresora física en este
  hito. Las pruebas PFX sustituyen únicamente la frontera DPAPI; parseo y contexto SSL son
  reales y las respuestas de red están reemplazadas localmente.
- Una caída de proceso entre archivo protegido y metadatos no promete recuperación
  automática: la discrepancia bloquea TLS y requiere reinstalar el certificado original.
  Una caída entre renombrados del expediente puede requerir reinstalarlo desde la copia
  privada conservada; el diagnóstico permanece bloqueado si falta.
- No existe expediente aprobado, ni certificado proporcionado para un ensayo autorizado,
  ni aceptación AEAT real. El procedimiento reproducible y los comandos exactos están en
  `docs/FISCAL-LIBERACION-2026-09-23.md`. Construir el candidato precede a los ensayos; no se
  recompila ni altera el servicio después de fijar la evidencia de sus bytes.
- VERI*FACTU y B2B conservan adaptadores y estados separados. La mejora del validador local
  B2B no implementa ni simula un contrato público remoto que no esté acreditado.
- Root integra y verifica UI, empaquetado y batería conjunta final. Este informe no los
  atribuye a las pruebas backend dirigidas ni sustituye sus informes específicos.
