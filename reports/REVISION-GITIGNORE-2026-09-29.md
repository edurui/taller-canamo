# Revisión de .gitignore · 29/09/2026

Entorno: Ubuntu Linux, repositorio local recién inicializado por el usuario. Rama `main`,
remoto `origin` configurado; sin commits ni archivos añadidos al índice en la revisión.
No se ha contactado con el remoto, modificado el índice ni creado un commit.

## Cambios

- Excluidas capturas/sesiones de `.playwright-mcp/`, esquemas generados de Tauri, cachés
  de TypeScript/Python, cobertura y archivos temporales.
- Consolidadas las exclusiones de recursos generados de Access, modelos y licencias.
  Permanecen incluidas las licencias fuente de `tools/legal/` y los locks que permiten
  reconstruir estos recursos.
- Extendidas las reglas de bases a `.db` y sus journals, bloqueos de Access y extensiones
  de claves/certificados; coinciden también con extensiones en mayúsculas o mixtas.
  Se mantienen las exclusiones de `.env*` y referencias personales; se añaden directorios
  locales de datos, copias, exportaciones, PDF y credenciales en la raíz.
- `reports/` conserva los resúmenes Markdown y scripts Python situados directamente
  en esa carpeta. Sus subdirectorios, JSON, capturas, trazas, PDF y demás resultados
  automáticos permanecen en disco sin entrar en Git. README explica esta política.

## Comprobaciones ejecutadas

| Comando o comprobación | Resultado |
|---|---|
| `git status --short --untracked-files=normal`, `git ls-files`, `git rev-parse --verify HEAD` | Solo archivos sin seguimiento; índice vacío y sin primer commit |
| `git check-ignore --no-index -z --stdin`, alimentado mediante Python | 70 rutas que deben excluirse y 28 que deben incluirse: todas correctas |
| `scripts/package_source.py::source_files()` leído mediante `runpy`, contrastado con `git check-ignore` | 279 archivos fuente, ninguno ignorado; no se genera ni cambia el paquete |
| Inventario con `git ls-files --others --exclude-standard -z` y tamaños de los archivos | Antes: 669 archivos, 151.516.985 bytes. Después de ajustar las reglas: 301 archivos, 9.179.644 bytes, antes de añadir este informe y actualizar documentación |

Las rutas de comprobación incluyen bases SQLite y Access, claves, certificados,
archivos auxiliares, recursos generados, locks de npm/Cargo/Python, esquemas XML/XSD,
fuentes tipográficas, fixtures sintéticos, iconos, capabilities, CI y la excepción
`src-tauri/binaries/.gitkeep`. El tamaño candidato se reduce aproximadamente 135,7 MiB.

## Límites

Cambios de configuración Git y documentación: no se han repetido las pruebas de aplicación
ni la compilación. No se han borrado archivos ni abierto bases reales o credenciales.
La revisión comprueba rutas y reglas; no es una auditoría de secretos del contenido ni
del historial remoto. No había archivos versionados que retirar con `git rm --cached`.
