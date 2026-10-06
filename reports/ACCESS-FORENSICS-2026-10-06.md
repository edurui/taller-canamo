# Forense local de objetos Access · 06/10/2026

## Resultado y alcance

Se han leído **los dos MDB originales en modo de solo lectura** y recuperado las fórmulas
de los informes y el código fuente VBA almacenado, sin ejecutar Access, consultas, macros,
VBA ni vínculos. El informe principal actualmente guardado aplica **21 % fijo**; también
existen informes con **18 % y 16 %**. Esto **no prueba qué plantilla se utilizó al emitir
cada factura histórica ni su redondeo exacto**. No se ha descubierto una regla de selección
del IVA por fecha. No es correcto convertir estas observaciones en un 21 % global para la
migración.

Este documento contiene exclusivamente metadatos técnicos, expresiones y resultados
agregados. Los BLOB, SQL completos, fuentes VBA, literales, imágenes y datos de sistema
se conservan únicamente en un directorio local privado fuera del repositorio. No se han
transmitido bases, extractos ni datos personales a servicios externos. Las consultas web
se limitaron a documentación pública del formato y del motor.

| Evidencia | MDB principal | MDB de respaldo |
|---|---:|---:|
| Tamaño del original | 24.645.632 bytes | 17.039.360 bytes |
| Formato reconocido | Access 2003 / Jet 4 | Access 2003 / Jet 4 |
| Tablas de sistema leídas | 10 | 10 |
| Registros MSysObjects | 72 | 69 |
| Registros MSysAccessStorage | 124 | 115 |
| Formularios | 4 | 4 |
| Informes | 10 | 9 |
| Macros almacenadas como objeto | 1 | 1 |
| Módulos generales registrados como objeto | 1 | 1 |
| Fuentes VBA recuperadas, incluidas clases de formularios/informes | 12 de 12 | 11 de 11 |
| Consultas SELECT / DELETE | 20 / 1 | 18 / 1 |
| SHA-256 antes/después | Idéntico | Idéntico |

Huellas de los originales, contrastadas también con el registro previo al trabajo:

- Principal: `ae5cc1de6a990609a699cf17c366ecf17c124f0c2150c84995d4eb0ac7ccbb16`.
- Respaldo: `bf27f26633703b7a869e5d09bdc07d3fdc6aa3daf0543631b910b1b6743a8dbf`.

Jackcess emitió en ambos un aviso de mapa de uso inválido para una columna de
`MSysAccessXML`; esa tabla enumera cero filas en ambos. No se ocultó: los logs completos
están en la evidencia privada. Las otras tablas y BLOB investigados pudieron leerse.
Esto no constituye una certificación de integridad de todos los objetos de Access.

## Evidencia de cálculo recuperada

La correspondencia entre carpetas numéricas y nombres técnicos se obtuvo del flujo
`DirData` de `MSysAccessStorage`. Las expresiones son cadenas UTF-16LE localizadas en los
BLOB de diseño, buscando **ambas alineaciones de byte**; una búsqueda UTF-16 de alineación
única omitía algunas fórmulas. Se contrastaron con los módulos VBA descomprimidos.
La recuperación de cadenas no equivale a un parser completo de todas las propiedades
de diseño ni a un renderizado de Access.

| Objeto técnico | Expresiones presentes en ambos MDB | Alcance probado |
|---|---|---|
| Formulario `Subformulario DETALLE` | `=Sum([TOTAL])`, `=Sum([TOTAL])*0.21`, `=Sum([TOTAL])*1.21` | Cálculo de pie del formulario guardado |
| Informe `Facturacion` | `=[BRUTO]*0.21`, `=[BRUTO]*1.21` | Tipo fijo del informe que abre el botón de facturas |
| Informe `Copia de Facturacion5` | `=[BRUTO]*0.18`, `=[BRUTO]*1.18` | Plantilla alternativa guardada; sin vigencia por fecha acreditada |
| Informe `DETALLE1` | `=Sum([TOTAL])`, `=[Suma De TOTAL]*0.16`, `=[Suma De TOTAL]*1.16` | Otro informe guardado; sin vigencia por fecha acreditada |
| Informes `Copia de Facturacion`, `Copia de Copia de Facturacion`, `factura 1`, `factura turbo` | `=[BRUTO]*0.21`, `=[BRUTO]*1.21` | Variantes guardadas |
| Informe `escritorio` | `=[BRUTO]*0.21`, `=[BRUTO]*1.21` | Solo existe en el principal |

