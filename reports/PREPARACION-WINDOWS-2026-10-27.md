# Preparación de entrega Windows · 27/10/2026

## Estado de esta revisión

Datos de ensayo preparados y restaurados correctamente. Construcción candidata
Windows en curso; todavía no se acepta ni se entrega un instalador. El resultado
final debe actualizar este apartado y `docs/ESTADO-VERIFICADO.md`.

Se utiliza el repositorio público existente y el runner estándar Windows de su
workflow manual. Solo fuentes, dependencias públicas y pruebas sintéticas viajan
al runner. No se suben MDB, copias `.canamo`, certificados ni datos de clientes.

## Datos completos para el ensayo

Copia `.canamo` cifrada, con contraseña aleatoria guardada en un archivo local
separado, fuera de Git y de la carpeta de entrega. La copia contiene 1.598 clientes,
1.292 vehículos y 5.145 históricos activos, sus revisiones, configuración y recursos.

Antes de crearla se añadió el MDB actualizado completo como un lote exclusivamente
diagnosticado del mismo origen, sin aplicar sus modificaciones de fichas ni altas
pendientes. Así se conserva en la propia copia toda la evidencia nueva, incluidos
los nombres/NIF de los dos códigos pendientes y las líneas sin número de factura.
Los casos que el usuario decidió dejar pendientes conservan esa condición.

Comprobaciones sobre el archivo cifrado real:

- SHA-256 del archivo exportado coincide con la copia creada por la aplicación.
- Restauración por bloques en un destino vacío con otro identificador de equipo.
- Las 22 tablas comparadas son idénticas y los 36 recursos mantienen sus hashes.
- Integridad SQLite, claves foráneas, auditoría y reapertura correctas.
- Rechazo de contraseña incorrecta.
- Restauración desde la interfaz real: selección del archivo, contraseña, vista
  previa sin cambios de dominio, confirmación RESTAURAR y datos tras recargar.
- Cero errores JavaScript, cero peticiones externas y auditoría Axe sin violaciones
  en ese recorrido. La accesibilidad completa no se certifica con esta comprobación.

Después de corregir la portabilidad de copias, se restauró otra vez **el mismo
archivo cifrado** en un destino nuevo con el backend `f115935`: vuelven a coincidir
las 22 tablas y los 36 recursos; integridad/FK, auditoría y reapertura correctas.
Este ensayo adicional se ejecutó en Linux; no se atribuye a Windows ni se subieron
datos del taller al runner.

La copia ordinaria restaurada en otro equipo queda en `transfer_required`: permite
consulta y borradores, pero conserva bloqueada la emisión. No se preparó ni activó
un traslado que retirase la previsualización de origen. El traslado definitivo
requiere el corte y la copia final de Access, además de los requisitos de emisión.

Las cantidades monetarias y los documentos que identifican a clientes permanecen
exclusivamente en el expediente privado. Los 99 históricos pendientes de revisión
y las estimaciones conservan sus etiquetas; no se sustituyeron por importes acreditados.

## Correcciones comprobadas del proceso Windows

1. El primer intento rechazó la versión Java de cuatro componentes en setup-java.
   Se fija el JDK oficial exacto en `tools/access/dependencies.lock.json` y se instala
   su archivo tras comprobar SHA-256, sin bajar de versión ni saltarse la verificación.
2. El siguiente intento detectó lectura CP1252 de JSON UTF-8 en el inventario de
   licencias. Los preparadores afectados leen UTF-8 explícitamente. Una regresión
   sintética reproduce el error con el código anterior y pasa con el corregido.
3. El tercer intento detectó que el checkout de Windows alteraba avisos fijados por
   hash. `.gitattributes` conserva los bytes de recursos publicados. También se
   recuperaron los CRLF originales de tres archivos AEAT que Git había normalizado
   anteriormente. Ningún hash esperado, esquema ni aviso se sustituyó por otro.
4. El cuarto alcanzó pytest y detectó incompatibilidades reales con Windows: URI
   `file:/D:/...` rechazadas por los resolutores locales, `fsync` sobre archivos
   abiertos solo para lectura y comprobaciones POSIX de permisos. Se admiten solo
   las formas equivalentes de cada ruta verificada, sin acceso a red ni resolución
   por basename; se mantiene `fsync` con descriptores de escritura. El forense aplica
   la DACL privada existente antes de escribir, y su prueba inspecciona los SID en
   Windows. La simulación de una base v8 cierra sus conexiones antes de renombrarla.
   No se omiten pruebas ni se rebajan las garantías de copia o de validación XML.
