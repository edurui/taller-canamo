# Expediente fiscal de liberación

Estado actual: **no existe un expediente aprobado**. No se han ejecutado pruebas autenticadas
AEAT ni ensayos Windows físicos. La edición fuente es de desarrollo y sigue generando
documentos de prueba. La ruta de liberación está programada, exige un candidato Windows
explícito y evidencias reales; no requiere editar una constante de producción. Este documento
define el procedimiento sin atribuir resultados externos a los tests locales.

## Edición candidata antes de ensayar

El recurso empaquetado `taller/release-policy.json` tiene exactamente tres campos:
`format_version: 1`, `application_version` y `edition`. La fuente lleva `development`.
El constructor permite `release_candidate` solo en la construcción Windows x64 MSVC
completa; rechaza esa opción en Linux y junto a `--sidecar-only`.

Una vez preparado el entorno de [BUILD-WINDOWS.md](BUILD-WINDOWS.md), ejecutar en PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\build_desktop.py --release-candidate
```

El constructor crea la política temporal, la incorpora **antes** de producir el servicio,
ejecuta sus comprobaciones y registra la edición, el hash de la política y los artefactos.
No cambia la fuente ni crea un expediente positivo. Deben conservarse el instalador y
el servicio exactos resultantes: los ensayos posteriores acreditan esos bytes. Reconstruir,
firmar o sustituir el servicio después cambia su hash y obliga a repetir su verificación.
La actualización de versión necesita su candidato y expediente correspondientes.

`build_policy()` exige Windows empaquetado, formato y versión exactos y edición candidata.
El símbolo legado `PRODUCTION_RELEASED` no participa en ninguna autorización. Ser candidato
solo permite presentar la evidencia: faltando cualquier comprobación, producción permanece
bloqueada. La edición de desarrollo distribuida en esta sesión no puede habilitarse mediante
un ajuste, una respuesta simulada o un cambio de esa constante.

## Qué comprueba la aplicación

`taller.fiscal_release.verify_release_dossier(db, config)` solo lee archivos y SQLite.
`Fiscal.readiness()` incorpora su resultado y nunca abre el certificado ni la red.

El expediente se guarda localmente en `secure/release-evidence/manifest.json`, dentro de
la carpeta de datos del usuario. Se comprueban:

- versión de aplicación, NIF del productor e identificador del sistema;
- SHA-256 de la declaración responsable exacta y de cada esquema oficial;
- SHA-256 del ejecutable del servicio actualmente en ejecución, que debe ser Windows
  empaquetado (`sys.frozen`), y coincidencia con el informe de ensayo;
- identidad y fecha con huso del responsable que revisó los ensayos;
- ocho comprobaciones Windows con resultado positivo y artefactos cuyo hash coincide;
- altas, subsanación, anulación y consulta AEAT de pruebas de esta versión, emisor,
  productor y certificado, procedentes del transporte mTLS real de la aplicación.

El hash del servicio se calcula por bloques y admite hasta 2 GiB. El límite del manifiesto
sigue siendo 1 MB; cada artefacto del expediente mantiene el límite de 100 MB. El binario
no tiene que duplicarse dentro del expediente: el verificador lo lee de `sys.executable`.

La migración 4 añade `fiscal_wire_evidence`. Solo el transporte real crea sus entradas,
ligadas al intento o consulta, endpoint exacto, huella pública del certificado y hashes
de petición/respuesta. El verificador vuelve a validar acuses y consultas contra XSD,
operación y registro correspondiente. Ni un CSV inventado en un test ni una respuesta
pasada mediante `transport=` crean esta procedencia. Las entradas antiguas sin procedencia
requieren repetir el ensayo; no se rellenan retroactivamente.

La comprobación de hashes acredita qué archivos revisó la persona responsable. No puede
demostrar por sí sola una impresión física o sustituir la revisión humana de esos ensayos.
El expediente y los XML permanecen en el equipo: pueden contener datos identificativos y
no deben adjuntarse al repositorio ni al informe público de entrega.

## Estructura del expediente

Campos de `manifest.json` (JSON UTF-8):

| Campo | Contenido |
| --- | --- |
| `format_version` | Número `1`. |
| `application_version` | Versión exacta de `taller.__version__`. |
| `producer_nif`, `system_id` | Identidad real del productor y código del sistema ensayado. |
| `declaration_sha256` | Hash SHA-256 hexadecimal minúsculo del texto UTF-8 de la declaración en Ajustes. |
| `sidecar_sha256` | Hash SHA-256 del ejecutable Windows del servicio instalado. |
| `schemas` | Objeto nombre de recurso → SHA-256, exactamente los siete del manifiesto AEAT incluido. |
| `reviewer`, `reviewed_at` | Nombre del responsable y fecha ISO 8601 con huso. |
| `windows` | Objeto `{ "path": "windows-report.json", "sha256": "hash real" }`. |
| `aeat` | Objeto con claves `alta`, `subsanacion`, `anulacion`, `consulta`; valores: ID local del registro cuyo intercambio real acredita cada caso. |

El informe Windows contiene `platform: "Windows"`, `application_version`, `sidecar_sha256`
y un objeto `checks`. Sus claves obligatorias son `install`, `upgrade`, `reinstall`,
`launch`, `dpapi`, `single_instance`, `backup_restore`, `physical_print`. Cada valor contiene
`result: "passed"` y una lista no vacía `artifacts` con objetos `path`/`sha256`. Todos los
archivos se resuelven dentro de la carpeta del expediente; se rechazan salidas de ruta,
artefactos inexistentes y discrepancias de hash. El servicio no crea resultados positivos.

## Ensayo autenticado pendiente

El procedimiento automatizable está en
[FISCAL-ENSAYO-AUTORIZADO-2026-09-23.md](FISCAL-ENSAYO-AUTORIZADO-2026-09-23.md):
`scripts/verify_aeat_authorized.py` comprueba y ejecuta una selección explícita de registros
mediante el candidato real, sin crear documentos ni expedientes. La preparación usa una
cuenta Windows aislada y su carpeta AppLocalData antes del primer arranque de la UI.

1. Usar el candidato Windows ya construido para la versión. No copiar documentos
   operativos. Realizar instalación, actualización, reinstalación, arranque, DPAPI, instancia
   única, copia/restauración e impresión física y conservar sus artefactos reales.
2. Identificar al emisor y productor y confirmar la representación legítima. Importar el
   certificado por el selector local; contraseña y clave nunca van a comandos o informes.
3. Activar únicamente `aeat_test`. Generar un alta y enviarla por la acción normal de la
   aplicación. El código usa el endpoint del WSDL y TLS verificado, sin redirecciones.
4. Consultar el registro, efectuar una subsanación justificada y presentar su anulación
   mediante las acciones de factura/fiscalidad. Conservar IDs, acuses reales y consultas.
   Ejecutar además rechazo/corrección y el caso de resultado incierto según el guion de
   puesta en marcha; los casos locales no sustituyen estas observaciones externas.
5. Reunir el informe Windows y sus artefactos en el expediente y registrar la revisión de
   la declaración. Instalarlo con la herramienta local descrita a continuación, sobre la
   instalación que conserva los registros e intercambios autenticados. No borrar ni
   sustituir el historial de pruebas para trasladarlo: un expediente con IDs ausentes se
   rechaza. Las bases operativas existentes no se utilizan como datos de ensayo.
6. Verificar el diagnóstico completo de Fiscalidad. Solo si `production_ready` es verdadero
   se puede guardar expresamente el modo `production` en Ajustes. Ese guardado vuelve a
   comprobar los requisitos reales con la configuración propuesta y exige resolver la cola
   pendiente antes de cambiar de entorno. Emitir o enviar también vuelve a comprobarlos.
   El expediente y el modo no convierten documentos previos de prueba en operativos.

## Verificar e instalar un expediente existente

Cerrar la aplicación antes de instalar el expediente. Usar el `canamo-service.exe` que
acompaña a la instalación candidata, con la ruta real de sus datos y una carpeta privada
que contenga el expediente revisado. Los siguientes nombres de carpeta son marcadores
de ruta; no contienen datos de prueba para enviar.

```powershell
& 'C:\Ruta\Taller\canamo-service.exe' --data 'C:\Ruta\Datos' --install-release-evidence 'D:\ExpedienteRevisado'
& 'C:\Ruta\Taller\canamo-service.exe' --data 'C:\Ruta\Datos' --verify-release-evidence
```

La herramienta devuelve JSON y código `0` solo si la operación solicitada supera sus
comprobaciones. No inicializa App, migra SQLite, emite, se conecta a la red, crea acuses ni
rellena observaciones positivas. Lee la base existente en modo de solo lectura. La
instalación verifica los hashes, copia únicamente los archivos referenciados, vuelve a
verificar la copia y sustituye la carpeta mediante renombrado. Si existía un expediente,
queda preservado como `release-evidence.previous-<id>` dentro de `secure`.

Un fallo durante el reemplazo intenta reponer la carpeta anterior. Ante una caída de
proceso entre renombrados puede quedar ausente el expediente instalado: el diagnóstico
bloquea producción y debe repetirse la instalación desde la copia privada conservada.
No se afirma una recuperación automática después de cualquier caída. El bloqueo del
sistema operativo evita que una restauración sustituya la instalación durante la copia.

`production_activated` y `network_called` son siempre `false` en esta herramienta. Su
resultado verifica el expediente; el diagnóstico de Fiscalidad comprueba además emisor,
productor, vigencia del certificado y cadena local. El cambio de entorno es una acción
separada de Ajustes y no se hace mediante esta herramienta. La acción pública
`fiscal.readiness` no acepta una configuración enviada por IPC; únicamente Ajustes utiliza
la comprobación privada de su configuración candidata, dentro de su validación.

Los documentos guardan `test_document` según el entorno efectivo **después** de pasar los
controles de emisión; auditoría conserva ese mismo valor. El formateador de URL QR es una
función pura sin red ni emisión. Construir una URL no autoriza emitir un registro.

## Coherencia del certificado protegido

La instalación de un certificado valida el PKCS#12 y escribe su contenido protegido con
DPAPI mediante reemplazo atómico. Si falla el guardado de sus metadatos durante la llamada,
se repone el archivo protegido anterior; si no había uno, se elimina el recién creado.
Una caída del proceso puede interrumpir esa compensación. Antes de construir el transporte
TLS, el programa vuelve a abrir el PKCS#12 y compara su huella SHA-256 real con los metadatos.
Si difieren, pide reinstalar el certificado original y no inicia el envío ni crea evidencia
de intercambio. No se promete recuperar automáticamente un certificado ante esa caída.

La evidencia se atribuye a la huella del certificado efectivamente cargado en el contexto
TLS de esa petición. Un cambio posterior del certificado de la instalación no modifica la
huella de un intercambio que ya está en curso. Contraseña y clave privada nunca se incluyen
en las evidencias, argumentos de proceso, copias ni informes públicos.

## Evidencia local de este cambio

`reports/pytest-release-certificate-2026-09-23.xml`: 137 pruebas dirigidas correctas en
6,82 s en la repetición final dirigida en Linux/Python 3.13.2. Incluyen política de candidato, límites de hash con fichero
disperso real de 100.000.001 bytes, rechazo del expediente sintético sin mTLS, rollback de
instalación, herramienta en un proceso separado sin mutación SQLite, protección de la
publicación y certificados PKCS#12 sintéticos. Las pruebas de certificado sustituyen solo
la frontera DPAPI en Linux; se ejecutan el parseo y la carga real del contexto SSL. Las
respuestas de transporte son locales y no se persisten como aceptación externa.

Los primeros fallos de las pruebas nuevas eran el nombre de tabla de auditoría del fixture
y la ruta de importación del subproceso de desarrollo. Se corrigieron los fixtures; se
conservan ambos XML iniciales. La repetición final ya incorpora el control de caracteres
imprimibles del PDF previo a emisión. Antes pasó también la batería específica de esa
integración (50 pruebas, 2,34 s). La batería conjunta final sigue siendo un hito separado.

No hay autorización para realizar estas llamadas autenticadas en esta sesión. Se han
consultado únicamente documentos y esquemas oficiales públicos, sin certificados.
