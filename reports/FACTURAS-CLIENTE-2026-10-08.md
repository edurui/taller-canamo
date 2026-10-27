# Nombre del cliente vinculado en facturas · 08/10/2026

## Causa y corrección

Los históricos importados podían tener `customer_id` válido y un snapshot `customer`
vacío. El enlace usaba correctamente el ID, pero el texto sólo consultaba el nombre
del snapshot y mostraba «Cliente no conservado en el original». El detalle añadía
un párrafo que confundía ausencia de snapshot con ausencia de cliente.

Ahora se muestra el nombre original si existe; cuando falta se muestra el nombre
de la ficha vinculada, identificado como ficha actual. El listado devuelve
`current_customer_name` aprovechando el JOIN ya existente. La búsqueda y el COUNT
usan el mismo criterio, incluido nombre nulo, vacío o compuesto por espacios.
Un nombre original conservado mantiene prioridad, aunque se edite la ficha actual.

El detalle presenta directamente el nombre enlazado sin el párrafo confuso. El mismo
criterio se aplica a Últimas facturas de Inicio y al listado de facturas de un vehículo.
No se cambia `customer_name` original ni el payload, PDF, importes, titularidades
o vínculos. No hay migración, índices, dependencias ni peticiones por cada fila.

## Archivos

- `backend/taller/documents.py`: campo explícito y búsqueda coherente.
- `frontend/documents.tsx`: nombre en listado/detalle y etiqueta de ficha actual.
- `frontend/app.tsx`, `frontend/people.tsx`: consumidores del mismo listado.
- `tests/test_integrity_regressions.py`: cuatro casos nuevos con nombre original
  ausente/nulo/vacío/espacios, cambio de nombre, archivo, búsqueda con acentos y
  `%`, `_`, `\`, y payload original intacto.
- `e2e/historical-review.spec.ts`: navegación desde Inicio/listado/detalle y búsqueda;
  cuatro comprobaciones visuales ampliadas para el nombre y ausencia del aviso.
- `e2e/ownership-rectification.spec.ts`: actualizar la expectativa del texto que
  precisamente se elimina; comprobar nombre original NULL y ficha actual separada.
  Se mantienen las aserciones de originales intactos y rectificación.
- Este informe, estado verificado y relevo. Cambios anteriores conservados.

## Verificación

Sólo datos sintéticos. No se accedió a la base real del taller.

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_integrity_regressions.py -q` | 23 correctas, 1,57 s |
| `.venv/bin/python -m pytest -q` | 712 correctas, 73,56 s |
| `npm run typecheck` | Correcto |
| `npm run typecheck:e2e` | Correcto |
| `npm run build` | Correcto |
| E2E dirigidas: históricos, ausencia de originales y navegación | 21 correctas, 33,0 s, antes de ampliar Inicio/vehículos |
| `npm run test:e2e` | 130 correctas, 199,204 s; cero fallos, omitidas o reintentos |
| `git diff --check` | Correcto |

Las pruebas visuales comprueban claro/oscuro y 1366/390 px, navegación, espacios,
ausencia de desbordamiento y ocho auditorías Axe en detalle/diálogo. Se revisaron
las cuatro capturas del detalle con nombre enlazado y sin el párrafo incorrecto.
El E2E final usa una copia temporal con fuentes/compilación idénticas por SHA-256,
para evitar que un `npm run start` simultáneo regenere `dist` durante la prueba.
Se comprobaron los hashes finales y se eliminó únicamente esa copia temporal después
de conservar los resultados.

La primera suite completa tuvo 129 correctas y una expectativa del antiguo aviso.
Se conserva el fallo y se actualiza esa expectativa al comportamiento solicitado,
añadiendo comprobaciones del nombre original y del actual por separado.
Playwright muestra el warning de precedencia de FORCE_COLOR sobre NO_COLOR.
Evidencia ignorada por Git en `reports/facturas-cliente-2026-10-08/`.

Benchmark posterior, ejecutado tras las suites con
`.venv/bin/python scripts/benchmark_historical_reviews.py`: 5.000 históricos y
28.230 líneas sintéticas, 5 warmups y 60 iteraciones. Apertura mediana/p95
11,076/12,615 ms; página 10 13,199/15,405 ms; pendientes 3,653/4,334 ms;
estimadas 26,994/30,114 ms; búsqueda por número 65,079/71,496 ms; detalle
11,281/13,275 ms. Se conserva `benchmark-5000.json`, sin umbrales temporales en CI
ni afirmar que todas las búsquedas tarden lo mismo. El buscador ahora incluye el
nombre actual cuando falta el original; no se añade una consulta por cliente.

Verificado en Linux/Chromium; Windows/WebView2 no ejecutado en esta corrección.
Sin commit ni push. Reiniciar con Ctrl+C y `npm run start` para cargar también
el campo nuevo del backend; no hace falta reimportar ni modificar la base.
