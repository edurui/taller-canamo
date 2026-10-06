# Comparación estructural local de los dos MDB · 6 de octubre de 2026

Comparación ejecutada con Jackcess 5.0.1 sobre copias privadas, lectura `read_only`,
sin ejecutar consultas, VBA, formularios, informes ni vínculos. Los originales permanecen
en su ubicación. Las extracciones y el resultado completo local se mantienen fuera del
repositorio, en un directorio con permisos 0700. Este informe contiene únicamente
metadatos de esquema, fechas de cobertura y conteos; no contiene identificadores,
nombres, NIF, matrículas, teléfonos, direcciones ni conceptos de los registros.

## Reproducción y alcance

`scripts/compare_access.py` recibe dos directorios de extracción nativa ya preparados
por el lector local. Solo emite agregados JSON por una lista fija de tablas; no muestra
valores de filas, claves, huellas de registros, nombres de tablas desconocidas ni rutas.
No altera los directorios y no utiliza red. Verifica el número de filas de cada JSONL
y rechaza nombres de fichero/rutas que escapen del directorio. Los contadores de
comparación son **multiconjuntos**: una repetición adicional sigue siendo una fila.
Se comprobó también que invertir el orden de recorrido de todas las tablas produce
exactamente el mismo JSON de agregados. Los SHA-256 de ambos originales se contrastaron
al terminar este análisis con el manifiesto inicial: **2 de 2 sin cambios**.

```bash
.venv/bin/python scripts/compare_access.py "$EXTRACCION_PRINCIPAL" "$EXTRACCION_BACKUP"
.venv/bin/python -m pytest tests/test_access_comparison.py -q
```

Resultado de las pruebas sintéticas: **5 correctas, 0,07 s**. Cubren cero frente a NULL,
duplicidad y multiplicidad, salida sin valores privados, candidatos que duplicarían
líneas, conflictos de fecha antiguos, intervalos de facturación y rutas hostiles.
El comparador es una herramienta de diagnóstico; no sustituye la conciliación del
lote ni decide titularidades o modificaciones fiscales.

## Conteos leídos y comparación

Ambas bases tienen el mismo esquema en las siete tablas de usuario examinadas.
Los contadores internos incorrectos aparecen también en el backup.

| Tabla | Principal leídas / contador | Backup leídas / contador | Filas exactamente comunes | Solo principal | Solo backup |
|---|---:|---:|---:|---:|---:|
| Clientes | 1.613 / 1.609 | 990 / 987 | 887 | 726 | 103 |
| Clientes 2004 | 137 / 137 | 137 / 137 | 137 | 0 | 0 |
| Codigos_Postal | 339 / 339 | 339 / 339 | 339 | 0 | 0 |
| DETALLE | 19.661 / 19.631 | 11.478 / 11.464 | 11.468 | 8.193 | 10 |
| Detalle 2004 | 762 / 762 | 762 / 762 | 762 | 0 | 0 |
| Errores de pegado | 1 / 1 | 1 / 1 | 1 | 0 | 0 |
| Facturas | 5.108 / 3.906 | 2.933 / 1.734 | 2.928 | 2.180 | 5 |

Todos los códigos de cliente del backup existen en el principal: los 103 clientes no
idénticos son cambios sobre claves existentes, no clientes perdidos. Hay 623 códigos
nuevos. No se importa el backup como segunda base.

La cobertura de fechas de DETALLE es 2003-05-09 a 2026-10-05 en el principal y
2003-05-09 a **2016-06-23** en el backup. El apelativo «backup 2018» no acredita la fecha
de sus últimos datos ni su fecha de creación. Los conteos anuales previos facilitados
no representaban todas las filas extraídas: el comparador emite los conteos completos
de fechas, incluidas líneas de claves incompletas y fechas con hora.

## Claves, fantasmas y cabeceras

La diferencia **296 frente a 281** queda resuelta sin atribuirla a corrupción:

- 281 filas de DETALLE tienen FACTURA NULL; ninguna tiene COD_CLI NULL.
- Otras 15 tienen algún cero: 10 solo FACTURA cero, 3 solo COD_CLI cero y 2 ambos.
- El recuento anterior usó una condición de valor falso (`not value`), que mezcla cero
  y NULL. Cero es una clave escalar completa, aunque deba revisarse su significado.
- El cliente de código cero no existe. No se inventa para importar las líneas.

En Facturas hay 57 filas de clave incompleta: 52 con COD_CLI NULL y número presente,
3 con ambos campos NULL y 2 con cliente presente/número NULL. La consulta del programa
«Borrar Fantasmas» aporta evidencia para clasificar las 55 con COD_CLI NULL, pero no
justifica borrar sus originales. Los 3 registros totalmente vacíos constituyen el caso
más claro de cabecera sin contenido. Se conserva toda fila y su decisión.

Las 5.051 filas de cabecera con clave completa representan 5.043 claves. Los **7 grupos
duplicados tienen 8 filas adicionales**: seis grupos de dos y uno de tres. La tabla
solo contiene COD_CLI y FACTURA; todas las cabeceras de esos grupos son idénticas.
Es seguro representar cada grupo mediante un histórico y conservar todas sus filas
de origen. El grupo adicional de tres filas totalmente NULL pertenece a cuarentena,
no a las siete claves completas.

Hay **45 cabeceras completas sin líneas**. Se preservan como históricos incompletos,
sin conceptos ficticios, fecha elegida ni importes cero. Los 82 errores previos de
fecha/cabecera se explican por esas 45 cabeceras más 37 cabeceras con fechas en conflicto.

