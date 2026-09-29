# PDF: texto, fuentes y revisión visual — 23/09/2026

## Defecto reproducido y corrección

El renderizador Helvetica perdía caracteres fuera de su codificación: `Łukasz Петров sintético`
aparecía como `■ukasz ■■■■■■ sintético` al extraer el texto; `Łódź` tampoco se conservaba.
Se incorporan DejaVu Sans normal/negrita 2.37, TTF sin modificar, licencia oficial y manifiesto
SHA-256 en `backend/taller/fonts/`. No depende de las fuentes instaladas en Windows.
ReportLab incorpora al PDF los subconjuntos utilizados, con texto seleccionable.

Se comprueban los glifos antes de emitir y al renderizar: si falta un carácter, se conserva
el borrador y se muestra el carácter/código Unicode, sin sustituirlo ni consumir número.
Las fuentes no cubren todos los alfabetos Unicode. Esta validación evita un PDF silenciosamente
incorrecto; no translitera nombres ni inventa letras. Los PDF emitidos ya conservados siguen
leyéndose de su caché inmutable; la actualización no los regenera.

## Ejecución

Entorno Ubuntu x64, Python 3.13.2, ReportLab 4.4.9, pypdf 6.19.0. Datos sintéticos.

```bash
.venv/bin/python -m pytest tests/test_pdf_layout.py --junitxml=reports/pytest-pdf-unicode-2026-09-23.xml
.venv/bin/python scripts/pdf_samples.py --output reports/pdf-layout-unicode-2026-09-23
pdftoppm -scale-to 1200 -png -singlefile reports/pdf-layout-unicode-2026-09-23/factura.pdf reports/pdf-layout-unicode-2026-09-23/factura
pdftoppm -scale-to 1200 -f 7 -png -singlefile reports/pdf-layout-unicode-2026-09-23/multipagina.pdf reports/pdf-layout-unicode-2026-09-23/multipagina-ultima
```

- 12 pruebas correctas en 1,12 s, código 0. Regresión de nombres/conceptos en polaco,
  griego y cirílico; fuentes embebidas; rechazo sin consumir número ni registro fiscal.
- Se mantienen pruebas de conceptos largos, diez grupos de IVA, precisión de precios,
  rectificativas, histórico incompleto y caché inmutable.
- Muestras generadas: factura 1 página / 53.259 bytes; multipágina 7 / 86.955 bytes;
  rectificativa 1 / 53.447 bytes. Hashes en el manifiesto de esa carpeta.
- Imágenes de factura y última página de la multipágina inspeccionadas: cabecera/QR
  separados, columnas legibles, totales sin recorte y pie/numeración dentro del margen.
- Esto verifica generación y revisión visual, no impresión física ni fidelidad de un
  controlador de impresora de Windows.

Procedencia de fuentes y licencia: https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37

y https://dejavu-fonts.github.io/License.html .
