# Revisión para publicar cambios acumulados · 27/10/2026

Destino autorizado por el usuario: rama existente `main`, remoto `origin` del
repositorio actual. Se agrupan los cambios locales del 7 y 8 de octubre: listados,
navegación, agenda/avisos, direcciones, revisión de históricos, importes e inicio npm.

Entorno: Ubuntu/Linux, Python 3.13.2, Node 22.22.2, npm 10.9.7, Rust 1.98.1.

| Comando | Resultado de esta revisión |
| --- | --- |
| `.venv/bin/python -m pip check` | Correcto |
| `.venv/bin/python -m pytest` | 809 correctas; ejecución con permiso para puertos locales |
| `npm run typecheck` | Correcto |
| `npm run typecheck:e2e` | Correcto |
| `npm run build` | Primera ejecución correcta; segunda interrumpida a petición del usuario |
| `cargo +1.98.1 test --offline --locked --manifest-path src-tauri/Cargo.toml --no-default-features --features native-notifications --lib` | 23 correctas; PATH incluye `$HOME/.cargo/bin` |
| `npm ls --depth=0` | Correcto, versiones fijadas instaladas |
| `git diff --check` | Correcto antes de actualizar estos documentos |

Los comandos Python/TypeScript/build se lanzaron mediante `scripts/verify.py`.
La primera ejecución, en `reports/precommit-2026-10-27/`, tuvo 804 pytest correctas
y cinco errores HTTP porque el sandbox impide crear sockets; pasó typechecks/build
y se detuvo antes de completar E2E. La repetición con permiso, en
`reports/precommit-2026-10-27-unrestricted/`, pasó las 809 pytest y ambos typechecks.
Se interrumpió durante el segundo build cuando el usuario pidió evitar más
comprobaciones. No hay resultado integrado final ni E2E completa nueva; las
164 E2E documentadas del 08/10 son evidencia de aquella revisión.

Lectura SQLite inmutable de la copia habitual de previsualización: 1.595 clientes,
1.290 vehículos, 5.133 facturas históricas, esquema v8, integridad correcta y cero
errores FK. Se preparó una copia temporal privada idéntica para ensayar el arranque,
pero no se arrancó al detener las comprobaciones adicionales. La copia habitual
y el Access original no se modificaron. El primer `npm run start` aplicará v9 con
copia previa; no requiere reimportación.

Revisados 96 archivos pendientes: sin bases/certificados/claves privadas ni
coincidencias de nombres, NIF, teléfonos o correos de los clientes reales en las
adiciones. Los datos están fuera de Git. No se ejecutó Windows/WebView2, impresión
física ni aceptación fiscal; se conserva la edición de pruebas.
