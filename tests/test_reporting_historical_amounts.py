"""Consultation totals are useful without rewriting original financial evidence."""
import base64
import csv
import io
import json
from datetime import date

import pytest

from taller.access_mapping import source_key
from taller.db import dumps
from taller.errors import AppError
from taller.reporting import OVERVIEW_FIELDS
from test_access_imports import finish, load_file
from test_access_partial import package
from test_historical_review_lifecycle import partial_archive
from test_reporting import issued


def historical(app, customer, identifier, *, day='2020-01-15', amount='100',
               original=(None, None, None), status='historical', **metadata):
    payload = {'historical': True, 'preservation': 'partial', 'payment_state': 'unknown',
               'date_state': 'known' if day else 'unknown', 'invoice_type': 'F1',
               'base_cents': original[0], 'tax_cents': original[1], 'total_cents': original[2],
               'customer': {'name': 'Cliente original sintético'}, 'issuer': {}, 'taxes': [],
               'lines': [{'description': 'Trabajo sintético', 'amount_raw': amount}], **metadata}
    with app.db.transaction() as conn:
        conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,
            payload,base_cents,tax_cents,total_cents,created_at,updated_at)
            VALUES(?,'invoice',?,?,?,?,?,?,?,?,?,?)''',
                     (identifier, status, customer['id'], day, identifier, dumps(payload),
                      *original, '2026-01-01', '2026-01-01'))
    return identifier


def csv_rows(app, kind, **period):
    result = app.dispatch('data.export', {'kind': kind, **period})
    decoded = base64.b64decode(result['content']).decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded), delimiter=';')
    rows = list(reader)
    return reader.fieldnames, rows


def test_mixed_origins_count_each_invoice_once_and_keep_original_billing(app, customer):
    app.settings.save_series({'kind': 'invoice', 'label': 'Serie sintética 2020', 'year': 2020,
                              'prefix': 'SYN20-', 'padding': 4, 'next_number': 1})
    issued(app, customer, issue_date='2020-01-15')
    historical(app, customer, 'complete', original=(2000, 420, 2420))
    historical(app, customer, 'total-only', original=(None, None, 5000))
    historical(app, customer, 'zero', amount='0', original=(0, 0, 0))
    historical(app, customer, 'credit', amount='-10', original=(-1000, -210, -1210))
    historical(app, customer, 'estimated')
    historical(app, customer, 'verified', amount='200')
    app.historical_reviews.save('verified', 0, '18', 'Contraste sintético', True, 'Original sintético completo')
    historical(app, customer, 'unknown', amount=None)
    with app.db.read() as conn:
        originals = [tuple(row) for row in conn.execute('SELECT * FROM documents ORDER BY id')]
    result = app.dispatch('reports', {'start': '2020-01-01', 'end': '2020-01-31'})
    assert result['billing_overview'] == {
        'count': 8, 'amount_count': 7, 'unknown_count': 1, 'total_cents': 54010,
        'original_count': 5, 'original_cents': 18310, 'verified_count': 1,
        'verified_cents': 23600, 'estimated_count': 1, 'estimated_cents': 12100}
    assert result['overview_months'] == [{'month': '2020-01', **result['billing_overview']}]
    assert result['billing']['count'] == 4 and result['billing']['total_cents'] == 13310
    assert result['billing']['excluded_incomplete_count'] == 4
    assert result['months'][0]['total_cents'] == 13310
    assert result['cash']['net_cents'] == 0 and result['receivables']['receivable_cents'] == 12100
    with app.db.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM documents ORDER BY id')] == originals


@pytest.mark.parametrize('total', [0, -500, 12100])
def test_original_total_wins_even_with_incomplete_original_tax_fields(app, customer, total):
    historical(app, customer, 'known-total', original=(None, None, total))
    result = app.reports()['billing_overview']
    assert result['total_cents'] == result['original_cents'] == total
    assert result['amount_count'] == result['original_count'] == 1
    assert result['estimated_count'] == result['verified_count'] == result['unknown_count'] == 0


@pytest.mark.parametrize('amount,expected', [('0', 0), ('-10', -1210)])
def test_zero_and_negative_estimates_are_present_amounts(app, customer, amount, expected):
    historical(app, customer, 'signed-estimate', amount=amount)
    result = app.reports()['billing_overview']
    assert result['total_cents'] == result['estimated_cents'] == expected
    assert result['amount_count'] == result['estimated_count'] == 1 and result['unknown_count'] == 0


def test_unknown_only_period_is_null_but_empty_period_is_zero(app, customer):
    historical(app, customer, 'no-lines', lines=[])
    historical(app, customer, 'no-amount', amount=None)
    unknown = app.reports('2020-01-01', '2020-01-31')
    assert unknown['billing_overview']['count'] == unknown['billing_overview']['unknown_count'] == 2
    assert unknown['billing_overview']['amount_count'] == 0
    assert unknown['billing_overview']['total_cents'] is None
    assert unknown['overview_months'][0]['total_cents'] is None
    for source in ('original', 'verified', 'estimated'):
        assert unknown['billing_overview'][source + '_cents'] == 0
        assert unknown['billing_overview'][source + '_count'] == 0
    empty = app.reports('2019-01-01', '2019-12-31')
    assert empty['billing_overview'] == dict.fromkeys(OVERVIEW_FIELDS, 0)
    assert empty['overview_months'] == []


def test_months_include_unknowns_and_exact_boundaries_without_truncation(app, customer):
    for index in range(30):
        day = date(2020 + index // 12, index % 12 + 1, 15).isoformat()
        historical(app, customer, str(index), day=day, amount=None if index == 1 else '1')
    historical(app, customer, 'undated', day=None)
    result = app.reports()
    assert len(result['overview_months']) == 30
    assert result['overview_months'][0]['month'] == '2022-06'
    assert result['billing_overview']['count'] == 30
    assert result['billing_overview']['total_cents'] == 29 * 121
    assert result['billing']['undated_historical_count'] == 1
    selection = app.reports('2020-02-15', '2020-03-14')
    assert selection['overview_months'][0]['month'] == '2020-02'
    assert selection['billing_overview']['count'] == selection['billing_overview']['unknown_count'] == 1
    assert selection['billing_overview']['total_cents'] is None
    assert selection['billing']['undated_historical_count'] == 1
    assert app.reports('2020-03-15', '2020-03-15')['billing_overview']['total_cents'] == 121
    with pytest.raises(AppError):
        app.reports('2020-03-01', '2020-02-01')


def test_excluded_document_states_and_kinds_never_enter_overview(app, customer):
    historical(app, customer, 'active')
    historical(app, customer, 'reverted', status='import_reverted')
    historical(app, customer, 'conflicting', date_state='conflict')
    document = issued(app, customer)
    app.documents.void(document['id'], 'Anulación sintética', 'ANULAR')
    app.documents.save({'customer_id': customer['id'], 'lines': [{'description': 'Borrador', 'unit_price': '500'}]})
    issued(app, customer, kind='quote')
    issued(app, customer, kind='order')
    result = app.reports()['billing_overview']
    assert result['count'] == 2 and result['estimated_count'] == 1
    assert result['unknown_count'] == 1 and result['total_cents'] == 12100


def test_only_current_version_is_counted_and_report_reflects_reset(app, customer):
    historical(app, customer, 'reviewed')
    assert app.reports()['billing_overview']['estimated_cents'] == 12100
    app.historical_reviews.save('reviewed', 0, '18', 'Hipótesis sintética')
    assert app.reports()['billing_overview']['estimated_cents'] == 11800
    app.historical_reviews.save('reviewed', 1, '16', 'Contraste sintético', True, 'Original sintético consultado')
    result = app.reports()['billing_overview']
    assert result['count'] == result['verified_count'] == 1
    assert result['verified_cents'] == result['total_cents'] == 11600 and result['estimated_cents'] == 0
    app.historical_reviews.reset('reviewed', 2, 'Restablecer sugerencia por fecha')
    result = app.reports()['billing_overview']
    assert result['count'] == result['estimated_count'] == 1 and result['total_cents'] == 12100
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 4


@pytest.mark.parametrize('state,base', [('pending_review', 100), ('estimated', None), ('verified', None)])
def test_only_complete_available_reviews_can_be_summed(app, customer, state, base):
    historical(app, customer, 'defensive')
    with app.db.transaction() as conn:
        conn.execute('INSERT INTO historical_review_versions VALUES(?,0,?,?,?,?)',
                     ('defensive', state, dumps({'state': state, 'base_cents': base,
                         'tax_cents': 21, 'total_cents': 121}), 'automatic', '2026-01-01'))
    result = app.reports()['billing_overview']
    assert result['total_cents'] is None and result['amount_count'] == 0 and result['unknown_count'] == 1


def test_overview_materializes_once_then_reads_without_writes_or_per_invoice_queries(app, customer, monkeypatch):
    historical(app, customer, 'queued')
    connect = app.db.connect
    statements = []

    def traced_connect():
        conn = connect()
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(app.db, 'connect', traced_connect)
    assert app.reports()['billing_overview']['total_cents'] == 12100
    assert any(command.startswith('INSERT INTO historical_review_versions') for command in statements)
    assert statements.index('BEGIN') > statements.index('COMMIT')
    statements.clear()

    def read_only_connect():
        conn = traced_connect()
        conn.execute('PRAGMA query_only=ON')
        return conn

    monkeypatch.setattr(app.db, 'connect', read_only_connect)
    assert app.reports()['billing_overview']['total_cents'] == 12100
    queries = [command for command in statements if command.startswith('WITH amounts AS')]
    assert len(queries) == 1
    assert not any(command.startswith(('INSERT', 'UPDATE', 'DELETE', 'SAVEPOINT')) for command in statements)
    with app.db.read() as conn:
        plan = [row['detail'] for row in conn.execute('EXPLAIN QUERY PLAN ' + queries[0])]
    assert not any('CORRELATED' in step for step in plan)
    assert any('SEARCH h USING INDEX' in step and 'document_id=?' in step for step in plan)


def test_overview_csv_has_stable_origin_columns_and_original_exports_are_untouched(app, customer):
    fields, empty = csv_rows(app, 'billing_overview')
    assert fields == ['month', *OVERVIEW_FIELDS] and empty == []
    historical(app, customer, 'csv-estimate')
    historical(app, customer, 'csv-unknown', day='2020-02-15', amount=None)
    fields, rows = csv_rows(app, 'billing_overview', start='2020-01-01', end='2020-02-29')
    assert fields == ['month', *OVERVIEW_FIELDS]
    assert rows[0]['month'] == '2020-02' and rows[0]['total_cents'] == '' and rows[0]['unknown_count'] == '1'
    assert rows[1]['estimated_cents'] == rows[1]['total_cents'] == '12100'
    assert rows[1]['amount_count'] == '1' and rows[1]['original_count'] == '0'
    assert csv_rows(app, 'billing_overview', start='2020-02-01', end='2020-02-29')[1] == rows[:1]
    fields, originals = csv_rows(app, 'billing')
    assert fields == ['month', 'count', 'base_cents', 'tax_cents', 'total_cents'] and originals == []
    _, invoices = csv_rows(app, 'invoices')
    assert len(invoices) == 2 and all(row['total_cents'] == '' for row in invoices)
    assert all(json.loads(row['payload'])['total_cents'] is None for row in invoices)


def test_estimates_and_verified_reviews_do_not_enable_financial_operations(app, customer):
    historical(app, customer, 'protected')
    before = app.reports()
    app.historical_reviews.save('protected', 0, '21', 'Contraste sintético', True, 'Original de prueba')
    after = app.reports()
    assert after['billing_overview']['verified_cents'] == 12100
    for key in ('billing', 'months', 'cash', 'cash_months', 'opening_adjustments', 'opening_balances', 'receivables'):
        assert after[key] == before[key]
    assert after['receivables']['receivable_cents'] == after['receivables']['refund_due_cents'] == 0
    assert after['receivables']['unknown_documents'] == 1
    document = app.documents.get('protected')
    assert document['total_cents'] is None and not document['payment_known'] and not document['can_rectify']
    with pytest.raises(AppError):
        app.documents.pay('protected', '1', 'cash', '2020-01-15', 'blocked-payment')
    with pytest.raises(AppError):
        app.documents.rectify('protected', 'Rectificación sintética')
    assert not app.fiscal.records()


def test_replacement_and_nested_import_rollback_only_sum_active_original(app, tmp_path):
    first = load_file(app, package(tmp_path, partial_archive('100')))
    app.imports.map(first['batch_id'], first['profile'])
    assert finish(app, first['batch_id'])['balanced']
    original_id = app.documents.list()['items'][0]['id']
    app.historical_reviews.save(original_id, 0, '21', 'Hipótesis inicial sintética')
    assert app.reports()['billing_overview']['total_cents'] == 12100
    replacement = partial_archive('200')
    second = load_file(app, package(tmp_path, replacement, 'replacement.zip'), first['source_id'])
    key = 'invoices:' + source_key(replacement['Facturas'][0], ['COD_CLI', 'FACTURA'])
    app.imports.map(second['batch_id'], second['profile'],
                    {key: {'replace': True, 'reason': 'Copia sintética corregida'}})
    assert finish(app, second['batch_id'])['balanced']
    replacement_id = app.documents.list()['items'][0]['id']
    app.historical_reviews.save(replacement_id, 0, '16', 'Contraste de la copia sintética', True, 'Original sintético')
    result = app.reports()['billing_overview']
    assert result['count'] == result['verified_count'] == 1 and result['total_cents'] == 23200
    app.imports.rollback(second['batch_id'], 'Revertir segunda copia sintética')
    result = app.reports()['billing_overview']
    assert result['count'] == result['estimated_count'] == 1 and result['total_cents'] == 12100
    app.imports.rollback(first['batch_id'], 'Revertir primera copia sintética')
    assert app.reports()['billing_overview'] == dict.fromkeys(OVERVIEW_FIELDS, 0)
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM historical_review_current').fetchone()[0] == 2
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
