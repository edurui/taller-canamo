# Integridad de documentos, IVA y conversiones — 2026-09-23

Revisión ejecutada con bases SQLite temporales y datos sintéticos. No se han consultado
datos de `private-reference/`, bases operativas, certificados ni Access reales.

## Defectos reproducidos y correcciones

- **Identidad histórica:** el listado consultaba `customers.name` y `vehicles.plate`
  actuales mientras el detalle devolvía snapshots. Detalle, filtros, recuento y paginación
  usan ahora una proyección común de la identidad documentada. Los borradores ordinarios
  siguen mostrando los datos actuales. Las facturas emitidas, anuladas e históricas
  conservan la identidad de su snapshot, aunque el cliente cambie de nombre y el vehículo
  se transfiera o cambie de matrícula. Los presupuestos/órdenes con snapshot también lo
  respetan. La matrícula histórica se busca con o sin guiones/espacios.
- **Edición de órdenes:** guardar los trabajos de una orden recibida descartaba el
  emisor, cliente, vehículo, marca y fecha de publicación. Esos snapshots se conservan;
  una selección explícita de otro cliente/vehículo actualiza solo esa selección.
- **IVA equivalente:** `21`, `21.0` y `21.00` creaban grupos distintos y podían sumar
  tres céntimos de IVA en vez de dos sobre tres líneas de 0,03 €. Se canonicalizan las
  representaciones antes de agrupar y redondear. El catálogo acepta la misma representación.
  Se mantienen grupos distintos por tipo y tratamiento fiscal, incluidas las exenciones.
- **Borradores de una versión anterior:** la emisión recalcula y contrasta los importes.
  Si cambia el total por la corrección de redondeo, exige guardar y revisar el borrador
  antes de emitir; no cambia silenciosamente el importe revisado ni reescribe emitidas.
- **Claves de stock:** una clave usada con otro producto, cantidad, documento o motivo
  daba éxito sin aplicar la operación solicitada. Ahora devuelve conflicto. Una repetición
  equivalente, como `5`/`5.000`, conserva el mismo movimiento. Un conflicto durante emisión
  revierte también registro fiscal, número y estado del documento.
- **Conversiones concurrentes:** comprobar y crear en conexiones/transacciones separadas
  producía `UNIQUE constraint failed` entre instancias del backend. Se ejecuta toda la
  conversión en una transacción SQLite y se reutiliza el documento en toda la cadena de
  presupuesto/orden. `stock_affect`, líneas y condiciones se trasladan al destino; stock
  se consume al emitir la factura. Convertir la orden y convertir su presupuesto al mismo
  tiempo no genera dos facturas ni dos salidas de existencias. Una factura emitida no puede
  iniciar ciclos de conversión a presupuestos/órdenes.
- **Rectificación tras transferencia:** se permite corregir la factura del cliente
  original usando la instantánea del vehículo original. No cambia su propietario ni los
  kilómetros actuales. Se prueba una rectificativa parcial y se rechaza emitir el borrador
  rectificativo si entretanto se ha anulado su factura original.

La prueba de rectificativa descubrió además un `IDEmisorFactura` ausente en el bloque
`IDFacturaRectificada`; la corrección se hizo coordinadamente en el módulo fiscal y la
prueba final atraviesa su validación XSD oficial. Esto es validación local, no aceptación AEAT.

## Política de cálculo comprobada

Cantidades/precios/descuentos se procesan con `Decimal`. Se redondea la base de cada línea
a céntimos con `ROUND_HALF_UP`, se suman bases por tipo de IVA y tratamiento fiscal y se
redondea la cuota una vez por grupo. Los casos cubren importes positivos y negativos,
cantidades fraccionarias, descuentos, varios tipos y operaciones exentas.

## Ejecución y evidencia

Entorno: Linux 6.8.0-139-generic x86_64, glibc 2.39, Python 3.13.2, SQLite 3.49.1.

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_integrity_regressions.py -q --tb=short` antes de corregir | 12 fallos reproducidos, salida 1; `integridad-regresiones-antes-2026-09-23.txt`. |
| `.venv/bin/python -m pytest tests/test_validation_money.py tests/test_workflows.py -q --tb=short` | 68 casos superados, salida 0. |
| `.venv/bin/python -m pytest tests/test_integrity_regressions.py -q --tb=short --junitxml=reports/integridad-2026-09-23.xml` | 19 casos superados, salida 0. |
| `.venv/bin/python -m pytest -q --junitxml=reports/integridad-suite-2026-09-23.xml` | 147 casos superados, salida 0; `integridad-suite-2026-09-23.txt` y XML. |

La concurrencia de conversión se ejerce contra cuatro instancias `App` con conexiones
SQLite reales compartiendo una base temporal, además de las regresiones existentes de
emisión concurrente. El lote de importación histórica usa un paquete JSON sintético;
esta comprobación no acredita lectura nativa de un MDB/ACCDB.

## Alcance y límites

Archivos de implementación: `backend/taller/documents.py`, `money.py` y `catalogue.py`.
Regresiones: `tests/test_integrity_regressions.py`. No se modifica el esquema SQLite,
no se recalculan documentos emitidos y no se cambian las barreras de producción.

Este informe acredita los escenarios de integridad descritos y la batería integrada
ejecutada en ese momento. No acredita escritorio Windows, impresora, migración real ni
aceptación fiscal autenticada. La verificación de UX, empaquetado y requisitos restantes
corresponde a sus informes y a la integración final del objetivo completo.
