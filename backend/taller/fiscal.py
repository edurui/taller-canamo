"""VERI*FACTU sandbox adapter. Production is deliberately not released.

Official schemas are bundled, fingerprinted and validated without network access.
Sources and review evidence: docs/FISCAL-FUENTES-2026-09-23.md.
Local unit tests do NOT establish conformity or replace external acceptance.
"""
import hashlib
import json
import os
import re
import ssl
import tempfile
import threading
import urllib.request
import urllib.error
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from lxml import etree
from . import __version__
from .db import dumps, uid
from .errors import AppError, require
from .money import amount, canonical_tax_rate
from .validation import TZ, now, valid_tax_id

BASE = 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/'
SF, LR, RESPONSE = BASE+'SuministroInformacion.xsd', BASE+'SuministroLR.xsd', BASE+'RespuestaSuministro.xsd'
SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
TEST_ENDPOINT = 'https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP'
PRODUCTION_ENDPOINT = 'https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP'
SPEC_BASE = 'https://prewww2.aeat.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/'
BUNDLED_SCHEMA_DIR = Path(__file__).resolve().parent/'schemas'/'aeat_1_0'
SCHEMA_FILES = ('SistemaFacturacion.wsdl', 'SuministroLR.xsd', 'SuministroInformacion.xsd',
                'RespuestaSuministro.xsd', 'ConsultaLR.xsd', 'RespuestaConsultaLR.xsd',
                'xmldsig-core-schema.xsd')
XMLDSIG_URL = 'https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd'
MAX_XML_BYTES = 2_000_000
# Retained for older integrations; changing this symbol has no release effect.
# Eligibility now comes from the embedded build policy plus verified evidence.
PRODUCTION_RELEASED = False
ET.register_namespace('soapenv', SOAP)
ET.register_namespace('sum', LR)
ET.register_namespace('sf', SF)


def schema_manifest():
    """Return the reviewed manifest; downloaded files never replace this trust root."""
    try:
        manifest = json.loads((BUNDLED_SCHEMA_DIR/'manifest.json').read_text(encoding='utf-8'))
        require(set(manifest['files']) == set(SCHEMA_FILES), 'Manifiesto fiscal incompleto.', 'schema')
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AppError('Faltan los esquemas oficiales del paquete. Reinstala la aplicación.', 'schema') from exc


def verify_schema_files(folder=None):
    """Verify the exact reviewed bytes before any XSD is compiled."""
    folder = Path(folder) if folder is not None else BUNDLED_SCHEMA_DIR
    manifest = schema_manifest()
    try:
        for name in SCHEMA_FILES:
            content = (folder/name).read_bytes()
            require(hashlib.sha256(content).hexdigest() == manifest['files'][name]['sha256'],
                    'Esquema oficial modificado o incompleto: '+name, 'schema')
    except OSError as exc:
        raise AppError('Falta un esquema oficial del paquete: '+str(exc.filename), 'schema') from exc
    return manifest


def official_schema(name):
    require(name in SCHEMA_FILES and name.endswith('.xsd'), 'Esquema no admitido.', 'schema')
    verify_schema_files()
    folder = BUNDLED_SCHEMA_DIR.resolve()
    # Do not let a schema import read arbitrary files or contact a network host.
    allowed = {str(folder/filename): folder/filename for filename in SCHEMA_FILES}
    allowed[XMLDSIG_URL] = folder/'xmldsig-core-schema.xsd'
    allowed[XMLDSIG_URL.replace('https:', 'http:', 1)] = folder/'xmldsig-core-schema.xsd'

    class Resolver(etree.Resolver):
        def resolve(self, url, pubid, context):
            require(url in allowed, 'Importación de esquema no admitida: '+url, 'schema')
            return self.resolve_filename(str(allowed[url]), context)

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    parser.resolvers.add(Resolver())
    try:
        return etree.XMLSchema(etree.parse(str(folder/name), parser))
    except (etree.XMLSchemaError, etree.XMLSyntaxError, OSError) as exc:
        raise AppError('No se puede cargar el esquema oficial: '+str(exc)[:600], 'schema') from exc


def _soap_message(xml, namespace, name, error_code='schema'):
    require(isinstance(xml, str) and len(xml.encode('utf-8')) <= MAX_XML_BYTES
            and '<!DOCTYPE' not in xml.upper() and '<!ENTITY' not in xml.upper(),
            'XML fiscal no seguro.', error_code)
    try:
        root = etree.fromstring(xml.encode('utf-8'), etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False))
    except etree.XMLSyntaxError as exc:
        raise AppError('XML fiscal no reconocible.', error_code) from exc
    require(root.tag == '{'+SOAP+'}Envelope', 'Falta el sobre SOAP fiscal.', error_code)
    bodies = root.findall('{'+SOAP+'}Body')
    require(len(bodies) == 1, 'El XML fiscal no contiene un único cuerpo SOAP.', error_code)
    elements = [element for element in bodies[0] if isinstance(element.tag, str)]
    require(len(elements) == 1, 'El cuerpo SOAP fiscal debe contener un único mensaje.', error_code)
    message = elements[0]
    if message.tag == '{'+SOAP+'}Fault':
        raise AppError('SOAP: '+''.join(message.itertext())[:1500], 'transport')
    require(message.tag == '{'+namespace+'}'+name, 'Tipo de mensaje fiscal inesperado.', error_code)
    return message


def validate_official_xml(xml, schema_name='SuministroLR.xsd', namespace=LR,
                          message_name='RegFactuSistemaFacturacion', error_code='schema'):
    message = _soap_message(xml, namespace, message_name, error_code)
    try:
        official_schema(schema_name).assertValid(message)
    except etree.DocumentInvalid as exc:
        raise AppError('El XML no supera el esquema oficial: '+str(exc)[:600], error_code) from exc
    return message


def child(parent, name, value=None, ns=SF):
    element = ET.SubElement(parent, '{'+ns+'}'+name)
    if value is not None:
        element.text = str(value)
    return element