5. El quinto deja 812 pruebas correctas y dos fallos. Quedaba otro descriptor de
   solo lectura en la copia del expediente; se corrige y la regresión exige un
   descriptor de escritura también en Linux. Control negativo: falla con el código
   anterior (0,24 s); con la corrección, 38 dirigidas correctas (3,99 s).
   Revisados todos los `fsync` de backend/scripts y `sync_all` de Rust: archivos
   escritos con descriptor de escritura; sincronización de directorios solo POSIX.
   El otro fallo era la autoload de Get-Acl en la cadena pwsh → Python → Windows
   PowerShell, con `PSModulePath` heredado. Se aplica la
   [solución documentada por Microsoft](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath?view=powershell-7.3):
   retirar esa variable solo del proceso hijo; se mantienen los SID exigidos y se
   convierten los errores PowerShell en fallos del proceso. La DACL no se relaja.

Para evitar esperar una batería entera por esas regresiones, el workflow ejecuta
primero ambos casos en un paso independiente. Solo si pasan inicia el build completo.
Pytest completo usa `--maxfail=1`: se detiene en el primer fallo, pero si pasa ejecuta
todos los casos. No se acepta un instalador solo con la comprobación dirigida.

El sexto intento se detuvo en ese paso inicial en 5,81 s: Get-Acl ya leía la DACL
y mostró permisos explícitos adicionales creados por `mkdir(0700)` de Windows.
`icacls /grant:r` no eliminaba esos permisos de otros SID. Se sustituye la DACL
completa mediante la [API nativa SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow),
con DACL protegida y una única entrada heredable para el SID actual. Se tipan los
punteros y se libera el descriptor; no se cambia el usuario propietario ni se
ocultan errores del sistema. Se conserva la exigencia original del test, sin admitir
otros SID para forzar su aceptación. 56 dirigidas locales correctas (11,70 s);
su rama Win32 requiere el resultado real del siguiente paso inicial de Windows.

Checkout nuevo con `core.autocrlf=true`: **69 recursos** coinciden con sus SHA-256
publicados/fijados. Regresión Git sintética correcta. Las diferencias de los tres
recursos oficiales son solo sus saltos de línea originales. Su whitespace publicado
se conserva: el `diff --check` de fuentes excluye esos recursos verbatim y pasa;
los recursos se verifican byte a byte, sin alterar el validador de integridad.

Pruebas Python locales finales tras las correcciones Windows: **818 correctas, 57,72 s**,
cero fallos. Nuevas regresiones para alias exactos y sincronización con escritura;
74 pruebas dirigidas correctas antes de la batería completa. Logs/XML
en `reports/windows-delivery-2026-10-27/`, fuera de Git. Antes, 25 pruebas dirigidas
correctas. No hay cambios de interfaz o dependencias npm en estas correcciones.

Intentos públicos y fuentes exactas:

