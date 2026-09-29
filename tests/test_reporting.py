"""Operational totals and portable originals, using only synthetic temporary data."""
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tracemalloc
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from taller.db import dumps
from taller.errors import AppError
from taller.reporting import Reporting, csv_bytes
from taller.backups import CHUNK_BYTES, INLINE_BYTES
from taller.validation import today


def historical(app, customer, number='H-1', day='2020-01-15', payment='unknown', total=12100):
    document = app.documents.save({'customer_id': customer['id'], 'issue_date': day,
                                   'lines': [{'description': 'Trabajo histórico sintético', 'unit_price': '100'}]})
    payload = {**document['payload'], 'historical': True, 'payment_state': payment,
               'customer': {'name': customer['name'], 'id': customer['id']}, 'issuer': {}, 'branding': {}}
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='historical',full_number=?,payload=?,total_cents=? WHERE id=?",
                     (number, dumps(payload), total, document['id']))
    return app.documents.get(document['id'])


def issued(app, customer, **changes):
    draft = app.documents.save({'customer_id': customer['id'], 'lines': [{'description': 'Trabajo sintético', 'unit_price': '100'}], **changes})
    return app.documents.publish(draft['id'])


def test_cash_separates_opening_balance_adjustments_actual_payments_and_reversals(app, customer):
    report = Reporting(app.db, app.settings)
    old = historical(app, customer)
    app.documents.record_payment_state(old['id'], 6000, 'Recibo sintético conservado', 'opening-report')
    app.documents.adjust_payment_state(old['id'], 5000, 'Corrección documental del recibo', 'adjust-report')
    paid = app.documents.pay(old['id'], '10', 'cash', today(), 'real-report')
    payment_id = next(p['id'] for p in paid['payments'] if p['method'] == 'cash')
    app.documents.reverse_payment(payment_id, 'El cobro real se devuelve')
    app.documents.pay(old['id'], '20', 'card', today(), 'card-report')
    unknown = historical(app, customer, number='H-UNKNOWN')
    reverted = historical(app, customer, number='H-REVERTED', payment='unpaid')
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='import_reverted' WHERE id=?", (reverted['id'],))
    rows = report.summary()
    assert rows['cash'] == {'count': 3, 'received_cents': 3000, 'returned_cents': 1000, 'net_cents': 2000, 'reversals': 1}
    assert rows['opening_adjustments'] == {'count': 1, 'amount_cents': -1000}
    assert rows['opening_balances'] == {'count': 1, 'paid_cents': 6000}
    assert rows['receivables']['receivable_cents'] == 5100
    assert rows['receivables']['unknown_documents'] == 1
    assert rows['billing']['count'] == 2
    assert report.summary(today(), today())['cash']['net_cents'] == 2000
    assert report.summary(today(), today())['billing']['count'] == 0


def test_reporting_has_no_24_month_truncation_and_filters_exact_dates(app, customer):
    for index in range(30):
        day = date(2020 + index // 12, index % 12 + 1, 15).isoformat()
        historical(app, customer, str(index), day)
    report = Reporting(app.db, app.settings)
    assert len(report.summary()['months']) == 30
    selection = report.summary('2020-02-15', '2020-03-14')
    assert selection['billing']['count'] == 1 and selection['months'][0]['month'] == '2020-02'
    with pytest.raises(AppError):
        report.summary('2020-03-01', '2020-02-01')


def test_credit_to_refund_does_not_hide_another_receivable(app, customer):
    original = issued(app, customer)
    credit = app.documents.rectify(original['id'], 'Devolución sintética completa')
    app.documents.publish(credit['id'])
    result = Reporting(app.db, app.settings).summary()
    assert result['billing']['total_cents'] == 0
    assert result['billing']['rectifications'] == 1
    assert result['receivables']['receivable_cents'] == 12100
    assert result['receivables']['refund_due_cents'] == 12100
    assert result['billing']['test_count'] == 2


def test_work_and_minimums_are_explicit_current_state(app, customer):
    supplier = app.catalogue.save_supplier({'name': 'Recambios sintéticos', 'phone': '600000005'})
    product = app.catalogue.save_product({'name': 'Filtro sintético', 'sku': '0007', 'min_stock': '2.5', 'supplier_id': supplier['id']})
    app.catalogue.move(product['id'], '1.250', 'Entrada inicial', 'minimum')
    order = issued(app, customer, kind='order')
    app.documents.change_status(order['id'], 'waiting_parts')
    quote = issued(app, customer, kind='quote')
    app.documents.change_status(quote['id'], 'accepted')
    result = Reporting(app.db, app.settings).summary()
    assert {(row['kind'], row['status']) for row in result['work']} == {('order', 'waiting_parts'), ('quote', 'accepted')}
    assert result['low_stock'][0]['units_to_minimum'] == '1.250'
    assert result['low_stock'][0]['supplier_phone'] == '600000005'


def test_csv_preserves_zero_and_snapshots_payload_with_formula_protection(app, customer):
    original = issued(app, customer, lines=[{'description': '=SUM(1;2)', 'quantity': '1', 'unit_price': '0', 'tax_rate': '0'}])
    app.contacts.save_customer({**customer, 'name': 'Nombre posterior'})
    report = Reporting(app.db, app.settings)
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(report.export('invoices')['content']).decode('utf-8-sig')), delimiter=';'))
    assert rows[0]['total_cents'] == '0' and rows[0]['tax_cents'] == '0'
    assert json.loads(rows[0]['payload'])['customer']['name'] == customer['name']
    lines = list(csv.DictReader(io.StringIO(base64.b64decode(report.export('document_lines')['content']).decode('utf-8-sig')), delimiter=';'))
    assert lines[0]['description'] == "'=SUM(1;2)" and lines[0]['unit_price'] == '0'
    assert lines[0]['customer_name'] == customer['name']
    assert original['id'] == lines[0]['document_id']
    special = csv_bytes([{'text': '\ufeff =CMD()', 'zero': 0, 'empty': None, 'code': '0008'}], ['text', 'zero', 'empty', 'code']).decode('utf-8-sig')
    assert "'\ufeff =CMD()" in special and "'0008" in special