def fiscal_hash(data: dict, previous_hash='', kind='alta') -> str:
    require(kind in ('alta', 'subsanacion', 'anulacion'), 'Tipo de registro fiscal no admitido.')
    if kind == 'anulacion':
        fields = [('IDEmisorFacturaAnulada',data['issuer_nif']), ('NumSerieFacturaAnulada',data['number']),
                  ('FechaExpedicionFacturaAnulada',data['date']), ('Huella',previous_hash), ('FechaHoraHusoGenRegistro',data['timestamp'])]
    else:
        fields = [('IDEmisorFactura',data['issuer_nif']), ('NumSerieFactura',data['number']),
                  ('FechaExpedicionFactura',data['date']), ('TipoFactura',data['type']), ('CuotaTotal',data['tax']),
                  ('ImporteTotal',data['total']), ('Huella',previous_hash), ('FechaHoraHusoGenRegistro',data['timestamp'])]
    preimage = '&'.join(f'{key}={str(value).strip()}' for key,value in fields)
    return hashlib.sha256(preimage.encode('utf-8')).hexdigest().upper()


def qr_url(data, environment='aeat_test'):
    # Pure formatting only. append/correct enforce the runtime release gate
    # before storing a production record; constructing a URL sends no request.
    require(environment in ('local_test','aeat_test','production'), 'Entorno fiscal no admitido.')
    require(re.fullmatch(r'[\x20-\x7e]{1,60}', data['number']),
            'La serie y número deben tener entre 1 y 60 caracteres ASCII imprimibles.')
    host = 'www2.agenciatributaria.gob.es' if environment=='production' else 'prewww2.aeat.es'
    return 'https://'+host+'/wlpl/TIKE-CONT/ValidarQR?' + urlencode({'nif':data['issuer_nif'], 'numserie':data['number'], 'fecha':data['date'], 'importe':data['total']})


def xml_record(data: dict, previous: dict | None = None, kind='alta') -> tuple[str,str]:
    try:
        timestamp = datetime.fromisoformat(data['timestamp'])
        require(timestamp.utcoffset() is not None, 'La fecha del registro fiscal debe incluir su huso horario.')
    except (ValueError, TypeError) as exc:
        raise AppError('La fecha del registro fiscal no es válida.') from exc
    if previous:
        require(re.fullmatch(r'[0-9A-F]{64}', previous['hash']), 'La huella anterior no es válida.')
    digest = fiscal_hash(data, previous['hash'] if previous else '', kind)
    envelope = ET.Element('{'+SOAP+'}Envelope')
    body = child(envelope,'Body',ns=SOAP)
    message = child(body,'RegFactuSistemaFacturacion',ns=LR)
    header = child(message,'Cabecera',ns=LR)
    issuer = child(header,'ObligadoEmision')
    child(issuer,'NombreRazon',data['issuer_name']); child(issuer,'NIF',data['issuer_nif'])
    record = child(message,'RegistroFactura',ns=LR)
    row = child(record, 'RegistroAnulacion' if kind == 'anulacion' else 'RegistroAlta')
    child(row,'IDVersion','1.0')
    identity = child(row,'IDFactura')
    suffix = 'Anulada' if kind == 'anulacion' else ''
    child(identity,'IDEmisorFactura'+suffix,data['issuer_nif'])
    child(identity,'NumSerieFactura'+suffix,data['number'])
    child(identity,'FechaExpedicionFactura'+suffix,data['date'])
    child(row,'RefExterna',data['document_id'])
    if kind != 'anulacion':
        child(row,'NombreRazonEmisor',data['issuer_name'])
        if kind == 'subsanacion':
            child(row,'Subsanacion','S')
            rejection = data.get('rejection_previous', 'N')
            require(rejection in ('N','S','X'), 'Rechazo previo de subsanación no válido.')
            if rejection != 'N':
                child(row,'RechazoPrevio',rejection)
        child(row,'TipoFactura',data['type'])
        if data['type'].startswith('R'):
            child(row,'TipoRectificativa','I')
            reference = child(child(row,'FacturasRectificadas'),'IDFacturaRectificada')
            child(reference,'IDEmisorFactura',data['reference'].get('issuer_nif',data['issuer_nif']))
            child(reference,'NumSerieFactura',data['reference']['number'])
            child(reference,'FechaExpedicionFactura',data['reference']['date'])
        if data.get('operation_date'):
            child(row,'FechaOperacion',data['operation_date'])
        child(row,'DescripcionOperacion',data['description'][:500])
        person = child(child(row,'Destinatarios'),'IDDestinatario')
        child(person,'NombreRazon',data['customer_name']); child(person,'NIF',data['customer_nif'])
        breakdown = child(row,'Desglose')
        for tax in data['taxes']:
            detail = child(breakdown,'DetalleDesglose')
            child(detail,'Impuesto','01'); child(detail,'ClaveRegimen','01')
            if tax['kind'] == 'S1':
                child(detail,'CalificacionOperacion','S1')
                child(detail,'TipoImpositivo',tax['rate'])
                child(detail,'BaseImponibleOimporteNoSujeto',amount(tax['base_cents']))
                child(detail,'CuotaRepercutida',amount(tax['tax_cents']))
            else:
                child(detail,'OperacionExenta',tax['kind'])
                child(detail,'BaseImponibleOimporteNoSujeto',amount(tax['base_cents']))
        child(row,'CuotaTotal',data['tax']); child(row,'ImporteTotal',data['total'])
    else:
        no_previous = data.get('no_previous_record', 'N')
        rejection = data.get('rejection_previous', 'N')
        require(no_previous in ('N','S') and rejection in ('N','S'), 'Indicadores de anulación no válidos.')
        if no_previous != 'N':
            child(row,'SinRegistroPrevio',no_previous)
        if rejection != 'N':
            child(row,'RechazoPrevio',rejection)
    chain = child(row,'Encadenamiento')
    if previous:
        last = child(chain,'RegistroAnterior')
        child(last,'IDEmisorFactura',previous['issuer_nif']); child(last,'NumSerieFactura',previous['number'])
        child(last,'FechaExpedicionFactura',previous['date']); child(last,'Huella',previous['hash'])
    else:
        child(chain,'PrimerRegistro','S')
    system = child(row,'SistemaInformatico')
    producer = data['producer']
    child(system,'NombreRazon',producer['name']); child(system,'NIF',producer['nif'])
    child(system,'NombreSistemaInformatico','El Canamo Taller')
    child(system,'IdSistemaInformatico',producer['system_id']); child(system,'Version',producer.get('version',__version__))
    child(system,'NumeroInstalacion',producer['installation_id'])
    child(system,'TipoUsoPosibleSoloVerifactu','S'); child(system,'TipoUsoPosibleMultiOT','N'); child(system,'IndicadorMultiplesOT','N')
    child(row,'FechaHoraHusoGenRegistro',data['timestamp']); child(row,'TipoHuella','01'); child(row,'Huella',digest)
    return ET.tostring(envelope,encoding='unicode',xml_declaration=True), digest


