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

Usar las fuentes actuales del 29/09/2026: el ZIP del 23/09 no contiene esta revisión visual.
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

## Archivo Access original

Obtener una copia cerrada del MDB/ACCDB y conservar el original intacto. Seguir
`docs/IMPORTACION-ACCESS.md`: diagnóstico → perfil de origen/mapeo → incidencias → simulación
→ importación por lotes → conciliación → ensayo de rollback. Confirmar relaciones/claves,
IVA y cobros realmente conservados; los datos ausentes siguen siendo desconocidos.
El corte final de emisión y la serie nueva se acuerdan expresamente; no se deducen de una
foto o del número máximo importado. El importador nativo y el paquete alternativo ya tienen
implementación y pruebas con bases sintéticas.

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
