# Revisión de interfaz · 29/09/2026

Cambios locales sobre React/TypeScript/Tauri, manteniendo Python/SQLite y los datos del
usuario intactos. Se trabajó con bases temporales sintéticas. Sin servicios externos para
datos del taller, publicación, instalación global de dependencias ni modificación fiscal.

## Resultado por petición

| Petición | Implementación y comprobación |
|---|---|
| Modales agradables y breves | Entrada de 160 ms y salida de 140 ms; opacidad/desplazamiento suave, movimiento reducido, foco y fondo inerte compartidos. Cierre/reapertura rápida y doble clic protegidos. |
| Buscador sin parpadeo | La lista permanece montada mientras llega la siguiente respuesta; conserva foco y navegación. Opciones antiguas bloqueadas hasta el resultado actual. Indicador de espera sólo tras 250 ms. |
| Alineación y espaciado | Vehículo/km/alta alineados; botones sin partir palabras; barra PDF se redistribuye; separación en ficha y Resumen; corregido el recorte de Historial y titular. |
| Controles comunes | Texto, número, textarea, select, sugerencias y fecha usados en todas las pantallas. Archivos, casillas y rango mantienen su comportamiento nativo. |
| Calendario | Meses y días en castellano, selección directa de año/mes/día, años por bloques, teclado, Hoy/Borrar, min/max y hora cuando corresponde. Se conserva entrada manual ISO mediante el control nativo. |
| Móvil | Buscadores, selectores y calendarios ocupan la pantalla hasta 640 px; cabecera con cierre, desplazamiento propio y foco contenido. |
| Orden de líneas | Arrastre del asa, botones subir/bajar y flechas de teclado. Identidad estable; orden inmediato de líneas/importes y posterior PDF. Persistencia y texto real del PDF comprobados. |
| Tamaño de letra | Acceso destacado en Configuración, Normal/Grande/Muy grande (16/18/20 px), muestra, prueba inmediata y guardado persistente. Salir sin guardar restaura el tamaño anterior. PDF A4 conserva sus medidas. |
| Icono Configuración | Alto/ancho iguales y sin contracción en el sidebar. |

## Causas y decisiones

El buscador vaciaba sus resultados al cambiar la consulta, desmontando el desplegable
durante el debounce y la petición. Ahora separa texto escrito y consulta resuelta, conserva
la lista y su nodo DOM, y descarta respuestas tardías mediante el contador existente. No
se permite entrar en una ficha antigua mientras se resuelve la búsqueda nueva.

`frontend/overlays.tsx` concentra Modal, Popup, Presence y la pila de foco/inert. La salida
retiene el contenido sólo para animarlo: los controles quedan inertes y los trabajos de
dictado se cancelan inmediatamente con `useClosing`. La generación del contenido cambia
al reabrir, evitando recuperar un formulario anterior durante esos 140 ms. El fondo
saliente absorbe un segundo clic para no ejecutar una acción de la pantalla inferior.

`frontend/controls.tsx` conserva los contratos value/onChange y la validación de formulario.
El select mantiene su control nativo oculto para la semántica de formulario, y usa una
lista accesible visible. Los E2E interactúan con esa lista; no se fuerzan valores ocultos.
El calendario respeta fechas bisiestas y límites; el formato de escritura manual depende
del sistema/navegador. El autocompletado de conceptos conserva texto libre y tarifa sugerida.

Cada línea de borrador tiene una clave estable local, excluida de calculate/save. Moverla
actualiza también el orden de `totals.lines` y marca cambios pendientes, sin recalcular ni
alterar importes por el mero movimiento. La vista previa guarda antes de generar el PDF.
No se modifica el orden de facturas emitidas ni sus snapshots.

El tamaño de letra ya tenía soporte persistente; se ha convertido en una opción clara,
con prueba reversible y diseño adaptado. No se añadió otra preferencia ni migración.

