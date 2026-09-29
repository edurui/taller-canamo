"""UBL 2.1 invoices/credit notes with official XSD and CEN EN16931 validation."""
import hashlib
import json
import re
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from lxml import etree
from saxonche import PySaxonProcessor, PySaxonApiError

from .errors import AppError, require
from .money import amount, calculate
from .validation import valid_tax_id

RESOURCES = Path(__file__).resolve().parent/'schemas'/'b2b_ubl21'
CBC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
CAC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
INVOICE = 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'
CREDIT = 'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2'
SVRL = 'http://purl.oclc.org/dsdl/svrl'
MAX_XML = 5_000_000


def resources():
    try:
        manifest = json.loads((RESOURCES/'manifest.json').read_text(encoding='utf-8'))
        for name,metadata in manifest['files'].items():
            path = (RESOURCES/name).resolve()
            require(path.is_relative_to(RESOURCES.resolve()), 'Recurso B2B fuera de su carpeta.', 'b2b_schema')
            require(hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256'],
                    'Recurso de validación B2B alterado: '+name, 'b2b_schema')
        return manifest
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise AppError('No se pueden verificar los recursos oficiales B2B.', 'b2b_schema') from exc


def parse_xml(xml):
    require(isinstance(xml,str) and 0 < len(xml.encode('utf-8')) <= MAX_XML,
            'La factura XML está vacía o supera 5 MB.', 'b2b_xml')
    require('<!DOCTYPE' not in xml.upper() and '<!ENTITY' not in xml.upper(),
            'El XML no admite DTD ni entidades externas.', 'b2b_xml')
    try:
        # The RPC string is already Unicode. Its original encoding declaration
        # must not cause UTF-8 bytes to be decoded again as a legacy encoding.
        content = re.sub(r'^\ufeff?<\?xml[^?]*\?>','',xml).encode('utf-8')
        node = etree.fromstring(content,etree.XMLParser(
            resolve_entities=False,no_network=True,load_dtd=False,remove_comments=True,remove_pis=True))
    except etree.XMLSyntaxError as exc:
        raise AppError('La factura no contiene XML reconocible.', 'b2b_xml') from exc
    require(node.tag in ('{'+INVOICE+'}Invoice','{'+CREDIT+'}CreditNote'),
            'Solo se admiten facturas y notas de crédito UBL 2.1.', 'b2b_xml')
    return node


def decode_file(content):
    require(isinstance(content,bytes) and 0<len(content)<=MAX_XML,'El archivo B2B está vacío o supera 5 MB.','b2b_xml')
    try:
        node = etree.fromstring(content,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,
                                                      remove_comments=False,remove_pis=True))
    except etree.XMLSyntaxError as exc:
        raise AppError('El archivo no contiene XML reconocible.','b2b_xml') from exc
    require(not node.getroottree().docinfo.doctype,'El archivo B2B no admite DTD ni entidades externas.','b2b_xml')
    xml = etree.tostring(node,encoding='UTF-8',xml_declaration=True).decode('utf-8')
    parse_xml(xml)
    return xml


@contextmanager
def validation_session():
    """Compile verified resources once for a bounded batch on the same thread.

    Every XML still passes both validators. No document result or compiled
    resources survive this context, so the next batch verifies hashes again.
    """
    manifest = resources()
    allowed = {str((RESOURCES/path).resolve()) for path in manifest['files'] if path.endswith('.xsd')}
    try:
        with PySaxonProcessor(license=False) as processor:
            processor.set_configuration_property('http://saxon.sf.net/feature/allowedProtocols','#none')
            processor.set_configuration_property('http://saxon.sf.net/feature/allow-external-functions','false')
            xslt = processor.new_xslt30_processor()
            executable = xslt.compile_stylesheet(stylesheet_text=(RESOURCES/'en16931/xslt/EN16931-UBL-validation.xslt').read_text(encoding='utf-8'))
            yield _BatchValidator(processor,executable,allowed)
    except PySaxonApiError as exc:
        raise AppError('No se pudo ejecutar el validador EN16931: '+str(exc)[:600],'b2b_schema') from exc


