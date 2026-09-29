# Copias grandes y exportación portable por bloques — 23/09/2026

## Alcance implementado

`backend/taller/backups.py` ya no reúne SQLite, originales y recursos en un
diccionario de bytes ni genera el ZIP completo en memoria. Utiliza un snapshot
SQLite privado, lee los recursos por bloques de 1 MiB, calcula hashes mientras
escribe ZIP64 y conserva los cambios de conjunto, diario, rollback, copia previa,
retirada de certificado y bloqueo de historial anterior ya verificados.

El cifrado usa `Cipher(AES, GCM)` por bloques con PBKDF2-SHA256. Mantiene exactamente
el contenedor `CANAMO1` anterior, incluyendo AAD, sal y nonce. El tag debe validarse
antes de abrir el ZIP; una contraseña incorrecta o contenido alterado elimina el
temporal descifrado y no llega al parser ni a la restauración. Las regresiones
comprueban interoperabilidad con el cifrado AESGCM de las copias V1.

La segunda carpeta recibe el archivo final por streaming y sustitución atómica.
Si falla, se distingue la copia local terminada de la segunda ubicación pendiente.
Reexportar un traslado entrega el mismo archivo y SHA-256 aunque se cancele el
primer guardado; no desbloquea el equipo de origen ni cambia su contraseña.

`backend/taller/reporting.py` usa el mismo transporte para exportaciones `.zip` y
`.csv`. Recorre JSON y CSV por filas, incluyendo BLOB originales, y recursos por
bloques. Mantiene relaciones, snapshots, auditoría, procedencia, nulos, ceros,
decimales y protección de fórmulas en CSV. El portable continúa siendo una salida
sin cifrar, separada de la copia operativa y sin certificados ni claves.

## Límites comprobados

| Elemento | Límite |
| --- | --- |
| Conjunto descomprimido de copia o portable | 8 GiB |
| Archivos, incluido manifiesto | 50.000 |
| Archivo recibido / transporte | 9 GiB |
| Manifiesto JSON | 16 MiB |
| Directorio central ZIP | 32 MiB |
| Nombre ZIP / campo extra / comentario de entrada | 512 bytes / 4 KiB / 4 KiB |
| Bloque RPC | 1 MiB |
| Compatibilidad RPC con `content` completo | Solo archivos de hasta 4 MiB |
| Cargas pendientes | 3, caducidad a las 24 h sin actualización |
| Permisos de descarga | 32, caducidad tras 1 h sin actividad |