## Verificación ejecutada

Entorno: Ubuntu 24.04.5 x86_64, Python 3.13.2 en `.venv`, Node 22.22.2, npm 10.9.7,
Rust 1.98.1, Chromium de Playwright 1.63.0 y WebKitGTK/WebKitWebDriver 2.52.6.
No existe `.git` en esta carpeta. Locks y dependencias de aplicación no modificados.

Los logs indicados están en [ui-2026-09-29](ui-2026-09-29/).

| Comando/prueba | Resultado final | Evidencia |
|---|---|---|
| `.venv/bin/python -m pytest` | 438 correctas en 77,06 s; ejecutadas al inicio, backend sin cambios después | `baseline-pytest.log` |
| `npm run typecheck` | Código 0 | `typecheck.log` |
| `npm run typecheck:e2e` | Código 0 | `typecheck-e2e.log` |
| `npm run build` | Código 0; Vite 1,13 s, 40 módulos | `build-final.log` |
| `npm run test:e2e` | 38 correctas, 0 fallos/omitidas/flaky; 178,012 s | `e2e-final.log`, `e2e-final-results.json` |
| `npm ls --depth=0` | Código 0 | `npm-dependencies.log` |
| `.venv/bin/python -m pip check` | Sin incompatibilidades, código 0 | `python-dependencies.log` |
| Build Tauri Linux con Cargo bloqueado | Código 0; 2 min 41 s | `tauri-build-final.log` |
| `desktop_smoke.py` con Tauri/sidecar reales | Código 0; siete comprobaciones | `desktop/result.json`, `desktop-smoke.log` |

Las seis pruebas nuevas de `e2e/interface-polish.spec.ts` comprueban orden de líneas,
cantidades e importes, identidad fuera del RPC, guardado/reapertura y texto/orden del PDF;
calendario bisiesto, año/mes/día, teclado, mínimo y foco; tamaños persistentes tras reinicio,
selectores móviles en claro/oscuro; modales anidados y movimiento reducido; espaciado,
alineación y adaptación a 1280/1024/780/390/320 px. Se mantienen las regresiones anteriores
de doble clic, agenda, importaciones, fiscalidad, micrófono y protección de borradores.

Axe pasa con etiquetas WCAG 2 A/AA, 2.1 AA y 2.2 AA en los recorridos auditados, incluidos
calendario, selector, móvil, editor y Resumen. No es una certificación de accesibilidad
completa ni cubre todas las combinaciones de lector de pantalla/sistema.

Capturas inspeccionadas:

- [Ficha de cliente](ui-2026-09-29/customer-desktop-final.png).
- [Calendario de escritorio](ui-2026-09-29/calendar-desktop-final.png).
- [Letra muy grande a 320 px](e2e/artifacts/interface-polish-espacios--18ad0-rande-en-ventanas-estrechas/letra-extra-320.png).
- [Calendario móvil](e2e/artifacts/interface-polish-letra-per-c4fd0-talla-completa-light-390-px/calendario-movil-light.png).
- Resto de capturas y adjuntos Axe en `reports/e2e/artifacts/` y `reports/e2e/html/`.

## Prueba nativa Linux

Se extrajeron los paquetes de desarrollo GTK/WebKit y drivers oficiales de Ubuntu en
`/tmp/canamo-ui-sdk`, sin instalarlos globalmente. Cargo se ejecutó con el SDK privado:

