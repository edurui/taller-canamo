# Talleres El Cañamo: completar, verificar y entregar la aplicación

## 1. Encargo y definición de terminado

Actúa como responsable técnico de este producto y trabaja directamente sobre los archivos. Inspecciona el código real, implementa lo pendiente, corrige defectos, ejecuta pruebas y prepara una entrega reproducible para Windows. No quiero un plan sin ejecución, un prototipo visual ni archivos sueltos que no arranquen.

Estaré ausente. No me hagas preguntas rutinarias ni te detengas entre fases para solicitar revisión. Resuelve los detalles con las decisiones de este documento, registra los supuestos y continúa. Completar incluye poner la aplicación en funcionamiento, inspeccionarla y corregir lo que falle; no basta con escribir una primera implementación.

Quiero todo el código de las funciones solicitadas terminado, mantenible y ejecutable. La ausencia del Access original, certificado, identidad fiscal confirmada o impresora no justifica dejar métodos vacíos, asistentes sin desarrollar o integraciones pendientes de programación.

Distingue código implementado, build superado, instalador probado y validación fiscal externa. No sustituyas un resultado por otro. Si falta una dependencia externa, completa su configuración, pruebas independientes y procedimiento de verificación; registra exclusivamente lo que no se pudo comprobar y sigue con el resto. No inventes datos, respuestas oficiales ni certificados.

No declares el producto apto para facturación real hasta cumplir los requisitos correspondientes. No retires protecciones para aparentar que una integración de demostración es un producto terminado.

## 2. Contexto y decisiones cerradas

El usuario final es mi tío, autónomo mecánico de Automecánica Talleres El Cañamo, Calle Torres Quevedo, 22, 41300 San José de la Rinconada, Sevilla. Es práctico y poco interesado en funciones complicadas. Su edad exacta no se conoce: diseña para legibilidad, comodidad y poca experiencia digital, sin infantilizarlo.

Utiliza un programa antiguo de Microsoft Access, principalmente para clientes y facturas. Su recorrido esencial es:
BUSCAR CLIENTE O MATRÍCULA -> NUEVA FACTURA -> IMPRIMIR.

Yo, Eduardo, soy desarrollador web acostumbrado a React/TypeScript y desarrollo habitualmente en Ubuntu. Mi tío no debe instalar herramientas de desarrollo ni utilizar terminales.

Decisiones:
- Un solo ordenador Windows, inicialmente Windows 11 x64, trasladable después a otro PC.
- Aplicación de escritorio real, datos locales y coste recurrente del núcleo de 0 euros.
- React + TypeScript + Tauri 2 + servicio auxiliar Python + SQLite.
- Castellano de España, euros y zona horaria Europe/Madrid.
- Clientes, borradores, históricos y operaciones locales funcionan sin Internet. Los envíos fiscales gestionan interrupciones sin fingir éxito.
- No añadir Supabase, Vercel, servidor cloud, dominio, cuenta remota, suscripción ni telemetría obligatorios.
- SQLite se crea automáticamente; migrar Access es opcional. La aplicación debe funcionar con una base nueva.
- Certificado, identidad fiscal completa y datos del productor pendientes: formularios y validaciones, nunca identidades inventadas.
- Logo independiente no disponible. Usa un marcador EC digno y permite cargar/cambiar imagen. No bloquees el desarrollo por ello.

## 3. Autonomía y límites de full access

Autorizo leer y editar este proyecto, crear archivos, refactorizar justificadamente, instalar dependencias de fuentes oficiales en entornos de desarrollo, ejecutar comandos/pruebas/builds, generar datos ficticios, capturas e informes y crear commits locales sin alterar trabajo ajeno.

Puedes investigar documentación pública, descargar dependencias y usar las herramientas/subagentes disponibles cuando aporten valor. No presupongas herramientas inexistentes.

No autorizo:
- Leer o modificar otros proyectos, especialmente repositorios, bases o cuentas de mi empresa.
- Buscar secretos en el ordenador, consultar correos/contactos o reutilizar certificados encontrados.
- Publicar código, hacer push, crear recursos remotos, gastar dinero o consumir APIs comerciales adicionales.
- Emitir documentos reales, enviar mensajes a clientes o transmitir facturas ficticias a producción.
- Alterar el Access original, una base operativa o cambios previos del usuario.
- Desactivar antivirus, controles del sistema, sandbox o políticas del entorno.
- Instalar software de procedencia desconocida o con licencias incompatibles.

