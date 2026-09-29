# Talleres El Cáñamo · Manual de uso

Versión 0.9.1. Esta entrega es una edición de pruebas. **No debe utilizarse todavía
para emitir facturas operativas.** Los requisitos externos y las pruebas ejecutadas
se detallan en [estado verificado](docs/ESTADO-VERIFICADO.md).

## Instalar y abrir

La aplicación destinada al taller es de escritorio para Windows. El equipo del usuario
final no necesita Python, Node, Rust ni Java. El instalador incluye los motores locales;
puede necesitar Internet para instalar WebView2 si no existe en el equipo.

En este entorno Linux no se ha generado ni ejecutado un instalador Windows. La
[guía Windows](docs/BUILD-WINDOWS.md) explica cómo construirlo y comprobarlo. No
desactives las protecciones del sistema para omitir un problema de distribución.

Al abrir por primera vez, configura el taller. **Cargar demostración** crea únicamente
datos ficticios y solo está disponible con la base vacía. Usa una instalación de ensayo
separada; no mezcles la demostración con una migración del taller.

Cerrar la ventana con X la oculta en la bandeja y mantiene los recordatorios activos.
Para terminar el programa, usa la acción Salir del icono de bandeja. Si hay cambios sin
guardar, vuelve al documento y guarda o descarta esos cambios. No copies manualmente
la base SQLite mientras el programa está abierto.

## Trabajo diario: buscar → factura → imprimir

1. Escribe un nombre, matrícula, teléfono, NIF o código antiguo en **Buscar cliente o
   matrícula**. Las matrículas admiten espacios y guiones. Verás el cliente, el vehículo
   y su teléfono. Usa flechas y Enter o selecciona con el ratón.
2. Abre **Nueva factura**. Selecciona el vehículo si procede; también puedes facturar
   maquinaria o trabajos sin vehículo. No necesitas presupuesto, orden ni artículo de stock.
3. Añade los trabajos: descripción, cantidad u horas, precio, descuento e IVA. Los
   conceptos libres no requieren crear artículos. Comprueba cliente, fechas e importes.
   Puedes cambiar el orden arrastrando el asa de cada línea o con sus botones de subir y
   bajar. El asa también admite las flechas del teclado. La vista previa recoge ese orden.
4. **Guardar borrador** permite continuar después. **Revisar y emitir** muestra una
   confirmación. En esta edición el botón indica **Emitir prueba** y el PDF queda marcado.
5. Abre la vista previa del PDF. Puedes guardarlo, abrirlo en el lector del equipo o
   solicitar su impresión. Si el lector no admite imprimir directamente, ábrelo y utiliza
   su menú de impresión. Comprueba la cola y el papel: una solicitud aceptada por el sistema
   no demuestra que la impresora haya terminado.

Una factura emitida conserva sus datos, número, logo y PDF. Cambiar después una ficha o
el logo no cambia esa factura. Si una operación se interrumpe, consulta primero el histórico
antes de repetirla; los números no deben reutilizarse.

El PDF incorpora sus fuentes. Si encuentra un carácter que no puede representar, muestra
cuál es y conserva el borrador sin consumir número; consulta al soporte sin cambiar el
nombre real por una aproximación.

Atajos: **Ctrl K** buscar, **F2** factura, **F3** cliente, **Ctrl S** guardar borrador,
**Ctrl P** vista previa y **Esc** cerrar una ventana emergente.

## Clientes y vehículos

Puedes crear una ficha con un nombre y completar después los datos necesarios para
facturar. Un cliente puede tener varios vehículos. Desde **Historial y titular** puedes
cambiar el propietario con un motivo: el teléfono de la búsqueda pasa a ser el actual,
mientras que las facturas antiguas siguen perteneciendo al titular que figuraba al emitirlas.

La ficha conserva país y código postal. Admite contactos extranjeros; la emisión fiscal
de esta edición está limitada a las operaciones españolas documentadas. El historial usa
páginas para poder acceder también a los documentos antiguos.

Los históricos importados pueden carecer de NIF, dirección, cantidad, precio o tipo de IVA.
El programa muestra **No consta** cuando el original no los conserva. No los completa
con datos actuales ni presenta como impagada una factura cuyo estado de cobro se desconoce.

