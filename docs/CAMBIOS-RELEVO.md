# Relevo técnico · actualizado el 29/09/2026

La especificación principal es `PROMPT_MAESTRO_TALLER_CANAMO.md`. La revisión local ha terminado. Leer primero `ESTADO-VERIFICADO.md` y `PROGRESO.md`, que sustituyen las afirmaciones
históricas de este archivo sobre herramientas que antes no estaban disponibles.

## Ajustes posteriores de Configuración y campos

`web/style.css` alinea arriba las celdas de `.form-grid` para que las ayudas no muevan
controles vecinos; `.align-end` mantiene las acciones inferiores. El menú de Configuración
es sticky sólo cuando es lateral, con alto máximo de ventana y foco interior. `selectTab`
en `frontend/settings.tsx` lleva al inicio de la sección al navegar desde abajo. El aviso
de Asistencia deja 1rem sobre el botón anterior. Logo provisional con `role="img"`.

`chooseOption` en `e2e/fixtures.ts` busca la lista activa de `aria-controls`, evitando
coincidir con opciones retenidas durante la salida de otro popup. Evidencia más reciente:
`reports/AJUSTES-ALINEACION-2026-09-29.md` (38 E2E, ocho posteriores de interfaz/accesibilidad,
typechecks/build y siete checks Tauri Linux). Backend y locks sin cambios.

## Interfaz del 29/09/2026

- `frontend/overlays.tsx` centraliza Modal/Popup/Presence y la pila de inert/foco. `Presence`
  retiene el contenido 140 ms para salir, cambia generación al reabrir y libera recursos
  con `useClosing`; el fondo saliente absorbe el segundo clic. No retirar esos controles.
- `frontend/controls.tsx` centraliza texto/número/textarea/select/autocomplete/fecha. El
  select mantiene validación nativa y lista propia con teclado; el calendario emite valores
  ISO y conserva min/max. En móvil, los paneles se convierten en diálogos de pantalla completa.
- `CustomerSearch` conserva resultados durante la consulta; `resolvedQuery` impide elegir
  una opción obsoleta. No vaciar la lista en cada pulsación ni retirar el serial de peticiones.
- Las líneas de borrador tienen `_uiKey` estable sólo en memoria. Se elimina de cálculo y
  guardado RPC. Reordenar actualiza también `totals.lines` y el estado de cambios pendientes;
  el PDF se genera después de guardar. No modificar snapshots emitidos.
- Los tamaños existentes 16/18/20 px se destacan en Configuración, con prueba inmediata y
  restauración del guardado al abandonar. No hay nueva migración ni preferencia duplicada.
- CSS corrige espaciado, filas y botones; controles de archivo/casilla/rango siguen nativos.
  `e2e/fixtures.ts::chooseOption` recorre la lista visible, sin forzar valores del select oculto.
- Verificación: 438 pytest antes de cambios exclusivamente frontend; 38 E2E finales,
  ambos typechecks/build/dependencias y Tauri Linux correctos. Smoke nativo con siete checks.
  El harness espera a que el servicio finalice antes de borrar los datos de su sesión.
  Con `--xvfb` desactiva aceleración WebKit: sin DRI3 el lienzo PDF se dibujaba mal, aunque
  el archivo original era correcto. Se verificó el lienzo completo por software y Poppler.
- Informe actual: `reports/MEJORAS-INTERFAZ-2026-09-29.md`. El ZIP del 23/09 se conserva como
  histórico; no contiene estos cambios. Windows/WebView2 e impresión física pendientes.

## Arquitectura

- React18/TypeScript strict y Vite; IPC Tauri en escritorio y adaptador HTTP con token solo
  para desarrollo/E2E. El usuario final recibe ejecutable con sidecar, no un servidor web.
- Tauri2/Rust: instancia única, servicio JSONL supervisado, timeout y cierre/bandeja;
  datos persistentes en ruta del usuario. No cambiar a la carpeta del ejecutable.
- Python/SQLite con migraciones, transacciones, versiones, snapshots y auditoría.
- Motores opcionales locales Vosk/RapidOCR, Saxon para EN16931 y Jackcess/JRE para Access.
  Se preparan con scripts y dependencias fijadas; no dependen de Office instalado.

## Puntos que requieren conservar su semántica

- `App.dispatch` mantiene el bloqueo compartido; un diario de restauración pendiente impide
  operar hasta recuperar. No quitar ese control para ocultar un fallo de copia.
- PDFs emitidos conservados son inmutables. No regenerar con emisor/cliente/logo actuales.
- Saldo histórico desconocido no es deuda cero ni impago: existe estado desconocido y
  evidencia inicial independiente, con ajustes append-only.
- Subsanación fiscal enlaza registros; una respuesta incierta exige Consulta. Los transportes
  de prueba no generan evidencias autenticadas. Revisar el procedimiento de liberación.
- Los originales Access y staging forman parte de copias/restauración; rollback no elimina
  trabajo posterior del taller. No usar un hash de archivo como única identidad de origen.
- Los modales usan pila compartida de `inert`/foco/overflow para cerrar varios a la vez.
  La E2E agenda conserva la regresión que dejaba toda la pantalla bloqueada.
- B2B conserva originales, validación y eventos propios. VERI*FACTU no acredita entrega B2B.
- Asistencia `assistant.start/job_status/cancel`: motor en hilo auxiliar, solo propuestas
  en memoria. Mantener la búsqueda/emisión independiente y descartar resultados cancelados.
- Archivos grandes: copias y portable usan capabilities, bloques con hashes y destino
  temporal. Revocar una copia conserva el `.canamo`; revocar una exportación borra su temporal.
  Cargas de restauración persistentes se listan y pueden descartarse después de reiniciar.
- No se permite anular una original con rectificativas activas. Las identidades de una
  conversión (origen/cliente/vehículo) se conservan; usar Convertir evita duplicados.
- R2/R3 corrigen cuota con base cero y ajustes explícitos; la fecha de operación se conserva.
  Un tipo histórico no permitido por validaciones AEAT se conserva, sin cambiarlo a 21 %.

## Verificación al retomar

Usar `.venv/bin/python` en este Linux (o activar `.venv`). Preparar modelos/lector siguiendo
README antes de probar desde una copia limpia. Coordinar builds: no reemplazar `dist/`
mientras otro proceso ejecuta E2E. `scripts/verify.py` comprueba si cambiaron fuentes durante
la batería y no concede una revisión única cuando eso sucede.

Los informes previos son evidencia fechada, no una autorización de producción. La batería
del 23/09 pasó con 438 backend y 32 E2E; la revisión del 29/09 añade seis E2E y vuelve a
comprobar las 38, ambos typechecks, build y Tauri Linux. El selector GTK real del 23/09 no
se ha repetido en esta revisión; las siete comprobaciones actuales están en su informe.
Windows/certificado/impresora/Access real siguen siendo comprobaciones externas concretas
con los procedimientos correspondientes en docs/ y CONTINUAR.md. El guion de ensayo AEAT
no se ha ejecutado contra la red; sus 15 pruebas locales no acreditan aceptación externa.
