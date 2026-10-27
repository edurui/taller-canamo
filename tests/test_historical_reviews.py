"""Exact estimates never become original fiscal/accounting evidence."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from taller.db import Database, dumps
from taller.errors import AppError
from taller.historical_reviews import HistoricalReviews, estimate


def source(*, issued='2012-09-01', amounts=('100.005',), **payload):
    return {'id': 'synthetic', 'kind': 'invoice', 'status': 'historical', 'issue_date': issued,
            'base_cents': None, 'tax_cents': None, 'total_cents': None,
            'payload': {'preservation': 'partial', 'date_state': 'known',
                        'lines': [{'amount_raw': value} for value in amounts], **payload}}


def insert(app, customer, *, identifier='synthetic', **options):
    row = source(**options)
    payload = {**row['payload'], 'historical': True, 'payment_state': 'unknown',
               'customer': {'name': 'Nombre original sintético'}, 'issuer': {}, 'taxes': [],
               'base_cents': None, 'tax_cents': None, 'total_cents': None}
    with app.db.transaction() as conn:
        conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,
            payload,base_cents,tax_cents,total_cents,created_at,updated_at)
            VALUES(?,'invoice','historical',?,?,?, ?,NULL,NULL,NULL,'2026-01-01','2026-01-01')''',
                     (identifier, customer['id'], row['issue_date'], 'H-'+identifier, dumps(payload)))
    return identifier


@pytest.mark.parametrize(('issued','rate'), [('2003-01-01','16'), ('2010-06-30','16'),
    ('2010-07-01','18'), ('2012-08-31','18'), ('2012-09-01','21'), ('2026-10-08','21')])
def test_general_rate_boundaries_are_suggestions_not_original_amounts(issued, rate):
    doc = source(issued=issued, amounts=('100',))
    review = estimate(doc)
    assert review['state'] == 'estimated' and review['tax_rate'] == rate
    assert review['base_cents'] == 10000 and review['tax_cents'] == int(rate) * 100
    assert review['total_cents'] == 10000 + int(rate) * 100
    assert all(doc[key] is None for key in ('base_cents','tax_cents','total_cents'))
    assert 'orientación' in review['policy'] and review['version'] == 0


@pytest.mark.parametrize(('amounts','expected'), [(('0.005','0.005'), (1,0,1)),
    (('0.045',), (5,1,6)), (('-0.045',), (-5,-1,-6)), (('0',), (0,0,0)),
    (('0.123456789123456789','0.001543210876543211'), (13,3,16))])
def test_exact_sum_then_half_up_base_then_tax_and_total_addition(amounts, expected):
    review = estimate(source(amounts=amounts))
    assert review['state'] == 'estimated'
    assert tuple(review[key] for key in ('base_cents','tax_cents','total_cents')) == expected


@pytest.mark.parametrize('value', [None, '', 'NaN', 'Infinity', '-Infinity', '1e1000000000',
    '1e-1000000000', '100000000000', True, 0.1, {}, '1'*257])
def test_missing_or_unsafe_raw_values_never_fall_back_to_quantity_price(value):
    review = estimate(source(lines=[{'amount_raw': value, 'quantity':'1', 'unit_price':'10'}]))
    assert review['state'] == 'pending_review' and review['issues']
    assert review['base_cents'] is review['tax_cents'] is review['total_cents'] is None


@pytest.mark.parametrize('lines', [[], None, [True], [{'amount_raw':'10','quantity':'2','unit_price':'6'}],
    [{'amount_raw':'10','quantity':'NaN'}], [{'amount_raw':'10','unit_price':'Infinity'}],
    [{'amount_raw':'0','quantity':'1e999999999','unit_price':'0'}]])
def test_unusable_lines_or_contradictions_block_estimation(lines):
    review = estimate(source(lines=lines))
    assert review['state'] == 'pending_review' and review['total_cents'] is None


def test_quantity_price_are_only_a_consistency_check_when_present():
    review = estimate(source(lines=[{'amount_raw':'2.4690','quantity':'2','unit_price':'1.2345'},
                                   {'amount_raw':'0.005','quantity':None,'unit_price':None}]))
    assert (review['base_cents'],review['tax_cents'],review['total_cents']) == (247,52,299)


@pytest.mark.parametrize('options', [{'issued':None}, {'issued':'2012-99-01'},
    {'date_state':'conflict'}, {'date_state':'unknown'}, {'date_candidates':['2010-01-01','2010-01-02']}])
def test_manual_rate_cannot_resolve_unknown_or_conflicting_date(options):
    result = estimate(source(**options), '21')
    assert result['tax_rate'] == '21' and result['state'] == 'pending_review'
    assert result['total_cents'] is None


def test_dates_before_2003_require_explicit_rate_but_not_a_fabricated_date():
    doc = source(issued='2002-12-31')
    assert estimate(doc)['issues'][0]['code'] == 'date_outside_policy'
    assert estimate(doc, '16')['state'] == 'estimated'


def test_sum_limit_and_existing_known_amount_contradictions_are_blocked():
    assert estimate(source(amounts=('90000000000','90000000000')))['state'] == 'pending_review'
    doc = source(amounts=('100',))
    doc['base_cents'] = 9999
    assert estimate(doc)['issues'][0]['code'] == 'original_amount_mismatch'
    doc['base_cents'] = 10000
    assert estimate(doc)['state'] == 'estimated'


@pytest.mark.parametrize('payload', [
    {'lines':[{'amount_raw':'100','tax_rate':'16'}]},
    {'lines':[{'amount_raw':'50','tax_rate':'21'},{'amount_raw':'50','tax_rate':'16'}]},
    {'lines':[{'amount_raw':'100','tax_rate':'0','tax_kind':'exempt'}]},
    {'lines':[{'amount_raw':'100','base_cents':9999}]},
    {'lines':[{'amount_raw':'100','tax_cents':1600}]},
    {'taxes':[{'rate':'16','kind':'historical','base_cents':10000,'tax_cents':1600}]},
    {'taxes':[{'rate':'21','kind':'subject','base_cents':9999,'tax_cents':2100}]},
    {'taxes':[{'rate':'21','kind':'subject','base_cents':10000,'tax_cents':2101}]},
    {'taxes':[{'rate':'NaN','base_cents':10000,'tax_cents':2100}]},
])
def test_known_source_tax_rates_regimes_and_amounts_are_not_overridden(payload):
    review = estimate(source(amounts=('100',), **payload))
    assert review['state'] == 'pending_review' and review['issues']
    assert review['base_cents'] is review['tax_cents'] is review['total_cents'] is None


def test_explicit_rate_can_match_preserved_source_evidence():
    doc = source(lines=[{'amount_raw':'100','tax_rate':'16','base_cents':10000,'tax_cents':1600}],
                 taxes=[{'rate':'16','kind':'historical','base_cents':10000,'tax_cents':1600}])
    assert estimate(doc)['state'] == 'pending_review'
    matching = estimate(doc,'16')
    assert matching['state'] == 'estimated' and matching['total_cents'] == 11600


def test_subject_tax_classification_is_preserved_without_blocking_matching_estimate():
    doc = source(lines=[{'amount_raw': '100', 'tax_rate': '21', 'tax_kind': 'S1'}])
    assert estimate(doc)['state'] == 'estimated'
    assert estimate(doc, '18')['state'] == 'pending_review'


@pytest.mark.parametrize('rate', [None, '', 'NaN', 'Infinity', '-1', '101', True, 21, '0.0000001'])
def test_save_rejects_invalid_explicit_rates(app, customer, rate):
    identifier = insert(app, customer)
    with pytest.raises(AppError):
        app.dispatch('historical.review_save', dict(identifier=identifier, expected_version=0,
                     tax_rate=rate, reason='Revisión sintética'))


def test_preview_is_read_only_and_save_reset_are_optimistic_append_only(app, customer):
    identifier = insert(app, customer)
    with app.db.read() as conn:
        original = tuple(conn.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone())
        audit_before = conn.execute('SELECT count(*) FROM audit').fetchone()[0]
    preview = app.dispatch('historical.review_preview', {'identifier':identifier,'tax_rate':'18'})
    assert preview['version'] == 0 and preview['tax_rate'] == '18'
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM audit').fetchone()[0] == audit_before
    saved = app.dispatch('historical.review_save', {'identifier':identifier,'expected_version':0,
        'tax_rate':'18','reason':'Hipótesis manual sintética'})
    assert saved['state'] == 'estimated' and saved['version'] == 1
    with pytest.raises(AppError) as conflict:
        app.historical_reviews.save(identifier,0,'16','Ventana antigua')
    assert conflict.value.code == 'conflict'
    reset = app.dispatch('historical.review_reset', {'identifier':identifier,'expected_version':1,'reason':'Volver a política por fecha'})
    assert reset['state'] == 'estimated' and reset['tax_rate'] == '21' and reset['version'] == 2
    document = app.documents.get(identifier)
    assert [item['action'] for item in document['historical_review']['history']] == ['reset','adjust','automatic']
    assert document['customer_name'] == 'Nombre original sintético'
    assert document['current_customer_name'] == customer['name']
    with app.db.transaction() as conn:
        assert tuple(conn.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone()) == original
        for command in ('UPDATE historical_review_versions SET state=\'verified\'', 'DELETE FROM historical_review_versions'):
            with pytest.raises(sqlite3.IntegrityError, match='inalterable'):
                conn.execute(command)
    assert app.db.check_audit()['ok']


def test_verification_needs_explicit_boolean_evidence_and_no_issues(app, customer):
    identifier = insert(app, customer)
    for values in ({'verified':True}, {'verified':'true','evidence':'Documento'}, {'verified':1,'evidence':'Documento'}):
        with pytest.raises(AppError):
            app.historical_reviews.save(identifier,0,'21','Revisión',**values)
    saved = app.historical_reviews.save(identifier,0,'21','Contraste sintético',True,'Factura original sintética: base, cuota y total contrastados')
    assert saved['state'] == 'verified' and saved['evidence']
    changed = app.historical_reviews.save(identifier,1,'18','Cambio posterior')
    assert changed['state'] == 'estimated' and changed['evidence'] == ''
    blocked = insert(app,customer,identifier='blocked',amounts=(None,))
    with pytest.raises(AppError):
        app.historical_reviews.save(blocked,0,'21','Revisión',True,'Documento sin importe')
    pending = app.historical_reviews.save(blocked,0,'21','Importe por recuperar')
    assert pending['state'] == 'pending_review' and pending['version'] == 1


def test_two_connections_cannot_overwrite_a_concurrent_review(app, customer):
    identifier = insert(app,customer)
    first,second = HistoricalReviews(Database(app.db.root)),HistoricalReviews(Database(app.db.root))
    barrier = Barrier(2)
    def save(service):
        barrier.wait()
        try:
            return service.save(identifier,0,'18','Revisión concurrente sintética')['version']
        except AppError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save,[first,second]))
    assert sorted(results,key=str) == [1,'conflict']
    assert [h['version'] for h in app.documents.get(identifier)['historical_review']['history']] == [1,0]


def test_review_does_not_enable_original_payments_reports_rectification_or_fiscal(app, customer):
    identifier = insert(app,customer)
    before_report = app.reports()
    before_dashboard = app.dashboard()
    with app.db.read() as conn:
        originals = [tuple(row) for row in conn.execute('SELECT * FROM documents')]
        original_series = [tuple(row) for row in conn.execute('SELECT * FROM series')]
    app.historical_reviews.save(identifier,0,'21','Contraste sintético',True,'Evidencia completa sintética')
    document = app.documents.get(identifier)
    assert document['historical_review']['state'] == 'verified'
    assert document['amounts_state'] == 'unknown' and document['total_cents'] is None
    assert not document['can_rectify'] and not document['payment_known'] and document['pending_cents'] is None
    after_report = app.reports()
    consultation_keys = ('billing_overview', 'overview_months')
    assert {key: value for key, value in after_report.items() if key not in consultation_keys} == {
        key: value for key, value in before_report.items() if key not in consultation_keys}
    for previous, current in [(before_report['billing_overview'], after_report['billing_overview']),
                              (before_report['overview_months'][0], after_report['overview_months'][0])]:
        assert previous['total_cents'] == current['total_cents'] == 12101
        assert previous['estimated_count'] == current['verified_count'] == 1
        assert previous['estimated_cents'] == current['verified_cents'] == 12101
        assert previous['verified_count'] == current['estimated_count'] == 0
        assert previous['verified_cents'] == current['estimated_cents'] == 0
        assert previous['count'] == current['count'] == 1
    after_dashboard = app.dashboard()
    for key in ('pending_cents','refund_due_cents','unknown_payment_documents'):
        assert after_dashboard[key] == before_dashboard[key]
    with pytest.raises(AppError):
        app.documents.pay(identifier,'1','cash','2026-01-01','synthetic-key')
    with pytest.raises(AppError):
        app.documents.record_payment_state(identifier,0,'Revisión','synthetic-opening')
    with pytest.raises(AppError):
        app.documents.rectify(identifier,'Revisión')
    with app.db.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM documents')] == originals
        assert [tuple(row) for row in conn.execute('SELECT * FROM series')] == original_series
        for table in ('payments','fiscal_records','fiscal_outbox','b2b_documents'):
            assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0] == 0


def test_review_filters_pagination_and_other_document_lists(app, customer, draft):
    for index in range(62):
        insert(app,customer,identifier=f'estimated-{index:03}',issued='2011-01-01')
    insert(app,customer,identifier='pending',issued=None)
    app.historical_reviews.save('estimated-000',0,'18','Contraste',True,'Documento sintético completo')
    first = app.documents.list(review_state='estimated')
    second = app.documents.list(review_state='estimated',page=1)
    assert first['total'] == second['total'] == 61
    assert len(first['items']) == 50 and len(second['items']) == 11
    assert not ({row['id'] for row in first['items']} & {row['id'] for row in second['items']})
    assert all(row['historical_review']['state'] == 'estimated' for row in first['items']+second['items'])
    assert all('history' not in row['historical_review'] for row in first['items'])
    assert app.documents.list(review_state='pending_review')['total'] == 1
    assert app.documents.list(review_state='verified')['items'][0]['id'] == 'estimated-000'
    assert app.documents.list(review_state='estimated',query='NO SUCH NUMBER')['total'] == 0
    assert app.documents.list(review_state='estimated',customer_id='missing')['total'] == 0
    assert app.documents.list(review_state='estimated',kind='quote')['total'] == 0
    assert app.documents.list(page=100)['items'] == []
    assert app.documents.get(draft['id'])['historical_review'] is None
    with pytest.raises(AppError):
        app.documents.list(review_state='invalid')


def test_original_complete_and_reverted_history_cannot_be_reviewed(app,customer,draft):
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='historical',full_number='COMPLETE' WHERE id=?",(draft['id'],))
    assert app.documents.get(draft['id'])['historical_review'] is None
    with pytest.raises(AppError):
        app.historical_reviews.preview(draft['id'])
    identifier = insert(app,customer)
    app.documents.get(identifier)
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='import_reverted' WHERE id=?",(identifier,))
    for operation in (lambda:app.historical_reviews.preview(identifier),
                      lambda:app.historical_reviews.save(identifier,0,'21','Cambio'),
                      lambda:app.historical_reviews.reset(identifier,0,'Volver')):
        with pytest.raises(AppError) as caught:
            operation()
        assert caught.value.code == 'historical_review_unavailable'
    assert app.documents.list(review_state='estimated')['total'] == 0