Full access no amplía este alcance. Usa fixtures y directorios temporales propios. Si una acción requiere una credencial ausente, elevación no disponible, autorización externa o pago, no la eludas ni quedes esperando: registra el bloqueo concreto y continúa con lo independiente.

Instala herramientas de usuario necesarias sin cambiar configuraciones globales innecesariamente. No modifiques instrucciones globales de agentes. Las políticas del entorno siguen vigentes.

## 4. Inspección del relevo existente

La referencia es taller-canamo-codex-2026-09-07.zip o su carpeta extraída. Trabaja sobre la versión más reciente realmente disponible y preserva cambios posteriores. Si solo hay un ZIP, extráelo de manera segura en el espacio autorizado.

Consulta al inicio AGENTS.md y docs/ESTADO-VERIFICADO.md. Usa README.md, docs/CONTEXTO-PRODUCTO.md, docs/ACEPTACION.md, docs/BUILD-WINDOWS.md y docs/CAMBIOS-RELEVO.md cuando corresponda. No releas todos los documentos antes de cada edición. Este encargo actualiza mis requisitos de producto/autonomía, no las políticas de seguridad del entorno.

Si falta documentación, este encargo contiene el contexto. Si no hay código ni ZIP, construye el proyecto con estos requisitos sin buscar por el resto del disco ni atribuirle tests de otra versión. No vuelques este documento entero en AGENTS.md: conserva allí instrucciones breves y aplicables.

El relevo anterior registró 88 casos pytest superados, arranque del backend, IPC/HTTP y un PDF de demostración. Es evidencia histórica, no prueba del estado actual: reproduce la línea base. Se habían añadido validation.py, errors.py y el paquete Python; no repitas automáticamente el diagnóstico antiguo de módulos ausentes.

Entonces no se habían verificado typecheck completo, Vite, Cargo, instalador Windows ni comunicación autenticada con AEAT. Verifica y resuelve, entre otros:
- Dependencias, lockfiles, compilación y contratos TypeScript; uso de any y strict:false.
- Ruta del sidecar instalado, instancia única, cierre y timeouts con resultado incierto.
- Notificaciones nativas y bandeja.
- Históricos/listados que consultaban datos vivos en vez de snapshots.
- Restauración coherente de SQLite, imágenes y documentos ante fallos.
- Normalización de IVA, redondeos y rectificativas parciales.
- Restricciones que podrían impedir subsanaciones fiscales sucesivas.
- Importador CSV/JSON sin lectura real de Access.
- Fiscalidad limitada a pruebas, banderas de producción y PDFs demo.
- Automatizaciones, dictado/OCR y factura electrónica estructurada pendientes.

Una captura o un directorio llamado final no demuestran que exista código adicional. Actualiza el estado con evidencia.

## 5. Arquitectura y seguridad

Conserva el stack y reutiliza lo válido. Refactoriza lo defectuoso; no reescribas por preferencia ni conserves código inseguro por inercia.

El servicio Python es la autoridad de negocio y cálculos oficiales. Define contratos explícitos entre React, Tauri y Python, validación en backend, errores estructurados y pruebas de contrato. El frontend no ejecuta SQL ni decide importes fiscales por separado.

Usa Decimal/representación exacta para cantidades, precios, impuestos y descuentos. Centraliza/documenta el redondeo. SQLite con claves, restricciones, transacciones, índices y migraciones versionadas.

Emisión, cobros, conversiones, stock, importaciones y envíos deben ser idempotentes. Ante timeout, recupera el resultado por identificador antes de repetir. No prometas entrega de red exactamente una vez.

Tauri inicia y cierra automáticamente el servicio empaquetado, controla versiones y errores. Sin consola, procesos huérfanos, Python instalado por el cliente ni listener expuesto a la red local. Mínimo privilegio en IPC, rutas, plugins y navegación.

