"""Offline checks with official AEAT XSDs and independent published hash vectors.

Only the three hash vectors and QR example are official examples. Response XML
and workshop records below are synthetic fixtures, never AEAT acknowledgements.
"""
import io
import json
import shutil
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest

from taller import fiscal
from taller.errors import AppError
from taller.validation import now, today


# AEAT "Detalle de las especificaciones técnicas para generación de la huella",
# v0.1.2 (27/08/2024), sections 6.1, 6.2 and 6.3, pages 10, 11 and 12.
# https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf
HASH_1 = '3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60'
HASH_2 = 'F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97'
HASH_3 = '177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68'


@pytest.mark.parametrize('number,timestamp,previous,kind,expected', [
    ('12345678/G33', '2024-01-01T19:20:30+01:00', '', 'alta', HASH_1),
    ('12345679/G34', '2024-01-01T19:20:35+01:00', HASH_1, 'alta', HASH_2),
    ('12345679/G34', '2024-01-01T19:20:40+01:00', HASH_2, 'anulacion', HASH_3),
])
def test_independent_aeat_hash_vectors(number, timestamp, previous, kind, expected):
    data = {'issuer_nif':'89890001K', 'number':number, 'date':'01-01-2024',
            'type':'F1', 'tax':'12.35', 'total':'123.45', 'timestamp':timestamp}
    assert fiscal.fiscal_hash(data, previous, kind) == expected
    # AEAT specifies stripping outer spaces, preserving content inside values.
    assert fiscal.fiscal_hash({k:' '+v+' ' for k,v in data.items()}, previous, kind) == expected


def record_data():
    return {'issuer_nif':'89890001K', 'issuer_name':'TALLER FICTICIO',
            'number':'TEST-1', 'date':'23-09-2026', 'type':'F1', 'tax':'21.00',
            'total':'121.00', 'timestamp':'2026-09-23T09:00:00+02:00',
            'document_id':'synthetic-document-id', 'description':'Mano de obra & piezas <revisadas>',
            'customer_name':'CLIENTE FICTICIO', 'customer_nif':'12345678Z',
            'taxes':[{'kind':'S1','rate':'21','base_cents':10000,'tax_cents':2100}],
            'producer':{'name':'PRODUCTOR FICTICIO','nif':'12345678Z',
                        'system_id':'EC','installation_id':'synthetic-installation'},
            'reference':{'number':'TEST-0','date':'22-09-2026'}}


@pytest.mark.parametrize('kind,changes', [
    ('alta', {}),
    ('alta', {'type':'R1'}),
    ('alta', {'type':'R2'}),
    ('alta', {'type':'R3'}),
    ('alta', {'type':'R4'}),
    ('subsanacion', {}),
    ('subsanacion', {'rejection_previous':'X'}),
    ('subsanacion', {'rejection_previous':'S'}),
    ('anulacion', {}),
    ('anulacion', {'no_previous_record':'S'}),
    ('anulacion', {'rejection_previous':'S'}),
])
def test_generated_records_pass_actual_official_schema(kind, changes):
    data = {**record_data(), **changes}
    if data['type'].startswith('R'):
        data.update(tax='-21.00',total='-121.00',taxes=[
            {'kind':'S1','rate':'21','base_cents':-10000,'tax_cents':-2100}])
    previous = {**record_data(), 'number':'TEST-0', 'hash':HASH_1}
    xml, digest = fiscal.xml_record(data, previous, kind)
    message = fiscal.validate_official_xml(xml)
    row = message.find('{'+fiscal.LR+'}RegistroFactura')[0]
    assert row.tag == '{'+fiscal.SF+'}'+('RegistroAnulacion' if kind == 'anulacion' else 'RegistroAlta')
    assert row.findtext('{'+fiscal.SF+'}Huella') == digest
    assert row.findtext('{'+fiscal.SF+'}Encadenamiento/{'+fiscal.SF+'}RegistroAnterior/{'+fiscal.SF+'}Huella') == HASH_1
    if kind == 'subsanacion':
        assert row.findtext('{'+fiscal.SF+'}Subsanacion') == 'S'
        assert row.findtext('{'+fiscal.SF+'}RechazoPrevio') == changes.get('rejection_previous')


