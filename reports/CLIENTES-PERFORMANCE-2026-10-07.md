# Rendimiento de Clientes · 7 de octubre de 2026

## Alcance y punto de partida

Revisión sobre `388cb2ac000823b5af6c8a13402abc27defd3def`, con el árbol de trabajo
limpio al empezar. Se ejecutaron `git status --short` y `git diff` antes de editar.
El alcance es `CustomersPage` y `customers.list`; `customers.search`, importador,
facturación, históricos, PDF, agenda, stock y fiscalidad no cambian.

La medición del origen privado utiliza exclusivamente una conexión SQLite
`mode=ro&immutable=1`, `query_only=ON`, y rechaza un WAL no vacío sin intentar
checkpoint. No instancia `Database` ni `App` sobre el original. Las pruebas de
interfaz usan una copia privada porque el arranque ordinario de la aplicación
puede escribir configuración, auditoría o copias. No se guardan consultas con
nombres/matrículas, respuestas privadas, capturas ni trazas del taller.

## Causa comprobada

La consulta anterior devolvía todo `customers`, agregaba matrículas por cliente,
calculaba la última visita y ordenaba mediante una función Python de normalización:

```sql
SELECT c.*,
  (SELECT group_concat(v.plate, ', ') FROM vehicles v
   WHERE v.customer_id=c.id AND v.archived=0) AS plates,
  (SELECT max(d.issue_date) FROM documents d
   WHERE d.customer_id=c.id AND d.kind='invoice') AS last_visit
FROM customers c
WHERE c.archived=? /* más filtro opcional */
ORDER BY normalized(c.name)
LIMIT 50 OFFSET ?;
```

Ningún consumidor de `customers.list` utiliza `last_visit`. En el origen real,
EXPLAIN muestra que la subconsulta utiliza `idx_docs_kind_date` por `kind`, y
repite la búsqueda de factura por cliente. La proyección ancha y las agregaciones
se evalúan para candidatos de la ordenación, incluidos clientes que finalmente
no se muestran. Paginar no limitaba todo ese trabajo a 50 fichas.

La pantalla además sustituía la tabla completa por `Loading` en cada recarga,
aunque `useLoad` conservaba el resultado anterior. Esto añadía un parpadeo visible
al coste del backend.

## Solución aplicada

1. Contrato explícito de **siete campos**: `id`, `name`, `city`, `phone`, `tax_id`,
   `legacy_code`, `plates`. El sexto se conserva porque el asistente de importación
   lo muestra al vincular una identidad. Para editar se obtiene la ficha completa
   mediante `customers.get`.
2. Eliminada toda lectura de `documents` del listado y el cálculo de `last_visit`.
3. Primero se seleccionan los clientes de la página. Una única consulta agrega
   los vehículos activos de esos identificadores mediante `idx_vehicle_owner`:

   ```sql
   SELECT customer_id, group_concat(plate, ', ') AS plates
   FROM vehicles
   WHERE customer_id IN (?, /* hasta 50 identificadores */ ?) AND archived=0
   GROUP BY customer_id;
   ```

4. El filtro de matrícula precalcula sus propietarios con `IN (SELECT customer_id
   FROM vehicles WHERE plate_normalized LIKE ? ESCAPE '\')`, en vez de ejecutar
   `EXISTS` correlacionado para cada cliente. No cambia qué vehículos coinciden.
5. Se conserva `COUNT(*)` separado y el total del paginador. Si el total no alcanza
   el desplazamiento solicitado, no se repiten el filtro ni la consulta de matrículas.
6. El frontend mantiene la tabla durante recargas. Una revisión monotónica de la
   petición y la limpieza del efecto descartan respuestas antiguas, incluso A→B→A.
   Los resultados conservados se identifican como anteriores y sus filas/paginador
   quedan deshabilitados mientras no correspondan a la petición actual.
7. Primera carga vacía con `Loading`, región `aria-busy`, estado anunciado y errores
   visibles con reintento. Sin debounce, temporizadores de espera artificiales,
   caché de entidades ni cambios globales en `useLoad`.

## Índices, alternativas y semántica

No se añaden ni eliminan índices y no hay migración v9. Se conserva el esquema v8.

