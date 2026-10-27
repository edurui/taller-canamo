# Comprobaciones externas para la puesta en marcha

Especificación principal: `PROMPT_MAESTRO_TALLER_CANAMO.md`. Consultar primero
`docs/ESTADO-VERIFICADO.md`: allí consta qué versión de las pruebas/artefactos se ejecutó.
La edición de desarrollo conserva sus avisos de prueba y no debe usarse para facturar
operativamente. Los siguientes pasos requieren medios o datos que no están disponibles
en este entorno; no son instrucciones para volver a programar los módulos.

## Preparación Windows y copia de ensayo · 27/10/2026

Copia cifrada actual creada, restaurada y comparada: 1.598 clientes, 1.292 vehículos
y 5.145 históricos; 22 tablas y 36 recursos idénticos. También restaurada desde la
interfaz. El Access actualizado completo conserva las incidencias pendientes como
evidencia; no se resuelven identidades ni importes por suposición. Contraseña local
separada de la entrega. El traslado definitivo permanece sin activar.

Build real en el workflow público existente, solo con código y datos sintéticos.
Sobre `8dcf8ad` pasaron servicio/818 pytest/164 E2E/16 Rust en Windows, pero NSIS
fue rechazado por Cargo.toml CRLF/LF; reproducido y corregido conservando hashes.
Sobre `2eb0e90`, servicio y 818 pytest correctos, 163 E2E correctas y una selección
alterada por un puntero inmóvil bajo el popup. Corregida en controles/buscador con
regresión real: typechecks/build y tres dirigidas correctos. 819 pytest (107,51 s) y 166 E2E
locales completas (4,1 min) correctas, sin omitidas ni flaky. El build ejecuta ahora toda la batería de navegador
antes de empaquetar y detiene el primer fallo; todas las pruebas siguen exigidas.
Ningún instalador aceptado. Detalle: `reports/PREPARACION-WINDOWS-2026-10-27.md`.

El usuario confirma disponer de un archivo Personal Information Exchange: no se
ha recibido ni validado. Configurarlo en el Windows de destino y comprobar vigencia
y legitimación; no enviarlo al chat ni incluirlo en Git/copias generales. Mantener
los bloqueos de emisión y los requisitos del expediente fiscal.

## Access actualizado en la prueba local · 27/10/2026

La copia persistente de `npm run start` ya incorpora 3 clientes, 2 vehículos y 12
históricos nuevos: totales 1.598 / 1.292 / 5.145. Intervalo solicitado desde 05/10;
altas de facturas con fecha única entre 09 y 26/10. No volver a importar todo ni
reemplazar SQLite. Si el preview sigue abierto, basta recargar la interfaz.

Dos facturas nuevas quedan pendientes por cambio de nombre y NIF en sus códigos de
cliente. El usuario ha elegido conservarlas pendientes; no sobrescribir las fichas
ni atribuirles las facturas sin aclarar la identidad. Una matrícula ya registrada
y dos líneas sin número también quedan documentadas aparte. Comparaciones e importes
por factura están en el expediente privado de actualización, fuera de Git.

Informe sanitizado, comprobaciones y límites: `reports/ACCESS-ACTUALIZACION-2026-10-27.md`.
El MDB conserva las mismas fórmulas y sigue sin guardar los importes finales. Las
estimaciones no son contraste con papel/PDF y no habilitan cobros ni fiscalidad.

## Listados ordenables y acciones · 08/10/2026

Implementadas cabeceras ascendente/descendente/original en las 21 tablas de datos,
ordenación global antes de paginar y filas navegables con acciones por entidad.
Se conservan referencias interiores, protecciones de documentos, teclado y
confirmaciones. Resúmenes agrupados sólo ordenables; sin acciones ficticias.
Corregidos filas antiguas tras errores, última página después de archivo/borrado,
desbordamiento móvil y margen del foco en los menús.

**809 pytest y 164 E2E completas** correctas, sin omitidas ni reintentos. Typechecks,
build, pip check y diff check correctos; 80 casos Python y 24 E2E nuevos. Sólo
sintéticos, sin migración/índice/dependencia nueva. Evidencias y límites de rendimiento:
`reports/LISTADOS-2026-10-08.md`. La pasada global interrumpida por cambio de permisos
se repitió entera; copia final idéntica por hashes y eliminada tras guardar evidencias.

Detener el preview anterior con Ctrl+C y ejecutar `npm run start`: el backend debe
reiniciarse para aceptar `sort_by`/`sort_direction`. No reimportar ni tocar SQLite.
Sin commit/push; pendiente ensayo Windows/WebView2 del paquete actualizado.

