# Avisos de agenda · 07/10/2026

El adaptador de Windows conserva el sonido normal del sistema y ahora permite
abrir Agenda al pulsar el aviso mientras el programa sigue abierto, incluida la
bandeja. Se ha comprobado por tipos el escritorio completo para Windows. **No
se han ejecutado ni escuchado avisos en Windows real en esta sesión.**

## Comportamiento y cambios

- Se mantiene `ToastGeneric` y `ms-winsoundevent:Notification.Default`, una sola
  reproducción, sin escenario urgente, bucles, archivos de sonido ni reproducción
  paralela que evada los ajustes de Windows. Sin sonido se solicita `silent=true`.
- La prueba de Configuración usa la opción de sonido que muestra el formulario;
  antes activaba siempre el sonido nativo. La interfaz distingue solicitud al
  sistema de visibilidad/sonido efectivo, muestra errores y evita pruebas repetidas
  mientras la anterior está en curso.
- Se comprueba `ToastNotifier.Setting`. Un rechazo síncrono de Windows no consume
  el recordatorio. No se interpreta `Show` como prueba de que el usuario haya visto
  u oído el aviso: Windows sigue controlando No molestar, permisos y volumen.
- El objeto Windows y su manejador `Activated` se conservan mientras el aviso está
  vigente. Prueba y agenda usan etiquetas distintas. La activación enfoca la ventana
  y emite `agenda-notification-open` con `{"destination":"agenda"}`. El cliente usa
  la navegación existente con su protección de cambios sin guardar.
- Tras aceptar el sistema un aviso, se conserva en memoria su confirmación pendiente.
  Un fallo de transporte o respuesta `ok:false` reintenta la confirmación sin volver
  a reproducirlo en cada consulta. Esta memoria es del proceso; la confirmación
  persistente del servicio continúa siendo la que permite deduplicar tras reiniciar.
- La confirmación opcional `expected_due_at` impide consumir una repetición que se
  haya reprogramado entre presentación y confirmación. `expected_members` conserva
  los pares exactos `id/due_at` aceptados; otro listado concurrente no puede ampliar
  lo que se confirma. Se valida forma, pertenencia al evento, unicidad y el límite
  natural de 732 repeticiones por cinco avisos. Leer y posponer conservan su contrato.
- `notifications.list` devuelve `delivery_members` y `has_undelivered`. Este último
  permite al navegador detectar un miembro nuevo pendiente aunque el representante
  del grupo ya esté entregado. La confirmación reintentada usa el grupo original.
- El intervalo sigue siendo 20 segundos en programa y navegador. Se conservan los
  horarios Europe/Madrid, el texto de hora local y la alarma de eventos de día
  completo a las 09:00, sin modificar la semántica de agenda.
- Se conservan cierre de ventana a bandeja, inicio de sesión con `--background`,
  salida explícita con copia y protección de borradores. Configuración consulta el
  último error nativo al abrir Agenda, sin añadir sondeos periódicos.

## Validación ejecutada

Entorno Linux, Rust 1.98.1. Talleres y entradas de pruebas exclusivamente sintéticos.
No se modificaron datos reales ni se emitieron avisos del sistema en estas pruebas.

| Comando | Resultado |
|---|---|
| `.venv/bin/python -m pytest tests/test_notification_delivery.py tests/test_agenda_occurrences.py -q` | 34 correctas, 0,84 s |
| `cargo +1.98.1 test --locked --manifest-path src-tauri/Cargo.toml --no-default-features --features native-notifications --lib notifications::tests` | 5 correctas; XML, sonido/silencio, destino, rechazo, reintento y grupo inmutable |
| `cargo +1.98.1 check --locked --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-gnu --no-default-features --features native-notifications --lib` | Código 0; tipos reales del adaptador Windows |
| `cargo +1.98.1 check --locked --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-gnu`, con entorno descrito abajo | Código 0, 5,19 s; incluye `main.rs`, IPC y estado nativo |
| `cargo +1.98.1 clippy --locked --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-gnu -- -D warnings`, mismo entorno | Código 0, 1,36 s |
| `rustfmt +1.98.1 --check --edition 2021 --config skip_children=true src-tauri/src/notifications.rs src-tauri/src/main.rs` y `git diff --check` de los archivos modificados | Código 0 |

Las pruebas de backend incluyen reprogramación ya vencida, idempotencia, lectura,
posposición, un grupo ampliado entre presentación y confirmación, representante
entregado con un miembro pendiente, rechazo de miembros de otro evento y snapshots
inválidos o demasiado grandes. Las pruebas de navegador y la suite general quedan
recogidas en la verificación conjunta de esta entrega.

## Comprobación de tipos Windows desde Linux

Se añadió únicamente `rust-std` para `x86_64-pc-windows-gnu`. Para comprobar también
`main.rs`, se descargaron mediante `apt-get download` dos paquetes oficiales Ubuntu
y se extrajeron con `dpkg-deb -x` en `/tmp/canamo-windows-check.lXpqck/root`, sin
instalación global: 11,6 MB descargados y 121 MB extraídos.

