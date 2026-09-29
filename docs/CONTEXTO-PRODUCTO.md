# Contexto funcional y decisiones del usuario

## Negocio y personas
Eduardo, desarrollador web habitual en React/TypeScript y usuario de Ubuntu, está renovando
el programa de su tío. El negocio es **Automecánica Talleres El Cañamo**, taller familiar
con un titular autónomo, en Calle Torres Quevedo 22, Polígono El Cañamo, 41300
San José de la Rinconada, Sevilla. No es un proyecto corporativo de su empleador.
Teléfonos distintos aparecen en Maps y en las fotos: los datos deben ser configurables,
no tomarse una foto como confirmación fiscal vigente.

No se conoce la edad exacta del tío. Usuario poco interesado en informática o gestión
compleja; necesita texto legible, atajos opcionales y acciones evidentes. Su sobrino configurará
el sistema, pero el uso diario debe ser autónomo y sin terminal.

Se usará en **un solo PC Windows**, probablemente Windows 11 por las fotos, versión por
confirmar. Se debe poder trasladar al siguiente PC mediante exportación/restauración.
No se ha pedido uso concurrente, red entre PCs, tienda online ni acceso desde el móvil.

## Programa antiguo
Las fotografías muestran Microsoft Access: relaciones, formularios e informe impreso.
No se ha recibido el archivo MDB/ACCDB. La estructura real, macros, consultas y numeración
siguen pendientes de comprobar. Las fotos permiten identificar estas tablas aproximadas:

- `Codigos_Postal`: `cp_codpos`, `cp_poblacion`, `cp_provincia`.
- `Clientes`: `Cod_cli`, `Cliente`, `Cif o Nif`, `Direccion`, `Codigo_postal`, `Telefono1`,
  `Telefono2`, `Fax`, `Email`, `Matricula`, `Tipo de Vehiculo`.
- `Facturas`: `COD_CLI`, `FACTURA`.
- `DETALLE`: `COD_CLI`, `FACTURA`, `CANTIDAD`, `CONCEPTO`, `PRECIO`, `TOTAL`, `FECHAFACTURA`.

El formulario también muestra kilómetros y número de chasis: no se conoce aún su
almacenamiento exacto. No asumir que el diseñador visible muestra todas las tablas/campos.
La factura fotografiada totaliza 770,41 de base + 161,79 de IVA = 932,20; se usa como vector
aritmético de prueba, no como datos a importar. Su número 5133 no debe convertirse
por defecto en el siguiente número real del taller.

## Prioridad 1: lo que el tío necesita
Pantalla inicial sin dashboard cargado de gráficas: búsqueda dominante, nueva factura,
nuevo cliente y acceso al historial. Menú principal: Inicio, Clientes y Facturas.
Vehículos dentro de la ficha del cliente y accesibles desde el buscador global.

Un cliente puede tener varios vehículos. Matrícula normalizada para buscar y detectar
duplicados, preservando su representación visible. Cambio de propietario con historial.
Teléfono del dueño visible inmediatamente: el caso real es ver el coche delante y no
recordar a quién llamar. También hay trabajos en maquinaria; no exigir matrícula
ni vehículo al emitir una factura de un trabajo sin coche.

### Buscador obligatorio
Un input global por nombre, apellidos/razón social, matrícula, teléfono, NIF y código
antiguo. Responde desde el primer carácter, muestra opciones, preselecciona una coincidencia
relevante y ofrece autocompletado aceptable. Enter abre la selección, flechas navegan y Esc
cierra; sin robar el foco ni cambiar de pantalla por quedar una sola coincidencia.
`0540-BZD`, `0540 bzd` y `0540BZD` deben encontrar el mismo vehículo.
Sin resultados obsoletos al escribir rápido y con pruebas de ordenación/latencia.

### Facturas e historial
Cliente -> conceptos/cantidad/precio -> revisar -> emitir -> imprimir/guardar.
Sin presupuesto, orden, referencia de artículo ni movimiento de stock obligatorios.
Conceptos frecuentes/recentes y precios sugeridos editables. Cantidades y precios decimales.
Borradores editables; documentos emitidos inmutables; correcciones por el procedimiento adecuado.
Snapshots del receptor, emisor y vehículo; historial por cliente y por vehículo.
Cobros parciales, pendientes y reversión con trazabilidad. Numeración transaccional,
idempotencia y control de concurrencia, incluso en un solo PC.

## Prioridad 2: aplicación completa pero discreta
Dentro de **Más herramientas**, ocultable sin borrar datos ni romper la facturación:
presupuestos, órdenes/entradas de vehículos, proveedores, artículos, almacén,
movimientos, agenda, informes sencillos y exportaciones.