def test_empty_csv_has_headers(app):
    content = base64.b64decode(Reporting(app.db, app.settings).export('invoices')['content']).decode('utf-8-sig')
    assert 'payload' in content and 'total_cents' in content and len(content.splitlines()) == 1


def test_portable_contains_original_rows_relations_resources_and_hashes_but_no_secrets(app, customer):
    original = issued(app, customer)
    electronic = app.b2b.prepare(original['id'], True)
    app.pdf(original['id'])
    imported = app.imports.preview('legacy_code,name,unmapped_column\nOLD,Cliente exportable,dato original\n')
    (app.db.root/'secure'/'certificate.dpapi').write_bytes(b'DO-NOT-EXPORT-PRIVATE-KEY')
    (app.db.root/'secure'/'assistant-key').write_bytes(b'DO-NOT-EXPORT-CREDENTIAL')
    app.settings.internal_update('assistant', 'api_key', 'DO-NOT-EXPORT-TOKEN')
    app.settings.internal_update('backup', 'external_directory', '/DO-NOT-EXPORT-PRIVATE-PATH')
    app.settings.internal_update('fiscal', 'certificate_info', {'subject': 'DO-NOT-EXPORT-CERTIFICATE'})
    raw = base64.b64decode(Reporting(app.db, app.settings).portable()['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        data = json.loads(archive.read('data.json'))
        assert manifest['format'] == 'canamo-portable-v1'
        assert set(archive.namelist()) == set(manifest['files']) | {'manifest.json'}
        for name, record in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == record['sha256']
            assert b'DO-NOT-EXPORT-' not in archive.read(name)
        documents = data['tables']['documents']
        assert len(documents) == 1 and json.loads(documents[0]['payload']) == original['payload']
        assert data['tables']['series'] and data['tables']['fiscal_records'] and data['tables']['audit']
        binary = data['tables']['b2b_source_files'][0]['content']['$binary']
        decoded = base64.b64decode(binary['data'])
        assert decoded == electronic['xml'].encode('utf-8')
        assert hashlib.sha256(decoded).hexdigest() == binary['sha256']
        assert archive.read('resources/pdfs/' + original['id'] + '.pdf').startswith(b'%PDF-')
        source = 'resources/imports/' + imported['batch_id'] + '/source.bin'
        assert b'dato original' in archive.read(source)
        assert json.loads(archive.read('schema.json'))['documents']['foreign_keys']
        assert 'certificate_info' not in data['settings']['fiscal']
        assert 'assistant' not in data['settings'] and 'backup' not in data['settings']
    with pytest.raises(AppError):
        app.backups.preview(base64.b64encode(raw).decode())


def test_export_rejects_unexpected_secret_resource_and_symlink(app, tmp_path):
    path = app.db.root/'assets'/'certificate.p12'
    path.write_bytes(b'not-an-image')
    with pytest.raises(AppError, match='certificados'):
        Reporting(app.db, app.settings).portable()
    path.unlink()
    target = tmp_path/'private.txt'
    target.write_text('private', encoding='utf-8')
    path.symlink_to(target)
    with pytest.raises(AppError, match='enlaces'):
        Reporting(app.db, app.settings).portable()


def test_recount_is_atomic_idempotent_and_rejects_stale_or_conflicting_operations(app):
    product = app.catalogue.save_product({'name': 'Pieza contada'})
    app.catalogue.move(product['id'], '10', 'Entrada', 'recount-in')
    args = dict(product_id=product['id'], target='7.5', expected_stock='10', reason='Recuento físico sintético', idempotency_key='recount-1')
    first = app.catalogue.adjust_stock(**args)
    assert app.catalogue.adjust_stock(**{**args, 'target': '7.50', 'expected_stock': '10.0'})['id'] == first['id']
    with pytest.raises(AppError, match='otra|otro'):
        app.catalogue.adjust_stock(**{**args, 'target': '6'})
    with pytest.raises(AppError, match='han cambiado'):
        app.catalogue.adjust_stock(**{**args, 'idempotency_key': 'stale'})
    assert Decimal(app.catalogue.products()[0]['stock']) == Decimal('7.5')
    with pytest.raises(AppError, match='cero'):
        app.catalogue.archive_product(product['id'])


def test_catalogue_revision_references_archival_and_document_return(app, customer):
    supplier = app.catalogue.save_supplier({'name': 'Proveedor revisable'})
    product = app.catalogue.save_product({'name': 'Última pieza', 'sku': 'abc', 'supplier_id': supplier['id']})
    with pytest.raises(AppError, match='referencia'):
        app.catalogue.save_product({'name': 'Duplicado', 'sku': 'ABC'})
    app.catalogue.move(product['id'], '1', 'Entrada', 'archival-in')
    with pytest.raises(AppError, match='ha cambiado'):
        app.catalogue.save_product({**product, 'name': 'Vista obsoleta'})
    document = issued(app, customer, stock_affect=True, lines=[{'description': 'Última pieza', 'product_id': product['id'], 'unit_price': '1'}])
    app.catalogue.archive_product(product['id'])
    assert not app.catalogue.products()
    app.documents.void(document['id'], 'Error material sintético', 'ANULAR')
    restored = app.catalogue.products()[0]
    assert Decimal(restored['stock']) == 1 and restored['archived'] == 0
    app.catalogue.archive_supplier(supplier['id'])
    assert not app.catalogue.suppliers()
    with pytest.raises(AppError, match='activo'):
        app.catalogue.save_product({'name': 'Nuevo material', 'supplier_id': supplier['id']})
    app.catalogue.archive_supplier(supplier['id'], False)
    assert app.catalogue.suppliers()[0]['name'] == supplier['name']


def test_portable_streams_rows_and_resources_with_bounded_memory_and_revokes_temporary_file(app, monkeypatch):
    # A normal accumulated customer table plus an incompressible stored PDF.
    with app.db.transaction() as conn:
        conn.executemany('INSERT INTO customers(id,name,search_text,notes,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                         ((f'stream-{index}', f'Cliente sintético {index}', f'stream {index}', 'N'*2048, today(), today()) for index in range(5000)))
    resource = app.db.root/'pdfs'/'synthetic-incompressible.pdf'
    with resource.open('wb') as output:
        for _ in range(6):
            output.write(os.urandom(CHUNK_BYTES))
    with resource.open('rb') as source:
        expected = hashlib.file_digest(source, 'sha256').hexdigest()
    original_read = Path.read_bytes
    def limited_read(path):
        assert path.stat().st_size<=INLINE_BYTES, 'Whole-file read of a large export or resource'
        return original_read(path)
    monkeypatch.setattr(Path, 'read_bytes', limited_read)
    tracemalloc.start()
    try:
        result = Reporting(app.db, app.settings, app.backups).portable()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak<24*1024**2
    assert 'content' not in result and result['bytes']>INLINE_BYTES
    target = app.backups.downloads[result['capability']]['path']
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['counts']['customers']==5000
        assert manifest['files']['resources/pdfs/synthetic-incompressible.pdf']['sha256']==expected
        with archive.open('data.json') as data:
            rows = json.load(data)['tables']['customers']
        assert len(rows)==5000 and rows[-1]['notes']=='N'*2048
    digest, offset = hashlib.sha256(), 0
    while offset<result['bytes']:
        part = app.backups.download_chunk(result['capability'], offset)
        chunk = base64.b64decode(part['content'])
        digest.update(chunk)
        offset += len(chunk)
    assert digest.hexdigest()==result['sha256']
    app.backups.release_download(result['capability'])
    assert not target.exists() and not list(app.db.root.glob('.portable-work-*'))


def test_export_temporaries_expire_but_retained_operational_backups_do_not(app):
    backup = app.backups.create()
    portable = Reporting(app.db, app.settings, app.backups).portable()
    target = app.backups.downloads[portable['capability']]['path']
    for result in (backup, portable):
        app.backups.downloads[result['capability']]['expires'] = datetime.now(timezone.utc)-timedelta(seconds=1)
    app.backups._expire_downloads()
    assert not target.exists()
    assert (app.db.root/'backups'/backup['name']).exists()
