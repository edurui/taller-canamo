"""Synthetic preservation cases: absence must never become a zero or today's date."""
import base64
import io
import csv
import json
import sqlite3

import pytest
from pypdf import PdfReader

from taller.db import Database, SCHEMA, dumps
from taller.errors import AppError
from taller.migrations import MIGRATIONS, upgrade
from taller.validation import today


def partial_history(app, draft, *, issue_date=None, amounts=(None, None, None), lines=None):
    payload = {**draft['payload'], 'historical': True, 'preservation': 'partial',
               'payment_state': 'known',  # A claimed receipt still cannot invent a total.
               'date_state': 'conflict' if issue_date is None else 'known',
               'base_cents': amounts[0], 'tax_cents': amounts[1], 'total_cents': amounts[2],
               'amounts_provenance': {'total_cents': {'state': 'unknown', 'reason': 'No original final total'}},
               'lines': [] if lines is None else lines, 'taxes': [], 'operation_date': None,
               'customer': {'name': 'Cliente histórico sintético'}, 'issuer': {}, 'branding': {},
               'kilometres': None, 'payment_method': 'unknown', 'footer': ''}
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='historical',full_number='H-PARTIAL',due_date='',payload=?,issue_date=?,base_cents=?,tax_cents=?,total_cents=? WHERE id=?",
                     (dumps(payload), issue_date, *amounts, draft['id']))
    return app.documents.get(draft['id'])


def test_unknown_totals_and_conflicting_dates_remain_null_everywhere(app, draft):
    document = partial_history(app, draft)
    assert document['issue_date'] is None and document['date_state'] == 'conflict'
    assert document['amounts_state'] == 'unknown'
    assert document['amounts_provenance']['total_cents']['state'] == 'unknown'
    assert document['paid_cents'] is None and document['pending_cents'] is None
    assert not document['payment_known'] and not document['can_rectify']
    listed = app.documents.list()['items'][0]
    assert listed['total_cents'] is None and listed['issue_date'] is None
    assert listed['date_state'] == 'conflict' and listed['amounts_state'] == 'unknown'
    assert listed['amounts_provenance'] == document['amounts_provenance']
    assert not listed['payment_known'] and listed['paid_cents'] is None
    history = app.assistance.history(customer_id=draft['customer_id'])['items'][0]
    assert history['total_cents'] is None and history['issue_date'] is None
    dashboard = app.dashboard()
    assert dashboard['pending_cents'] == dashboard['refund_due_cents'] == 0
    assert dashboard['unknown_payment_documents'] == 1
    assert not app.fiscal.records()


@pytest.mark.parametrize('action', ['receipt', 'opening', 'adjust_opening', 'rectify', 'save_rectification'])
def test_incomplete_history_cannot_create_balances_or_rectifications(app, draft, action):
    document = partial_history(app, draft)
    with pytest.raises(AppError) as caught:
        if action == 'receipt':
            app.documents.pay(document['id'], '1', 'cash', today(), 'synthetic-payment')
        elif action == 'opening':
            app.documents.record_payment_state(document['id'], 0, 'Synthetic receipt reviewed', 'synthetic-opening')
        elif action == 'adjust_opening':
            app.documents.adjust_payment_state(document['id'], 0, 'Synthetic receipt reviewed', 'synthetic-opening')
        elif action == 'rectify':
            app.documents.rectify(document['id'], 'Synthetic correction', operation_date='2001-01-01', lines=draft['payload']['lines'])
        else:
            app.documents.save({'kind': 'invoice', 'customer_id': draft['customer_id'], 'reference_id': document['id'],
                                'invoice_type': 'R4', 'notes': 'Synthetic correction', 'operation_date': '2001-01-01',
                                'lines': draft['payload']['lines']})
    assert caught.value.code in ('historical_amount_unknown', 'historical_incomplete')
    assert not app.documents.get(document['id'])['payments']
    assert app.documents.list()['total'] == 1


def test_partial_amounts_are_not_combined_into_false_report_totals(app, draft):
    document = partial_history(app, draft, issue_date='2001-02-03', amounts=(1000, None, None))
    assert document['amounts_state'] == 'partial'
    summary = app.reports('2001-01-01', '2001-12-31')
    assert summary['billing']['excluded_incomplete_count'] == 1
    assert summary['billing']['undated_historical_count'] == 0
    assert summary['billing']['count'] == 0 and summary['billing']['total_cents'] == 0
    assert summary['billing']['base_cents'] == 0 and summary['months'] == []
    assert summary['receivables']['unknown_documents'] == 1


def test_known_zero_remains_distinct_from_unknown(app, draft):
    document = partial_history(app, draft, issue_date='2001-02-03', amounts=(0, 0, 0))
    assert document['amounts_state'] == 'known' and document['date_state'] == 'known'
    assert document['payment_known'] and document['pending_cents'] == 0
    summary = app.reports('2001-01-01', '2001-12-31')
    assert summary['billing']['count'] == 1 and summary['billing']['excluded_incomplete_count'] == 0


