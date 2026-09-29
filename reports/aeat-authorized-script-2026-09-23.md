# Guion de ensayo AEAT autorizado · comprobación local

Implementación: `scripts/verify_aeat_authorized.py`. No se modificó backend ni frontend.
Pruebas: `tests/test_aeat_authorized_script.py`. Guía completa y orden de ejecución:
`docs/FISCAL-ENSAYO-AUTORIZADO-2026-09-23.md`.

Comando ejecutado:

```text
.venv/bin/python -m pytest -q tests/test_aeat_authorized_script.py --junitxml=reports/pytest-aeat-authorized-script-2026-09-23.xml
```

Resultado: **15 correctas, 1,05 s**. Linux x86_64, Python 3.13.2. Datos sintéticos y SQLite
temporales. La CLI predeterminada se ejecutó también en un subproceso real, comprobando que
no muta SQLite, inicia el servicio ni abre la red. El ensayo autorizado real no se ejecutó.

Guardas comprobadas: carpeta nueva y distinta de la operativa; rechazo dentro del proyecto;
modo producción, expediente instalado, certificado/configuración incompletos, hash de binario
o registro distinto, otros entornos y pendientes fuera de selección; orden de cola, espera
persistente y obligación de consulta ante resultado incierto. No hay credenciales por argv.

La prueba de flujo reemplaza explícitamente el servicio Windows por un sustituto local y
utiliza el motor fiscal real con respuestas inyectadas. Conserva XML, consultas y hashes,
pero **falla la comprobación autenticada** porque no se fabrican entradas de procedencia mTLS.
No hay aceptación AEAT atribuida a los tests ni expediente positivo generado. Ninguna acción
del guion crea facturas o cambia el modo fiscal.

El guion real utiliza el sidecar candidato por su hash, con `--no-background`, y el mismo
transporte oficial de la aplicación. `init` solo crea un marcador antes de abrir Tauri en una
cuenta Windows aislada. La UI no admite `--data` arbitrario: se documenta explícitamente su
carpeta `%LOCALAPPDATA%\es.tallereselcanamo.desktop.dev`. La ruta operativa se compara sin abrirla.

Límites: máximo 500 registros de ensayo y 20 pasos por manifiesto; espera explícita hasta
una hora; consultas sin correspondencia exacta de un registro quedan conservadas y requieren
revisión. El guion no crea automáticamente documentos comerciales, subsanaciones ni
anulaciones. Se preparan por etapas en la UI porque dependen del resultado anterior y de la
revisión del operador. Certificado legítimo, Windows y ensayo externo siguen pendientes.
