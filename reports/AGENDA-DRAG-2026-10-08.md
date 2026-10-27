# Agenda: guardar al soltar el arrastre · 08/10/2026

## Causa y comportamiento final

El código ya distinguía el gesto de arrastre y suprimía el clic posterior. El problema
era que `TimeEvent.finish` llamaba a `onEvent` con fechas propuestas: esa misma función
abría el editor. Por eso mover o alargar exigía después confirmar un formulario.
La corrección visual anterior no había cambiado ese comportamiento.

Ahora las rutas están separadas: un clic abre el editor; soltar un arrastre válido
ejecuta una sola llamada a `agenda.save`, muestra inmediatamente la posición propuesta
y refresca la lista con las versiones autoritativas. Se mantiene el tamaño/estilo del
agarre corregido anteriormente.

- Movimiento mínimo para reconocer gesto, identificación del puntero y pasos de 15 minutos.
  Un temblor pequeño conserva el clic; un arrastre que vuelve al origen no guarda ni abre
  el editor. Escape, cancelación del puntero y pérdida de captura restauran la posición.
- Un segundo cambio queda bloqueado durante el guardado y la recarga. El clic generado
  al soltar no abre la ficha. Enter sigue abriendo la edición manual.
- Si falla el guardado, se restaura la cita y aparece el error. Si se salió de Agenda,
  el fallo se comunica mediante un aviso global de error accesible.
- Si falla la recarga posterior, las filas obsoletas no se pueden editar: «Reintentar
  carga» recupera las versiones antes del siguiente cambio.
- Las citas recurrentes cambian sólo en esa repetición, usando su clave original y la
  versión de la serie. No se reinician otras excepciones ni se pierde información.
- Se conserva la duración real al mover y la zona Europe/Madrid. Un destino inexistente
  o ambiguo por cambio horario muestra ayuda para editar la hora manualmente; no guarda
  una hora inventada ni abre automáticamente un modal.
- Se preserva la hora de las citas posteriores a las 23:45 al moverlas horizontalmente.
  El límite anterior podía introducir involuntariamente un desplazamiento hacia atrás.
- Una cita eliminada desde otra ventana no se recrea al recibir una actualización antigua.

La carga y la vista previa se gestionan dentro de CalendarPage; `useLoad` global no
cambia. No se añaden dependencias, servicios ni migraciones. Se utiliza la transacción,
control de versión y programación de avisos existentes. Sólo datos sintéticos en pruebas.

## Archivos de esta revisión

- `frontend/calendar.tsx`: separación clic/arrastre, guardado directo, estado provisional,
  recuperación, bloqueo durante carga, cancelación y ayuda visible.
- `frontend/app.tsx` y `web/style.css`: variante opcional de aviso de error, con
  `role="alert"`, para fallos después de salir de Agenda. Los avisos existentes conservan
  su comportamiento por defecto.
- `backend/taller/agenda.py`: rechazar actualización con versión informada si el ID ya
  no existe. Se conserva el alta con UUID del cliente y sin versión.
- `tests/test_agenda_occurrences.py`: tres casos de actualización eliminada/altas compatibles.
- `e2e/agenda.spec.ts`: el arrastre comprueba persistencia directa sin modal; se conserva
  la edición posterior por teclado, verificación en base y auditorías Axe.
- `e2e/agenda-drag.spec.ts`: doce nuevas regresiones.
- Este informe, estado verificado y relevo. Los cambios anteriores permanecen intactos.

