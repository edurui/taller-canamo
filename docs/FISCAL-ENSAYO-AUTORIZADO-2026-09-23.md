# Ensayo AEAT autorizado con el candidato exacto

**Pendiente de ejecución externa.** Este procedimiento es para el mantenedor, con acceso
legítimo al entorno oficial de pruebas, identidad confirmada y certificado autorizado.
No se ha ejecutado ninguna de estas llamadas de red durante el desarrollo de esta entrega.
Las 15 pruebas locales del guion no acreditan aceptación AEAT.

El ejecutable `scripts/verify_aeat_authorized.py` tiene tres operaciones:

- `init`: crea únicamente un marcador en una carpeta nueva. No crea SQLite ni usa la red.
- `check` (predeterminada): verifica configuración, selección, certificado declarado,
  binario/huellas y aislamiento en modo de solo lectura; no inicia el servicio.
- `run --authorized`: ejecuta los pasos revisados mediante el **servicio candidato Windows
  exacto**, por IPC, con su temporizador desactivado. No genera facturas, cambia el modo,
  crea subsanaciones/anulaciones ni aprueba un expediente de liberación.

## 1. Preparar una cuenta Windows de ensayo

Construir el candidato completo según [BUILD-WINDOWS.md](BUILD-WINDOWS.md), con
`--release-candidate`, e instalarlo en una cuenta Windows nueva destinada a pruebas.
Conservar sus bytes; reconstruirlos o firmarlos después invalida la huella ensayada.
No copiar una base operativa o documentos de Access a esta cuenta.

**Antes del primer arranque de Tauri**, inicializar su futura carpeta de datos. La aplicación
interactiva no tiene un parámetro `--data` arbitrario: utiliza la carpeta local del usuario
más el identificador `es.tallereselcanamo.desktop.dev`.

En PowerShell, dentro del proyecto y con el entorno de desarrollo preparado:

```powershell
$EnsayoCanamo = Join-Path $env:LOCALAPPDATA 'es.tallereselcanamo.desktop.dev'
.\.venv\Scripts\python.exe scripts\verify_aeat_authorized.py init --data $EnsayoCanamo --operational-data 'C:\RUTA-REAL-DEL-USUARIO-OPERATIVO\DatosCanamo'
```

Sustituir la ruta operativa por la confirmada del taller. El guion solo compara su ruta;
no abre esa carpeta. Si la futura carpeta de ensayo ya existe, `init` se niega a adoptarla:
utilizar otra cuenta nueva, sin borrar instalaciones existentes. El directorio de ensayo
queda fuera del proyecto y debe mantenerse privado.

Abrir el candidato en esa cuenta, configurar emisor/productor/declaración e instalar el
certificado mediante su selector local. Confirmar la representación legítima. Seleccionar
únicamente **AEAT pruebas**. No cargar demostración: produce registros `local_test`, que
este ensayo rechaza. Preparar en UI los documentos de prueba revisados y cerrar totalmente
la aplicación antes de ejecutar el guion; cerrar la ventana a bandeja no basta.

La UI en modo `aeat_test` procesa su cola periódicamente: iniciar esta etapa únicamente
cuando ya exista autorización para usar el entorno oficial de pruebas. Un envío que haya
terminado desde UI se conserva y el guion comprueba su acuse auténtico, sin reenviarlo.

## 2. Preparar el manifiesto de selección

Guardar el JSON en una carpeta privada fuera del repositorio. Sustituir los marcadores
siguientes por los datos de esa instalación; no son identidades ni acuses de ejemplo válidos:

```json
{
  "format_version": 1,
  "workspace_id": "ID-DEVUELTO-POR-INIT",
  "installation_id": "ID-VISIBLE-EN-CONFIGURACION-FISCAL",
  "issuer_nif": "NIF-LEGITIMO-DEL-EMISOR",
  "producer_nif": "NIF-REAL-DEL-PRODUCTOR",
  "system_id": "ID-DEL-SIF",
  "certificate_fingerprint": "SHA256-DEL-CERTIFICADO-EN-MAYUSCULAS",
  "sidecar_sha256": "sha256-del-exe-en-minusculas",
  "steps": [
    {
      "record_id": "ID-LOCAL-DEL-REGISTRO",
      "record_hash": "HUELLA-DEL-REGISTRO-EN-MAYUSCULAS",
      "operation": "send",
      "expected_status": "accepted"
    },
    {
      "record_id": "ID-LOCAL-DEL-REGISTRO",
      "record_hash": "HUELLA-DEL-REGISTRO-EN-MAYUSCULAS",
      "operation": "query",
      "expected_status": "accepted"
    }
  ]
}
```

