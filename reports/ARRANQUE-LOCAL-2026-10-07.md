# Arranque local con npm · 07/10/2026

Punto de partida: `main` en `6be3445`, árbol limpio. Se conserva la optimización de Clientes.

`package.json` incorpora `npm run start`: compila con `npm run build` (incluye typecheck)
y arranca `scripts/run_preview.py` mediante `.venv/bin/python`, sin activar el entorno
manualmente. Usa la carpeta persistente `${XDG_DATA_HOME:-$HOME/.local/share}/taller-canamo-preview/data`;
el navegador abre `http://127.0.0.1:8765`. `Ctrl+C` detiene el servicio.

Se encontró vacía la antigua carpeta temporal. Se preparó una copia privada persistente
del ensayo original completo, con 1.595 clientes, 1.290 vehículos y 5.133 históricos.
La copia queda fuera del repositorio, con permisos privados, y se reutiliza entre
arranques. El comando no importa, recrea ni sobrescribe la base existente. Esta preparación
es local y no viaja con un clon nuevo. No se han modificado los datos del origen.

Verificación ejecutada: `npm run start -- --no-open --port 0`; typecheck y Vite correctos,
HTTP 200 para la interfaz y RPC autenticado correcto. Páginas 0 y 10: total 1.595,
50 filas cada una y sin IDs compartidos. Cierre mediante Ctrl+C; conteos e integridad/FK
correctos tras cerrar. Los 26 archivos del origen conservan sus hashes anteriores.

No cambian backend, frontend, esquema ni dependencias. No se añadieron tests unitarios ni
se repitieron pytest/E2E completos para este cambio de comando y documentación. Se
actualizaron README, CONTINUAR y ESTADO-VERIFICADO. Sin staging, commit ni push.
