# Criterios de aceptación

Estos criterios no son una declaración de que ya se cumplan. Ver `ESTADO-VERIFICADO.md`.

## Calidad y publicación autorizada · 04/11/2026

- [x] Formato y lint reproducibles: Prettier, ESLint, Ruff, rustfmt y Clippy sin errores.
- [x] Batería tras formateo: 842 Python, 166 E2E/Axe, typechecks/build y dependencias,
  sin fallos, omitidas, reintentos ni cambios de fuentes durante la ejecución.
- [x] Configuración posterior del driver externo: exclusión sintética correcta,
  seis controles de calidad y 28 regresiones del proceso correctos.
- [x] Rama nueva y ejecución Windows autorizadas expresamente por el usuario.
- [ ] Nuevo instalador Windows construido, instalado y probado con WebView2.

Evidencia de esta fase: `../reports/CALIDAD-WINDOWS-2026-11-04.md`.

## Revisión actual · 04/11/2026

- [x] Contrastar cambios previos, logs originales y hash del EXE conservado.
- [x] Repetir batería base: 827 Python, 166 E2E, typechecks/build, sin fallos.
- [x] Corregir seis dependencias con avisos; auditorías npm/Python sin avisos
  de vulnerabilidad conocidos tras la actualización.
- [x] Corregir inventario de recursos y rechazo de pruebas incompletas: 25
  casos dirigidos correctos, con control negativo del CSS omitido.
- [x] Corregir PDF largo: 14 casos dirigidos y nueve páginas renderizadas revisadas.
- [x] Batería final integrada: 841 Python, 166 E2E/Axe, ambos typechecks, build
  y pip check; cero fallos/omitidas/reintentos, sin cambios de fuentes. 18 pruebas Rust.
- [x] Servicio empaquetado Linux con las dependencias nuevas: nueve comprobaciones
  funcionales correctas, 1.803 entradas y hash del binario contrastados.
- [ ] Nuevo NSIS y ventana del EXE instalado comprobados en Windows real.
- [ ] Ensayo del PC destino, copia/restauración, impresora y cierre/reinicio.
- [ ] Certificado, expediente fiscal, identidad/serie y corte acordado desde Access.

El instalador anterior no incorpora las correcciones. No usar los resultados
históricos siguientes para marcar completadas estas casillas. Evidencia actual:
`../reports/REVISION-ENTREGA-2026-11-04.md`.

## Comprobación de entrega del 27/10/2026

- [x] Instalador NSIS x64 construido e instalado en el runner Windows; diagnóstico
  del servicio instalado correcto, con hashes coincidentes.
- [x] 819 pytest y 166 E2E correctas en el build Windows; batería local repetida,
  typechecks y build correctos. Ocho pruebas adicionales de reutilización correctas.
- [x] Copia cifrada real restaurada en Linux; 22 tablas y 36 recursos contrastados.
  Comparación de tablas/integridad/FK y hashes de copia/MDB repetida al entregar.
- [x] Paquete privado local con EXE, datos cifrados, guía, muestra A4 y SHA-256;
  contraseña separada y originales conservados.
- [ ] Recorrido de ventana nativa Windows: la conexión WebDriver anterior agotó
  el timeout. Repetición preparada sobre el mismo EXE, sin reconstruirlo.
- [ ] Instalación/uso en PC Windows sin herramientas de desarrollo, restauración
  de datos reales en destino, actualización/reinicio, notificaciones e impresora física.
- [ ] Certificado y expediente fiscal autorizados, identidad/numeración y corte
  definitivo. La entrega de ensayo no habilita emisión operativa.

Evidencias y límites: `../reports/ENTREGA-WINDOWS-2026-10-27.md`.

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
