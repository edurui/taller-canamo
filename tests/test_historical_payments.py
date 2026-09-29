import pytest

from taller.db import dumps
from taller.errors import AppError
from taller.validation import today


def historical(app, draft):
    payload = {**draft['payload'], 'historical': True, 'payment_state': 'unknown',
               'customer': {'name': 'Cliente conservado'}, 'issuer': {}, 'branding': {}}
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='historical',full_number='H-0001',payload=? WHERE id=?", (dumps(payload), draft['id']))
    return app.documents.get(draft['id'])


def test_unknown_imported_payment_is_not_presented_as_debt(app, draft):
    document = historical(app, draft)
    assert document['paid_cents'] is None and document['pending_cents'] is None
    assert not document['payment_known']
    row = app.documents.list()['items'][0]
    assert row['paid_cents'] is None and not row['payment_known']
    assert app.dashboard()['pending_cents'] == 0
    assert app.dashboard()['unknown_payment_documents'] == 1
    with pytest.raises(AppError, match='no está documentado'):
        app.documents.pay(document['id'], '10', 'cash', today(), 'unknown-receipt')


def test_documented_balance_is_idempotent_and_does_not_change_snapshot(app, draft):
    before = historical(app, draft)
    params = {'identifier': before['id'], 'paid_cents': 2000, 'evidence': 'Recibo sintético 17 revisado', 'idempotency_key': 'opening-17'}
    first = app.documents.record_payment_state(**params)
    assert app.documents.record_payment_state(**params) == first
    assert first['payload'] == before['payload'] and first['full_number'] == before['full_number']
    assert first['paid_cents'] == 2000 and first['pending_cents'] == 4171
    assert app.dashboard()['pending_cents'] == 4171 and app.dashboard()['unknown_payment_documents'] == 0
    with pytest.raises(AppError, match='otra conciliación'):
        app.documents.record_payment_state(**{**params, 'paid_cents': 2500})
    collected = app.documents.pay(first['id'], '41.71', 'card', today(), 'remainder')
    assert collected['pending_cents'] == 0 and collected['paid_cents'] == 6171
    assert collected['payload'] == before['payload']
    assert not app.fiscal.records()


def test_wrong_documented_balance_can_be_corrected_without_rewriting_evidence(app, draft):
    before = historical(app, draft)
    app.documents.record_payment_state(before['id'], 3000, 'Recibo sintético 18', 'opening-18')
    params = {'identifier': before['id'], 'paid_cents': 2000, 'evidence': 'El recibo anterior correspondía a otro importe: corrección comprobada', 'idempotency_key': 'correct-18'}
    corrected = app.documents.adjust_payment_state(**params)
    assert app.documents.adjust_payment_state(**params) == corrected
    assert corrected['paid_cents'] == 2000
    assert corrected['payment_baseline']['paid_cents'] == 3000
    assert len(corrected['payments']) == 1
    assert corrected['payments'][0]['amount_cents'] == -1000
    assert corrected['payload'] == before['payload']
    with pytest.raises(AppError, match='este ajuste no es un cobro'):
        app.documents.reverse_payment(corrected['payments'][0]['id'], 'No debe borrar la evidencia')
    with pytest.raises(AppError, match='otro ajuste'):
        app.documents.adjust_payment_state(**{**params, 'paid_cents': 1000})


def test_reverted_import_is_excluded_from_lists_and_operational_reports(app, draft):
    document = historical(app, draft)
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='import_reverted' WHERE id=?", (document['id'],))
    assert app.documents.list()['total'] == 0
    assert app.reports()['months'] == []
    assert app.documents.get(document['id'])['status'] == 'import_reverted'
