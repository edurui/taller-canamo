# Navegación de referencias entre entidades — 7 de octubre de 2026

Auditoría e implementación local con pruebas sintéticas y un ensayo posterior de lectura sobre una nueva copia privada de los datos importados. Los originales y la instalación persistente del usuario no se abrieron ni modificaron. No se incluyen identificadores, nombres ni capturas de personas reales. El informe describe las superficies de navegación; la verificación conjunta de agenda, cabecera y avisos se registra en el informe de usabilidad de esta entrega.

## Patrón común

`frontend/entity-navigation.tsx` centraliza las referencias a cliente, vehículo, documento, artículo y proveedor. Usa botones nativos porque las rutas de Tauri y de la previsualización son estado React, sin inventar URLs. Enter y Espacio funcionan con la semántica del navegador. Cada referencia detiene la propagación hacia su fila y llama a la navegación global sin `force`; se mantiene la confirmación del editor con cambios pendientes. Un identificador ausente deja texto normal. Una etiqueta antigua vacía con ID real usa «Consultar» y el tipo de entidad, evitando botones sin nombre accesible.

Se conserva la etiqueta original de cada snapshot y se navega por el identificador almacenado, aunque cambien el nombre, la matrícula o el titular. Las fichas archivadas siguen siendo consultables por su identidad. No se busca ninguna entidad por el texto visible ni se hacen consultas por fila.

## Inventario de superficies y contratos

| Superficie | Referencia / destino | Evidencia del contrato y tratamiento |
| --- | --- | --- |
| Clientes, lista | Nombre → cliente; cada matrícula → vehículo | `customers.list.id`; nueva lista mínima `vehicles[{id,plate}]`, obtenida por lote de la página. La antigua cadena `plates` se conserva. Resultados anteriores en recarga mantienen todos sus botones deshabilitados. |
| Cliente, ficha | Tarjetas de vehículo y su historial | El selector de tarjeta conserva su función de filtrar; el botón existente «Historial y titular» abre `vehicles.id`, sin anidar botones. Facturas por `documents.list.id`; matrícula por `vehicle_id`. |
| Vehículos, lista | Matrícula → vehículo; titular → cliente | `vehicles.page` devuelve `v.*`, incluido `customer_id`, y el nombre unido a clientes. |
| Vehículo, ficha | Titular actual y anteriores → cliente | `vehicles.get.customer_id` y `owners[].customer_id`. Se conservan fechas y motivos; no se deduce identidad de los nombres. |
| Vehículo, facturas | Documento, cliente histórico y matrícula histórica | `documents.list` ya devuelve los tres identificadores y las etiquetas de snapshot. |
| Facturas / presupuestos / órdenes, lista | Número, cliente y matrícula | Una referencia a cliente o vehículo no dispara la apertura de la fila de documento. El documento conserva su `kind` de lista. |
| Editor de documento | Cliente, vehículo y artículo de cada línea | IDs del documento y `lines[].product_id`. Se conserva el nombre/matrícula visible del snapshot. Si no existe nombre original, se ofrece por separado la consulta de la ficha actual. Navegación deshabilitada durante operaciones del editor. |
| Rectificativas vinculadas | Cada documento rectificativo → editor | `active_rectifications[].id/full_number`, siempre de la familia de facturas. No hay lectura adicional. |
| Inicio, documentos recientes | Número, cliente y matrícula → sus fichas | Integrado por el agente de Inicio con el mismo helper y contratos de documentos. |
| Inicio / Agenda, citas | Cliente y vehículo del evento | Integrado por el agente de Agenda. Las referencias se separan del control que abre la cita; no hay controles anidados. |
| VERI*FACTU | Fila y detalle de registro → factura | `fiscal.records.document_id`, unido a documentos. No se usa el UUID del registro fiscal como ID del documento. Bloqueadas durante operaciones; una confirmación protege configuración, archivo de certificado y contraseña aún no guardados. |
| Factura electrónica B2B | Factura preparada, seleccionada o conservada → factura local | `b2b.list/get.document_id`; las recibidas sin documento local quedan como texto y mantienen su botón propio de detalle B2B. La factura seleccionada permite consultar su cliente mediante `documents.list.customer_id`. |
| Importación, conciliación | Número histórico → factura importada | Se usa `import.reconcile.items[].target_id` existente, sólo presente cuando se resolvió el destino histórico. Orígenes excluidos, claves de staging y objetos sin destino no producen referencias ficticias. |
| Resumen, stock mínimo | Artículo y proveedor → ficha | `reporting.low_stock` selecciona `p.*` y conserva `id/supplier_id`; no requiere ampliar el backend. Los demás paneles son agregados, no entidades individuales. |
| Catálogo | Nombre de artículo → ficha; proveedor → ficha | Listas completas existentes. La entrada por ID incluye archivados y abre una vez el modal de esa identidad; muestra error si no existe. |
| Artículo, formulario | Proveedor seleccionado → consulta de ficha | Modal de sólo lectura con el proveedor ya cargado; permite volver sin perder ningún campo del artículo. No navega fuera del formulario. |
| Almacén, movimientos | Documento vinculado → editor de su tipo real | La lista sólo tiene `document_id`. Al pulsar se hace una única lectura `documents.get` para conocer `kind`. Errores visibles. Cantidad o motivo escritos requieren confirmación antes de salir; cancelar conserva ambos. |
| Proveedores | Nombre → ficha | Identidad de `suppliers.list`; entrada por ID admite archivados y no depende de nombres únicos. |
| Búsqueda global e historial | Selección / documento | La búsqueda global ya abre una ficha por IDs devueltos por su RPC. `assistant.HistoryResults` ya abre el documento por `item.id`; no muestra nombres o matrículas como referencias independientes. |