## Verificación

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pip check` | Sin dependencias rotas |
| `.venv/bin/python -m pytest tests/test_agenda_occurrences.py -q` | 21 correctas, 1,01 s |
| `.venv/bin/python -m pytest -q` | 631 correctas, 87,09 s |
| `npm run build` (incluye `npm run typecheck`) | Correcto; 43 módulos, 2,02 s |
| `npm run typecheck:e2e` | Correcto |
| `npm run test:e2e -- e2e/agenda.spec.ts e2e/agenda-presentation.spec.ts e2e/agenda-drag.spec.ts --reporter=list,json --output=reports/agenda-drag-2026-10-08/verified-artifacts` | 26 correctas, 45,175 s |
| `npm run test:e2e` (copia aislada idéntica por hashes) | 118 correctas, 243,002 s; 0 fallos, omitidas o reintentos |
| `git diff --check` | Correcto |

Las doce regresiones nuevas cubren clic/temblor/gesto sin cambio/cancelaciones; una única
escritura con respuesta retenida y persistencia tras reiniciar; rollback y reintento;
conflicto de versión; recarga fallida; recurrencias y excepciones; borrado desde otra
ventana; cambio de día durante guardado; desplazamiento horizontal a las 23:50; error
tras navegar; y ambos cambios horarios de Madrid.

Las pruebas existentes de Agenda siguen comprobando accesibilidad, movimiento entre
días, redimensionado, edición por teclado, horas en dos zonas del navegador y aspecto
claro/oscuro a distintos anchos. Revisadas capturas finales del calendario y del agarre.
Las pruebas normales no contactan con CartoCiudad ni usan bases reales.

Evidencia local en `reports/agenda-drag-2026-10-08/`:
`before.log/json` y `before-artifacts/` reproducen el modal no deseado;
`pytest-agenda-occurrences.log`, `pytest-full.log`, `pip-check.log`,
`build-verified.log`, `typecheck-e2e-verified.log`, `directed-verified.log/json`,
`verified-artifacts/`, `source-hashes.json` y `e2e-full.log`.
Se fijó `PLAYWRIGHT_JSON_OUTPUT_NAME` para conservar cada ejecución dirigida.
La ejecución completa final está en `e2e-isolated.log`, `e2e-final.json` e
`isolated-artifacts/`. Se comprobaron los hashes de fuentes y compilación, tanto en
el repositorio como en la copia aislada, después de terminar. La copia temporal se
eliminó tras conservar los resultados y capturas; no contiene una entrega distinta.

El primer lote ampliado tuvo una expectativa incorrecta en el test de conflicto:
comparaba el retorno de save con get sin incluir `exceptions: []`, metadato que get
siempre añade. Se corrigió la comparación manteniendo comprobación exacta de todos
los campos persistidos. Las siguientes ejecuciones dirigidas completas pasaron.
El fallo inicial por apertura de modal se conserva como evidencia anterior al cambio.

La primera batería completa terminó con 117 pruebas correctas y una que no pudo arrancar
el backend: `dist/index.html` no estaba presente en el instante de iniciar su fixture.
El directorio se regeneró durante la ejecución (Vite vacía `dist` al compilar); se observó
un `npm run start` simultáneo. El archivo volvió a aparecer y sus hashes, y los de las
fuentes, seguían siendo idénticos. Se conservan `e2e-full.log` y `e2e-first.json`, sin
atribuir ese resultado a una prueba funcional ni ocultar el fallo de infraestructura.
La verificación completa final utiliza una copia temporal aislada de las mismas fuentes
y `dist`, comprobada por hashes, con las dependencias ya instaladas. No copia bases reales
ni cambia fixtures o lógica del producto para sortear el fallo. Se ejecuta el mismo
`npm run test:e2e` desde esa copia; registro en `e2e-isolated.log`.

Playwright avisa de que `NO_COLOR` se ignora por estar definido `FORCE_COLOR`; no afecta
a las aserciones. Sin errores de dependencias, TypeScript o compilación.

## Uso y límites

En Agenda → Día/Semana, arrastrar la cita o su borde inferior y soltar guarda el cambio.
Hacer clic abre la edición normal. Escape cancela un arrastre en curso.
En repeticiones, el arrastre sólo afecta a la cita seleccionada; editar toda la serie
sigue disponible en el formulario.

Esta revisión se ha ejecutado en Linux/Chromium y servicio Python real con SQLite
sintética. No se ha ejecutado Windows/WebView2 ni reconstruido el instalador.
Sin commit ni push. Para cargar también la protección backend nueva en la previsualización,
detener el proceso anterior con Ctrl+C y ejecutar `npm run start` desde el repositorio.