def parse_response(raw: str, expected: dict, kind='alta') -> dict:
    root = validate_official_xml(raw, 'RespuestaSuministro.xsd', RESPONSE,
                                'RespuestaRegFactuSistemaFacturacion', 'transport')
    def text(node, name, ns=RESPONSE):
        found = node.find('{'+ns+'}'+name)
        return (found.text or '').strip() if found is not None else ''
    rows = root.findall('{'+RESPONSE+'}RespuestaLinea')
    require(len(rows) == 1, 'Respuesta sin una l\u00ednea identificable. Se mantiene pendiente de verificaci\u00f3n.', 'transport')
    row = rows[0]
    identity = row.find('{'+RESPONSE+'}IDFactura')
    nif = text(identity,'IDEmisorFactura',SF)
    number = text(identity,'NumSerieFactura',SF)
    date = text(identity,'FechaExpedicionFactura',SF)
    require((nif,number,date) == (expected['issuer_nif'],expected['number'],expected['date']), 'La respuesta no corresponde a la factura enviada.', 'transport')
    header = root.find('{'+RESPONSE+'}Cabecera')
    issuer = header.find('{'+SF+'}ObligadoEmision')
    require(text(issuer,'NIF',SF) == expected['issuer_nif'], 'La respuesta no corresponde al emisor enviado.', 'transport')
    operation = row.find('{'+RESPONSE+'}Operacion')
    require(text(operation,'TipoOperacion',SF) == ('Anulacion' if kind == 'anulacion' else 'Alta'),
            'La respuesta no corresponde a la operación enviada.', 'transport')
    expected_subsanation = 'S' if kind == 'subsanacion' else 'N'
    require((text(operation,'Subsanacion',SF) or 'N') == expected_subsanation,
            'La respuesta no corresponde a la subsanación enviada.', 'transport')
    require((text(operation,'RechazoPrevio',SF) or 'N') == expected.get('rejection_previous','N')
            and (text(operation,'SinRegistroPrevio',SF) or 'N') == expected.get('no_previous_record','N'),
            'La respuesta no corresponde a los indicadores enviados.', 'transport')
    if text(row,'RefExterna'):
        require(text(row,'RefExterna') == expected.get('document_id'),
                'La respuesta no corresponde a la referencia enviada.', 'transport')
    state = text(row,'EstadoRegistro')
    status = {'Correcto':'accepted','AceptadoConErrores':'accepted_with_errors','Incorrecto':'rejected'}.get(state)
    require(status is not None, 'Estado de respuesta no reconocido.', 'transport')
    overall = text(root,'EstadoEnvio')
    compatible = {'Correcto': ('Correcto',), 'AceptadoConErrores': ('ParcialmenteCorrecto',),
                  'Incorrecto': ('Incorrecto',)}
    require(overall in compatible[state], 'Estados de respuesta fiscal incoherentes.', 'transport')
    if status in ('accepted','accepted_with_errors'):
        require(bool(text(root,'CSV')), 'Aceptación sin CSV. Es necesario verificar el resultado.', 'transport')
    duplicate = row.find('{'+RESPONSE+'}RegistroDuplicado')
    if duplicate is not None:
        require(state == 'Incorrecto', 'Respuesta de duplicado incoherente.', 'transport')
        status = 'duplicate_review'
    wait = text(root,'TiempoEsperaEnvio')
    require(wait.isascii() and wait.isdigit() and 0 <= int(wait) <= 9999,
            'Tiempo de espera de AEAT no válido. Se conserva el resultado pendiente de verificación.', 'transport')
    result = {'status':status,'csv':text(root,'CSV'),'error': (text(row,'CodigoErrorRegistro')+' '+text(row,'DescripcionErrorRegistro')).strip(),
              'wait': max(1,int(wait))}
    if duplicate is not None:
        result['duplicate'] = {'request_id':text(duplicate,'IdPeticionRegistroDuplicado',SF),
                               'state':text(duplicate,'EstadoRegistroDuplicado',SF),
                               'error_code':text(duplicate,'CodigoErrorRegistro',SF),
                               'error':text(duplicate,'DescripcionErrorRegistro',SF)}
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AppError('Se ha rechazado una redirecci\u00f3n del servicio fiscal.', 'transport')


def validate_business(data, kind):
    """Checks for the invoice types and Spanish general VAT regime we generate."""
    require(valid_tax_id(data['issuer_nif']), 'El NIF del emisor no es válido.')
    require(re.fullmatch(r'[\x20-\x7e]{1,60}', data['number'])
            and not any(char in data['number'] for char in '\"\'<>='),
            'La numeración contiene caracteres no admitidos por AEAT.')
    if kind == 'anulacion':
        return
    require(data['type'] in ('F1','R1','R2','R3','R4'), 'Tipo de factura fuera del alcance configurado.')
    require(valid_tax_id(data['customer_nif']), 'El NIF del destinatario no es válido.')
    require(len(data['description'].strip()) > 0, 'El registro fiscal necesita una descripción.')
    if data.get('operation_date'):
        try:
            operation=datetime.strptime(data['operation_date'],'%d-%m-%Y').date()
            issued=datetime.strptime(data['date'],'%d-%m-%Y').date()
        except (ValueError,TypeError) as exc:
            raise AppError('La fecha de operación fiscal no es válida.','operation_date') from exc
        require(operation<=issued,'La fecha de operación fiscal es posterior a la expedición.','operation_date')
    for detail in data['taxes']:
        require(detail['kind'] not in ('E2','E3','E5'),
                'La exención '+detail['kind']+' requiere régimen o identificación internacional que esta configuración aún no admite. No se ha emitido el documento.',
                'unsupported_tax_regime')
        require(detail['kind'] in ('S1','E1','E4','E6'), 'Tratamiento fiscal no admitido.')
        if detail['kind'] == 'S1':
            canonical_tax_rate(detail['rate'])
    tax = sum(x['tax_cents'] for x in data['taxes'])
    total = tax + sum(x['base_cents'] for x in data['taxes'])
    require(Decimal(data['tax']) == Decimal(tax)/100 and Decimal(data['total']) == Decimal(total)/100,
            'El desglose fiscal no coincide con los importes de la factura.')


