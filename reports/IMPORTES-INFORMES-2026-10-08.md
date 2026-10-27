# Importes coherentes y resumen de facturas · 08/10/2026

## Causa

Los históricos incompletos conservan `documents.total_cents = NULL`; sus importes
calculados viven en una revisión separada. El listado principal de Facturas ya
mostraba esa revisión, pero Inicio, la ficha del cliente, la del vehículo y la
búsqueda de trabajos seguían mostrando únicamente el original. Por eso faltaban
cantidades que sí podían consultarse en otro lugar.

Informes sumaba exclusivamente facturas con base, IVA y total originales completos.
Al consultar una importación parcial, devolvía cero y meses vacíos, aunque hubiera
estimaciones disponibles. Ese criterio sigue siendo adecuado para su desglose fiscal,
pero no bastaba para el resumen de consulta solicitado.

## Solución y semántica

- Las cuatro superficies reutilizan `HistoricalTotal`, igual que Facturas. Primero
  se presenta el total original, incluido cero/negativo. Si falta, la revisión lleva
  la etiqueta «Estimado» o «Contrastado con original». Pendientes sin importe muestran
  «No consta». No hay llamadas adicionales por fila ni recálculos desde React.
- `reports` añade `billing_overview` y `overview_months`. Se suma una sola cantidad
  por factura: original presente, o revisión vigente completa en estado estimado/
  contrastado. Nunca se suman versiones anteriores ni se sobrescriben documentos.
- Cada agregado devuelve `count`, `amount_count`, `unknown_count`, `total_cents` y
  pares `original_count/cents`, `verified_count/cents`, `estimated_count/cents`.
  El mensual añade `month`. Si hay facturas pero ninguna tiene importe, el total es
  `null`. Si no hay facturas, es cero. Los grupos sin facturas aportan cero al total,
  pero la tabla los representa con raya; un cero conocido se muestra como importe.
- El rango es inclusivo por fecha de factura. Sólo entran emitidas e históricas
  activas; borradores, anuladas y lotes revertidos quedan fuera. Las facturas sin
  fecha se cuentan en un aviso independiente y no reciben un mes inventado.
- Resumen presenta el total disponible y su cobertura, avisa si es parcial y separa
  originales, contrastados y estimados por mes. El desglose fiscal original sigue
  accesible en una sección desplegable con su exportación anterior.
- `data.export(kind='billing_overview')` exporta el mismo desglose mensual en céntimos
  enteros y con cabeceras estables. Un total desconocido queda vacío. Los contratos
  `billing`, `months`, CSV originales y portable conservan su semántica.
- Si falla un cambio de período, se ocultan las cifras anteriores y se ofrece
  reintento. Aplicar el mismo período permite refrescar revisiones. Las respuestas
  obsoletas se descartan mediante el patrón existente de `useLoad`.
- Tablas desplazables accesibles con teclado y tarjetas legibles en pantallas
  estrechas. Corregido también el mínimo intrínseco de la tabla del cliente en móvil.

Los cobros, deudas, rectificaciones, PDF, snapshots y fiscalidad siguen basándose
en sus datos documentados. Las revisiones no generan pagos ni deuda supuesta.
Esta ampliación del resumen de consulta sustituye la limitación del informe previo
sobre estimaciones en Informes; no cambia el desglose fiscal original.

## SQL y rendimiento

Una agregación mensual con `LEFT JOIN` a la proyección actual; a partir de sus
pequeños resultados se calcula el total del período. La cola de estimaciones se
consume antes de iniciar el snapshot de lectura, como en `documents.list`. Con la
cola vacía no hay escrituras. No se procesa el payload completo de cada factura ni
se consulta cada revisión por separado.

Se comparó el CTE inline con `AS MATERIALIZED`. SQLite expandía repetidamente las
expresiones CASE/JSON para cada suma. Materializar únicamente mes, origen e importes
redujo ese coste, con resultados idénticos. Se reutilizan `idx_docs_kind_date` y la
clave primaria de `historical_review_current(document_id)`. Sin nueva migración,
índice, dependencia ni cambio del esquema.

Plan seleccionado resumido:

```text
MATERIALIZE amounts
SEARCH d USING INDEX idx_docs_kind_date (kind=? AND issue_date>? AND issue_date<?)
SEARCH h USING INDEX sqlite_autoindex_historical_review_current_1 (document_id=?) LEFT-JOIN
SCAN amounts
USE TEMP B-TREE FOR GROUP BY
```

No hay subconsulta correlacionada en el agregado nuevo. La agrupación por mes sigue
usando una estructura temporal, justificada por la consulta. SQLite medido: 3.49.1;
`AS MATERIALIZED` necesita ≥3.35 (el proyecto empaqueta Python 3.13 en Windows).

Reproducción exclusivamente sintética:

```bash
.venv/bin/python scripts/benchmark_reporting_amounts.py
```

Cinco calentamientos y 30 iteraciones, 36 meses, seis líneas salvo los pendientes:

| Escenario | Informe completo mediana/p95 | Agregado final mediana/p95 | Agregado inline mediana/p95 |
| --- | ---: | ---: | ---: |
| 5.000 facturas / 28.230 líneas | 24,321 / 27,064 ms | 11,243 / 12,181 ms | 40,340 / 41,922 ms |
| 30.000 facturas / 169.410 líneas | 251,353 / 270,251 ms | 110,639 / 126,781 ms | 295,282 / 310,967 ms |