Datos persistentes fuera de la instalación y permisos adecuados de Windows. Separa bases/credenciales de demostración, pruebas AEAT y producción. Nada de demos mezcladas con datos reales.

Secretos protegidos con mecanismos adecuados de Windows, renovación y traslado seguros. Nunca en Git, logs o telemetría. .gitignore no cifra datos. Dependencias soportadas/fijadas, lockfiles reales y licencias revisadas. No introducir SaaS multiempresa, microservicios o sincronización distribuida.

## 6. Interfaz y buscador

Principales: Inicio, Clientes y Facturas; buscador siempre accesible, acciones grandes y Configuración separada. Vehículos, agenda y extras dentro de Más herramientas, ocultables sin borrar datos.

Amarillo como acento, superficies tranquilas, modos claro/oscuro/sistema, letra ajustable, contraste, foco visible, teclado y etiquetas comprensibles. No llenar el fondo de amarillo intenso ni crear un ERP visualmente abrumador.

Probar escalas Windows 100/125/150 %, ventanas 1366x768 y 1024x768 y adaptación a una ventana estrecha. No esconder acciones esenciales, cortar texto ni encadenar modales innecesarios. Confirmaciones donde protegen de errores, no por cada cambio rutinario.

Buscador:
- Desde el primer carácter por nombre/apellidos/razón social, matrícula, teléfono, NIF y código antiguo.
- Normalizar tildes, espacios, mayúsculas y separadores pertinentes. 0540-BZD, 0540 BZD y 0540bzd encuentran el mismo vehículo.
- Autocompletado visible, desplegable con alternativas y primera coincidencia preseleccionada. Enter, flechas, Tab y Esc coherentes.
- No abrir ficha ni emitir automáticamente por quedar una coincidencia.
- Mostrar cliente, matrícula/vehículo y teléfono: identificar al dueño para llamarlo viendo solo la matrícula.
- Evitar respuestas antiguas, selecciones incorrectas y coincidencias masivas por signos.
- Priorizar exactas/prefijos; las aproximadas nunca sustituyen una selección silenciosamente.
- Medir con datos sintéticos suficientes. Objetivo orientativo: actualización perceptible inferior a 200 ms en un equipo de referencia declarado; informar dataset y percentiles, no una garantía universal.

## 7. Clientes, vehículos, facturas y ajustes

Particulares y empresas: nombre fiscal/comercial, NIF cuando corresponda, dirección, CP, población, provincia, país, teléfonos, email, notas y código antiguo. Distingue lo necesario para crear una ficha de lo necesario para emitir cada tipo de factura. No exigir NIF, email o matrícula para crear un contacto.

Varios vehículos por cliente: matrícula normalizada, marca/modelo, tipo, VIN/chasis, kilómetros, ITV y revisión. Titularidad histórica; cambiar de dueño no atribuye al nuevo facturas anteriores. Admitir maquinaria/trabajos sin vehículo.

Facturas:
- Conceptos libres y frecuentes, mano de obra por horas y recambios sin alta obligatoria en almacén.
- Cantidades/precios decimales, descuentos coherentes, impuestos y causas fiscales correctos.
- Borradores persistentes, guardado seguro y protección de cambios no guardados.
- Revisión antes de emitir y numeración transaccional, sin reutilización ni duplicados.
- Snapshots de emisor, cliente, vehículo, condiciones y marca. Respetarlos en PDF, listados y búsquedas históricas.
- Rectificaciones totales/parciales, referencia al original y distinción entre anulación de registro y corrección comercial.
- Cobros parciales/completos, contrapartidas/devoluciones, saldos correctos y estados fiscal/pago separados.
- Histórico por cliente/vehículo, filtros, PDF e impresión.
- Nunca exigir presupuesto, orden, artículo, stock o matrícula para facturar normalmente.

Configuración independiente de migración: emisor/contacto, logo, IBAN opcional, formas de pago, vencimiento, IVA habitual, tarifa de mano de obra, validez de presupuesto, textos/pie, impresión, marca de agua, accesibilidad, agenda, copias y fiscalidad.