class _BatchValidator:
    def __init__(self,processor,executable,allowed):
        self.processor,self.executable,self.allowed=processor,executable,allowed
        self.schemas={}

    def validate(self,xml,_root=None):
        root = parse_xml(xml) if _root is None else _root
        name = 'CreditNote' if root.tag == '{'+CREDIT+'}CreditNote' else 'Invoice'
        allowed=self.allowed
        class Resolver(etree.Resolver):
            def resolve(self,url,pubid,context):
                require(url in allowed, 'Dependencia XSD B2B no admitida.', 'b2b_schema')
                return self.resolve_filename(url,context)
        try:
            if name not in self.schemas:
                parser = etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False)
                parser.resolvers.add(Resolver())
                path = RESOURCES/'ubl'/'xsd'/'maindoc'/('UBL-'+name+'-2.1.xsd')
                self.schemas[name]=etree.XMLSchema(etree.parse(str(path.resolve()),parser))
            self.schemas[name].assertValid(root)
        except (etree.DocumentInvalid,etree.XMLSchemaError) as exc:
            raise AppError('La factura no supera el XSD UBL oficial: '+str(exc)[:700],'b2b_xsd') from exc
        try:
            document = self.processor.parse_xml(xml_text=etree.tostring(root,encoding='unicode'))
            report = self.executable.transform_to_string(xdm_node=document)
        except PySaxonApiError as exc:
            raise AppError('No se pudo ejecutar el validador EN16931: '+str(exc)[:600],'b2b_schema') from exc
        report_root = etree.fromstring(report.encode('utf-8'))
        findings = [{'id':item.get('id',''),'severity':item.get('flag','fatal'),
                     'message':''.join(item.find('{'+SVRL+'}text').itertext()).strip(),
                     'location':item.get('location','')} for item in report_root.findall('.//{'+SVRL+'}failed-assert')]
        errors = [item for item in findings if item['severity'] != 'warning']
        return {'ok':not errors,'xsd':'UBL-2.1','semantic':'EN16931-1.3.16','errors':errors,
                'warnings':[item for item in findings if item['severity']=='warning'],
                'svrl':report,'sha256':hashlib.sha256(xml.encode('utf-8')).hexdigest(),
                'network_called':False,'spanish_service_profile_validated':False}


def validate_xml(xml):
    root=parse_xml(xml)
    with validation_session() as validator:
        return validator.validate(xml,_root=root)


def add(parent,name,value=None,ns=CBC,**attributes):
    node = etree.SubElement(parent,'{'+ns+'}'+name,**attributes)
    if value is not None:
        node.text = str(value)
    return node


def decimal_text(value):
    return format(Decimal(value),'f')


def vat_category(kind,rate):
    return 'E' if kind != 'S1' else ('Z' if Decimal(rate)==0 else 'S')


def party(parent,name,data):
    node = add(add(parent,name,ns=CAC),'Party',ns=CAC)
    party_name = data.get('legal_name') or data.get('name') or data.get('trading_name','')
    require(party_name and valid_tax_id(data.get('tax_id','')),'Falta nombre fiscal o NIF válido en una de las partes.','b2b_party')
    require(data.get('address') and data.get('postal_code') and data.get('city'),
            'Completa la dirección fiscal de ambas partes antes de preparar la factura electrónica.','b2b_party')
    require(data.get('country','ES') == 'ES','El generador B2B está configurado para operaciones interiores de España.','b2b_scope')
    add(add(node,'PartyIdentification',ns=CAC),'ID',data['tax_id'])
    add(add(node,'PartyName',ns=CAC),'Name',party_name)
    address = add(node,'PostalAddress',ns=CAC)
    add(address,'StreetName',data['address']);add(address,'CityName',data['city']);add(address,'PostalZone',data['postal_code'])
    if data.get('province'):
        add(address,'CountrySubentity',data['province'])
    add(add(address,'Country',ns=CAC),'IdentificationCode',data.get('country','ES'))
    tax = add(node,'PartyTaxScheme',ns=CAC)
    add(tax,'CompanyID','ES'+data['tax_id']);add(add(tax,'TaxScheme',ns=CAC),'ID','VAT')
    legal = add(node,'PartyLegalEntity',ns=CAC)
    add(legal,'RegistrationName',party_name);add(legal,'CompanyID',data['tax_id'])