## Importes coherentes y resumen de consulta · 08/10/2026

Inicio, cliente, vehículo y búsqueda histórica reutilizan el importe de Facturas con
procedencia visible. Informes incorpora originales/contrastados/estimados disponibles,
sin doble cómputo, con desconocidos aparte y exportación equivalente. Se conserva el
desglose fiscal original y la semántica de pagos, deuda, PDF y snapshots. Sin esquema
nuevo ni modificación de bases reales. Las cantidades estimadas siguen siendo orientativas.

**729 pytest y 140 E2E** completas correctas, typechecks/build/pip check y diff check
correctos. Verificación visual/Axe claro/oscuro, 1366/390 px. Informes completo p95
27,064 ms con 5.000 históricos y 270,251 ms con 30.000, exclusivamente sintéticos.
Informe: `reports/IMPORTES-INFORMES-2026-10-08.md`. Se conservaron pruebas/evidencias
anteriores y se eliminó la copia temporal E2E tras comprobar hashes idénticos.

Reiniciar Ctrl+C → `npm run start` para cargar frontend/backend; no hay que reimportar.
Sin commit/push. Sigue pendiente ensayo Windows/WebView2 del paquete actualizado.

## Nombre del cliente vinculado en facturas · 08/10/2026

Listado, detalle, Inicio y facturas de un vehículo muestran el nombre de la ficha
actual cuando falta el nombre original; conserva prioridad el snapshot cuando existe.
La búsqueda aplica el mismo criterio. Los originales no se rellenan ni modifican.
712 pytest y 130 E2E completas correctas, typechecks/build correctos, sólo sintéticos.
Detalle: `reports/FACTURAS-CLIENTE-2026-10-08.md`. Reiniciar con Ctrl+C y `npm run start`
para cargar frontend y backend; sin nueva migración. Cambios anteriores conservados,
sin commit/push. Windows/WebView2 no ejecutado en esta corrección.

## Históricos: revisión separada verificada · 08/10/2026

Implementados estados Estimada/Pendiente/Contrastada, filtro, ajuste con motivo,
confirmación documental explícita, historial y restablecimiento. Propuesta general
16/18/21 % por fecha, con hipótesis y redondeo visibles; no sobrescribe originales ni
habilita pagos/fiscalidad/rectificaciones. v9, índices/proyección y materialización
atómica; importación, reversión, copias y portable conservan las revisiones por separado.
Corregidos los tres espacios/alineaciones/nombre del cliente en detalle de factura.

708 pytest y 129 E2E finales correctas, typechecks/build/pip check correctos. Sólo datos
sintéticos; ocho auditorías Axe y capturas revisadas. Apertura p95 12,926 ms con 5.000
históricos. Informe y fallos intermedios: `reports/HISTORICOS-REVISION-2026-10-08.md`.
E2E final sobre copia aislada idéntica por hashes, eliminada después de guardar evidencia.

Para verlo, detener el preview anterior y ejecutar `npm run start`. La base anterior
se migra con copia previa; no hay que reimportar Access. No se aplicó a bases reales
durante las pruebas. Queda reconstrucción/ensayo Windows y contraste documental humano;
no presentar los importes estimados como originales acreditados. Sin commit ni push.

## Guardado directo al arrastrar en Agenda · 08/10/2026

Mover/alargar y soltar guarda sin modal; clic/teclado abren edición. Escape cancela.
Se comprueban errores, versiones, citas borradas, recurrencias, navegación durante
guardado y cambios horarios. 631 pytest y 118 E2E finales correctas, typechecks/build y
pip check correctos, sólo datos sintéticos. Informe: `reports/AGENDA-DRAG-2026-10-08.md`.
La prueba completa final usa una copia aislada con hashes idénticos para evitar otra
recompilación simultánea de la previsualización. Los resultados previos se conservan.

Reiniciar la previsualización con `npm run start` para cargar frontend y backend nuevos.
El paquete Windows requiere reconstrucción y ensayo real; estas pruebas son Linux/Chromium.
Sin commit ni push. Esta revisión sustituye el flujo anterior de confirmar el arrastre
desde el formulario; mantiene la corrección visual del agarre.

## Control de duración de Agenda · 08/10/2026

