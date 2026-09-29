"""Real SQLite flows for original tax dates and AEAT's tax-only R2/R3 example."""
import copy
from datetime import date, timedelta
import json

from lxml import etree
import pytest

from taller.b2b_xml import CBC, CAC, generate, validate_xml
from taller.db import dumps
from taller.errors import AppError
from taller.fiscal import SF, validate_business, validate_official_xml, xml_record
from taller.fiscal_query import QUERY_RESPONSE, compare_query_record, parse_query_response, period
from taller.money import calculate
from taller.validation import today

from test_fiscal_official import record_data
from test_fiscal_workflow import query_reply


def original_invoice(app,customer,operation_date='2024-09-30'):
    return app.documents.publish(app.documents.save({'customer_id':customer['id'],'operation_date':operation_date,
        'lines':[{'description':'Operación sintética documentada','quantity':'1','unit_price':'1000','tax_rate':'21'}]})['id'])


@pytest.mark.parametrize('invoice_type',['R2','R3'])
def test_official_tax_only_example_keeps_zero_base_and_negative_quota(app,customer,invoice_type):
    # AEAT FAQ Procedimientos de facturación, diferencias, ejemplo 3:
    # original base 1,000 / IVA 210; correction base 0 / IVA -210 / total -210.
    original=original_invoice(app,customer)
    draft=app.documents.rectify(original['id'],'Supuesto sintético documentado de recuperación de IVA',invoice_type,
                                tax_adjustments=[{'tax_rate':'21.00','tax_cents':-21000}])
    assert draft['base_cents']==0 and draft['tax_cents']==draft['total_cents']==-21000
    assert draft['payload']['operation_date']=='2024-09-30'
    issued=app.documents.publish(draft['id'])
    assert app.documents.publish(draft['id'])['full_number']==issued['full_number']
    assert app.documents.get(original['id'])['payload']==original['payload']
    assert issued['pending_cents']==-21000 and app.documents.get(original['id'])['pending_cents']==121000
    with app.db.read() as conn:
        row=conn.execute('SELECT * FROM fiscal_records WHERE document_id=?',(issued['id'],)).fetchone()
    data=json.loads(row['payload'])
    validate_business(data,'alta')
    root=validate_official_xml(row['xml'])
    detail=root.find('.//{'+SF+'}DetalleDesglose')
    assert detail.findtext('{'+SF+'}BaseImponibleOimporteNoSujeto')=='0.00'
    assert detail.findtext('{'+SF+'}CuotaRepercutida')=='-210.00'
    assert root.findtext('.//{'+SF+'}TipoRectificativa')=='I'
    assert root.findtext('.//{'+SF+'}FechaOperacion')=='30-09-2024'
    assert period(data)==('2024','09')
    rows,_=parse_query_response(query_reply(dict(row)),data)
    assert compare_query_record(rows[0],row['xml'],'alta')['status']=='accepted'
    assert app.fiscal.verify_chain()['ok']


def test_tax_only_drafts_compete_for_remaining_quota_and_can_be_reversed(app,customer):
    original=original_invoice(app,customer)
    params={'identifier':original['id'],'reason':'Incobro sintético documentado','invoice_type':'R3',
            'tax_adjustments':[{'tax_rate':'21','tax_cents':-21000}]}
    first=app.documents.rectify(**params)
    stale=app.documents.rectify(**params)
    first=app.documents.publish(first['id'])
    before=app.settings.list_series()
    with pytest.raises(AppError) as failure:
        app.documents.publish(stale['id'])
    assert failure.value.code=='tax_adjustment_limit'
    assert app.settings.list_series()==before
    assert app.documents.get(stale['id'])['status']=='draft'
    reversal=app.documents.rectify(first['id'],'Reversión sintética con evidencia de cambio de circunstancias','R3',
                                  tax_adjustments=[{'tax_rate':'21','tax_cents':21000}])
    restored=app.documents.publish(reversal['id'])
    assert restored['base_cents']==0 and restored['tax_cents']==21000
    assert sum(doc['tax_cents'] for doc in (original,first,restored))==21000


def test_tax_only_does_not_allow_a_second_refund_through_a_commercial_correction(app,customer):
    original=original_invoice(app,customer)
    tax=app.documents.rectify(original['id'],'Incobro sintético documentado','R3',
                             tax_adjustments=[{'tax_rate':'21','tax_cents':-21000}])
    app.documents.publish(tax['id'])
    with pytest.raises(AppError,match='ya rectificado'):
        app.documents.rectify(original['id'],'Devolución posterior exige resolver primero la cuota','R1')


@pytest.mark.parametrize('invalid',[
    {'invoice_type':'R4','tax_adjustments':[{'tax_rate':'21','tax_cents':-1}]},
    {'invoice_type':'R3','tax_adjustments':[{'tax_rate':'10','tax_cents':-1}]},
    {'invoice_type':'R3','tax_adjustments':[{'tax_rate':'21','tax_cents':-21001}]},
    {'invoice_type':'R3','tax_adjustments':[{'tax_rate':'21','tax_cents':1}]},
])
def test_quota_edits_require_correct_type_and_original_evidence(app,customer,invalid):
    original=original_invoice(app,customer)
    before=app.documents.list()['total']
    with pytest.raises(AppError):
        app.documents.rectify(original['id'],'Supuesto sintético inválido',**invalid)
    assert app.documents.list()['total']==before


