# Migración del Access real · 6 de octubre de 2026

## Resultado local y límites

Se investigaron ambos MDB, se corrigió e integró el importador y se ensayó la migración
local con datos aislados. Se importan **1.595 clientes, 1.290 vehículos, 5.133 históricos
y 19.335 líneas**, sin reconstruir importes, IVA, fechas conflictivas ni titularidades.
Se conservan las **27.621 filas originales** de las siete tablas, incluso las no mapeadas.
La conciliación de los registros importados tiene **cero diferencias**.

Los datos desconocidos se conservan explícitamente. Esto no significa que se haya
recuperado una reproducción fiscal exacta de cada factura ni que todos los registros
puedan activarse. Hay identidades/fechas que requieren evidencia humana, descritas abajo.
La aplicación sigue en **0.9.1, development**. No se ha habilitado producción, enviado
a AEAT, hecho push ni publicado ningún archivo o release.

Anexos:

- [Objetos, fórmulas y VBA recuperados](ACCESS-FORENSICS-2026-10-06.md).
- [Comparación principal, backup y snapshots](ACCESS-COMPARISON-2026-10-06.md).
- [Revisión independiente de integridad](ACCESS-INTEGRITY-REVIEW-2026-10-06.md).
- [Modelo, PDF e interfaz de históricos parciales](HISTORICOS-PARCIALES-2026-10-06.md).
- [Recorrido del asistente en navegador](ACCESS-PARTIAL-E2E-2026-10-06.md).
- [Servicio empaquetado y Tauri/Linux real](ACCESS-DESKTOP-2026-10-06.md).

## Entorno, preservación y Git

Repositorio local `/home/eruizgarcia/proyectos/personal/taller-canamo`, rama `main`,
HEAD `a67f8d24c03ab439820bfc11198629d909878e13`. Antes de editar se ejecutaron
`git status --short`, `git diff` y `git diff -- tools/access/CanamoAccess.java`.
El cambio previo intencionado del usuario se guardó en `/tmp/taller-canamo-pre-codex.diff`
y se integró sin revertirlo. No se utilizó reset, restore, clean ni se descartó trabajo.
Estado final: **18 archivos versionados modificados y 21 nuevos**, índice vacío,
sin commit ni push. El inventario de abajo incluye código, pruebas y documentación.

Linux x86_64, Python 3.13.2 en `.venv`, Node 22.22.2, npm 10.9.7, Rust 1.98.1,
Jackcess 5.0.1 y JRE Temurin 17 incluido.
Se reconstruyó el lector desde sus dependencias fijadas. Los originales siempre se
leyeron en modo read-only; los ensayos usan copias nuevas. Extracciones, bases, BLOB,
SQL/VBA completos, PDF e informes detallados permanecen privados y fuera del repositorio.

SHA-256 iniciales y comprobados al terminar:

- Principal: `ae5cc1de6a990609a699cf17c366ecf17c124f0c2150c84995d4eb0ac7ccbb16`.
- Backup: `bf27f26633703b7a869e5d09bdc07d3fdc6aa3daf0543631b910b1b6743a8dbf`.

La carpeta de diagnóstico anterior `.canamo-access-prueba` permanece intacta.

## Qué se encontró en Access

Ambos archivos son Access 2003 / Jet 4. Las tablas se recorren aunque sus contadores
internos estén desactualizados: principal Clientes 1.613 frente a 1.609 declaradas,
DETALLE 19.661 frente a 19.631, Facturas 5.108 frente a 3.906. El backup presenta el mismo
tipo de discrepancia. La lectura utiliza el recorrido como conteo efectivo, conserva
ambos valores y concilia el JSONL con las filas realmente extraídas.

Se leyeron diez tablas de sistema por MDB, incluidos MSysObjects/MSysAccessStorage,
y se recuperaron 12/12 módulos VBA en principal y 11/11 en backup. Los once módulos
comunes son idénticos. Se localizaron cuatro formularios por MDB y diez/nueve informes.
El código confirma `TOTAL = CANTIDAD * PRECIO`; el informe principal suma BRUTO y aplica
0.21/1.21. También contiene informes alternativos 0.18/1.18 y 0.16/1.16.

