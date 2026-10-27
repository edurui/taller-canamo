# Estado verificado · 27 de octubre de 2026

## Entrega Windows en preparación · 27/10/2026

Creada y restaurada la copia cifrada real de los datos actuales: 1.598 clientes,
1.292 vehículos y 5.145 históricos, con el MDB actualizado completo conservado como
lote solo diagnosticado para preservar pendientes. Coinciden 22 tablas y 36 recursos;
reapertura, integridad/FK y auditoría correctas. Restauración desde la interfaz
comprobada, con datos tras recargar, sin errores JS ni violaciones Axe en el recorrido.
El destino nuevo conserva `transfer_required`; no se activó el traslado definitivo.

Corregidos requisitos del workflow, lectura UTF-8 de metadatos y conservación exacta
de recursos fijados por SHA-256, resolutores XML, fsync y permisos en Windows.
818 pytest y 164 E2E locales correctas; checkout Windows nuevo con 69 recursos
idénticos a sus hashes. Sobre `dabe244` han pasado
los dos casos de regresión, **814 pytest Windows**, ambos typechecks y el build.
La batería de navegador detectó seis incidencias del arnés (158 casos correctos),
corregidas en `b7d6da9`: UTF-8 explícito y esperas sobre la aplicación lista.
Sobre `8dcf8ad` ya pasan en Windows el servicio congelado completo, 818 pytest,
164 E2E y 16 Rust; Tauri compila, genera NSIS y supera el diagnóstico del conjunto.
La guarda final rechazó variaciones de entradas; en un clon se reprodujo que Tauri
convierte Cargo.toml CRLF a LF. Se fija su LF desde el checkout y se mantiene la
comparación byte a byte. Prueba corregida: 383 archivos intactos. Sobre `69035ab`
pasan herramientas WebDriver, regresiones iniciales, servicio congelado y 818 pytest
Windows (446,93 s). La batería E2E termina con 163 correctas y una espera agotada:
el arnés pulsa un elemento mientras su contenedor se está desplegando. Se espera
el final de las animaciones reales en el helper común; no se desactivan animaciones
ni se omiten aserciones. Cuatro casos dirigidos pasan con la transición ralentizada
a 1,2 s; batería local completa: 164 correctas (4,0 min), sin fallos, omitidas ni flaky.
Todavía sin instalador aceptado ni instalación/UI acreditadas.
Seguimiento, comandos,
evidencias, incidencias y límites: `reports/PREPARACION-WINDOWS-2026-10-27.md`.

## Access actualizado: altas incrementales de la prueba local · 27/10/2026

Aplicada a la previsualización persistente la selección nueva desde el 05/10/2026,
incluido, hasta el 27/10/2026: **3 clientes, 2 vehículos y 12 facturas históricas con
38 líneas**. Totales actuales: **1.598 clientes, 1.292 vehículos y 5.145 facturas**.
Se reutilizó el origen anterior y no se sustituyó ningún registro existente.
Los clientes nuevos se detectan por diferencia de claves: Access no conserva fecha de alta.

La copia nueva contiene 14 facturas nuevas, fechadas del 09 al 26/10. Dos utilizan
códigos cuyos clientes han cambiado de nombre y NIF; el usuario ha indicado dejarlas
pendientes. También quedan sin alta automática una matrícula ya asignada y dos líneas
nuevas del 13/10 sin número de factura. Los originales completos y el desglose privado
se conservan fuera del repositorio; no se atribuyen esas incidencias a otra persona.

Ensayo aislado, simulación, conciliación, idempotencia de un segundo lote, conservación
exacta de filas anteriores, integridad/FK y auditoría correctos. Aplicación mediante
RPC autenticado del preview abierto, con copia previa. Navegador real: 12 detalles de
factura, tres búsquedas de clientes y dos auditorías Axe sin violaciones. Sin cambios
de fuentes ejecutables ni dependencias; no se repitieron pytest/build/E2E sintéticas.

Forense actualizado: 15 objetos y 12 módulos VBA idénticos al MDB anterior. Cabeceras
sin base/IVA/total final; las 14 propuestas son estimaciones y se contrastaron con
aritmética decimal independiente. En destino quedan 5.046 estimadas y las mismas
99 pendientes de revisión anteriores. No se crearon cobros, deudas ni envíos fiscales,
ni se modificaron series. Informe: `reports/ACCESS-ACTUALIZACION-2026-10-27.md`.

## Lote para publicar en main · 27/10/2026

Agrupadas las mejoras del 7 y 8 de octubre para el commit/push solicitado por el
usuario. Las menciones «sin commit/push» siguientes corresponden a esas revisiones.
Ahora han pasado 809 pytest, ambos typechecks, pip check, el build inicial y 23
pruebas Rust. La repetición Python resolvió cinco errores causados por el bloqueo
de puertos del sandbox. A petición del usuario se detuvieron las comprobaciones
adicionales durante el segundo build; no se completó una nueva batería E2E.
Las 164 E2E del 08/10 siguen siendo evidencia anterior. Informe:
`reports/PUBLICACION-2026-10-27.md`.

Copia persistente comprobada en lectura inmutable: 1.595 clientes, 1.290 vehículos
y 5.133 facturas históricas; integridad/FK correctas. `npm run start` la reutiliza
y migra v8 a v9 con copia previa, sin reimportar Access. No se arrancó el servicio
sobre esa copia durante esta revisión. Windows/aceptación fiscal siguen pendientes.