Antes de crear objetos `ZipFile` se inspeccionan EOCD y ZIP64 con lecturas acotadas,
y se recorren los encabezados centrales para comprobar su tamaño y recuento real.
Así un ZIP no puede anunciar pocos archivos y provocar primero la lectura de un
directorio de varios GiB. Se rechazan volúmenes múltiples, posiciones incoherentes,
nombres de control, rutas peligrosas, duplicados para Windows y compresión no
admitida. Se siguen comprobando tamaños extraídos, CRC y hashes. La estructura
se contrastó con [PKWARE APPNOTE 6.3.10](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT)
y los riesgos documentados de [zipfile en Python 3.13](https://docs.python.org/3.13/library/zipfile.html#decompression-pitfalls).

Se comprueba espacio disponible por etapas; una falta de espacio no autoriza una
restauración parcial. Se excluyen `imports/*/simulation.*`, que el importador puede
recrear. Se conservan originales, metadatos, diagnóstico, preparación y datos no
mapeados. Las copias verifican también XML/payload/cadena fiscal y el almacenamiento
B2B, incluidos sus bytes originales, antes de migrar y después si hay migración.

## API y ciclo de vida

- `backup.create` y `backup.prepare_transfer` devuelven nombre, MIME, bytes,
  SHA-256 del archivo final, `capability` opaca y `chunk_bytes`. El valor opcional
  `content` permite mantener clientes antiguos únicamente con archivos pequeños.
- `backup.download_chunk(capability, offset, length)` devuelve un bloque con su
  hash, posición, tamaño total y fin. No acepta rutas proporcionadas por el cliente.
- `backup.release_download(capability)` revoca el permiso. Conserva las copias
  `.canamo`; borra las salidas portables temporales de `.file-exports/`.
- `backup.upload_start(name, total_bytes)`, `upload_chunk`, `upload_status`,
  `upload_finish`, `upload_list` y `upload_cancel` reciben y verifican archivos.
  Los metadatos de progreso se escriben después de `fsync` del bloque. Repetir
  bytes idénticos es idempotente; un hueco o repetición distinta se rechaza.
- Si se interrumpe entre escritura y confirmación del bloque, el siguiente estado
  trunca solo la cola no confirmada. El progreso sobrevive al reinicio. La UI
  continúa con el mismo `File` y permite descartar cargas pendientes al reabrir;
  no combina archivos nuevos solo por compartir nombre y tamaño.
- `Reporting(db, settings, backups)` comparte el registro de capacidades de App.
  La revocación, caducidad y limpieza periódica eliminan salidas portables privadas.
  Directorios de trabajo huérfanos propios se limpian al arrancar cuando superan
  24 h; los diarios y conjuntos de recuperación se gestionan por separado.

Root integró App/UI. Escritorio integró guardado nativo por bloques, comprobación
de tamaño/hash, destino temporal y revocación. Las operaciones largas tienen plazo
específico; el agente de escritorio documenta su regresión de cola y timeout.

## Ejecución local

Entorno: Linux 6.8.0-139-generic x86_64, glibc 2.39, Python 3.13.2 en `.venv`,
SQLite 3.49.1 y cryptography 50.0.1. Todos los datos son sintéticos y temporales.

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_backup_streaming.py tests/test_restore_recovery.py tests/test_workflows.py tests/test_access_imports.py tests/test_access_adversarial.py tests/test_b2b.py -q --tb=short --junitxml=reports/backup-streaming-2026-09-23.xml` | 119 passed, 21,27 s, salida 0 |
| `.venv/bin/python -m pytest tests/test_reporting.py -q --tb=short --junitxml=reports/portable-streaming-2026-09-23.xml` | 12 passed, 3,68 s, salida 0 |
| `.venv/bin/python -m pytest -q --tb=short --junitxml=reports/backend-streaming-final-2026-09-23.xml` | Hito de integración: 371 passed, 38,04 s, salida 0 |
| `.venv/bin/python -m pytest tests/test_backup_streaming.py tests/test_restore_recovery.py tests/test_reporting.py -q --tb=short --junitxml=reports/streaming-zip-directory-2026-09-23.xml` | Tras la guarda ZIP: 65 passed, 21,96 s, salida 0 |

El hito de 371 casos precede a la guarda del directorio ZIP y no es la batería
final del candidato: otros agentes seguían modificando política y expediente.
La regresión posterior específica está en `streaming-zip-directory-2026-09-23.txt/xml`
y cubre directorio sobredimensionado, recuentos falsos, nombres con NUL, ZIP64 y
comentario legacy, además de restauración y portable. La batería final conjunta
la dirige root tras congelar las fuentes.

El caso de exportación recorre 5.000 clientes sintéticos con notas de 2 KiB más un
PDF aleatorio de 6 MiB. Comprueba originales, hashes, descarga y eliminación del
temporal, prohíbe `read_bytes()` sobre archivos grandes y exige menos de 24 MiB de
pico en asignaciones Python. No es una medición del RSS completo del proceso.

## Prueba ejecutada con original de 2 GiB

```bash
PYTHONPATH=backend .venv/bin/python reports/backup-capacity-check-2026-09-23.py \
  > reports/backup-capacity-2026-09-23.json \
  2> reports/backup-capacity-2026-09-23.stderr
```

Resultado: salida 0. Original binario **2.147.483.648 bytes**, más PDF aleatorio de
4.194.304 bytes. Copia AES, segunda carpeta, descarga/carga por bloques, vista
previa, restauración y lectura del original recuperado con SHA-256 idéntico.

- Archivo cifrado: 13.582.419 bytes.
- Creación: 5,712 s; carga/verificación: 3,704 s; restauración/hash: 4,124 s.
- Pico de asignaciones Python durante copia/restauración: **7.687.082 bytes**.
- Portable: 13.584.235 bytes; creación, descarga y verificación: 6,847 s.
- Pico de asignaciones Python del portable: **6.332.335 bytes**.
- Original portable verificado por lectura descomprimida y SHA; temporal eliminado.

El binario es disperso y compresible, con marcadores sintéticos. **No mide un
conjunto de 8 GiB, un Access real, su parser, rendimiento en Windows ni un USB**.
Los tiempos describen este ensayo Linux y no son una promesa de rendimiento.
El primer ensayo tuvo un marcador de fixture un byte más largo que la reserva;
se corrigió el desplazamiento, conservando su stderr. La restauración del primer
ensayo también devolvía el tamaño original, pero el assert del fixture era erróneo.

## Pendiente externo

DPAPI, ACL NTFS, interrupción de Tauri en Windows, USB real e impresión física
requieren el ensayo externo documentado. No hubo envío autenticado AEAT, entrega
remota B2B, credenciales reales ni modificación de datos reales. Manuales actualizados:
`docs/COPIAS-TRASLADO.md` y `docs/INFORMES-EXPORTACION.md`.