Series por tipo, prefijo, ejercicio cuando corresponda, relleno y número inicial/siguiente con previsualización. Continuidad numérica o nuevas series anuales explícitamente configuradas. No reiniciar series usadas ni alterar emitidas. Importar no decide el siguiente número. Cada ajuste debe influir realmente en todos sus flujos y tener pruebas.

## 8. PDF e impresión

Usa las fotos de la factura antigua si existen: cabecera/logo, destinatario, número, fecha, código cliente, matrícula/km pertinentes, cantidad/concepto/precio/importe y base/IVA/total.

A4 con texto seleccionable, legibilidad, márgenes seguros y varias páginas sin solapamientos. Desgloses completos y cabeceras repetidas donde ayuden. Logo cambiable y marca de agua tenue que no tape texto ni QR.

No reutilizar datos de clientes de las fotos en demos. No copiar condiciones legales antiguas del cartel sin comprobar vigencia. Impresión sencilla, vista previa y guardado. Probar textos largos, muchas líneas, varios impuestos, descuentos, imágenes y rectificativas. Crear un PDF no demuestra impresión física.

## 9. Extras completos, pero secundarios

Presupuestos: líneas, vigencia, estados, PDF, constancia de aceptación/rechazo y conversión sin reescribir.

Órdenes: entrada de vehículo/maquinaria, síntomas, observaciones, kilómetros, trabajos/piezas y estados recibido/en reparación/esperando piezas/terminado/entregado; documentos imprimibles y trazabilidad con presupuesto/factura.

Almacén: artículos, referencias, proveedores, precios/costes, existencias/mínimos, entradas/salidas, ajustes/devoluciones. Movimientos auditables e idempotentes, política explícita de stock negativo. No descontar dos veces al facturar una orden ya consumida.

Informes operativos sencillos: facturación, cobros, trabajos y mínimos. No presentarlos como contabilidad completa ni declaraciones tributarias. Exportaciones utilizables y portables. Ningún botón decorativo ni éxito ficticio.

## 10. Agenda

Mes, semana, día, Hoy, anterior/siguiente, selector de fecha y semana desde lunes. Inspiración de uso en Google Calendar, sin cuenta Google obligatoria.

Crear/editar/mover/cancelar, seleccionar día/hora y arrastrar/redimensionar donde corresponda con alternativa accesible de formulario. Todo el día, varias fechas, solapamientos, citas, entregas, ITV, mantenimiento, tareas y asuntos personales.

Recurrencias diarias/semanales/mensuales, fin y excepciones; editar una ocurrencia o la serie. Documentar días mensuales inexistentes. Europe/Madrid, UTC donde proceda y fechas sin hora separadas. Cubrir cambios de horario.

Avisos configurables persistentes, posponibles y sin duplicados; sonido opcional y soporte nativo Windows. Cierre a bandeja frente a salida total, inicio de sesión opcional. Con ventana oculta funciona si sigue activo; no prometer avisos con PC apagado o proceso detenido. Recuperar pendientes al abrir sin avalancha. No distribuir herramientas de control remoto de pruebas en producción.

## 11. VERI*FACTU completo

No entregar solo un XML de ejemplo ni decir preparado para VERI*FACTU. Implementa todo el circuito y la configuración, sin métodos vacíos, endpoints inventados o una edición permanentemente sandbox como sustituto del desarrollo.

Investiga AEAT/BOE vigentes. Identifica ámbito del taller y operaciones soportadas; configura lo dependiente de sus datos. No memorices plazos ni requisitos. Distingue obligaciones del usuario y del productor.

Implementa:
- Generación, conservación, versión y encadenamiento de registros según especificaciones.
- Serialización/validación con XSD oficiales y dependencias fijadas, procedencia y hashes.
- Huellas con vectores independientes, formatos, QR y leyendas aplicables.
- Altas, rectificaciones, anulaciones, subsanaciones, rechazos previos, duplicados y correcciones sucesivas según proceda.
- Cola persistente, secuencia válida, espera exigida, reintentos y recuperación tras reinicio.
- Reconciliación de resultados desconocidos; ausencia de excepción no equivale a aceptación.
- Respuestas, acuses/CSV y diagnóstico comprensible con acciones concretas.
- Certificado o representación legítima según mecanismo soportado, caducidad y renovación segura.
- Destinos oficiales restringidos, separación prueba/producción y asistente de puesta en marcha.
- Diagnóstico que no emita facturas reales inadvertidamente.

