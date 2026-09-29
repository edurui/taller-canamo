# Copias, recuperación y traslado

La aplicación guarda sus datos en la carpeta de usuario indicada en Configuración.
No necesita una base Access para empezar. Las copias de este formato incluyen SQLite,
las imágenes guardadas y los PDF conservados; nunca incluyen el almacén `secure/`,
el certificado, sus claves privadas ni la contraseña protegida de las copias automáticas.

## Crear y conservar una copia

1. En Configuración, abre Copias y crea una copia manual. Puedes protegerla con una
   contraseña de al menos diez caracteres.
2. Guarda el archivo `.canamo` en una ubicación que puedas recuperar si falla el PC.
3. Si configuras una segunda carpeta, la aplicación deposita allí otra copia terminada.
   Puede ser una unidad externa o una carpeta sincronizada. No selecciones la carpeta
   de datos de la aplicación ni sincronices la SQLite que está en uso.
4. Comprueba el resultado. Si la segunda carpeta falla, el mensaje conserva la distinción:
   la copia local existe, pero la segunda copia no se ha completado.

Las copias se escriben en un archivo temporal y se renombran al terminar. Los hashes del
manifiesto comprueban el contenido de cada archivo antes de aceptar una restauración.
Las copias cifradas usan AES-256-GCM y una clave derivada de la contraseña mediante
PBKDF2-SHA256. Conserva la contraseña en un lugar seguro: el archivo cifrado no ofrece
un mecanismo para recuperar una contraseña olvidada.

En Windows se puede proteger la contraseña de las copias automáticas con DPAPI, ligada
al usuario. Esa protección no viaja en las copias. Hay que volver a configurarla en el
PC nuevo; no envíes contraseñas ni certificados por el chat.

La retención automática es configurable por días, semanas y meses; los valores iniciales
son 7, 4 y 12 respectivamente. Solo elimina archivos automáticos que sobren según esa
política. Las copias manuales, previas a una restauración y preparadas para traslado se
conservan hasta que decidas gestionarlas. La retención de copias no sustituye las obligaciones
de conservación de facturas y documentos.

Límites explícitos: **8 GiB de contenido descomprimido y 50.000 entradas**, incluyendo
el manifiesto, que admite hasta 16 MiB. El archivo recibido puede ocupar hasta 9 GiB
para dar cabida al ZIP y al cifrado. Si un conjunto supera un límite se rechaza completo;
no se excluyen registros ni PDF para hacerlo caber. También se comprueba espacio libre
para los archivos temporales y la copia previa antes de reemplazar los datos vivos.
Antes del parser ZIP se recorren sus metadatos con lecturas acotadas: directorio central
de hasta 32 MiB, nombres de hasta 512 bytes y campos extra/comentarios por entrada de
hasta 4 KiB. Se contrastan los recuentos reales y los anunciados. Esto impide que el
índice de un ZIP malicioso solicite primero una reserva de memoria de varios GiB.

ZIP, cifrado y segunda carpeta se procesan mediante bloques de 1 MiB. En el escritorio,
el guardado descarga bloques a un archivo temporal y comprueba tamaño y SHA-256 antes
de sustituir el destino. Se conserva el archivo anterior si falla. Las copias cifradas
mantienen el formato `CANAMO1`: siguen admitiéndose copias de versiones anteriores.

## Restaurar en el mismo PC

1. Selecciona una copia y, si está cifrada, introduce su contraseña.
2. Revisa la fecha, los recuentos y la información sobre migración de versión.
3. Confirma escribiendo `RESTAURAR`.
4. Conserva el nombre de la copia previa que devuelve la aplicación. Esa copia contiene
   el estado anterior a la restauración y puede utilizarse para volver a él.

La carga se hace por bloques y muestra su progreso. Puede pausarse y continuar mientras
se conserva el mismo archivo seleccionado. Tras reiniciar, los bloques ya recibidos siguen
registrados y las cargas pendientes pueden descartarse desde Copias. No se combinan
automáticamente archivos que solo comparten nombre y tamaño. Se admiten tres cargas
pendientes y se retiran las que llevan 24 horas sin actualizarse.

Antes de abrir un ZIP cifrado se autentica todo el contenido AES-GCM. Una contraseña
incorrecta o una alteración no llega al parser ZIP ni al proceso de restauración. El texto
descifrado se prepara en una carpeta privada y se elimina si la validación falla.

La restauración sustituye el conjunto completo de SQLite, imágenes y PDF. También elimina
los recursos que solo existían en el estado posterior; no mezcla carpetas de dos fechas.
El certificado queda retirado y su configuración se borra para evitar heredar credenciales
de otra instalación. Reinstálalo por el procedimiento de configuración del PC autorizado.

Si la restauración falla, se recupera automáticamente el conjunto anterior, incluido el
certificado anterior. Si se interrumpe el proceso o también falla esa recuperación, la
aplicación conserva un diario y los archivos anteriores. Al volver a iniciarla completa
la recuperación antes de abrir o migrar SQLite. Mientras existe el diario no admite
operaciones normales. No borres los archivos `.restore-*` ni edites SQLite para desbloquearla.