**Migración del Access real implementada y ensayada localmente con conservación explícita
de datos desconocidos y conflictos.** Versión 0.9.1 de desarrollo: no apta todavía para
emitir facturas operativas. Quedan conflictos históricos que requieren evidencia humana
y las comprobaciones externas, sin atribuirles resultados locales. La revisión previa
de interfaz está documentada en
`reports/MEJORAS-INTERFAZ-2026-09-29.md`; la entrega del 23/09 es evidencia histórica.

## Listados ordenables y acciones por entidad · 08/10/2026

Las 21 tablas de datos permiten ordenar cada columna y recuperar su orden original.
Los listados paginados ordenan en SQLite antes de LIMIT/OFFSET; los conjuntos completos
se ordenan localmente. Las 15 tablas de entidades abren fichas por celda y ofrecen
menú de acciones, conservando enlaces interiores, teclado, confirmaciones y guardas.
Los seis resúmenes agrupados se ordenan sin inventar fichas ni acciones individuales.
Se descartan respuestas obsoletas y se bloquean filas antiguas durante carga/error.
Archivo/borrado de la última fila devuelve a una página válida. Sin nueva migración,
índice ni dependencia; sólo datos sintéticos, sin modificar bases reales.

Verificado: **809 pytest (66,99 s) y 164 E2E completas (289,217 s)**, cero fallos,
omitidos o reintentos finales. Typechecks, build, pip check y diff check correctos.
80 casos Python y 24 E2E nuevos; Axe y capturas de menús/tablas claro/oscuro en
1366/390 px, más regresión de navegación/Clientes a 320 px y texto grande.
1.869 archivos de ejecución idénticos por SHA-256; evidencia final guardada antes
de eliminar la copia E2E. Informe, rendimiento sintético y fallos intermedios:
`reports/LISTADOS-2026-10-08.md`. La interrupción por permisos de solo lectura se
resolvió repitiendo la batería completa; no se contó como ejecución correcta.

Consultas predeterminadas sin regresión material medida; ordenación explícita p95
6–31 ms en el escenario habitual y hasta 198 ms con 30.000 históricos. Son medidas
locales, no umbrales CI. Reiniciar `npm run start` para cargar frontend y backend.
Sin commit/push. Windows/Tauri/WebView2 real sigue pendiente de ensayo externo.

## Importes de facturas e Informes · 08/10/2026

Inicio, historial del cliente, facturas del vehículo y búsqueda de trabajos muestran
el mismo importe que Facturas: original prioritario, revisión etiquetada o «No consta».
Resumen suma los importes disponibles una vez por factura y separa originales,
contrastados y estimados por mes, con CSV equivalente. Desconocidos y sin fecha se
avisan aparte. El desglose fiscal original sigue accesible; las revisiones no crean
cobros ni deudas ni sobrescriben documentos. Sin nueva migración/índice/dependencia.

Corregidos presentación móvil, acceso por teclado a las tablas y ocultación de cifras
anteriores si falla un cambio de período, con reintento. Agregado SQL medido con
5.000/30.000 facturas sintéticas: informe completo p95 **27,064/270,251 ms**; los
listados no incorporan llamadas adicionales. Detalle, contrato, planes, mediciones y
fallos intermedios: `reports/IMPORTES-INFORMES-2026-10-08.md`.

Verificado: **729 pytest (58,35 s), 10 nuevas E2E dirigidas y 140 E2E completas
(192,601 s)**, sin fallos, omitidas ni reintentos finales. Pip check, typechecks/build
y diff check correctos; 17 nuevos casos Python, ocho auditorías Axe y revisión visual
claro/oscuro, 1366/390 px. Sólo sintéticos, fuentes/dist idénticos por SHA-256.
No se abrieron datos reales ni se ejecutó Windows/WebView2. Reiniciar `npm run start`
para cargar el backend y frontend nuevos; sin reimportación, commit ni push.
Esta sección amplía el resumen de consulta respecto a la evidencia histórica de
estimaciones siguiente; conserva intacto el cálculo fiscal original.

## Facturas: nombre del cliente vinculado · 08/10/2026

Si el histórico no conserva nombre original, el listado y el detalle muestran el
nombre enlazado de la ficha actual, sin el aviso que parecía indicar que faltaba cliente.
Mismo criterio en Inicio y facturas de un vehículo. Buscar encuentra ese nombre; si
existe nombre original, se conserva su prioridad. Sin rellenar snapshots ni modificar
facturas, PDF o datos reales. Se aprovecha el JOIN existente, sin peticiones por fila
ni migración adicional.

Verificado: **712 pytest (73,56 s), 21 E2E dirigidas y 130 E2E finales (199,204 s)**,
typechecks/build y diff check correctos. Cero fallos, omitidas o reintentos finales.
Cuatro casos Python nuevos y un E2E; ocho auditorías Axe y revisión visual en ambos
temas a 1366/390 px. Sólo datos sintéticos, copia E2E aislada idéntica por hashes.
Informe y expectativa antigua corregida: `reports/FACTURAS-CLIENTE-2026-10-08.md`.
Reiniciar `npm run start` para cargar también el campo nuevo del backend. Sin commit/push;
no se ejecutó Windows/WebView2. Las evidencias anteriores se conservan a continuación.