def test_multiple_rates_and_exempt_operation_are_distinct():
    data = record_data()
    data.update(tax='23.10', total='143.10', taxes=[
        {'kind':'S1','rate':'21','base_cents':10000,'tax_cents':2100},
        {'kind':'S1','rate':'10','base_cents':2100,'tax_cents':210},
        {'kind':'E1','rate':'0','base_cents':-100,'tax_cents':0},
    ])
    xml, _ = fiscal.xml_record(data)
    message = fiscal.validate_official_xml(xml)
    details = message.findall('.//{'+fiscal.SF+'}DetalleDesglose')
    assert len(details) == 3
    assert details[2].findtext('{'+fiscal.SF+'}OperacionExenta') == 'E1'
    assert details[2].find('{'+fiscal.SF+'}CuotaRepercutida') is None


@pytest.mark.parametrize('old,new', [
    ('<sum:Cabecera>', '<sf:Cabecera>'),
    ('<sf:RegistroAlta>', '<sum:RegistroAlta>'),
    ('>21.00<', '>21,00<'),
    ('>23-09-2026<', '>2026-09-23<'),
])
def test_schema_rejects_wrong_qname_and_formats(old, new):
    xml, _ = fiscal.xml_record(record_data())
    malformed = xml.replace(old, new).replace(old.replace('<','</'), new.replace('<','</'))
    with pytest.raises(AppError):
        fiscal.validate_official_xml(malformed)


def test_timestamp_requires_timezone_and_xml_content_is_escaped():
    with pytest.raises(AppError, match='huso'):
        fiscal.xml_record({**record_data(), 'timestamp':'2026-09-23T09:00:00'})
    xml, _ = fiscal.xml_record(record_data())
    assert 'Mano de obra &amp; piezas &lt;revisadas&gt;' in xml
    assert fiscal.validate_official_xml(xml) is not None


def test_qr_formats_official_escaped_example_without_emitting_or_connecting():
    # AEAT QR v0.5.0, page 8, literal URL for the ampersand example.
    data = {'issuer_nif':'89890001K', 'number':'12345678&G33',
            'date':'01-01-2024', 'total':'241.4'}
    assert fiscal.qr_url(data) == ('https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?'
        'nif=89890001K&numserie=12345678%26G33&fecha=01-01-2024&importe=241.4')
    assert fiscal.qr_url(data,'production') == ('https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?'
        'nif=89890001K&numserie=12345678%26G33&fecha=01-01-2024&importe=241.4')
    with pytest.raises(AppError):
        fiscal.qr_url(data,'unknown')
    with pytest.raises(AppError):
        fiscal.qr_url({**data,'number':'SERIE-Ñ'})


def test_bundled_schemas_include_all_imports_and_detect_modified_bytes(tmp_path):
    manifest = fiscal.verify_schema_files()
    for name in fiscal.SCHEMA_FILES:
        assert manifest['files'][name]['source'].startswith('https://')
        if name.endswith('.xsd'):
            assert fiscal.official_schema(name) is not None
    target = tmp_path/'schema-copy'
    shutil.copytree(fiscal.BUNDLED_SCHEMA_DIR, target)
    (target/'SuministroLR.xsd').write_text('<schema/>',encoding='utf-8')
    with pytest.raises(AppError,match='modificado'):
        fiscal.verify_schema_files(target)