La huella del registro aparece en Fiscalidad → Detalle. Su identificador local forma parte
del nombre `verifactu-<id>.xml` al guardar el XML conservado. El identificador de instalación
es visible en configuración. La huella del servicio se obtiene sin ejecutarlo:

```powershell
(Get-FileHash 'C:\RUTA-INSTALADA\canamo-service.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
```

Para consultar exclusivamente los metadatos públicos del certificado instalado y la
identidad de esta instalación, el mantenedor puede ejecutar este bloque de **solo lectura**
con Tauri cerrado. No abre el PKCS#12, extrae claves ni muestra contraseñas:

```powershell
@'
import json, sqlite3, sys
from pathlib import Path
p=Path(sys.argv[1]).resolve()/'taller.sqlite3'
with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as c:
    c.execute('PRAGMA query_only=ON')
    s=json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
f=s['fiscal']
print(json.dumps({'installation_id':f['installation_id'],
 'issuer_nif':s['company']['tax_id'],'producer_nif':f['producer_tax_id'],
 'system_id':f['system_id'],'certificate_fingerprint':(f.get('certificate_info') or {}).get('fingerprint')},indent=2))
'@ | .\.venv\Scripts\python.exe - $EnsayoCanamo
```

No modificar SQLite. El manifiesto admite como máximo 20 pasos y la instalación de ensayo,
500 registros. Todas las entradas pendientes deben pertenecer a la selección; el orden de
los envíos debe coincidir con la cola. `send` admite pendientes/reintentos y la reutilización
de un acuse terminal. Un resultado incierto exige primero `query`; nunca se reenvía a ciegas.
Los resultados esperados admitidos son `accepted`, `accepted_with_errors`, `rejected`,
`retry` y `reconciliation_conflict`, según el caso real que se esté ensayando.

## 3. Comprobar y ejecutar

Usar el servicio junto al candidato instalado, sin sufijo del target. Estas rutas son
marcadores y se deben sustituir por las de la cuenta de ensayo:

```powershell
.\.venv\Scripts\python.exe scripts\verify_aeat_authorized.py check --data $EnsayoCanamo --manifest 'D:\EnsayoPrivado\casos.json' --sidecar 'C:\RUTA-INSTALADA\canamo-service.exe'
.\.venv\Scripts\python.exe scripts\verify_aeat_authorized.py run --data $EnsayoCanamo --manifest 'D:\EnsayoPrivado\casos.json' --sidecar 'C:\RUTA-INSTALADA\canamo-service.exe' --authorized --max-wait-seconds 3600
```

`check` no inicia servicio ni red. `run` requiere Windows/DPAPI y candidato, niega producción
o expedientes ya instalados, comprueba huellas e identidades, y usa el transporte real de la
aplicación hacia el endpoint de pruebas. El bloqueo de restauración protege el conjunto
mientras se ejecutan los pasos. No abrir otra instancia durante el ensayo.

La espera predeterminada es cero: si AEAT exige esperar, termina sin acortarla. Se puede
permitir una espera explícita de hasta una hora. Ante interrupción, inspeccionar la cola y
las evidencias antes de repetir; el guion no fabrica un resultado aceptado.

## 4. Casos y evidencia que deben quedar completados

Trabajar por etapas porque una corrección depende del resultado anterior:

1. Alta revisada → envío → consulta que corresponde al registro.
2. Subsanación justificada desde UI → selección de su nuevo ID/huella → envío/consulta.
3. Anulación desde UI sobre el documento de ensayo correspondiente → envío/consulta.
4. Rechazo/corrección y recuperación de resultado incierto según el guion acordado de
   aceptación; observar los resultados reales, sin inventar un rechazo para completar una casilla.

Cada ejecución deja `authorized-aeat-evidence/<id>/result.json` dentro de los datos privados
de ensayo, junto con manifiesto, XML conservado, respuestas, consultas, estados y SHA-256.
El resultado solo verifica un paso si encuentra procedencia mTLS real, certificado/endpoint
correctos y respuesta validada/correspondiente. Las respuestas inyectadas por tests no cumplen
esa condición. Una consulta que necesite revisar páginas adicionales queda conservada sin
atribuir una aceptación al guion reducido.

La salida JSON y código `0` indican que pasaron los pasos seleccionados; **no autorizan por sí
solos producción**. `production_activated` y `release_approved` permanecen en `false`.
Reunir estas pruebas y los ensayos Windows/impresora para la revisión y el expediente de
[FISCAL-LIBERACION-2026-09-23.md](FISCAL-LIBERACION-2026-09-23.md). Mantener intacta la base que
contiene los intercambios: el verificador del expediente los comprueba de nuevo.

No incorporar datos identificativos, certificados, contraseñas, XML o evidencias privadas
al ZIP de fuentes, repositorio, informe público o chat.