En `Facturacion` principal, los nombres de control `Texto237` y `Texto238` aparecen
inmediatamente antes de las expresiones de cuota y total, en los offsets de BLOB
**1.198.086** y **1.198.497** respectivamente. El nombre de control `bruto` precede
al formato monetario. Son offsets del BLOB extraído, no del archivo MDB completo.
En el respaldo las expresiones equivalentes están en **1.198.093** y **1.198.504**.

Código fuente del subformulario:

```vb
Private Sub CANTIDAD_AfterUpdate()
    TOTAL = CANTIDAD * PRECIO
End Sub

Private Sub PRECIO_AfterUpdate()
    TOTAL = CANTIDAD * PRECIO
End Sub
```

El módulo del informe acumula `BRUTO = BRUTO + TOTAL` dentro de `Detalle_Format`,
reiniciando `BRUTO = 0` en `EncabezadoDelInforme_Format` y `Report_Activate`.
No comprueba `FormatCount` ni contiene un manejador `Retreat` que revierta la suma.
Se trata de un **riesgo demostrado en el código**, no de un descuadre de impresión ya
reproducido: Microsoft documenta que Access puede formatear la misma sección varias
veces al paginar. La suma SQL simple no acredita por sí sola lo que llegó a imprimirse.
[Evento Format de Access 2003](https://learn.microsoft.com/en-us/previous-versions/office/aa211384%28v%3Doffice.11%29).

El botón `Comando33_Click` de `Form_Facturas` asigna `stDocName = "Facturacion"` y llama a
`DoCmd.OpenReport`. Ese flujo está guardado igual en ambos MDB. La numeración antigua toma
el último registro visible y asigna `FACTURA = temporal + 1`; no debe reutilizarse como
garantía de secuencia global o como siguiente número del sistema nuevo.

## Redondeo: qué se conoce y qué falta

Los controles monetarios contienen un formato con dos decimales (`#,##0.00` y su sección
negativa). En los módulos VBA recuperados y las consultas guardadas no se encontró una
llamada a `Round`. Tampoco hay `Round` en las expresiones monetarias recuperadas.
La propiedad de formato afecta a cómo se presenta el dato, no a su almacenamiento.
[Propiedad Format de Access](https://learn.microsoft.com/en-us/office/vba/api/access.textbox.format).

Por tanto, **no se ha probado redondeo comercial por línea, por factura ni redondeo
bancario del documento original**. Que la función VBA `Round` use redondeo bancario no
prueba que esta base lo aplicara: esa llamada está ausente en el código recuperado.
[Función Round de VBA](https://learn.microsoft.com/es-es/office/vba/language/reference/user-interface-help/round-function).

`TOTAL = CANTIDAD * PRECIO` y los formatos de visualización tampoco prueban que todos los
valores históricos se introdujeran por ese formulario o que no existieran correcciones
manuales. Se deben preservar los importes de línea almacenados y su precisión, no
recalcularlos silenciosamente desde cantidad/precio. Una reconstrucción futura deberá
registrar por separado la fórmula observada, el periodo elegido, la política de
redondeo y la condición de reconstruido, sin convertir hipótesis en importe original.

La comprobación externa concreta que falta es contrastar en una copia aislada de Access
la impresión/visualización con casos sintéticos de empate, fracción de céntimo y varias
páginas, además de documentos originales representativos de los periodos del taller.
No se ha ejecutado Access ni se ha emulado su paginación en esta investigación.

## Fecha, selección de factura y datos históricos

La consulta de `Facturacion` une las líneas con **Clientes y códigos postales actuales**
y filtra por `DETALLE.FACTURA = Forms!Facturas!FACTURA`. No incluye `COD_CLI` en ese
filtro. Se confirma lo mismo en el respaldo y en la copia del informe al 18 %. Por tanto,
una reimpresión de número compartido puede mezclar líneas de varios clientes; esto es
una posibilidad derivada de la consulta, no una afirmación de que todas las facturas
impresas sufran ese problema.

El informe principal contiene `=Format(Date(),"Short Date")` para la fecha mostrada.
El subformulario tiene `=DATE()` junto a `FECHAFACTURA`. La fecha actual del informe no
es prueba de fecha de emisión histórica. Los datos de cliente consultados en vivo tampoco
constituyen una instantánea histórica del receptor o del vehículo.

No se recuperó una tabla o expresión de selección automática 16/18/21 % por fecha en
estos informes o módulos. La mera presencia de tres tipos, las fechas de modificación
del objeto y el nombre de una copia **no establecen periodos de vigencia**. La ausencia
observada se refiere a lo recuperado, no a una auditoría ejecutada de todo Access.

## Comparación entre los dos archivos

- Las **11 fuentes VBA comunes son idénticas byte a byte**. El principal añade la clase
  del informe `escritorio`.
- De los 13 BLOB comunes de formularios/informes, **11 son idénticos**. Cambian
  `Facturacion` y `Subformulario DETALLE`; conservan las fórmulas monetarias citadas.
  El principal añade `escritorio`.
- El principal incluye dos consultas adicionales; una corresponde a `escritorio` y otra
  al origen explícito del subformulario. La comparación no se interpreta como historial
  completo de versiones ni prueba de uso de cada plantilla.
- Se conservaron los BLOB binarios y propiedades OLE de sistema. El BLOB principal de
  informe contiene firmas JPEG incrustadas; no se publicaron ni enviaron imágenes.
  La presencia de esas firmas no se usa para inferir operaciones monetarias.
- La consulta DELETE `Borrar Fantasmas` elimina cabeceras con `COD_CLI Is Null` según el
  SQL guardado; no se ejecutó. El módulo general de macro convertida referencia una
  consulta llamada `Consulta1`, no localizada entre las consultas enumeradas. La macro
  binaria independiente se preservó, sin afirmar una decodificación completa de sus
  acciones. Ninguna de estas observaciones autoriza ejecutar macros contra originales.

## Herramienta y reproducibilidad

Nuevos archivos:

- `scripts/access_forensics.py`: orquesta lectura privada y genera un resumen por lista
  permitida exacta; no exporta nombres arbitrarios, textos, SQL ni literales a stdout.
- `tools/access/AccessForensics.java`: lee exclusivamente tablas de sistema con Jackcess;
  guarda datos privados en archivos numerados, desactiva expresiones y vínculos.
- `tests/test_access_forensics.py`: vectores sintéticos, límites, rechazo de datos
  malformados, privacidad y comprobación real de MDB sintético sin modificación.

Requiere el runtime Access ya preparado y JDK 17 o posterior. No instala dependencias,
no usa Office ni requiere red. Ejemplo con nombres sustituidos:

```bash
.venv/bin/python scripts/access_forensics.py '/ruta/privada/copia.mdb' \
  --private-output /tmp/forense-access-nueva
.venv/bin/python -m pytest tests/test_access_forensics.py -q
```

El destino debe ser nuevo y estar fuera del repositorio. En Linux se crea con permisos
0700 y sus archivos con 0600. Los logs del lector también son privados. Los originales
se abren con `setReadOnly(true)` y se comprueba SHA-256 antes/después; los destinos ya
existentes se rechazan. El resumen público sólo contiene alias, conteos, hashes y
expresiones técnicas de una lista cerrada. No se copian bases ni datos de negocio al repo.

El decodificador VBA implementa el contenedor y las referencias de copia MS-OVBA con
límites de 16 MiB por flujo/resultado descomprimido y 120 segundos para el lector Java.
La recuperación busca en los primeros 65.536 offsets de cada flujo de módulo un
contenedor completo válido y una cabecera de fuente VBA; conserva el offset encontrado.
Un flujo no admitido produce error o módulo no recuperado, sin inventar su contenido.
No valida el p-code compilado.
[Contenedor MS-OVBA](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ovba/492124cc-5afc-48c8-b439-b42ad7087a7b),
[tokens de copia](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ovba/97fde8bb-df11-48a1-9bdd-805b024c65a7).

Un módulo común termina con un byte de flags sin token. El modo estricto lo rechaza;
para su recuperación se utiliza una excepción explícita que sigue el comportamiento del
pseudocódigo de Microsoft y queda marcada como `empty_tail_compatibility: true`.
No se oculta como decodificación estricta. El caso cuenta con regresión sintética.
[Algoritmo de TokenSequence](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ovba/70ea7393-cc0d-4efd-ae18-853f29a062c8).

Verificación ejecutada en Linux el 06/10/2026:

- Suite propia: **14 pruebas correctas**, último pase 1,13 s.
- Lector recompilado y extracción real completa de objetos de ambos MDB: código 0.
- Resumen final: 12/12 y 11/11 fuentes VBA recuperadas; hashes originales sin cambios.
- `sha256sum -c` contra el registro inicial: **ambos OK**.

No se modificaron en este encargo el importador, el modelo contable, el frontend ni los
originales. La verificación integrada de la aplicación corresponde al informe general
de esta sesión; esta suite acredita exclusivamente la herramienta forense.
