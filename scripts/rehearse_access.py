"""Run a local isolated Access rehearsal; emit only sanitized counts, never rows.

The destination must not exist. The input is copied and hashed, never modified.
All private databases, evidence, PDF and backups remain inside that destination.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from taller.access import CHUNK_BYTES, Staging, digest_file
from taller.app import App


def check(condition, name):
    if not condition:
        raise RuntimeError('Rehearsal check failed: ' + name)


def rehearse(source, destination, rollback=True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    check(source.is_file() and source.suffix.lower() in ('.mdb', '.accdb'), 'input_format')
    check(not destination.exists(), 'destination_must_be_new')
    before = digest_file(source)
    destination.mkdir(mode=0o700, parents=True)
    copied = destination / ('input' + source.suffix.lower())
    shutil.copyfile(source, copied); copied.chmod(0o600)
    check(digest_file(copied) == before, 'copy_hash')
    started = time.monotonic()
    app = App(destination / 'data')
    with app.db.read() as conn:
        series = [dict(row) for row in conn.execute('SELECT * FROM series')]
    source_id = app.imports.source_save('Ensayo local aislado')['id']
    upload = app.imports.upload_start(copied.name, copied.stat().st_size, source_id)
    with copied.open('rb') as stream:
        offset = 0
        while chunk := stream.read(CHUNK_BYTES):
            app.imports.upload_chunk(upload['upload_id'], offset, base64.b64encode(chunk).decode())
            offset += len(chunk)
    diagnosed = app.imports.diagnose(upload['upload_id'])
    preview = app.imports.map(diagnosed['batch_id'], diagnosed['profile'])
    folder = app.imports._folder(preview['batch_id'])
    check(preview['incident_counts']['error'] == 0, 'preview_no_blockers')
    print(json.dumps({'phase': 'preview', 'counts': preview['counts'], 'actions': preview['actions'], 'blockers': preview['incident_counts']['error']}), flush=True)
    while not app.imports.simulate(preview['batch_id'], 500, acknowledge_warnings=True)['done']:
        pass
    check(app.contacts.list_customers()['total'] == 0, 'simulation_isolated')
    print(json.dumps({'phase': 'simulated'}), flush=True)
    while not app.imports.run(preview['batch_id'], 500)['done']:
        pass
    print(json.dumps({'phase': 'imported'}), flush=True)
    reconciliation = app.imports.reconcile(preview['batch_id'])
    check(reconciliation['balanced'], 'reconciliation')
    with Staging(folder).connect() as stage:
        raw_counts = {row[0]: row[1] for row in stage.execute('SELECT table_name,count(*) FROM raw_rows GROUP BY table_name')}
        for table in diagnosed['diagnostic']['tables']:
            if not table.get('linked'):
                check(raw_counts.get(table['name'], 0) == table['rows'], 'raw_table_count')
        row_decisions = [dict(row) for row in stage.execute('SELECT entity,disposition,rule,count(*) AS count FROM row_decisions GROUP BY entity,disposition,rule ORDER BY entity,disposition,rule')]
        line_accounting = stage.execute("SELECT count(*) FROM row_decisions WHERE entity='lines'").fetchone()[0]
        line_table = preview['profile'].get('lines', {}).get('table')
        if preview['profile'].get('options', {}).get('preservation') == 'partial':
            check(line_accounting == raw_counts.get(line_table, 0), 'every_detail_row_accounted')
        raw_rows = sum(raw_counts.values())
    with app.db.read() as conn:
        check(series == [dict(row) for row in conn.execute('SELECT * FROM series')], 'series_unchanged')
        check(conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0, 'no_fiscal_records')
        check(conn.execute('SELECT count(*) FROM fiscal_outbox').fetchone()[0] == 0, 'no_fiscal_queue')
        check(not conn.execute('PRAGMA foreign_key_check').fetchall(), 'foreign_keys')
        check(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'sqlite_integrity')
        vehicles = conn.execute('SELECT id,plate,customer_id FROM vehicles WHERE archived=0').fetchall()
        customers = conn.execute('SELECT id,legacy_code FROM customers WHERE archived=0').fetchall()
        docs = conn.execute("SELECT id,payload,issue_date FROM documents WHERE status='historical' ORDER BY id").fetchall()
        states = {}
        for document in docs:
            payload = json.loads(document['payload'])
            state = payload.get('date_state', 'known')
            states[state] = states.get(state, 0) + 1
        selected = {}
        for document in docs:
            payload = json.loads(document['payload'])
            selected.setdefault(payload.get('date_state', 'known'), document['id'])
            if not payload['lines']:
                selected.setdefault('no_lines', document['id'])
            if any(line.get('description') == '' for line in payload['lines']):
                selected.setdefault('no_description', document['id'])
            if any(line.get('amount_raw') and len(line['amount_raw'].partition('.')[2]) > 2 for line in payload['lines']):
                selected.setdefault('precise_decimal', document['id'])
    for vehicle in vehicles:
        check(any(item['vehicle_id'] == vehicle['id'] for item in app.contacts.search(vehicle['plate'], 100)), 'plate_search')
    for customer in customers:
        check(any(item['customer_id'] == customer['id'] for item in app.contacts.search(customer['legacy_code'], 100)), 'legacy_code_search')
    print(json.dumps({'phase': 'search_verified', 'vehicles': len(vehicles), 'customers': len(customers)}), flush=True)
    for identifier in selected.values():
        check(base64.b64decode(app.pdf(identifier)['content']).startswith(b'%PDF-'), 'historic_pdf')
    dashboard = app.dashboard()
    check(dashboard['pending_cents'] == 0 and dashboard['refund_due_cents'] == 0, 'unknown_payments_not_debt')
    report = app.reports()
    check(app.db.check_audit()['ok'], 'audit_chain')
    # Generate the complete private evidence stream, including raw unmapped tables.
    chunk = app.imports.export_report_chunk(preview['batch_id'])
    while not chunk['done']:
        chunk = app.imports.export_report_chunk(preview['batch_id'], chunk['next_offset'])
    summary = {
        'source_sha256': before, 'batch_id': preview['batch_id'], 'profile': preview['profile'],
        'counts': preview['counts'], 'actions': preview['actions'], 'incident_counts': preview['incident_counts'],
        'incident_groups': preview['incident_groups'], 'quarantine_groups': preview['quarantine_groups'],
        'reconciliation': {key: reconciliation[key] for key in ('balanced', 'totals', 'entity_counts')},
        'row_decisions': row_decisions, 'raw_rows': raw_rows, 'raw_counts': raw_counts, 'date_states': states,
        'search_checks': {'vehicles': len(vehicles), 'customers': len(customers)}, 'pdf_checks': len(selected),
        'dashboard': {key: dashboard[key] for key in ('customers', 'pending_cents', 'refund_due_cents', 'unknown_payment_documents')},
        'audit_ok': True, 'fiscal_records': 0, 'series_changed': False,
    }
    if rollback:
        reverted = app.imports.rollback(preview['batch_id'], 'Ensayo local: verificación de reversión sin borrar evidencia')
        check(reverted['originals_retained'], 'rollback_retains_sources')
        check(app.documents.list()['total'] == app.contacts.list_customers()['total'] == 0, 'rollback_active_records')
        with app.db.read() as conn:
            check(conn.execute('SELECT count(*) FROM vehicles WHERE archived=0').fetchone()[0] == 0, 'rollback_vehicles')
            check(conn.execute('SELECT count(*) FROM import_records WHERE active=1').fetchone()[0] == 0, 'rollback_identities')
            check(series == [dict(row) for row in conn.execute('SELECT * FROM series')], 'rollback_series')
        summary['rollback'] = {'completed': True, 'changes': reverted['changes'], 'active_records': 0, 'evidence_retained': True}
    check(digest_file(source) == digest_file(copied) == before, 'original_unchanged')
    summary.update(original_unchanged=True, elapsed_seconds=round(time.monotonic() - started, 3))
    (destination / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'phase': 'complete', 'reconciliation': summary['reconciliation'], 'date_states': states,
                      'raw_rows': raw_rows, 'rollback': summary.get('rollback'), 'elapsed_seconds': summary['elapsed_seconds']}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--keep-imported', action='store_true', help='Leave only this new isolated rehearsal imported for local inspection.')
    args = parser.parse_args()
    os.umask(0o077)
    rehearse(args.source, args.destination, not args.keep_imported)
