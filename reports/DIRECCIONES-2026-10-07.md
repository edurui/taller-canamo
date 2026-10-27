# Autocompletado de direcciones · 07/10/2026

Implementado en alta y edición de clientes, con CartoCiudad oficial y entrada manual
siempre disponible. Verificación final: **628 pytest y 96 E2E correctas**, sin fallos,
omitidas ni reintentos; ambos typechecks, build y pip check correctos. Solo datos
sintéticos en pruebas. No se han abierto, copiado ni modificado bases reales del taller.
Los cambios locales anteriores se conservan. Sin staging, commit ni push.

## Implementación

`CustomerForm → AddressAutocomplete → RPC → Python → CartoCiudad`.
Se amplía el combobox existente sin cambiar sus consumidores de conceptos locales.
País ES, mínimo tres caracteres escritos manualmente y debounce de 300 ms. Abrir una
edición, enfocar el campo o cambiar otro dato no consulta una dirección ya guardada.
Se descartan respuestas antiguas por secuencia y contexto; editar, cambiar país,
seleccionar, Escape y cerrar invalidan la búsqueda. Ratón, flechas, Enter y Tab operativos.

Seleccionar rellena los campos disponibles; después todos siguen siendo editables.
Los campos ausentes no vacían valores manuales. El código postal de una vía que abarca
varios códigos queda sin confirmar: no se escoge arbitrariamente el primero.
La línea postal conserva número/extensión del proveedor; únicamente se retiran sufijos
de localidad identificados por campos estructurados, sin deducir población por comas.
IDs estables distinguen portales diferentes aunque compartan identificador de vía.

La consulta remota usa urllib y TLS estándar con host fijo HTTPS, `Accept: application/json`,
timeout de socket de 2,5 s, máximo 256 KiB y 12 candidatos. Rechaza redirecciones, contenido
inesperado, exceso de tamaño y errores HTTP/DNS/socket/JSON. Solo sale el texto de dirección;
el contexto geográfico se utiliza localmente. Sin logs permanentes de consultas.

Una única búsqueda nacional, sin filtros territoriales excluyentes; clasificación por
CP, población/municipio y provincia, además de vía/portal según la consulta. Se excluyen
administraciones y POI, se deduplica y se devuelven hasta ocho resultados. La preferencia
local opera entre los candidatos que devuelve el proveedor: no garantiza exhaustividad.
Caché LRU en memoria de 192 consultas normalizadas y contexto, vigencia 15 minutos,
con bloqueo breve, copias defensivas y una sola petición concurrente por clave idéntica.

## Contratos y escritorio

`addresses.search` acepta:

```typescript
{ query: string; postal_code?: string; city?: string;
  province?: string; country?: string /* ES por defecto */ }
```

Devuelve:

```typescript
{ status: "ok" | "unavailable"; items: Array<{
  id: string; label: string; address: string; postal_code: string;
  city: string; province: string; country: "ES";
}> }
```

Sin latitud, longitud ni JSON original. `customers.save` no se ha modificado ni exige
haber seleccionado una sugerencia. El fallo se presenta como ayuda discreta, sin modal.

Se detectó una restricción real del escritorio: su puente JSONL procesa cada RPC de
forma secuencial. Una llamada HTTP síncrona lo bloquearía incluso sin bloqueo SQLite.
Por eso el adaptador Tauri usa tres acciones cortas del mismo servicio:

- `addresses.start` recibe los mismos campos y devuelve `{identifier: string | null}`.
- `addresses.result({identifier})` devuelve `{ready: false}` o `{ready: true, result}`.
- `addresses.cancel({identifier})` libera el resultado y devuelve `{ok: true}`.

Ocho trabajadores daemon como máximo, 32 resultados temporales y caducidad de 60 s;
sondeo local de 150 ms, espera del formulario limitada a 12 s y cancelación al invalidar.
Cancelar no interrumpe un socket ya iniciado, pero su resultado tardío no revive el trabajo.
El timeout de urllib mide operaciones de socket, no garantiza un plazo total DNS/HTTP.
El preview HTTP usa `addresses.search` fuera del bloqueo de SQLite. Se probó guardar
con el proveedor retenido, tanto por dispatch concurrente como por el protocolo JSONL
secuencial real (`stdio.serve` con transporte e IO sintéticos). No se modificó Rust.

## Archivos de este encargo

| Archivos | Cambio |
|---|---|
| `backend/taller/addresses.py`, `address_jobs.py`, `app.py` | Proveedor, caché, trabajos limitados y acciones RPC |
| `frontend/address-autocomplete.tsx`, `address-service.ts` | Formulario y adaptación del transporte Tauri |
| `frontend/controls.tsx`, `people.tsx` | Combobox compatible y alta/edición de clientes |
| `frontend/settings.tsx`, `tools/legal/SOURCES.md` | Atribución y fuentes, también en el ZIP de licencias |
| `tests/test_addresses.py`, `test_address_jobs.py` | 81 casos backend nuevos |
| `e2e/address-autocomplete.spec.ts`, `fixtures.ts` | 28 casos nuevos y bloqueo del transporte externo en toda la suite |
| `e2e/recovery-fiscal.spec.ts` | Espera correcta de una propiedad que aún no existe antes de finalizar el guardado |
| `README.md`, `docs/DIRECCIONES.md`, `docs/ESTADO-VERIFICADO.md`, `CONTINUAR.md`, este informe | Uso, contrato, privacidad y resultados |

