# Registro de trabajo · actualizado el 04/11/2026

## Entrega privada con datos · 04/11/2026

Preparados EXE con datos locales y manual de 24 páginas con índice pulsable.
Copia real: 33 tablas y 36 recursos verificados sin modificar el origen.
Windows `41816215691`: carga/reinstalación/rechazos correctos con datos ficticios,
app sin recompilar; 58 pruebas locales dirigidas y calidad correctas. El certificado
no está disponible aquí según el usuario. Emisión real y corte de Access pendientes.
Detalle: `../reports/INSTALADOR-CON-DATOS-2026-11-04.md`.

## Cierre Windows · 04/11/2026

Instalador de `0e4b4d0` comprobado en Windows Server 2025: construcción completa
`41802145854` (843 Python/166 E2E/16 Rust) y verificación nativa `41810156535`
correcta en 1 min 54 s, sin recompilar. Diagnóstico instalado y cinco controles
Tauri/WebView2, hashes y 206 entradas verificados; 57 regresiones locales de las
correcciones de pruebas. Ver `../reports/REANUDACION-WINDOWS-2026-11-04.md`.
Candidato de ensayo; persisten los pasos físicos/fiscales y de corte para uso real.
Los apartados anteriores en el tiempo se conservan como antecedentes.

Fase posterior de calidad: usuario autoriza rama y workflow Windows. Prettier,
ESLint, Ruff, rustfmt y Clippy correctos; 842 Python y 166 E2E/Axe tras el formato,
typechecks/build/pip check correctos y fuentes estables. Exclusión del driver externo
validada después con calidad y 28 casos dirigidos. Seguimiento de publicación y
Windows: `../reports/CALIDAD-WINDOWS-2026-11-04.md`. Lo siguiente conserva la fase previa.

Revisión de entrega: verificación final actual correcta (841 Python/166 E2E,
typechecks/build/pip check, sin fallos, omisiones, reintentos ni cambios de fuentes).
Auditadas y corregidas seis
dependencias; las auditorías npm/Python posteriores no detectan vulnerabilidades
conocidas. RustSec no tiene entradas en `vulnerabilities`; conserva nueve avisos de
mantenimiento y dos `unsound` de API Unix/Linux, documentados con su alcance.
Corregida omisión de CSS y otros recursos del inventario, reproducida con control
negativo. Pasan 25 casos dirigidos y 18 pruebas Rust. Workflow preparado para
probar el EXE instalado y comparar sus bytes con el manifiesto. No se ha ejecutado
en Windows ni hecho push. El servicio empaquetado Linux supera nueve comprobaciones
con fuentes estables. Corregida paginación PDF, con 14 pruebas dirigidas y revisión
visual de nueve páginas. Batería integrada final cerrada con 287 entradas estables;
las 1.803 entradas del servicio empaquetado siguen coincidiendo con su manifiesto.
El instalador del 27/10 necesita reconstrucción; no reutilizarlo como versión
corregida. Datos reales intactos. Registro y cierre de esta revisión:
`../reports/REVISION-ENTREGA-2026-11-04.md`.

## Antecedentes del 27/10

Reanudación posterior: `40579253295` sí generó e instaló el NSIS de `10bb937` tras
819 pytest/166 E2E correctas. Falló la conexión WebDriver a la ventana; no se acepta
todavía el ensayo nativo. EXE conservado y verificado por hash, 124 entradas de
fuentes coincidentes. Nueva batería local completa correcta (819 Python/166 E2E,
typechecks/build/pip check) y ocho pruebas de la guarda de reutilización. Copia real
comparada de nuevo en solo lectura: 22 tablas idénticas, integridad/FK y hashes
correctos. Herramientas para repetir Windows preparadas, autorización de publicación
solicitada. Ver `../reports/ENTREGA-WINDOWS-2026-10-27.md`.
Lo que sigue conserva el historial anterior a esta reanudación.

Preparación de entrega Windows: copia cifrada real restaurada y verificada,
Windows ha superado servicio/818 pytest/164 E2E/16 Rust en un intento anterior,
pero NSIS fue rechazado por CRLF/LF de Cargo.toml, reproducido y corregido. Sobre
`2eb0e90`, servicio/818 pytest correctos y un fallo entre 164 E2E: puntero inmóvil
bajo la segunda sugerencia alteró la selección. Corregidos controles/buscador con
regresión real; typechecks/build y tres dirigidas correctos. Correctas: 819 pytest (107,51 s) y
166 E2E locales completas (4,1 min), sin omitidas ni flaky. La batería completa de navegador pasa ahora antes del
empaquetado, con parada al primer fallo. Sin instalador aceptado todavía. Detalle:
`../reports/PREPARACION-WINDOWS-2026-10-27.md`.

