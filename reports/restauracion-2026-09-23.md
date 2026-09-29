# Restauración coherente y traslado — 2026-09-23

Trabajo realizado exclusivamente con directorios temporales y datos sintéticos. Los bytes
usados como certificado en las pruebas son un marcador inerte: no hay una clave privada real
ni una prueba DPAPI fingida.

## Cambios implementados

- `backups.py` usa un directorio de preparación en el mismo volumen, sustituciones de archivos
  y carpetas, un diario persistente y recuperación repetible. SQLite, `assets`, `pdfs`,
  certificado y control de restauración avanzan o vuelven al estado anterior como conjunto.
- La recuperación se ejecuta antes de construir `Database`. La integración en `App` se hizo
  coordinadamente con el agente raíz. Un diario pendiente bloquea los RPC ordinarios.
- Las conexiones SQLite temporales se cierran explícitamente antes de mover los archivos.
  Se completa el WAL del original y se sincronizan archivos/directorios antes de los puntos de
  confirmación donde la plataforma lo soporta. En Windows no se acredita `fsync` de directorios.
- Los recursos restaurados sustituyen exactamente sus carpetas; desaparecen los recursos
  posteriores. Se comprueban también las imágenes referenciadas por los documentos.
- Existe copia previa a cada restauración. Conserva cifrado cuando se proporcionó contraseña
  o está configurada la contraseña automática. El certificado nunca entra en el ZIP; se
  conserva únicamente durante el rollback local y se retira después de una restauración completa.
- Se comprueban hashes, integridad SQLite, relaciones, auditoría y cadena fiscal. El esquema
  del manifiesto debe coincidir con el archivo. Las versiones antiguas admitidas se migran
  después de comprobar hashes y exclusivamente en la copia de preparación.
- El ZIP rechaza escapes de ruta, alias reservados de Windows, colisiones de nombres sin
  distinguir mayúsculas, enlaces/dispositivos, entradas duplicadas, archivos ajenos, compresión
  no admitida y límites excedidos. La vista previa caduca y se vuelve a comprobar antes del uso.
- Los máximos fiscales y de series y los estados de acuses conocidos se mantienen fuera de
  la base restaurada. Una copia anterior bloquea nueva emisión y envíos. Restaurar una copia
  que recupera el historial conocido permite continuar; no existe una anulación manual del control.
- El traslado preparado retira el origen, permite reexportar el mismo paquete tras cancelar
  el guardado y activa un solo destino mediante confirmación explícita. También se prueba la
  vuelta posterior mediante un nuevo traslado desde el equipo activo.
- Si falla una operación después de escribir el paquete de traslado, el origen permanece
  inactivo y el mismo paquete se puede recuperar. El fallo no deja dos orígenes autorizados
  por la misma operación.
- La segunda copia se escribe y publica solo al completarse; un error devuelve advertencia
  con éxito local diferenciado. La retención configurable afecta únicamente a copias automáticas.

## Pruebas ejecutadas

Entorno: Linux 6.8.0-139-generic x86_64, glibc 2.39; Python 3.13.2; SQLite 3.49.1;
cryptography 50.0.1. Las pruebas nuevas están en `tests/test_restore_recovery.py`.

Comando de verificación de esta revisión:

```bash
.venv/bin/python -m pytest tests/test_restore_recovery.py tests/test_workflows.py -q --tb=short --junitxml=reports/restauracion-2026-09-23.xml
```

Resultado: **64 casos superados, salida 0**. Texto y JUnit en
`reports/restauracion-2026-09-23.txt` y `reports/restauracion-2026-09-23.xml`.
La batería combina las regresiones de restauración con los flujos ya existentes;
no representa 64 operaciones de usuario diferentes.

Evidencia relevante:

- Fallo inyectado después de preparar y después de guardar/instalar base, imágenes,
  PDF, certificado y control: el conjunto anterior sobrevive en las diez etapas ensayadas.