El agregado mejora aproximadamente 3,6× y 2,7× en mediana. Es una comparación de
las dos implementaciones del agregado nuevo, no una afirmación de que el informe
antiguo que omitía estimaciones hiciera el mismo trabajo. El informe completo incluye
caja, saldos, stock y el resto de apartados; no se afirma que 30.000 facturas se
resuman por debajo de 100 ms.

La inicialización sintética con cola pendiente costó 424,505 y 2.651,440 ms una vez;
en el uso normal esa materialización ocurre en migración/importación. Las lecturas
posteriores usan la proyección. Comprobadas integridad, claves foráneas, originales
NULL y ausencia de pagos/registros fiscales. Sin umbrales de hardware en CI.

También se ejecutó `.venv/bin/python scripts/benchmark_historical_reviews.py`
después de la suite completa, con 5.000 históricos, 28.230 líneas, cinco calentamientos
y 60 iteraciones. Mediana/p95: primera página 10,391/11,660 ms; página 10
12,507/14,820 ms; pendientes 3,296/3,901 ms; estimadas 24,152/25,536 ms; búsqueda
por número 60,398/63,235 ms; detalle 6,732/8,036 ms. No se añade una consulta por fila
para presentar los importes. Evidencia: `benchmark-lists-5000.json` en el directorio
de esta corrección.

## Archivos de esta corrección

- `backend/taller/reporting.py`: agregados, CSV y aviso.
- `frontend/app.tsx`, `people.tsx`, `assistant.tsx`: reutilización de `HistoricalTotal`.
- `frontend/reports.tsx`, `web/style.css`: resumen, procedencia, errores y presentación.
- `tests/test_reporting_historical_amounts.py`: 17 casos nuevos, incluidos límites,
  negativos/cero, desconocidos, versiones, reset, importación/reversión real sintética,
  exportaciones y estructura del plan sin N+1.
- `tests/test_historical_reviews.py`: igualdad de todos los campos anteriores más
  comprobación explícita del cambio estimado→contrastado en el nuevo resumen.
- `e2e/invoice-amount-surfaces.spec.ts`: cuatro pruebas en ambas apariencias y
  1366/390 px; Inicio, cliente, vehículo, trabajos, filtros y navegación.
- `e2e/report-amounts.spec.ts`: seis pruebas del resumen/CSV, procedencia, fechas,
  ausencia vs cero, revisión, fallo/reintento, teclado y accesibilidad.
- `e2e/operations.spec.ts`: nombre actualizado de la tarjeta; mismas cifras esperadas.
- `scripts/benchmark_reporting_amounts.py`, documentación de informes, estado y relevo.

## Verificación

Sólo datos sintéticos y bases temporales. No se han abierto ni modificado datos reales.

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pip check` | Sin incompatibilidades |
| `.venv/bin/python -m pytest -q` | 729 correctas, 58,35 s |
| `npm run typecheck` | Correcto, también ejecutado por build |
| `npm run typecheck:e2e` | Correcto |
| `npm run build` | Correcto |
| `npm run test:e2e -- e2e/invoice-amount-surfaces.spec.ts` | 4 correctas, 5,6 s |
| `npm run test:e2e -- e2e/report-amounts.spec.ts` | 6 correctas, 6,9 s |
| `npm run test:e2e` | 140 correctas, 192,601 s; sin fallos, omitidas ni reintentos |
| `git diff --check` | Correcto |

Cuatro auditorías Axe nuevas para las superficies y cuatro para Informes, sin
violaciones finales. Se comprueban claro/oscuro, 1366/390 px, ausencia de overflow
global y desplazamiento con teclado de las tablas. Revisadas las capturas sintéticas;
las tarjetas del resumen conservan etiquetas, cifras y ayudas en filas distintas.

Durante las pruebas se corrigieron: tablas desplazables sin foco de teclado,
mes/recuento pegados, tarjetas comprimidas en móvil y datos anteriores tras error.
Una ejecución dirigida intermedia agotó el tiempo porque el helper de navegación
comprobaba el menú antes de que terminase el arranque; ahora espera el sidebar.
Se conservan los fallos y capturas intermedios, sin ocultar warnings. Playwright
advierte que FORCE_COLOR tiene precedencia sobre NO_COLOR.

Evidencia local ignorada por Git en `reports/importes-informes-2026-10-08/`,
`reports/importes-superficies-2026-10-08/` y `reports/reporting-amounts-2026-10-08/`.
La suite de navegador usa copia temporal aislada de fuentes y dist, idénticos por
SHA-256, para que un arranque del usuario no regenere el bundle durante la ejecución.
Verificados los 1.912 archivos al acabar y eliminada únicamente esa copia temporal
después de conservar los resultados completos.

Verificado en Linux/Chromium. No se ha ejecutado Windows/WebView2 ni reconstruido el
instalador en esta corrección. Cambios anteriores conservados; sin commit ni push.
Para cargar el backend y el frontend nuevos, detener el preview con Ctrl+C y ejecutar
`npm run start` desde el repositorio. No hace falta reimportar los históricos.