**Se recuperaron fórmulas, pero no una fórmula histórica completa y fiable por periodo.**
No se recuperó selección temporal del IVA ni una regla explícita de redondeo. Los dos
decimales son formato visual. El informe usa Date() al imprimirse, datos actuales de
cliente y filtro por FACTURA sin COD_CLI. Además suma en el evento Format sin guardia
FormatCount: es un riesgo de repetición al paginar, no un fallo de impresión reproducido.
No se ejecutaron Access, macros o VBA, ni se afirmó equivalencia con el documento impreso.

Recuento monetario local con Decimal de precisión ampliada: 19.593 TOTAL utilizables,
68 ausentes/no numéricos y 759 líneas con fracción de céntimo. En los 19.592 triples
cantidad/precio/TOTAL disponibles, 19.588 productos coinciden exactamente y cuatro no.
Se preservan también esas cuatro discrepancias; no se recalcula el TOTAL fuente.

El backup contiene líneas hasta **2016-06-23**; llamarlo «2018» no acredita esa fecha.
Los snapshots «2004» son iguales entre ambos MDB, pero llegan a febrero de 2005.
Los 137 clientes antiguos están en el principal por código; 62 son versiones distintas.
De 762 líneas antiguas, cuatro no son idénticas al principal: se conservan como versiones
de evidencia, sin añadirlas automáticamente y duplicar trabajos.

## Resolución de los grupos de incidencias

| Problema anterior | Comportamiento implementado y evidencia |
|---|---|
| `access_unreadable` por contador | No aborta por metadato obsoleto; `rows`, `reported_rows`, `row_count_mismatch`, UI y fixture MDB real de regresión |
| 4.215 errores de totales ausentes | Esquema v8, importes NULL con estado/procedencia; no se inventa IVA/base/total, ni se suman como cero |
| 726 errores de fracciones de céntimo | Decimal fuente exacto en `amount_raw`; sin redondeo por línea/factura; raw íntegro y PDF sin clasificación fiscal |
| 281 errores de clave de líneas | 281 FACTURA NULL conservadas en cuarentena. La cifra previa 296 sumaba 15 claves con cero: cero sigue siendo valor válido |
| 218 avisos de matrícula compartida | 105 matrículas sin titular actual acreditable: no se transfieren. Las referencias quedan en cuarentena y revisables |
| 103 claves sin cabecera | Clave compuesta completa permite recuperar identidad, no total. 101 históricos/328 líneas activables; dos claves con cliente inexistente se conservan aparte |
| 82 errores previos de fecha/cabecera | 45 cabeceras sin líneas más 37 conflictos de cabecera. Incluyendo huérfanas hay 38 conflictos: NULL+candidatos, sin elegir primera/última |
| 57 cabeceras de clave incompleta | Preservadas con fila/regla. 55 tienen COD_CLI NULL, compatible con la consulta Borrar Fantasmas; no se borran |
| 19 errores de concepto ausente | Se conserva la línea y el concepto desconocido, sin texto inventado |
| 18 clientes incompletos | Ningún nombre recuperable en backup/snapshot. Quedan en cuarentena; dos códigos afectan a facturación |
| 9 importes no válidos | Campo desconocido con valor fuente preservado; no conversión silenciosa a cero |
| 7 grupos duplicados de cabecera | Todas son iguales por COD_CLI+FACTURA: consolidar 8 filas extra en 7 históricos, conservando las 15 cabeceras fuente |
| 3 matrículas inválidas | Referencias conservadas para revisión, sin activar un vehículo ficticio |
| 53 NIF inválidos | Advertencia y evidencia original; no inventar NIF |
| 186 relaciones postales antiguas | Perfil sugiere relación real. 171 advertencias en clientes activables; las otras corresponden a clientes retenidos antes del join |

