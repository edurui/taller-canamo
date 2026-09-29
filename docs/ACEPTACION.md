# Criterios de aceptación

Estos criterios no son una declaración de que ya se cumplan. Ver `ESTADO-VERIFICADO.md`.

## Repositorio y construcción
- Una carpeta recién extraída permite instalar dependencias documentadas sin archivos manuales.
- Locks reales para frontend/Rust y resolución Python reproducible, sin vulnerabilidades críticas no explicadas.
- Typecheck, build, tests backend/E2E y compilación Tauri con comandos y códigos de salida guardados.
- Instalador NSIS probado en Windows limpio sin Node, Python, Rust ni VS Code preinstalados.
- Abrir/cerrar/reabrir, reiniciar PC y actualizar no pierden datos ni procesos huérfanos.

## Flujo diario
- Buscar por un carácter/matrícula/teléfono, elegir con teclado y ver teléfono correcto.
- Cliente con varios vehículos; transferencia conserva historiales anteriores.
- Crear factura SIN orden, stock o presupuesto; maquinaria SIN matrícula.
- Doble clic, repetición RPC o interrupción no crean doble factura/cobro/movimiento.
- PDF A4 legible en impresora real, logo cambiable y marca de agua discreta.
- Editar ficha no altera datos ni PDFs de facturas emitidas, tampoco sus listados/búsquedas.

## Opcionales y UX
- Ocultar Más herramientas no bloquea el trabajo ni elimina datos.
- Presupuesto -> orden -> factura conserva líneas y no duplica stock.
- Mes/semana/día, selección de fecha, solapamientos, todos los días y cambio horario probados.
- Alertas leídas/pospuestas/repetidas persistentes con ventana visible/oculta y reinicio.
- Claro/oscuro, texto grande, foco, teclado, contraste y ventanas de 1366x768/1024x768 revisados.
- Modales con entrada/salida breve y movimiento reducido; cierre/reapertura, foco anidado
  y micrófono liberado sin esperar a la animación.
- Buscadores mantienen sus opciones al escribir y descartan selecciones/respuestas antiguas.
- Controles compartidos, calendario con mes/año/día y selectores a pantalla completa en móvil.
- Texto Normal/Grande/Muy grande persistente; filas, botones y paneles legibles hasta 320 px.
- Textos de ayuda no desalinean campos vecinos; el menú lateral de Configuración permanece
  accesible al bajar y en ventanas bajas, sin cubrir los formularios en móvil.
- Reordenar líneas conserva importes, cantidades y orden al guardar/reabrir y generar PDF.
- IA desactivada no rompe ninguna acción esencial; cualquier resultado exige revisión.

## Datos y seguridad
- Migración con vista previa, informe de problemas y conciliación de registros/importes.
- Históricas nunca se envían como nuevas; se conserva procedencia y número antiguo.
- Copia online consistente y cifrado; segunda ubicación falla con aviso sin falsa confirmación.
- Restauración completa, rollback con fallo inyectado, ZIP malicioso rechazado, claves fuera de copias/Git.
- Sin listener abierto a la LAN, sin rutas arbitrarias de archivos, ni SQL/HTML/CSV injection.
- Calendario y saldos no muestran una deuda/cobro falso sobre rectificativas/históricas.

## Fiscal
- Revisión con fuentes oficiales actuales, esquemas guardados con hashes y vectores independientes.
- Pruebas locales distinguidas de pruebas autenticadas con AEAT.
- Altas, anulaciones, rectificativas, subsanaciones, duplicados, errores/transporte/reintentos cubiertos.
- Certificado protegido, metadatos correctos y reconfiguración segura al trasladar PC.
- No datos ficticios a producción. No promesa de homologación por parte de AEAT.
- Productor identificado y declaración responsable basada en versión/funciones verificadas.
- Factura electrónica B2B declarada como adaptador separado, con estado propio, no inferida de VERI*FACTU.
