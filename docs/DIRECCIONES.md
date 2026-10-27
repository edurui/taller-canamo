# Direcciones españolas en clientes

En Nuevo cliente o Editar cliente, con país ES, escribe al menos tres caracteres en
Dirección. Tras 300 ms sin escribir se consultan sugerencias de CartoCiudad. Puedes
elegir con ratón o con las flechas y Enter; Escape cierra la lista. Elegir una sugerencia
completa dirección, código postal, población y provincia cuando el proveedor los conoce.
Un campo ausente no borra lo que ya tenías escrito. Si una vía abarca varios códigos
postales, se conserva el código manual; añadir el portal puede concretarlo.

Las sugerencias son opcionales: puedes corregir cualquier campo, no elegir ninguna o
guardar sin Internet. La consulta no valida la dirección ni bloquea Guardar cliente.
Abrir una ficha existente o enfocar su dirección no envía una búsqueda.

## Proveedor y privacidad

Direcciones: **CartoCiudad (IGN/CNIG) · CC BY 4.0**.
Se usa exclusivamente su [geocodificador REST oficial](https://github.com/IDEESpain/Cartociudad#1-candidates)
en `https://www.cartociudad.es/geocoder/api/geocoder/candidates`.
Las nuevas sugerencias necesitan Internet; no hay API key ni coste por llamada
configurado en la aplicación. No se incorpora una suscripción ni otro servidor.

Solo sale del equipo el texto que escribes en Dirección. Código postal, población y
provincia se usan localmente para ordenar las coincidencias, en ese orden. No se
envían el nombre del cliente, NIF, teléfonos, correo, matrícula, notas ni documentos.
No hay telemetría, registro permanente de consultas ni copia del JSON del proveedor.
La caché vive en memoria (192 entradas, 15 minutos); al guardar se usan los campos
normales del cliente. No se guardan coordenadas ni se modifica el esquema SQLite.

La búsqueda es nacional, sin filtro que excluya otras provincias. La preferencia local
ordena los 12 candidatos devueltos por el proveedor y presenta hasta ocho, sin duplicados;
no garantiza que todas las vías locales entren en esos candidatos. Si falta una calle,
añade la localidad al texto o escribe manualmente. Se admiten vías sin número y portales;
no se ofrecen municipios, provincias ni puntos de interés como direcciones postales.

## Comportamiento técnico

`CustomerForm → AddressAutocomplete → servicio Python → CartoCiudad`.
`addresses.search` recibe `query` y opcionalmente `postal_code`, `city`, `province`,
`country` (ES por defecto). Devuelve `{status: "ok" | "unavailable", items: [...]}`;
cada elemento contiene únicamente `id`, `label`, `address`, `postal_code`, `city`,
`province`, `country: "ES"`.

React no contacta con CartoCiudad. Python usa urllib, HTTPS/TLS estándar, cabecera
Accept JSON, límite de 256 KiB y timeout de socket de 2,5 segundos. No acepta URLs
desde RPC ni sigue redirecciones. Un fallo devuelve `unavailable` y una ayuda discreta.

El canal JSONL del escritorio es secuencial. Para liberarlo durante la consulta,
el adaptador Tauri utiliza `addresses.start`, `addresses.result` y `addresses.cancel`:
hasta ocho hilos de consulta, 32 resultados temporales durante 60 segundos y sondeo
local de 150 ms. El formulario deja de esperar a los 12 segundos. Cambiar el texto,
contexto, país o cerrar cancela la espera y descarta resultados tardíos; cancelar no
interrumpe un socket ya iniciado. El preview HTTP usa `addresses.search` directamente
en su hilo, fuera del bloqueo de SQLite. Ninguna ruta de sugerencias accede a SQLite.

## Atribución y comprobación

El formulario y Configuración → Acerca de incluyen la atribución. El inventario de
licencias descargable incorpora `tools/legal/SOURCES.md`, con procedencia y enlaces
a las [condiciones IGN/CNIG](https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf)
y [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.es).

Las pruebas Python inyectan transportes sintéticos; las E2E interceptan las sugerencias
y sustituyen además el transporte Python por uno sin red. No dependen de CartoCiudad.
Resultados ejecutados y límites en `reports/DIRECCIONES-2026-10-07.md`.