El agarre inferior ya no pinta una franja opaca sobre la cita. Mantiene arrastre,
confirmación de duración y teclado; dos pruebas nuevas verifican presentación y
accesibilidad en Día/Semana, claro/oscuro y escritorio/ventana estrecha.
14 pruebas dirigidas y 106 E2E completas correctas; typechecks/build correctos.
Sólo datos sintéticos y cambios frontend, sin nueva ejecución de pytest.
Detalle: `reports/AGENDA-RESIZE-2026-10-08.md`. Recargar la previsualización para verlo;
el ensayo Windows/WebView2 requiere reconstruir y probar el paquete actualizado.

## Sidebar verificado · 07/10/2026

Despliegue de «Más herramientas» animado y accesible; logo/pie fijos, sin scroll en
768/900 px con letra normal/grande. En alturas menores sólo se desplaza el menú.
104 E2E correctas, incluidas ocho nuevas; 13 auditorías Axe, capturas revisadas,
typechecks y build correctos. Datos exclusivamente sintéticos. Informe:
`reports/SIDEBAR-2026-10-07.md`. Sin cambios backend ni nueva ejecución de pytest.

Para el ensayo externo, reconstruir el paquete y comprobar también abrir/cerrar el
lateral con las escalas de pantalla de Windows y movimiento reducido. Esta evidencia
de Chromium/Linux no sustituye Windows/WebView2 real. Cambios locales sin commit ni push.

## Direcciones CartoCiudad verificadas · 07/10/2026

Autocomplete opcional en alta/edición de clientes, con servicio Python y entrada manual
siempre disponible. Caché/debounce, privacidad, teclado y guardado con proveedor pendiente
probados: 628 pytest, 96 E2E, typechecks/build/pip check correctos. Solo datos sintéticos;
no se han utilizado bases reales en esta revisión. Detalle y límites:
`reports/DIRECCIONES-2026-10-07.md`; uso y contrato en `docs/DIRECCIONES.md`.

Para el ensayo Windows hay que reconstruir el paquete desde estas fuentes y comprobar
Nuevo cliente/Editar cliente con Internet y sin él, además del teclado y guardado durante
consulta. La evidencia actual del adaptador Tauri es simulada en navegador y del protocolo
JSONL en Python; no equivale a ejecutar Windows/WebView2. No usar el binario previo como
si contuviera esta función. Los cambios permanecen locales, sin commit ni push.

## Agenda, navegación y cabecera verificadas · 07/10/2026

Mes cuadrado, hora de Madrid coherente, cabecera sticky y referencias de entidades
con formularios protegidos. Suite final: 547 pytest / 68 E2E correctas, typechecks/build,
cinco pruebas Rust y check/clippy completo para Windows. Benchmarks mantienen Clientes
en 3,9 ms de mediana de apertura; originales intactos. Informe conjunto:
`reports/USABILIDAD-AGENDA-NAVEGACION-2026-10-07.md`.

Pendiente externo específico: instalar y probar el aviso en Windows real (sonido,
silencio, No molestar, clic con borrador y ventana en bandeja). No confundir el check
cruzado con una ejecución de Windows. Comandos y límites en
`reports/NOTIFICACIONES-AGENDA-2026-10-07.md`.

## Clientes: rendimiento verificado · 07/10/2026

Consultar `reports/CLIENTES-PERFORMANCE-2026-10-07.md`: mediciones antes/después sobre el
ensayo de 1.595 clientes y un sintético de 15.000, contratos, EXPLAIN y pruebas.
La optimización está en `6be3445`; las mejoras posteriores permanecen locales, sin push.
Para revisar la versión actual desde el repositorio:

```bash
npm run start
```

El comando compila y abre el navegador usando `.venv` automáticamente. La copia privada
persistente está en `${XDG_DATA_HOME:-$HOME/.local/share}/taller-canamo-preview/data`,
fuera de Git, y contiene los datos completos importados. Abrir Clientes, paginar, filtrar
y abrir una ficha. El origen `$HOME/.canamo-access-codex-rehearsal-20261006-b/data` permanece
intacto; la ruta temporal anterior ya no se utiliza. `Ctrl+C` detiene el servicio.
Los cambios realizados desde la interfaz permanecen en esta copia entre arranques.
La verificación nueva es de servicio Python y navegador; no reutilizar los binarios
nativos anteriores como evidencia de esta revisión visual.

## Windows e impresión

En Windows 11 x64 de desarrollo, seguir `docs/BUILD-WINDOWS.md`: dependencias fijadas,
construcción completa y, para el ensayo de puesta en marcha, `--release-candidate`.
Instalar y ensayar el candidato exacto en una cuenta/VM limpia: actualización/reinstalación,
DPAPI, instancia única, cierre/bandeja/notificaciones, copias/restauración y una impresora.
Registrar resultados reales y hashes. El workflow preparado es manual; no se ha publicado
ni ejecutado en un runner remoto. No desactivar antivirus o SmartScreen.