## Facturas históricas: estimación y revisión · 08/10/2026

Estimaciones separadas de originales: 16/18/21 % según los períodos generales;
importes calculados con decimales exactos y redondeo explícito, siempre identificados
como orientativos. Sin líneas/importes, con fechas inciertas o contradicciones quedan
pendientes, sin ceros ni sumas parciales. Ajustar exige motivo; contrastar con original
exige confirmación y evidencia. Historial inalterable, restablecimiento con motivo,
control de versiones y protección de formularios. Los originales, PDF, pagos, informes
y fiscalidad conservan su comportamiento; las estimaciones no habilitan cobros/rectificación.

Migración v9 transaccional, copia previa, proyección indexada y cola técnica. Probados
upgrade desde v8, base nueva, fallo atómico, restauración, simulaciones antiguas,
sustitución/reversión encadenada y portable completo. Tres correcciones visuales del
detalle: aviso centrado con su icono, espacio después de Preparar mensaje y nombre
actual enlazado con separación antes del vehículo, sin falsificar un snapshot ausente.

Verificación final: **708 pytest (158,22 s) y 129 E2E (234,219 s)** correctas, sin fallos,
omitidas ni reintentos finales. 77 nuevas pruebas Python y 11 E2E; ocho auditorías Axe
y ocho capturas revisadas en claro/oscuro, 1366/390 px. Pip check, typechecks/build y
diff check correctos. Sólo bases sintéticas; E2E en copia aislada idéntica por hashes.
Con 5.000 históricos la lista tiene p95 de 12,926 ms y el filtro de pendientes 3,916 ms.
Fallos intermedios corregidos y evidencia: `reports/HISTORICOS-REVISION-2026-10-08.md`.
No se modificaron bases reales, ni se ejecutó Windows/WebView2 o reconstruyó instalador.
Sin commit/push. Reiniciar `npm run start` para cargar el backend y migrar con copia previa.
Uso y límites: `docs/IMPORTACION-ACCESS.md`. Se conservan verificaciones anteriores.

## Agenda: guardado directo al arrastrar · 08/10/2026

Soltar una cita al moverla o alargarla guarda directamente, sin abrir el editor;
el clic y Enter conservan la edición manual. Escape y cancelación del puntero revierten
el gesto. Vista previa inmediata, una sola escritura, errores visibles y bloqueo hasta
recuperar las versiones; recarga fallida con reintento. En series sólo cambia la repetición
seleccionada. Se conservan duración real, campos, excepciones y validación Europe/Madrid.
Una cita borrada desde otra ventana no puede recrearse mediante una actualización antigua.

Verificación final: **631 pytest (87,09 s), 26 E2E dirigidas y 118 E2E completas
(243,002 s)** correctas, sin fallos, omitidas ni reintentos en la ejecución final.
Doce nuevas regresiones E2E y tres Python. Pip check, typechecks/build y diff check correctos.
Sólo bases sintéticas. La primera batería completa tuvo un fallo de arranque por
recompilación simultánea de dist; la final se ejecutó sobre copia aislada idéntica por
hashes. No se modificaron fixtures para evitar el fallo. Windows/WebView2 pendiente.
Detalle: `reports/AGENDA-DRAG-2026-10-08.md`. Sin commit/push; reiniciar `npm run start`
para cargar también la protección backend. Se conservan los cambios anteriores.

## Agenda: control de duración · 08/10/2026

Corregida la franja opaca que tapaba la parte inferior del evento al pasar el cursor
o enfocar el control de duración. Fondo transparente y agarre discreto; hora legible,
zonas de interacción accesibles para mover/alargar incluso las citas cortas y foco visible.
Se conserva la lógica de arrastre, fechas, confirmación y guardado.

Verificado con datos sintéticos: **14 pruebas de Agenda y 106 E2E completas correctas
(165,824 s)**, sin fallos, omitidas ni reintentos. Dos regresiones nuevas con ocho
auditorías Axe WCAG 2.2 AA y ocho capturas revisadas en Día/Semana, claro/oscuro,
1366/390 px. Typechecks/build y diff check correctos. Sin cambios Python/SQLite;
no se repitió pytest ni se ejecutó Windows/WebView2. Informe e incidencias intermedias:
`reports/AGENDA-RESIZE-2026-10-08.md`. Cambios anteriores conservados, sin commit/push.

## Sidebar: transición y espacio · 07/10/2026

«Más herramientas» abre/cierra con transición CSS de 200 ms, admite inversión rápida
y respeta movimiento reducido. Logo y pie permanecen fijos; las opciones ocultas quedan
fuera del foco. A 768/900 px con letra normal/grande no hay scroll ni opciones cortadas,
en ambos temas. En ventanas más bajas sólo se desplaza el menú; móvil probado a 320/390 px
con Escape, cierre por fondo y recuperación de foco.

Verificación final: **104 E2E correctas (148,542 s)**, sin fallos, omitidas ni reintentos;
ocho nuevas, con 13 auditorías Axe y 13 capturas revisadas. Ambos typechecks, build y
`git diff --check` correctos. Sólo datos sintéticos; sin cambios backend, dependencias
o SQLite. No se repitió pytest ni se ejecutó Windows/WebView2 en esta revisión.
Detalle, medidas e incidencias corregidas: `reports/SIDEBAR-2026-10-07.md`.
Cambios previos conservados; sin commit ni push.

