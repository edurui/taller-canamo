"""Synthetic real Access files, identity across copies and conservative historic accounting."""
import base64
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from taller.access import CHUNK_BYTES, digest_file, java_command
from taller.access_mapping import source_key
from taller.errors import AppError
from taller.imports import Imports


def load_file(app, path, source_id=None):
    source_id = source_id or app.imports.source_save('Access sintético')['id']
    data = Path(path).read_bytes()
    upload = app.imports.upload_start(Path(path).name, len(data), source_id)
    for offset in range(0, len(data), CHUNK_BYTES):
        app.imports.upload_chunk(upload['upload_id'], offset, base64.b64encode(data[offset:offset + CHUNK_BYTES]).decode())
    return app.imports.diagnose(upload['upload_id'])


def finish(app, batch_id, limit=2):
    while not app.imports.simulate(batch_id, limit, acknowledge_warnings=True)['done']:
        pass
    while not app.imports.run(batch_id, limit)['done']:
        pass
    return app.imports.reconcile(batch_id)


def bundle():
    return {'format': 'canamo-import-v2', 'customers': [{'legacy_code': '0001', 'name': 'Cliente actual sintético', 'phone': '600000003'}],
            'vehicles': [{'legacy_customer_code': '0001', 'plate': '9999XYZ', 'km': 100}],
            'invoices': [{'legacy_key': '0001/0007', 'legacy_customer_code': '0001', 'full_number': '0007', 'issue_date': '2010-03-28',
                          'lines': [{'description': 'Trabajo IVA antiguo', 'quantity': '1.0000', 'unit_price': '10.0000', 'base_cents': 1000, 'tax_rate': '16'}],
                          'base_cents': 1000, 'tax_cents': 160, 'total_cents': 1160}]}


@pytest.mark.parametrize('extension', ['mdb', 'accdb'])
def test_real_access_readonly_link_refusal_compound_numbers_and_reimport(app, tmp_path, extension):
    path = tmp_path / ('Copia con tildes á.' + extension)
    subprocess.run([*java_command(), 'fixture', str(path), extension], check=True)
    before = digest_file(path)
    diagnosed = load_file(app, path)
    assert digest_file(path) == before
    diagnostic = diagnosed['diagnostic']
    assert diagnostic['links_followed'] == 0 and not diagnostic['expressions']
    assert next(table for table in diagnostic['tables'] if table['name'] == 'Vinculo_no_abrir')['linked']
    assert diagnostic['read_only'] and diagnostic['drivers_required'] is False
    profile = diagnosed['profile']
    mapped = app.imports.map(diagnosed['batch_id'], profile)
    assert mapped['incident_counts']['error'] == 0, mapped['errors']
    assert mapped['counts'] == {'customers': 2, 'vehicles': 2, 'invoices': 2}
    with app.db.read() as conn:
        series_before = [dict(row) for row in conn.execute('SELECT * FROM series')]
    result = finish(app, mapped['batch_id'], 1)
    assert result['balanced'] and result['totals']['source_total_cents'] == 3520
    assert result['totals']['source_lines'] == result['totals']['destination_lines'] == 2
    assert result['totals']['unknown_payment'] == 2
    invoices = app.documents.list()['items']
    assert len(invoices) == 2 and {invoice['full_number'] for invoice in invoices} == {'0007'}
    assert all(invoice['paid_cents'] is None for invoice in invoices)
    assert app.dashboard()['pending_cents'] == 0
    assert app.reports()['dashboard']['unknown_payment_documents'] == 2
    for invoice in invoices:
        document = app.documents.get(invoice['id'])
        assert document['payload']['customer'] == {} and document['payload']['issuer'] == {}
        assert document['payload']['snapshot_certainty']['customer'] == 'unknown'
        assert document['pending_cents'] is None
        assert document['fiscal_status'] is None
        assert base64.b64decode(app.pdf(invoice['id'])['content']).startswith(b'%PDF-')
        with pytest.raises(AppError):
            app.documents.pay(invoice['id'], 100, 'cash', '2026-09-23', idempotency_key='unexpected-payment-' + invoice['id'])
    with app.db.read() as conn:
        assert [dict(row) for row in conn.execute('SELECT * FROM series')] == series_before
        assert conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0
        assert conn.execute("SELECT original_json FROM import_records WHERE entity='customers' AND source_key=?", ('["001"]',)).fetchone()[0].find('Línea uno') != -1
    # Different file name and header bytes: record identities remain stable.
    copied = tmp_path / ('Copia final.' + extension)
    subprocess.run([*java_command(), 'fixture', str(copied), extension + '-copy'], check=True)
    assert digest_file(copied) != before
    second = load_file(app, copied, diagnosed['source_id'])
    repeated = app.imports.map(second['batch_id'], second['profile'])
    assert repeated['actions'] == {'unchanged': 6}
    assert finish(app, repeated['batch_id'])['balanced']
    assert app.documents.list()['total'] == 2
    assert app.db.check_audit()['ok']


def test_persistent_batches_simulation_and_resume_are_idempotent(app):
    preview = app.imports.preview(json.dumps(bundle()), 'json')
    identifier = preview['batch_id']
    app.imports.simulate(identifier, limit=1, acknowledge_warnings=True)
    assert app.contacts.list_customers()['total'] == 0
    app.imports = Imports(app.db, app.contacts, app.backups)
    while not app.imports.simulate(identifier, 1)['done']: pass
    first = app.imports.run(identifier, 1)
    assert first['cursor'] == 1 and not first['done']
    app.imports.pause(identifier)
    app.imports = Imports(app.db, app.contacts, app.backups)
    while not app.imports.run(identifier, 1)['done']: pass
    assert app.imports.run(identifier)['done']
    assert app.contacts.list_customers()['total'] == app.documents.list()['total'] == 1
    assert app.imports.reconcile(identifier)['balanced']


