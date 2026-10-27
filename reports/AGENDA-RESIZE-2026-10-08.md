# Agenda: control de duración sin franja opaca · 08/10/2026

Actualización posterior: `AGENDA-DRAG-2026-10-08.md` sustituye el flujo de confirmación
del arrastre por guardado directo al soltar. Este informe conserva la evidencia de
la corrección visual previa; el estilo del agarre se mantiene.

## Problema reproducido

El control `.event-resize-handle` ocupaba 20 px de alto y aplicaba
`background: var(--surface-2)` al pasar el cursor o recibir foco de teclado.
En una cita corta de 45 px tapaba casi la mitad inferior, incluida parte de la hora.
Se reprodujo con un evento sintético de 30 minutos antes de modificar el producto:
la nueva prueba falló por ese fondo opaco y guardó una captura equivalente al defecto.

## Corrección

- Fondo transparente en reposo, hover, foco y arrastre. Un agarre de 20×3 px utiliza
  el color de la propia cita; su opacidad aumenta en hover/foco/pulsación con una
  transición CSS de 120 ms. La preferencia global de movimiento reducido sigue vigente.
- Se conserva el botón semántico, nombre accesible, cursor de redimensionar y handlers
  existentes. El símbolo de flechas se sustituye por un indicador decorativo sin texto.
- Zona de interacción de 24 px y desplazamiento inferior de 3 px: deja otros 24 px
  libres para mover las citas de altura mínima (45 px). El indicador visible permanece
  dentro de la tarjeta; no se pinta nada fuera. Foco visible con contorno interior.
- Menor padding inferior del contenido para que la hora de las citas cortas se vea
  completa. Sin cambiar cálculo de fechas, duración, guardado o confirmación.

Sólo se cambian `frontend/calendar.tsx` y `web/style.css` en el producto. Se amplía
`e2e/agenda-presentation.spec.ts` con dos pruebas parametrizadas por tema; documentación
en este informe, `docs/ESTADO-VERIFICADO.md` y `CONTINUAR.md`.
Sin dependencias, peticiones, estado React o trabajo de red adicionales. Cambios previos
conservados sobre `6be3445`; sin commit ni push.

## Verificación

Entorno Linux y Chromium/Playwright. Cada prueba usa SQLite temporal sintética;
no se abrieron ni modificaron datos reales. Nuevos casos: Día/Semana, claro/oscuro,
1366/390 px, geometría invariable en hover, transparencia, hora visible, foco y apertura
con teclado, cancelación sin modificación. Ocho auditorías Axe WCAG 2.2 AA correctas
en esas combinaciones y ocho capturas revisadas visualmente.

La batería existente de Agenda comprueba además mover, alargar, guardar y reabrir con
teclado en ventana de 1024 px, tema oscuro y letra grande, persistencia, recurrencia
y cambios horarios.

| Comando | Resultado |
| --- | --- |
| `npm run build` (incluye `npm run typecheck`) | Correcto; 43 módulos, 907 ms |
| `npm run typecheck:e2e` | Correcto |
| `npm run test:e2e -- e2e/agenda.spec.ts e2e/agenda-presentation.spec.ts --reporter=list,json --output=reports/agenda-resize-2026-10-08/verified-artifacts` | 14 correctas, 25,164 s, sin omitidas ni reintentos |
| `npm run test:e2e` | 106 correctas, 165,824 s; 0 fallos, omitidas o reintentos |
| `git diff --check` | Correcto |

Evidencia local en `reports/agenda-resize-2026-10-08/`: `before.log/json` y
`before-artifacts/` (reproducción), `directed-verified.log/json` y
`verified-artifacts/` (14 pruebas y capturas), `build-verified.log`,
`typecheck-e2e-verified.log`, `source-hashes.json`, `e2e-full.log` y `e2e-final.json`.
Hashes de fuentes y compilación comprobados sin cambios durante la batería completa.
El JSON dirigido se escribe mediante `PLAYWRIGHT_JSON_OUTPUT_NAME`.

Incidencias intermedias conservadas: la primera corrección visual dejó un objetivo
de 20 px que la auditoría WCAG 2.2 rechazó. Al ampliarlo a 24 px completamente dentro
de la tarjeta invadía el control principal de las citas cortas y bloqueaba sus clics;
esa ejecución se interrumpió tras confirmar la causa. El desplazamiento inferior
corrige ambos controles sin relajar pruebas, excluir reglas Axe ni cambiar alturas
de eventos. La ejecución dirigida final incluye la regla de tamaño de objetivos
también en las dos pruebas nuevas.

Advertencia de entorno en Playwright: Node ignora `NO_COLOR` porque `FORCE_COLOR`
está definido. Sin errores de TypeScript/compilación. No se repitió pytest porque no
hay cambios Python. No se ejecutó Windows/WebView2 ni se reconstruyó el instalador;
las verificaciones descritas corresponden al navegador en Linux.

Para comprobarlo, recargar la previsualización existente o ejecutar `npm run start`
desde el repositorio. En Agenda → Día/Semana, pasar el cursor por el borde inferior
y arrastrarlo: el fondo permanece uniforme y la propuesta de duración se confirma
en el formulario habitual.