Actualización incremental del Access nuevo aplicada únicamente a la prueba local:
3 clientes, 2 vehículos y 12 históricos con 38 líneas. Los datos previos permanecen
intactos; ensayo de repetición sin duplicados y comprobación del navegador correctos.
Dos facturas quedan pendientes de identidad por decisión del usuario. Estado actual
y análisis de importes: `ESTADO-VERIFICADO.md` y
`../reports/ACCESS-ACTUALIZACION-2026-10-27.md`. La matriz inferior es histórica.

La revisión de interfaz del 29/09 está al final de este documento y en
`reports/MEJORAS-INTERFAZ-2026-09-29.md`. La matriz siguiente conserva el cierre anterior.

Especificación: `PROMPT_MAESTRO_TALLER_CANAMO.md`. Implementación y revisión locales cerradas.
La puesta en marcha operativa requiere las verificaciones externas de ESTADO-VERIFICADO.md.
No se declara aptitud fiscal por compilar ni se sustituye Windows por una web.

## Matriz de cierre

| Área | Implementación y evidencia actual | Dependencia restante |
|---|---|---|
| Dependencias | Locks; npm/Python sin vulnerabilidades conocidas; licencias exportadas; Cargo con 7 advertencias documentadas | Mantener seguimiento upstream, sin ocultar GLib Linux |
| Clientes/vehículos | Búsqueda, país, paginación, titularidad, teléfono y km sin carreras; 5 E2E dirigidas incluidas en 32; p95 117,084 ms con 15k/30k | Datos reales de migración |
| Facturas/cobros | Borradores, idempotencia, números/snapshots, cobros/devoluciones, relaciones y R2/R3 | Configuración real y aceptación fiscal |
| Ajustes/series | Defaults, tarifa, continuidad/ejercicio, selección de serie y protección de usadas | Confirmar identidad/serie de arranque con el taller |
| PDF | Unicode embebido, A4 1/7/1 páginas, históricos desconocidos, caché, apertura/impresión IPC | Lector/impresora y papel Windows |
| Herramientas secundarias | Presupuestos/órdenes, proveedores/stock, informes y exportación portable probados | Ninguna programación pendiente identificada |
| Agenda | Vistas, excepciones/serie, teclado/arrastre/duración, DST Madrid y avisos | Avisos físicos, bandeja, reinicio Windows |
| UX/accesibilidad | 32 E2E con axe, claro/oscuro/texto grande, ventanas 1024/1366 y capturas revisadas | Escalas/locale/notificaciones de Windows |
| Escritorio | Servicio completo verificado, 18 Rust, Tauri real/8 comprobaciones y selector GTK con copia cifrada por bloques | Build/instalación/actualización real Windows |
| Windows | Scripts/workflow/locks, NSIS/WebView2 y diagnóstico instalados preparados; bug de informes corregido con regresión | Equipo Windows autorizado; ningún EXE Windows inventado |
| VERI*FACTU | XSD/hash/QR, cola/Consulta/correcciones, certificado TLS, candidato/expediente y guion autorizado | Certificado/identidad legítimos, pruebas AEAT y revisión del productor |
| B2B | UBL2.1 + EN16931 real, recepción original, estados y exportación; 1.000 documentos medidos | Contrato público definitivo y casos especiales documentados |
| Access | MDB/ACCDB nativos, perfiles/mapeo/lotes/conciliación/rollback, bases sintéticas reales | Esquema/incidencias del MDB/ACCDB original y corte acordado |
| Copias/traslado | AES/streaming/ZIP64, restauración y fallos, original 2 GiB y selector nativo 3,76 MB | Prueba de destino Windows del taller |
| Asistencia | OCR/Vosk reales, revisión humana, historial/mensajes, jobs sin bloquear servicio | Micrófono/condiciones reales; Ollama opcional no instalado |
| Entrega | Manuales, fuente empaquetable, hashes, matriz y revisión final actualizados | Solo pasos externos de CONTINUAR.md |

## Resultado integrado

`reports/final-verification-2026-09-23/result.json`: seis comandos con código 0, fuentes
estables, 438 pytest y 32 Playwright correctos, sin omitidas ni flaky, ambos typechecks y build.
`reports/desktop-final/result.json`: 8 comprobaciones nativas correctas sobre binarios finales.
No repetir toda la batería sin cambios o un riesgo concreto. Las próximas pruebas deben
centrarse en las dependencias externas; si se modifica código, verificar el área afectada
y reconstruir los artefactos antes de atribuirles una aceptación.