## Direcciones españolas opcionales · 07/10/2026

Alta/edición de clientes con CartoCiudad oficial, sin dependencia nueva ni migración.
Debounce 300 ms, mínimo tres caracteres y país ES; completar dirección/CP/población/
provincia conserva los valores manuales cuando faltan campos. Sin consulta al abrir
edición, con teclado accesible y descarte de respuestas obsoletas. Guardado manual
disponible también sin Internet. Solo sale el texto de dirección; contexto local para
ranking nacional, caché limitada en memoria y atribución en formulario/Acerca de/licencias.

El escritorio usa trabajos cortos start/result/cancel para no bloquear su canal JSONL
con la espera de red; el proveedor tampoco retiene SQLite. Verificado guardar mientras
la consulta permanece pendiente. Sin cambios en listados ni funcionalidad ajena.

Verificación final: **628 pytest (95,52 s) y 96 E2E (149,156 s)**, sin fallos/omitidas/
reintentos; pip check, typechecks y build correctos. Añadidas 81 pruebas Python y 28 E2E,
incluidas 16 auditorías Axe y capturas en cuatro anchos y ambos temas. Solo datos sintéticos.
Consulta manual pública al IGN correcta; ninguna prueba normal depende de Internet.
No se ha ejecutado Windows/WebView2 ni reconstruido el instalador o sidecar de esta función.
Detalle, fallos intermedios corregidos y warnings: `reports/DIRECCIONES-2026-10-07.md`.
Guía de uso y privacidad: `docs/DIRECCIONES.md`. Cambios locales, sin commit ni push.

## Agenda, navegación y cabecera · 07/10/2026

Mes mantiene cuadrados exactos en 320/390/768/1366 px y acceso a todos sus eventos.
Inicio y Agenda presentan la misma hora Europe/Madrid: corregida la doble conversión
que mostraba 21:00 para una cita de 19:00. Cabecera sticky y compensación del menú
de Configuración; salto al contenido accesible con teclado.

Referencias por ID entre clientes, vehículos, documentos, artículos y proveedores,
también en Inicio, Agenda, histórico, registros fiscales/B2B, conciliación y stock.
Se conservan snapshots y archivados, sin inferir vínculos ausentes. Confirmación
de cambios pendientes en editor, evento, movimiento y configuración fiscal.
`customers.list` añade únicamente los IDs/matrículas usados para navegar; conserva
la consulta por lote y `plates`. Sin índices nuevos, migraciones ni cambio en búsqueda global.

Avisos Windows con sonido normal/silencio del sistema y clic hacia Agenda mientras
la aplicación vive o está en bandeja. Registro de entrega con snapshot exacto y
reintentos sin sonido duplicado; errores visibles. Prueba de sonido respeta preferencia.
Tipos y clippy del escritorio completo para Windows correctos; **no se han ejecutado
ni escuchado notificaciones en Windows real**. Instalador y prueba física pendientes.

Verificación final de estas fuentes: **547 pytest correctas (51,22 s), 68 E2E correctas**,
sin fallos/reintentos, pip check, ambos typechecks y build correctos; cinco pruebas Rust
y check/clippy Windows. Nuevas medidas/Axe/capturas en cuatro anchos y claro/oscuro.
Doce comprobaciones sobre copia privada del ensayo; nueve tablas de dominio intactas.
Los 26 archivos del original permanecen idénticos. Medianas reales Clientes:
apertura **3,881 ms**, página 10 **4,793 ms**, filtros de nombre/matrícula **1,418/1,343 ms**;
p95 máximo **5,031 ms**. Sintético 15.000/30.000/60.000: p95 máximo **51,512 ms**.

Detalle: `reports/USABILIDAD-AGENDA-NAVEGACION-2026-10-07.md`, inventario de navegación
y ensayo nativo enlazados desde él. Cambios locales sobre `6be3445`, sin commit ni push;
reiniciar la previsualización con `npm run start` para cargar también el backend nuevo.

## Vehículos: presentación y búsqueda · 07/10/2026

La ficha separa sus paneles 24 px y presenta marca/modelo o la descripción original
conservada en `kind`, también en listado y tarjetas de cliente. Los motivos automáticos
muestran «Alta desde importación» sin UUID; los motivos manuales y la auditoría interna
se conservan íntegros. Búsqueda de vehículos ampliada a `kind` manteniendo las coincidencias
anteriores y contador real del listado. Sin reimportación, migración ni cambios en datos.

Verificado: 532 pytest (51,55 s), 22 dirigidas, typechecks/build y cuatro E2E nuevos;
13 auditorías Axe sin violaciones a 1024/320 px y claro/oscuro, con medidas de separación
y revisión de capturas. Ocho comprobaciones sobre copia privada del ensayo real.
Rendimiento p95: ficha 0,595 ms, listado 2,103 ms, página 10 2,960 ms; filtros hasta
10,342 ms y Clientes 4,504 ms. El original permanece intacto. Batería de navegador
completa final: **50 E2E correctas, 86,416 s**, sin reintentos. Contraste reforzado
en el buscador y auditoría de interfaz sincronizada con el fin real de animaciones,
sin modificar las reglas de accesibilidad. Evidencia en
`reports/VEHICULOS-PRESENTACION-2026-10-07.md`.
Estos cambios quedan locales sobre `6be3445`, conservando el arranque npm anterior;
para revisarlos, reiniciar el servidor con `npm run start` y recargar el navegador.

