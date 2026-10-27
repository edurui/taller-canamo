# Agenda, navegación y cabecera · 7 de octubre de 2026

Cambios locales sobre `6be3445`, conservando el trabajo anterior de Clientes,
arranque con npm y presentación de vehículos. No se ha hecho commit ni push.
No se han modificado los datos originales del taller.

## Cambios y causas

- **Mes cuadrado:** las alturas mínimas anteriores producían rectángulos. Cada día
  usa ahora `aspect-ratio: 1`, contenido limitado al cuadrado y adaptación al ancho
  real de la celda. En anchos pequeños se muestran fecha y contador; con espacio,
  también vistas previas. El contador abre el día completo, sin perder eventos.
  Se conservan los eventos de varios días, la recurrencia, el arrastre y el teclado.
- **19:00 frente a 21:00:** `wallDate` crea un portador UTC para operar con la hora
  local de Madrid. Inicio volvía a formatearlo con la zona del navegador, añadiendo
  un segundo desplazamiento. Inicio y Agenda comparten ahora un formateador
  `Intl.DateTimeFormat` que recibe el instante real y fija `Europe/Madrid`.
  La fecha de Inicio también usa Madrid. No se resta un número fijo de horas.
- **Cabecera:** `position: sticky; top: 0`, 80 px en escritorio y 70 px en móvil.
  El desplazamiento y el menú de Configuración reservan esa altura. Se corrigió
  además una regla previa `visibility:hidden` que impedía enfocar «Saltar al
  contenido»; el enlace conserva su ocultación visual fuera de pantalla hasta el foco.
- **Referencias:** patrón común para clientes, vehículos, documentos, artículos y
  proveedores. Se añaden en listados, fichas, documentos recientes, Agenda,
  rectificativas, configuración fiscal, B2B, conciliación de importaciones,
  resumen de stock y catálogo. Se navega por IDs existentes, conservando las
  etiquetas históricas. Un texto sin identidad acreditada no genera un enlace.
  El inventario completo está en [NAVEGACION-ENTIDADES-2026-10-07.md](NAVEGACION-ENTIDADES-2026-10-07.md).
- **Formularios protegidos:** los enlaces respetan la confirmación del editor.
  Agenda, movimientos de almacén y configuración fiscal incorporan protección
  local de sus cambios y bloqueo durante operaciones. La consulta del proveedor
  desde un artículo usa un modal secundario y conserva el formulario del artículo.
- **Avisos:** se conserva la notificación nativa de Windows y su sonido normal del
  sistema, sin bucles ni audio paralelo. La prueba respeta sonido/silencio; el clic
  abre Agenda con la aplicación abierta o en bandeja. La confirmación de entrega
  conserva el grupo exacto presentado: fallos de registro no repiten el sonido en
  cada sondeo ni consumen miembros añadidos o reprogramados durante la operación.
  Errores visibles y sondeo de 20 segundos, sin temporizadores nuevos por fila.
  Detalle y límites en [NOTIFICACIONES-AGENDA-2026-10-07.md](NOTIFICACIONES-AGENDA-2026-10-07.md).

Los controles de selección mantienen su función; no se anidan botones en opciones
o controles. Las rutas son estado React tanto en Tauri como en la previsualización:
se usan botones semánticos y no URLs ficticias. Las referencias admiten Enter y
Espacio, subrayado y foco visible. La búsqueda global conserva su contrato.

## Rendimiento antes/después

Benchmark reproducible de `customers.list`: tres calentamientos y 31 muestras por
caso, conexión nueva de sólo lectura `mode=ro&immutable=1`, `query_only=ON` y sin WAL
activo. Se incluyen SQL, construcción del resultado y cierre; se excluyen HTTP,
render y los PRAGMA de conexión del servicio. Python 3.13.2 / SQLite 3.49.1 / Linux.
Se ejecutó sin suites de pruebas ni compilaciones concurrentes.

El «antes» es el código ya optimizado del commit `6be3445`; esta revisión añade
los IDs necesarios para abrir cada matrícula. No se atribuye a esta revisión la
aceleración del listado conseguida en la tarea anterior.

Datos privados: **1.595 clientes / 1.290 vehículos / 5.133 históricos**. Valores en ms:

| Consulta | Mediana antes | Mediana después | p95 antes | p95 después |
|---|---:|---:|---:|---:|
| Apertura | 3,843 | 3,881 | 4,118 | 4,163 |
| Página índice 10 | 4,711 | 4,793 | 5,073 | 5,031 |
| Nombre parcial | 1,418 | 1,418 | 1,485 | 1,540 |
| Matrícula parcial | 1,352 | 1,343 | 1,441 | 1,401 |
| Sin resultados | 0,827 | 0,827 | 0,895 | 0,984 |

La diferencia mediana de apertura/paginación es +0,038/+0,082 ms. No hay una
degradación material ni se presenta como una mejora de velocidad. COUNT p95 queda
por debajo de 0,81 ms en los cinco casos. La primera página crece de 9.724 a 13.068
bytes JSON por los identificadores de vehículos que ahora consume la interfaz.

Sintético: **15.000 clientes / 30.000 vehículos / 60.000 históricos**:

| Consulta | Mediana antes | Mediana después | p95 antes | p95 después |
|---|---:|---:|---:|---:|
| Apertura | 44,476 | 44,614 | 53,479 | 46,060 |
| Página índice 10 | 46,833 | 47,311 | 49,553 | 50,118 |
| Nombre parcial | 46,787 | 46,608 | 48,599 | 51,512 |
| Matrícula parcial | 11,639 | 11,715 | 13,151 | 13,228 |
| Sin resultados | 4,393 | 4,485 | 4,788 | 4,980 |

La respuesta de primera página ocupa 17.638 bytes con los vehículos enlazables.
No hay umbrales temporales en CI. Se compararon en memoria todos los campos
anteriores, resultados, orden y total; los textos reales de filtros nunca se guardan.

La consulta de matrículas por lote selecciona ahora `customer_id,id,plate` para
los clientes de la página y reconstruye `plates` para compatibilidad. Conserva
tres SELECT por página con resultados y sólo COUNT fuera de rango. EXPLAIN sigue
mostrando `idx_vehicle_owner` para el lote; no se leen documentos ni se añade una
consulta por fila. **No se añaden índices, migraciones o dependencias de JavaScript.**
La única lectura al pulsar una referencia es `documents.get` en movimientos de
almacén, cuyo contrato original sólo conserva el ID y requiere resolver el tipo.

```bash
.venv/bin/python scripts/benchmark_navigation.py \
  --work /tmp/canamo-navigation-benchmark-20261007 \
  --real-data "$HOME/.canamo-access-codex-rehearsal-20261006-b/data" \
  --report reports/usabilidad-2026-10-07/performance.json
```

El script y el JSON conservan tiempos, tamaños, conteos, planes y hashes de código;
no incluyen filas, matrículas, nombres, teléfonos, NIF ni textos reales de búsquedas.

## Verificación conjunta

- `source .venv/bin/activate; python -m pip check`: sin dependencias rotas.
- `python -m pytest tests/test_contacts_search.py tests/test_customers_list.py tests/test_notification_delivery.py -q`:
  50 correctas en la pasada dirigida previa al caso adicional de matrícula vacía.
- `python -m pytest`: **547 correctas, 51,22 s**, incluyendo el contrato final de
  listado (25), búsqueda (10), entrega de avisos (16) e importaciones completas.
- `npm run typecheck`, `npm run typecheck:e2e`, `npm run build`: correctos.
  Build final: JS 396,84 kB / gzip 120,49 kB; CSS 73,43 kB / gzip 15,58 kB.
- Pruebas dirigidas: ocho de navegación; seis de presentación/zonas horarias de
  Agenda y dos adicionales de protección de borradores; dos de cabecera/avisos web.
  El caso fiscal ampliado también pasó tras su última corrección.
- `npm run test:e2e`: **68 correctas, 107,852 s**, sin fallidas, omitidas, flaky ni reintentos.
  Incluye todas las regresiones previas y los 18 nuevos casos sobre el build final.
- 42 celdas medidas en cada ancho 320/390/768/1366: diferencia ancho/alto **0 px**,
  desbordamiento vertical **0 px**. Cuatro auditorías Axe del mes y seis de
  referencias móviles (claro/oscuro), sin infracciones en las pasadas dirigidas.
- Horario 19:00 comprobado en ambos cambios de horario de 2026 con navegador en
  Madrid y Nueva York; fecha de Inicio comprobada cerca de medianoche de Madrid.
- Cabecera visible tras scroll, búsqueda funcional, salto al contenido enfocable
  y contenido sin quedar debajo del header en cuatro tamaños. Capturas finales
  revisadas después de terminar las animaciones reales de cierre de modales.
- Cinco pruebas Rust del adaptador y ledger: correctas. `cargo check` y
  `cargo clippy -- -D warnings` del escritorio completo para target Windows:
  correctos, incluidos `main.rs`, estado, IPC y activación. Recursos Windows
  compilados con herramientas reales extraídas en una carpeta privada.
- `git diff --check`: correcto. Los **26 archivos del ensayo original** coinciden
  byte a byte con su manifiesto anterior; no se copian bases ni PII al repositorio.
- Recorrido de navegador sobre otra copia privada del ensayo: **12 comprobaciones
  correctas**, nueve tablas de dominio idénticas antes/después y cero RPC mutantes
  o peticiones externas. Clientes, vehículos, titulares y facturas abren su ID real.
  Los históricos de este ensayo no conservan `vehicle_id`: se comprobó que no se
  fabrican enlaces de vehículo en sus listados o detalles. No se guardaron DOM,
  capturas, trazas o textos reales; sólo booleanos y conteos.

## Límites y revisión local

La comprobación de tipos Windows no equivale a ejecutar el instalador, WebView2,
notificación o altavoz. **No se ha visto ni escuchado el aviso en Windows real**.
Queda esa comprobación física, documentada con pasos concretos en el informe de
notificaciones. Windows controla permisos, volumen y No molestar. Tras «Salir»
no queda un proceso que reciba clics de notificaciones antiguas; cerrar la ventana
a bandeja conserva los recordatorios activos.

Para abrir la web con la copia local completa y cargar también el backend nuevo,
detener con `Ctrl+C` cualquier previsualización anterior y arrancar de nuevo:

```bash
cd ~/proyectos/personal/taller-canamo
npm run start
```

Abre `http://127.0.0.1:8765` y utiliza la copia persistente privada en
`${XDG_DATA_HOME:-$HOME/.local/share}/taller-canamo-preview/data`. La prueba web no
sustituye el programa instalado de Windows para comprobar sus avisos nativos.
