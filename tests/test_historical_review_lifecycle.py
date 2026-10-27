"""Historical review lifecycle uses synthetic records and disposable databases only."""
import base64
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest

from taller.access_mapping import source_key
from taller.db import Database, SCHEMA, SCHEMA_VERSION, dumps, migrate_connection
from taller.errors import AppError
from taller.historical_reviews import current_review, synchronize_defaults
from taller.migrations import MIGRATIONS, upgrade
from taller.migrations import v0009_historical_reviews
from taller.settings import DEFAULTS
from test_access_imports import finish, load_file
from test_access_partial import package


STAMP = '2026-01-01T00:00:00+00:00'


def historical_payload(amount='100.0050'):
    return {'historical': True, 'preservation': 'partial', 'payment_state': 'unknown',
            'date_state': 'known', 'amounts_state': 'unknown',
            'base_cents': None, 'tax_cents': None, 'total_cents': None,
            'customer': {'name': 'Cliente de ciclo sintético'}, 'issuer': {}, 'vehicle': None,
            'lines': [{'position': 1, 'description': 'Trabajo sintético', 'quantity': '1',
                       'unit_price': amount, 'amount_raw': amount, 'base_cents': None}],
            'taxes': [], 'amounts_provenance': {}}


def insert_historical(conn, identifier, customer_id, *, status='historical', amount='100.0050'):
    conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,
                    payload,base_cents,tax_cents,total_cents,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                 (identifier, 'invoice', status, customer_id, '2011-03-04', identifier,
                  dumps(historical_payload(amount)), None, None, None, STAMP, STAMP))


def create_v8(path):
    with sqlite3.connect(path, isolation_level=None) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        upgrade(conn, SCHEMA, migrations=tuple(m for m in MIGRATIONS if m.VERSION <= 8))
        conn.execute('INSERT INTO settings(id,data) VALUES(1,?)', (dumps(DEFAULTS),))
        conn.execute('''INSERT INTO customers(id,name,search_text,created_at,updated_at)
                        VALUES('synthetic-customer','Cliente sintético','cliente sintetico',?,?)''',
                     (STAMP, STAMP))
        insert_historical(conn, 'old-historical', 'synthetic-customer')
        insert_historical(conn, 'old-reverted', 'synthetic-customer', status='import_reverted')
        for identifier, status in [('old-complete', 'historical'), ('old-issued', 'issued')]:
            conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,
                            payload,base_cents,tax_cents,total_cents,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (identifier, 'invoice', status, 'synthetic-customer', '2011-03-04',
                          identifier, '{}', 10000, 1800, 11800, STAMP, STAMP))
        return conn.execute('SELECT * FROM documents ORDER BY id').fetchall()