```bash
PATH="/home/eruizgarcia/.cargo/bin:$PATH" \
PKG_CONFIG_PATH=/tmp/canamo-ui-sdk/usr/lib/x86_64-linux-gnu/pkgconfig:/tmp/canamo-ui-sdk/usr/share/pkgconfig \
LIBRARY_PATH=/tmp/canamo-ui-sdk/usr/lib/x86_64-linux-gnu \
cargo +1.98.1 build --locked --manifest-path src-tauri/Cargo.toml

env -u GIO_MODULE_DIR -u GTK_EXE_PREFIX -u GTK_IM_MODULE_FILE \
  -u GTK_PATH -u GTK_MODULES -u GSETTINGS_SCHEMA_DIR \
  LD_LIBRARY_PATH=/tmp/canamo-ui-sdk/usr/lib/x86_64-linux-gnu \
  PATH="/home/eruizgarcia/.cargo/bin:$PATH" \
  .venv/bin/python src-tauri/tests/desktop_smoke.py \
  --application src-tauri/target/debug/taller-canamo \
  --driver /home/eruizgarcia/.cargo/bin/tauri-driver \
  --native-driver /tmp/canamo-ui-sdk/usr/bin/WebKitWebDriver \
  --xvfb /tmp/canamo-ui-sdk/usr/bin/Xvfb \
  --test-document-handlers --output reports/ui-2026-09-29/desktop
```

El smoke verifica ventana y API Tauri, demo por IPC, búsqueda normalizada/teléfono/ficha,
PDF del servicio empaquetado, botones abrir/imprimir y error visible, rechazo de contenido
o acciones no permitidas e instancia única. Usa Xvfb, bus y rutas de usuario aisladas.
`xdg-open/lpr` se sustituyen por receptores de ensayo: no abren un lector ni imprimen papel.
El selector GTK real de guardado, ensayado el 23/09, no se repitió en esta revisión.

Se conservan los fallos intermedios. Los de interfaz se corrigieron, sin retirar sus
aserciones: foco antes de colocar el popup, anchura mínima del calendario, cierre del
dictado, doble clic durante la salida, reapertura del formulario y medición durante la
animación. El test antiguo que exigía vaciar la lista se actualizó al comportamiento
solicitado, manteniendo la protección contra resultados obsoletos y añadiendo continuidad
del nodo DOM. Las esperas de dimensiones comprueban el tamaño final, sin quitar transiciones.

El primer intento nativo falló por cargar bibliotecas GTK heredadas de VS Code Snap;
se limpiaron esas variables sólo para el proceso de prueba. El segundo alcanzó la captura
final y falló al borrar SQLite antes de terminar su servicio. Se corrigió el harness para
esperar su finalización, identificando exclusivamente la ruta temporal de esa sesión.
No se relajan aserciones, se ignoran fallos ni se tocan otros procesos del usuario.

La inspección posterior detectó dibujo incorrecto del PDF dentro de WebKit con aceleración
en Xvfb, que informa de ausencia de DRI3. El mismo archivo se ve correctamente al renderizarlo
con Poppler y en el visor WebKit con renderizado por software. El harness activa
`WEBKIT_DISABLE_DMABUF_RENDERER=1` y `WEBKIT_DISABLE_COMPOSITING_MODE=1` sólo cuando recibe
`--xvfb`; no cambia la aplicación instalada. El smoke final se ha repetido con ese ajuste.
Se conservan la captura original, el PDF sintético, el lienzo extraído del visor y la
comparación en `desktop-render-canvas/` y `desktop-render-software/`. La imagen completa
correcta está en [viewer-canvas.png](ui-2026-09-29/desktop-render-software/viewer-canvas.png).

## Límites y relevo

Windows/WebView2, escalas de Windows y papel siguen pendientes porque este entorno es
Linux. No se ha generado un instalador Windows ni se declara aceptación fiscal externa.
Las fuentes y el ejecutable Linux están actualizados; el ZIP del 23/09 es histórico y no
incluye esta revisión. El siguiente candidato Windows debe construirse desde las fuentes
actuales. Instrucciones concretas en `CONTINUAR.md` y `docs/BUILD-WINDOWS.md`.

Estado, criterios, progreso, relevo y manual actualizados. Inventario SHA-256 de las fuentes,
`dist` y binarios comprobados: [artifacts.json](ui-2026-09-29/artifacts.json).
