# Facturas históricas: estimación y revisión · 08/10/2026

## Resultado y criterio

Los históricos incompletos conservan íntegros sus datos importados. Se añade una
estimación versionada, separada y etiquetada. El listado permite filtrar **Estimada**,
**Pendiente de revisión** y **Contrastada con original**. El detalle permite ajustar
el porcentaje con motivo, contrastar explícitamente los importes contra el documento
original y restablecer la propuesta automática sin borrar el historial.

El defecto no era únicamente un porcentaje de IVA ausente: el importe de línea
conservado no acredita por sí mismo su clasificación fiscal, y existen cabeceras sin
líneas, importes ausentes, fechas inciertas y discrepancias. Aplicar un porcentaje
directamente a los originales habría convertido hipótesis en datos supuestamente fiables.
La implementación no hace esa conversión y no modifica datos reales para probarla.

La política automática v1:

- Supone explícitamente que `amount_raw` representa el importe anterior al IVA.
- Suma decimales exactos, redondea la base una sola vez a céntimos con HALF_UP,
  calcula/redondea el IVA sobre esa base y obtiene el total como base más IVA.
- Sugiere 16 % entre 01/01/2003 y 30/06/2010, 18 % entre 01/07/2010 y 31/08/2012
  y 21 % desde 01/09/2012. Antes de 2003 exige un tipo explícito.
- Fecha desconocida/conflictiva, líneas ausentes, importe ausente/no válido,
  contradicción entre cantidad × precio e importe, tipos/regímenes originales
  incompatibles o importes conservados contradictorios dejan todos los valores
  estimados en NULL y el estado pendiente. No usa cero ni una suma parcial.
- Cantidad × precio comprueba coherencia; nunca sustituye un importe ausente.
- Un ajuste manual conserva «Estimada». «Contrastada con original» exige casilla
  explícita, evidencia textual y ausencia de incidencias.