La ruta real debe quedar programada, no pendiente de desarrollo por mi parte. Activarla exige la configuración, verificación y responsabilidad aplicables. Cambiar PRODUCTION_RELEASED, borrar un banner o sustituir una URL no termina la integración.

Sin certificado: completar código, XSD, vectores y simulaciones identificadas; dejar una prueba autenticada reproducible y automatizable en el entorno oficial de pruebas cuando exista acceso legítimo. No ejecutar producción en esta sesión. No inventar aceptación AEAT.

Preparar identidad del productor/versión y documentación de declaración responsable con matriz requisito->código->test->evidencia. No inventar firma, identidad ni homologación oficial. Un checkbox no demuestra cumplimiento.

VERI*FACTU no sustituye la factura electrónica B2B. Investiga esta por separado e implementa formatos y procesos exigibles al alcance identificado con su validación. PDF, XML arbitrario o interfaz vacía no equivalen a B2B terminado. Si una especificación/servicio necesario no se publica o no está disponible, acredita la dependencia concreta sin inventarlo ni detener todo lo demás.

Diferencia implementación local, aceptación en pruebas AEAT y aptitud para puesta en marcha real. La ausencia de certificado no excusa código incompleto; tampoco autoriza una afirmación de cumplimiento no verificada.

## 12. Migración Access preparada antes de recibir los datos

El MDB/ACCDB todavía no está disponible salvo que yo lo adjunte. No lo busques por mi ordenador ni inventes sus datos.

Esquema aproximado observado, NO confirmado:
- Codigos_Postal: cp_codpos, cp_poblacion, cp_provincia.
- Clientes: Cod_cli, Cliente, Cif o Nif, Direccion, Codigo_postal, Telefono1, Telefono2, Fax, Email, Matricula, Tipo de Vehiculo.
- Facturas: COD_CLI, FACTURA.
- DETALLE: COD_CLI, FACTURA, CANTIDAD, CONCEPTO, PRECIO, TOTAL, FECHAFACTURA.
- Formularios: KMS y número de chasis, ubicación real desconocida.

Puede haber tablas vinculadas, claves compuestas, consultas, duplicados y cálculos en informes. No asumir FACTURA globalmente única ni que cada fila Cliente es una persona diferente.

Asistente completo: seleccionar copia -> diagnosticar -> previsualizar/mapear -> resolver incidencias -> simular -> importar -> conciliar.

Requisitos:
- Lectura no destructiva MDB/ACCDB soportada por la tecnología elegida; detectar controlador/arquitectura/cifrado y vínculos.
- Nunca ejecutar macros/VBA, convertir el original, alterar datos ni seguir orígenes remotos automáticamente.
- Extracción viable en Windows y documentada; no instalar controladores incompatibles con Office a ciegas.
- Alternativa CSV/paquete intermedio realmente implementada con herramienta y plantilla. No renombrar CSV como importación nativa Access.
- Mapeo configurable/guardable con perfil sugerido de las tablas observadas y validación previa.
- Preservar ceros, textos, tildes, fechas, precisión monetaria, claves y campos desconocidos recuperables.
- Separar clientes/vehículos sin fusionar ambiguamente; informar huérfanos, duplicados, matrículas compartidas y titularidad.
- Identidad de origen y claves estables por registro para reimportaciones, cambios y corte final. Hash del archivo completo no basta entre copias diferentes.
- Conservar números, fechas, conceptos e importes históricos. No recalcular con IVA actual ni corregir totales silenciosamente.
- No inventar snapshots no conservados; indicar procedencia/certeza y conservar originales disponibles.
- Cobro desconocido no significa automáticamente impagado.
- Lotes y límites documentados con progreso/reanudación segura. No truncar registros por límites ocultos.
- Históricas sin consumir numeración nueva y nunca enviadas a AEAT como nuevas.
- Conciliación de conteos, claves, líneas, bases/impuestos/totales y diferencias por documento y agregado.
- Copia previa, transacciones, recuperación y reversibilidad segura. Actividad posterior no se borra para deshacer una migración.
- Bases Access sintéticas reales cuando sea posible, además de fixtures CSV/JSON difíciles. Tests CSV no demuestran lectura MDB.
- Guía de obtención de copia, ensayo y migración final con corte de emisión.

