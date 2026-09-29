# Revisión de dependencias y licencias — 23/09/2026

Consultas ejecutadas sobre dependencias instaladas/locks de esta entrega; no constituyen
una garantía de ausencia de vulnerabilidades desconocidas.

| Consulta | Resultado | Evidencia |
|---|---|---|
| `npm audit --json` | 0 avisos de vulnerabilidad, código 0 | `npm-audit-final-2026-09-23.json` |
| `uv tool run pip-audit --path .venv/lib/python3.13/site-packages --format=json --output reports/python-audit-final-2026-09-23.json` | 41 distribuciones, ninguna vulnerabilidad conocida detectada, código 0 | JSON indicado |
| `build/audit-tools/bin/cargo-audit audit --file src-tauri/Cargo.lock --db build/rustsec-advisory-db --format json` | 543 dependencias; 0 categoría vulnerabilities, **7 advertencias**; código 0 | `cargo-audit-final-2026-09-23.json` y stdout completo |

Cargo Audit 0.22.2 instalado localmente en `build/audit-tools`, con lock. Base RustSec:
1.264 avisos, commit `f7dc4b2860b29978f400fda0aab31cc4dbd21134`, actualizada 22/09/2026.
El stdout conserva dos avisos de lectura de un certificado del sistema; la descarga y
consulta de la base RustSec sí concluyeron. El JSON no se usa para ocultar esos avisos.

## Advertencias Rust conservadas

- `proc-macro-error` 1.0.4: RUSTSEC-2024-0370, sin mantenimiento.
- `unic-char-property`, `unic-char-range`, `unic-common`, `unic-ucd-ident`,
  `unic-ucd-version` 0.9.0: RUSTSEC-2025-0081/0075/0080/0100/0098, sin mantenimiento.
- `glib` 0.18.5: RUSTSEC-2024-0429, implementación insegura de `VariantStrIter`.

GLib procede de GTK3/WebKit del escritorio Linux. El árbol Cargo del objetivo
`x86_64-pc-windows-msvc` no contiene GLib. Corregir a GLib >=0.20 no es una actualización
compatible de la cadena GTK0.18 actual de Tauri. Se conserva el aviso, sin exclusiones de
Cargo Audit ni afirmación de auditoría limpia. La revisión de alcance y los árboles
quedan en el informe de escritorio. No se sustituye esa revisión por una prueba de Windows.
Fuente primaria: https://rustsec.org/advisories/RUSTSEC-2024-0429.html .

## Licencias de distribución

`scripts/prepare_licenses.py` recoge los avisos del entorno de construcción real y genera
`backend/taller/legal/manifest.json` con hashes. Incluye versiones Python/npm/Rust,
modelos OCR/voz, lector Access/JRE, reglas EN16931, esquemas y fuentes PDF. Acerca de permite
exportar un ZIP con los textos y el manifiesto, verificado antes de entregarlo.

`tools/legal/SOURCES.md` identifica las fuentes correspondientes, las excepciones de
licencia del JRE y los componentes incluidos por OpenCV. Los recursos se distribuyen
sin modificar. La herramienta opcional de construcción `@napi-rs/lzma-linux-x64-gnu`
1.5.1 declara MIT pero carece de texto LICENSE en su paquete/repositorio de esa versión:
se registra expresamente y no se inventa un copyright. No se incorpora como biblioteca
ejecutable al instalador. El inventario final se regenera durante el empaquetado, por lo
que sus cifras y hashes deben tomarse de la salida final del builder.

## Revisión de superficie

- Pruebas de rutas ZIP/ZIP64, XML externo, CSV/HTML/SQL, enlaces remotos Access,
  límites, recursos corruptos, certificados y restauración están en la batería backend.
- PDF de escritorio se analiza antes de abrirlo; exportaciones verifican todos los bloques
  y SHA final. El enlace externo permitido se restringe a la preparación de WhatsApp.
- `reports/frontend-api-contract-review-2026-09-23.json`: 96 acciones literales de
  interfaz comprobadas contra 128 acciones registradas; ninguna ausente. Es inspección
  estática, complementada por E2E, no una prueba funcional equivalente.
- Las pruebas usan datos sintéticos. No se han publicado datos, buscado credenciales
  ni enviado documentos a AEAT o mensajes a clientes.
