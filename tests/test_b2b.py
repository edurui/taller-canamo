"""Official UBL/CEN validation with synthetic local workshop workflows."""
import base64
import hashlib
import json
import sqlite3

from lxml import etree
import pytest

from taller.app import App
from taller.b2b import B2B, check_storage
from taller.b2b_xml import RESOURCES, CBC, CAC, CREDIT, generate, validate_xml
from taller.errors import AppError
from taller.validation import today


@pytest.fixture
def b2b(app):
    return B2B(app.db,app.settings,app.documents)


def issue(app,customer,lines=None):
    return app.documents.publish(app.documents.save({'customer_id':customer['id'],'lines':lines or [
        {'description':'Trabajo sintético','quantity':'1.25','unit_price':'37.455','discount':'7.25','tax_rate':'21'}]})['id'])


@pytest.mark.parametrize('filename',['ubl-tc434-example1.xml','ubl-tc434-creditnote1.xml'])
def test_independent_cen_examples_pass_official_xsd_and_all_semantic_rules(filename):
    result = validate_xml((RESOURCES/'en16931/examples'/filename).read_text(encoding='utf-8'))
    assert result['ok'] and result['errors'] == []
    assert result['semantic']=='EN16931-1.3.16' and result['network_called'] is False


def test_xsd_valid_but_incorrect_monetary_total_is_rejected_by_official_semantic_rule(app,customer):
    xml = generate(issue(app,customer))
    root = etree.fromstring(xml.encode())
    root.find('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}TaxInclusiveAmount').text = '1.00'
    result = validate_xml(etree.tostring(root,encoding='unicode'))
    assert result['ok'] is False
    assert any(item['id']=='BR-CO-15' for item in result['errors'])


def test_prepared_export_is_idempotent_snapshotted_and_never_reported_as_delivery(app,customer,b2b):
    issued = issue(app,customer)
    before = app.settings.list_series()
    first = b2b.prepare(issued['id'],True)
    app.contacts.save_customer({**customer,'name':'Nombre posterior'})
    assert b2b.prepare(issued['id'],True)['id'] == first['id']
    assert 'Lucia de Prueba' in first['xml'] and 'Nombre posterior' not in first['xml']
    export = b2b.export(first['id'])
    assert export['name'].startswith('PRUEBA-')
    assert base64.b64decode(export['content']).decode()==first['xml']
    assert export['remote_delivered'] is False and first['remote_delivered'] is False
    assert first['obligations'][0]['status']=='awaiting_official_specification'
    assert app.settings.list_series()==before
    assert b2b.check(first['id'])['ok']
    assert len(app.fiscal.records())==1


def test_prepare_requires_business_confirmation_and_an_issued_invoice(app,customer,b2b):
    draft = app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Prueba','quantity':'1','unit_price':'1'}]})
    with pytest.raises(AppError,match='empresa o profesional'):
        b2b.prepare(draft['id'],False)
    with pytest.raises(AppError,match='emitida'):
        b2b.prepare(draft['id'],True)
    assert b2b.list()['total']==0


def test_credit_note_maps_negative_workshop_adjustment_to_positive_ubl_credit_amounts(app,customer,b2b):
    original = issue(app,customer)
    correction = app.documents.rectify(original['id'],'Descuento parcial sintético')
    correction = app.documents.publish(correction['id'])
    record = b2b.prepare(correction['id'],True)
    root = etree.fromstring(record['xml'].encode())
    assert root.tag=='{'+CREDIT+'}CreditNote'
    assert root.findtext('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}TaxInclusiveAmount') == f'{abs(correction["total_cents"])/100:.2f}'
    assert root.findtext('{'+CAC+'}BillingReference/{'+CAC+'}InvoiceDocumentReference/{'+CBC+'}ID') == original['full_number']
    assert record['total_cents']==correction['total_cents']<0 and record['validation']['ok']