## Cobros y correcciones

- Registra cobros parciales o completos indicando método, fecha y referencia. Los movimientos
  quedan conservados; una contrapartida revierte el importe sin borrar el movimiento original.
- Una rectificativa referencia la factura original, indica el motivo y permite corregir una
  parte o el total. Las devoluciones y las cantidades pendientes de cobro se muestran separadas.
- Si el desglose histórico está incompleto, introduce el desglose documentado de la diferencia
  y la fecha de la operación original. No deduzcas un IVA antiguo a partir del total.
- Los supuestos R2/R3 corrigen exclusivamente la cuota de IVA cuando corresponda legalmente:
  requieren importe de cuota explícito y conservan la base. Consulta la
  [guía de rectificación](docs/FISCAL-RECTIFICATIVAS-2026-09-23.md).
- **Anular por error material** conserva la factura y su rastro. No está disponible mientras
  existan rectificativas vinculadas que deban revisarse o borradores rectificativos pendientes.
  La anulación del registro fiscal y la corrección comercial tienen finalidades distintas.

## Configuración

En **Taller y logo** y **Facturación** configura identidad, dirección, contactos, logo, IBAN
opcional, tarifa de mano de obra, forma de pago, vencimiento, IVA habitual y textos del PDF.
Los valores predeterminados se aplican a nuevos documentos; revisa los borradores existentes.

Las series pueden ser anuales o continuas. Antes del uso operativo verifica el siguiente
número contra los documentos ya emitidos. Importar Access no decide ese número. Las series
utilizadas no permiten reiniciar su numeración.

**Aspecto y comodidad** permite cambiar tema y tamaño del texto y ocultar las herramientas
secundarias. Ocultarlas no borra su información. Los avisos internos siguen accesibles.

El acceso **Tamaño de letra y aspecto** muestra **Normal**, **Grande** y **Muy grande**.
Al elegir uno puedes comprobar cómo se ve toda la aplicación. Pulsa **Guardar cambios**
para conservarlo al reiniciar; si sales sin guardar se recupera el tamaño anterior.
Este ajuste no cambia el tamaño del PDF impreso.

En los campos de fecha, el botón de calendario permite elegir directamente año, mes y
día; también puedes escribir la fecha. En una ventana estrecha, calendarios y listas de
opciones se abren a pantalla completa. Usa **Esc** o el botón de cerrar para volver.

## Herramientas secundarias

**Más herramientas** contiene presupuestos, órdenes, artículos/stock, proveedores, agenda
y resumen. Ninguna es obligatoria para emitir una factura directa.

- Un presupuesto conserva su validez y estado de aceptación/rechazo. Puedes convertirlo en
  orden o factura conservando la relación. La conversión repetida recupera el documento creado.
- Una orden registra entrada, síntomas, trabajos, piezas y estados hasta la entrega. Convertir
  una orden que ya consumió existencias no vuelve a descontar las mismas piezas.
- El catálogo permite entradas, salidas, devoluciones y recuentos con motivo. Consulta los
  movimientos antes de repetir una operación interrumpida. Archivar conserva el historial.
- **Resumen** filtra fechas y muestra facturación, cobros, pendientes, devoluciones, trabajos
  y mínimos. Los saldos documentados de históricos se distinguen de movimientos de caja.
  Es un resumen operativo; no genera la contabilidad ni declaraciones tributarias.
- La exportación portable entrega JSON, CSV y recursos documentados. Conserva los datos
  originales; los CSV protegen frente a fórmulas al abrirlos en una hoja de cálculo. Para
  recuperar o trasladar el programa utiliza una copia `.canamo`.

## Agenda y recordatorios

Elige mes, semana o día; usa Hoy, las flechas o el selector de fecha. Crea citas, entregas,
ITV, mantenimiento, tareas o asuntos personales. Para cambiar horario/duración puedes
arrastrar o utilizar el formulario. Al editar una repetición, distingue la ocurrencia
individual de la serie completa. Se utiliza la zona horaria Europe/Madrid.