- Tres subprocesos terminan realmente con `os._exit(73)`: base retirada, imágenes instaladas
  y commit escrito. El siguiente `App` recupera el estado anterior en los dos primeros
  casos y conserva el conjunto restaurado en el último.
- Fallan tanto instalación como rollback: el diario queda disponible, los RPC no escriben
  sobre la base parcial y el siguiente arranque termina la recuperación.
- Una cadena con huella incorrecta se rechaza incluso aunque el ZIP contenga hashes
  actualizados que coincidan con los archivos modificados.
- Copia con mismo registro fiscal pero anterior al acuse: queda bloqueada sin olvidar el
  resultado conocido. Copia anterior a una factura: no permite repetir su número.
- Copia previa recuperada: siguiente factura conserva número y encadenamiento.
- Esquema 1 con factura real sintética: la copia temporal se migra al esquema actual;
  el archivo de origen permanece idéntico y la factura/huella continúan intactas.
- Paquete cifrado y segunda carpeta: los bytes finales coinciden; no quedan archivos
  parciales. La falta de segunda carpeta produce advertencia y conserva la copia local.
- Caducidad y modificación posterior a la vista previa: no sustituyen los datos vivos.

## Integración pública

Funciones: `recover_pending_restore(root)` antes de `Database(root)` y
`assert_restore_allows_emission(db)` antes de emisión y operaciones fiscales que creen/envíen
registros. La consulta/reconciliación fiscal puede seguir disponible para resolver información.

API: `backup.recovery_status`, `backup.prepare_transfer`, `backup.activate_transfer` y
`backup.retention`, además de `backup.create/list/preview/restore/password`. La restauración
devuelve `recovery` y `certificate_reconfiguration`; el estado no debe tratarse como emisión
activada cuando `recovery.blocked` es verdadero.

Manual: `docs/COPIAS-TRASLADO.md`.

## Límites que siguen siendo externos a estas pruebas

No se ha ejecutado Windows/NTFS/USB, DPAPI real ni cierre de Tauri durante una copia; las
pruebas de subproceso son del backend Linux. No hay aceptación AEAT ni datos reales.
La ausencia del historial posterior a un backup no se resuelve generando números o huellas
inventados: permanece bloqueada hasta recuperar y conciliar información suficiente.

La protección de traslado presupone el uso autorizado de un solo equipo. Un sistema local
sin conexión entre PCs no puede observar una copia manual del directorio ni impedir que
alguien active deliberadamente el mismo paquete en dos destinos desconectados. La UI exige
declarar que solo se activa el destino y mantiene retirado el origen del traslado preparado.

La implementación inicial tenía un límite de 200 MB/20.000 entradas. La ampliación
posterior lo sustituyó por streaming de archivos con límite de 8 GiB/50.000 entradas;
ver `copias-streaming-2026-09-23.md`. No se ha afirmado que una prueba sintética mida
el volumen ni el parser de un Access real aún no recibido.

## Ampliación posterior: XML fiscal e importaciones

La inspección fiscal de una copia valida ahora también el XSD oficial y la equivalencia del XML con su payload inmutable mediante `validate_stored_record`. Una regresión altera solo el concepto XML y recalcula las huellas del ZIP; la vista previa lo rechaza.

El importador Access añadido durante la misma sesión conserva archivos fuera de SQLite. `imports/` se añadió al conjunto transaccional de restauración. Se preservan los originales y los auxiliares, se comprueba `import_batches.source_digest` y se rechazan rutas, enlaces y originales ausentes o alterados. Pruebas con importación CSV sintética real verifican restauración y fallo tras instalar la carpeta. Los diarios de recuperación previos sin `imports` siguen admitidos.

La batería conjunta de agenda/avisos/workflows/restauración, ejecutada tras estos cambios, dio **88 passed**: `reports/agenda-backend-2026-09-23.txt` y su XML contienen el comando efectivo y el resultado. La prueba sigue siendo Linux/SQLite temporal, no Windows físico.
