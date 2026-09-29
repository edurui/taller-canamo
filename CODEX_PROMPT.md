# Encargo para Codex: completar Talleres El Cañamo

Actúa como responsable técnico de un producto de escritorio para un pequeño negocio real.
Tu encargo es **trabajar sobre esta carpeta, implementar lo pendiente, ejecutarlo, probarlo y
preparar una entrega instalable y mantenible**. No quiero otra respuesta que describa lo que
podrías hacer ni que me pida programar las piezas que faltan.

## 1. Lectura inicial y autoridad de las fuentes

Lee `AGENTS.md`, `README.md`, `docs/ESTADO-VERIFICADO.md`, `docs/CONTEXTO-PRODUCTO.md`,
`docs/ACEPTACION.md`, `docs/BUILD-WINDOWS.md` y `docs/CAMBIOS-RELEVO.md`. Inspecciona el código,
los informes `reports/` y las configuraciones reales antes de planificar cambios.
No supongas que existe una versión anterior más completa ni que un comentario de código
que dice "validado" equivale a evidencia. Las fotos privadas se pueden consultar localmente
para diseño/migración, pero contienen datos personales y no deben publicarse ni enviarse a terceros.

La versión del chat anterior tuvo entregas incompletas. El relevo 0.9.1 recupera los 22 archivos
originales y añade las piezas de arranque, configuración, IPC y tests que faltaban. Usa el estado
verificado de ESTA carpeta, no acusaciones o promesas antiguas del chat.

## 2. Usuario final y objetivo

Soy Eduardo, desarrollador web acostumbrado a React/TypeScript, normalmente en Ubuntu.
El usuario final es mi tío, autónomo mecánico de **Automecánica Talleres El Cañamo**,
Calle Torres Quevedo 22, 41300 San José de la Rinconada, Sevilla. Su programa es un Access
antiguo. Es práctico, poco interesado en funciones complicadas; no conocemos su edad exacta.

Solo usará un ordenador Windows. Debe funcionar sin Internet para clientes, borradores,
historial y trabajo local; las comunicaciones fiscales y otros servicios tratarán los cortes
según el mecanismo permitido, no fingiendo confirmaciones. Debe poder trasladarse a un PC nuevo.

**Flujo sagrado: buscar cliente o matrícula -> nueva factura -> imprimir.**
No obligues a mi tío a aprender un ERP. Los extras existen, pero no le estorban.

## 3. Arquitectura que debes conservar

React + TypeScript para la interfaz, Tauri 2 para Windows, servicio Python auxiliar y SQLite.
No añadas Supabase, Vercel, servidores remotos, dominio, cuenta cloud obligatoria o pagos
recurrentes para hacer funcionar el núcleo. No despliegues nada ni crees recursos de pago.
No conviertas la entrega final en una simple web con un acceso directo.

La API Python ya centraliza operaciones de negocio; el frontend no debe ejecutar SQL ni
calcular los importes oficiales de forma independiente. Utiliza decimales exactos, transacciones,
snapshots y claves idempotentes. Datos persistentes fuera del directorio de instalación.
El servicio debe arrancar/cerrarse solo, sin terminal ni Python instalado por el usuario final.

Mantén el trabajo existente y refactoriza donde haga falta. Solo plantea un cambio de stack
con una razón técnica demostrada, no por preferencia. Mejora los tipos y legibilidad del TSX
heredado sin alterar el flujo funcional.

## 4. Funciones y experiencia que debe tener

### Uso diario visible
Inicio sencillo, Clientes y Facturas. Cliente con NIF, dirección, contacto, notas y varios
vehículos. Vehículo con matrícula, marca/modelo, tipo, chasis/VIN, km y titularidad.
No exigir coche/matrícula para facturar reparaciones de maquinaria o trabajos no asociados a uno.

Buscador global permanente por nombre/apellidos/razón social, matrícula, teléfono, NIF y
código antiguo. Respuesta desde el primer carácter, lista desplegable, coincidencia relevante
preseleccionada y autocompletado aceptable. Flechas, Enter, Tab cuando corresponda y Esc,
sin cambiar de pantalla automáticamente ni dejar que una respuesta vieja sustituya a una nueva.
Encontrar el teléfono del propietario viendo solo su matrícula es un requisito esencial.

Facturas con conceptos libres y frecuentes, cantidades, precio, IVA, descuentos, borradores,
revisión antes de emitir, PDF e impresión, cobros y pendientes. Histórico por cliente y
vehículo. Nada de presupuestos, órdenes o artículos obligatorios para facturar.
Los datos impresos de documentos antiguos no cambian al editar las fichas. No permitir borrar
documentos emitidos ni reciclar números como si no hubieran existido.

