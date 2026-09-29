# Campos, menú de Configuración y Asistencia · 29/09/2026

Segunda revisión visual del día, posterior a `MEJORAS-INTERFAZ-2026-09-29.md`.
Cambios de aplicación limitados a `web/style.css` y `frontend/settings.tsx`.
Sin cambios de backend, base de datos, dependencias o locks. Pruebas con datos sintéticos
y directorios temporales; no se abrió ni modificó una base operativa.

## Cambios y causa

- **Campos con ayuda**: `.form-grid` alineaba sus celdas por el borde inferior. La ayuda
  formaba parte de la altura de una celda, desplazando el campo vecino. Ahora las filas
  alinean sus celdas por arriba; `.align-end` conserva explícitamente la colocación inferior
  de acciones como Todo el día en Agenda. No se ocultan ayudas ni se fijan alturas de texto.
- **Menú de Configuración**: posición sticky al alcanzar `1rem` del borde superior,
  altura limitada a la ventana y desplazamiento interior en pantallas bajas. El foco queda
  dentro del botón y no se recorta. En los diseños de una columna el menú vuelve al flujo
  normal, sin tapar el formulario. Cambiar de sección desde abajo muestra su comienzo.
- **Asistencia**: separación de `1rem` entre botón y aviso en Configuración, incluida la
  respuesta opcional del diagnóstico. Se conserva el espacio posterior del aviso.
- **Accesibilidad**: el logo provisional ya tenía nombre accesible sobre un `span`; se le
  añadió `role="img"` para que ese nombre tenga una semántica válida.

Puntos de implementación: `web/style.css:1462` (filas), `web/style.css:2173` (menú),
`web/style.css:2241` (espacio), `frontend/settings.tsx:705` (navegación) y
`frontend/settings.tsx:70` (logo).

Se revisaron las instancias de Field/Input con ayuda en cliente, serie, datos del taller,
valores habituales, copias, asistencia y documentos. El patrón de varias columnas afectaba
especialmente a Prefijo/Continuidad, NIF/Correo, Provincia/País y Nombre fiscal/NIF.
El resto usa el mismo estilo compartido o dispone sus ayudas en una columna.

## Comprobaciones visuales y accesibilidad

Mediciones guardadas en [visual-checks.json](ui-alignment-2026-09-29/visual-checks.json):

- Prefijo y Continuidad: diferencia vertical **0 px**.
- NIF/Correo y Provincia/País del cliente: diferencia vertical **0 px**.
- Menú: pasa de y=241,09 a **y=16 px** al bajar. En ventana de 380 px de alto, su área
  desplazable mide 348 px y la última opción queda visible entre y=318 e y=364. Enter
  abre la sección con su título a y=16,09, sin tener que subir manualmente.
- Asistencia: **16 px** entre el botón y el aviso.
- Axe: cero infracciones y ninguna revisión manual pendiente en serie, cliente y asistencia.

[responsive-checks.json](ui-alignment-2026-09-29/responsive-checks.json) registra letra de
20 px a 1600, 1280, 1024, 390 y 320 px de ancho, sin desbordamiento horizontal. En 1600 px
se conserva el menú lateral sticky a 20 px y la alineación fiscal/NIF; el resto adopta el
diseño de una columna con el menú sobre el contenido. La revisión inicial de Axe encontró el atributo del logo;
tras corregirlo, [axe-settings-final.json](ui-alignment-2026-09-29/axe-settings-final.json)
contiene cero infracciones y ninguna revisión pendiente en Configuración a 320 px.

Capturas inspeccionadas:

- [Serie](ui-alignment-2026-09-29/series-fields.png) y [cliente](ui-alignment-2026-09-29/customer-fields.png).
- [Menú al bajar](ui-alignment-2026-09-29/settings-sticky.png) y [ventana baja](ui-alignment-2026-09-29/settings-short-window.png).
- [Asistencia](ui-alignment-2026-09-29/assistance-spacing.png).
- [Letra muy grande](ui-alignment-2026-09-29/settings-extra-1600.png) y [móvil de 320 px](ui-alignment-2026-09-29/settings-extra-320.png).

## Comandos y resultados

Ubuntu 24.04.5 x86_64, Node 22.22.2, Python 3.13.2, Rust 1.98.1 y SDK GTK/WebKit privado
en `/tmp/canamo-ui-sdk`. Logs en `reports/ui-alignment-2026-09-29/`.

| Comprobación | Resultado | Evidencia |
|---|---|---|
| `npm run typecheck` | Código 0 | `typecheck.log` |
| `npm run typecheck:e2e` | Código 0 | `typecheck-e2e.log` |
| `npm run build` | Código 0; Vite 1,23 s | `build.log` |
| `npm run test:e2e` | 38 correctas, 0 fallos/omitidas/flaky; 103,138 s | `e2e.log`, `e2e-results.json` |
| `npm run test:e2e -- e2e/accessibility.spec.ts e2e/interface-polish.spec.ts` | 8 correctas tras el último ajuste semántico del logo; 30,2 s | `e2e-accessibility-final.log` y JSON |
| `cargo +1.98.1 build --locked --manifest-path src-tauri/Cargo.toml` | Código 0, 4,32 s; interfaz final embebida | `tauri-build-final.log` |
| `desktop_smoke.py` sobre ese ejecutable | Código 0; siete comprobaciones nativas | `desktop-final/result.json` |

Cargo y el smoke se ejecutaron con las mismas variables de SDK/GTK y argumentos descritos
en el informe de interfaz anterior, usando `--output reports/ui-alignment-2026-09-29/desktop-final`.
No se repitió pytest: no cambió el backend. Las 438 pruebas anteriores conservan su fecha;
no se presentan como una nueva ejecución de esta revisión.

El primer typecheck detectó la nulabilidad del nuevo ref y se corrigió su contrato. La
primera batería E2E terminó con 37 correctas y un fallo del helper de selección: al pasar
rápidamente entre dos selectores, su búsqueda CSS incluía también una opción de la lista
que estaba desapareciendo. `e2e/fixtures.ts` ahora selecciona la lista accesible indicada
por `aria-controls` del campo activo. No se utiliza `.first()`, no se eliminan aserciones
ni se cambian las animaciones para ocultar el fallo. El log y la traza fallidos se conservan
en `e2e-first.log` y `agenda-first-failure/`.

## Límites

Se verificó Tauri real en Linux, no Windows/WebView2. Las acciones de abrir/imprimir del
smoke usan receptores de ensayo y no acreditan papel ni un lector físico. La accesibilidad
se comprobó en los recorridos descritos; no equivale a certificación completa.
Las comprobaciones externas de `CONTINUAR.md` siguen vigentes.

Huellas de los archivos modificados, `dist` y binarios finales:
[artifacts.json](ui-alignment-2026-09-29/artifacts.json).
