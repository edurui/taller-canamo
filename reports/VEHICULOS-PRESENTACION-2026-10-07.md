# Presentación y búsqueda de vehículos · 7 de octubre de 2026

## Punto de partida y alcance

Repositorio `taller-canamo`, HEAD `6be3445`. Se leyeron AGENTS, estado, contexto y
criterios; se revisaron status y diff. Se conservan sin descartar los cambios previos
para `npm run start`, su documentación y el informe de arranque.

El encargo cubre la ficha del vehículo, su listado, las tarjetas de vehículo de la
ficha de cliente y el filtro de vehículos. No se modifican importador, esquema,
facturación, PDF, históricos, lógica/contrato de búsqueda rápida de clientes ni `CustomersPage`.

## Causas y correcciones

- **Paneles unidos:** las tres secciones de detalle eran hermanas sin contenedor que
  separase sus bordes. Un contenedor local usa grid con gap de 24 px; los apartados de
  titularidad separan su contenido 12 px. El texto largo puede envolver sin desbordar.
- **Descripción invisible:** los 1.290 vehículos importados tienen marca y modelo
  separados vacíos, pero 1.244 conservan la descripción original en `kind`, procedente
  de «Tipo de Vehiculo» de Access. Las 1.290 filas coinciden con su valor raw original.
  La UI sólo imprimía `make` y `model`. Ahora utiliza marca/modelo si existen, luego la
  descripción íntegra de `kind`, y finalmente «Vehículo sin descripción». Se aplica a
  ficha, listado y tarjeta del cliente. No se infieren ni separan marcas/modelos, no
  hay backfill, ni hace falta reimportar o editar los datos del taller.
- **Identificador técnico:** el motivo automático `Importación: <UUID>` se presenta
  como «Alta desde importación». Sólo se reconoce ese formato completo; otros motivos
  y notas manuales (incluidos saltos de línea) se muestran completos. El UUID, el motivo
  original, el estado importado y la procedencia siguen en la base para auditoría.
- **Búsqueda:** `vehicles.page` y `vehicles.list` incluyen `kind` al final de la cadena
  de texto buscable. Mantienen escapes literales, tildes, matrícula, marca/modelo,
  titular, orden, límites y paginación. Añadirlo al final conserva incluso consultas
  anteriores que cruzan modelo y nombre de titular; hay regresión automatizada.
- **Contraste en selección del buscador:** la primera batería completa observó contraste
  de 4,19:1 durante la animación de entrada de una opción activa clara. Se refuerza sólo el color
  de ese texto en selección/hover con el token `--text` sobre `--brand-soft`, adaptado
  a claro/oscuro; la lógica y las aserciones de accesibilidad se mantienen. Las auditorías
  del test de interfaz esperan a que terminen las animaciones finitas reales antes de
  medir el estado estable: sin sleeps, desactivar animaciones, excluir nodos ni ignorar
  violaciones. Esto evita tomar colores compuestos transitorios también en el calendario,
  cuyo código y colores de producción no cambian.
- **Contador:** el listado muestra el total real del paginador, sustituyendo el mensaje
  obsoleto «Hasta 300 coincidencias» de la antigua ruta sin paginar.

El frontend deriva el texto de campos que ya recibe: no añade llamadas HTTP, consultas
por fila, dependencias, memoización innecesaria ni cambios en los tokens globales o cargadores compartidos.
No se añaden índices ni migraciones. Referencias aplicadas: skill local
`vercel-react-best-practices` y
[Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)
para estados vacíos, texto largo, semántica y accesibilidad.

## Rendimiento local medido

SQLite original del ensayo usado exclusivamente en `mode=ro&immutable=1`, con WAL
vacío comprobado, `query_only=ON` y función de normalización real. Se ejecuta la clase
Contacts anterior congelada y la final sobre el mismo origen/adaptador. Cada petición
abre/cierra su conexión; se incluyen diccionarios y SQL. Se excluyen PRAGMA de conexión
de producción, transporte y render. Sin suites concurrentes durante el benchmark.
Python 3.13.2, SQLite 3.49.1, Linux x86_64. Tres calentamientos y 31 muestras por caso;
p95 por rango más próximo. Consultas e IDs se seleccionan en memoria y no se guardan.

Dataset: **1.595 clientes, 1.290 vehículos, 5.133 documentos históricos**.
Todas las cifras están en milisegundos.

| Caso | Mediana antes | p95 antes | Mediana después | p95 después |
|---|---:|---:|---:|---:|
| Vehículos: primera página | 1,654 | 1,722 | 1,759 | 2,103 |
| Vehículos: página índice 10 | 2,511 | 2,725 | 2,707 | 2,960 |
| Filtro parcial de matrícula | 6,472 | 6,671 | 9,169 | 10,019 |
| Filtro de titular | 6,575 | 6,893 | 9,117 | 10,117 |
| Filtro de descripción importada | 6,906 | 7,651 | 9,016 | 10,342 |
| Selector de vehículos: descripción | 3,586 | 4,061 | 4,767 | 5,034 |
| Ficha del vehículo | 0,559 | 0,600 | 0,569 | 0,595 |
| Clientes: primera página | 3,802 | 4,521 | 3,950 | 4,504 |

Los seis casos de comportamiento previo comparados conservan íntegros filas, orden y
total. La muestra de descripción pasa de cero a cuatro coincidencias en ambos endpoints:
es una corrección funcional, no una comparación de resultados iguales. El texto adicional
cuesta alrededor de 2,5–2,7 ms en filtros; el mayor p95 final es 10,342 ms. No se afirma
una aceleración de esos filtros. Ficha y Clientes mantienen tiempos equivalentes; no hay
umbrales dependientes del hardware en los tests.