def generate(document):
    payload = document['payload']
    corrected = payload.get('invoice_type','F1').startswith('R')
    require(payload.get('tax_adjustments') is None,
            'La rectificación exclusiva de cuota no puede representarse en el perfil EN16931 general con base cero y cuota distinta de cero (BR-S-09/BR-CO-17). Se conserva la factura fiscal; su adaptación B2B requiere el perfil español aplicable.',
            'b2b_tax_only_profile')
    computed = calculate(payload['lines'],corrective=corrected,invoice_type=payload.get('invoice_type','F1'))
    require(all(computed[key] == document[key] for key in ('base_cents','tax_cents','total_cents')),
            'Los importes guardados no coinciden con el cálculo; no se genera B2B.','b2b_integrity')
    credit = corrected and document['total_cents'] < 0
    sign = -1 if credit else 1
    namespace,name = (CREDIT,'CreditNote') if credit else (INVOICE,'Invoice')
    root = etree.Element('{'+namespace+'}'+name,nsmap={None:namespace,'cac':CAC,'cbc':CBC})
    add(root,'UBLVersionID','2.1');add(root,'CustomizationID','urn:cen.eu:en16931:2017')
    add(root,'ID',document['full_number']);add(root,'IssueDate',document['issue_date'])
    if document.get('due_date') and not credit:
        add(root,'DueDate',document['due_date'])
    if credit and payload.get('operation_date'):
        add(root,'TaxPointDate',payload['operation_date'])
    add(root,'CreditNoteTypeCode' if credit else 'InvoiceTypeCode','381' if credit else ('384' if corrected else '380'))
    notes = []
    if payload.get('test_document'):
        notes.append('DOCUMENTO DE PRUEBA SIN VALIDEZ FISCAL')
    if payload.get('notes'):
        notes.append(payload['notes'])
    if payload.get('footer'):
        notes.append(payload['footer'])
    vehicle = payload.get('vehicle') or {}
    if vehicle.get('plate'):
        notes.append('Matrícula: '+vehicle['plate']+'; kilómetros: '+str(payload.get('kilometres',0)))
    if payload.get('fiscal',{}).get('qr_url'):
        notes.append('VERI*FACTU: '+payload['fiscal']['qr_url'])
    if notes:
        add(root,'Note','\n'.join(notes))
    if not credit and payload.get('operation_date'):
        add(root,'TaxPointDate',payload['operation_date'])
    add(root,'DocumentCurrencyCode','EUR')
    if corrected:
        reference = payload.get('reference') or {}
        require(reference.get('full_number') and reference.get('issue_date'),'La rectificativa carece de referencia completa.','b2b_reference')
        original = add(add(root,'BillingReference',ns=CAC),'InvoiceDocumentReference',ns=CAC)
        add(original,'ID',reference['full_number']);add(original,'IssueDate',reference['issue_date'])
    party(root,'AccountingSupplierParty',payload['issuer'])
    party(root,'AccountingCustomerParty',payload['customer'])
    method = payload.get('payment_method','other')
    payment = add(root,'PaymentMeans',ns=CAC)
    # 1 preserves unspecified instruments; a credit transfer needs its real account.
    add(payment,'PaymentMeansCode',{'cash':'10','card':'48','transfer':'30'}.get(method,'1'))
    if method == 'transfer':
        require(payload['issuer'].get('iban'),'La transferencia necesita el IBAN de la factura emitida.','b2b_payment')
        add(add(payment,'PayeeFinancialAccount',ns=CAC),'ID',payload['issuer']['iban'])
    terms = add(root,'PaymentTerms',ns=CAC)
    add(terms,'Note',('Vencimiento: '+document['due_date']) if document.get('due_date') else 'Pago según las condiciones acordadas en la factura.')
    groups = {}
    for line in computed['lines']:
        require(line['tax_kind'] not in ('E2','E3','E5'),'Este generador no admite ese régimen de exención.','b2b_scope')
        category = vat_category(line['tax_kind'],line['tax_rate'])
        key = category,line['tax_rate']
        group = groups.setdefault(key,{'base':0,'reasons':set()})
        group['base'] += line['base_cents']*sign
        if line['tax_reason']:
            group['reasons'].add(line['tax_reason'])
    tax_total = add(root,'TaxTotal',ns=CAC)
    add(tax_total,'TaxAmount',amount(document['tax_cents']*sign),currencyID='EUR')
    for (category,rate),group in sorted(groups.items()):
        subtotal = add(tax_total,'TaxSubtotal',ns=CAC)
        add(subtotal,'TaxableAmount',amount(group['base']),currencyID='EUR')
        from .money import cents
        tax = cents(Decimal(group['base'])/100*Decimal(rate)/100) if category == 'S' else 0
        add(subtotal,'TaxAmount',amount(tax),currencyID='EUR')
        classified = add(subtotal,'TaxCategory',ns=CAC)
        add(classified,'ID',category);add(classified,'Percent',rate)
        if category == 'E':
            add(classified,'TaxExemptionReason','; '.join(sorted(group['reasons'])))
        add(add(classified,'TaxScheme',ns=CAC),'ID','VAT')
    totals = add(root,'LegalMonetaryTotal',ns=CAC)
    for key,value in [('LineExtensionAmount','base_cents'),('TaxExclusiveAmount','base_cents'),
                      ('TaxInclusiveAmount','total_cents'),('PayableAmount','total_cents')]:
        add(totals,key,amount(document[value]*sign),currencyID='EUR')
    for index,line in enumerate(computed['lines'],1):
        node = add(root,'CreditNoteLine' if credit else 'InvoiceLine',ns=CAC)
        add(node,'ID',index)
        quantity = Decimal(line['quantity'])*sign
        price = Decimal(line['unit_price'])
        if price < 0:
            quantity,price = -quantity,-price
        add(node,'CreditedQuantity' if credit else 'InvoicedQuantity',decimal_text(quantity),unitCode='C62')
        add(node,'LineExtensionAmount',amount(line['base_cents']*sign),currencyID='EUR')
        item = add(node,'Item',ns=CAC);add(item,'Name',line['description'])
        classified = add(item,'ClassifiedTaxCategory',ns=CAC)
        add(classified,'ID',vat_category(line['tax_kind'],line['tax_rate']));add(classified,'Percent',line['tax_rate'])
        add(add(classified,'TaxScheme',ns=CAC),'ID','VAT')
        price_node = add(node,'Price',ns=CAC)
        net = price*(1-Decimal(line['discount'])/100)
        add(price_node,'PriceAmount',decimal_text(net),currencyID='EUR')
        add(price_node,'BaseQuantity','1',unitCode='C62')
        if Decimal(line['discount']):
            allowance = add(price_node,'AllowanceCharge',ns=CAC)
            add(allowance,'ChargeIndicator','false')
            add(allowance,'Amount',decimal_text(price-net),currencyID='EUR')
            add(allowance,'BaseAmount',decimal_text(price),currencyID='EUR')
    return etree.tostring(root,encoding='UTF-8',xml_declaration=True,pretty_print=True).decode('utf-8')


def identity(xml):
    root = parse_xml(xml)
    ns = {'cbc':CBC,'cac':CAC}
    def text(path):
        return root.findtext(path,namespaces=ns) or ''
    seller = text('cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID') or text('cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:CompanyID')
    buyer = text('cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID') or text('cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:CompanyID')
    total = Decimal(text('cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount'))*100
    require(total == total.to_integral_value(),'La factura contiene fracciones de céntimo en su total.','b2b_amount')
    return {'issuer_nif':seller,'recipient_nif':buyer,'invoice_number':text('cbc:ID'),
            'issue_date':text('cbc:IssueDate'),'currency':text('cbc:DocumentCurrencyCode'),
            'total_cents':int(total)*(-1 if root.tag=='{'+CREDIT+'}CreditNote' else 1),
            'test_document':'DOCUMENTO DE PRUEBA SIN VALIDEZ FISCAL' in text('cbc:Note')}
