# Revisión técnica fiscal — 23 de septiembre de 2026

Este documento acredita XML, huellas, transporte, correcciones y reconciliación locales.
No autoriza facturación real. La definición de terminado sigue siendo
`PROMPT_MAESTRO_TALLER_CANAMO.md`, especialmente su sección 11.

## Fuentes oficiales consultadas

| Fuente | Versión visible / referencia | Uso en el código y las pruebas |
| --- | --- | --- |
| [Índice técnico AEAT](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html) | Consultado 23/09/2026 | Punto de partida para localizar fuentes vigentes. |
| [Esquemas AEAT](https://www.agenciatributaria.es/AEAT.desarrolladores/Desarrolladores/_menu_/Documentacion/Sistemas_Informaticos_de_Facturacion_y_Sistemas_VERI_FACTU/Esquemas_de_los_servicios_web/Esquemas_de_los_servicios_web.html) y [WSDL](https://prewww2.aeat.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SistemaFacturacion.wsdl) | `tikeV1.0`, `IDVersion=1.0` | QNames, orden de elementos, tipos, operaciones y destino oficial de pruebas. |
| [Huellas AEAT](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf) | 0.1.2, 27/08/2024, §§3 y 6.1–6.3 | Entrada UTF-8 ordenada, SHA-256 hexadecimal mayúscula y tres vectores independientes publicados. |
| [Servicios web AEAT](https://sede.agenciatributaria.gob.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_Descripcion_SWeb.pdf) | 1.0.3, 28/07/2025, §§6.4.4 y 9.1–9.2 | Estados/CSV, espera entre envíos, subsanación y anulación. |
| [Validaciones y errores AEAT](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Validaciones_Errores_Veri-Factu.pdf) | 1.2.2, §§3.1.3 y 3.1.4 | Reglas de negocio adicionales al XSD; se registran incompatibilidades pendientes abajo. |
| [QR AEAT](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/DetalleEspecificacTecnCodigoQRfactura.pdf) | 0.5.0, §§4–6 | Cuatro parámetros, URL de pruebas y ejemplo independiente con `&` escapado. |
| [XMLDSig W3C](https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd) | Bytes descargados y fijados | Dependencia del XSD AEAT. Su inclusión no implica firma electrónica ni soporte NO VERI*FACTU. |

No se han usado fuentes comerciales para inferir formatos o aceptación. Los esquemas se
descargaron mediante HTTPS verificando TLS y sin certificado de cliente. La AEAT los enlaza
con una indicación de certificado, pero las siete peticiones públicas de esta revisión
respondieron sin él. No se modificaron políticas TLS para descargar documentación.

## Recursos reproducibles y validación

Los siete originales están en `backend/taller/schemas/aeat_1_0/`. Se conservan sus bytes,
incluidos comentarios y saltos de línea. `manifest.json` registra URL inicial/final,
fecha UTC de descarga, tamaño, namespace y SHA-256 por recurso. El 22/09/2026 a las
22:59 UTC corresponde al 23/09/2026 en Europe/Madrid.

El paquete contiene WSDL; XSD de suministro, tipos comunes, respuesta, consulta y respuesta
de consulta; y la dependencia XMLDSig. Se compilan los seis XSD offline. El DTD declarado por
el original W3C no se descarga ni se carga: el parser usa `load_dtd=False`,
`resolve_entities=False` y `no_network=True`.

`official_schema()` verifica las huellas del manifiesto antes de compilar y solo resuelve
las rutas locales previstas y la referencia exacta XMLDSig. `validate_official_xml()` exige
un mensaje único dentro de SOAP. La emisión local también aplica el XSD antes de guardar
el registro y consumir su numeración transaccional. No depende de descargar esquemas ni
de configurar un certificado.

La acción `fiscal.specs` comprueba otra vez los originales públicos con TLS, sin usar el
certificado del titular. Una divergencia respecto a los bytes revisados produce
`schema_update`: exige revisar y actualizar la aplicación; no activa esquemas nuevos
silenciosamente. La copia descargada es informativa; la validación usa siempre los
recursos de la versión instalada.

Los avisos/licencia de XMLDSig permanecen en el recurso original. Los ficheros AEAT conservan
su autoría. No se han incorporado documentos, certificados o identidades de clientes.

## Cambios comprobados en este hito

| Problema previo | Corrección y evidencia |
| --- | --- |
| No había XSD en la entrega y la descarga exigía certificado. | Recursos fijados, validación offline, descarga pública real sin certificado y prueba de cambio de huella. |
| Las rectificativas omitían `IDEmisorFactura` en `IDFacturaRectificada`. | Se usa el NIF del snapshot original. Casos R1/R2/R3/R4 por diferencias, con importes negativos, superan el XSD. |
| `subsanacion` forzaba `RechazoPrevio=S`. | La normal omite rechazo previo; el circuito selecciona `X` tras rechazo sin versión aceptada y `S` tras rechazo cuando existe una versión aceptada anterior. |
| Anulación no podía expresar indicadores. | El serializador admite `SinRegistroPrevio` y `RechazoPrevio`, diferenciados de rectificación comercial. |
| El parser admitía XML sin estructura oficial. | Valida XSD, emisor, identidad, operación, indicadores, referencia si viene informada, coherencia de estados y CSV para aceptar. |
| Error anidado de duplicado podía confundirse con el error actual. | Lectura por ruta directa y detalle del registro duplicado separado; permanece `duplicate_review`, nunca aceptación automática. |
| Espera AEAT truncada a 3.600 segundos y registros nuevos podían adelantar anteriores. | Conserva hasta 9.999 segundos, hereda la espera persistida y atiende el registro pendiente más antiguo. Pruebas con SQLite real y transporte inyectado. |
| Respuesta no reconocida se borraba del intento. | Se conserva y pasa a resultado incierto. La consulta oficial precede a cualquier reenvío del XML inmutable. |

Los tres valores esperados de huella de las pruebas proceden del PDF oficial, no de
ejecutar la función probada. La URL QR esperada también procede de su ejemplo oficial.
Los registros de taller, CSV y respuestas de transporte de los tests son sintéticos y
están identificados como tales. Ningún test constituye un acuse real.

## Circuito integrado en la segunda fase

`Fiscal.correct` genera nuevos registros relacionados con su predecesor, conserva XML,
huellas y factura comercial, y usa una clave idempotente ligada al contenido solicitado.
La migración 2 retira la unicidad por documento/tipo que impedía sucesivas subsanaciones.
Los cambios monetarios exigen rectificativa comercial. La anulación de un resultado
desconocido espera a que se resuelva, para no adivinar sus indicadores.

`Fiscal.reconcile` construye la consulta oficial por emisor, período e identidad exacta.
La respuesta se valida contra `RespuestaConsultaLR.xsd` y se compara con el XML enviado:
identidad, importes, destinatarios, descripción, sistema, encadenamiento, instante y huella.
Un contenido divergente bloquea la cola como conflicto. Una coincidencia con una versión
anterior conocida permite reintentar la corrección pendiente sin modificar sus bytes.
No encontrar el registro permite reenvío; nunca significa aceptación. Se conserva cada
petición/respuesta de consulta. El CSV del envío se conserva cuando se recibe y no se
reconstruye: el servicio de consulta no lo recupera. El identificador de petición devuelto
queda separado del CSV. Fuentes: servicios web, §§6.4.1–6.4.4 y anexo IV.

La cola tiene una reserva SQLite por entorno, con vencimiento de 120 segundos, y un plazo
global persistente. Varios objetos del servicio no pueden enviar simultáneamente; al
reiniciar solo se recuperan reservas vencidas. Una espera remota se aplica también a
facturas creadas después. Un envío interrumpido pasa a consulta. Los acuses, intentos y
reconciliaciones son inmutables. La protección de restauración se aplica a emisión,
subsanación y envío; permite la consulta para resolver resultados ya existentes.

`verify_chain` verifica asimismo XSD y equivalencia XML/datos. La antigua versión del
productor se conserva desde el XML cuando una base v1 todavía no la tenía en el JSON.
El envío vuelve a comprobar la integridad del registro antes de abrir el transporte.

La validación de negocio rechaza E2/E3/E5 en esta configuración antes de consumir número:
el régimen general fijo no cubre E2/E3 y falta identificación internacional para E5.
La aplicación no genera silenciosamente una combinación que pase XSD y sea incompatible
con estas reglas. Ampliar esos tratamientos exige modelar sus datos y reglas específicas.

## Migraciones y recuperación

`taller.db.migrate_connection(conn)` es compartida por arranque y restauración en staging.
No acepta una transacción ya activa. Aplica todas las versiones pendientes dentro de
`BEGIN EXCLUSIVE`, comprueba claves foráneas e integridad antes del commit y conserva
un historial con SHA-256 del SQL. Un fallo revierte DDL, filas e identificador de versión.
Una base sin versión pero con tablas o un historial divergente se bloquean para diagnóstico.
El arranque hace una copia SQLite consistente antes de actualizar una base antigua.

La migración 3 añade procedencia/lotes de importación y evidencia de cobros históricos.
Permite números repetidos de documentos históricos sin relajar la unicidad de facturas
emitidas. Los snapshots y evidencias de cobro permanecen inmutables; una factura no puede
volver a borrador. Las futuras migraciones se añaden como módulos nuevos, sin reescribir
el SQL de una versión ya entregada. Copias verificadas se migran antes de sustituir el activo.
La migración 4 registra procedencia de intercambios mTLS reales. La 5 incorpora el esquema
coordinado de agenda, excepciones y avisos; su comportamiento se verifica en su propia fase.

## Desarrollo y verificaciones que todavía impiden cerrar VERI*FACTU

Esta lista es resultado de inspección de este hito; debe actualizarse al resolver cada
punto y no sustituye la matriz completa del encargo.

1. Completar verificación integrada de la interfaz de corrección/consulta y recorridos E2E
   sobre la última versión; las pruebas fiscales aquí descritas cubren el servicio Python.
2. Completar separación de instalaciones/datos y activación real con todos los gates,
   destinos autorizados y diagnóstico. Se conservan las barreras de producción y documentos
   de pruebas; retirarlas no completa esta tarea.
3. Ampliar reglas fiscales si se incorporan tratamientos bloqueados, y ejecutar las
   validaciones remotas reales del alcance admitido; pasar XSD no sustituye esa comprobación.
4. Completar interpretación de errores y acciones recuperables, representación y custodia
   Windows/caducidad real, y matriz de declaración responsable para productor identificado.
5. El adaptador B2B ya genera/valida UBL y conserva recepción y estados locales por separado.
   Su conexión pública depende del perfil/contrato definitivo no localizado en las fuentes
   oficiales revisadas. Alcance, evidencia y dependencia en `B2B-FUENTES-2026-09-23.md`;
   no se deduce cumplimiento B2B de este XML VERI*FACTU.

## Verificación externa pendiente

La prueba autenticada requiere certificado/representación legítimos e identidad del
obligado y productor. No se han facilitado ni buscado. Una vez disponible el acceso:

1. Usar una instalación de pruebas separada, con copia previa y sin datos del taller.
2. Configurar las identidades autorizadas e importar el certificado mediante el selector
   local de Ajustes. Contraseña y clave permanecen en el equipo; nunca en comandos, Git o informes.
3. Verificar la cadena y la versión de esquemas, activar `aeat_test` y generar una factura
   de prueba con serie propia. La ruta de envío está restringida al destino de pruebas
   del WSDL; el procedimiento no requiere habilitar producción.
4. Ejecutar el envío desde Ajustes y conservar la respuesta XML, estado y CSV reales;
   registrar fecha, versión y huella de la petición, omitiendo datos personales del informe público.
5. Repetir altas, correcciones sucesivas, rechazo/subsanación, anulaciones y consulta de
   reconciliación usando los endpoints implementados; conservar acuses reales de cada caso.

La ruta mTLS está implementada tanto para pruebas como para el destino oficial de producción.
La producción permanece bloqueada por la liberación de versión y el diagnóstico de emisor,
productor, declaración, certificado vigente, esquemas e integridad. Retirar una constante o
rellenar un texto no acredita ensayos externos ni autoriza usar documentos de pruebas como
facturas operativas. No se ha ejecutado autenticación ni presentado datos reales.
El verificador de expediente impide que cambiar un flag sustituya los artefactos requeridos.
Formato, comprobaciones y procedimiento externo en `FISCAL-LIBERACION-2026-09-23.md`.

## Ampliación de rectificativas

Se conserva y serializa FechaOperacion, incluida la comparación en consultas. R2/R3
disponen de rectificación exclusiva de cuota con base cero, importes explícitos y control
de cuota disponible por tipo y familia de documentos. Los tipos históricos 18/8/16/7 se
conservan al importar y se bloquean para emisión S1 por la regla oficial 15.1 revisada.
Contrato, fuentes, caso AEAT y límites B2B en `FISCAL-RECTIFICATIVAS-2026-09-23.md`.
Suite integrada de este hito: 330 pruebas correctas; informe
`reports/pytest-rectification-integrated-2026-09-23.xml`.
