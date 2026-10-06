# Importación histórica incompleta · navegador · 6 de octubre de 2026

Pruebas con SQLite nueva por caso y datos exclusivamente sintéticos. No se abrió la
base real desde el navegador ni se incluyeron datos del taller en capturas, trazas o ZIP.

`e2e/access-partial-import.spec.ts` ejecuta desde la interfaz:

- Carga de paquete de tablas que reproduce identidades incompletas, matrícula compartida,
  cabecera duplicada, cabecera ausente, factura sin líneas, número cero, fecha conflictiva,
  concepto vacío, precisión de cuatro decimales y tablas históricas sin mapear.
- Selección automática del modo de conservación; vista de incidencias agrupada y
  advertencia de casos pendientes, sin desplegar cada incidencia individual.
- Simulación sin fichas/documentos en destino; importación explícita y conciliación.
  Se comprueban cuatro históricos seguros, importes desconocidos, deuda desconocida,
  dos candidatos de fecha y dos importes de línea `0.0050` sin redondeo.
- Descarga del informe con decimales originales, línea sin atribuir y versión de tabla
  no mapeada. Reversión desde la interfaz y documento conservado como `import_reverted`.
- Segundo caso con **MDB nativo** generado por Jackcess y contador interno alterado
  exclusivamente en la fixture: dos filas recorridas, contador uno, aviso visible y
  cero incidencias bloqueantes al mapear.

La pantalla recorrida a 1024×768 pasa Axe con etiquetas WCAG 2 A/AA y 2.1 AA, sin
infracciones. Se inspeccionó la captura sintética de conciliación; no equivale a una
auditoría de toda la aplicación ni a pruebas Windows o de impresión física.

Comandos ejecutados:

```text
npm run build
  → typecheck correcto; build Vite correcto, 1,61 s.

npx playwright test e2e/access-import.spec.ts e2e/access-partial-import.spec.ts --reporter=list
  → los dos casos Access anteriores y el caso MDB con contador obsoleto correctos.
    El primer intento del caso parcial detectó una aserción incorrecta del test:
    documents.list no expone pending_cents. El test se corrigió para comprobar
    paid_cents en el listado y pending_cents mediante documents.get para cada factura.

npx playwright test e2e/access-partial-import.spec.ts --reporter=list
  → 2 correctas, 16,8 s, 0 fallos.

npm run typecheck:e2e
  → código 0 después de corregir la aserción.
```

El test CSV anterior se adapta para abrir primero «Revisar incidencias individuales
y sus claves», ahora recogido en un desplegable. Conserva todas sus comprobaciones de
vinculación explícita y conservación de la ficha existente.

La revisión independiente del modo parcial detectó claves de cliente duplicadas que
mostraban cero bloqueos pero fallaban al simular; se comunicó al responsable del
importador para corregir la clasificación y añadir su regresión de backend. Este
informe acredita los recorridos indicados, no sustituye la batería general posterior.