Los controles de selección (opciones de cliente, vehículo, proveedor o catálogo) conservan su semántica de selección. Los campos de edición libre, motivos, conceptos manuales, tablas de mapeo, originales JSON y resúmenes estadísticos no se convierten en enlaces por coincidencias de texto. `origin_id` no se muestra como referencia con tipo supuesto: el contrato no aporta el tipo del origen ni se presenta actualmente una etiqueta individual del mismo en el editor.

## Rendimiento y conservación

La ampliación de `customers.list` sustituye la agregación de matrículas por una lectura de `customer_id,id,plate` de los mismos propietarios de la página, mediante `idx_vehicle_owner`. Mantiene tres SELECT para una página con resultados y sólo COUNT para una página fuera de rango. No lee documentos, notas ni otros campos extensos; respeta filtros, archivados, orden y paginación. La representación anterior de `plates` se reconstruye conservando su orden.

Los tests de contrato comparan los campos anteriores con la consulta previa y verifican por separado IDs/matrículas, omisión de vehículos archivados, lote limitado a la página e índice de consulta. No se ha ejecutado un nuevo benchmark temporal ni se atribuyen aquí las medianas de sesiones anteriores a esta modificación.

## Verificación

- `npm run typecheck`: correcto tras integrar las props de Settings y las rutas de artículo/proveedor.
- `npm run typecheck:e2e`: correcto.
- `.venv/bin/python -m pytest tests/test_customers_list.py -q`: **25 pasadas**, 1,36 s. Incluye conservación exacta del valor agregado de una matrícula antigua vacía.
- `npx playwright test e2e/entity-navigation.spec.ts --reporter=list --output=reports/usabilidad-2026-10-07/navigation-artifacts`: **8 pasadas**, 9,7 s, antes de la última ampliación del guard fiscal y de la etiqueta vacía. Comprueba IDs con nombres repetidos, archivados, snapshots renombrados, Enter/Espacio, propagación de filas, guardar/reabrir y confirmaciones de documentos/almacén. La regresión de etiqueta vacía se añadió al primer caso de la suite para la verificación conjunta final.
- Sobre el build final `index-B0RYgGX9.js`, `npx playwright test e2e/entity-navigation.spec.ts --grep 'registros fiscales y B2B' --reporter=list --output=reports/usabilidad-2026-10-07/navigation-fiscal-final-artifacts`: **1 pasada**, 4,4 s. Comprueba volver desde la referencia de fila y desde el detalle conservando productor, contraseña ficticia y archivo sintético; salir tras confirmar abre la factura. Cero llamadas a guardar certificado o enviar registros.
- **6 auditorías Axe, 0 violaciones** (Clientes, Vehículo y Editor a 320 px, en claro y oscuro). Se revisaron visualmente las seis capturas: referencias legibles, editor en una columna y tablas con su desplazamiento interno habitual, sin desbordamiento de página.
- El primer pase se conserva en `navigation-first-e2e.log` y `navigation-first-artifacts`: cuatro localizadores nuevos necesitaban ajustarse a los nombres accesibles reales (`Volver` y campos requeridos) y a esperar el montaje de la barra lateral antes de abrir el menú móvil. Se corrigieron los tests, sin modificar aplicación, aserciones de datos ni Axe.
- `git diff --check`: correcto al revisar los cambios.

Artefactos locales ignorados en `reports/usabilidad-2026-10-07/`: log de navegación, trazas en fallos y capturas exclusivamente sintéticas. No se han ejecutado ni declarado pruebas físicas de Tauri para este cambio de interfaz.

## Ensayo sobre copia privada de datos importados

Se creó una nueva carpeta temporal privada, con permisos 0700, a partir de la copia de ensayo previamente preparada. Se arrancó el build final en loopback y se cerró al terminar. El arnés local mantiene los nombres e IDs únicamente en memoria; no toma capturas ni trazas, no imprime DOM, selectores, respuestas o mensajes de error que puedan incluir datos personales. Bloquea solicitudes externas y RPC que no pertenezcan a una lista explícita de lectura y cálculo local.

**12 comprobaciones correctas**: referencias de matrículas en Clientes, titular de la lista Vehículos, tarjeta de vehículo del cliente, titular actual y titular histórico, referencia de cliente de factura, apertura del documento histórico y referencia de cliente en el editor. Se comprobó la correspondencia exacta del ID solicitado por cada destino. Se compararon hashes en memoria antes y después de las nueve tablas de dominio usadas por estas entidades: sin cambios. Hubo **0 solicitudes mutantes o externas**.

La copia tiene 1.595 clientes, 1.290 vehículos y 5.133 documentos históricos. Ninguno de estos históricos conserva `vehicle_id`; se verificó expresamente que sus celdas y editores no presentan enlaces ficticios de vehículo. El primer intento del arnés suponía indebidamente ese vínculo para escoger la muestra y terminó antes de abrir la interfaz. Se corrigió la selección de muestra para verificar vehículos y documentos por separado, respetando la información realmente conservada, sin tocar código ni datos.

Resultado sanitizado: `reports/usabilidad-2026-10-07/navigation-real-ui.json`; primer intento preservado con sufijo `navigation-real-first-ui`. Los archivos sólo contienen booleanos, conteos, nombres técnicos de comprobaciones y etapa de ejecución. La carpeta privada no se incorpora al repositorio.