| Paquete | SHA-256 |
|---|---|
| `binutils-mingw-w64-x86-64_2.41.90.20240122-1ubuntu1+11.4_amd64.deb` | `28bfabbf64a68813a56360bca056072af9ff71ef4090a4b8a8a085afcda3e4dd` |
| `mingw-w64-common_11.0.1-3build1_all.deb` | `4a42fd30fbc3838c58c929d8a4882682fc12408bb7a0e6cafa913c0f0a57c187` |

El wrapper privado `windres-private` ejecuta el compilador real de recursos:

```sh
exec /tmp/canamo-windows-check.lXpqck/root/usr/bin/x86_64-w64-mingw32-windres \
  --preprocessor=/usr/bin/cpp --preprocessor-arg=-E --preprocessor-arg=-xc \
  --preprocessor-arg=-DRC_INVOKED --preprocessor-arg=-D_WIN32 \
  --include-dir=/tmp/canamo-windows-check.lXpqck/root/usr/share/mingw-w64/include "$@"
```

Los dos comandos completos usan las variables:

```sh
TAURI_CONFIG='{"bundle":{"externalBin":[]}}'
RC=/tmp/canamo-windows-check.lXpqck/windres-private
```

Se pasaron como variables de entorno del comando. El overlay evita exigir un
sidecar Windows todavía no construido; no modifica `tauri.conf.json` ni sustituye
el servicio por un archivo falso. Se compilaron los recursos reales y se comprobaron
los tipos de `main.rs`, **sin enlazar un ejecutable ni verificar su instalación**.
Los intentos previos fallaron por sidecar ausente y después por `windres` ausente;
ambos obstáculos quedaron resueltos para este alcance. El check de escritorio
Linux quedó bloqueado por ausencia de los paquetes de desarrollo GTK/cairo/libsoup;
no se reinstaló ese SDK grande.

## Revisión de inicialización e identidad Windows

Se inspeccionó el código exacto de las dependencias fijadas: `windows` 0.61.3 usa
`FactoryCache` para `CreateToastNotifierWithId`; `windows-core` 0.61.2, en
`src/imp/factory_cache.rs`, reintenta la activación tras `CoIncrementMTAUsage` cuando
recibe `CO_E_NOTINITIALIZED`. Microsoft documenta que esta función crea el MTA si
falta y incorpora un hilo que no pertenece a otro apartamento. No se añadió una
inicialización COM redundante a los hilos de sondeo y prueba. Esta conclusión
procede del código y la documentación, no de ejecutar esos hilos en Windows.
[Referencia de Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coincrementmtausage).

Se comprobó la plantilla oficial correspondiente a la CLI instalada, Tauri 2.11.5:
el instalador obtiene `bundle_id` de `settings.bundle_identifier()`, crea el acceso
del menú Inicio y asigna su `PKEY_AppUserModel_ID` al mismo identificador. El
adaptador usa `app.config().identifier`, actualmente
`es.tallereselcanamo.desktop.dev`, por lo que las fuentes coinciden. Las
[plantillas NSIS](https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.5/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi)
y su [macro de identidad](https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.5/crates/tauri-bundler/src/bundle/windows/nsis/utils.nsh)
son las predeterminadas: el proyecto no las sustituye.

## Límites y prueba pendiente en Windows

El clic se implementa para una aplicación que sigue viva. Después de «Salir» no
hay receptor de activación: no se ha añadido registro COM para relanzar el programa
desde una notificación antigua. El adaptador Linux conserva su comportamiento
anterior; la nueva activación es específica de Windows.

La identidad del aviso debe comprobarse con una instalación normal que conserve
el acceso del menú Inicio. Un ejecutable suelto de desarrollo, un acceso eliminado
o una instalación con `/NS` que omita accesos no equivalen a esa instalación y no
se dan por válidos para notificaciones nativas.

La aceptación física debe realizarse con el instalador Windows real: aviso visible
y un solo sonido normal, prueba silenciosa, No molestar y bloqueo de notificaciones,
clic hacia Agenda con y sin borrador pendiente, aviso con ventana en bandeja e inicio
de sesión automático. Al salir o apagar el equipo no debe prometerse entrega. Las
comprobaciones de tipos y XML aquí ejecutadas no sustituyen esas pruebas.

## Fuentes primarias consultadas

- [Microsoft: audio de una notificación](https://learn.microsoft.com/en-us/uwp/schemas/tiles/toastschema/element-audio): sonido del sistema, silencio y bucles.
- [Microsoft: ToastNotifier.Setting](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotifier.setting?view=winrt-26100): estado de habilitación.
- [Microsoft: ToastNotification.Activated](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotification.activated?view=winrt-26100): activación mientras vive la aplicación.
- [Microsoft: activación y registro de notificaciones de aplicaciones](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/notifications/app-notifications/app-notifications-quickstart?tabs=cpp): ciclo de vida y registro necesarios para activación externa.
- [Microsoft: notificaciones y No molestar](https://support.microsoft.com/en-us/windows/experience/notifications-and-do-not-disturb-in-windows?authuser=0): control del usuario sobre presentación, sonido y excepciones.
- [Tauri: notificaciones](https://v2.tauri.app/plugin/notification/): comportamiento de instalación y alcance de las acciones del plugin. Se conserva el adaptador Windows existente; no se añade ese plugin.