### Extras discretos
En «Más herramientas», ocultable: presupuestos, órdenes de reparación/entrada,
agenda, artículos/stock, proveedores, informes sencillos y exportaciones. Conversiones entre
documentos sin reescribir ni duplicar movimientos. Desactivar/ocultar extras no borra datos.

Agenda realmente usable: mes, semana, día, Hoy, anterior/siguiente, selector de fecha,
eventos de todo el día/multidía, solapamientos, repeticiones y avisos configurables.
Europe/Madrid y cambios de horario. Buen comportamiento al reducir la ventana. Avisos
persistentes, leídos/pospuestos, permiso de Windows y funcionamiento con ventana oculta en
bandeja si se implementa. No prometer notificaciones con PC apagado; recuperar pendientes
sin duplicarlas ni crear una tormenta al volver a abrir.

Automatizaciones primero sin IA: conceptos recientes, conversiones, próximas revisiones y
mensajes preparados de presupuesto/vehículo terminado. IA optativa para dictado, lectura de
ficha técnica, búsqueda del historial o redacción, siempre revisable y sin inventar seguridad
mecánica, diagnósticos, precios o trabajos. No debe bloquear nada sin modelo/credenciales.
No actives envíos automáticos a clientes sin configuración y confirmaciones apropiadas.

### Diseño e impresión
Amarillo, negro y blanco; minimalista, moderno y tranquilo. Modo oscuro/claro/sistema,
letra ajustable, contraste, foco visible, controles grandes y etiquetas comprensibles.
No llenar la pantalla de cuadros y gráficas. No sustituir facilidad por animaciones.

El logo independiente no existe aún; el usuario acepta un marcador EC y carga/cambio de
imagen desde Configuración. Las fotos contienen coches rojos usados en la identidad del
negocio; no inventar derechos o afiliación con fabricantes. Mantén el selector de logo.

PDF A4 parecido al antiguo: cabecera del negocio/logo, destinatario, número, fecha, código
de cliente, matrícula/km, cantidades/conceptos/precios/importes y base/IVA/total.
Marca de agua tenue del logo, varias páginas sin solapamientos y QR/textos correctos cuando
proceda. Documento generado como texto/vector, no una foto entera.

### Configuración, importación y copias
Ajustes de emisor, contacto, IVA y forma de pago habituales, vencimientos, presupuesto,
pie, impresión, logo/agua, accesibilidad y avisos. Series por tipo/año, prefijo, relleno y
número inicial/siguiente. No permitir reiniciar una serie usada. La migración no decide
la numeración nueva; contrastar el último número real al hacer el corte.

El MDB/ACCDB no está disponible. Las tablas aproximadas están documentadas. Prepara
extracción/mapeo/importación con vista previa, no inventes el esquema real ni fusiones
ambiguas. Preserva códigos e histórico; no enviar facturas antiguas como nuevas a AEAT.
El importador actual lee CSV/JSON, no abre Access directamente: debes completar ese tramo.

Copias consistentes, segunda ubicación opcional, cifrado y restauración con copia previa y
rollback ante fallo. Exportar para nuevo PC sin pérdidas. No sincronizar la SQLite activa
mediante OneDrive. Certificados fuera de Git, logs y copias generales; reinstalación segura
cuando cambie el usuario/PC por protección DPAPI.

## 5. Estado comprobado y lo que NO está terminado

El backend carga y **88 casos pytest locales pasan**; consulta los logs. Hay test de proceso
IPC y HTTP reales, pero fixtures fiscales simulados. Hay una comprobación de sintaxis de
siete TSX, NO typecheck ni build de Vite. PDF demo generado y revisado en una página.

Se han escrito los archivos de dependencias/compilación, el puente Rust y los scripts
Windows, pero no se ejecutaron: falló DNS de npm y no había Rust en el entorno del relevo.
No hay lockfiles JS/Rust, `dist`, instalador ni pruebas Windows/WebView2. No confías en
que un archivo nuevo compila solo porque existe. Verifica cada pieza en tu entorno real.

El estado fiscal es local/sandbox. `PRODUCTION_RELEASED=False`, configuración de pruebas,
`test_document=True` y PDF de pruebas. Subsanaciones, rechazos, duplicados, cadena,
reintentos, QR y validaciones oficiales requieren revisión completa. No basta con cambiar
un flag o una URL para terminarlo. Algunos puntos concretos están ya identificados en
`docs/ESTADO-VERIFICADO.md`: listado histórico con joins a datos vivos, restauración no
atómica de todos los recursos, representaciones equivalentes de IVA, ciclo de vida del
sidecar, notificaciones y esquemas fiscales. Resuélvelos y añade regresiones.

## 6. Fiscal: condiciones no negociables

