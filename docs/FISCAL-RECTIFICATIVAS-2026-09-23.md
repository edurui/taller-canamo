# Fecha de operación y rectificación exclusiva de IVA — 23/09/2026

## Fuentes y decisión de alcance

La [AEAT, procedimientos de facturación VERI*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/procedimientos-facturacion.html)
indica que la rectificativa conserva la fecha de operación original. Su ejemplo 3 por
diferencias describe una factura con base 1.000 y cuota 210, corregida mediante R2/R3 con
base cero, cuota −210 y total −210. Se implementa ese supuesto explícito, con importes
introducidos y revisados por el usuario.

El [manual IVA de AEAT, pregunta 5](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/manual-iva-2025/capitulo-04-sujetos-pasivos-repercusion-impositivo/cuestiones-frecuentes-planteadas-capitulo.html)
y el [artículo 90.2 de la LIVA](https://www.boe.es/buscar/act.php?id=BOE-A-1992-28740#a90)
vinculan el tipo aplicable al devengo original. Sin embargo, las
[validaciones VERI*FACTU 1.2.2, apartado 15.1](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Validaciones_Errores_Veri-Factu.pdf)
enumeran para IVA S1 únicamente 0, 2, 4, 5, 7,5, 10 y 21; algunos con ventanas de fecha.
No se ha localizado allí una excepción para 18/8/16/7 en rectificativas.

Por tanto, se conservan esos tipos históricos en la importación y se bloquea su emisión
con `unsupported_historical_tax_rate`, explicando el contrato que limita el caso. No se
sustituyen por 21 ni se cambia el impuesto/régimen para eludir la regla. El hecho de que
un XSD numérico admita 18 no acredita aceptación del servicio. Los tipos temporales
2/5/7,5 siguen fuera del alcance de emisión configurado para este taller.

## Implementación y contrato local

`documents.save` conserva `operation_date` ISO; por defecto coincide con expedición en
documentos nuevos. `documents.rectify` copia la fecha de operación conservada. Para una
factura emitida por versiones anteriores que no guardaron una fecha distinta se conserva
el comportamiento previo de misma fecha. Un histórico sin fecha de operación requiere
introducirla expresamente desde la evidencia original.

El campo se serializa como `FechaOperacion` en VERI*FACTU y se compara en reconciliación.
La consulta usa su período; AEAT describe el filtro de año/mes por operación y, si falta,
por expedición en su [guía de consulta](https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/presentacion-declaraciones-ayuda-tecnica/aplicacion-gratuita-verifactu-aeat/consulta-facturas.html).
En UBL normal se conserva como `TaxPointDate`, respetando el orden diferente de Invoice
y CreditNote que exigen sus XSD.

Ejemplo de creación local de borrador R3, sin envío:

```json
{
  "identifier": "id-de-la-factura-original",
  "reason": "Causa y evidencia de la rectificación comprobadas por el usuario",
  "invoice_type": "R3",
  "operation_date": "2024-09-30",
  "tax_adjustments": [{"tax_rate": "21", "tax_cents": -21000}]
}
```

La API admite `operation_date=None` y `tax_adjustments=None` para los casos ordinarios.
R2/R3 requieren las cuotas explícitas; R1/R4 siguen utilizando líneas normales. Si se
omite `lines` en una corrección exclusiva de cuota, se crean conceptos descriptivos con
precio y base cero. Se permite editar su descripción. Su finalidad se conserva mediante
`correction_mode: "tax_only"` y `tax_adjustments` en el snapshot.

La vista previa usa `documents.calculate(lines, corrective, invoice_type, tax_adjustments)`.
No deriva una cuota distinta de la solicitada ni inventa una base para producirla. Se
rechazan flotantes, cuotas nulas, tipos repetidos, artículos, descuentos y movimientos de
stock en ese modo.

Guardar y publicar verifican de nuevo las cuotas disponibles por tipo en la familia de
facturas y correcciones ya emitidas. Dos borradores no pueden consumir dos veces la misma
cuota; el segundo fallo no avanza la serie. Una rectificación posterior puede revertir
la reducción documentada, sin borrar antecedentes. Una devolución comercial posterior
debe resolver la cuota ya rectificada para evitar descontarla otra vez.

Cuando el histórico carece de desglose por tipo, no se deduce del total ni de una tasa
actual. Hay que obtener y mapear el desglose documentado de origen. No se modifica el
snapshot antiguo para hacer posible una corrección ni se presenta este control como una
resolución jurídica de los requisitos, causas o plazos de recuperación del IVA.

Los saldos se calculan sobre el total de la nueva rectificativa. El original y sus cobros
permanecen intactos; registrar la rectificativa no inventa un cobro/devolución bancaria.
PDF e interfaz muestran fecha de operación y modo de cuota con sus totales propios.

### Anulación y documentos relacionados

La anulación comprueba toda la descendencia de rectificativas dentro de la misma
transacción. Si queda una emitida, histórica o en borrador, devuelve
`rectifications_exist` con sus identificadores y estados. Hay que revisar las emitidas
y eliminar los borradores que no deban continuar. No se anulan ni borran automáticamente
otros documentos. Una rectificativa ya anulada no bloquea al original; sus sucesoras
todavía vigentes sí lo hacen. La comprobación también cubre crear una rectificativa y
anular su original desde conexiones concurrentes.

El detalle expone `active_rectifications` para explicar el bloqueo en la interfaz.
Las relaciones presupuesto → orden → factura conservan cliente, vehículo y origen;
se validan al guardar, convertir y publicar. `conversion_identity_locked` indica que
esos campos pertenecen a un conjunto enlazado. Los documentos independientes mantienen
su edición normal. Se conserva la reutilización de la factura existente y el control
de movimientos de stock.

## Límite B2B demostrado con el validador

Las [reglas generales CEN EN16931](https://github.com/ConnectingEurope/eInvoicing-EN16931/blob/validation-1.3.16/ubl/schematron/abstract/EN16931-model.sch)
BR-S-09/BR-CO-17 relacionan la cuota con base y tipo. El test construye un candidato UBL
con base cero y cuota no nula: pasa estructura, pero el XSLT oficial devuelve esas reglas.

La generación B2B de este caso se detiene con `b2b_tax_only_profile`, conserva la factura
fiscal y explica que necesita el tratamiento aplicable del perfil español. No se rebajan
reglas, se inventa una exención o se atribuye cumplimiento por disponer de un XML. Esta
limitación es distinta de la implementación local R2/R3 de VERI*FACTU, que sí queda
serializada y validada. Véase `B2B-FUENTES-2026-09-23.md`.

## Evidencia

`tests/test_rectification_tax.py` reproduce el vector monetario publicado por AEAT,
fecha distinta, rectificación sucesiva, competencia entre borradores, conservación de
original, límites por tipo, consulta discordante y fallo semántico B2B real.
La suite integrada posterior pasó **330 pruebas** en 27,96 segundos:
`reports/pytest-rectification-integrated-2026-09-23.xml`.

Una ejecución anterior detectó dos fallos XSD al colocar `TaxPointDate` de CreditNote
como en Invoice; se corrigió su orden sin alterar el esquema ni los validadores.
No hubo autenticación AEAT, confirmación externa, datos personales ni uso de producción.

Después de ese hito, `tests/test_document_relations_audit.py` añade las regresiones de
anulación y conversión. Su ejecución conjunta con integridad, rectificación y flujos
pasó 77 casos en 3,59 s (`reports/pytest-document-relations-corrected-2026-09-23.xml`).
Es una comprobación dirigida posterior; no sustituye la batería final conjunta.