Hay **103 claves completas de líneas sin cabecera, con 333 líneas**. El recuento 99
excluía otras cuatro claves que contienen cero. De las 103, 101 tienen un código de
cliente presente y 2 no; la existencia de cliente no garantiza que su nombre sea válido.
Ninguna de estas líneas encuentra una cabecera completa en el backup. Una cabecera
derivada de la clave compuesta es una reconstrucción de identidad documentada; no
acredita fecha de emisión, cuota, total, pago ni impresión original.

En 20 números FACTURA de las líneas completas aparecen varios COD_CLI. El filtro del
informe por FACTURA solamente no demuestra unicidad global. Debe mantenerse la clave
compuesta, sin fusionar facturas de clientes distintos por compartir número.

De las 281 líneas sin número, 81 tienen un candidato único en el backup que coincide
en todos los demás campos; **la línea completa candidata ya existe en el principal en
los 81 casos**. Rellenar su número produciría repeticiones. Otras 3 tienen candidatos
en más de una factura y 197 no tienen ninguno. No hay recuperación automática segura
con esta regla; se conservan las filas sin atribuirlas a una factura arbitraria.

## Fechas ambiguas

Las 38 claves completas con varias fechas se mantienen como conflictos explícitos,
con sus candidatos originales. El máximo es tres fechas distintas.

- 27 ya tienen varias fechas en el backup, con exactamente el mismo multiconjunto
  de líneas que en el principal. No son una alteración posterior de esta copia.
- 11 no existían en el backup.
- Una de las 38 claves carece de cabecera, de ahí las 37 cabeceras afectadas.

El backup no aporta una fecha única original que permita resolver ninguna de las 38.
Elegir mínimo, máximo, mayoría o la primera fila no tendría evidencia suficiente.

## Matrículas compartidas

Se confirman **105 matrículas normalizadas compartidas por 218 filas**, todas con
varios códigos de cliente; máximo cuatro filas. En el backup, 52 ya estaban compartidas,
12 aparecían para un solo cliente y 41 no aparecían.

Por fechas de facturación de los códigos implicados, 42 grupos tienen intervalos
disjuntos, 42 presentan solapamiento y 21 no tienen fechas suficientes para todos los
códigos. Hay 18 grupos con el mismo nombre no vacío y 10 con el mismo NIF no vacío.
Estos agregados se solapan; no se suman entre sí.

Los intervalos corresponden al **cliente**, no a una matrícula guardada en cada factura.
Ni el orden temporal ni un nombre/NIF repetido prueban transferencia de un vehículo
o identidad duplicada. Tampoco la foto de un solo titular en el backup prueba quién
es el propietario actual. La decisión segura es conservar asociaciones y evidencia
sin insertar un titular actual inventado. `vehicle_owners` requiere evidencia o una
resolución explícita antes de asignar una cronología; los demás vehículos pueden avanzar.

## Tablas llamadas «2004» y clientes incompletos

Las dos tablas «2004» son idénticas entre ambos MDB y compatibles con copias congeladas,
pero su etiqueta no define el corte: Detalle 2004 contiene fechas hasta **2005-02-01**
(217 líneas de 2003, 466 de 2004 y 79 de 2005).

Los 137 códigos de Clientes 2004 siguen presentes en Clientes: 75 filas son idénticas
y 62 muestran cambios. Los campos cambiados incluyen datos de contacto y vehículo;
cuatro filas cambian el nombre y cuatro el NIF. Se conserva esta versión histórica;
no se crean otros 137 clientes ni se reemplaza silenciosamente la ficha actual.

De las 762 líneas de Detalle 2004, 758 ya existen exactamente, conservando multiplicidad.
Las otras cuatro pertenecen a una clave que sigue en DETALLE pero carece de cabecera.
Tres tienen un candidato de la misma clave que difiere en concepto, precio y total;
la cuarta tiene varios candidatos y también difiere en cantidad. Ninguna de las cuatro
es idéntica a DETALLE del backup. Sin identidad estable de línea, no se puede probar
si fueron corregidas, sustituidas o retiradas: conservar la versión y no añadirlas
automáticamente a la factura. La misma cautela aplica a las diez líneas exclusivas
del DETALLE del backup, agrupadas en dos claves ya presentes.

Los 18 clientes incompletos tienen código pero no nombre. Nueve aparecen en el backup
y uno en Clientes 2004; **ninguna fuente aporta el nombre ausente**. Dos tienen facturas
y líneas; 16 no tienen facturación. Solo uno carece de todo contenido salvo el código.
Por tanto no se clasifican indiscriminadamente como basura, no se inventan nombres y
las relaciones afectadas permanecen revisables en su evidencia.

## Decisiones y límites

Se puede consolidar únicamente la duplicidad exacta de cabeceras completas; preservar
cabeceras vacías e históricos sin importes; recuperar identidad compuesta desde líneas
cuando exista un cliente importable; y aislar las identidades no resolubles sin impedir
el resto del lote. Cada decisión del importador necesita su fila original, regla y
conteo, con conciliación independiente. El comparador no modifica ni aplica estas reglas.

Esta evidencia estructural no reconstruye IVA, redondeo, deuda ni total impreso.
Los hallazgos de objetos Access y las pruebas del importador/modelo se documentan por
separado. Las salidas privadas de la extracción y ambos originales se conservan para
revisión local; no se adjuntan a este informe ni se publican.
