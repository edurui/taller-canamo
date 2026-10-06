# Históricos parcialmente desconocidos · 06/10/2026

Implementado y verificado con datos exclusivamente sintéticos en SQLite temporal.
No se han modificado bases operativas ni emitido/remitido facturas reales.

## Contrato y conservación

La migración 8 permite `NULL` en fecha, base, IVA y total únicamente en documentos
`historical`/`import_reverted`. Conserva las restricciones de documentos nuevos,
los índices, referencias y disparadores de inmutabilidad. El arranque conserva
una copia previa de una base anterior. La prueba desde versión 7 confirma snapshot,
cobro vinculado y claves foráneas sin alteraciones.

Detalle y listado exponen disponibilidad (`amounts_state`: known/partial/unknown;
`date_state`: known/unknown/conflict), procedencia y capacidad de rectificar.
`0` conocido y `NULL` desconocido permanecen distintos. El contrato parcial del
importador conserva importes decimales originales mediante `amount_raw`; esos
importes no acreditan por sí solos base, IVA o total fiscal.

La interfaz y el PDF muestran «No consta» y la etiqueta de importe original sin
clasificación fiscal. Un histórico sin líneas se abre e imprime como tal. Las
fechas contradictorias permanecen sin fecha confirmada; no se elige hoy ni una
fecha arbitraria. También se corrigió el acceso a `.slice()` sobre fecha nula que
la primera ejecución E2E reprodujo al abrir el documento.

Sin total conocido no se crean saldos, cobros ni ajustes de saldo; no se presenta
una deuda. La rectificación exige fecha e importes fiscales completos, también
por llamadas directas a guardar/publicar. El IVA avanzado no muestra S1 como
valor por defecto si su clasificación no consta.

La facturación agregada solo suma documentos con base, IVA y total conocidos.
Los incompletos del período se cuentan aparte. Los históricos sin fecha se
cuentan sin asignarlos a un período. La exportación completa incluye documentos
sin fecha y mantiene nulos en JSON; una exportación filtrada por fechas no les
inventa ubicación temporal. Listados e historial continúan mostrando esos registros.

## Verificación dirigida

- `.venv/bin/python -m pytest tests/test_partial_history.py tests/test_historical_payments.py tests/test_pdf_layout.py tests/test_reporting.py tests/test_fiscal_workflow.py -q`: **74 correctas**, 16,15 s. Incluye 13 nuevas regresiones parciales. Log: `partial-history-2026-10-06/pytest.log`.
- `npm run build`: correcto, incluye `tsc --noEmit`; Vite final 996 ms.
- `npm run typecheck:e2e`: correcto.
- `npx playwright test e2e/partial-history.spec.ts --reporter=list`: **1 correcta**, 8,0 s; controles nulos, importe original exacto, acciones protegidas y opciones avanzadas. Axe sin infracciones en ese recorrido. Se repite con directorio de salida aislado para conservar la captura sin interferir con la suite general; log: `partial-history-2026-10-06/e2e.log`.
- PDF A4 de una página con datos sintéticos renderizado con Poppler e inspeccionado: texto legible, totales y tabla sin solapamientos, ausencias explícitas. Archivos `partial-history-2026-10-06/historico-incompleto-sintetico.pdf` y `.png`.

Un intento E2E posterior falló por un localizador ambiguo entre el `option` nativo
y el texto del combobox. Se precisó el rol/nombre sin alterar el comportamiento
ni desactivar la comprobación; log conservado en `e2e-before-selector-fix.log`.
La primera prueba también corrigió el nombre de acción del propio harness
(`bootstrap`). La ejecución correcta indicada arriba corresponde al estado final.

Esta batería es dirigida. La consolidación de toda la suite, la validación del
importador real, el escritorio Windows y la impresión física se documentan por
separado; este informe no les atribuye resultados.

## Revisión final de precisión del PDF

La etiqueta de precio conserva los decimales exactos hasta 16 posiciones en
formato ordinario. Para exponentes extremos usa la representación decimal
compacta exacta; no expande una entrada como `1E-1000000000` a mil millones de
caracteres ni la redondea a cero. Se añadieron tres regresiones (exponentes enorme
positivo/negativo y nueve decimales). Batería posterior
`python -m pytest tests/test_partial_history.py tests/test_pdf_layout.py -q`:
**28 correctas**, 4,00 s. Son ahora 16 pruebas en `test_partial_history.py`.

La repetición E2E con `--output reports/partial-history-2026-10-06/e2e-artifacts`
terminó con **1 correcta**, 7,9 s. Se conserva una copia estable de su captura en
`partial-history-2026-10-06/pantalla-historico-sintetico.png`.