Cuando aporte los archivos, debe bastar configurar mapeo y resolver incidencias reales, no escribir un importador desde cero.

## 13. Copias y traslado

Copias consistentes de base/recursos, retención configurable y segunda ubicación opcional. Diferenciar retención de copias de conservación legal de documentos. Cifrado opcional con gestión/recuperación documentadas. Mostrar resultado real; disco ausente significa aviso, no éxito.

Restauración con previsualización, compatibilidad, integridad, copia previa y sustitución coherente del conjunto. Inyectar fallos y demostrar recuperación. Rechazar ZIP malicioso, escapes de ruta y tamaños desproporcionados.

No sincronizar SQLite activa con OneDrive; si se utiliza carpeta sincronizada, depositar copias cerradas consistentes. Trasladar a otro PC conserva históricos, series y estado fiscal sin repetir envíos, bifurcar cadenas ni permitir dos emisores accidentales. Un backup antiguo no autoriza rebobinar numeración. Reconciliar antes de reactivar emisión.

Certificados fuera de copias generales salvo procedimiento específico seguro. Reconfigurarlos cuando Windows impida transportarlos por protección ligada a usuario/equipo.

## 14. Automatizaciones e IA

Primero automatizaciones deterministas: conceptos, conversiones, recordatorios y mensajes preparados de presupuesto, factura o vehículo terminado. Abrir/preparar un mensaje no es enviarlo automáticamente. No automatizar WhatsApp con scraping/sesiones no autorizadas ni enviar mensajes reales durante pruebas.

Asistencia opcional implementada: dictado a campos, extracción de documentación, consulta de histórico y mejora de textos. Soluciones locales o proveedores configurables, licencias compatibles, costes visibles y revisión humana. Sin modelo/credencial el núcleo funciona.

Datos extraídos editables con incertidumbre y fuente. No inventar seguridad mecánica, diagnósticos, precios, documentos o matrículas. Consulta determinista del histórico disponible sin IA. No enviar información personal a terceros sin configuración/consentimiento ni descargar modelos enormes sin necesidad. Adaptadores reales con pruebas; mock o botón no equivalen a funcionalidad terminada.

## 15. Ejecución y pruebas

Hitos: base reproducible; dominio/datos; interfaz/módulos; fiscal/migración; escritorio; distribución y revisión final. Intercala/paraleliza donde ahorre trabajo, con responsabilidades claras de archivos. No lances agentes ilimitados o duplicados.

Lista breve de requisitos/aceptación y registro de decisiones/progreso en disco para sobrevivir a compactación. Cada hito deja implementación ejecutada, no solo documentos.

Pruebas según riesgo:
- Unitarias: cálculos, validación, numeración, calendario y formatos.
- Integración: SQLite temporal real, migraciones y procesos IPC reales.
- Concurrencia, doble clic, idempotencia, reintentos y timeout durante emisión/cobro.
- Snapshots, titularidad, rectificativas y saldos.
- PDFs multipágina, tasas, descuentos y codificaciones.
- Históricas completas, repetición de lotes y discrepancias.
- Copia/restauración con fallo inyectado y traslado.
- XSD/huellas y escenarios fiscales independientes, mocks identificados.
- E2E navegador con backend real, no todos los servicios simulados.
- E2E de escritorio real y ciclo del sidecar; navegador no equivale a Tauri.
- Agenda: solapamientos, recurrencias/excepciones, zonas, avisos/reinicio.
- Accesibilidad y revisión visual claro/oscuro, letra grande y ventanas objetivo.
- Seguridad: inyección SQL/CSV/HTML, rutas, importaciones maliciosas, límites, IPC y secretos.

