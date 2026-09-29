# Asistencia, titularidad, rectificación y copias en interfaz

Entorno: Ubuntu Linux x64, Node22.22.2, npm10.9.7, Python3.13.2 en `.venv`, Chromium
de Playwright1.63.0. Bases SQLite temporales individuales; solo datos sintéticos.

## Ejecuciones dirigidas

| Comandos | Resultado | Evidencia |
|---|---|---|
| `npm run typecheck`, `npm run typecheck:e2e`, `npm run build` | Código0; TypeScript real y Vite | Salida de herramientas de la sesión; se repetirán con logs en la batería final |
| `npx playwright test e2e/ownership-rectification.spec.ts --reporter=line --output=reports/e2e-ownership-recheck` | 3 correctas,3,1s | Propietario/teléfono/PDF idéntico tras reinicio; R3base0/cuota/fechaoriginal; histórico incompleto y R4manual |
| `npx playwright test e2e/assistance.spec.ts e2e/recovery-fiscal.spec.ts --reporter=line --output=reports/e2e-assistance-streaming` | 5 correctas,9,6s | OCR/Vosk reales mediante jobs y flujo de revisión; audio sintético navegador; traslado y subsanación local |
| `npx playwright test e2e/backup-streaming.spec.ts e2e/assistance.spec.ts --reporter=line --output=reports/e2e-backup-streaming/recheck` | 5 correctas,10,8s | AES6MiB aleatorios, capability/fragmentos, contraseña incorrecta sin cambios, reintento sin recargar, restore y originales exactos, carga pendiente tras reinicio |
| `npx playwright test e2e/operations.spec.ts e2e/ownership-rectification.spec.ts e2e/recovery-fiscal.spec.ts --reporter=line --output=reports/e2e-integration-review` | 7 correctas,15,5s | Catálogo/proveedores, conversiones/stock/cobros/informes/CSV/portable, titularidad/rectificación y diagnóstico fiscal después de las integraciones |

Estos son hitos dirigidos; las fuentes han seguido cambiando. No sustituyen la batería
final conjunta ni acreditan el mismo ejecutable empaquetado hasta reconstruirlo.

## Fallos encontrados y conservados

- La primera E2E de rectificativa esperaba `RECT-`, pero la serie configurada es `REC-`.
  La emisión se había completado correctamente. Se corrigió el prefijo exacto esperado
  y se volvió a ejecutar. Informe/screenshot/trace en `reports/e2e-ownership/`.
- La primera E2E de copia no encontraba el nombre accesible exacto de la contraseña:
  el `label` incluía la explicación. Se corrigió el componente compartido `Field` para
  usar `aria-labelledby` para el título y `aria-describedby` para la ayuda. No se ocultaron
  las ayudas ni se rebajaron las comprobaciones. Error original conservado en
  `reports/e2e-backup-streaming/artifacts/`.
- La auditoría de dominio detectó anulación de original con rectificativas activas e
  identidades de conversión incoherentes. Backend las bloquea y la interfaz explica el
  motivo, conserva cliente/vehículo y deshabilita anulación cuando corresponde.
- La asistencia síncrona podía bloquear la búsqueda durante el motor/proveedor. Los
  trabajos asíncronos conservan solo propuestas en memoria y admiten cancelación.

## Revisión visual y límites

Se han abierto e inspeccionado las capturas `reports/e2e-backup-streaming/restauracion.png`
y `reports/desktop-pdf/native-window.png`: controles y mensajes legibles, aviso de prueba
visible y error de impresión explícito. La captura completa de una página desplazada
sitúa la barra fija en la posición del viewport; no es una prueba de escala física.

El PDF de la captura Tauri corresponde al sidecar anterior y debe repetirse con el paquete
final. La prueba de impresión usa receptores locales que registran argumentos y fallo
controlado; no acredita papel impreso. El micrófono de Playwright es sintético. No se
ha enviado un mensaje, una factura de producción ni una solicitud AEAT autenticada.