## Arranque local con npm · 07/10/2026

Añadido `npm run start`: ejecuta typecheck/build, usa `.venv/bin/python` y abre la web
local con la copia persistente `${XDG_DATA_HOME:-$HOME/.local/share}/taller-canamo-preview/data`.
Preparada desde el ensayo completo: 1.595 clientes, 1.290 vehículos y 5.133 históricos.
La ruta temporal anterior estaba vacía y ya no se utiliza para arrancar. Verificado el
comando, servicio HTTP, RPC autenticado y páginas 0/10; integridad/FK correctas y origen
sin cambios. Detalle en `reports/ARRANQUE-LOCAL-2026-10-07.md`. La optimización de Clientes
ya está en `6be3445`; esta modificación de arranque permanece local, sin commit ni push.

## Clientes · 07/10/2026

Optimización terminada de `customers.list` y `CustomersPage`, desde el commit publicado
`388cb2ac000823b5af6c8a13402abc27defd3def`. Se eliminan `last_visit`, la lectura de documentos
y campos no consumidos; las matrículas se agregan sólo para los 50 clientes de la página.
Se conserva `legacy_code`, utilizado por el selector del asistente de importación.
Sin índices nuevos, migración, FTS, debounce ni cambio en `customers.search`/`useLoad`.
La tabla permanece durante recargas; datos anteriores identificados y no seleccionables,
respuestas obsoletas descartadas, errores visibles y espacio de estado estable.

Medianas reales: apertura **1.163,111 → 5,926 ms**, página índice 10 **4.135,003 → 6,346 ms**,
nombre parcial **44,758 → 1,934 ms**, matrícula parcial **7,679 → 1,949 ms**. p95 final
máximo de estos casos: **12,830 ms**. Sintético de **15.000 clientes / 30.000 vehículos /
60.000 documentos**: apertura/paginación **53,116 / 61,455 ms** de mediana y
**59,325 / 71,044 ms** p95. Benchmark, EXPLAIN, alternativas y límites en
`reports/CLIENTES-PERFORMANCE-2026-10-07.md`.

Verificado: **520 pytest correctas (152,25 s)**, 35 dirigidas (4,49 s), buscador por
separado 10 (0,79 s), pip check, ambos typechecks, build y los cinco E2E nuevos correctos;
cuatro auditorías Axe sin violaciones y revisión visual a 1024/320 px. Batería E2E
completa final: **46 correctas, 130,126 s**, sin fallos, omitidas ni reintentos. Recorrido real: 21 comprobaciones
contra una copia privada. Los 23 archivos del origen se mantienen idénticos y pasan
integridad/FK; los datos de clientes/vehículos/documentos de la copia no han cambiado.
El origen real no contiene clientes archivados ni varias matrículas activas por cliente:
los casos positivos están cubiertos con datos sintéticos.

Cambios locales sin staging, commit ni push, con esquema v8. No se recompiló ni se afirma
haber probado un nuevo binario Tauri/Windows en este encargo; la evidencia nativa de abajo
pertenece a la revisión Access anterior. Para comprobar la interfaz actual se usa el
preview recién construido y la copia indicada en `CONTINUAR.md`.

## Access real · 06/10/2026

Informe actual: `reports/ACCESS-REAL-2026-10-06.md` y anexos. Los dos MDB existen y se
leyeron en modo read-only; sus SHA-256 permanecen iguales. Se recuperaron fórmulas de
informes y 12/11 módulos VBA, pero no su vigencia por periodo ni redondeo/impresión
histórica suficiente para reconstruir importes. No se impone 21 % ni calendario legal.

- Lector corregido para contadores internos obsoletos, con conteos efectivos/metadatos
  visibles. Fixture MDB real que reproduce discrepancia de contador.
- Migración SQLite 8: fechas/importes históricos desconocidos NULL, estados explícitos,
  precisión raw y procedencia. Facturación nueva mantiene restricciones. PDF/listado/UI
  muestran «No consta», sin deuda, pagos ni agregados financieros inventados.
- Perfil sugerido sobre columnas reales, relación postal y modo parcial. Cabeceras
  idénticas consolidadas, identidades huérfanas recuperadas por clave compuesta, conflictos
  agrupados, decisiones por fila y originales completos. No se inventan propietarios.
- Ensayos limpios A/B y comprobación final C: **1.595 clientes, 1.290 vehículos, 5.133
  históricos, 19.335 líneas**; 27.621 filas raw conservadas, conciliación sin diferencias,
  series/cola fiscal intactas. A y C revertidos, B conservado para inspección; no operativo.
- Pendientes explícitos: 18 clientes, 222 referencias de vehículos, 70 candidatos de
  histórico y 326 líneas no atribuibles; 38 históricos importados con fecha conflictiva
  y 45 sin fecha. No presentarlos como resueltos ni como datos perdidos.
- Búsqueda comprobada para los 1.595 códigos de cliente y 1.290 matrículas importados;
  seis comprobaciones de PDF, dashboard/reportes, auditoría e integridad SQLite/FK.