La copia previa se cifra con la contraseña proporcionada para restaurar o con la contraseña
automática configurada, cuando exista. Sin ninguna de ellas se guarda sin cifrar, como una
copia manual ordinaria.

## Una copia antigua puede servir para consultar y seguir bloqueando la emisión

La aplicación conserva fuera de la SQLite restaurada la cabeza fiscal, las posiciones
de numeración y el estado de los acuses que ya conocía. Restaurar una copia antigua no
permite borrar esos controles, reutilizar números ni reenviar registros cuyo resultado
posterior se perdería. Puedes consultar el histórico recuperado y preparar borradores.

Para reanudar la emisión debes restaurar una copia que contenga ese historial conocido;
normalmente puede ser la copia previa creada antes de restaurar. No hay un botón que ignore
una cadena incompleta. Un archivo antiguo por sí solo tampoco permite reconstruir las
facturas, números o respuestas emitidos después de su fecha.

## Trasladar a otro ordenador

1. Termina el trabajo del día en el equipo de origen. En Copias, utiliza **Preparar traslado**.
   Esta acción genera el paquete y deja el origen inactivo para emisión y envíos fiscales.
2. Guarda el paquete preparado. Si cancelas el diálogo o necesitas volver a guardarlo,
   repite la acción: se entrega el mismo archivo, con el mismo identificador y su contraseña
   original. No se reactiva el origen.
3. Instala la aplicación en el destino y restaura ese paquete preparado.
4. Verifica los recuentos y el historial. Retira el equipo anterior del uso diario y confirma
   `ACTIVAR SOLO ESTE EQUIPO` en el destino.
5. Configura de nuevo el certificado, la contraseña automática, la segunda carpeta de
   copias y la impresora. La ruta de segunda copia del PC anterior se elimina al trasladar.
6. Comprueba el siguiente número y el estado fiscal antes de la puesta en marcha autorizada.

Una copia ordinaria restaurada en otra carpeta/equipo queda disponible para consulta y
requiere un traslado preparado para activar la emisión. Copiar toda la carpeta de trabajo
manualmente o activar el mismo paquete en dos destinos no constituye un traslado seguro.
Sin un servicio compartido entre ordenadores, la aplicación no puede observar otro PC
desconectado; la confirmación exige mantener un único equipo activo.

Para volver más adelante al PC anterior, prepara un **nuevo traslado desde el PC que esté
activo**, restaura ese nuevo paquete en el anterior y actívalo allí. Así se conserva el
historial generado durante el uso del segundo PC. No reutilices el paquete viejo.

Si el equipo de origen se ha perdido antes de preparar el traslado, conserva la última copia
disponible y los documentos/acuse posteriores que tengas. La restauración permite consultar
los datos, pero no inventa el historial ausente ni autoriza automáticamente la continuación
fiscal. La recuperación de información y su reconciliación son necesarias antes de emitir.

## Verificación y límites

Las pruebas locales cubren bases temporales reales, sustitución exacta de recursos, cifrado,
fallos por etapas, terminación abrupta del proceso, recuperación al arrancar, migración del
esquema 1, rechazo de archivos peligrosos y traslado de ida y vuelta con continuidad de cadena.
Consulta `reports/restauracion-2026-09-23.md` y sus resultados ejecutados.

Todavía debe comprobarse en Windows real el bloqueo de archivos, DPAPI con cambio de usuario,
permisos NTFS, USB y cierre del escritorio durante la copia. La ejecución Linux no acredita
esas pruebas, la impresión física ni aceptación fiscal autenticada.

## Originales de las importaciones

Las copias incluyen `imports/`: originales Access/CSV/JSON, diagnóstico, mapeos en la base
principal, SQLite de preparación y archivos auxiliares. Se verifica que el original coincida
con la huella del lote. Si falta un original o un diagnóstico requerido, la copia falla de
forma explícita. Al restaurar, esta carpeta se cambia y recupera junto con SQLite, imágenes
y PDF, también ante un fallo intermedio. Las cargas incompletas conservan sus originales.

Se excluyen `simulation.*`, copias desechables del ensayo de importación. Su resultado
persistente permanece en SQLite y el asistente puede repetir el ensayo cuando sea necesario.
La capacidad del importador considera el límite conjunto de 8 GiB y los recursos que deberá
conservar la copia previa. Un original de 2 GiB no se convierte entero a base64 en memoria.

La prueba local con un binario sintético de exactamente 2 GiB, más un PDF aleatorio de 4 MiB,
verifica copia cifrada, segunda carpeta, descarga/carga y restauración con SHA-256 idéntico.
No equivale a ensayar un Access real de ese tamaño ni el máximo agregado de 8 GiB. Evidencia:
`reports/backup-capacity-2026-09-23.json` y `reports/copias-streaming-2026-09-23.md`.