Evidencia sanitizada local ignorada: `reports/vehicle-presentation-2026-10-07/performance-before.json`
y `performance-after.json`. Sus hashes y conteos confirman que el original no cambió.

## Verificación

- `python -m pip check`: sin requisitos rotos.
- `python -m pytest tests/test_vehicle_description.py tests/test_contacts_search.py -q`:
  **22 correctas, 0,74 s**, incluidas 12 nuevas de descripción/importación/búsqueda.
- `python -m pytest`: **532 correctas, 51,55 s**.
- Recorrido sobre copia privada: **8 comprobaciones correctas**, incluidas descripción
  en tres superficies, búsqueda por modelo importado, motivo legible sin UUID, separación
  a 1024/320 px y comparación íntegra del vehículo/historial antes y después.

- `npm run typecheck`: correcto; `npm run build` vuelve a ejecutarlo antes de Vite.
- `npm run typecheck:e2e`: correcto después de la última modificación del helper de auditoría.
- `npm run build`: correcto sobre CSS/fuentes finales (3,351 s de proceso).
- `npx playwright test e2e/vehicle-presentation.spec.ts --output=reports/vehicle-presentation-2026-10-07/ui-artifacts`:
  **4 correctas**, 7,0 s de Playwright; 13 auditorías Axe sin violaciones. Separación de
  paneles 24 px en las cuatro combinaciones 1024/320 y claro/oscuro; capturas revisadas,
  incluidos textos largos y ancho de columna legible en tabla móvil.
- `npx playwright test e2e/interface-polish.spec.ts --grep "letra persistente" --output=reports/vehicle-presentation-2026-10-07/search-contrast-artifacts`:
  **2 correctas**, 6,3 s; diez auditorías Axe sin violaciones. Contraste final de selección
  13,44:1 claro y 9,92:1 oscuro; calendario sin modificar 4,98:1 y 7,70:1 en estado estable.
- `npm run test:e2e`: **50 correctas, 86,416 s**, cero fallidas, omitidas o flaky;
  configuración sin reintentos. Incluye de nuevo las cuatro pruebas nuevas y las dos
  afectadas por la sincronización de la auditoría, sobre el build final.
- `git diff --check`: correcto.

Los E2E nuevos importan una base sintética mediante las APIs reales; comprueban precedencia
marca/modelo, descripción combinada, datos ausentes, texto largo, búsqueda, contador,
notas manuales completas, UUID técnico sólo interno, tarjetas y geometría. No usan
respuestas simuladas para aparentar que los datos se han recuperado. La suite backend
prueba importación Access sintética, preservación del raw y estado importado al editar,
escapes `%`, `_`, barra inversa, tildes, búsqueda previa cruzando modelo/titular y
paginación/archivo/propietarios sin duplicados. El buscador rápido conserva sus tests.

Los intentos anteriores y sus fallos se conservan como evidencia local: navegación de
móvil del test corregida para localizar el diálogo activo; columna de descripción
ampliada antes del cierre visual; auditoría durante animaciones sincronizada antes
de repetir la batería completa. No se eliminan aserciones ni se rebaja Axe.

## Privacidad, integridad y archivos

Los 26 archivos del origen conservan sus hashes del inicio de esta revisión. Original y
copia privada pasan integridad SQLite y claves foráneas. Se comparan íntegramente las
tablas customers, vehicles, vehicle_owners, documents e import_records: la consulta de
interfaz no altera descripciones, propietarios ni evidencia importada. No se han usado
los datos originales para probar escrituras; los ensayos de edición usan fixtures
sintéticos. La aplicación de desarrollo habitual sigue abriéndose con `npm run start`.

Revisión del diff y escaneo de adiciones contra 5.264 valores privados completos de
al menos cinco caracteres: cero coincidencias. Sin bases, originales Access, certificados
ni datos privados trackeados/staged. Sin staging, commit ni push.

| Archivo de este cambio | Finalidad |
|---|---|
| `frontend/people.tsx` | Descripción visible en tres superficies, razón legible, contador real y contenedor de paneles |
| `web/style.css` | Separación, texto largo/columna móvil y contraste de opción de búsqueda seleccionada |
| `backend/taller/contacts.py` | Incluir descripción en el filtro de dos APIs, sin consultas adicionales |
| `tests/test_vehicle_description.py` | Doce pruebas de datos importados, búsqueda y conservación |
| `e2e/vehicle-presentation.spec.ts` | Cuatro E2E y trece auditorías de vehículos |
| `e2e/interface-polish.spec.ts` | Esperar fin real de animaciones finitas antes de auditar, con las mismas reglas/aserciones |
| `docs/ESTADO-VERIFICADO.md` | Estado actual y evidencia |
| `reports/VEHICULOS-PRESENTACION-2026-10-07.md` | Este informe |

Los cambios anteriores de package.json, README, CONTINUAR y ARRANQUE-LOCAL se conservan.
La evidencia JSON/log/capturas sintéticas permanece ignorada en
`reports/vehicle-presentation-2026-10-07/`: performance-before/after, pytest-full,
e2e-final, real-ui, integrity, privacy y los resúmenes de accesibilidad.

## Comprobación y límites

Si el servidor está abierto, detenerlo con Ctrl+C y volver a arrancar desde el repositorio:

```bash
npm run start
```

Recargar el navegador para usar el build nuevo. La descripción importada aparece sin
reimportar ni editar registros, también en la copia persistente preparada para start.

Mediciones locales con caché caliente y muestra finita; no equivalen a transporte/render
ni garantizan idéntico tiempo en todo equipo. No se ha modificado ni recompilado Tauri,
ni se ha probado Windows en esta tarea. La evidencia corresponde al servicio Python y
la interfaz de navegador actuales.
