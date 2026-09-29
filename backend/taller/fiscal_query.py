"""Official consultation XML and conservative comparison with an immutable send.

A consultation is evidence of current registry content, not a reconstructed CSV.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from .errors import AppError, require
from .fiscal import BASE, SF, LR, SOAP, child, validate_official_xml

QUERY = BASE+'ConsultaLR.xsd'
QUERY_RESPONSE = BASE+'RespuestaConsultaLR.xsd'
ET.register_namespace('con',QUERY)


def period(data):
    date = datetime.strptime(data.get('operation_date') or data['date'],'%d-%m-%Y')
    return str(date.year), f'{date.month:02d}'


def xml_query(data, cursor=None):
    envelope = ET.Element('{'+SOAP+'}Envelope')
    message = child(child(envelope,'Body',ns=SOAP),'ConsultaFactuSistemaFacturacion',ns=QUERY)
    header = child(message,'Cabecera',ns=QUERY)
    child(header,'IDVersion','1.0')
    issuer = child(header,'ObligadoEmision')
    child(issuer,'NombreRazon',data['issuer_name']); child(issuer,'NIF',data['issuer_nif'])
    filters = child(message,'FiltroConsulta',ns=QUERY)
    tax_period = child(filters,'PeriodoImputacion',ns=QUERY)
    year, month = period(data)
    child(tax_period,'Ejercicio',year); child(tax_period,'Periodo',month)
    child(filters,'NumSerieFactura',data['number'],ns=QUERY)
    dates = child(filters,'FechaExpedicionFactura',ns=QUERY)
    child(dates,'FechaExpedicionFactura',data['date'])
    if cursor:
        page = child(filters,'ClavePaginacion',ns=QUERY)
        for key in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura'):
            child(page,key,cursor[key])
    additional = child(message,'DatosAdicionalesRespuesta',ns=QUERY)
    child(additional,'MostrarNombreRazonEmisor','S',ns=QUERY)
    child(additional,'MostrarSistemaInformatico','S',ns=QUERY)
    xml = ET.tostring(envelope,encoding='unicode',xml_declaration=True)
    validate_official_xml(xml,'ConsultaLR.xsd',QUERY,'ConsultaFactuSistemaFacturacion')
    return xml


def _text(node, name, ns=QUERY_RESPONSE):
    found = node.find('{'+ns+'}'+name) if node is not None else None
    return (found.text or '').strip() if found is not None else ''


def parse_query_response(raw, expected):
    root = validate_official_xml(raw,'RespuestaConsultaLR.xsd',QUERY_RESPONSE,
                                'RespuestaConsultaFactuSistemaFacturacion','transport')
    header = root.find('{'+QUERY_RESPONSE+'}Cabecera')
    issuer = header.find('{'+SF+'}ObligadoEmision')
    require(_text(issuer,'NIF',SF) == expected['issuer_nif'], 'Consulta de otro emisor.', 'transport')
    tax_period = root.find('{'+QUERY_RESPONSE+'}PeriodoImputacion')
    require((_text(tax_period,'Ejercicio'),_text(tax_period,'Periodo')) == period(expected),
            'La respuesta de consulta corresponde a otro período.', 'transport')
    rows = root.findall('{'+QUERY_RESPONSE+'}RegistroRespuestaConsultaFactuSistemaFacturacion')
    result = _text(root,'ResultadoConsulta')
    require((result=='ConDatos') == bool(rows), 'Resultado y filas de consulta incoherentes.', 'transport')
    for row in rows:
        identity = row.find('{'+QUERY_RESPONSE+'}IDFactura')
        actual = tuple(_text(identity,name,SF) for name in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura'))
        require(actual == (expected['issuer_nif'],expected['number'],expected['date']),
                'La consulta devuelve una identidad distinta de la solicitada.', 'transport')
    cursor = None
    if _text(root,'IndicadorPaginacion') == 'S':
        page = root.find('{'+QUERY_RESPONSE+'}ClavePaginacion')
        require(page is not None and bool(rows), 'Paginación de consulta incompleta.', 'transport')
        cursor = {name:_text(page,name,SF) for name in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura')}
    return rows,cursor


NUMERICAL = {'CuotaTotal','ImporteTotal','TipoImpositivo','BaseImponibleOimporteNoSujeto',
             'CuotaRepercutida','TipoRecargoEquivalencia','CuotaRecargoEquivalencia',
             'BaseImponibleACoste','BaseRectificada','CuotaRectificada'}


def _semantic(node):
    name = node.tag.rsplit('}',1)[-1]
    children = [x for x in node if isinstance(x.tag,str)]
    if children:
        return name,tuple(_semantic(x) for x in children)
    value = (node.text or '').strip()
    try:
        if name in NUMERICAL:
            value = Decimal(value)
            require(value.is_finite(), 'Importe no finito en la consulta.', 'transport')
        elif name == 'FechaHoraHusoGenRegistro':
            stamp = datetime.fromisoformat(value)
            require(stamp.utcoffset() is not None, 'La consulta omite el huso horario del registro.', 'transport')
            value = stamp.astimezone(timezone.utc).isoformat()
    except (ValueError, InvalidOperation) as exc:
        raise AppError('Formato no interpretable en la consulta: '+name, 'transport') from exc
    return name,value


def compare_query_record(row, request_xml, kind):
    request = validate_official_xml(request_xml)
    local = request.find('{'+LR+'}RegistroFactura')[0]
    remote = row.find('{'+QUERY_RESPONSE+'}DatosRegistroFacturacion')
    fields = ['RefExterna','Encadenamiento','SistemaInformatico','FechaHoraHusoGenRegistro','TipoHuella','Huella']
    if kind != 'anulacion':
        fields += ['NombreRazonEmisor','TipoFactura','TipoRectificativa','FacturasRectificadas',
                   'FechaOperacion','DescripcionOperacion','Destinatarios','Desglose','CuotaTotal','ImporteTotal']
    differences = []
    for name in fields:
        left = local.find('{'+SF+'}'+name)
        right = remote.find('{'+QUERY_RESPONSE+'}'+name)
        if left is None:
            if right is not None:
                differences.append(name)
        elif right is None or _semantic(left) != _semantic(right):
            differences.append(name)
    for name in ('Subsanacion','RechazoPrevio','SinRegistroPrevio'):
        if (_text(local,name,SF) or 'N') != (_text(remote,name) or 'N'):
            differences.append(name)
    state = row.find('{'+QUERY_RESPONSE+'}EstadoRegistro')
    remote_state = _text(state,'EstadoRegistro')
    if (remote_state == 'Anulado') != (kind == 'anulacion'):
        differences.append('EstadoRegistro')
    presentation = row.find('{'+QUERY_RESPONSE+'}DatosPresentacion')
    request_id = _text(presentation,'IdPeticion',SF)
    if not request_id:
        differences.append('IdPeticion')
    if differences:
        return {'status':'reconciliation_conflict','differences':differences,
                'error':'La consulta no coincide con el registro local: '+', '.join(differences),
                'remote_state':remote_state,'remote_request_id':request_id}
    return {'status':'accepted_with_errors' if remote_state=='AceptadoConErrores' else 'accepted',
            'verified_by':'query','remote_state':remote_state,'remote_request_id':request_id,
            'error':(_text(state,'CodigoErrorRegistro')+' '+_text(state,'DescripcionErrorRegistro')).strip(),
            'csv_recovered':False}
