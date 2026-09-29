# Evidencia fiscal local — 23/09/2026

Entorno observado: Linux 6.8.0-139-generic x86_64, glibc 2.39; Python 3.13.2 de `.venv`;
lxml 6.1.1. Datos en directorios temporales. Sin certificado real, sin datos personales,
sin llamadas autenticadas ni peticiones a producción.

## Ejecuciones

| Comando / acción | Resultado observado |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_transport_fiscal.py tests/test_workflows.py` | 45 passed, 1,60 s, salida 0 tras integrar validación en la emisión. |
| `.venv/bin/python -m pytest -q tests/test_fiscal_official.py tests/test_transport_fiscal.py` (primera ejecución) | 4 failed, 46 passed. El XSD demostró la omisión de NIF en referencia de rectificativas R1/R2/R3/R4. |
| Mismo comando, tras corregir el serializador | 50 passed, 0,58 s, salida 0. No se modificó el XSD ni se rebajó la aserción. |
| `.venv/bin/python -m pytest -q` | 147 passed, 3,20 s, salida 0. Batería completa presente en ese momento, incluidos cambios de integridad concurrentes. |
| `App(Path(temp)/'synthetic-data').fiscal.download_specs()` con almacén sin certificado | Descargados los 7 originales públicos; `verified=true`; salida 0. SHA-256 coincide con cada entrada del manifiesto. |
| `official_schema(name)` para cada XSD fijado | Los 6 XSD se compilan con resolución exclusivamente local; salida 0. |

Las cifras identifican estas ejecuciones, no un objetivo de cobertura. Cambios posteriores
requieren la batería integrada correspondiente.

## Reproducir la comprobación offline

Desde la raíz, con dependencias instaladas:

```sh
.venv/bin/python -m pytest -q tests/test_fiscal_official.py tests/test_transport_fiscal.py
```

La suite verifica vectores oficiales independientes, namespaces/formatos, referencias,
subsanación/anulación, respuestas válidas y malformadas, protección de esquemas, QR,
integración con publicación local, espera persistida, orden de cola y reintento del mismo XML.
Los transports inyectados jamás abren un certificado ni una conexión con AEAT.

Para repetir únicamente la descarga pública y su comprobación, sin importar claves:

```sh
PYTHONPATH=backend .venv/bin/python - <<'PY'
import tempfile
from pathlib import Path
from taller.app import App
from taller.fiscal import verify_schema_files
with tempfile.TemporaryDirectory(prefix='canamo-aeat-public-') as directory:
    app = App(Path(directory) / 'data')
    assert not app.certificates.path.exists()
    print(app.fiscal.download_specs())
    verify_schema_files(app.fiscal.spec_dir)
PY
```

Esta segunda comprobación sí requiere Internet y solicita exclusivamente XSD/WSDL públicos
de AEAT y el XSD W3C. No emite facturas ni ejecuta el servicio de suministro.

## Límites

No se ha probado autenticación, presentación real, validez censal, custodia DPAPI en Windows,
impresora ni activación para producción. La validez XSD no prueba todas las reglas de
negocio. La cola usa transporte simulado en sus tests y una respuesta sintética nunca
se presenta como aceptación oficial.

Fuentes, hashes, alcance exacto, defectos resueltos y desarrollo pendiente están en
`docs/FISCAL-FUENTES-2026-09-23.md` y
`backend/taller/schemas/aeat_1_0/manifest.json`. El objetivo general permanece abierto.

## Segundo hito: circuito y migraciones

Comprobado después del hito anterior. No se atribuyen estos resultados a modificaciones
posteriores de los otros módulos que continúan en desarrollo.

| Comando | Resultado observado |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_fiscal_workflow.py tests/test_fiscal_official.py tests/test_transport_fiscal.py -q` | 81 correctos, 2,16 s, antes de añadir el último caso de consulta del histórico aceptado. |
| `.venv/bin/python -m pytest tests/test_fiscal_workflow.py -q` | 32 correctos, 1,61 s; incluye dicho caso. |
| `.venv/bin/python -m pytest -q --junitxml=reports/pytest-fiscal-workflow-2026-09-23.xml` | 221 correctos, 7,86 s, antes del verificador de liberación y últimos cambios coordinados. |
| `.venv/bin/python -m pytest -q --junitxml=reports/pytest-fiscal-release-2026-09-23.xml` | 228 correctos, 8,54 s. |
| `.venv/bin/python -m pytest -q --junitxml=reports/pytest-fiscal-release-final-2026-09-23.xml` | 229 correctos, 9,19 s, salida 0. Una ejecución previa detectó que el mensaje de validación de cadena había cambiado al integrar backups; se precisó «cadena fiscal» y se mantuvo la aserción. |

Escenarios verificados con SQLite real y datos sintéticos:

- subsanaciones sucesivas, claves idempotentes concurrentes y conservación de snapshots;
- indicadores X/S/N tras rechazo o aceptación, anulación y corrección de anulación rechazada;
- rechazo atómico de E2/E3/E5, sin consumir número ni emitir XML incompatible;
- timeout → resultado incierto → consulta oficial por identidad exacta;
- consulta inexistente o de versión anterior conocida → reenvío de los mismos bytes;
- conflicto de huella, descripción o importe → aceptación denegada y cola bloqueada;
- consulta de histórico aceptado frente a versión posterior conocida → acuse histórico conservado;
- anulación confirmada por consulta con estado Anulado, sin inventar CSV;
- respuesta de proxy o fecha sin huso → evidencia conservada, resultado sin confirmar;
- espera global de 9.999 segundos, reinicio, nuevas facturas y reserva entre objetos del servicio;
- verificación de XML/payload/huella antes de envío y al restaurar, no solo hash en JSON;
- migración v1→v5 con registros existentes, claves foráneas y copia previa; fallo de DDL
  en v2/v3 revierte versión, datos y tablas; históricos repetidos y cobros documentados;
- cambiar el flag de liberación no sustituye el expediente; una aceptación sintética no
  crea evidencia mTLS; un artefacto modificado invalida el expediente.

La migración 5 incorpora el esquema pedido para agenda/excepciones/avisos. Este informe
no afirma que la ampliación funcional de agenda, desarrollada en paralelo, esté completa.
Los esquemas importados permanecen idénticos a su manifiesto. El adaptador conserva el
destino real de producción y exige todos los controles; no se ha habilitado ni contactado.

El verificador de expediente y el guion de ensayo con certificado están documentados en
`docs/FISCAL-LIBERACION-2026-09-23.md`. Su resultado actual es bloqueo por falta de evidencia,
coherente con la ausencia de ensayos externos. Resta el circuito B2B separado y el resto
de la especificación maestra; este hito no cierra el objetivo general.