def test_changed_history_needs_explicit_replacement_and_keeps_original(app):
    data = bundle(); original = app.imports.preview(json.dumps(data), 'json'); finish(app, original['batch_id'])
    old_document = app.documents.list()['items'][0]['id']
    data['invoices'][0]['lines'][0]['description'] = 'Corrección documentada del origen'
    changed = app.imports.preview(json.dumps(data), 'json')
    assert changed['incident_counts']['error'] == 1
    key = 'invoices:' + source_key(data['invoices'][0], ['legacy_key'])
    mapped = app.imports.map(changed['batch_id'], changed['profile'], {key: {'replace': True, 'reason': 'Copia final corregida por el propietario'}})
    assert mapped['incident_counts']['error'] == 0
    finish(app, changed['batch_id'])
    assert app.documents.list()['total'] == 1
    new_document = app.documents.list()['items'][0]['id']
    assert new_document != old_document
    assert app.documents.get(old_document)['status'] == 'import_reverted'
    assert app.documents.get(old_document)['payload']['lines'][0]['description'] == 'Trabajo IVA antiguo'
    app.imports.rollback(changed['batch_id'], 'Ensayo de reversión')
    assert app.documents.list()['items'][0]['id'] == old_document
    assert app.documents.get(new_document)['status'] == 'import_reverted'


def test_rollback_preserves_later_activity_and_unknown_payment_baseline(app):
    data = bundle(); preview = app.imports.preview(json.dumps(data), 'json'); finish(app, preview['batch_id'])
    document = app.documents.list()['items'][0]['id']
    app.documents.record_payment_state(document, 0, 'Libro de cobros revisado', 'baseline-after-import')
    with pytest.raises(AppError, match='actividad posterior'):
        app.imports.rollback(preview['batch_id'], 'No debe borrar el saldo documentado')
    assert app.documents.list()['total'] == 1
    assert app.documents.get(document)['payment_known'] is True
    assert app.documents.get(document)['pending_cents'] == 1160


def test_rollback_archives_only_imported_records_and_preserves_evidence(app):
    preview = app.imports.preview(json.dumps(bundle()), 'json'); finish(app, preview['batch_id'])
    document = app.documents.list()['items'][0]['id']
    result = app.imports.rollback(preview['batch_id'], 'Ensayo terminado')
    assert result['originals_retained']
    assert app.documents.list()['total'] == app.contacts.list_customers()['total'] == 0
    assert app.documents.get(document)['status'] == 'import_reverted'
    assert (app.imports._folder(preview['batch_id']) / 'source.bin').is_file()
    assert app.imports.rollback(preview['batch_id'], 'Repetición idempotente')['already_reverted']


def test_historic_discrepancy_is_preserved_only_after_explicit_resolution(app):
    data = bundle(); data['invoices'][0]['total_cents'] = 1161
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['error'] == 1
    with pytest.raises(AppError): app.imports.simulate(preview['batch_id'], acknowledge_warnings=True)
    key = 'invoices:' + source_key(data['invoices'][0], ['legacy_key'])
    app.imports.map(preview['batch_id'], preview['profile'], {key: {'accept_difference': True, 'reason': 'El original impreso tiene un céntimo de ajuste'}})
    reconciliation = finish(app, preview['batch_id'])
    assert reconciliation['balanced']
    assert reconciliation['items'][0]['source_internal_differences']['base_tax_total_cents'] == -1
    assert app.documents.list()['items'][0]['total_cents'] == 1161


def test_upload_retry_and_invalid_package_paths(app):
    source = app.imports.source_save('Archivo adversarial')['id']; data = b'codigo;nombre\n001;Prueba\n'
    upload = app.imports.upload_start('copía.csv', len(data), source)
    first = base64.b64encode(data[:10]).decode()
    assert app.imports.upload_chunk(upload['upload_id'], 0, first)['received'] == 10
    assert app.imports.upload_chunk(upload['upload_id'], 0, first)['received'] == 10
    with pytest.raises(AppError): app.imports.upload_chunk(upload['upload_id'], 0, base64.b64encode(b'other-data').decode())
    with pytest.raises(AppError): app.imports.diagnose(upload['upload_id'])
    with pytest.raises(AppError): app.imports.upload_status('../../outside')


def test_more_than_300_issues_are_paged_and_exported_without_truncation(app):
    data = bundle(); data['invoices'] = [{**data['invoices'][0], 'legacy_key': 'L-' + str(index), 'full_number': 'N-' + str(index)} for index in range(101)]
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['warning'] == 404
    assert len(preview['incidents']) == 50
    assert len(app.imports.review(preview['batch_id'], page=8)['incidents']) == 4
    chunks = []; offset = 0
    while True:
        chunk = app.imports.export_report_chunk(preview['batch_id'], offset); chunks.append(base64.b64decode(chunk['content']))
        if chunk['done']: break
        offset = chunk['next_offset']
    evidence = [json.loads(line) for line in b''.join(chunks).splitlines()]
    assert sum(row['type'] == 'incidents' for row in evidence) == 404