El comparador comprobó 81 líneas sin número con candidato único en backup, pero la
línea completa ya estaba en principal en los 81 casos: rellenar duplicaría datos.
Las 27 fechas conflictivas ya presentes en backup tienen el mismo multiconjunto de
líneas; no son resolubles eligiendo ese archivo. Las otras once son posteriores.
La separación temporal de facturación entre clientes tampoco acredita la titularidad
actual de un vehículo. No se han usado estas hipótesis para completar datos.

## Contrato e integración

- Perfil sugerido `options.preservation=partial` solo cuando la estructura carece de
  todos los totales de cabecera; relación postal sugerida por columnas reales.
- `canonical_historical` mantiene modo completo/v1 y añade parcial explícito. Diferencia
  cero conocido de desconocido; no modifica el objeto raw al normalizar grupos fiscales.
- `amounts_state`, `amounts_provenance`, `date_state`, candidatos de fecha y
  `header_state` acompañan al histórico. Se mantiene el raw original y toda su procedencia.
- `row_decisions` conserva entidad, tabla, número de fila, disposición, regla y clave.
  También registra exclusiones explícitas y vínculos documentados. `quarantine` permite
  avanzar a los registros seguros sin borrar ni atribuir los ambiguos.
- Una identidad duplicada actual no reutiliza silenciosamente el cliente de una copia
  anterior. Un vehículo dudoso no impide conservar la factura sin atribuirle ese vehículo.
- La huella semántica no cambia por mover una fila física; orden de líneas explícito
  respetado. La conciliación compara líneas, impuestos, fechas e importes conocidos/NULL.
- Listado, detalle, PDF y reportes muestran «No consta». Históricos sin total no admiten
  saldos/cobros; históricos incompletos no admiten rectificaciones. Facturación nueva
  mantiene restricciones y triggers de inmutabilidad. No se modifican series ni cola fiscal.
- Incidencias agrupadas en la interfaz; 19 motivos en este origen, no 26.798 decisiones
  manuales. El detalle paginado y el informe privado conservan todas las observaciones.
- La conversión a céntimos desplaza el exponente Decimal sin redondear al contexto.
  Se prueba una fracción casi exacta de más de 28 dígitos. El PDF no expande exponentes
  extremos hasta agotar memoria y mantiene representación decimal exacta.

## Ensayos y conciliación real

Comando reproducible, siempre con un destino inexistente:

```bash
.venv/bin/python scripts/rehearse_access.py "$MDB_PRINCIPAL" "$DIRECTORIO_NUEVO"
# --keep-imported permite conservar únicamente ese ensayo para inspección local.
```

Directorios privados de esta sesión:

1. `~/.canamo-access-codex-rehearsal-20261006-a`: ciclo completo y rollback; 182,148 s.
2. `~/.canamo-access-codex-rehearsal-20261006-b`: segundo entorno limpio; 185,071 s;
   importado para inspección, sin uso productivo. Agregados completamente desconocidos
   ya se devuelven como NULL, también en conciliación.
3. `~/.canamo-access-codex-rehearsal-20261006-c`: comprobación del código final y rollback;
   **343,745 s**, conciliado sin diferencias; 8.018 cambios revertidos y cero registros
   activos, con evidencia retenida. La diferencia de duración incluye ejecución simultánea
   de pruebas y compresión del servicio; no es una medición de rendimiento comparable.

Cada ciclo incluye diagnóstico → mapeo → previsualización → simulación aislada →
importación con copia previa → conciliación → búsqueda de todos los clientes/vehículos
importados → seis comprobaciones de PDF representativas (pueden compartir documento)
→ dashboard/reportes → integridad SQLite/FK,
auditoría y hash. El informe completo se genera y conserva localmente.