def test_unconfirmed_date_is_counted_separately_and_preserved_by_full_csv_export(app, draft):
    partial_history(app, draft)
    assert app.reports()['billing']['undated_historical_count'] == 1
    assert app.reports('2001-01-01', '2001-12-31')['billing']['undated_historical_count'] == 1
    export = app.reporting.export('invoices')
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(export['content']).decode('utf-8-sig')), delimiter=';'))
    assert len(rows) == 1 and rows[0]['issue_date'] == rows[0]['total_cents'] == ''
    assert json.loads(rows[0]['payload'])['total_cents'] is None
    filtered = app.reporting.export('invoices', '2001-01-01', '2001-12-31')
    assert len(base64.b64decode(filtered['content']).decode('utf-8-sig').splitlines()) == 1
    with app.db.read() as conn:
        assert conn.execute('SELECT issue_date,total_cents FROM documents').fetchone()[:] == (None, None)


def test_pdf_shows_absence_and_exact_raw_amount_without_fabricating_fiscal_values(app, draft):
    document = partial_history(app, draft, lines=[{'description': '', 'quantity': None, 'unit_price': None,
                               'discount': None, 'base_cents': None, 'tax_cents': None, 'total_cents': None,
                               'amount_raw': '12.3456789', 'tax_rate': None, 'tax_kind': 'historical'}])
    content = base64.b64decode(app.pdf(document['id'])['content'])
    reader = PdfReader(io.BytesIO(content))
    text = ' '.join(' '.join(page.extract_text().split()) for page in reader.pages)
    assert 'No consta' in text and 'Fecha: No consta' in text
    assert 'Importe original sin clasificación fiscal: 12,3456789' in text
    assert '0,00 EUR' not in text and today() not in text and 'Vencimiento' not in text
    assert 'TOTAL No consta' in text and 'Histórico incompleto' in text
    assert len(reader.pages) == 1


def test_empty_historical_header_renders_without_lines(app, draft):
    document = partial_history(app, draft)
    content = base64.b64decode(app.pdf(document['id'])['content'])
    text = ' '.join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert 'No constan líneas en el archivo histórico.' in text


def test_database_still_rejects_nulls_for_new_documents_and_preserves_history(app, draft):
    with app.db.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
            conn.execute('UPDATE documents SET total_cents=NULL WHERE id=?', (draft['id'],))
        with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
            conn.execute('UPDATE documents SET issue_date=NULL WHERE id=?', (draft['id'],))
    document = partial_history(app, draft)
    with app.db.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError, match='modificar'):
            conn.execute('UPDATE documents SET total_cents=0 WHERE id=?', (document['id'],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE documents SET status='draft' WHERE id=?", (document['id'],))
        conn.execute("UPDATE documents SET status='import_reverted' WHERE id=?", (document['id'],))
    assert app.documents.list()['total'] == 0
    assert app.dashboard()['unknown_payment_documents'] == 0


def test_v7_migration_preserves_issued_snapshot_payment_and_foreign_keys(tmp_path):
    root = tmp_path / 'synthetic-old'; root.mkdir()
    with sqlite3.connect(root / 'taller.sqlite3', isolation_level=None) as conn:
        upgrade(conn, SCHEMA, migrations=MIGRATIONS[:-1])
        stamp = '2001-01-01T00:00:00Z'
        conn.execute('INSERT INTO customers(id,name,search_text,created_at,updated_at) VALUES(?,?,?,?,?)', ('c','Synthetic','synthetic',stamp,stamp))
        conn.execute("INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,base_cents,tax_cents,total_cents,created_at,updated_at) VALUES('d','invoice','issued','c','2001-01-01','SYN-1','{}',100,21,121,?,?)", (stamp,stamp))
        conn.execute("INSERT INTO payments VALUES('p','d',121,'cash','2001-01-01','',NULL,'synthetic-key',?)", (stamp,))
        before = conn.execute('SELECT * FROM documents').fetchall()
    database = Database(root)
    assert database.migration_result == {'from_version': 7, 'to_version': 8, 'applied': [8]}
    with database.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM documents')] == before
        assert conn.execute('SELECT amount_cents FROM payments').fetchone()[0] == 121
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert len(list((root / 'backups').glob('pre-migration-v7-*.sqlite3'))) == 1


@pytest.mark.parametrize('value', ['1E-1000000000', '1E+1000000000'])
def test_pdf_price_keeps_extreme_exponent_exact_without_expanding_it(value):
    from taller.pdf import unit_price_label
    label = unit_price_label(value)
    assert label == value + ' EUR' and len(label) < 40


def test_pdf_price_retains_real_decimal_precision_beyond_four_places():
    from taller.pdf import unit_price_label
    assert unit_price_label('0.123456789') == '0,123456789 EUR'
