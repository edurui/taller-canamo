# Automecánica Talleres El Cáñamo

Aplicación local de escritorio para un taller: **buscar cliente o matrícula → factura → imprimir**.
React + TypeScript + Tauri 2 + servicio Python + SQLite. Sin nube ni suscripción obligatoria.

**Versión 0.9.1 de desarrollo. Emisión de prueba; no apta todavía para facturación operativa.**
La especificación principal es [PROMPT_MAESTRO_TALLER_CANAMO.md](PROMPT_MAESTRO_TALLER_CANAMO.md).
El [estado verificado](docs/ESTADO-VERIFICADO.md) y [registro de trabajo](docs/PROGRESO.md)
distinguen resultados ejecutados, desarrollo y dependencias externas.

## Preparación local

Python 3.13 y Node 22.22.2 en el entorno comprobado. Desde esta carpeta:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
npm ci
python scripts/prepare_assistant_models.py
python scripts/prepare_access_runtime.py
npm run typecheck
npm run build
python -m pytest
```

La preparación de Access requiere un JDK 17 o posterior para construir el lector; el paquete final incluye su JRE. Los modelos pequeños de voz/OCR se descargan una vez, con hashes fijados, durante la preparación. La facturación no descarga modelos.

Previsualización para desarrollo con datos separados de cualquier taller real:

```bash
python scripts/run_preview.py --data /tmp/canamo-demo
```

La distribución al taller es Tauri con servicio empaquetado y datos persistentes del usuario.
No abrir index.html directamente: la interfaz necesita el servicio y token de sesión.

## Verificación reproducible

```bash
npx playwright install chromium --no-shell
python scripts/verify.py --report reports/local-verification
```

Ejecuta dependencias, pytest, TypeScript, Vite y E2E con SQLite temporal real.
Guarda comandos, salidas y hashes; no envía a AEAT ni sustituye pruebas Windows.
Se ha ejecutado una ventana Tauri real Linux y el sidecar PyInstaller; consultar evidencias
y límites en los informes de `reports/` y en el estado verificado.
Git conserva los informes redactados (`reports/*.md`) y sus scripts de reproducción
(`reports/*.py`). Los resultados automáticos, capturas, trazas y logs quedan en disco,
fuera del repositorio; las rutas a esos artefactos requieren la ejecución local correspondiente.

`python scripts/package_source.py` genera un ZIP de fuentes con hashes individuales en
`build/entrega/`, sin datos privados, bases, dependencias instaladas ni artefactos. Los
motores y dependencias se reconstruyen con los locks y scripts incluidos.

## Windows

[Construcción para Windows](docs/BUILD-WINDOWS.md).
PREPARAR-WINDOWS.cmd instala desde locks y comprueba el entorno de desarrollo.
scripts/build_desktop.py prepara servicio y artefactos Tauri.
ABRIR-PREVISUALIZACION.cmd sirve para desarrollo. El cliente final no deberá instalar
Node, Python ni Rust. No se ha ejecutado Windows ni generado su instalador en este entorno Linux.

## Documentación y datos

[Manual de uso en castellano](LEEME.md): trabajo diario, impresión, agenda, asistencia,
copias/restauración y traslado. [Asistencia local](docs/ASISTENCIA.md) y
[exportación portable](docs/INFORMES-EXPORTACION.md) detallan las herramientas opcionales.

[Criterios de aceptación](docs/ACEPTACION.md), [contexto](docs/CONTEXTO-PRODUCTO.md),
[fuentes fiscales](docs/FISCAL-FUENTES-2026-09-23.md).
El acceso autenticado AEAT requiere certificado legítimo y verificación posterior;
no se presenta una simulación como aceptación.

SQLite y recursos se guardan fuera del ejecutable, en una carpeta persistente del usuario.
No incluir bases, certificados, secretos o clientes en Git. private-reference/ contiene
referencias personales de lectura local exclusivamente. Conservar Access y sus originales
durante el desarrollo y validación de la migración.