| Índice o alternativa | Decisión y evidencia |
|---|---|
| `idx_vehicle_owner(customer_id)` | Utilizado por la consulta única de matrículas de la página |
| `idx_docs_customer(customer_id,issue_date DESC)` | Sigue disponible para otras rutas; el listado ya no consulta documentos |
| Índice nuevo solo en `customers.archived` | No justificado por el coste medido del COUNT frente al total; no añadir coste de escritura por defecto |
| `idx_customer_search(search_text)` | No resuelve un LIKE con comodín inicial; se conserva sin atribuirle esa capacidad |
| Índice de expresión `(archived,normalized(name))` | Ensayado solo en copia; evita ordenar, pero es incompatible con la validación protegida actual de copias |
| Columna persistida normalizada e índice compuesto | Ensayada en copia; exigiría mantener otro dato derivado en todas las escrituras y migrar. No necesaria para los objetivos medidos |
| Subconsulta paginada frente a placas por lote | Ambas reducen trabajo; se elige el lote por simplicidad y límite explícito de 50 propietarios |
| FTS/trigramas | No necesarios para los tamaños y tiempos comprobados |

La limitación de índices con UDF bajo `trusted_schema=OFF` está documentada por
[SQLite, Function Flags](https://www.sqlite.org/c3ref/c_deterministic.html).
`deterministic=True` por sí solo no declara una función `SQLITE_INNOCUOUS`.
Se reprodujo el rechazo en una base sintética; no se relajó la validación de copias.
Las restricciones de expresiones están en
[SQLite, Indexes On Expressions](https://www.sqlite.org/expridx.html).

Se mantiene exactamente `ORDER BY normalized(c.name)`: tildes, mayúsculas y
espacios se tratan igual que antes. No se añade un desempate diferente ni se
sustituye el orden por `NOCASE`. La ordenación temporal sigue existiendo y su
coste se incluye en las mediciones, en lugar de ocultarlo mediante caché.

Se conservan también dos particularidades anteriores: las matrículas archivadas
pueden hacer coincidir a un cliente, aunque no se muestran entre sus vehículos
activos; una consulta formada solo por símbolos cuya matrícula normalizada queda
vacía coincide con propietarios de vehículos. Los escapes SQL del texto siguen
siendo literales. Ambas conductas están probadas y no se modifican dentro de esta
optimización. El autocompletado rápido mantiene su contrato propio.

## Medición reproducible

Entorno: Linux x86_64, Python 3.13.2, SQLite 3.49.1, Node 22.22.2, npm 10.9.7,
16 CPU lógicas visibles. Sin suites/builds concurrentes durante los tiempos finales.

Se ejecuta el método `Contacts.list_customers` del commit anterior, congelado y
verificado por hash, y el método actual mediante el mismo adaptador de lectura.
Cada petición abre y cierra su conexión. Se incluyen SQL, creación de diccionarios
y cierre; se excluyen los PRAGMA de `Database.connect`, transporte y renderizado.
No se fuerza una caché fría del sistema operativo. Tres calentamientos por caso;
15 muestras antes y 31 después para páginas/consultas completas; 7 antes y 15 después
para parciales. p95 por rango más próximo: con 7/15 muestras coincide con el máximo.
Los textos privados se eligen en memoria; las filas, totales, orden y matrículas se
comparan sin serializar información privada en el informe.

Los experimentos iniciales SQL directos usaron otro límite de temporización y ciclo
de conexión. Sirven para elegir alternativas, **no** se mezclan con esta comparación
final ni se atribuye sin evidencia la diferencia entre sus tiempos absolutos.

Todas las cifras de las tablas siguientes están en **milisegundos**. El máximo
anterior coincide con su p95 por el número de muestras. El índice de página 10 es
la undécima página visible, con desplazamiento de 500 clientes.

### Ensayo real: 1.595 clientes, 1.290 vehículos, 5.133 históricos

| Caso | Coincidencias | Mediana antes | p95 antes | Mediana después | p95 después | Máximo después | Factor mediano |
|---|---:|---:|---:|---:|---:|---:|---:|
| Apertura (p0) | 1595 | 1.163,111 | 1.249,564 | 5,926 | 12,830 | 21,989 | 196.27× |
| Página índice 10, offset 500 | 1595 | 4.135,003 | 4.466,107 | 6,346 | 6,884 | 6,987 | 651.59× |
| Nombre parcial | 16 | 44,758 | 59,503 | 1,934 | 2,198 | 2,198 | 23.14× |
| Matrícula parcial | 1 | 7,679 | 8,253 | 1,949 | 2,660 | 2,660 | 3.94× |
| Sin resultados | 0 | 3,289 | 3,573 | 1,385 | 1,710 | 1,794 | 2.37× |
| Nombre completo (adicional) | 4 | 4,957 | 5,553 | 3,099 | 3,801 | 3,893 | 1.60× |
| Matrícula completa (adicional) | 1 | 7,791 | 9,946 | 2,151 | 2,826 | 5,877 | 3.62× |

### Sintético: 15.000 clientes, 30.000 vehículos, 60.000 históricos

| Caso | Coincidencias | Mediana antes | p95 antes | Mediana después | p95 después | Máximo después | Factor mediano |
|---|---:|---:|---:|---:|---:|---:|---:|
| Apertura (p0) | 15000 | 4.363,282 | 4.725,315 | 53,116 | 59,325 | 59,901 | 82.15× |
| Página índice 10, offset 500 | 15000 | 31.220,965 | 32.090,077 | 61,455 | 71,044 | 74,436 | 508.03× |
| Nombre parcial | 15000 | 4.488,099 | 4.724,904 | 56,317 | 68,555 | 68,555 | 79.69× |
| Matrícula parcial | 10 | 167,450 | 180,399 | 17,063 | 18,048 | 18,048 | 9.81× |
| Sin resultados | 0 | 30,964 | 38,818 | 7,789 | 9,528 | 9,605 | 3.98× |
| Nombre completo (adicional) | 1 | 44,969 | 51,838 | 15,429 | 17,968 | 18,722 | 2.91× |
| Matrícula completa (adicional) | 1 | 77,302 | 83,150 | 17,655 | 20,016 | 20,305 | 4.38× |

El filtro parcial amplio del sintético coincide con los 15.000 clientes: no se ha
medido únicamente una coincidencia fácil. En el real, apertura y paginación reducen
su mediana un **99,49 % y 99,85 %**, respectivamente. La primera respuesta real pasa
de **29.295 a 9.687 bytes** en el array JSON, un 66,93 % menos.

El COUNT de apertura tiene mediana de **0,731 ms real / 2,342 ms sintético**. Se probó
además `COUNT(*) OVER()` integrado en la selección de página, alternando ambas formas,
con 2 calentamientos y 7 muestras por forma. Medianas de la petición completa:
**5,079 ms separado / 5,960 ms ventana** en real y **49,592 / 55,630 ms** en sintético.
La ventana no mejora este caso y no devuelve el total si se pide una página fuera
de rango sin añadir otra ruta. Se conserva el COUNT separado.

### EXPLAIN y trabajo realmente eliminado

Antes, apertura: `SCAN c`, subconsulta correlacionada de matrículas con
`idx_vehicle_owner`, subconsulta correlacionada de documentos con
`idx_docs_kind_date (kind=?)`, y `USE TEMP B-TREE FOR ORDER BY`.

Después: COUNT/selección sobre `customers`; filtro de matrícula con una subconsulta
`LIST SUBQUERY` independiente; agregación de la página con
`SEARCH vehicles USING INDEX idx_vehicle_owner (customer_id=?)`. No hay lectura de
`documents`. Se conserva la ordenación temporal de los nombres normalizados.
Los planes completos sanitizados están en los JSON locales enlazados por ruta abajo.

Las matrículas procesadas para representar la primera página bajan de **198 a 38**
en real y de **642 a 100** en sintético. Para offset 500: **921 a 44** y **4.704 a 100**.
Normalizar nombres sigue recorriendo 1.595/15.000 nombres cuando no hay filtro;
es una limitación explícita incluida en los tiempos, no una operación oculta.

### Comando de reproducción

Usar un directorio temporal privado nuevo. La variante baseline de la página 10
sintética tardó unos 31 segundos **por petición**: repetir todas sus muestras lleva
varios minutos. No ejecutar suites/builds en paralelo con un benchmark comparable.

```bash
.venv/bin/python scripts/benchmark_customers.py \
  --work /tmp/canamo-clientes-benchmark-nuevo \
  --real-data "$HOME/.canamo-access-codex-rehearsal-20261006-b/data" \
  --baseline-ref 388cb2ac000823b5af6c8a13402abc27defd3def \
  --pages 0,10 --filters exact,partial --samples 15 --warmup 3 \
  --variants baseline --service-after \
  --report reports/clientes-performance-repeticion.json
```

Evidencia de esta ejecución, fuera de Git:
`reports/clientes-performance-2026-10-06/baseline-final.json`, `after-final.json`,
`partial-filters-final.json`, `summary.json`, `count-window.json` y
`baseline-candidates.json`. El nombre del directorio refleja el inicio del encargo;
las mediciones finalizaron el 07/10 en Europe/Madrid. Las variantes de índices sólo
se crearon en copias privadas; el script rechaza reutilizar un baseline con otro ref.
La revisión final añadió validación de dimensiones, esquema, integridad relacional y
manifiesto/hash del fixture sintético antes de reutilizarlo: un cambio de tamaños o una
siembra incompleta exige otro directorio de trabajo, sin sobrescribir el anterior.
Este control de preparación se añadió después de medir, sin cambiar el código de
listado medido ni el contenido de sus fixtures/evidencia.

## Verificación de producto y privacidad

Ejecutado con `.venv` activado para Python. Todos los comandos siguientes terminaron
con código 0. Las verificaciones de navegador usan el build final, incluido el ajuste
que reserva espacio al estado de recarga y evita desplazar el buscador o la tabla.

| Comando | Resultado |
|---|---|
| `python -m pip check` | Sin dependencias rotas |
| `python -m pytest tests/test_contacts_search.py -q` | 10 passed, 0,79 s |
| `python -m pytest tests/test_contacts_search.py tests/test_customers_list.py tests/test_access_adversarial.py::test_changes_in_live_customer_block_replacement_and_full_rollback -q` | 35 passed, 4,49 s; incluye las 24 pruebas nuevas del listado |
| `python -m pytest` | 520 passed, 152,25 s |
| `npm run typecheck` | Correcto, 6,816 s de proceso |
| `npm run typecheck:e2e` | Correcto, 3,169 s de proceso |
| `npm run build` | Correcto, 10,111 s de proceso |
| `npx playwright test e2e/customers-list.spec.ts --output=reports/customers-performance-verification/artifacts` | 5 passed, 13,4 s Playwright; 15,594 s de proceso |
| `npm run test:e2e` | **46 passed**, 130,126 s Playwright; 0 fallos, omitidas o flaky, sin reintentos |
| Validación del fixture del benchmark + `py_compile` | 10 comprobaciones correctas; fixture grande existente aceptado sin cambiar SQLite |
| `git diff --check` | Correcto |

Las pruebas de listado comprueban campos exactos, total, paginación, nombres normalizados,
empates, archivados, ausencia/variedad de vehículos, placas completas y sin duplicados,
filtros por nombre/teléfono/matrícula y `%`, `_`, `\`, alta/edición/archivo/restauración,
traspaso de vehículo y contrato inalterado del buscador rápido. Comparación diferencial
con la consulta anterior para 19 consultas, ambos estados de archivo y dos páginas.
El autorizador SQLite impide leer documentos o columnas no consumidas; trazas y EXPLAIN
comprueban el lote de hasta 50 propietarios y el índice existente. No hay umbrales
cronometrados en CI. La prueba adversarial de importación conserva sus aserciones y
obtiene la ficha completa con `customers.get` antes de editar.

Los cinco E2E nuevos cubren respuestas invertidas, A→B→A, paginación/archivados,
bloqueo de filas anteriores, errores iniciales/de recarga y reintento. Cuatro auditorías
Axe sin violaciones, a 1024 px claro y 320 px oscuro con letra grande, antes y durante
recarga. Capturas sintéticas revisadas: sin cortes/solapamientos nuevos; la geometría
comprueba que el borde superior de la tabla y el ancho del buscador permanecen iguales.
No se modificó globalmente `useLoad`.

El recorrido local sobre la copia privada completó **21 comprobaciones**: entrada,
diez cambios de página, nombre/matrícula parcial, borrado, filtros rápidos, cero
coincidencias, ficha y regreso, archivados y vuelta a activos. Se compara lo visible
con las respuestas en memoria y se verifica que no se desmonta la tabla al filtrar.
La automatización no guarda capturas, DOM, trazas ni mensajes con datos personales.
La apertura completa medida por ese recorrido fue 324 ms, y los pasos posteriores de
página 71–100 ms: incluyen clic, esperas del navegador y aserciones, por lo que **no**
son comparables a los tiempos backend de las tablas ni una medición aislada de render.
El ensayo real no tiene clientes archivados ni varios vehículos activos de un mismo
cliente; esos casos positivos se verifican con datos sintéticos, sin inventarlos en el
ensayo ni probar escrituras sobre datos reales.

Comprobación final: los **23 archivos** de la carpeta original conservan sus hashes;
la SQLite original y la copia pasan `integrity_check` y `foreign_key_check`.
Las tablas completas de clientes, vehículos y documentos de la copia siguen idénticas
al origen. El arranque sólo se ha realizado sobre la copia privada. No se guarda SQLite
ni se copia información privada al repositorio. La revisión automatizada de adiciones
contra 5.120 valores completos privados de al menos cinco caracteres no detectó
coincidencias; se complementa con revisión del diff y de archivos de Git.

Logs y evidencia agregada local:
`reports/clientes-performance-2026-10-06/{pip-check,contacts-search,targeted,pytest-full,e2e-final}.log`,
`e2e-final-results.json`, `real-ui.json`, `real-integrity.json`, `benchmark-fixture-guard.json`, más
`reports/customers-performance-verification/` para typechecks, build, cinco E2E,
capturas sintéticas y auditorías. Son artefactos ignorados; este informe y las fuentes
reproducibles sí forman parte del cambio revisable.

## Archivos y estado de entrega

| Archivo | Cambio |
|---|---|
| `backend/taller/contacts.py` | Proyección mínima, elimina documentos, filtros y matrículas por lote |
| `frontend/people.tsx` | Carga localizada, resultados anteriores identificados, control de carreras y errores |
| `tests/test_customers_list.py` | 24 pruebas funcionales, diferenciales y estructurales |
| `tests/test_access_adversarial.py` | Obtener ficha completa antes de editar; mismas aserciones |
| `e2e/customers-list.spec.ts` | Cinco E2E, accesibilidad y estabilidad visual |
| `scripts/benchmark_customers.py` | Benchmark reproducible, privado y sanitizado; variantes y planes |
| `reports/CLIENTES-PERFORMANCE-2026-10-07.md` | Este informe |
| `docs/ESTADO-VERIFICADO.md` | Estado actual y distinción de evidencia histórica |
| `CONTINUAR.md` | Instrucciones para revisar la versión actual con la copia privada |

Rama `main`, HEAD `388cb2ac000823b5af6c8a13402abc27defd3def`: cinco archivos modificados
y cuatro nuevos. Sin staging, commit ni push. No cambian migraciones, esquema v8,
importador, `customers.search`, facturación, históricos, PDFs, agenda, stock ni fiscalidad.

Para abrir la versión comprobada:

```bash
cd ~/proyectos/personal/taller-canamo
source .venv/bin/activate
python scripts/run_preview.py --data /tmp/canamo-clientes-preview-20261007/data
```

La copia temporal está preparada; puede desaparecer si el sistema limpia `/tmp`.
El origen permanece en `$HOME/.canamo-access-codex-rehearsal-20261006-b/data`.
No arrancar pruebas de escritura sobre ese original. El preview normal necesita poder
escribir ajustes/copias, razón por la que se ha utilizado la copia incluso para el
recorrido de consulta.

## Límites de lo verificado

- Tiempos locales, con calentamiento y muestras finitas; no promesa de latencia idéntica
  en todo hardware, caché fría o millones de registros.
- Se conserva la ordenación temporal y la búsqueda substring. Sus costes están medidos;
  no se añadió infraestructura que el tamaño comprobado no necesita.
- No hay migración nueva: no corresponde afirmar un upgrade v8→v9 ni un rollback v9.
  La base real v8 se lee sin cambios y la suite completa cubre las migraciones existentes.
- No se tocaron Rust/Tauri, puente IPC ni empaquetado. No se recompiló ni se comprobó
  un nuevo binario nativo o Windows en esta tarea. El preview y los E2E verifican las
  fuentes finales; las comprobaciones Tauri anteriores pertenecen al commit de partida.
