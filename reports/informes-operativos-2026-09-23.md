# Informes operativos, exportación y flujos opcionales — 23/09/2026

## Cambios verificados

- `backend/taller/reporting.py` sustituye la consulta limitada a 24 meses por
  períodos inclusivos y todo el historial. Separa facturación, caja, saldos
  iniciales, ajustes documentales, deuda positiva y devoluciones pendientes.
  Excluye de deuda las históricas sin cobro acreditado y lotes revertidos; los
  ajustes `opening_adjustment` no se suman como caja.
- `frontend/reports.tsx` permite consultar y descargar cada resumen. Identifica
  pruebas, saldos desconocidos, fechas de pago y datos que reflejan el estado
  actual. Root integró las acciones en App y el saldo separado en el inicio.
- Exportación portable original con JSON, CSV, esquema, recursos permitidos,
  auditoría y manifiesto SHA-256. Conserva snapshots, payload, ceros, decimales,
  relaciones, procedencia y bytes originales B2B. No exporta certificados, claves,
  almacén `secure/`, motores de asistencia ni rutas privadas de configuración.
- Catálogo/proveedores con archivo recuperable, búsqueda normalizada y detección
  de edición obsoleta; referencias duplicadas rechazadas. Entrada, salida,
  devolución y recuento justificado, atómico e idempotente. Una devolución de
  documento reactiva el artículo archivado para mantener visible el stock.
- Manual: `docs/INFORMES-EXPORTACION.md`.

## Ejecución real

Entorno: Linux, Python 3.13.2 en `.venv`, Node 22.22.2, Chromium de Playwright.
Solo SQLite y archivos temporales sintéticos; sin datos reales ni servicios externos.

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_reporting.py tests/test_integrity_regressions.py tests/test_restore_recovery.py -q --tb=short --junitxml=reports/reporting-backend-2026-09-23.xml` | 67 passed, 5,35 s, salida 0 |
| `.venv/bin/python -m pytest tests/test_reporting.py -q --tb=short` tras añadir comprobación de bytes B2B | 10 passed, 1,23 s, salida 0 |
| `npm run typecheck` | Salida 0 |
| `npx tsc -p tsconfig.e2e.json --noEmit` | Salida 0 |
| `npm run build` | Salida 0; Vite 7.3.6 |
| `npx playwright test e2e/operations.spec.ts --reporter=list --output=reports/operations-e2e-artifacts` | 2 passed, 4,1 s, salida 0 |

Evidencias: `reporting-backend-2026-09-23.txt/xml`,
`operations-e2e-2026-09-23.txt`, capturas y resultados axe bajo
`operations-e2e-artifacts/`. Intentos iniciales se conservan con sufijos
`first`, `selectors` y `fixture`: se corrigieron selectores del test y la dirección
fiscal omitida en su cliente sintético. No se rebajaron las validaciones de emisión.

El E2E usa interfaz y backend reales para crear/archivar/restaurar proveedor,
crear artículo y registrar cuatro operaciones de almacén con doble clic. Comprueba
persistencia tras reinicio, rechazo de archivo con stock, y cero violaciones axe
en proveedores/catálogo oscuro con texto grande a 1024 × 768.

El segundo E2E confirma presupuesto, lo acepta, crea y termina orden, convierte y
emite una factura de prueba con doble clic. Las tres piezas conservan líneas y
relaciones; repetir la conversión desde presupuesto y orden devuelve la misma
factura. Diez unidades iniciales quedan en ocho con un único consumo. Registra un
cobro, reinicia, verifica facturación/caja/pendiente y descarga CSV y ZIP desde la
interfaz. Abre el ZIP real y comprueba originales y recuentos. Axe en informes:
cero violaciones WCAG A/AA, incluido 2.2.

## Límites y continuación

El resumen es operativo, no contabilidad. La exportación portable es texto sin
cifrar y no activa una instalación ni restaura una cola fiscal. Su transporte
inicial tenía un límite de 200 MB/20.000 archivos. La ampliación posterior de esta
sesión lo sustituyó por archivos y capacidades de descarga: 8 GiB/50.000 archivos,
JSON/CSV por filas y recursos por bloques. El resultado de esa revisión, incluido
un recurso sintético de 2 GiB, se documenta en `copias-streaming-2026-09-23.md`.

Las pruebas de navegador no acreditan Tauri real en Windows, DPAPI, discos externos
ni impresión física. No hubo envío autenticado a AEAT ni entrega remota B2B.