Usar las fuentes actuales del 07/10/2026: el ZIP del 23/09 no contiene la revisión visual
ni la migración del Access real.
Comprobar también los tres tamaños de letra con las escalas de Windows, los selectores y
calendarios a pantalla completa en ventana estrecha, el cierre de modales anidados y el
orden de líneas en la vista previa/lector PDF. La evidencia Linux y de navegador está en
`reports/MEJORAS-INTERFAZ-2026-09-29.md`; no sustituye esa prueba de WebView2.

## Certificado, emisor y productor

Instalar mediante el selector local un certificado legítimo del titular/representante;
configurar identidades confirmadas y revisar la declaración responsable. Ejecutar solamente
el ensayo autorizado AEAT en el entorno oficial de pruebas, conforme a
`docs/FISCAL-LIBERACION-2026-09-23.md`. Conservar altas, subsanaciones, anulaciones y consultas
con sus respuestas auténticas. No adjuntar certificado, contraseña, XML identificativos o
expediente privado al repositorio ni al chat.

La aplicación valida el expediente contra los intercambios reales, versión, esquemas y
bytes del servicio ensayado. Instalarlo con la CLI documentada, comprobar el diagnóstico y
activar producción solo después de completar todas las verificaciones. Una constante,
un checkbox o un acuse sintético no autorizan la activación. No reconstruir el binario
después de ensayarlo sin repetir la verificación correspondiente.

## Access real: ensayo local de 06/10/2026

Los dos originales ya se han investigado sin modificarlos. Informe principal:
`reports/ACCESS-REAL-2026-10-06.md`; análisis estructural y VBA en los informes enlazados.
No volver a aplicar el requisito antiguo de totales completos a este MDB: usar el perfil
sugerido de conservación parcial y la relación postal. Los importes desconocidos son
NULL/«No consta», no cero; no reconstruir todo el archivo al 21 %.

Resultados conciliados: 1.595 clientes, 1.290 vehículos, 5.133 históricos y 19.335 líneas.
Se conservan las 27.621 filas raw. Quedan para revisión 18 clientes, 222 referencias
de vehículos, 70 registros/candidatos de histórico y 326 líneas sin atribución segura;
38 históricos importados tienen fecha conflictiva y 45 carecen de fecha. Son conflictos
reales preservados, no aceptación fiscal ni un corte de producción.

Para revisar al volver, usar la copia privada preparada del ensayo, desde el proyecto:

```bash
npm run start
```

Configuración → Traer datos → lote del ensayo → motivos agrupados, registros originales
y conciliación. Los ensayos A y C fueron revertidos y conservan evidencia; B queda importado para
inspección local. No usar ninguno como carpeta operativa. La carpeta de diagnóstico
anterior `.canamo-access-prueba` se ha conservado.

Quien conoce el taller debe acreditar las titularidades de 105 matrículas compartidas,
las identidades incompletas y, si se quiere completar el histórico monetario, aportar
documentos impresos/periodos/criterios de redondeo verificables. El código recuperado del
informe no acredita por sí solo lo que se imprimió en cada época. No es necesario resolver
estas cuestiones para consultar los registros importados con sus datos desconocidos.

El corte final y la última factura en Access siguen requiriendo confirmación física con
el propietario. Obtener entonces una copia cerrada reciente, revisar diferencias con el
mismo origen/perfil y acordar la serie nueva por separado. No se deduce del máximo importado.

## Contrato público B2B

Revisar la publicación definitiva del perfil/servicio público de intercambio y sus pruebas
oficiales, según `docs/B2B-FUENTES-2026-09-23.md`. UBL 2.1, validación real EN16931, recepción,
conservación, estados y exportación funcionan localmente; ello no acredita entrega a un
servicio cuyo contrato final no se ha localizado. VERI*FACTU y B2B mantienen estados separados.

## Copia o traslado a otro equipo

Usar `docs/COPIAS-TRASLADO.md` y el manual `LEEME.md`. No copiar SQLite mientras está abierta
ni sincronizar la base activa. El traslado autorizado inactiva la emisión del origen y
requiere activación del destino; restaurar una copia antigua no autoriza retroceder series
o repetir envíos. Reinstalar el certificado en el nuevo usuario/equipo cuando proceda.