Verificación actual: **496 pytest correctas, 208,45 s**; **47 pruebas dirigidas Access/
contratos correctas, 37,24 s**; pip check, ambos typechecks y Vite correctos;
**41 E2E correctas**, 141,260 s (incluida accesibilidad). Servicio empaquetado final con
9 grupos funcionales correctos, 18 pruebas Rust correctas, check/build Tauri Linux y
diagnóstico correctos, **8/8 comprobaciones de ventana Tauri/WebKit real**, incluido
selector GTK, con datos sintéticos. Véase `reports/ACCESS-DESKTOP-2026-10-06.md`.

Al cerrar aquella revisión, `main` estaba en `a67f8d24c03ab439820bfc11198629d909878e13`
y sus cambios seguían locales. Después se publicaron en `388cb2ac000823b5af6c8a13402abc27defd3def`;
la optimización de Clientes del 07/10 parte de ese commit y permanece local. No hay bases ni certificados trackeados/staged ni PII real
en las adiciones revisadas. Los apartados fechados de septiembre son evidencia anterior,
no describen el esquema ni los artefactos reconstruidos actuales.

## Revisión de Git · 29/09/2026

El usuario ha inicializado Git y configurado `origin`. En esta revisión local, rama `main`
sin commits ni archivos en el índice. `.gitignore` excluye artefactos de compilación/pruebas,
datos privados y certificados, conservando fuentes, locks, licencias fuente e informes
redactados. Comprobadas las reglas con Git y la inclusión de las 279 fuentes del inventario
de empaquetado. Los artefactos de `reports/` referenciados abajo permanecen locales;
sus resúmenes Markdown sí se incluyen. Detalle en `reports/REVISION-GITIGNORE-2026-09-29.md`.
Las menciones anteriores a la ausencia de `.git` describen el entorno de esas fechas.

## Ajustes posteriores de alineación · 29/09/2026

Campos con textos de ayuda alineados por arriba en el estilo común; se conserva la
alineación inferior de acciones explícitas. Menú lateral de Configuración sticky con
altura adaptable, desplazamiento interior y foco visible; cambiar de sección desde abajo
muestra su comienzo. Separación de 1rem entre botón y aviso en Asistencia. Corregida también
la semántica accesible del logo provisional. Sin cambios de backend ni datos reales.

Verificación: 38 E2E correctas (103,138 s); después del último atributo del logo, ocho E2E
de interfaz/accesibilidad correctas. Ambos typechecks y build correctos, Tauri Linux final
recompilado (4,32 s) y siete comprobaciones nativas correctas. Medidas de alineación,
ventana de 380 px de alto, letra de 20 px hasta 320 px de ancho y Axe documentados en
`reports/AJUSTES-ALINEACION-2026-09-29.md`. Windows sigue pendiente. Los hashes actuales
están en `reports/ui-alignment-2026-09-29/artifacts.json`; los de la primera revisión quedan
como evidencia de aquella versión.

## Revisión de interfaz · 29/09/2026

- Controles comunes de texto, número, selección, texto largo, sugerencias y fecha en toda
  la interfaz; calendario en castellano con elección de año/mes/día, teclado y límites.
  Selectores y calendarios ocupan la pantalla en móvil. Archivos, casillas y rango siguen
  siendo controles nativos. La edición manual de fechas conserva el formato del sistema.
- Modales y paneles con entrada/salida breve, preferencia de movimiento reducido, pila de
  foco/inert y cierre seguro. Cerrar el dictado libera el micrófono al iniciar la salida.
- El buscador conserva la lista durante la siguiente consulta, sin desmontarla por tecla;
  las opciones antiguas no son seleccionables hasta recibir el resultado vigente.
- Espaciado de ficha/Resumen, fila vehículo/km/alta, botones PDF sin saltos, tarjetas de
  vehículo y proporciones del icono Configuración corregidos.
- Borradores con líneas reordenables por arrastre, botones y teclado; cantidades/importes,
  guardado, reapertura y orden del PDF verificados. Las facturas emitidas siguen protegidas.
- Configuración destaca Normal/Grande/Muy grande (16/18/20 px), vista previa reversible y
  persistencia tras reiniciar. Comprobado hasta 320 px sin desbordamiento horizontal en los
  recorridos ensayados; no cambia el tamaño de impresión A4.

| Comprobación actual | Resultado | Evidencia en `reports/ui-2026-09-29/` |
|---|---|---|
| `.venv/bin/python -m pytest` | 438 correctas, 77,06 s; ejecutadas al inicio, backend sin cambios posteriores | `baseline-pytest.log` |
| `npm run typecheck` y `npm run typecheck:e2e` | Ambos código 0 | `typecheck.log`, `typecheck-e2e.log` |
| `npm run build` | Código 0; Vite 1,13 s | `build-final.log` |
| `npm run test:e2e` | 38 correctas, 0 fallos/omitidas/flaky; 178,012 s | `e2e-final-results.json`, `e2e-final.log` |
| Axe y revisión visual | Sin infracciones en los recorridos automatizados; claro/oscuro, teclado, móvil y letra grande | Capturas y adjuntos en `reports/e2e/` |
| `npm ls --depth=0` y `python -m pip check` | Ambos código 0, sin incompatibilidades | Logs de dependencias |
| `cargo +1.98.1 build --locked` | Código 0; Tauri Linux con interfaz actual, 2 min 41 s | `tauri-build-final.log` |
| Tauri/WebKit real | 7 comprobaciones correctas, datos sintéticos e IPC real | `desktop/result.json` |