## Decisiones conservadas

- Sin `.git`, remoto, despliegue o datos reales en pruebas. Referencias privadas excluidas.
- Arquitectura React/TypeScript/Tauri/Python/SQLite mantenida; núcleo local sin suscripción.
- OCR/voz y lector Access se empaquetan; Ollama rechaza modelos remotos antes de enviar notas.
- Un dato histórico ausente sigue desconocido, incluidos cobros, IVA, cantidades y emisor.
- Exportar datos no activa otro emisor. El traslado protege series/cadena y desactiva origen.
- Transportes simulados no crean procedencia mTLS. Una constante no habilita producción.
- Guardas de impresión, copia y publicación conservadas; errores corregidos sin debilitar tests.
- El fallo del último selector era del harness: extensión duplicada. Se corrigió su selección,
  se mantuvieron las aserciones y se conservó el intento fallido.
- El manifiesto anterior queda en `docs/MANIFEST-HEREDADO-SHA256.json`; los hashes actuales
  están en informes de verificación/empaquetado y en el ZIP de fuentes.

Matriz detallada por requisito: `reports/revision-flujo-final-2026-09-23.md` y
`reports/ENTREGA-2026-09-23.md`. Relevo semántico: `docs/CAMBIOS-RELEVO.md`.


## 29/09/2026 · Revisión de interfaz verificada localmente

- Encargo: transiciones de modales, estabilidad del buscador, controles compartidos con
  selectores/calendarios a pantalla completa en móvil, espaciado/alineación, tamaño de
  letra destacado y persistente, orden de líneas y proporción del icono Configuración.
- Base local: build correcto y 438 pytest correctas (77,06 s), con datos sintéticos.
- Implementados `frontend/controls.tsx` y `frontend/overlays.tsx`; migración de controles
  en todas las pantallas. Se conservan los controles nativos de archivos, casillas y rango.
- Buscador conserva resultados mientras actualiza, bloquea selección obsoleta y mantiene
  la protección frente a respuestas tardías. No se han cambiado backend ni datos reales.
- Ordenación con identidad local por línea, arrastre, botones y teclado; identidad excluida
  del RPC. Primer E2E nuevo verifica importes, guardado, reapertura y texto/orden del PDF.
- Ajuste existente normal/grande/muy grande destacado, previsualización reversible y
  guardado mediante la configuración persistente existente. Sin migración SQLite.
- Verificados foco inicial/restaurado, paneles anidados, tamaños móviles, Axe y regresiones
  completas. Corregidos cierre/reapertura rápida, clics que atravesaban la animación,
  liberación de micrófono, colocación del calendario y botón Historial y titular recortado.
- Final: 38 E2E correctas (178,012 s), sin omitidas/flaky; ambos typechecks, build y
  comprobaciones de dependencias correctos. Backend sin cambios desde las 438 pytest.
- Tauri Linux reconstruido (2 min 41 s), siete comprobaciones nativas correctas sobre
  datos sintéticos. Se limpió la configuración GTK heredada de VS Code Snap para ejecutar
  el driver y se corrigió el harness para esperar al servicio antes de borrar su SQLite.
- Inspección adicional del PDF nativo: Xvfb sin DRI3 dibujaba mal el lienzo acelerado;
  el PDF original y su render Poppler eran correctos. El harness usa renderizado por
  software sólo con `--xvfb`; lienzo WebKit completo correcto y smoke repetido.
- Evidencia de iteraciones conservada en `reports/ui-2026-09-29/`. Windows/WebView2 y
  papel no disponibles: no se declaran ensayados. El ZIP anterior no contiene este frontend.

## 29/09/2026 · Ajustes posteriores de campos y Configuración

- Corregido `align-items: end` de los formularios comunes; las ayudas ya no desplazan
  sus campos vecinos. `.align-end` conserva las acciones que sí van abajo.
- Menú lateral sticky con límite de altura, scroll interior y retorno al principio de
  la sección seleccionada; menú de una columna conserva el flujo en pantallas estrechas.
- Asistencia separa el botón de su aviso. Logo provisional con rol de imagen accesible.
- 38 E2E correctas; ocho de interfaz/accesibilidad adicionales tras el último atributo.
  Typechecks/build correctos; Tauri reconstruido y siete comprobaciones nativas correctas.
- El helper E2E usa `aria-controls` para distinguir el selector activo de otro en salida;
  se conserva el fallo previo y su traza. No se cambió el comportamiento para pasar el test.
- Informe, capturas y límites: `reports/AJUSTES-ALINEACION-2026-09-29.md`.
