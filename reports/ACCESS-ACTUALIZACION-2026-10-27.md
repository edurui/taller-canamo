# Actualización incremental de la prueba local · 27/10/2026

## Alcance autorizado y resultado

El usuario aportó un MDB actualizado en la raíz y pidió añadir a la prueba local
solo lo nuevo desde el 05/10/2026 y analizar los importes. El intervalo se trató como
05/10–27/10, ambos incluidos. No se modificaron el MDB aportado, el ensayo original
del 06/10 ni sus datos operativos de Access. Solo se actualizó la previsualización
persistente `~/.local/share/taller-canamo-preview/data`.

| Entidad | Antes | Añadidos | Después |
| --- | ---: | ---: | ---: |
| Clientes | 1.595 | 3 | 1.598 |
| Vehículos | 1.290 | 2 | 1.292 |
| Históricos | 5.133 | 12 | 5.145 |
| Líneas de los históricos añadidos | — | 38 | — |

No hubo sustituciones de clientes, vehículos o documentos. Los clientes nuevos se
identifican por claves ausentes de la copia anterior; la tabla no acredita fechas
de alta. Las facturas nuevas tienen fecha única entre 09 y 26/10. El histórico que
ya existía dentro del intervalo no se duplicó.

## Comparación completa del origen

Extracción Jackcess local de solo lectura, sin vínculos ni ejecución de consultas,
macros, formularios o VBA. Los conteos efectivos vuelven a diferir de algunos
contadores internos de Access: se compararon filas leídas, no esos metadatos.

| Tabla | Anterior | Actual | Diferencia efectiva |
| --- | ---: | ---: | --- |
| Clientes | 1.613 | 1.616 | Tres claves nuevas y dos filas existentes modificadas |
| DETALLE | 19.661 | 19.706 | 45 filas añadidas; ninguna anterior eliminada/modificada |
| Facturas | 5.108 | 5.122 | 15 filas añadidas y una anterior ausente/modificada |
| Clientes 2004 | 137 | 137 | Sin cambios |
| Detalle 2004 | 762 | 762 | Sin cambios |
| Codigos_Postal | 339 | 339 | Sin cambios |
| Errores de pegado | 1 | 1 | Sin cambios |

La comparación de cabeceras es un multiconjunto de filas, no una afirmación de
emisiones/borrados: el mapeo por COD_CLI + FACTURA conserva los 5.133 históricos
anteriores sin cambios semánticos y detecta 14 candidatos nuevos con 43 líneas.
Las otras dos líneas nuevas, del 13/10, carecen de número de factura y permanecen
en el origen y en la evidencia privada, sin inventar una identidad.

## Conflictos conservados

Dos códigos de cliente ya importados tienen distinto nombre y NIF en el MDB nuevo.
Dos de las 14 facturas nuevas utilizan esos códigos. No se puede decidir si son
correcciones de identidad o reutilización de fichas para otras personas. Tras ver
la comparación privada, el usuario eligió expresamente «No lo sé; dejarlos pendientes».
Se excluyeron esas dos altas con motivo documentado; sus cinco líneas se conservan.
No se atribuyeron a las personas anteriores ni se sobrescribieron sus datos.

Una referencia de vehículo de un cliente nuevo comparte matrícula con una ficha
existente. Se excluyó expresamente su alta, sin transferir ni duplicar el vehículo.
Los otros dos vehículos nuevos no presentan conflicto y sí se incorporaron.

## Aplicación y protección

Se guardó un expediente privado, con permisos restringidos, bajo
`~/.local/share/taller-canamo-import-audits/`. Incluye snapshot online previo,
MDB íntegro, extracciones completas de ambas copias, informes forenses, selección
incremental, correspondencia de filas originales, comparaciones HTML, CSV de
importes, resultados y scripts de operación. No contiene recursos remotos.

La selección usa un paquete intermedio explícitamente derivado del MDB, el mismo
origen y el mismo perfil anterior. Incluye tres clientes nuevos, sus datos postales,
14 cabeceras y 43 líneas; tres exclusiones motivadas dejan 17 altas efectivas.
Los hashes semánticos de los clientes/facturas seleccionados se comprobaron contra
el mapeo completo: seleccionar filas no cambió su contenido. Las omisiones del
paquete incremental son intencionadas y no provocan borrados.