def review_rows(conn, table='historical_review_versions'):
    return [tuple(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY document_id,version')]


def archive_database(path, version):
    raw = path.read_bytes()
    manifest = {'schema': version, 'created_at': STAMP, 'certificate_included': False,
                'files': {'taller.sqlite3': hashlib.sha256(raw).hexdigest()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('taller.sqlite3', raw)
    return base64.b64encode(output.getvalue()).decode()


def partial_archive(amount='100.0050'):
    return {'Clientes': [{'Cod_cli': 1, 'Cliente': 'Cliente importado sintético'}],
            'Facturas': [{'COD_CLI': 1, 'FACTURA': 17}],
            'DETALLE': [{'COD_CLI': 1, 'FACTURA': 17, 'CONCEPTO': 'Trabajo sintético',
                         'CANTIDAD': '1', 'PRECIO': amount, 'TOTAL': amount,
                         'FECHAFACTURA': '2011-03-04'}]}


def test_fresh_schema_has_empty_review_storage(app):
    with app.db.read() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        for table in ('historical_review_versions', 'historical_review_current', 'historical_review_pending'):
            assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0] == 0
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_v8_migration_materializes_active_and_reverted_without_rewriting_originals(tmp_path):
    root = tmp_path / 'synthetic-old'
    root.mkdir()
    original = create_v8(root / 'taller.sqlite3')
    database = Database(root)
    assert database.migration_result == {'from_version': 8, 'to_version': SCHEMA_VERSION,
                                         'applied': list(range(9, SCHEMA_VERSION + 1))}
    with database.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM documents ORDER BY id')] == original
        versions = conn.execute('SELECT document_id,version FROM historical_review_versions ORDER BY document_id').fetchall()
        assert [tuple(row) for row in versions] == [('old-historical', 0), ('old-reverted', 0)]
        assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 0
        before = review_rows(conn)
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    copies = list((root / 'backups').glob('pre-migration-v8-*.sqlite3'))
    assert len(copies) == 1
    with sqlite3.connect(copies[0]) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0] == 8
        assert old.execute('SELECT * FROM documents ORDER BY id').fetchall() == original
        assert not old.execute("SELECT name FROM sqlite_master WHERE name LIKE 'historical_review_%'").fetchall()
    assert Database(root).migration_result['applied'] == []
    with database.read() as conn:
        assert review_rows(conn) == before


def test_python_migration_failure_rolls_back_schema_defaults_and_version(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic-v8.sqlite3'
    original = create_v8(path)
    after = v0009_historical_reviews.after

    def fail_after_defaults(conn):
        after(conn)
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 2
        raise RuntimeError('Synthetic failure after Python materialization')

    with sqlite3.connect(path, isolation_level=None) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        with monkeypatch.context() as patch:
            patch.setattr(v0009_historical_reviews, 'after', fail_after_defaults)
            with pytest.raises(RuntimeError, match='Synthetic failure'):
                migrate_connection(conn)
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 8
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('SELECT * FROM documents ORDER BY id').fetchall() == original
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'historical_review_%'").fetchall()
        assert not conn.execute('SELECT 1 FROM schema_migrations WHERE version=9').fetchone()
        assert migrate_connection(conn)['applied'] == list(range(9, SCHEMA_VERSION + 1))
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 2


@pytest.mark.parametrize('mutation', ['insert', 'update'])
def test_direct_historical_changes_are_queued_then_materialized_on_read(app, customer, mutation):
    if mutation == 'update':
        draft = app.documents.save({'customer_id': customer['id'],
                                    'lines': [{'description': 'Borrador sintético', 'unit_price': '100'}]})
        identifier = draft['id']
    else:
        identifier = 'direct-insert'
    with app.db.transaction() as conn:
        if mutation == 'insert':
            insert_historical(conn, identifier, customer['id'])
        else:
            conn.execute('''UPDATE documents SET status='historical',full_number='DIRECT-UPDATE',
                            payload=?,base_cents=NULL,tax_cents=NULL,total_cents=NULL WHERE id=?''',
                         (dumps(historical_payload()), identifier))
        original = tuple(conn.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone())
        assert conn.execute('SELECT document_id FROM historical_review_pending WHERE document_id=?', (identifier,)).fetchone()
        assert not conn.execute('SELECT 1 FROM historical_review_current WHERE document_id=?', (identifier,)).fetchone()
    document = app.documents.get(identifier)
    assert document['base_cents'] is document['tax_cents'] is document['total_cents'] is None
    assert not document['payment_known'] and not document['can_rectify']
    with app.db.read() as conn:
        assert tuple(conn.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()) == original
        assert conn.execute('SELECT version FROM historical_review_current WHERE document_id=?', (identifier,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 0


def test_repeated_get_and_list_do_not_write_when_pending_queue_is_empty(app, customer, monkeypatch):
    with app.db.transaction() as conn:
        insert_historical(conn, 'read-only-repeat', customer['id'])
    app.documents.get('read-only-repeat')
    connect = app.db.connect

    def read_only_connection():
        conn = connect()
        conn.execute('PRAGMA query_only=ON')
        return conn

    monkeypatch.setattr(app.db, 'connect', read_only_connection)
    assert app.documents.get('read-only-repeat')['total_cents'] is None
    assert app.documents.list()['total'] == 1


def test_pending_materialization_failure_retains_entire_queue_without_partial_versions(app, customer, monkeypatch):
    import taller.historical_reviews as reviews

    with app.db.transaction() as conn:
        insert_historical(conn, 'pending-one', customer['id'])
        insert_historical(conn, 'pending-two', customer['id'])
    estimate = reviews.estimate
    calls = 0

    def fail_second(document, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Synthetic failure during queued materialization')
        return estimate(document, *args, **kwargs)

    with app.db.read() as conn:
        with monkeypatch.context() as patch:
            patch.setattr(reviews, 'estimate', fail_second)
            with pytest.raises(RuntimeError, match='Synthetic failure'):
                synchronize_defaults(conn)
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM historical_review_current').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 2
        assert not conn.in_transaction
        synchronize_defaults(conn)
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 0


def test_restore_v8_migrates_only_staging_under_untrusted_schema(app, tmp_path, monkeypatch):
    old_path = tmp_path / 'synthetic-v8.sqlite3'
    original = create_v8(old_path)
    before = old_path.read_bytes()
    after = v0009_historical_reviews.after
    trusted_values = []

    def verified_untrusted_after(conn):
        trusted_values.append(conn.execute('PRAGMA trusted_schema').fetchone()[0])
        return after(conn)

    monkeypatch.setattr(v0009_historical_reviews, 'after', verified_untrusted_after)
    preview = app.backups.preview(archive_database(old_path, 8))
    assert trusted_values == [0]
    assert preview['migration']['from_version'] == 8
    assert preview['migration']['to_version'] == SCHEMA_VERSION
    assert old_path.read_bytes() == before
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 0
    staged_path = app.backups.previews[preview['token']]['folder'] / 'taller.sqlite3'
    with sqlite3.connect(staged_path) as staged:
        staged.execute('PRAGMA trusted_schema=OFF')
        assert staged.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert staged.execute('SELECT * FROM documents ORDER BY id').fetchall() == original
        versions = review_rows(staged)
        assert len(versions) == 2
    result = app.backups.restore(preview['token'], 'RESTAURAR')
    assert result['restored']
    with app.db.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM documents ORDER BY id')] == original
        assert review_rows(conn) == versions
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_import_simulation_and_execution_materialize_independently(app, tmp_path):
    preview = load_file(app, package(tmp_path, partial_archive()))
    mapped = app.imports.map(preview['batch_id'], preview['profile'])
    assert mapped['incident_counts']['error'] == 0
    assert app.imports.simulate(preview['batch_id'], acknowledge_warnings=True)['done']
    simulated = app.imports._folder(preview['batch_id']) / 'simulation.sqlite'
    with sqlite3.connect(simulated) as conn:
        assert conn.execute('SELECT count(*) FROM historical_review_current').fetchone()[0] == 1
        assert conn.execute('SELECT version FROM historical_review_current').fetchone()[0] == 0
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 0
    assert app.imports.run(preview['batch_id'])['done']
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM historical_review_current').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 0
        document = conn.execute('SELECT * FROM documents').fetchone()
        assert document['base_cents'] is document['tax_cents'] is document['total_cents'] is None
        assert json.loads(document['payload'])['lines'][0]['amount_raw'] == '100.0050'
    assert app.imports.reconcile(preview['batch_id'])['balanced']


def test_persisted_v8_simulation_migrates_and_resumes_before_import(app, tmp_path):
    preview = load_file(app, package(tmp_path, partial_archive()))
    app.imports.map(preview['batch_id'], preview['profile'])
    progress = app.imports.simulate(preview['batch_id'], limit=1, acknowledge_warnings=True)
    assert not progress['done']
    simulated = app.imports._folder(preview['batch_id']) / 'simulation.sqlite'
    legacy = simulated.with_suffix('.v8.sqlite')
    # Build the actual v8 schema, then retain only data from its common tables.
    # This represents a saved simulation from the previous application version.
    with sqlite3.connect(simulated) as source, sqlite3.connect(legacy, isolation_level=None) as old:
        upgrade(old, SCHEMA, migrations=tuple(m for m in MIGRATIONS if m.VERSION <= 8))
        tables = [row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_migrations'")]
        for table in tables:
            columns = [row[1] for row in old.execute('PRAGMA table_info('+table+')')]
            rows = source.execute('SELECT '+','.join(columns)+' FROM '+table).fetchall()
            old.executemany('INSERT OR REPLACE INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', rows)
        assert old.execute('PRAGMA user_version').fetchone()[0] == 8
        assert not old.execute('PRAGMA foreign_key_check').fetchall()
    legacy.replace(simulated)
    while not app.imports.simulate(preview['batch_id'], limit=1)['done']:
        pass
    with sqlite3.connect(simulated) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert conn.execute('SELECT count(*) FROM historical_review_current').fetchone()[0] == 1
    assert app.imports.run(preview['batch_id'])['done']
    assert app.imports.reconcile(preview['batch_id'])['balanced']


def test_revisions_stay_with_each_original_through_replacement_and_rollback(app, tmp_path):
    first = load_file(app, package(tmp_path, partial_archive()))
    app.imports.map(first['batch_id'], first['profile'])
    assert finish(app, first['batch_id'])['balanced']
    original_id = app.documents.list()['items'][0]['id']
    original_review = app.historical_reviews.save(original_id, 0, '21', 'Hipótesis sintética inicial')
    assert original_review['version'] == 1

    replacement_data = partial_archive('110.0050')
    second = load_file(app, package(tmp_path, replacement_data, 'replacement.zip'), first['source_id'])
    key = 'invoices:'+source_key(replacement_data['Facturas'][0], ['COD_CLI', 'FACTURA'])
    mapped = app.imports.map(second['batch_id'], second['profile'],
                             {key: {'replace': True, 'reason': 'Copia sintética corregida del origen'}})
    assert mapped['incident_counts']['error'] == 0
    assert finish(app, second['batch_id'])['balanced']
    replacement_id = app.documents.list()['items'][0]['id']
    assert replacement_id != original_id
    assert app.documents.get(original_id)['status'] == 'import_reverted'
    with app.db.read() as conn:
        assert conn.execute('SELECT version FROM historical_review_current WHERE document_id=?', (original_id,)).fetchone()[0] == 1
        assert conn.execute('SELECT version FROM historical_review_current WHERE document_id=?', (replacement_id,)).fetchone()[0] == 0
    replacement_review = app.historical_reviews.save(replacement_id, 0, '16', 'Otra hipótesis para la copia sustituida')
    with app.db.read() as conn:
        versions = review_rows(conn)
    assert app.imports.rollback(second['batch_id'], 'Revertir únicamente la segunda copia')['originals_retained']
    assert app.documents.list()['items'][0]['id'] == original_id
    assert app.documents.get(replacement_id)['status'] == 'import_reverted'
    with app.db.read() as conn:
        assert review_rows(conn) == versions
        assert current_review(conn, original_id, history=True) == original_review
        assert current_review(conn, replacement_id, history=True) == replacement_review
    assert app.imports.rollback(first['batch_id'], 'Revertir el ensayo inicial conservando sus revisiones')['originals_retained']
    assert app.documents.list()['total'] == 0
    with app.db.read() as conn:
        assert review_rows(conn) == versions
        assert conn.execute('SELECT count(*) FROM documents WHERE total_cents IS NOT NULL').fetchone()[0] == 0
    with pytest.raises(AppError):
        app.historical_reviews.save(original_id, 1, '18', 'No debe editarse una histórica revertida')
    assert app.db.check_audit()['ok']


def test_backup_roundtrip_retains_selected_review_and_immutable_original(app, customer):
    with app.db.transaction() as conn:
        insert_historical(conn, 'backup-reviewed', customer['id'])
        original = tuple(conn.execute("SELECT * FROM documents WHERE id='backup-reviewed'").fetchone())
    reviewed = app.historical_reviews.save('backup-reviewed', 0, '21', 'Comparación sintética',
                                           verified=True, evidence='Documento de prueba sintético que acredita este resultado')
    backup = app.backups.create()
    app.historical_reviews.reset('backup-reviewed', 1, 'Restablecimiento posterior al punto de copia')
    preview = app.backups.preview(backup['content'])
    assert preview['migration']['applied'] == []
    assert app.backups.restore(preview['token'], 'RESTAURAR')['restored']
    with app.db.read() as conn:
        assert tuple(conn.execute("SELECT * FROM documents WHERE id='backup-reviewed'").fetchone()) == original
        current = current_review(conn, 'backup-reviewed', history=True)
        assert current == reviewed
        assert conn.execute('SELECT count(*) FROM historical_review_versions').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match='inalterable'):
            conn.execute("UPDATE historical_review_versions SET payload='{}' WHERE document_id='backup-reviewed'")
        with pytest.raises(sqlite3.IntegrityError, match='inalterable'):
            conn.execute("DELETE FROM historical_review_versions WHERE document_id='backup-reviewed'")
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    document = app.documents.get('backup-reviewed')
    assert document['total_cents'] is None and not document['payment_known'] and not document['can_rectify']
    assert app.db.check_audit()['ok']


def test_portable_preserves_reviews_pending_queue_and_originals_separately(app, customer):
    with app.db.transaction() as conn:
        insert_historical(conn, 'portable-reviewed', customer['id'])
    app.historical_reviews.save('portable-reviewed', 0, '18', 'Hipótesis sintética conservada')
    with app.db.transaction() as conn:
        insert_historical(conn, 'portable-pending', customer['id'])
    tables = ('documents', 'historical_review_versions', 'historical_review_current',
              'historical_review_pending')
    with app.db.read() as conn:
        before = {table: [dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                  for table in tables}
    result = app.reporting.portable()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['content']))) as archive:
        data = json.loads(archive.read('data.json'))
        manifest = json.loads(archive.read('manifest.json'))
        schema = json.loads(archive.read('schema.json'))
        assert data['schema_version'] == SCHEMA_VERSION
        for table in tables:
            assert data['tables'][table] == before[table]
            assert schema[table]['columns']
            assert 'csv/'+table+'.csv' in archive.namelist()
        for name, record in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == record['sha256']
        assert len(data['tables']['historical_review_versions']) == 2
        assert data['tables']['historical_review_pending'] == [{'document_id': 'portable-pending'}]
        assert all(row['total_cents'] is None for row in data['tables']['documents'])
    with app.db.read() as conn:
        after = {table: [dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                 for table in tables}
    assert after == before