VERI*FACTU y factura electrónica B2B no son lo mismo. Trátalos por separado y consulta
AEAT/BOE actuales, no plazos legales o códigos XML memorizados. Diseña adaptadores,
registros y estados claros. Al usuario no le deben aparecer errores técnicos sin acción.

Completa todo lo verificable sin credenciales: serialización, XSD oficiales, huellas con
vectores independientes, cola y reconciliación, pruebas de red fallida y respuestas simuladas.
La prueba autenticada requiere certificado/representación legítima y el entorno adecuado.
No pedir la clave privada en el prompt, no enviarla a terceros, no usar facturas ficticias en
producción. No presentar mocks como aceptación AEAT ni prometer homologación inexistente.

El productor y su declaración responsable deben tratarse correctamente según fuentes
oficiales; no generar una declaración firmada o afirmar cumplimiento sin verificación.
Si falta un requisito externo, distingue qué código está terminado, qué verificación falta
y cómo ejecutarla. No uses esa dependencia como motivo para abandonar el resto.

## 7. Forma de trabajar y orden de ejecución

1. Inspecciona carpeta, entorno, permisos, dependencias y estado real de Git. Ejecuta la línea
   base pytest y reproduce el build actual. Crea una lista de trabajo breve con criterios de cierre.
2. Resuelve dependencias, genera lockfiles reales y consigue typecheck/build. No hagas un
   rediseño masivo antes de tener una base reproducible.
3. Completa el puente y empaquetado de escritorio; prueba inicio/cierre, instancia única,
   rutas, guardados, errores de IPC y proceso auxiliar. Ejecuta las pruebas Windows que el
   entorno permita; no describas instrucciones como si fueran una compilación ejecutada.
4. Corrige dominio, integridad, PDF, agenda, UX y extras. Desarrolla tests de regresión a la vez.
5. Completa el adaptador fiscal y la importación hasta donde sea verificable sin los archivos/
   credenciales reales. Mantén bloqueada la operación real hasta superar los gates necesarios.
6. Ejecuta unitarias/integración, E2E de navegador (Playwright o equivalente), accesibilidad,
   revisión visual y pruebas del escritorio real. Registra comandos, resultados y plataforma.
7. Entrega fuente completa, lockfiles, scripts, migraciones, tests, informes, instrucciones
   para instalar/actualizar/restaurar y el instalador cuando realmente pueda construirse.

Puedes paralelizar frontend/calendario, dominio/datos, fiscal y empaquetado cuando dispongas
de subagentes, pero evita editar simultáneamente los mismos archivos. La integración final
es tu responsabilidad; no aceptar cambios sin comprobarlos juntos.

Trabaja con autonomía en acciones locales reversibles autorizadas. No me preguntes por cada
archivo o dependencia. Pregunta solo por una decisión de negocio indispensable, permiso para
un servicio de pago, credenciales o una acción irreversible. No publiques ni fuerces pushes.
Si falla una herramienta, diagnostica con evidencia y usa una alternativa segura; no atribuyas
52 minutos sin entrega a un fallo genérico. Guarda avances verificables y continúa con lo no bloqueado.

## 8. Pruebas que importan

Prioriza fallos reales: doble clic y reintentos, concurrencia, redondeos y varios IVA, cambios de
año, snapshots/listados, cambio de propietario, pagos repetidos/revertidos, stock negativo,
restauración interrumpida, ZIP malicioso, claves fuera de logs, timezone/DST, citas solapadas,
recordatorio pospuesto, inicio de PC, importación duplicada y recuperación tras cierre abrupto.

Prueba el flujo completo cliente -> vehículo -> búsqueda -> factura -> PDF -> cierre ->
reapertura -> historial. Repite sin vehículo y con extras ocultos. Haz pruebas en modo oscuro,
letra grande y ventana pequeña. Para importaciones, cuadra cuentas e importes y conserva
procedencia: no basta con un toast verde.

No desactives validaciones para que pasen tests. No añadas cientos de pruebas triviales para
inflar una cifra. No digas "sin errores" o "perfecto" como garantía absoluta: presenta evidencia
reproducible y las limitaciones restantes.

## 9. Entrega y cierre

Quiero archivos terminados, no otro resumen del trabajo pendiente. Actualiza el estado y
checklist conforme verifiques, y deja el proyecto preparado para que yo ejecute los pasos
externos concretos que no puedas realizar aquí. Mi tío no debe instalar un entorno de desarrollo.

Al cerrar, indica: qué cambiaste, comandos ejecutados y resultado, dónde está el artefacto,
cómo se inicia, qué está realmente probado y qué depende de certificado, Access o impresora.
No confundas "código escrito", "build correcto", "instalador probado" y "fiscal validado".

Empieza ahora inspeccionando y ejecutando la base. Después implementa; no respondas solo con
un plan ni me devuelvas de nuevo tareas de programación que forman parte de este encargo.