| Concepto | Importado / conservado |
|---|---:|
| Clientes activos | 1.595 |
| Vehículos activos con relación de origen no conflictiva | 1.290 |
| Históricos activos | 5.133 |
| Líneas en históricos activos | 19.335 |
| Históricos con fecha única conservada en líneas | 5.050 |
| Históricos sin fecha por ausencia de líneas | 45 |
| Históricos con fechas en conflicto explícito | 38 |
| Históricos con base/IVA/total finales desconocidos | 5.133 |
| Históricos con cobro desconocido, sin convertirlos en deuda | 5.133 |
| Filas raw de todas las tablas | 27.621 |
| Decisiones de líneas; ninguna sin original | 19.661 |
| Diferencias de conciliación | 0 |
| Registros/cola fiscal nuevos | 0 |
| Series modificadas | 0 |
| Cambios del lote reversibles | 8.018 |

Los 5.133 históricos corresponden a 5.043 claves de cabecera completas − 11 sin cliente
resuelto + 101 identidades recuperadas de líneas. Hay 19.007 líneas con cabecera y 328
con identidad recuperada. Un total de 5.203 candidatos incluye además los 70 retenidos;
no se presenta ese número como facturas activas.

Permanecen **310 registros/candidatos en cuarentena**: 18 clientes, 222 referencias de
vehículos y 70 históricos/cabeceras (57 claves incompletas + 13 clientes no resueltos).
En vehículos las razones finales son 217 referencias compartidas, dos sin cliente
resuelto y tres inválidas; una referencia compartida tiene también cliente sin nombre,
por eso hubo 218 advertencias de matrícula pero 217 con ese motivo final.

Las **326 líneas fuera de históricos activos** son 281 sin número + 45 sin cliente
resuelto. Permanecen íntegras; no se cuentan como líneas importadas ni desaparecen del
informe. Una revisión independiente read-only comparó todos los `raw_rows` y todas las
`row_decisions` con `report.jsonl` en A/B: contenidos idénticos, cero filas sin decisión,
cero decisiones sin fila original. Las 101 filas de Clientes sin matrícula no representan
un vehículo; conservan decisión `not_applicable` y su fila de cliente/raw.

## Verificación final

Las salidas automáticas quedan fuera de Git en `reports/access-real-verification/`.
Los comandos Python se ejecutan con `.venv/bin/python`.

| Comprobación | Resultado ejecutado |
|---|---|
| `python -m pip check` | Código 0, sin incompatibilidades |
| Access existente: `pytest tests/test_access_imports.py tests/test_access_adversarial.py -q` | 24 correctas, 19,87 s; incluida otra vez en pases finales |
| Access + parcial + contratos + revisión: cinco archivos de pruebas | 47 correctas, 37,24 s |
| `python -m pytest` final | **496 correctas**, 208,45 s, sin fallos ni omitidas |
| `npm run typecheck` | Código 0 |
| `npm run typecheck:e2e` | Código 0; repetido al ajustar la última aserción |
| `npm run build` | Código 0; 40 módulos, Vite 3,59 s |
| `npm run test:e2e` | **41 correctas**, cero fallos/flaky/omitidas; **141,260 s** según JSON Playwright |
| `cargo test --locked --no-default-features --lib` | **18 correctas**, 2,02 s |
| `cargo check --locked` / `cargo build --locked` | Ambos código 0 con SDK Linux privado oficial |
| `scripts/build_desktop.py --sidecar-only` final | Código 0; **9 grupos funcionales correctos**, fuentes estables comprobadas por hash |
| Diagnóstico del ejecutable Tauri | `ok: true`, servicio nuevo verificado por SHA |
| Tauri/WebKit real | **8/8 comprobaciones correctas**: búsqueda, ficha, PDF, instancia, IPC/errores, guardado GTK; receptores de impresión sintéticos |

Los pases intermedios no se ocultan: un build detectó dos errores de tipos al permitir
NULL en agregados, corregidos separando contadores numéricos; el primer E2E completo se
solapó con la reconstrucción de `dist` y encontró una página vacía; el segundo completó
40 casos y falló una aserción que todavía esperaba el texto anterior «suma conocida».
La aserción se actualizó para exigir **No consta en ambas celdas**, conservando todas
las comprobaciones de importación y rollback. No se aumentaron reintentos ni se retiraron
validadores para conseguir el resultado final.