No se han cambiado el backend, el esquema SQLite ni los locks. El smoke nativo espera
ahora a que termine su servicio antes de eliminar los datos temporales; se conservan los
intentos fallidos y su diagnóstico. Apertura/impresión usan receptores de prueba: **no es
impresión física**. Windows/WebView2 no están disponibles y siguen pendientes. Las huellas
de esta revisión se conservan en `reports/ui-2026-09-29/artifacts.json`.

## Verificación base · 23/09/2026

Los siguientes resultados corresponden a la revisión anterior. Sus tiempos, hashes y ZIP
no describen los nuevos archivos de interfaz; se conservan como evidencia fechada.

Entorno Ubuntu Linux x86_64, Python 3.13.2 en `.venv`, Node 22.22.2/npm 10.9.7 y Rust 1.98.1.
Sin directorio `.git`. Datos sintéticos y SQLite temporal; no se han abierto bases operativas,
publicado repositorios, enviado datos a AEAT ni mensajes a clientes. Las referencias privadas
no se usan en pruebas ni se incluyen en el ZIP de fuentes.

Comando: `.venv/bin/python scripts/verify.py --report reports/final-verification-2026-09-23`.
Informe `result.json`: **passed=true**, seis códigos 0 y **ningún cambio de fuentes** durante
la ejecución. Se registran 220 huellas y las de `dist`.

| Comprobación | Resultado exacto | Evidencia |
|---|---|---|
| `python -m pip check` | Sin incompatibilidades; 0,161 s | `final-verification-2026-09-23/python-dependencies.log` |
| `python -m pytest` | **438 correctas**, 0 fallos/errores/omitidas; 40,26 s de pytest | `final-verification-2026-09-23/pytest.xml` y log |
| `npm run typecheck` | Código 0; 2,524 s | `final-verification-2026-09-23/typescript.log` |
| `npm run typecheck:e2e` | Código 0; 1,090 s | log correspondiente |
| `npm run build` | Código 0; 4,374 s; Vite y TypeScript | `final-verification-2026-09-23/vite.log` |
| `npm run test:e2e` | **32 correctas**, 0 fallos/omitidas/flaky; 55,3 s de Playwright | `final-verification-2026-09-23/e2e-results.json`, log y `reports/e2e/html/` |
| `cargo test --locked --no-default-features --lib` | **18 correctas**, 2,00 s | `rust-final-2026-09-23.txt` |
| Build Tauri Linux final | Código 0, ejecutable enlazado; 6,34 s | `tauri-final-build-2026-09-23.txt` |
| Servicio PyInstaller completo | Motores reales Saxon/Vosk/RapidOCR/JRE, PDF, licencias, copia/portable y reapertura correctos | `sidecar-functional.json`, `sidecar-artifact.json` |
| Tauri/WebKit real final | **8 comprobaciones correctas**; búsqueda/ficha/PDF/instancia y selector GTK real | `desktop-final/result.json`, `escritorio-final-2026-09-23.md` |
| Tipos Win32/COM/notificaciones | Código 0; no ejecución ni enlace Windows | `rust-pdf-windows-typecheck-2026-09-23.txt` |

Los tiempos del comando contenedor se conservan también: pytest 40,592 s y E2E 56,186 s.
Los mensajes de color de Node quedan en el log; no son errores de tests. Las pruebas con
transportes simulados están identificadas y nunca producen evidencia de aceptación AEAT.

## Implementación y comprobaciones complementarias

- Flujo directo sin orden/presupuesto/stock obligatorio. Borradores, numeración, cálculos
  decimales, cobros, snapshots y titularidad con histórico; E2E sin vehículo y extras ocultos.
- Revisión final corrigió paginación de ficha a partir de 50 documentos, km iniciales y
  respuestas tardías, alta de vehículo desde factura, país/CP extranjero y ranking exacto
  por código/NIF/teléfono. `reports/revision-flujo-final-2026-09-23.md` contiene la matriz.
- Búsqueda: 15.000 clientes/30.000 vehículos, 15 muestras por consulta; p95 máximo
  **117,084 ms**, solo servicio. `reports/search-priority-benchmark-2026-09-23.json`.
- PDF Unicode con DejaVu embebida, A4 de 1/7/1 páginas inspeccionadas, precisión,
  rectificativas, datos históricos ausentes y caché inmutable. Carácter sin glifo detiene
  emisión antes de numerar. `reports/pdf-unicode-2026-09-23.md`.
- Agenda con recurrencias/excepciones, Madrid/DST, arrastre/duración, teclado y avisos;
  stock/proveedores/conversiones/informes/exportaciones; OCR/dictado reales, propuestas
  cancelables y revisión humana. Los 32 E2E recorren estos módulos con backend real.
- Copias AES-GCM/ZIP por bloques, límites explícitos 8 GiB descomprimidos/9 GiB de archivo/
  50.000 entradas, prevalidación ZIP/ZIP64, restauración con recuperación y traslado protegido.
  Ensayo real con original sintético compresible de **2 GiB** y SHA exactos; no acredita
  todos los máximos ni un MDB de ese tamaño. `reports/backup-capacity-2026-09-23.json`.