def test_local_publish_validates_without_network_or_downloaded_cache(app, draft, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('No network or certificate needed for XSD validation')
    monkeypatch.setattr(fiscal.urllib.request, 'build_opener', forbidden)
    monkeypatch.setattr(app.certificates, 'context', forbidden)
    assert not (app.fiscal.spec_dir/'SuministroLR.xsd').exists()
    issued = app.documents.publish(draft['id'])
    with app.db.read() as conn:
        xml = conn.execute('SELECT xml FROM fiscal_records WHERE document_id=?',(issued['id'],)).fetchone()[0]
    assert app.fiscal.validate_schema(xml)


def test_public_download_does_not_load_certificate_and_checks_fingerprints(app, monkeypatch):
    urls = []
    def open_public(url, **_kwargs):
        urls.append(url)
        return io.BytesIO((fiscal.BUNDLED_SCHEMA_DIR/url.rsplit('/',1)[-1]).read_bytes())
    def forbidden():
        raise AssertionError('A static schema must not require a client certificate')
    monkeypatch.setattr(app.certificates,'context',forbidden)
    monkeypatch.setattr(fiscal.urllib.request,'build_opener',lambda *_: SimpleNamespace(open=open_public))
    assert app.fiscal.download_specs()['verified'] is True
    assert len(urls) == len(fiscal.SCHEMA_FILES)
    fiscal.verify_schema_files(app.fiscal.spec_dir)
    previous_manifest = (app.fiscal.spec_dir/'manifest.json').read_bytes()
    monkeypatch.setattr(fiscal.urllib.request,'build_opener',lambda *_: SimpleNamespace(open=lambda *_a, **_k:io.BytesIO(b'<schema/>')))
    with pytest.raises(AppError,match='Ha cambiado'):
        app.fiscal.download_specs()
    assert (app.fiscal.spec_dir/'manifest.json').read_bytes() == previous_manifest
    fiscal.verify_schema_files(app.fiscal.spec_dir)


def response(data, state='Correcto', wait='60', kind='alta', duplicate=False):
    """Synthetic XSD-valid response. All identifiers belong to temporary tests."""
    overall = {'Correcto':'Correcto','AceptadoConErrores':'ParcialmenteCorrecto','Incorrecto':'Incorrecto'}[state]
    operation = 'Anulacion' if kind == 'anulacion' else 'Alta'
    flags = '<sf:Subsanacion>S</sf:Subsanacion>' if kind == 'subsanacion' else ''
    for key, name in [('rejection_previous','RechazoPrevio'),('no_previous_record','SinRegistroPrevio')]:
        if data.get(key):
            flags += f'<sf:{name}>{data[key]}</sf:{name}>'
    duplicated = '''<r:RegistroDuplicado><sf:IdPeticionRegistroDuplicado>SYNTHETIC-REQUEST</sf:IdPeticionRegistroDuplicado>
      <sf:EstadoRegistroDuplicado>Correcta</sf:EstadoRegistroDuplicado>
      <sf:CodigoErrorRegistro>9999</sf:CodigoErrorRegistro>
      <sf:DescripcionErrorRegistro>Detalle sintético del registro previo</sf:DescripcionErrorRegistro>
      </r:RegistroDuplicado>''' if duplicate else ''
    return f'''<s:Envelope xmlns:s="{fiscal.SOAP}" xmlns:r="{fiscal.RESPONSE}" xmlns:sf="{fiscal.SF}">
      <s:Body><r:RespuestaRegFactuSistemaFacturacion><r:CSV>SYNTHETIC-CSV</r:CSV>
        <r:Cabecera><sf:ObligadoEmision><sf:NombreRazon>TALLER FICTICIO</sf:NombreRazon>
          <sf:NIF>{data['issuer_nif']}</sf:NIF></sf:ObligadoEmision></r:Cabecera>
        <r:TiempoEsperaEnvio>{wait}</r:TiempoEsperaEnvio><r:EstadoEnvio>{overall}</r:EstadoEnvio>
        <r:RespuestaLinea><r:IDFactura><sf:IDEmisorFactura>{data['issuer_nif']}</sf:IDEmisorFactura>
          <sf:NumSerieFactura>{escape(data['number'])}</sf:NumSerieFactura>
          <sf:FechaExpedicionFactura>{data['date']}</sf:FechaExpedicionFactura></r:IDFactura>
          <r:Operacion><sf:TipoOperacion>{operation}</sf:TipoOperacion>{flags}</r:Operacion>
          <r:EstadoRegistro>{state}</r:EstadoRegistro>{duplicated}</r:RespuestaLinea>
      </r:RespuestaRegFactuSistemaFacturacion></s:Body></s:Envelope>'''


def test_strict_response_preserves_wait_and_duplicate_evidence():
    data = record_data()
    assert fiscal.parse_response(response(data,wait='9999'),data)['wait'] == 9999
    parsed = fiscal.parse_response(response(data,state='Incorrecto',duplicate=True),data)
    assert parsed['status'] == 'duplicate_review'
    assert parsed['duplicate']['state'] == 'Correcta'
    assert parsed['duplicate']['request_id'] == 'SYNTHETIC-REQUEST'
    assert parsed['error'] == ''  # Nested duplicate error must not masquerade as current error.


@pytest.mark.parametrize('mutation', [
    lambda xml:xml.replace('<r:CSV>SYNTHETIC-CSV</r:CSV>',''),
    lambda xml:xml.replace('<r:TiempoEsperaEnvio>60</r:TiempoEsperaEnvio>','<r:TiempoEsperaEnvio/>'),
    lambda xml:xml.replace('<r:EstadoEnvio>Correcto</r:EstadoEnvio>','<r:EstadoEnvio>Incorrecto</r:EstadoEnvio>'),
    lambda xml:xml.replace('<sf:TipoOperacion>Alta</sf:TipoOperacion>','<sf:TipoOperacion>Anulacion</sf:TipoOperacion>'),
    lambda xml:xml.replace('<r:Operacion><sf:TipoOperacion>Alta</sf:TipoOperacion></r:Operacion>',''),
    lambda xml:xml.replace('<r:IDFactura>','<sf:IDFactura>').replace('</r:IDFactura>','</sf:IDFactura>'),
    lambda xml:xml.replace('<s:Body>','<s:Body><extra/>'),
])
def test_incomplete_or_mismatched_response_never_becomes_acceptance(mutation):
    data = record_data()
    with pytest.raises(AppError):
        fiscal.parse_response(mutation(response(data)),data)


def test_subsanation_response_must_match_sent_flags():
    data = {**record_data(),'rejection_previous':'X'}
    assert fiscal.parse_response(response(data,kind='subsanacion'),data,'subsanacion')['status'] == 'accepted'
    with pytest.raises(AppError,match='indicadores'):
        fiscal.parse_response(response(data,kind='subsanacion'),record_data(),'subsanacion')


def enable_injected_transport(app, monkeypatch):
    # Stub only the existence gate. No key/certificate is generated or loaded;
    # all sends use an injected, local transport. Network access is forbidden.
    monkeypatch.setattr(app.certificates,'path',SimpleNamespace(exists=lambda:True))
    def forbidden():
        raise AssertionError('Synthetic transport tests must never authenticate or contact AEAT')
    monkeypatch.setattr(app.certificates,'context',forbidden)
    app.settings.save('fiscal',{'mode':'aeat_test','producer_name':'PRODUCTOR FICTICIO','producer_tax_id':'12345678Z'})


def issue(app, customer):
    draft = app.documents.save({'customer_id':customer['id'],'issue_date':today(),
        'lines':[{'description':'Trabajo sintético','quantity':'1','unit_price':'100','tax_rate':'21'}]})
    return app.documents.publish(draft['id'])


def pending_payload(app):
    with app.db.read() as conn:
        row = conn.execute('SELECT payload FROM fiscal_records ORDER BY seq DESC LIMIT 1').fetchone()
        return json.loads(row[0])


def test_wait_survives_new_record_and_preserves_queue_order(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    first = issue(app,customer)
    sent_data = pending_payload(app)
    assert app.fiscal.send_next(transport=lambda _:response(sent_data,wait='9999'))['status'] == 'accepted'
    second = issue(app,customer)
    with app.db.read() as conn:
        rows = conn.execute('SELECT r.document_id,o.next_attempt FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id ORDER BY r.seq').fetchall()
    assert [r['document_id'] for r in rows] == [first['id'],second['id']]
    assert rows[0]['next_attempt'] == rows[1]['next_attempt']
    assert datetime.fromisoformat(rows[0]['next_attempt']) > datetime.now(timezone.utc)+timedelta(seconds=9990)
    assert app.fiscal.send_next(transport=lambda _:pytest.fail('AEAT wait not respected'))['status'] == 'idle'
    # Even a later row with an early due time cannot overtake the oldest pending row.
    third = issue(app,customer)
    with app.db.transaction() as conn:
        conn.execute('UPDATE fiscal_outbox SET next_attempt=? WHERE record_id=(SELECT id FROM fiscal_records WHERE document_id=?)',(now(),third['id']))
    assert app.fiscal.send_next(transport=lambda _:pytest.fail('Out-of-order send'))['status'] == 'idle'


def test_timeout_requires_query_and_preserves_unrecognized_query_response(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    sent = []
    def timeout(xml):
        sent.append(xml)
        raise TimeoutError('Synthetic timeout')
    assert app.fiscal.send_next(transport=timeout)['status'] == 'uncertain'
    with app.db.transaction() as conn:
        conn.execute('UPDATE fiscal_outbox SET next_attempt=?',(now(),))
        conn.execute('UPDATE fiscal_channels SET next_allowed_at=?',(now(),))
    malformed = '<html>synthetic proxy response</html>'
    assert app.fiscal.send_next(transport=lambda xml:sent.append(xml) or malformed)['status'] == 'uncertain'
    with app.db.read() as conn:
        assert conn.execute('SELECT response_xml FROM fiscal_reconciliations ORDER BY created_at DESC,rowid DESC LIMIT 1').fetchone()[0] == malformed
        assert conn.execute('SELECT COUNT(*) FROM fiscal_attempts').fetchone()[0] == 1
        assert conn.execute('SELECT xml FROM fiscal_records').fetchone()[0] == sent[0]
    assert 'RegFactuSistemaFacturacion' in sent[0]
    assert 'ConsultaFactuSistemaFacturacion' in sent[1]
    assert app.fiscal.verify_chain()['ok']
