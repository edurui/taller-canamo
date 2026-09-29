# Importación de Access

## Qué lee esta versión

El asistente de Configuración → Traer datos lee copias **MDB y ACCDB** mediante Jackcess
5.0.1 y un JRE Temurin 17.0.20.1+1 incluido en el instalador. No requiere Access, Office,
ACE, ODBC, Python ni Java instalados por el usuario. La arquitectura objetivo es Windows
11 x64; la extracción real de pruebas se ejecuta también en Linux x64.

Se abren únicamente tablas locales en modo de lectura. Se desactivan expresiones y
resolución de vínculos. No se ejecutan consultas, formularios, informes, macros ni VBA.
El diagnóstico enumera tablas vinculadas y nombres/tipos de consultas, pero no abre sus
orígenes ni vuelca cadenas de conexión. La lectura del Access real del taller sigue
pendiente: no se ha recibido ese archivo.

Jackcess declara soporte de formatos Access 2000–2019. Un formato no admitido, una base
dañada o cifrada produce un error, sin importación parcial. El error distingue un codec
de cifrado no admitido cuando la biblioteca lo identifica. No se prueban contraseñas ni
se instala otro controlador automáticamente. Para bases cifradas, el propietario puede
exportar sus tablas desde Access autorizado a un paquete intermedio. Las contraseñas no
se solicitan ni guardan en este asistente.

