# Comprobaciones externas para la puesta en marcha

Especificación principal: `PROMPT_MAESTRO_TALLER_CANAMO.md`. Consultar primero
`docs/ESTADO-VERIFICADO.md`: allí consta qué versión de las pruebas/artefactos se ejecutó.
La edición de desarrollo conserva sus avisos de prueba y no debe usarse para facturar
operativamente. Los siguientes pasos requieren medios o datos que no están disponibles
en este entorno; no son instrucciones para volver a programar los módulos.

## Windows e impresión

En Windows 11 x64 de desarrollo, seguir `docs/BUILD-WINDOWS.md`: dependencias fijadas,
construcción completa y, para el ensayo de puesta en marcha, `--release-candidate`.
Instalar y ensayar el candidato exacto en una cuenta/VM limpia: actualización/reinstalación,
DPAPI, instancia única, cierre/bandeja/notificaciones, copias/restauración y una impresora.
Registrar resultados reales y hashes. El workflow preparado es manual; no se ha publicado
ni ejecutado en un runner remoto. No desactivar antivirus o SmartScreen.

Usar las fuentes actuales del 06/10/2026: el ZIP del 23/09 no contiene la revisión visual
ni la migración del Access real.
Comprobar también los tres tamaños de letra con las escalas de Windows, los selectores y
calendarios a pantalla completa en ventana estrecha, el cierre de modales anidados y el
orden de líneas en la vista previa/lector PDF. La evidencia Linux y de navegador está en
`reports/MEJORAS-INTERFAZ-2026-09-29.md`; no sustituye esa prueba de WebView2.

## Certificado, emisor y productor

Instalar mediante el selector local un certificado legítimo del titular/representante;
configurar identidades confirmadas y revisar la declaración responsable. Ejecutar solamente
el ensayo autorizado AEAT en el entorno oficial de pruebas, conforme a
`docs/FISCAL-LIBERACION-2026-09-23.md`. Conservar altas, subsanaciones, anulaciones y consultas
con sus respuestas auténticas. No adjuntar certificado, contraseña, XML identificativos o
expediente privado al repositorio ni al chat.

La aplicación valida el expediente contra los intercambios reales, versión, esquemas y
bytes del servicio ensayado. Instalarlo con la CLI documentada, comprobar el diagnóstico y
activar producción solo después de completar todas las verificaciones. Una constante,
un checkbox o un acuse sintético no autorizan la activación. No reconstruir el binario
después de ensayarlo sin repetir la verificación correspondiente.

## Access real: ensayo local de 06/10/2026

Los dos originales ya se han investigado sin modificarlos. Informe principal:
`reports/ACCESS-REAL-2026-10-06.md`; análisis estructural y VBA en los informes enlazados.
No volver a aplicar el requisito antiguo de totales completos a este MDB: usar el perfil
sugerido de conservación parcial y la relación postal. Los importes desconocidos son
NULL/«No consta», no cero; no reconstruir todo el archivo al 21 %.

Resultados conciliados: 1.595 clientes, 1.290 vehículos, 5.133 históricos y 19.335 líneas.
Se conservan las 27.621 filas raw. Quedan para revisión 18 clientes, 222 referencias
de vehículos, 70 registros/candidatos de histórico y 326 líneas sin atribución segura;
38 históricos importados tienen fecha conflictiva y 45 carecen de fecha. Son conflictos
reales preservados, no aceptación fiscal ni un corte de producción.

Para revisar al volver, abrir el ensayo aislado que indica el informe, desde el proyecto:

```bash
source .venv/bin/activate
python scripts/run_preview.py --data "$HOME/.canamo-access-codex-rehearsal-20261006-b"
```

Configuración → Traer datos → lote del ensayo → motivos agrupados, registros originales
y conciliación. Los ensayos A y C fueron revertidos y conservan evidencia; B queda importado para
inspección local. No usar ninguno como carpeta operativa. La carpeta de diagnóstico
anterior `.canamo-access-prueba` se ha conservado.

Quien conoce el taller debe acreditar las titularidades de 105 matrículas compartidas,
las identidades incompletas y, si se quiere completar el histórico monetario, aportar
documentos impresos/periodos/criterios de redondeo verificables. El código recuperado del
informe no acredita por sí solo lo que se imprimió en cada época. No es necesario resolver
estas cuestiones para consultar los registros importados con sus datos desconocidos.

El corte final y la última factura en Access siguen requiriendo confirmación física con
el propietario. Obtener entonces una copia cerrada reciente, revisar diferencias con el
mismo origen/perfil y acordar la serie nueva por separado. No se deduce del máximo importado.

## Contrato público B2B

Revisar la publicación definitiva del perfil/servicio público de intercambio y sus pruebas
oficiales, según `docs/B2B-FUENTES-2026-09-23.md`. UBL 2.1, validación real EN16931, recepción,
conservación, estados y exportación funcionan localmente; ello no acredita entrega a un
servicio cuyo contrato final no se ha localizado. VERI*FACTU y B2B mantienen estados separados.

## Copia o traslado a otro equipo

Usar `docs/COPIAS-TRASLADO.md` y el manual `LEEME.md`. No copiar SQLite mientras está abierta
ni sincronizar la base activa. El traslado autorizado inactiva la emisión del origen y
requiere activación del destino; restaurar una copia antigua no autoriza retroceder series
o repetir envíos. Reinstalar el certificado en el nuevo usuario/equipo cuando proceda.