Sin dependencias nuevas, migración, coordenadas, API key, servicios de pago configurados,
Google, infraestructura cloud ni cambios de branding/configuración del taller.
No cambian las consultas de listados, importador, facturación ni agenda.

## Comandos y evidencia ejecutada

Ubuntu Linux, Python de `.venv`, navegador Chromium; pruebas con SQLite temporal sintética.
Logs y JSON/XML locales en `reports/addresses-2026-10-07/` (ignorados por Git).

| Comando / comprobación | Resultado final |
|---|---|
| `.venv/bin/python -m pip check` | Código 0, sin incompatibilidades |
| `.venv/bin/python -m pytest --junitxml=reports/addresses-2026-10-07/pytest.xml` | 628 correctas, 95,52 s; 0 fallos/errores/omitidas |
| `npm run typecheck` | Código 0 |
| `npm run typecheck:e2e` | Código 0, repetido después de corregir la espera de retención |
| `npm run build` | Código 0; JS 401,46 kB / gzip 122,10 kB; CSS sin cambios |
| `npm run test:e2e` | 96 correctas, 149,156 s; 0 fallos/omitidas/flaky, sin reintentos |
| `.venv/bin/python scripts/prepare_licenses.py` y exportación ZIP | 620 componentes; 1.361 entradas exportadas, atribución y hash verificados |
| `git diff --check` | Código 0 |

Los 81 casos backend cubren parsing, vías/portales, opcionales, límites, país, ranking,
duplicados, CP ambiguo, JSON/red/HTTP inválidos, privacidad/SSRF, caché, concurrencia,
TTL/capacidad/cancelación y guardado sin esperar al proveedor. Los 28 E2E cubren mínimo,
debounce, ratón/teclado, Escape, selección, edición, fallos, races, guardado pendiente y
dos recorridos del adaptador Tauri con `invoke` simulado. Los 68 casos anteriores pasan.

Dieciséis auditorías Axe sin violaciones y dieciséis capturas revisadas: lista y selección
en 320/390/768/1366 px, claro/oscuro. Sin desbordamiento ni opciones recortadas en esos casos.
Las E2E sustituyen también el transporte Python; ninguna consulta llega a CartoCiudad.

Se conservan los fallos intermedios y su explicación: el primer dirigido obtuvo 27/28
por una expectativa del test de CP vacío pese al valor inicial; ahora prepara contexto
manual y comprueba que se conserva íntegro. El primer completo obtuvo 95/96 por un
`TypeError` en el sondeo previo de retención: la propiedad aparece tras guardar, de modo
que el test ahora espera su aparición y sigue exigiendo exactamente el valor 3. No se
relajó la validación del producto ni se cambiaron políticas de copias para pasar la prueba.

Warnings conservados: Node indica que `FORCE_COLOR` prevalece sobre `NO_COLOR`; el
inventario mantiene el aviso previo del paquete opcional de construcción LZMA que solo
declara licencia en metadatos. Ninguno corresponde a una dependencia nueva.

## Comprobación externa limitada y atribución

Una consulta manual al endpoint real con la dirección pública de la sede del IGN,
ajena a cualquier dato del taller: **status ok, seis resultados, 723,628 ms**;
repetición idéntica desde caché: **0,158 ms**. Campos exactos y presencia de población/CP
comprobados. `provider-smoke.json` contiene solo estado, conteos y tiempos. Es una muestra
puntual de disponibilidad, no una garantía de latencia ni una prueba normal dependiente de red.

Direcciones: **CartoCiudad (IGN/CNIG) · CC BY 4.0**. Fuentes oficiales consultadas:
[contrato REST](https://github.com/IDEESpain/Cartociudad#1-candidates),
[licencia IGN/CNIG](https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf),
[portal CartoCiudad](https://www.cartociudad.es/web/portal).
La función no descarga/distribuye la capa de códigos postales de Correos ni utiliza
la licencia del código del servidor como si fuera licencia de los datos.

**Pendiente externo:** instalación y ejecución del binario actualizado en Windows/WebView2;
este entorno es Linux. Se verificaron servicio Python, protocolo JSONL y navegador con
adaptador Tauri simulado; no se afirma ejecución de esta función en Windows ni se presenta
el binario anterior como actualizado. No se reconstruyó instalador o sidecar en esta tarea.

Para revisar desde las fuentes actuales, reinicia la previsualización con `npm run start`
y abre Clientes → Nuevo cliente. El comando ya existente conserva su base local; no fue
ejecutado con datos reales como parte de estas pruebas.