Recorridos de aceptación:
1. Cliente -> dos vehículos -> buscar matrícula -> teléfono correcto.
2. Factura directa -> emisión de prueba -> PDF -> cerrar/abrir -> histórico.
3. Repetir sin vehículo y con extras ocultos.
4. Presupuesto -> orden -> factura sin duplicar líneas/stock.
5. Cobro parcial -> resto -> contrapartida con saldo correcto.
6. Mes/semana/día -> recurrencia -> aviso -> posponer -> reiniciar.
7. Importar históricas -> reimportar -> cero duplicados y cero envíos fiscales.
8. Copia -> restaurar en otra ubicación -> recursos/datos/estado fiscal correctos.

No persigas una cifra arbitraria de tests ni debilites aserciones/validadores para conseguir verde. Prueba cambios y regresiones, y ejecuta una batería final integrada. No repitas comprobaciones sin cambios ni riesgos nuevos indefinidamente.

Guarda plataforma, comandos, códigos de salida y evidencia. Distingue fallo de código, falta de configuración, prueba no ejecutada y dependencia externa. No reutilices el informe antiguo de 88 tests como resultado actual.

## 16. Windows, distribución y cierre

Fuente completa más instalador Windows cuando el entorno permita construirlo. El cliente no necesita Node, Python, Rust ni herramientas de desarrollo/pruebas.

Termina scripts de dependencias, comprobaciones, servicio empaquetado, Tauri, NSIS y WebView2. Documenta necesidad de Internet al instalar; uso offline no significa instalador offline.

Prueba rutas con espacios/tildes, usuario sin privilegios, actualización, reinstalación, cierre forzado y conservación de datos. Firma con certificado legítimo cuando exista; no comprarlo ni falsificarlo. No recomendar desactivar SmartScreen como solución de distribución.

Prioriza Windows de desarrollo disponible y autorizado. En Linux, completa lo independiente y la automatización Windows; usa compilación cruzada solo cuando sea soportada y verificada. No sustituir el escritorio por una web.

Puedes preparar un workflow Windows; no publicar repositorios ni crear recursos remotos. Sin runner autorizado, indica la comprobación pendiente exacta: no inventes EXE ni llames probado al script.

Entregables:
- Código integrado, dependencias/locks y migraciones.
- Comandos reproducibles de arranque, tests y build comprobados.
- Artefactos realmente generados, versión y hashes.
- Manual castellano: instalar, configurar, usar, imprimir, copiar/restaurar/trasladar.
- Asistente/guía de migración y fixtures.
- Configuración/diagnóstico fiscal, documentación y prueba externa preparada.
- Informes actuales, cobertura útil, capturas y revisión de seguridad/licencias.
- Matriz requisito/evidencia/estado sin omisiones silenciosas.
- CONTINUAR.md solo ante interrupción o dependencia externa real, con reanudación mínima concreta.

No declares éxito mientras existan fallos reproducibles o desarrollo implementable pendiente. Si agotas presupuesto, tiempo o herramientas, conserva una versión coherente y estado preciso: interrupción no significa terminado.

La respuesta final indica ubicación, comandos/resultados, pruebas y si se ejecutó el instalador, separando datos/configuración/verificación externa. No me traslades tareas de programación como si fueran configuración.

## 17. Fuentes iniciales

Consulta versiones vigentes y guarda referencias con fecha y requisito. Investiga con foco; no conviertas la sesión en una comparativa interminable. No copiar condiciones fiscales o funcionalidades de competidores sin evaluar pertinencia.

AEAT:
https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html
https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html
https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/certificacion-sistemas-informaticos-declaracion-responsable.html

BOE, B2B:
https://www.boe.es/buscar/doc.php?id=BOE-A-2026-7295

Tauri:
https://v2.tauri.app/start/prerequisites/
https://v2.tauri.app/develop/sidecar/
https://v2.tauri.app/distribute/windows-installer/
https://v2.tauri.app/develop/tests/webdriver/

Access:
https://support.microsoft.com/en-us/access/export-a-database-object-to-another-access-database

Referencias de experiencia/configuración, no reglas fiscales:
https://help.holded.com/es/articles/6834644-facturacion-guia-de-inicio
https://help.holded.com/es/articles/6877971-configurar-las-preferencias-de-ventas-y-compras

Empieza inspeccionando y ejecutando la base disponible. Después implementa, verifica y continúa sin pedirme revisión entre hitos.