def test_quota_preview_does_not_derive_or_hide_tax_and_requires_zero_base(app,customer):
    original=original_invoice(app,customer)
    draft=app.documents.rectify(original['id'],'Incobro parcial sintético','R3',
                               tax_adjustments=[{'tax_rate':'21','tax_cents':-10500}])
    payload=draft['payload']
    preview=calculate(payload['lines'],corrective=True,invoice_type='R3',tax_adjustments=payload['tax_adjustments'])
    assert preview['tax_cents']==-10500 and preview['base_cents']==0
    changed=copy.deepcopy(payload['lines']);changed[0]['description']='Descripción revisada por el usuario'
    revised=app.documents.save({**draft,**payload,'lines':changed})
    assert revised['tax_cents']==-10500
    changed[0]['unit_price']='1'
    with pytest.raises(AppError,match='base cero'):
        app.documents.save({**revised,**revised['payload'],'lines':changed})


def test_operation_date_is_conserved_in_normal_rectification_b2b_and_reconciliation(app,customer):
    original=original_invoice(app,customer)
    corrected=app.documents.publish(app.documents.rectify(original['id'],'Descuento sintético','R1')['id'])
    assert corrected['payload']['operation_date']=='2024-09-30'
    xml=generate(corrected)
    assert validate_xml(xml)['ok']
    assert etree.fromstring(xml.encode()).findtext('{'+CBC+'}TaxPointDate')=='2024-09-30'
    with app.db.read() as conn:
        record=dict(conn.execute('SELECT * FROM fiscal_records WHERE document_id=?',(corrected['id'],)).fetchone())
    data=json.loads(record['payload'])
    response=query_reply(record,mutate=lambda node:setattr(node.find('{'+QUERY_RESPONSE+'}FechaOperacion'),'text','01-10-2024'))
    rows,_=parse_query_response(response,data)
    result=compare_query_record(rows[0],record['xml'],'alta')
    assert result['status']=='reconciliation_conflict' and 'FechaOperacion' in result['differences']


def test_historical_without_operation_date_requires_explicit_source_date(app,customer):
    draft=app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Histórico sintético','quantity':'1','unit_price':'100','tax_rate':'21'}]})
    payload=draft['payload'];payload.pop('operation_date')
    payload.update(historical=True,customer=customer,issuer={})
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='historical',full_number='H-2014-001',issue_date='2014-05-20',payload=? WHERE id=?",(dumps(payload),draft['id']))
    with pytest.raises(AppError,match='fecha de operación'):
        app.documents.rectify(draft['id'],'Ajuste comercial sintético posterior')
    corrected=app.documents.rectify(draft['id'],'Ajuste comercial sintético posterior',operation_date='2014-05-18')
    assert corrected['payload']['operation_date']=='2014-05-18'
    assert 'operation_date' not in app.documents.get(draft['id'])['payload']
    with pytest.raises(AppError,match='posterior'):
        app.documents.rectify(draft['id'],'Fecha sintética incorrecta',operation_date=(date.fromisoformat(today())+timedelta(days=1)).isoformat())


@pytest.mark.parametrize('rate',['7','8','16','18'])
def test_historical_vat_is_not_reclassified_to_pass_xsd_or_service(rate,app,customer):
    data=record_data();data['type']='R4'
    data['taxes'][0].update(rate=rate,tax_cents=int(rate)*100)
    data.update(tax=f'{int(rate)}.00',total=f'{100+int(rate)}.00')
    xml,_=xml_record(data)
    assert validate_official_xml(xml) is not None  # XSD alone does not enforce AEAT rule15.1.
    with pytest.raises(AppError) as failure:
        validate_business(data,'alta')
    assert failure.value.code=='unsupported_historical_tax_rate'
    with pytest.raises(AppError,match='histórico'):
        calculate([{'description':'No se cambia el IVA original','quantity':'-1','unit_price':'100','tax_rate':rate}],corrective=True)


def test_tax_only_ubl_is_blocked_by_actual_cen_rule_without_modifying_fiscal_document(app,customer):
    original=original_invoice(app,customer)
    draft=app.documents.rectify(original['id'],'Incobro sintético para probar mapeo','R3',
                               tax_adjustments=[{'tax_rate':'21','tax_cents':-21000}])
    issued=app.documents.publish(draft['id'])
    with pytest.raises(AppError) as failure:
        app.b2b.prepare(issued['id'],True)
    assert failure.value.code=='b2b_tax_only_profile'
    assert app.b2b.list()['total']==0 and app.documents.get(issued['id'])['total_cents']==-21000
    # A UBL-shaped zero-base/tax-only candidate is checked with the real CEN XSLT.
    root=etree.fromstring(generate(original).encode())
    for name in ('LineExtensionAmount','TaxExclusiveAmount'):
        root.find('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}'+name).text='0.00'
    for name in ('TaxInclusiveAmount','PayableAmount'):
        root.find('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}'+name).text='210.00'
    root.find('{'+CAC+'}TaxTotal/{'+CAC+'}TaxSubtotal/{'+CBC+'}TaxableAmount').text='0.00'
    root.find('{'+CAC+'}InvoiceLine/{'+CBC+'}LineExtensionAmount').text='0.00'
    root.find('{'+CAC+'}InvoiceLine/{'+CAC+'}Price/{'+CBC+'}PriceAmount').text='0'
    result=validate_xml(etree.tostring(root,encoding='unicode'))
    assert not result['ok']
    assert {'BR-S-09','BR-CO-17'} & {error['id'] for error in result['errors']}