- Selector GTK real: copia cifrada de **3.762.699 bytes**, cancelación, sustitución y SHA
  idéntico a copia local. El primer intento fallido del harness se conserva y explica.
- Access nativo MDB/ACCDB con Jackcess/JRE, diagnóstico/perfiles/mapeo/staging/simulación/
  lotes/reanudación/conciliación/rollback. Bases sintéticas reales y 15.001 clientes sin
  truncamiento. Guía y límites: `docs/IMPORTACION-ACCESS.md`.
- VERI*FACTU: XSD/hash/QR, cola/esperas/Consulta, subsanación y rectificación de cuota;
  certificado y huella TLS coherentes; candidato Windows con expediente verificable.
  `App.tick` procesa ambos modos remotos con los gates intactos. No autoriza producción.
- Guion `verify_aeat_authorized.py`: comprobación local por defecto y ejecución explícita
  de IDs revisados mediante el candidato real. **15 pruebas locales**, incluidas en 438.
  Procedimiento completo: `docs/FISCAL-ENSAYO-AUTORIZADO-2026-09-23.md`.
- B2B separado: UBL2.1 + XSD/EN16931 real, originales recibidos, estados/exportación;
  1.000 documentos B2B validados en 2,701 s, copia 2,862 s. No equivale a entrega remota
  ni a 1.000 registros fiscales. `reports/b2b-batch-benchmark-2026-09-23.json`.
- Axe sin infracciones en los recorridos comprobados; capturas claro/oscuro/texto grande,
  1024×768/1366×768 y PDF revisadas. No certifica accesibilidad completa. Los selectores
  de fecha de esa revisión eran nativos. La revisión del 29/09 añade el calendario propio;
  quedan por comprobar locale de entrada manual y escalas Windows.
- npm/Python: ninguna vulnerabilidad conocida detectada. Cargo: cero categoría vulnerabilities,
  **seis advertencias de mantenimiento y una GLib insegura**, conservadas; GLib ausente del
  árbol Windows. `reports/seguridad-dependencias-2026-09-23.md`.
- Licencias: 620 dependencias y ZIP de 1.361 archivos verificado; excepción de aviso MIT
  ausente del binario opcional de construcción LZMA documentada. No se distribuye ese
  binario como biblioteca ejecutable del instalador.

TypeScript tiene `strict:true`, pero conserva contratos `Row/any`; no se afirma tipado íntegro.
`check_ts_syntax.cjs` no se utiliza como sustituto de typecheck/E2E. Los informes anteriores
(88/147/274/371 casos) se conservan como hitos y no sustituyen esta batería final.

## Artefactos y documentación

- Ejecutable Tauri Linux: `src-tauri/target/debug/taller-canamo`.
- Servicio Linux completo: `src-tauri/binaries/canamo-service-x86_64-unknown-linux-gnu`,
  también junto al ejecutable Tauri. Arranque/reapertura 3,7801/3,7687 s en este equipo.
- ZIP de fuentes y licencias del 23/09 en `build/entrega/`; inventario histórico en
  `reports/artefactos-entrega-2026-09-23.json`. Ese ZIP no incorpora la interfaz del 29/09;
  construir el candidato Windows desde las fuentes actuales, no desde ese archivo anterior.
- `LEEME.md`, `docs/BUILD-WINDOWS.md`, guías de Access/copias/asistencia/fiscalidad y
  `CONTINUAR.md`. El manifiesto heredado se preserva en `docs/MANIFEST-HEREDADO-SHA256.json`.

## Dependencias externas reales

1. **Windows 11/WebView2 e impresora**: construir NSIS e instalar/actualizar/reinstalar;
   ejecutar DPAPI, Job Object, bandeja/notificaciones, escalas y papel. No existe instalador
   Windows generado aquí. Scripts/workflow preparados, sin remoto ni runner ejecutado.
2. **Certificado e identidad/representación legítimos**: ejecutar la batería autenticada
   AEAT pruebas con el candidato, conservar acuses/consultas y completar el expediente
   revisado del productor. No se sustituye por mocks ni por instalar un certificado.
3. **MDB/ACCDB original**: identificar su esquema concreto, mapearlo, resolver incidencias,
   conciliar y ensayar el corte. El importador ya está desarrollado.
4. **Contrato público B2B**: perfil/endpoint definitivo no localizado en las fuentes
   oficiales revisadas; dependencia acreditada en `docs/B2B-FUENTES-2026-09-23.md`.

No queda un defecto funcional reproducido sin corregir en los recorridos ejecutados.
Las dependencias externas impiden aprobar aún su uso operativo; no implican métodos vacíos
ni tareas de programación trasladadas al usuario como si fueran configuración.

El resumen de `desktop_smoke.py` también reproduce UnicodeEncodeError en CP1252
por las flechas de sus comprobaciones. Se escapa únicamente su JSON de consola,
conservando los caracteres originales al leer JSON y el informe UTF-8 en disco.
Control negativo anterior y comprobación corregida ejecutados sin abrir la app ni
repetir baterías. Se cancela `40573597348` durante preparación de dependencias para
incorporarlo antes del siguiente build completo. El selector Edge Driver aplica
la misma separación PSModulePath ya requerida por pwsh → Windows PowerShell 5.1.