El primer paquete del servicio pasó sus comprobaciones funcionales, pero se rechazó
correctamente por cambios de fuentes concurrentes. Se repitió y se ensayó el nuevo
artefacto. El SDK previo ya no existía: se extrajeron paquetes oficiales Ubuntu en un
directorio privado, sin sudo ni cambios globales. El anexo explica la regeneración de
caché Tauri y reparación de rutas del SDK; no se debilitaron las pruebas del producto.
La ventana nativa usa exclusivamente datos sintéticos. No es prueba de Windows,
WebView2, impresora física, certificado real ni AEAT autenticada.

En B se inspeccionaron localmente los cuatro PDF distintos generados por los seis casos:
todos tienen contenido extraíble, etiqueta «Histórico incompleto» y «No consta».
No se enviaron esas páginas al chat; la inspección visual/Axe usa únicamente fixtures
sintéticas. A/B coinciden exactamente en conteos, acciones, decisiones, fechas, tablas,
búsquedas y grupos retenidos.
B/C coinciden también en la conciliación final, incluidos los agregados NULL; se
compararon ocho grupos de métricas completos. El rollback final de C conserva fuentes,
archiva fichas importadas y desactiva históricos, sin restaurar una base antigua encima.

Auditoría de privacidad: cero MDB/ACCDB/SQLite/DB/copias/certificados trackeados o staged,
índice vacío; comparación local de los campos personales reales (sin imprimirlos) contra
líneas añadidas y archivos nuevos: cero coincidencias exactas. Esta búsqueda complementa
la revisión manual y `.gitignore`, no convierte el repositorio en almacén de datos privados.

## Archivos y organización del cambio

Código: `backend/taller/access.py`, `access_mapping.py`, `access_partial.py`,
`access_imports.py`, `access_writer.py`, `documents.py`, `pdf.py`, `reporting.py`,
`migrations/__init__.py`, `migrations/v0008_partial_history.py`;
`tools/access/CanamoAccess.java`, `tools/access/AccessForensics.java`;
`frontend/core.tsx`, `documents.tsx`, `imports.tsx`, `reports.tsx`.

Herramientas: `scripts/access_forensics.py`, `compare_access.py`, `rehearse_access.py`.
Regresiones: `tests/test_access_partial.py`, `test_partial_history.py`,
`test_access_partial_contracts.py`, `test_access_partial_review.py`,
`test_access_forensics.py`, `test_access_comparison.py`;
`e2e/access-partial-import.spec.ts`, `partial-history.spec.ts` y adaptación de apertura
del desplegable en `e2e/access-import.spec.ts`, sin retirar comprobaciones.

Documentación: `docs/IMPORTACION-ACCESS.md`, `ESTADO-VERIFICADO.md`,
`CONTEXTO-PRODUCTO.md`, `CONTINUAR.md` e informes técnicos sanitizados de esta fecha.
No se incorporan MDB, SQLite, certificados, registros reales o fixtures con PII.

## Al volver y gates externos

1. Abrir exclusivamente B como ensayo con `python scripts/run_preview.py --data
   "$HOME/.canamo-access-codex-rehearsal-20261006-b"`; revisar Traer datos, motivos
   agrupados, originales y conciliación. No convertirlo en base operativa.
2. Revisar con quien conoce el taller las 105 matrículas compartidas, identidades y
   fechas ambiguas. Si no existe evidencia adicional, mantenerlas explícitamente
   desconocidas. Ninguna requiere inventar una respuesta para consultar el resto.
3. Para completar importes históricos hacen falta originales impresos o una prueba
   reproducible de plantillas, periodos y redondeos. La fórmula actual no basta.
4. Ejecutar instalador Windows 11/WebView2 y prueba de impresora física; comprobar
   certificado legítimo, identidad de emisor/productor y AEAT pruebas autenticadas.
5. Solo después acordar corte final, copia Access cerrada reciente, última factura y
   numeración nueva. No están confirmados en Linux y no se declaran completados.

El ensayo local no sustituye esos medios externos ni acredita producción fiscal.