Fuentes oficiales revisadas el 23-09-2026:
[Jackcess](https://jackcess.sourceforge.io/),
[apertura en modo de lectura](https://jackcess.sourceforge.io/apidocs/com/healthmarketscience/jackcess/DatabaseBuilder.html),
[Temurin 17.0.20.1+1](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20.1%2B1),
[exportación de tablas a texto en Access](https://support.microsoft.com/en-us/access/export-data-to-a-text-file).

## Ensayo antes del cambio definitivo

1. Cierra Access y obtén una copia del archivo. Si usa tablas vinculadas, identifica con
   el propietario las bases que contienen los datos; no basta copiar el frontal.
2. Conserva el original fuera de la aplicación. Prueba primero con una base de ensayo
   de Talleres El Cañamo, separada del trabajo diario.
3. Crea un origen con nombre reconocible, por ejemplo «Access del taller». **Reutiliza
   ese origen en todas las copias posteriores**. Crear otro origen no evita conflictos
   de código o matrícula ni autoriza una fusión.
4. Selecciona la copia y pulsa Diagnosticar. La aplicación conserva sus bytes y SHA-256,
   los tipos/columnas y todas las filas locales; no altera el archivo seleccionado.
5. Revisa el perfil sugerido y guarda el mapeo. Las fotografías sirven para sugerir
   Clientes / Facturas / DETALLE, no para asumir su esquema real.
6. Valida el mapeo, revisa las incidencias y los registros originales. La paginación no
   recorta el lote. Puedes guardar un informe completo con campos no mapeados.
7. Confirma las advertencias y ejecuta Simular. Se aplica el mismo importador sobre una
   copia SQLite aislada. Las fichas de trabajo no cambian.
8. Confirma la importación. Se crea una copia previa y se aplican pasos transaccionales
   de hasta 250 registros desde la interfaz. Pausar o cerrar permite continuar el lote.
9. Comprueba la conciliación de clientes, vehículos, claves, facturas, líneas, bases,
   cuotas e importes. Revisa también exclusiones y discrepancias internas del original.

Para el corte final: detén la emisión en Access, identifica el último documento con el
propietario, conserva una última copia, importa con el **mismo origen y perfil**, compara
las diferencias y acuerda el inicio de uso. Las series nuevas se configuran por separado;
el importador nunca decide el siguiente número ni envía históricos a AEAT.

## Cómo mapear

- Cliente: clave estable, código antiguo y nombre; datos de contacto opcionales.
  Los códigos y teléfonos se leen como texto, incluidos ceros iniciales. Una columna
  numérica que Access ya guardaba como 1 no permite recuperar un formato «001» perdido:
  no se inventa ese formato.
- Vehículo: clave propia o compuesta, clave de cliente, matrícula y datos opcionales.
  Las filas sin matrícula pueden omitirse explícitamente en el perfil sugerido.
  Una matrícula compartida o un propietario ambiguo requiere resolución.
- Factura: clave propia o compuesta, clave de cliente, número, fecha, base, cuota y total
  originales. **FACTURA no se supone globalmente única**: el perfil sugerido usa
  COD_CLI + FACTURA. El número visible se conserva aunque otro cliente tenga el mismo.
- Líneas: claves de factura en el mismo orden, concepto e importe de línea. Cantidad y
  precio pueden ser desconocidos; se conserva el importe y el PDF muestra «No consta».
  Los porcentajes históricos 16 %, 18 %, etc. no se sustituyen por el IVA actual.
- Relación postal: tabla local, clave de cliente/CP y clave de tabla relacionada, con
  población/provincia. Más de una coincidencia bloquea el mapeo; no se elige una al azar.
- Instantáneas: mapear solo columnas guardadas con la factura. La ausencia se marca como
  desconocida; la ficha actual no se copia para aparentar un receptor o emisor original.
- Campos no mapeados: permanecen en el original, staging e informe. Binarios se extraen
  en base64; tipos complejos no convertidos se etiquetan y el Access original se conserva.

Los importes monetarios de cabecera y línea deben poder expresarse exactamente en céntimos.
Una fracción de céntimo en un importe guardado se señala como incidencia; no se redondea
silenciosamente. Cantidades/precios conservan su precisión decimal. El CSV admite punto o
coma decimal según perfil, sin separadores de millares; fechas ISO o día/mes/año explícitos.

Si el informe antiguo calculaba la cabecera y no guardaba esos importes, hay una opción
para declarar su porcentaje histórico y **la evidencia de la fórmula y su periodo**.
Se reconstruyen únicamente los importes ausentes a partir de las bases de línea, con
redondeo comercial a céntimos; el documento queda marcado con esa procedencia. No se debe
aplicar un tipo único a periodos con varios regímenes: prepara lotes/perfiles adecuados.
Importes que ya existen nunca se sustituyen por la reconstrucción.

Una diferencia entre líneas, grupos de IVA y cabecera bloquea por defecto. Se puede aceptar
conservar exactamente el original con una explicación. La conciliación distingue el
descuadre original conservado de una diferencia introducida al importar.

## Resolución, cambios y cobros

El asistente permite excluir un registro con motivo, vincular explícitamente una ficha
existente, aceptar una discrepancia del documento y autorizar una sustitución de un registro
de origen cambiado. No fusiona personas por nombre, NIF o matrícula.

Cada identidad se guarda como origen + entidad + clave de registro. El hash del archivo
identifica una copia; el hash del registro identifica cambios entre copias diferentes.
Un registro idéntico se omite sin duplicarlo. Si un registro desaparece de una copia posterior,
se conserva en destino y se avisa; la omisión no borra información.

La sustitución exige que el destino siga en el estado importado. No pisa una ficha editada,
una transferencia ni un cobro posterior. Una histórica sustituida se conserva inmutable con
estado import_reverted; la versión importada nueva conserva otro identificador y procedencia.

**Cobro desconocido no equivale a impago.** Si el origen no aporta saldo cobrado, el documento
devuelve pagos/saldo desconocidos y queda fuera de deuda pendiente. Si aporta saldo, se guarda
una evidencia de apertura separada e inmutable. Documentar o corregir después un saldo usa las
acciones de cobros documentados y su auditoría; no cambia la instantánea de factura.

## Reanudación y reversión

Las cargas usan fragmentos de 2.000.000 bytes con comprobación de offset/contenido. Al reanudar
se comparan también los fragmentos recibidos: nombre y tamaño no prueban que sea el mismo
archivo. Los lotes, cursor y cambios confirmados están en SQLite. Un paso interrumpido no
queda confirmado a medias; repetir una petición consulta el cursor y las identidades.

La simulación guarda su cursor en la misma transacción que sus cambios, en una base separada.
Cambiar el mapeo invalida esa simulación. Tras empezar a importar, conserva o revierte ese lote
antes de remapearlo. Las copias incluyen los originales y recursos de migración.

Revertir no restaura una base antigua sobre el trabajo posterior. Se comprueba el estado de
cada ficha/factura y sus dependencias. Si hay actividad posterior incompatible, se rechaza
la reversión completa. Si procede, los históricos se desactivan y las fichas nuevas se
archivan; originales y auditoría permanecen. Las fichas vinculadas no se archivan. Una
sustitución puede restaurar el histórico previo conservando ambas versiones.

## Límites visibles y exportación alternativa

| Elemento | Límite/comportamiento |
| --- | --- |
| Access/CSV/carga ZIP | 2 GiB por archivo |
| JSON canónico | 64 MiB; para más, usar ZIP de tablas JSONL |
| ZIP descomprimido | 8 GiB; solo nombres de archivo locales declarados |
| Metadatos ZIP | Directorio central hasta 32 MiB, comprobado antes de cargar su índice; paquete de hasta 10.001 entradas |
| Fila JSONL de extracción/paquete | 2 MiB por fila codificada, sin límite adicional de número de filas; adjuntos o textos mayores requieren extracción separada |
| Conjunto para copia previa | 8 GiB y 50.000 entradas, comprobados antes de copiar; incluye originales, extracción y base, excluye la simulación |
| Lectura nativa | 120 segundos, proceso con heap máximo 512 MiB; al excederse se informa error |
| Ejecución/simulación | API 1–500 registros por paso; interfaz 250 |
| Incidencias/registros | 50 por página; informe íntegro y sin corte de 300 errores |
| Informe descargado por interfaz | 100 MiB; para más, herramienta de copia secuencial |

No existe el antiguo límite de 15.000 registros por lote. Los originales no se truncan si
un recurso supera un límite: se detiene con un error y se conservan los datos para preparar
una extracción controlada. El tiempo de procesamiento depende del equipo y de los datos.
La vista previa informa del tamaño actual y del tamaño de SQLite proyectado tras simular;
la copia previa vuelve a comprobar el conjunto antes del primer cambio. Un lote de prueba
sin pasos aplicados se puede descartar con motivo; un lote aplicado conserva evidencia y usa
la reversión. La descarga de copias usa bloques de 1 MiB, sin reconstruir la copia entera en memoria.

Las plantillas sintéticas están en `tools/access/templates/`. Para preparar un paquete de
varias tablas CSV exportadas por el propietario, el desarrollador/encargado de migración dispone
de la herramienta completa (sin escribir código de conversión):

```powershell
.venv\Scripts\python scripts\access_tool.py csv-package copia-intermedia.zip `
  --table Clientes=clientes.csv --table Facturas=facturas.csv --table DETALLE=detalle.csv `
  --encoding utf-8-sig --delimiter ';'
```

No abrir y volver a guardar CSV en Excel con conversión automática de códigos/fechas. Exportar
con cabeceras y sin formato visual; escoger la codificación explícita y contrastar los
conteos con Access. Un CSV de clientes se puede seleccionar directamente en el asistente.

Extracción nativa independiente e informe grande:

```powershell
.venv\Scripts\python scripts\access_tool.py extract copia.accdb copia-intermedia.zip
.venv\Scripts\python scripts\access_tool.py report RUTA\imports\UUID\report.jsonl informe-completo.jsonl
```

La herramienta no sobrescribe destinos existentes. CSV/JSON/ZIP intermedio se identifica como
tal en el diagnóstico; no se presenta como una prueba de lectura MDB.

## Construcción y comprobación reproducible

```powershell
# Desarrollo: JDK 17 o posterior de fuente oficial. El cliente recibe el JRE incluido.
.venv\Scripts\python scripts\prepare_access_runtime.py
.venv\Scripts\python -m pytest tests/test_access_imports.py tests/test_access_adversarial.py
```

`tools/access/dependencies.lock.json` fija URLs y SHA-256. El script verifica descargas,
compila el lector y conserva licencias/avisos. Jackcess: Apache-2.0; Temurin: GPL-2.0 con
excepción Classpath, con sus avisos incluidos. Las fuentes del lector son propias y están
en `tools/access/CanamoAccess.java`; la biblioteca y runtime mantienen su distribución y
fuentes oficiales identificadas. No se incluyen controladores Office ni herramientas de
control remoto en el instalador.

`CanamoAccess fixture` genera MDB 2000 y ACCDB 2010 exclusivamente sintéticos, incluso un
vínculo a un destino inexistente para comprobar que no se sigue. Las bases generadas no van
a Git. Informes y límites ejecutados: `reports/access-2026-09-23.md`.