def test_multiple_rates_exempt_reasons_zero_rate_and_discount_keep_totals(app,customer,b2b):
    issued = issue(app,customer,[
        {'description':'IVA21','quantity':'3.125','unit_price':'10.2222','discount':'4.33','tax_rate':'21'},
        {'description':'IVA10','quantity':'1','unit_price':'11','tax_rate':'10'},
        {'description':'IVA0','quantity':'1','unit_price':'12','tax_rate':'0'},
        {'description':'Exenta1','quantity':'1','unit_price':'13','tax_rate':'0','tax_kind':'E1','tax_reason':'Causa sintética uno'},
        {'description':'Exenta6','quantity':'1','unit_price':'14','tax_rate':'0','tax_kind':'E6','tax_reason':'Causa sintética dos'},
    ])
    record = b2b.prepare(issued['id'],True)
    assert record['validation']['ok'] and record['total_cents']==issued['total_cents']
    root=etree.fromstring(record['xml'].encode())
    categories=root.findall('{'+CAC+'}TaxTotal/{'+CAC+'}TaxSubtotal/{'+CAC+'}TaxCategory')
    assert [item.findtext('{'+CBC+'}ID') for item in categories].count('E')==1
    assert {'S','Z','E'} == {item.findtext('{'+CBC+'}ID') for item in categories}


def test_reception_checks_recipient_and_identity_without_generating_sales_or_fiscal_records(app,customer,b2b,tmp_path):
    issued=issue(app,customer)
    record=b2b.prepare(issued['id'],True)
    receiver=App(tmp_path/'recipient')
    receiver.settings.save('company',{'legal_name':'RECEPTOR SINTETICO','tax_id':customer['tax_id']})
    inbox=B2B(receiver.db,receiver.settings,receiver.documents)
    received=inbox.receive(record['xml'])
    assert received['direction']=='inbound'
    assert inbox.receive(record['xml'])['id']==received['id']
    assert receiver.documents.list()['total']==0 and receiver.fiscal.records()==[]
    with pytest.raises(AppError,match='destinatario'):
        b2b.receive(record['xml'])
    changed=record['xml'].replace('Trabajo sintético','Otro trabajo con misma identidad')
    with pytest.raises(AppError,match='distinto contenido'):
        inbox.receive(changed)


def test_reception_and_export_preserve_original_non_utf8_bytes(app,customer,b2b,tmp_path):
    record=b2b.prepare(issue(app,customer)['id'],True)
    root=etree.fromstring(record['xml'].encode())
    original=etree.tostring(root,encoding='ISO-8859-1',xml_declaration=True)
    receiver=App(tmp_path/'recipient')
    receiver.settings.save('company',{'legal_name':'RECEPTOR SINTETICO','tax_id':customer['tax_id']})
    inbox=B2B(receiver.db,receiver.settings,receiver.documents)
    received=inbox.receive(content=base64.b64encode(original).decode())
    assert 'sintético' in received['xml']
    assert base64.b64decode(inbox.export(received['id'])['content'])==original


def test_local_commercial_and_payment_states_are_idempotent_correctable_and_separate(app,customer,b2b):
    record=b2b.prepare(issue(app,customer)['id'],True)
    params={'identifier':record['id'],'state':'accepted','occurred_on':today(),'evidence':'Confirmación sintética conservada','idempotency_key':'accept1'}
    accepted=b2b.record_state(**params)
    assert b2b.record_state(**params)['events']==accepted['events']
    with pytest.raises(AppError,match='corrección explícita'):
        b2b.record_state(record['id'],'rejected',today(),'Error documentado','reject1')
    corrected=b2b.record_state(record['id'],'rejected',today(),'Error documentado','reject1',corrects_event_id=accepted['events'][-1]['id'])
    assert corrected['commercial_state']=='rejected'
    paid=b2b.record_state(record['id'],'partially_paid',today(),'Pago parcial sintético','part1',paid_cents=100)
    paid=b2b.record_state(record['id'],'paid',today(),'Pago completo sintético','full1',paid_cents=abs(record['total_cents']))
    assert paid['payment_state']=='paid' and paid['commercial_state']=='rejected'
    assert all(item['status']=='awaiting_official_specification' for item in paid['obligations'])
    assert b2b.check(record['id'])['ok']
    with app.db.transaction() as conn,pytest.raises(sqlite3.IntegrityError,match='otro evento'):
        conn.execute("UPDATE b2b_events SET evidence='changed'")


