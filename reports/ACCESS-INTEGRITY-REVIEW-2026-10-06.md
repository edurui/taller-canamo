# Revisión independiente del importador parcial · 6 de octubre de 2026

Revisión de atribución, conservación de evidencia, decisiones por fila y contratos de
importación en `access_partial.py`, `access_mapping.py`, `access_writer.py`,
`access_imports.py` e interfaz de importación. Los casos nuevos son exclusivamente
sintéticos y están en `tests/test_access_partial_review.py`.

Se reprodujeron y corrigieron antes del cierre de esta revisión:

- Una identidad de cliente duplicada en la nueva copia podía reutilizar la vinculación
  de una importación previa y asignarle una factura nueva. La ambigüedad presente ahora
  impide esa atribución, aunque exista un cliente previamente importado.
- La exclusión explícita de una factura no actualizaba las decisiones de sus filas.
  Cabeceras y líneas quedan marcadas como excluidas con la regla correspondiente.
- El modo parcial ignoraba una clave explícita de vehículo fiable. Ahora conserva el
  vínculo cuando está resuelto; cuando el vehículo está en cuarentena, conserva el
  histórico sin asignarlo y advierte de la titularidad/identidad no resuelta.
- El número de factura canónico admitía NULL, booleanos y objetos por conversión a
  texto. Esos valores se rechazan; no se crean números ficticios por `str(...)`.
- La normalización del desglose fiscal mutaba el objeto de origen, introduciendo
  valores por defecto en la evidencia original. La normalización trabaja sobre copias.
- La procedencia de importes podía ser una cadena no JSON que rompía la lectura del
  documento. El contrato rechaza esa forma antes de persistirla.

Comando después de las correcciones:

```text
.venv/bin/python -m pytest tests/test_access_partial_review.py -q
.......... [100%]
10 passed in 2.36s
```

La prueba de cobertura del informe genera 281 líneas con clave incompleta, 45 líneas
dependientes de un cliente no importable y una línea segura. Verifica los 327 originales
exactos y las 327 decisiones exportadas, con los motivos correctos. Las líneas apartadas
siguen en la evidencia; no se convierten en importes cero ni se atribuyen arbitrariamente.

## Comprobación independiente de los ensayos reales

Se abrieron **solo para lectura** las SQLite de staging de los ensayos locales A y B.
No se volvieron a ejecutar importaciones ni se mostraron filas o identificadores reales.
Los dos ensayos ofrecen los mismos resultados de cobertura:

| Comprobación | Resultado en cada ensayo |
|---|---:|
| Filas originales de todas las tablas | 27.621 |
| Filas originales de DETALLE | 19.661 |
| Líneas con decisión individual | 19.661 |
| Líneas originales sin decisión | 0 |
| Decisiones de línea sin original correspondiente | 0 |
| Líneas mapeadas desde cabecera existente | 19.007 |
| Líneas mapeadas con cabecera recuperada | 328 |
| Líneas apartadas por clave incompleta | 281 |
| Líneas apartadas por cliente no resuelto | 45 |

Para cada ensayo se comparó el multiconjunto completo de `raw_rows` y de `row_decisions`
con las secciones correspondientes de `report.jsonl`, mediante huellas calculadas solo
en memoria local: **ambas comparaciones son idénticas en A y B**. El informe completo
incluye también las tablas no mapeadas. No se publican esas huellas ni el informe privado.

La conciliación de históricos importados sigue separada de la resolución de los casos
apartados. Estos resultados no resuelven el IVA histórico, la titularidad ambigua ni
las fechas conflictivas, y no equivalen a validar la aplicación en Windows.