- [40541843983](https://github.com/edurui/taller-canamo/actions/runs/40541843983):
  fallo de preparación Java, fuente `445f25b`.
- [40542558800](https://github.com/edurui/taller-canamo/actions/runs/40542558800):
  fallo de codificación del inventario, fuente `14e79fd`.
- [40543584227](https://github.com/edurui/taller-canamo/actions/runs/40543584227):
  alteración de bytes por checkout, fuente `5c52965`.
- [40545021401](https://github.com/edurui/taller-canamo/actions/runs/40545021401):
  fallo pytest Windows, fuente `cbb4af6`: 575 correctas, 206 fallos, 30 errores.
- [40548059287](https://github.com/edurui/taller-canamo/actions/runs/40548059287):
  812 correctas y dos fallos, 486,87 s, fuente `f115935`.
- [40550311167](https://github.com/edurui/taller-canamo/actions/runs/40550311167):
  fallo de DACL detectado en la comprobación inicial (5,81 s), fuente `2b1a723`.
- [40550982284](https://github.com/edurui/taller-canamo/actions/runs/40550982284):
  dos regresiones iniciales correctas; **814 pytest Windows correctas (455,99 s)**,
  typecheck de aplicación/E2E y build correctos. Navegador: 158 correctas y seis
  fallos (7 min); no llegó a empaquetar. Fuente `dabe244`.
- [40555479990](https://github.com/edurui/taller-canamo/actions/runs/40555479990):
  **814 pytest Windows (445,21 s) y 164 E2E Windows (7,5 min) correctas**,
  typechecks y build correctos. PyInstaller creó el servicio, pero su arranque
  detectó salida JSON CP1252, incompatible con el lector UTF-8. Fuente `b7d6da9`.
- [40559653905](https://github.com/edurui/taller-canamo/actions/runs/40559653905):
  fuente `64d89c7`, detenido antes de baterías largas: el servicio congelado ya
  arranca y supera PDF, cadena, CEN/EN16931, OCR, voz y lectura/mapeo Access.
  Falla el descarte de la importación sintética; aún sin NSIS aceptado.
- [40561307066](https://github.com/edurui/taller-canamo/actions/runs/40561307066):
  fuente `8dcf8ad`: servicio congelado completo correcto (nueve comprobaciones),
  **818 pytest Windows (608,96 s), 164 E2E (8,3 min) y 16 Rust correctas**.
  Tauri compilado, NSIS generado y diagnóstico del conjunto correcto. La guarda
  final rechazó cambios en entradas; no se aceptó el instalador ni se ejecutaron
  todavía instalación y WebView2.
- [40568228932](https://github.com/edurui/taller-canamo/actions/runs/40568228932):
  fuente `69035ab`; herramientas WebDriver y comprobaciones iniciales correctas,
  servicio congelado completo y 818 pytest Windows (446,93 s). Navegador: 163
  correctas y una fallida (7,3 min), al pulsar Artículos durante el despliegue del
  menú en el caso accesible claro a 1366 px. Sin instalador aceptado en este intento.

Las seis incidencias de navegador anteriores se localizaron en el arnés: tres
lectores Python emitían CP1252 y Node los interpretaba como UTF-8; ahora todas las
invocaciones auxiliares Python E2E usan `-X utf8`. Dos esperas admitían el h1 de la
pantalla inicial y continuaban antes de cargar la aplicación; ahora esperan la
cabecera real o el título concreto de Inicio. La restauración de proveedor espera
que desaparezca «Archivado» y que sus acciones estén habilitadas antes de abrir
el siguiente menú. Los seis recorridos pasan localmente en 13,8 s; typecheck E2E
correcto. No se sustituyen acentos, se eliminan aserciones ni se añaden reintentos.
No cambió código de aplicación ni datos en esta corrección. Batería completa de
navegador local final: **164 correctas, 3,9 min**, cero fallos, omitidas o reintentos.
En Windows también pasó la batería completa sobre `b7d6da9`; aún sin aceptar un EXE.

El siguiente fallo era del protocolo empaquetado: la consola Windows elegía CP1252
y la salida JSON incluía caracteres literales. El IPC y la CLI de expediente ahora
usan escapes JSON ASCII, un subconjunto válido de UTF-8; el receptor recupera los
caracteres originales, sin cambiarlos en SQLite, PDF o pantalla. Dos controles
negativos reproducen el fallo anterior en 0,42 s; con la corrección pasan 44
dirigidas en 1,32 s. La regresión fuerza consola CP1252 e incluye español, griego,
un emoji y ruta con tilde. El paso inicial Windows incluye ahora este caso.

La construcción verifica primero el servicio congelado y sus motores; después
ejecuta todas las pruebas Python/E2E y Rust, construye Tauri y verifica el instalador.
Una regresión de orquestación exige abortar antes de las baterías largas si falla
el servicio empaquetado. No se omite ninguna prueba ni se acepta un paquete con
pruebas incompletas: todas se refieren a los mismos bytes y permanece la guarda
de estabilidad de fuentes/recursos.

En la investigación del descarte se localizó una conexión sin cerrar en
`Staging.load_extracted`: el contexto SQLite hacía commit/rollback, pero no cerraba
el archivo. Se usa `closing` y se conserva el contexto transaccional. Se corrige
el mismo patrón en el guion de ensayo; no aparecen otros contextos de conexión
sin cierre en backend/scripts. Dos regresiones retienen una referencia fuerte
para que el GC no oculte el fallo: éxito y error debían cerrar la conexión, y el
error debía revertir las filas parciales. Ambas fallan en la versión anterior
(0,05 s); 26 dirigidas correctas después (8,34 s). La confirmación del descarte
en el ejecutable congelado corresponde al siguiente intento, no a estas pruebas
locales. Los MDB y datos reales no se usan en este diagnóstico.

La discrepancia final de entradas se reprodujo en un clon independiente con
`core.autocrlf=true`: Tauri CLI 2.11.5 reescribe `src-tauri/Cargo.toml` de CRLF a LF
antes de compilar. Fue el único archivo versionado modificado, y sus bytes finales
coincidían exactamente con el original LF de Git. Se fija LF para ese manifiesto
en `.gitattributes`; no se excluye del cálculo ni se normalizan sus hashes.
Repetida la prueba con el atributo corregido: **383 archivos versionados intactos**.
Ambas pruebas se detienen deliberadamente después del tratamiento del manifiesto
y antes del compilador; no se presentan como builds Windows. Cuatro controles
dirigidos de checkout/orquestación correctos (0,05 s). Si vuelve a cambiar cualquier
entrada, la guarda conserva el rechazo y genera `windows-inputs-changed.json` con
rutas y hashes anteriores/finales. Las herramientas WebDriver se compilan antes
de las baterías largas, para detectar sus dependencias sin esperar al empaquetado.

Comparación final de datos reales en solo lectura tras la preparación prolongada:
las 22 tablas de negocio de la previsualización siguen idénticas a las de la copia
restaurada. No hubo cambios de dominio posteriores a la copia verificada.

## Impresión y condiciones de puesta en marcha

Generada con el motor real una muestra A4 de una página, exclusivamente con datos
sintéticos y en `local_test`. Incluye «SIN VALIDEZ FISCAL», conceptos con acentos,
cantidades decimales y columnas de importes. PDF renderizado y revisado visualmente;
fuentes DejaVu incrustadas. No se ha enviado a una impresora física.

El diagnóstico real de la previsualización mantiene pendientes identidad fiscal
del emisor, productor, declaración responsable, certificado y expediente de ensayos.
El candidato no activa producción por sí mismo. No se cambiaron flags de producción
ni se enviaron datos a AEAT. Windows físico, impresora y habilitación operativa
siguen requiriendo pruebas y datos legítimos del destino.

El usuario confirma que existe un archivo de tipo Personal Information Exchange.
La interfaz acepta PFX/P12; no se ha recibido ni inspeccionado ese archivo y no se
presupone su vigencia ni representación. La contraseña se introduce exclusivamente
en destino y el certificado se configura aparte de las copias generales.

## Sincronización del menú en las pruebas de navegador

La traza del último fallo muestra foco en «Artículos y stock», pero Inicio sigue
abierto después del clic: el elemento se desplaza con su contenedor recortado
durante la transición. El helper común espera las animaciones finitas reales del
menú antes del clic. Se conservan las comprobaciones de navegación, ordenación,
teclado y Axe; no se añaden reintentos ni se desactivan transiciones. Las pruebas
específicas de animación del menú permanecen sin cambios. Los cuatro casos de
menús accesibles se ejecutan además con transición de 1,2 s, para exigir esa espera.

`npm run typecheck:e2e`: correcto. Cuatro casos dirigidos correctos (7,3 s).
Batería E2E local completa: **164 correctas (4,0 min)**, cero fallos, omitidas o flaky. El gate Windows previo incorpora esos cuatro
casos: exige diez correctos, cero omitidos, fallidos o flaky, antes del build largo.

El resumen de `desktop_smoke.py` también reproduce UnicodeEncodeError en CP1252
por las flechas de sus comprobaciones. Se escapa únicamente su JSON de consola,
conservando los caracteres originales al leer JSON y el informe UTF-8 en disco.
Control negativo anterior y comprobación corregida ejecutados sin abrir la app ni
repetir baterías. Se cancela `40573597348` durante preparación de dependencias para
incorporarlo antes del siguiente build completo. El selector Edge Driver aplica
la misma separación PSModulePath ya requerida por pwsh → Windows PowerShell 5.1.

## Selección con puntero inmóvil y orden de construcción

[40573910114](https://github.com/edurui/taller-canamo/actions/runs/40573910114),
fuente `2eb0e90`: seis regresiones Python (9,55 s), diez E2E iniciales (43,6 s),
servicio congelado completo y 818 pytest Windows (452,81 s) correctos. La batería
completa acaba con 163 E2E correctas y una fallida (7,8 min): la primera dirección
ya no estaba seleccionada antes de pulsar flechas. No se generó un instalador.

La traza conserva el ratón en (451,32;616,4), coordenadas del botón «Nuevo cliente»
que después ocupa la segunda sugerencia. Al aparecer el popup se genera entrada
de puntero sin movimiento y `onMouseEnter` cambia el índice activo. Se reproduce
localmente dejando el puntero en la futura segunda fila: falla la misma aserción
con el código anterior. Se cambia a movimiento real y se ignoran desplazamientos
cero, en Autocomplete, Select y buscador global. No cambian clic, teclado, foco,
validaciones, importes ni datos. Revisión React: eventos locales, sin estado,
efectos, listeners globales o dependencias adicionales; ARIA y teclas conservados.

Tres casos dirigidos correctos (5,0 s), typechecks y build correctos. Dos regresiones
con ratón real cubren direcciones y búsqueda de cliente. La batería completa local
termina con **166 E2E correctas (4,1 min)** y **819 pytest correctas (107,51 s)**,
sin fallos, omitidas ni flaky. Se interrumpió una primera pasada
local al corregir el texto esperado de un teléfono sintético; no cuenta como pasada
correcta. La aplicación conserva el formato que el usuario introduce.

Para detectar pronto otro fallo, el build ejecuta la batería completa de navegador
antes del servicio/Python, con parada ante el primer fallo. Si pasa debe ejecutar
todos los casos; después siguen congelado, pytest, Rust, NSIS, hashes, instalación
y WebView2. No se omite ni se reutiliza una batería anterior. La prueba de
orquestación exige que un navegador fallido detenga el empaquetado y borre la
aceptación anterior. El gate inicial Windows exige trece casos de navegador.