def test_wrong_payment_state_and_reused_key_are_rejected_without_extra_events(app,customer,b2b):
    record=b2b.prepare(issue(app,customer)['id'],True)
    with pytest.raises(AppError,match='no coincide'):
        b2b.record_state(record['id'],'paid',today(),'Pago incompleto','key1',paid_cents=1)
    accepted=b2b.record_state(record['id'],'accepted',today(),'Aceptación documentada','key1')
    with pytest.raises(AppError,match='clave de operación'):
        b2b.record_state(record['id'],'rejected',today(),'Rechazo documentado','key1')
    assert len(b2b.get(record['id'])['events'])==len(accepted['events'])


@pytest.mark.parametrize('xml',['<!DOCTYPE Invoice [<!ENTITY leak SYSTEM "file:///etc/passwd">]><Invoice>&leak;</Invoice>','<Invoice xmlns="urn:invented">1</Invoice>'])
def test_unsafe_or_arbitrary_xml_is_not_b2b(xml,b2b):
    with pytest.raises(AppError):
        b2b.receive(xml)
    assert b2b.list()['total']==0


def test_modified_official_rules_are_not_silently_used(tmp_path,monkeypatch):
    from taller import b2b_xml
    folder=tmp_path/'rules';folder.mkdir()
    manifest=json.loads((RESOURCES/'manifest.json').read_text())
    name=next(iter(manifest['files']))
    (folder/name).parent.mkdir(parents=True,exist_ok=True)
    (folder/name).write_text('tampered',encoding='utf-8')
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    monkeypatch.setattr(b2b_xml,'RESOURCES',folder)
    with pytest.raises(AppError,match='alterado'):
        b2b_xml.resources()


@pytest.mark.parametrize('tamper',['source_hash','unrelated_source','event_request','obligation'])
def test_staged_backup_checks_original_bytes_relationship_and_state_chain(app,customer,b2b,tamper):
    record=b2b.prepare(issue(app,customer)['id'],True)
    with app.db.read() as original:
        staging=sqlite3.connect(':memory:')
        original.backup(staging)
    try:
        assert check_storage(staging)['sources_checked']==1
        if tamper in ('source_hash','unrelated_source'):
            staging.execute('DROP TRIGGER b2b_source_no_update')
            changed=record['xml'].replace('Trabajo sintético','Otra descripción conservada').encode()
            digest=hashlib.sha256(changed).hexdigest() if tamper=='unrelated_source' else '0'*64
            staging.execute('UPDATE b2b_source_files SET content=?,sha256=?',(changed,digest))
        elif tamper=='event_request':
            staging.execute('DROP TRIGGER b2b_event_no_update')
            staging.execute("UPDATE b2b_events SET request_hash=?",('0'*64,))
        else:
            staging.execute("UPDATE b2b_obligations SET payload='{}'")
        with pytest.raises(AppError) as failure:
            check_storage(staging)
        assert failure.value.code=='b2b_integrity'
    finally:
        staging.close()


def test_storage_verifier_accepts_old_schema_without_initializing_or_migrating_it():
    connection=sqlite3.connect(':memory:')
    try:
        connection.execute('PRAGMA user_version=1')
        assert check_storage(connection)=={'ok':True,'documents_checked':0,'events_checked':0,'sources_checked':0,'sources_unavailable':0}
        assert connection.execute('PRAGMA user_version').fetchone()[0]==1
        assert not connection.execute('SELECT name FROM sqlite_master').fetchall()
    finally:
        connection.close()
