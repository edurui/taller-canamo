# Informes, exportación portable y almacén

## Resumen operativo

En **Más herramientas → Resumen** puedes elegir fechas inclusivas o consultar todo
el historial. No se limita la consulta a los últimos 24 meses.

- **Facturación:** facturas emitidas e históricas por fecha de factura, incluidas
  rectificativas; se identifican los documentos de prueba. Borradores, anuladas y
  lotes revertidos no se suman como facturación vigente.
- **Cobros:** movimientos reales por fecha de pago y medio, con entradas,
  devoluciones y contrapartidas. Los saldos iniciales documentados y sus ajustes
  aparecen separados: no son entradas ni salidas de caja.
- **Pendiente:** saldo actual de los documentos del período. Las deudas positivas
  y cantidades a devolver aparecen separadas. Una histórica cuyo cobro no está
  acreditado se cuenta como desconocida y no genera una deuda supuesta.
- **Trabajos:** presupuestos y órdenes del período agrupados por su estado actual.
- **Mínimos:** existencias actuales de artículos activos, con referencia, proveedor
  y teléfono. El período elegido no reconstruye el almacén de una fecha pasada.

Este resumen ayuda a gestionar el taller. No sustituye la contabilidad ni las
declaraciones tributarias. Los CSV de cada sección conservan estos mismos criterios.

## Datos para otras herramientas

**Exportación portable completa** genera un ZIP sin cifrar con:

- `data.json`: todas las filas originales, identificadores, relaciones, snapshots,
  líneas, series, cobros, saldos documentados, auditoría y procedencia. Incluye
  borradores, anuladas e importaciones revertidas, identificadas por su estado.
- `schema.json`: descripción de columnas, claves y relaciones.
- `csv/`: vistas UTF-8 con BOM y separador punto y coma. Las cabeceras se conservan
  incluso cuando no hay filas; `document_lines.csv` facilita los conceptos.
- `resources/`: logos, PDFs que ya estuvieran guardados y originales, diagnósticos
  y preparación de importaciones, incluidos los campos no mapeados. No incluye
  las copias desechables `simulation.*` del asistente de importación.
- `manifest.json` y `LEEME.txt`: formato, versión de esquema, recuentos, exclusiones,
  unidades y SHA-256 de cada archivo.

Los importes `*_cents` son céntimos enteros; cantidades y precios conservan sus
decimales exactos. JSON distingue cero, `null` y texto vacío. Las columnas JSON
originales de SQLite se conservan como cadenas. Los originales binarios B2B se
representan en base64 con su SHA-256 para recuperar exactamente los bytes.

El CSV protege con apóstrofo las cadenas que podrían ejecutarse como fórmulas o
perder ceros iniciales en una hoja de cálculo. `data.json` conserva el texto
original. Los CSV de facturas incluyen su payload y snapshots completos.

El paquete no contiene certificados, claves, contraseñas, `secure/`, motores de
asistencia ni rutas privadas de configuración. Contiene datos del taller: guarda
el archivo en una ubicación bajo tu control. No se envía a ningún servicio.

La exportación portable permite consultar o adaptar datos en otro programa; no
reactiva numeración, colas fiscales ni otro ordenador. Para recuperar la aplicación
o trasladar el único puesto activo utiliza [Copias y traslado](COPIAS-TRASLADO.md).

El transporte portable escribe JSON y CSV por filas y recursos por bloques de 1 MiB.
Admite hasta 8 GiB descomprimidos, 50.000 archivos y un manifiesto de 16 MiB. Si no
cabe el conjunto completo se informa del error y no se trunca ni se presenta una
exportación parcial como completa. Los CSV por período permiten extraer conjuntos
acotados. El escritorio comprueba tamaño y SHA-256 durante el guardado.

La salida temporal se elimina al guardar, cancelar o fallar la descarga. Su permiso
caduca tras una hora sin uso; las salidas huérfanas se limpian al volver a trabajar.
Esto no elimina las copias operativas `.canamo` conservadas en Copias y traslado.

## Catálogo, proveedores y movimientos

El catálogo y el inventario siguen siendo opcionales. Puedes facturar conceptos
manuales sin proveedor ni existencias. Para cada artículo puedes guardar referencia,
precios, IVA, proveedor y mínimo; un servicio puede desactivar el control de stock.

En **Existencias** elige entrada, salida, devolución al almacén o recuento. Escribe
un motivo. El recuento registra la diferencia entre la cantidad vista y la contada;
si otra acción ha cambiado el stock, se pide revisar el dato actualizado. Repetir
el mismo envío no duplica el movimiento.

Archivar oculta un artículo o proveedor sin borrar su historial. Para archivar un
artículo o desactivar su stock debe quedar a cero mediante un movimiento justificado.
**Mostrar archivados → Restaurar** lo vuelve a mostrar. Si una anulación devuelve
un artículo archivado al almacén, se reactiva para que esa existencia sea visible.

Convertir presupuesto → orden → factura conserva las líneas y el vínculo de
origen. Volver a convertir el mismo origen devuelve la misma factura. El control
de stock evita un segundo descuento dentro de esa familia de documentos.