Presupuesto convertible a orden/factura sin reescribir. Estados de orden: recibido,
en reparación, esperando piezas, terminado y entregado. Notas de entrada, diagnóstico,
trabajos y km. Stock optativo: entrada, salida, ajuste y motivo; evitar doble descuento al convertir.
No construir contabilidad general, ERP empresarial o inventario obligatorio fuera del alcance.

### Agenda
Experiencia comparable en claridad a Google Calendar, NO una integración obligatoria con Google.
Vistas mes/semana/día, Hoy, anterior/siguiente y selector de fecha. Eventos de todo el día,
varios días, citas, tareas, entregas, ITV, mantenimiento y asuntos personales. Cliente/vehículo
opcionales, notas, ubicación, repeticiones y varios recordatorios. Europe/Madrid y pruebas DST.
Diseño adaptable al reducir la ventana, sin tapar títulos o controles; resolver citas solapadas.
Avisos persistentes, configurables, leídos y pospuestos; notificaciones de Windows cuando esté
permitido. Con la ventana cerrada se necesita bandeja/proceso en segundo plano: implementarlo y
explicar el comportamiento. Un PC apagado no debe prometer avisos en tiempo real; recuperar
pendientes al abrir sin tormenta de notificaciones duplicadas.

## Aspecto
Minimalista, moderno, agradable, amarillo/negro/blanco. Amarillo en marca y acciones; no pintar
toda la pantalla de mostaza. Modo oscuro/claro/sistema, letra ajustable, alto contraste,
foco visible, controles grandes y etiquetas de texto. Atajos complementarios, nunca necesarios.

No hay un logo independiente aprobado. Hay un coche rojo/deportivo en el cartel del taller y
un mecánico/coche en la factura anterior; el usuario acepta un marcador temporal y un selector
de imagen en Ajustes. No inventar afiliación oficial con Ferrari ni usar insignias de terceros
como marca del programa. La versión actual lleva un marcador EC y un icono geométrico.

Factura A4 inspirada en la existente: cabecera del negocio y logo, destinatario, número,
fecha, código de cliente, matrícula/km cuando corresponda, conceptos, cantidades, precios,
base/IVA/total y marca de agua del logo. Multipágina con tabla repetida y totales sin solapar.
Reservar QR y textos fiscales según requisitos reales. No rasterizar toda la factura.

## Ajustes y copias
Datos fiscales/contacto, logo cambiable, temas, tamaño de letra, impresión, pie de documento,
IVA habitual, vencimiento, validez de presupuesto, forma de pago e IBAN opcional.
Series diferenciadas por tipo y año: prefijo, relleno, número inicial/siguiente, bloqueo una vez
utilizadas. La migración NO decide por sí sola la serie nueva. No reiniciar para reutilizar números.

SQLite local fuera del código. Copias coherentes automáticas + segunda ubicación opcional
USB/carpeta sincronizada. Sincronizar SOLO copias finalizadas, no SQLite vivo. Restauración
verificada, copia previa, rollback ante fallo y exportación de datos. Reinstalar certificado en
PC/usuario nuevo cuando la protección Windows impida trasladarlo.

## Automatización e IA (secundarias)
Primero las automatizaciones deterministas: reutilizar conceptos, convertir documentos,
recordatorios, preparación de mensajes de vehículo terminado o presupuesto.
IA optativa: dictado, OCR de documentación, consulta de historial y redacción revisada.
Nunca decide diagnósticos mecánicos, seguridad, precios o emisión sin confirmación.
Si no hay modelo/API configurado, todo el núcleo funciona; no forzar una suscripción.
La versión heredada contenía únicamente reescritura opcional con Ollama. La implementación
y comprobación actual de dictado, OCR, consulta y mensajes se documenta en ASISTENCIA.md
y ESTADO-VERIFICADO.md; esta observación histórica no describe el código actualizado.

## Fiscal y entrada en producción
Integrar VERI*FACTU según fuentes oficiales vigentes y separar factura electrónica B2B.
No reutilizar fechas legales desactualizadas de respuestas previas: verificarlas otra vez.
Certificado del titular/representación autorizado aún desconocido; identidad del productor
pendiente. No pedir claves privadas en el chat ni hardcodearlas. Desarrollo local sin ellas;
pruebas de autenticación posteriores en el entorno autorizado.
MDB y certificado NO bloquean el empaquetado, tests o UI. Sí bloquean afirmar migración
real y aceptación autenticada como terminadas. Mantener Access intacto hasta el corte acordado.
