# Agenda del taller

La agenda es opcional y está en **Más herramientas → Agenda**. Funciona con los datos locales del taller. Sus vistas de mes, semana y día usan la semana desde el lunes y la zona **Europe/Madrid**, aunque Windows esté configurado en otra zona.

## Crear, mover y terminar

Selecciona un día o una hora libre, o pulsa **Nuevo evento**. Puedes indicar cita de taller, entrega, ITV, mantenimiento, tarea o asunto personal. El cliente, vehículo, lugar y notas son opcionales.

En semana y día, arrastra una cita para cambiar el día y la hora. Arrastra su borde inferior para cambiar la duración. Los movimientos avanzan en pasos de 15 minutos y abren el formulario: **Guardar evento** confirma las fechas; **Cancelar** conserva las anteriores. Con teclado, abre la cita, modifica **Comienza** y **Termina** y guarda. Los eventos simultáneos se muestran en columnas contiguas.

**Todo el día** pide primer y último día, ambos incluidos en el formulario. Internamente se conservan fechas de calendario independientes y un final exclusivo; un cierre de tres días sigue ocupando tres fechas aunque el cambio horario haga que dure 71 o 73 horas reales. Los eventos que abarcan varios días aparecen en la banda superior de semana/día y en cada fecha afectada del mes.

**Marcar como terminado** detiene los avisos pendientes del evento o del ámbito elegido.

## Repeticiones y excepciones

Las repeticiones pueden ser diarias, semanales o mensuales y deben tener fecha final, hasta dos años desde el inicio. Si un mes no contiene el día elegido, se omite: una cita del día 31 no se desplaza al 28 o al 30.

Al abrir una repetición, **Aplicar cambios a** empieza en **Esta repetición**. Puedes cambiarla de fecha, duración, título, avisos o cliente sin alterar las restantes. Su identidad conserva la fecha original, incluso si la mueves a otro mes. **Eliminar** cancela solo esa repetición.

**Toda la serie** permite editar el patrón original. Las excepciones conservan sus propios datos. Si cambias las fechas o la repetición y existen excepciones, debes marcar **Reiniciar las repeticiones modificadas o eliminadas…**. Así se evita perder cambios individuales sin revisarlos. En ese mismo formulario puedes desplegar las excepciones y **Restablecer repetición**, para volver a los datos originales de la serie.

Si la cita cambió desde que abriste el formulario, la aplicación exige volver a abrirla antes de guardar.

## Cambios de horario

- Una hora inexistente por el adelanto de marzo se rechaza al crear o editar una cita. En una serie se omite esa repetición.
- Una hora repetida en octubre exige elegir **primera vez** (UTC+02) o **segunda vez** (UTC+01) para cada extremo ambiguo. No se elige una de forma silenciosa.
- Las series tienen una política visible para octubre: omitir, primera hora o segunda hora. Los eventos anteriores que no tenían esa elección usan «omitir».
- Las series conservan la hora de inicio de Madrid y la duración real. Un evento que atraviesa el cambio puede terminar a una hora distinta de la que resultaría contando solo las cifras del reloj.

## Avisos, cierre y reinicio

Puedes elegir hasta cinco avisos, de cero minutos a una semana antes. En todo el día, la referencia es las 09:00 de Madrid; los minutos de antelación se descuentan como tiempo real.

Los avisos leídos, entregados o pospuestos se conservan en SQLite. Cambiar solo el título o las notas conserva una postergación. Cambiar la hora vuelve a programar el aviso para la nueva fecha. Cancelar una repetición o completar una cita retira sus avisos pendientes.

Al volver a abrir se presenta un resumen por evento o serie con el número de avisos atrasados. Marcar, leer o posponer el resumen aplica la acción a los avisos que contiene. La confirmación tardía de una notificación no consume un aviso que entretanto se ha pospuesto.

Mantén la aplicación abierta o activa en la bandeja para avisar a tiempo. Al salir completamente, apagar el PC o suspenderlo, no hay un proceso que pueda mostrar avisos. Los pendientes se recuperan al abrir. La prueba física de notificaciones, sonido y bandeja en Windows se registra separadamente de las pruebas de navegador.

## Exportar calendario

**Exportar calendario** genera un `.ics` con las ocurrencias concretas hasta la fecha final de cada serie. Respeta las excepciones, las cancelaciones, las fechas de todo el día y las dos horas de octubre. Es una fotografía finita: no sincroniza cambios posteriores ni crea una serie editable compartida con otro programa. Cada ocurrencia tiene identificador estable; las alarmas de todo el día incluyen su instante real de las 09:00.

Si has cancelado todas las repeticiones, activa **Mostrar canceladas** en la agenda. Las entradas aparecen tachadas; ábrelas para restablecerlas. Mostrar esas entradas no reactiva sus avisos.