Los avisos se pueden leer o posponer y se conservan al reiniciar. Las notificaciones del
sistema necesitan permiso de Windows y pueden quedar ocultas por su configuración. Si el
programa o el ordenador están apagados, los avisos pendientes aparecen al volver a abrir.
Más detalles: [Agenda](docs/AGENDA.md).

## Copias y restauración

1. Abre **Configuración → Copias y traslado** y crea una copia. Para cifrarla introduce
   una contraseña de al menos diez caracteres; conserva esa contraseña fuera del PC.
2. Guarda el `.canamo` en un disco externo u otra ubicación recuperable. La segunda carpeta
   automática también puede estar en una unidad externa. Comprueba cualquier aviso de error.
3. Para verificarla, selecciona el archivo y pulsa **Comprobar copia**. La carga se realiza
   por bloques y puede pausarse. Una contraseña incorrecta no cambia los datos actuales.
4. Revisa los recuentos. Escribe **RESTAURAR** para reemplazar el conjunto. El programa crea
   una copia previa y restaura base, PDF, logos y originales de importación de forma conjunta.

Las copias no incluyen certificados ni contraseñas protegidas. Hay que configurarlos de nuevo
en el destino. Una copia antigua puede abrirse para consulta y mantener bloqueada la emisión
si le falta historia fiscal o numeración que ya se conocía. Conserva la copia previa.

Para **cambiar de ordenador**, usa **Preparar traslado** en el origen; queda inactivo para
emitir. Restaura ese paquete en el destino, retira el anterior del uso diario y confirma
**ACTIVAR SOLO ESTE EQUIPO**. Configura certificado, copias e impresora en el nuevo PC.
No actives un mismo paquete en dos equipos. Procedimiento completo y recuperación ante
interrupciones: [Copias y traslado](docs/COPIAS-TRASLADO.md).

## Importar Access

Trabaja con una copia del MDB/ACCDB, conservando intacto el original. En **Importar Access**
identifica el origen, carga el archivo, examina tablas y filas y define el mapeo. Revisa
las transformaciones e incidencias, ejecuta la simulación y concilia recuentos e importes
antes de importar. El proceso conserva procedencia y admite lotes, reanudación y rollback
con controles para proteger cambios posteriores.

Las facturas históricas mantienen su numeración y no se envían a AEAT como nuevas.
Cuando llegue el Access real habrá que mapear su esquema, resolver sus incidencias y
ensayar la conciliación con el taller: [guía Access](docs/IMPORTACION-ACCESS.md).

## Asistencia opcional

Se activa en Configuración. El dictado y la lectura de imágenes se procesan localmente;
presentan una propuesta editable antes de incorporarla y la ficha solo se guarda mediante
su acción habitual. Revisa nombres, matrículas, NIF, cifras y términos técnicos.

La consulta del historial y los mensajes preparados funcionan sin IA. Abrir WhatsApp
prepara un texto en una aplicación externa; debes revisarlo y enviarlo personalmente.
La asistencia no decide reparaciones, emite facturas ni contacta automáticamente con clientes.
Funcionamiento y límites: [Asistencia](docs/ASISTENCIA.md).

## Fiscalidad, licencia y soporte local

**VERI*FACTU** muestra la configuración, los registros, su estado y el diagnóstico.
Esta edición no autoriza envíos de producción. La prueba externa necesita certificado e
identidad legítimos y debe ejecutarse en el entorno oficial de pruebas. Consulta
[liberación fiscal](docs/FISCAL-LIBERACION-2026-09-23.md).

La **factura electrónica B2B** tiene su propio apartado y estados. Un XML validado localmente
no acredita entrega al destinatario ni a un servicio público. Su estado se describe en
[fuentes y alcance B2B](docs/B2B-FUENTES-2026-09-23.md).

En **Acerca del programa → Descargar licencias** puedes conservar el inventario, avisos y
enlaces de fuentes de los componentes. Para una incidencia anota acción, hora, texto del
error y versión. No envíes por chat bases del taller, certificados, contraseñas ni datos
personales de clientes. No borres archivos de recuperación ni edites SQLite para quitar un bloqueo.