Antes de tocar el preview se ejecutaron simulación y aplicación sobre una copia
aislada del estado existente. Una segunda carga del mismo paquete produjo 17
registros sin cambios, tres exclusiones y cero altas: idempotencia comprobada.

La aplicación efectiva utilizó el RPC autenticado del servidor local que ya estaba
abierto en 127.0.0.1:8765. Se creó copia de seguridad explícita y la importación
conservó también su mecanismo de copia previa. No se detuvo la ventana del usuario
ni se sustituyó su archivo SQLite manualmente.

## Importes

Forense actualizado y comparado con el MDB anterior: los 15 BLOB de objetos y las
12 fuentes VBA recuperadas tienen hashes idénticos. El informe principal mantiene
BRUTO × 0,21 y BRUTO × 1,21; el subformulario mantiene cantidad × precio y suma de
TOTAL. Siguen existiendo las variantes al 16/18 %. No se ejecutó Access ni su
paginación y no se contrastaron impresos originales.

Facturas sigue teniendo únicamente COD_CLI y FACTURA. No hay base, cuota ni total
final guardados en sus cabeceras. TOTAL de DETALLE conserva el importe de línea,
no una acreditación del total impreso ni del IVA aplicado a cada documento.

Las 43 líneas de los 14 candidatos nuevos conservan importes decimales de céntimos,
sin discrepancias detectadas con cantidad × precio. Las 14 propuestas automáticas
son estimadas; se contrastaron mediante un cálculo decimal independiente: suma
exacta, base HALF_UP a céntimos, IVA propuesto sobre esa base y total base + IVA.
El desglose y las cantidades monetarias de negocio permanecen exclusivamente en
`importes-nuevos.html`, `importes-nuevos.csv` y los resultados del expediente privado.

En la base actual hay 5.046 revisiones estimadas y las mismas 99 pendientes de antes.
No se marcaron propuestas como contrastadas con original. Los campos originales
base/IVA/total de las 12 facturas añadidas permanecen NULL. El informe del intervalo
aumenta exactamente en sus 12 documentos y sus estimaciones, manteniendo aparte la
facturación original. No se crearon cobros, deuda, series ni registros/envíos fiscales.

## Comprobaciones ejecutadas

Entorno Linux; servicio Python 3.13.2, SQLite y Chromium/Playwright locales. No hubo
cambios de fuentes ejecutables, migraciones ni dependencias en este encargo.

- SHA-256 del MDB antes/después idéntico y copias de trabajo verificadas.
- Extracción y forense read-only de ambas copias; cero vínculos o código ejecutado.
- Mapeo completo y comparación de filas/claves; alcance incremental documentado.
- Simulación aislada sin cambios de dominio; 17 altas previstas y realizadas.
- Conciliación final: 12 documentos/38 líneas, cero diferencias, cero claves ausentes.
- Conservación exacta de todas las filas previas de clientes, vehículos, titulares,
  documentos, revisiones, pagos, series, fiscalidad, stock, agenda y avisos.
- Integridad SQLite, claves foráneas y cadena de auditoría correctas.
- Segundo lote aislado sin duplicados; cero import_changes nuevos en esa repetición.
- Informe del intervalo: aumento exactamente igual a los documentos y estimaciones
  aceptados; cobros y deuda permanecen sin cambios.
- Navegador real sobre el preview actualizado: 12 búsquedas/listados/detalles de
  factura con el mismo importe estimado; tres búsquedas de los clientes nuevos.
- Dos auditorías Axe WCAG 2/2.1/2.2 A/AA sin violaciones en las pantallas recorridas,
  sin errores de JavaScript ni peticiones externas. No es una auditoría completa.

La primera auditoría Axe abortó después de recorrer las 12 facturas porque el script
usaba el contexto implícito de browser.newPage. Se corrigió el script de comprobación
para usar browser.newContext y se repitió todo el recorrido con resultado correcto;
no se cambió la aplicación ni se rebajaron reglas de accesibilidad.

No se repitieron pytest, typechecks, build ni la batería E2E sintética, al no cambiar
código ejecutable. No se ejecutaron Windows/WebView2, impresión física ni aceptación
fiscal externa. Esta actualización no cambia el estado de versión de pruebas.