Los períodos son una orientación del tipo general, no prueba del devengo, régimen
o porcentaje de cada factura. Referencias: [Ley 26/2009, art. 79](https://www.boe.es/buscar/doc.php?id=BOE-A-2009-20765),
[análisis oficial del IVA 2010](https://www.hacienda.gob.es/Documentacion/Publico/Tributos/Estadisticas/IVA/2010/Analisis_estadistico_IVA_2010.pdf),
[RDL 20/2012, art. 23](https://www.boe.es/buscar/doc.php?id=BOE-A-2012-9364) y
[criterio de devengo de la AEAT](https://sede.agenciatributaria.gob.es/Sede/iva/calculo-iva-repercutido-clientes/que-momento-tengo-que-repercutir-iva.html).

## Arquitectura, contrato y conservación

`DocumentEditor → api/RPC → HistoricalReviews → SQLite`. Cálculo puro con Decimal,
límites de coeficiente/exponente, líneas e importes; sin dependencias nuevas ni red.

Acciones nuevas:

| Acción | Entrada |
| --- | --- |
| `historical.review_preview` | `identifier`, `tax_rate?`; sólo lectura |
| `historical.review_save` | `identifier`, `expected_version`, `tax_rate`, `reason`, `verified?`, `evidence?` |
| `historical.review_reset` | `identifier`, `expected_version`, `reason` |

Devuelven `state`, `version`, `tax_rate`, `base_cents`, `tax_cents`, `total_cents`,
`issues[{code,message}]`, `reason`, `evidence` y `policy`; guardar/restablecer incluyen
el historial completo de revisiones con acción/fecha. Porcentaje decimal como texto,
importes como céntimos enteros o NULL. `documents.get` incluye revisión e historial;
`documents.list` incluye sólo la revisión actual y admite `review_state` opcional.
El contrato anterior y los importes originales mantienen su significado.

Migración nueva v9; no se modifican migraciones publicadas:

- `historical_review_versions`: versiones consecutivas e inalterables.
- `historical_review_current`: proyección de la última versión, actualizada por trigger.
- `historical_review_pending`: cola técnica para materializar los nuevos históricos.
- `idx_historical_review_state(state,document_id)`: filtro real de revisión. Las claves
  primarias resuelven detalle, proyección e historial; no se añaden otros índices.

El hook Python se ejecuta dentro de la transacción de migración. SQLite sólo usa SQL
en sus triggers y funciona con `trusted_schema=OFF` al validar copias. Se crea copia
previa al migrar una base anterior. Versiones/propuestas ya almacenadas no se recalculan
silenciosamente al cambiar código. Las lecturas normales sólo comprueban la cola vacía;
no escriben ni vuelven a calcular cada factura. El listado usa un JOIN con la proyección,
sin consulta adicional por fila. Dos conexiones no pueden sobrescribir una revisión
obsoleta ni materializar simultáneamente una versión inicial duplicada.

Los originales de `documents`, payloads, cantidades, precios y `amount_raw` no se
reescriben. Tampoco cambian PDF, pagos, saldos, informes, conciliación, exportación de
originales ni fiscalidad. Una revisión no habilita rectificar ni cobrar un histórico
sin total original. Copias y portable preservan las nuevas tablas por separado.
La exportación portable conserva también la cola pendiente sin resolverla ni modificarla.

Las simulaciones de importación antiguas se migran antes de reanudarse. Una sustitución
crea otro documento con propuesta independiente; no hereda el contraste del anterior.
Revertir preserva ambos documentos y sus revisiones. Se corrigió una reversión encadenada:
la validación compara contra el snapshot activo que se refrescó al restaurar un lote
previo; mantiene el rechazo de actividad posterior. Los documentos ya revertidos no
impiden archivar su contacto importado. Documentos activos y eventos sí siguen protegidos.

## Interfaz

Previsualización debounced 180 ms y descarte inmediato de respuestas obsoletas.
Guardar bloqueado durante cálculo/guardado o conflicto; errores visibles y borrador
conservado. Cerrar con cambios requiere confirmación; Escape recupera el foco.
Cambiar el porcentaje desmarca el contraste. Restablecer exige motivo.

Se corrigieron los tres defectos aportados: icono del aviso centrado verticalmente,
separación entre Preparar mensaje y barra protegida, y nombre actual del cliente
enlazado con espacio antes del vehículo. Si no hay snapshot, se identifica como ficha
actual; no se presenta como nombre conservado en el original. Estilos locales y
paneles adaptables, sin cambios globales de carga.

## Verificación

Datos exclusivamente sintéticos y temporales. No se abrió, copió ni modificó una base
real para estas pruebas. Fuentes y `dist` idénticos por SHA-256 en copia temporal aislada
para E2E, evitando la recompilación simultánea del usuario; mismas dependencias y fixtures.

| Comando | Resultado final |
| --- | --- |
| `.venv/bin/python -m pip check` | Sin dependencias rotas |
| `.venv/bin/python -m pytest tests/test_historical_reviews.py tests/test_historical_review_lifecycle.py tests/test_partial_history.py tests/test_access_adversarial.py tests/test_access_imports.py -q` | 116 correctas, 23,42 s; antes de añadir la regresión portable |
| `.venv/bin/python -m pytest tests/test_reporting.py tests/test_historical_review_lifecycle.py -q` | 25 correctas, 18,47 s |
| `.venv/bin/python -m pytest -q` | 708 correctas, 158,22 s |
| `npm run typecheck` | Correcto |
| `npm run typecheck:e2e` | Correcto |
| `npm run build` | Correcto; 44 módulos, 1,70 s |
| E2E dirigidas de histórico + ausencia original | 10 correctas; dos casos móviles corregidos y repetidos en el lote visual |
| E2E visuales finales | 4 correctas, 12,2 s |
| `npm run test:e2e` (copia aislada idéntica por hashes) | 129 correctas, 234,219 s; 0 fallos, omitidas o reintentos |
| `git diff --check` | Correcto |

77 nuevas pruebas Python y 11 E2E. Python cubre límites de fechas, decimales exactos,
redondeo, nulos/ceros, contradicciones, validación, concurrencia, auditabilidad, filtros,
paginación, invariantes fiscales/financieros, migración desde v8, fallo atómico, colas,
lecturas sin escrituras, copias, exportación, importación/simulación/sustitución/reversión.
E2E cubre cálculo, clasificación y filtro; ajuste y contraste; persistencia tras reinicio;
respuestas antiguas; conflictos; evidencia obligatoria; restablecimiento e historial;
teclado, confirmación de descarte y foco. Cuatro combinaciones claro/oscuro × 1366/390 px
comprueban alineación, separación, ausencia de desbordamiento y accesibilidad Axe WCAG
2.2 AA en detalle y diálogo: ocho auditorías sin infracciones, ocho capturas revisadas.

Evidencia local ignorada por Git: `reports/historical-review-2026-10-08/`, con logs,
capturas, JSON de resultados, artefactos de fallos y hashes. Los fallos intermedios
no se borran: comentario SQL final rechazado por el parser de migraciones; fixture
sintético sin `invoice_type`; selectores de labels que incluían el asterisco requerido;
auditoría durante transición de opacidad; menú móvil consultado antes del montaje;
reversión encadenada; exportación portable que rechazaba tablas nuevas (4 pytest y
1 E2E de la primera suite completa). Se corrigió código o sincronización/contrato del
test según la causa; se conserva la protección de exportación y las aserciones existentes.

Playwright avisa de que `NO_COLOR` se ignora porque existe `FORCE_COLOR`; no afecta a
las aserciones. No se ocultan warnings ni fallos intermedios.

## Rendimiento

Medición reproducible: `.venv/bin/python scripts/benchmark_historical_reviews.py`.
Base temporal nueva con históricos y líneas sintéticos; calentamiento de cinco
iteraciones, 60 mediciones, mediana/p95/máximo. No impone umbrales dependientes del
hardware a CI. En 5.000 históricos / 28.230 líneas: 4.705 estimados y 295 pendientes.
La materialización inicial de propuestas y primera lista tarda 428,184 ms, una sola
vez; no representa el tiempo de una migración completa ni se repite por filtro.

| Operación, 5.000 históricos | Mediana ms | p95 ms | Máximo ms |
| --- | ---: | ---: | ---: |
| Apertura/lista | 11,418 | 12,926 | 13,941 |
| Página 10 | 13,141 | 14,653 | 15,311 |
| Pendientes de revisión | 3,351 | 3,916 | 4,519 |
| Estimadas | 25,433 | 27,197 | 31,209 |
| Filtro por número sintético | 38,280 | 40,104 | 40,374 |
| Detalle con historial | 7,748 | 8,653 | 8,868 |

El EXPLAIN de las consultas reales capturadas al filtrar pendientes usa
`idx_historical_review_state`, covering en COUNT, y busca los documentos por su clave
primaria. La proyección no añade subconsultas correlacionadas por revisión. Se mantienen
las subconsultas originales de saldo/fiscalidad y ordenaciones temporales del listado
de facturas; no se refactorizan dentro de esta tarea. Son mediciones locales de backend,
sin afirmar una mejora antes/después ni extrapolar a Windows. Se verifican integridad,
claves foráneas, totales originales NULL y ausencia de pagos/registros fiscales inventados.
JSON sanitizado con tiempos, conteos y planes en `benchmark-5000.json`.

Escalabilidad: `.venv/bin/python scripts/benchmark_historical_reviews.py --documents 15000`.
15.000 históricos / 84.702 líneas, 14.117 estimados y 883 pendientes; materialización
inicial y primera lista 1.281,657 ms, una sola vez.

| Operación, 15.000 históricos | Mediana ms | p95 ms | Máximo ms |
| --- | ---: | ---: | ---: |
| Apertura/lista | 25,888 | 27,621 | 28,427 |
| Página 10 | 46,409 | 48,627 | 51,089 |
| Pendientes de revisión | 7,473 | 8,276 | 9,214 |
| Estimadas | 71,602 | 75,445 | 77,065 |
| Filtro por número sintético | 108,045 | 111,342 | 111,765 |
| Detalle con historial | 20,740 | 23,515 | 25,867 |

El filtro substring existente de facturas supera 100 ms en el escenario de 15.000;
se deja registrado como límite, sin atribuir velocidad instantánea a todas las consultas.
No se introducen índices indiscriminados ni se amplía esta revisión a una reescritura
del buscador de facturas. El índice de estados también se utiliza en esta escala.
Ambos benchmarks se ejecutaron tras terminar pytest/E2E. Los documentos usan un único
cliente y no contienen pagos ni registros fiscales: no representan todas las cargas
posibles de un taller. `benchmark-15000.json` conserva tiempos, conteos y planes.

## Archivos y límites

Backend: `historical_reviews.py`, `migrations/v0009_historical_reviews.py`, registro en
`migrations/__init__.py` y `app.py`, integración `documents.py`, `access_writer.py` y
tablas explícitas/aviso portable en `reporting.py`. Frontend: `historical-review.tsx`,
`documents.tsx`, estilos locales de `web/style.css`. Pruebas nuevas:
`test_historical_reviews.py`, `test_historical_review_lifecycle.py`,
`e2e/historical-review.spec.ts`; actualización del test de migración v7 en
`test_partial_history.py` para seleccionar versiones explícitas y comprobar todas
las migraciones posteriores. Benchmark, este informe, documentación de importación,
exportación, estado y relevo. Cambios previos ajenos conservados; sin commit ni push.

Verificado Linux/Chromium, Python y SQLite reales con datos sintéticos. No se ejecutó
Windows/WebView2 ni se reconstruyó el instalador de esta función. El contraste documental
de cada factura requiere su original; esta tarea no resuelve automáticamente esa evidencia
ni cambia la condición de edición de desarrollo para facturación operativa.

Para cargar fuentes y backend nuevos: detener la previsualización anterior con Ctrl+C,
ejecutar `npm run start` desde el repositorio y abrir Facturas. La base local anterior se
migra con copia previa; no hace falta repetir la importación de Access.
