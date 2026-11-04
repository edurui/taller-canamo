# Formato, lint y candidato Windows · 04/11/2026

El usuario autorizó publicar los cambios en una rama nueva de
`edurui/taller-canamo` y ejecutar la construcción/pruebas Windows, después de
revisar lint y formato. Esta fase continúa la revisión de
`REVISION-ENTREGA-2026-11-04.md`; no sustituye los ensayos fiscales ni la impresión física.

## Cambios preparados

- Prettier 3.9.8, configuración explícita y comandos `format`/`format:check`.
  Formatea código propio TS/JS/CSS/JSON/HTML/YAML. Documentos históricos, datos
  privados, recursos generados y recursos de terceros fijados por hash quedan fuera.
- ESLint 10.14.0, `@eslint/js` 10.0.1, typescript-eslint 8.72.1 y globals 17.14.0,
  fijados en package-lock. Reglas recomendadas, cero advertencias permitidas.
  El contrato RPC existente `Row/any` se conserva y sigue bajo TypeScript strict;
  no se finge haber migrado toda la API a tipos concretos. La omisión intencionada
  de propiedades mediante object-rest se reconoce como tal. La única supresión
  local justifica el patrón vacío de fixture exigido por Playwright.
- Ruff 0.17.3 fijado con hashes en requirements-dev.lock: reglas E4/E7/E9/F,
  formato de Python y limpieza de imports/variables sin uso. No se aplicaron
  arreglos inseguros automáticos. Las llamadas cuyos resultados no se utilizaban
  se conservaron para mantener sus efectos.
- `scripts/quality.py` ejecuta seis controles de solo lectura: Prettier, ESLint,
  Ruff lint/formato, rustfmt y Clippy de la biblioteca sin features de escritorio,
  con advertencias tratadas como errores. Guarda comando, código, tiempo y log.
  Lo invocan la batería integrada y el constructor Windows antes de empaquetar.
  Una regresión comprueba que un fallo de calidad impide construir el candidato.
- Git normaliza el código propio a LF también en checkout Windows; CMD/PowerShell
  conservan CRLF y los recursos externos conservan bytes. La prueba de checkout
  con autocrlf valida TSX/CSS/JSON/YAML, además de los recursos y formatos previos.
- El inventario de construcción y el ZIP de fuentes incluyen el script de calidad
  y sus configuraciones. Los artefactos antiguos no acreditan estas fuentes.

## Comprobaciones y hallazgos

Entorno: Ubuntu Linux x86_64, Python 3.13.2, Node 22.22.2, npm 10.9.7,
Rust 1.98.1. Evidencias locales en `reports/calidad-windows-2026-11-04/`.

Antes de corregir lint, se compararon los AST de los 120 archivos Python existentes
antes/después de Ruff format: **cero cambios de estructura**. Los cambios de lint
posteriores se revisaron por separado. Rust ya cumplía rustfmt.

La comprobación opcional `prettier --debug-check` inicial encontró una salida que
necesitaba una segunda pasada y una excepción de la propia herramienta al serializar
BigInt. Se conserva ese resultado; no se presenta como verificación AST exitosa de
TypeScript. La aceptación usa `prettier --check`, TypeScript, build y E2E reales.

ESLint incorporó minimatch 10.2.6, afectado por
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
Se fijó el override 11.0.1, versión corregida del mismo proveedor. La ejecución
real de ESLint comprueba su compatibilidad con el proyecto. Auditorías npm y Python
posteriores: cero vulnerabilidades conocidas; Rust conserva los avisos ya
documentados en la revisión anterior. No se usó `npm audit fix --force`.

Comandos principales:

```text
npm run lint:fix
npm run format
.venv/bin/python -m ruff check --fix backend/taller scripts tests src-tauri/tests
.venv/bin/python -m ruff format backend/taller scripts tests src-tauri/tests
.venv/bin/python scripts/quality.py --report reports/calidad-windows-2026-11-04/quality
.venv/bin/python scripts/prepare_licenses.py
.venv/bin/python scripts/verify.py --report reports/calidad-windows-2026-11-04/final
```

Los seis controles de calidad pasaron. La batería integrada tras el formateo
terminó correctamente (09:27:51–09:44:18 Europe/Madrid): **842 pytest y 166 E2E**,
ambos typechecks, build y pip check, además de calidad. Cero fallos, errores,
omisiones o reintentos; fuentes estables. Pytest: 359,358 s; Playwright: 509,175 s.
Las licencias se prepararon antes de empezar para mantener estable la revisión.

Después se añadió la exclusión de `edge-driver/` (herramienta Microsoft descargada
para las pruebas Windows) a Git/formato. `.gitignore` queda cubierto también por
los inventarios y se amplía su regresión. Se comprueba la exclusión con un HTML
sintético: Prettier lo ignora correctamente. Repitieron correctamente los seis
controles de calidad y **28 pruebas dirigidas** del proceso de construcción,
reutilización y checkout (0,76 s, sin omisiones).
No cambia el código de la aplicación después de la batería funcional. Esa corrección
del proceso y sus comprobaciones se identifican aparte; Windows ejecutará toda la
batería sobre el commit final.

También pasó `cargo clippy --locked --target x86_64-pc-windows-msvc
--no-default-features --lib -- -D warnings` (3,03 s), con la versión Rust fijada.
Es análisis/compilación cruzada del código Windows, no ejecución de un EXE ni
prueba de WebView2. Las verificaciones nativas siguen pendientes del runner Windows.

## Publicación y Windows

Publicada la rama `codex/entrega-windows-2026-11-04`, commit
`0e4b4d05a5ec497d1a090fce0b7edfb4cb21c61b`, después de aprobar las comprobaciones.
206 archivos en el commit, incluidos los cambios revisados de la fase anterior.
`main` se conserva en `10bb9372544dfb581e77e9b652c85becc116a559`; no se fuerza push,
fusiona ni publica una release. El inventario no contiene bases, certificados,
.env ni private-reference. Autor del commit: cuenta personal con correo noreply,
sin cambiar la configuración global del usuario.

El conector GitHub creó la rama; Git publicó el commit y la CLI lanzó el workflow
manual mediante la sesión personal existente, sin imprimir ni guardar credenciales.
Run [41802145854](https://github.com/edurui/taller-canamo/actions/runs/41802145854),
job `126480256385`, sobre ese SHA, iniciado el 04/11 a las 09:46:57 Europe/Madrid,
`release_candidate=true`. Construcción y baterías completas correctas: 843 Python,
166 E2E, 16 Rust, seis controles de calidad y servicio congelado. Falló después
la comparación del EXE instalado; la causa y su corrección sin recompilar están
en `REANUDACION-WINDOWS-2026-11-04.md`. Todavía no se atribuye éxito al recorrido
nativo. Ver `windows-dispatch.json`, `windows-runs.json`
y `publish-source-proof.json` en el directorio local de evidencias.

Pendiente: candidato nuevo instalado y probado con WebView2; después, equipo del
taller/impresora, certificado legítimo y expediente de esos bytes, identidad/serie
y corte acordado desde Access. No se activan flags de producción ni se modifican
datos reales como parte de esta revisión.