def _xml_values(element):
    """Expanded QNames and values, independent of prefixes and indentation."""
    return (element.tag, tuple(sorted(element.attrib.items())), (element.text or '').strip(),
            tuple(_xml_values(item) for item in element if isinstance(item.tag,str)))


def validate_stored_record(row, previous=None):
    data = json.loads(row['payload'])
    actual = validate_official_xml(row['xml'])
    # Version 1 did not persist the producer version separately. Preserve the
    # version inside its immutable XML instead of substituting today's version.
    if not data['producer'].get('version'):
        data['producer']['version'] = actual.findtext('.//{'+SF+'}SistemaInformatico/{'+SF+'}Version')
    expected_xml, expected_hash = xml_record(data,previous,row['kind'])
    expected = validate_official_xml(expected_xml)
    require(row['hash'] == expected_hash and row['previous_hash'] == (previous['hash'] if previous else ''),
            'La huella del registro no coincide con su cadena fiscal.', 'integrity')
    require(_xml_values(actual) == _xml_values(expected),
            'El XML fiscal no coincide con los datos inmutables del registro.', 'integrity')
    return data


class Fiscal:
    def __init__(self, db, settings, certificates):
        self.db,self.settings,self.certificates = db,settings,certificates
        self.send_lock = threading.Lock()
        self.spec_dir = db.root/'secure'/'aeat-specs'
        self.spec_dir.mkdir(exist_ok=True)

    def _channel(self, conn, environment):
        stamp = now()
        conn.execute('INSERT OR IGNORE INTO fiscal_channels(environment,next_allowed_at,updated_at) VALUES(?,?,?)',
                     (environment,stamp,stamp))
        return conn.execute('SELECT * FROM fiscal_channels WHERE environment=?',(environment,)).fetchone()

    def _append_data(self, conn, document_id, data, kind, environment, key,
                     correction_of_id=None, reason=''):
        validate_business(data,kind)
        last = conn.execute('SELECT hash,payload FROM fiscal_records WHERE environment=? ORDER BY seq DESC LIMIT 1',(environment,)).fetchone()
        previous = {**json.loads(last['payload']),'hash':last['hash']} if last else None
        xml,digest = xml_record(data,previous,kind)
        self.validate_schema(xml)
        identifier = uid()
        conn.execute('''INSERT INTO fiscal_records(id,document_id,kind,environment,payload,xml,hash,
            previous_hash,created_at,correction_of_id,idempotency_key,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (identifier,document_id,kind,environment,dumps(data),xml,digest,previous['hash'] if previous else '',
             now(),correction_of_id,key,reason))
        channel = self._channel(conn,environment)
        next_attempt = max(now(),channel['next_allowed_at'])
        conn.execute('INSERT INTO fiscal_outbox(record_id,status,next_attempt,updated_at) VALUES(?,?,?,?)',
                     (identifier,'local_only' if environment=='local_test' else 'pending',next_attempt,now()))
        return {'hash':digest,'record_id':identifier,'qr_url':qr_url(data,environment),'environment':environment}

    def append(self, conn, document, payload, kind='alta', reason=''):
        from .backups import assert_restore_allows_emission
        assert_restore_allows_emission(self.db)
        config = self.settings.get(conn)
        mode = config['fiscal']['mode']
        require(mode in ('local_test','aeat_test','production'), 'Entorno fiscal no admitido.')
        if mode == 'production':
            self._endpoint(mode)
        key = 'document:'+document['id']+':'+kind
        existing = conn.execute('SELECT id,hash,environment,payload FROM fiscal_records WHERE idempotency_key=?',(key,)).fetchone()
        if existing:
            return {'hash':existing['hash'],'record_id':existing['id'],'qr_url':qr_url(json.loads(existing['payload']),existing['environment']),
                    'environment':existing['environment']}
        if mode != 'local_test':
            require(config['fiscal']['producer_name'] and valid_tax_id(config['fiscal']['producer_tax_id']), 'Configura la identidad real del productor antes de enviar a pruebas AEAT.', 'setup')
            require(self.certificates.path.exists(), 'Falta configurar el certificado digital.', 'setup')
        issuer = payload['issuer']
        data = {'issuer_nif':issuer['tax_id'],'issuer_name':issuer['legal_name'] or issuer['trading_name'],
                'number':document['full_number'],'date':datetime.fromisoformat(document['issue_date']).strftime('%d-%m-%Y'),
                'type':payload.get('invoice_type','F1'),'tax':amount(document['tax_cents']),'total':amount(document['total_cents']),
                'timestamp':datetime.now(TZ).isoformat(timespec='seconds'),'document_id':document['id'],
                'description':payload.get('notes') or '; '.join(x['description'] for x in payload['lines']),
                'customer_name':payload['customer']['name'],'customer_nif':payload['customer']['tax_id'],
                'taxes':payload['taxes'],
                'producer':{'name':config['fiscal']['producer_name'] or 'DESARROLLO LOCAL NO VALIDADO',
                            'nif':config['fiscal']['producer_tax_id'] or issuer['tax_id'],
                            'system_id':config['fiscal']['system_id'],'installation_id':config['fiscal']['installation_id'],
                            'version':__version__}}
        if payload.get('operation_date'):
            data['operation_date']=datetime.fromisoformat(payload['operation_date']).strftime('%d-%m-%Y')
        if document.get('reference_id'):
            ref = conn.execute('SELECT full_number,issue_date,payload FROM documents WHERE id=?',(document['reference_id'],)).fetchone()
            original_issuer = json.loads(ref['payload']).get('issuer',{}).get('tax_id') or data['issuer_nif']
            data['reference'] = {'issuer_nif':original_issuer, 'number':ref['full_number'],
                                 'date':datetime.fromisoformat(ref['issue_date']).strftime('%d-%m-%Y')}
        parent = None
        if kind == 'anulacion':
            prior = conn.execute('''SELECT r.*,o.status FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
                WHERE r.document_id=? AND r.environment=? ORDER BY r.seq DESC LIMIT 1''',(document['id'],mode)).fetchone()
            require(prior is not None, 'No hay un registro de alta local que anular.')
            require(prior['status'] in ('local_only','accepted','accepted_with_errors','rejected'),
                    'Resuelve primero el resultado del envío original antes de anular su registro.', 'fiscal_pending')
            parent = prior['id']
            if prior['status'] == 'rejected':
                data['no_previous_record'] = 'S' if not self._remote_exists(conn,document['id'],mode) else 'N'
        return self._append_data(conn,document['id'],data,kind,mode,key,parent,reason)

    @staticmethod
    def _remote_exists(conn, document_id, environment):
        return bool(conn.execute('''SELECT 1 FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
            WHERE r.document_id=? AND r.environment=? AND o.status IN ('accepted','accepted_with_errors') LIMIT 1''',
            (document_id,environment)).fetchone())

    def correct(self, record_id, changes, reason, idempotency_key):
        from .backups import assert_restore_allows_emission
        assert_restore_allows_emission(self.db)
        require(isinstance(changes,dict), 'Los datos de subsanación no son válidos.')
        allowed = {'issuer_name','customer_name','customer_nif','description'}
        require(set(changes) <= allowed,
                'La subsanación de registro no modifica importes, numeración, fecha ni impuestos. Emite una rectificativa cuando proceda.',
                'requires_rectification')
        require(isinstance(reason,str) and 3 <= len(reason.strip()) <= 1500, 'Describe el motivo de la subsanación.')
        require(isinstance(idempotency_key,str) and 1 <= len(idempotency_key) <= 200, 'Falta una clave de operación válida.')
        clean = {}
        for key,value in changes.items():
            require(isinstance(value,str), 'El dato a subsanar debe ser texto.')
            value = value.strip()
            limit = 500 if key == 'description' else (9 if key == 'customer_nif' else 120)
            require(0 < len(value) <= limit, 'Longitud no válida para '+key+'.')
            clean[key] = value.upper() if key == 'customer_nif' else value
        fingerprint = hashlib.sha256(dumps({'record_id':record_id,'changes':clean,'reason':reason.strip()}).encode()).hexdigest()
        with self.db.transaction() as conn:
            existing = conn.execute('SELECT id,payload FROM fiscal_records WHERE idempotency_key=?',('correction:'+idempotency_key,)).fetchone()
            if existing:
                require(json.loads(existing['payload']).get('_request_fingerprint') == fingerprint,
                        'La clave de operación ya identifica otra subsanación.', 'conflict')
                return self._details(conn,existing['id'])
            prior = conn.execute('''SELECT r.*,o.status FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
                WHERE r.id=?''',(record_id,)).fetchone()
            require(prior is not None, 'Registro fiscal no encontrado.', 'not_found')
            latest = conn.execute('SELECT id FROM fiscal_records WHERE document_id=? AND environment=? ORDER BY seq DESC LIMIT 1',
                                  (prior['document_id'],prior['environment'])).fetchone()
            require(latest['id'] == record_id, 'Hay un registro posterior; abre su detalle para corregirlo.', 'conflict')
            require(prior['status'] in ('local_only','accepted','accepted_with_errors','rejected','invalid_local'),
                    'Consulta y resuelve el resultado pendiente antes de generar una subsanación.', 'fiscal_pending')
            require(prior['environment'] == self.settings.get(conn)['fiscal']['mode'], 'Selecciona el entorno original del registro.')
            data = {**json.loads(prior['payload']), **clean}
            data['timestamp'] = datetime.now(TZ).isoformat(timespec='seconds')
            producer = self.settings.get(conn)['fiscal']
            data['producer'] = {'name':producer['producer_name'] or data['producer']['name'],
                                'nif':producer['producer_tax_id'] or data['producer']['nif'],
                                'system_id':producer['system_id'],'installation_id':producer['installation_id'],
                                'version':__version__}
            if prior['environment'] == 'production':
                self._endpoint('production')
            data['_request_fingerprint'] = fingerprint
            data.pop('rejection_previous',None)
            data.pop('no_previous_record',None)
            rejected = prior['status'] in ('rejected','invalid_local')
            remote_exists = self._remote_exists(conn,prior['document_id'],prior['environment'])
            kind = 'anulacion' if prior['kind'] == 'anulacion' else 'subsanacion'
            if kind == 'anulacion':
                require(rejected, 'La anulación ya consta aceptada; solo se subsanan anulaciones rechazadas o inválidas.')
                require(not clean, 'La anulación se subsana con sus indicadores; no contiene datos comerciales.')
                data['rejection_previous'] = 'S' if rejected else 'N'
                data['no_previous_record'] = 'N' if remote_exists else 'S'
            else:
                require(clean, 'Indica al menos un dato a subsanar.')
                data['rejection_previous'] = ('S' if remote_exists else 'X') if rejected else 'N'
            result = self._append_data(conn,prior['document_id'],data,kind,prior['environment'],
                                       'correction:'+idempotency_key,record_id,reason.strip())
            if prior['status'] == 'invalid_local':
                conn.execute("UPDATE fiscal_outbox SET status='superseded',updated_at=? WHERE record_id=?",(now(),record_id))
            self.db.audit(conn,'fiscal.correct',result['record_id'],{'correction_of_id':record_id,'reason':reason.strip()})
            return self._details(conn,result['record_id'])

    def _details(self, conn, record_id):
        row = conn.execute('''SELECT r.*,o.status,o.attempts,o.next_attempt,o.last_error,o.csv,o.response
            FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id WHERE r.id=?''',(record_id,)).fetchone()
        require(row is not None, 'Registro fiscal no encontrado.', 'not_found')
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        result['attempt_history'] = [dict(x) for x in conn.execute('SELECT * FROM fiscal_attempts WHERE record_id=? ORDER BY created_at,rowid',(record_id,))]
        result['reconciliations'] = [dict(x) for x in conn.execute('SELECT * FROM fiscal_reconciliations WHERE record_id=? ORDER BY created_at,rowid',(record_id,))]
        result['corrections'] = [dict(x) for x in conn.execute('SELECT id,kind,reason,created_at FROM fiscal_records WHERE correction_of_id=? ORDER BY seq',(record_id,))]
        return result

    def details(self, record_id):
        with self.db.read() as conn:
            return self._details(conn,record_id)

    def records(self):
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute('SELECT r.seq,r.id,r.document_id,r.kind,r.environment,r.hash,r.created_at,o.status,o.attempts,o.last_error,o.csv,d.full_number FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id JOIN documents d ON d.id=r.document_id ORDER BY r.seq DESC LIMIT 300')]

    def download_specs(self):
        # Static official schemas are public. This request never loads or sends a
        # client certificate, including to W3C, and rejects redirects.
        manifest = verify_schema_files()
        public = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(
            context=ssl.create_default_context()))
        with tempfile.TemporaryDirectory(prefix='download-', dir=self.spec_dir) as temp:
            staging = Path(temp)
            for name in SCHEMA_FILES:
                url = XMLDSIG_URL if name == 'xmldsig-core-schema.xsd' else SPEC_BASE+name
                with public.open(url, timeout=30) as response:
                    content = response.read(MAX_XML_BYTES+1)
                require(len(content) <= MAX_XML_BYTES, 'Esquema oficial demasiado grande.', 'schema')
                require(hashlib.sha256(content).hexdigest() == manifest['files'][name]['sha256'],
                        'Ha cambiado el esquema oficial '+name+'. Requiere revisión y una actualización de la aplicación; no se activa automáticamente.',
                        'schema_update')
                (staging/name).write_bytes(content)
            downloaded_manifest = {**manifest, 'downloaded_at':now()}
            (staging/'manifest.json').write_text(dumps(downloaded_manifest), encoding='utf-8')
            for name in (*SCHEMA_FILES, 'manifest.json'):
                os.replace(staging/name, self.spec_dir/name)
        return {'downloaded':list(SCHEMA_FILES), 'verified':True,
                'reviewed_on':manifest['reviewed_on']}

    def validate_schema(self, xml):
        validate_official_xml(xml)
        return True

    def readiness(self):
        return self._readiness(self.settings.get())

    def _readiness(self,config):
        # Private entry for Settings' candidate configuration. The public RPC
        # method takes no arguments, so callers cannot supply an invented config.
        from .fiscal_release import verify_release_dossier,build_policy
        fiscal = config['fiscal']
        certificate = fiscal.get('certificate_info') or {}
        problems = []
        if not (config['company']['legal_name'] and valid_tax_id(config['company']['tax_id'])):
            problems.append({'code':'issuer','message':'Configura la identidad fiscal del emisor.'})
        if not (fiscal['producer_name'] and valid_tax_id(fiscal['producer_tax_id'])):
            problems.append({'code':'producer','message':'Identifica al productor del programa.'})
        if not fiscal.get('declaration_text','').strip():
            problems.append({'code':'declaration','message':'Falta la declaración responsable de esta versión.'})
        if not self.certificates.path.exists():
            problems.append({'code':'certificate','message':'Instala el certificado autorizado en este equipo.'})
        else:
            try:
                expiry = datetime.fromisoformat(certificate['expires'])
                require(expiry.utcoffset() is not None and expiry > datetime.now(timezone.utc), 'Certificado no vigente.')
            except (KeyError,ValueError,TypeError,AppError):
                problems.append({'code':'certificate_expiry','message':'Verifica la vigencia y metadatos del certificado.'})
        try:
            verify_schema_files()
        except AppError as exc:
            problems.append({'code':'schemas','message':str(exc)})
        chain = self.verify_chain()
        if not chain['ok']:
            problems.append({'code':'chain','message':'La cadena local tiene una incidencia de integridad.'})
        policy=build_policy()
        if not policy['candidate_build']:
            problems.append({'code':'release','message':policy['error']})
        release = verify_release_dossier(self.db,config)
        if not release['ok']:
            problems.append({'code':'release_evidence','message':release['error']})
        return {'production_ready':not problems,'problems':problems,'chain':chain,
                'test_endpoint':TEST_ENDPOINT,'production_endpoint':PRODUCTION_ENDPOINT,
                'network_called':False,'version':__version__,'release_evidence':release,'build_policy':policy}

    def _endpoint(self, environment):
        if environment == 'aeat_test':
            return TEST_ENDPOINT
        require(environment == 'production', 'No se realizan envíos desde el entorno local.', 'setup')
        readiness = self.readiness()
        require(readiness['production_ready'], 'Producción bloqueada: '+ '; '.join(x['message'] for x in readiness['problems']), 'production_blocked')
        return PRODUCTION_ENDPOINT

    def _transport(self, xml, environment):
        endpoint = self._endpoint(environment)
        try:
            context = self.certificates.context()
            fingerprint=getattr(context,'_canamo_certificate_fingerprint','')
            require(re.fullmatch('[0-9A-F]{64}',fingerprint),
                    'No se puede identificar el certificado del contexto TLS. Reinstálalo.','setup')
        except (AppError,OSError,ValueError) as exc:
            raise AppError('No se ha iniciado el envío: '+str(exc), 'setup') from exc
        opener = urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request(endpoint,data=xml.encode('utf-8'),
            headers={'Content-Type':'text/xml; charset=UTF-8','SOAPAction':'""'},method='POST')
        try:
            with opener.open(request,timeout=30) as response:
                raw = response.read(MAX_XML_BYTES+1)
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_XML_BYTES+1)
            if not raw:
                raise
        require(len(raw) <= MAX_XML_BYTES, 'Respuesta fiscal demasiado grande.', 'transport')
        return raw.decode('utf-8'),fingerprint

    def _recover(self, conn):
        stamp = now()
        # A live lease cannot be discarded just because another App object starts.
        conn.execute('''UPDATE fiscal_outbox SET status='uncertain',
            last_error='Envío interrumpido; se consultará el resultado antes de reenviar.',updated_at=?
            WHERE status='sending' AND NOT EXISTS (
              SELECT 1 FROM fiscal_channels c WHERE c.claimed_record_id=fiscal_outbox.record_id
              AND c.claim_token!='' AND c.claim_until>?)''',(stamp,stamp))
        conn.execute("UPDATE fiscal_channels SET claimed_record_id=NULL,claim_token='',claim_until='',updated_at=? WHERE claim_until<=?",(stamp,stamp))

    def recover_interrupted(self):
        with self.db.transaction() as conn:
            self._recover(conn)

    def _claim(self, conn, row, query=False):
        channel = self._channel(conn,row['environment'])
        stamp = now()
        if channel['claim_token'] and channel['claim_until'] > stamp:
            return {'status':'busy'}
        due = max(channel['next_allowed_at'],row['next_attempt'])
        if due > stamp:
            return {'status':'idle','reason':'waiting','next_attempt':due,'record_id':row['id']}
        token = uid()
        expiry = (datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat(timespec='seconds')
        conn.execute('''UPDATE fiscal_channels SET claimed_record_id=?,claim_token=?,claim_until=?,updated_at=?
            WHERE environment=?''',(row['id'],token,expiry,stamp,row['environment']))
        if not query:
            conn.execute("UPDATE fiscal_outbox SET status='sending',attempts=attempts+1,updated_at=? WHERE record_id=?",(stamp,row['id']))
        return {'token':token}

    def _exchange(self, xml, environment, transport):
        if transport is not None:
            return transport(xml),None
        raw,fingerprint = self._transport(xml,environment)
        # Only this branch opens the real mTLS transport. Injected responses never
        # produce release evidence, even when they are schema-valid acceptances.
        return raw,{'endpoint':TEST_ENDPOINT if environment=='aeat_test' else PRODUCTION_ENDPOINT,'request_sha256':hashlib.sha256(xml.encode()).hexdigest(),
                    'response_sha256':hashlib.sha256(raw.encode()).hexdigest(),'certificate_fingerprint':fingerprint}

    def _finish(self, row, token, result, raw='', queries=None, wires=None):
        with self.db.transaction() as conn:
            channel = self._channel(conn,row['environment'])
            require(channel['claim_token'] == token, 'El intento ha perdido su reserva; consulta el registro antes de continuar.', 'fiscal_pending')
            next_time = (datetime.now(timezone.utc)+timedelta(seconds=result.get('wait',60))).isoformat(timespec='seconds')
            next_time = max(next_time,channel['next_allowed_at'])
            csv = result.get('csv') or row.get('csv','')
            conn.execute('''UPDATE fiscal_outbox SET status=?,last_error=?,csv=?,response=?,next_attempt=?,updated_at=? WHERE record_id=?''',
                (result['status'],result.get('error',''),csv,raw or row.get('response',''),next_time,now(),row['id']))
            conn.execute('''UPDATE fiscal_channels SET next_allowed_at=?,claimed_record_id=NULL,
                claim_token='',claim_until='',updated_at=? WHERE environment=?''',(next_time,now(),row['environment']))
            conn.execute('''UPDATE fiscal_outbox SET next_attempt=? WHERE record_id IN
                (SELECT id FROM fiscal_records WHERE environment=?) AND status IN ('pending','retry','uncertain','duplicate_review')
                AND next_attempt<?''',(next_time,row['environment'],next_time))
            if queries is None:
                evidence_id = uid()
                conn.execute('INSERT INTO fiscal_attempts(id,record_id,status,response,created_at) VALUES(?,?,?,?,?)',
                             (evidence_id,row['id'],result['status'],raw,now()))
                evidence_ids = [evidence_id]
            else:
                evidence_ids = []
                for request_xml,response_xml in queries:
                    evidence_id = uid()
                    conn.execute('INSERT INTO fiscal_reconciliations VALUES(?,?,?,?,?,?)',
                        (evidence_id,row['id'],request_xml,response_xml,dumps(result),now()))
                    evidence_ids.append(evidence_id)
            for evidence_id,wire in zip(evidence_ids,wires or []):
                if wire:
                    conn.execute('INSERT INTO fiscal_wire_evidence VALUES(?,?,?,?,?,?,?,?,?)',
                        (uid(),row['id'],evidence_id,'query' if queries is not None else 'supply',wire['endpoint'],
                         wire['request_sha256'],wire['response_sha256'],wire['certificate_fingerprint'],now()))
            self.db.audit(conn,'fiscal.reconcile' if queries is not None else 'fiscal.response',row['id'],
                          {'status':result['status'],'remote_request_id':result.get('remote_request_id','')})
        return {**result,'record_id':row['id'],'next_attempt':next_time}

    def _submit(self, row, token, transport):
        raw, attempted, wire = '',False,None
        try:
            with self.db.read() as conn:
                prior = conn.execute('SELECT payload,hash FROM fiscal_records WHERE environment=? AND seq<? ORDER BY seq DESC LIMIT 1',
                                     (row['environment'],row['seq'])).fetchone()
            previous = {**json.loads(prior['payload']),'hash':prior['hash']} if prior else None
            data = validate_stored_record(row,previous)
            validate_business(data,row['kind'])
            attempted = True
            raw,wire = self._exchange(row['xml'],row['environment'],transport)
            result = parse_response(raw,data,row['kind'])
        except (AppError,urllib.error.URLError,TimeoutError,OSError,UnicodeError,ValueError,KeyError,TypeError) as exc:
            state = 'uncertain' if attempted else 'invalid_local'
            if isinstance(exc,AppError) and exc.code in ('setup','production_blocked'):
                state = 'retry'
            result = {'status':state,'csv':'','error':str(exc)[:1500],
                      'wait':min(3600,60*2**min(row['attempts'],6))}
        return self._finish(row,token,result,raw,wires=[wire])

    def _query(self, row, token, transport):
        from .fiscal_query import xml_query,parse_query_response,compare_query_record
        data = json.loads(row['payload'])
        queries, wires, rows, seen = [],[],[],set()
        cursor = None
        try:
            for _ in range(100):
                request_xml = xml_query(data,cursor)
                queries.append((request_xml,''))
                wires.append(None)
                raw,wire = self._exchange(request_xml,row['environment'],transport)
                queries[-1] = (request_xml,raw)
                wires[-1] = wire
                page,cursor = parse_query_response(raw,data)
                rows.extend(page)
                if not cursor:
                    break
                key = dumps(cursor)
                require(key not in seen, 'La consulta repite su clave de paginación.', 'transport')
                seen.add(key)
                with self.db.transaction() as conn:
                    expiry = (datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat(timespec='seconds')
                    changed = conn.execute('UPDATE fiscal_channels SET claim_until=? WHERE environment=? AND claim_token=?',
                                           (expiry,row['environment'],token)).rowcount
                    require(changed == 1, 'La consulta ha perdido su reserva.', 'transport')
            else:
                raise AppError('La consulta excede 100 páginas; resultado no confirmado.', 'transport')
            require(len(rows) <= 1, 'La consulta devuelve varias versiones para la misma identidad.', 'transport')
            if rows:
                result = compare_query_record(rows[0],row['xml'],row['kind'])
                if (result['status'] == 'reconciliation_conflict' and row['correction_of_id']
                        and row['status'] not in ('accepted','accepted_with_errors')):
                    with self.db.read() as conn:
                        predecessors = conn.execute('''SELECT r.* FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
                            WHERE r.document_id=? AND r.environment=? AND r.seq<? AND o.status IN ('accepted','accepted_with_errors')
                            ORDER BY r.seq DESC''',(row['document_id'],row['environment'],row['seq'])).fetchall()
                    for previous in predecessors:
                        try:
                            match = compare_query_record(rows[0],previous['xml'],previous['kind'])
                        except AppError:
                            continue
                        if match['status'] in ('accepted','accepted_with_errors'):
                            result = {'status':'retry','verified_by':'query','previous_record_id':previous['id'],
                                      'remote_request_id':match['remote_request_id'],
                                      'error':'La consulta conserva el registro anterior. Se reenviará esta corrección sin alterar su XML.'}
                            break
                if result['status'] == 'reconciliation_conflict' and row['status'] in ('accepted','accepted_with_errors'):
                    with self.db.read() as conn:
                        successors = conn.execute('''SELECT r.* FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
                            WHERE r.document_id=? AND r.environment=? AND r.seq>? AND o.status IN ('accepted','accepted_with_errors')
                            ORDER BY r.seq DESC''',(row['document_id'],row['environment'],row['seq'])).fetchall()
                    for newer in successors:
                        match = compare_query_record(rows[0],newer['xml'],newer['kind'])
                        if match['status'] in ('accepted','accepted_with_errors'):
                            # The old acknowledgement remains true. Consultation
                            # describes the latest version, so it cannot replace it.
                            result = {'status':row['status'],'verified_by':'query_history',
                                      'current_record_id':newer['id'],'remote_request_id':match['remote_request_id'],
                                      'error':'La consulta coincide con una versión posterior ya aceptada; se conserva el acuse histórico.'}
                            break
            elif row['status'] in ('accepted','accepted_with_errors'):
                result = {'status':'reconciliation_conflict','error':'La consulta no encuentra un registro previamente aceptado.'}
            else:
                # Absence is not acceptance. Re-submit the existing immutable XML
                # only after the consultation and the global wait have completed.
                result = {'status':'retry','error':'Registro no encontrado en la consulta. Se reenviará el mismo XML.',
                          'verified_by':'query','query_result':'not_found'}
        except (AppError,urllib.error.URLError,TimeoutError,OSError,UnicodeError,ValueError,KeyError,TypeError) as exc:
            status = row['status'] if row['status'] in ('accepted','accepted_with_errors','reconciliation_conflict') else 'uncertain'
            result = {'status':status,'error':'Consulta sin resultado verificable: '+str(exc)[:1400]}
        return self._finish(row,token,result,queries=queries,wires=wires)

    def send_next(self, transport=None):
        if not self.send_lock.acquire(blocking=False):
            return {'status':'busy'}
        try:
            mode = self.settings.get()['fiscal']['mode']
            if mode == 'local_test':
                return {'status':'idle'}
            self._endpoint(mode)
            with self.db.transaction() as conn:
                self._recover(conn)
                row = conn.execute('''SELECT r.*,o.status,o.attempts,o.next_attempt,o.csv,o.response
                    FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id
                    WHERE r.environment=? AND o.status IN
                    ('pending','retry','uncertain','duplicate_review','sending','invalid_local','reconciliation_conflict')
                    ORDER BY r.seq LIMIT 1''',(mode,)).fetchone()
                if not row:
                    return {'status':'idle'}
                row = dict(row)
                if row['status'] in ('invalid_local','reconciliation_conflict'):
                    return {'status':row['status'],'record_id':row['id'],'reason':'Revisa el registro antes de continuar la cola.'}
                query = row['status'] in ('uncertain','duplicate_review')
                if not query:
                    from .backups import assert_restore_allows_emission
                    assert_restore_allows_emission(self.db)
                claim = self._claim(conn,row,query)
                if 'token' not in claim:
                    return claim
            return self._query(row,claim['token'],transport) if query else self._submit(row,claim['token'],transport)
        finally:
            self.send_lock.release()

    def reconcile(self, record_id, transport=None):
        if not self.send_lock.acquire(blocking=False):
            return {'status':'busy'}
        try:
            with self.db.transaction() as conn:
                self._recover(conn)
                row = conn.execute('''SELECT r.*,o.status,o.attempts,o.next_attempt,o.csv,o.response
                    FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id WHERE r.id=?''',(record_id,)).fetchone()
                require(row is not None, 'Registro fiscal no encontrado.', 'not_found')
                row = dict(row)
                require(row['environment'] in ('aeat_test','production'), 'El registro local no está destinado a AEAT.')
                self._endpoint(row['environment'])
                require(row['status'] not in ('pending','local_only','sending'), 'El registro aún no tiene un resultado de envío que consultar.')
                claim = self._claim(conn,row,query=True)
                if 'token' not in claim:
                    return claim
            return self._query(row,claim['token'],transport)
        finally:
            self.send_lock.release()

    def verify_chain(self):
        last,checked = {},0
        with self.db.read() as conn:
            for row in conn.execute('SELECT * FROM fiscal_records ORDER BY seq'):
                try:
                    data = validate_stored_record(row,last.get(row['environment']))
                except (AppError,ValueError,KeyError,TypeError) as exc:
                    return {'ok':False,'record':row['id'],'checked':checked,'error':str(exc)[:600]}
                last[row['environment']] = {**data,'hash':row['hash']}
                checked += 1
        return {'ok':True,'checked':checked}
