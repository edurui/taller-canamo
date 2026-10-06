"""Synthetic regression cases motivated by old Access archives; no workshop data."""
import json
import subprocess
import zipfile

import pytest

from taller.access import Staging, digest_file, java_command
from taller.access_mapping import source_key
from taller.errors import AppError
from test_access_imports import finish, load_file


def package(tmp_path, tables, name='partial.zip'):
    path = tmp_path / name
    manifest = {'format': 'canamo-access-raw-v1', 'tables': []}
    with zipfile.ZipFile(path, 'w') as output:
        for index, (name, rows) in enumerate(tables.items()):
            filename = f'table-{index}.jsonl'
            columns = sorted({key for row in rows for key in row})
            manifest['tables'].append({'name': name, 'rows': len(rows), 'file': filename, 'linked': False,
                                       'columns': [{'name': column, 'type': 'TEXT'} for column in columns]})
            output.writestr(filename, ''.join(json.dumps(row) + '\n' for row in rows))
        output.writestr('manifest.json', json.dumps(manifest))
    return path


def archive():
    return {
        'Clientes': [
            {'Cod_cli': 1, 'Cliente': 'Sintético uno', 'Matricula': '1234ABC', 'Codigo_postal': '01001'},
            {'Cod_cli': 2, 'Cliente': 'Sintético dos', 'Matricula': '1234-ABC', 'Codigo_postal': '01001'},
            {'Cod_cli': 3, 'Cliente': None, 'Matricula': None},
            {'Cod_cli': 4, 'Cliente': 'Sintético cuatro', 'Matricula': '5678XYZ'}],
        'Facturas': [
            {'COD_CLI': 1, 'FACTURA': 7}, {'COD_CLI': 1, 'FACTURA': 7},
            {'COD_CLI': 1, 'FACTURA': 8}, {'COD_CLI': None, 'FACTURA': 9},
            {'COD_CLI': 3, 'FACTURA': 10}, {'COD_CLI': 4, 'FACTURA': 0}],
        'DETALLE': [
            {'COD_CLI': 1, 'FACTURA': 7, 'CONCEPTO': 'A', 'CANTIDAD': '1.0000', 'PRECIO': '0.0050', 'TOTAL': '0.0050', 'FECHAFACTURA': '2010-01-01T00:00:00'},
            {'COD_CLI': 1, 'FACTURA': 7, 'CONCEPTO': '', 'CANTIDAD': '1.0000', 'PRECIO': '0.0050', 'TOTAL': '0.0050', 'FECHAFACTURA': '2011-01-01T00:00:00'},
            {'COD_CLI': 2, 'FACTURA': 9, 'CONCEPTO': 'Huérfana', 'CANTIDAD': '2', 'PRECIO': '1.2345', 'TOTAL': '2.4690', 'FECHAFACTURA': '2004-01-01'},
            {'COD_CLI': 2, 'FACTURA': None, 'CONCEPTO': 'No atribuible', 'TOTAL': '6.1234'},
            {'COD_CLI': 3, 'FACTURA': 10, 'CONCEPTO': 'Sin nombre de cliente', 'TOTAL': '2'},
            {'COD_CLI': 0, 'FACTURA': 11, 'CONCEPTO': 'Cliente cero ausente', 'TOTAL': '3'},
            {'COD_CLI': 4, 'FACTURA': 0, 'CONCEPTO': 'Número cero literal', 'TOTAL': None, 'FECHAFACTURA': '2005-01-01'}],
        'Codigos_Postal': [{'cp_codpos': '01001', 'cp_poblacion': 'Localidad sintética', 'cp_provincia': 'Provincia sintética'}],
        'Clientes 2004': [{'Cod_cli': 1, 'Cliente': 'Versión antigua sintética'}],
        'Detalle 2004': [{'COD_CLI': 1, 'FACTURA': 7, 'CONCEPTO': 'Versión antigua', 'TOTAL': '99.9999'}],
    }


def test_native_stale_row_counter_keeps_every_traversed_row(app, tmp_path):
    path = tmp_path / 'stale.mdb'
    subprocess.run([*java_command(), 'fixture', str(path), 'mdb-stale-count'], check=True)
    before = digest_file(path)
    review = load_file(app, path)
    table = next(table for table in review['diagnostic']['tables'] if table['name'] == 'Clientes')
    assert (table['rows'], table['reported_rows'], table['row_count_mismatch']) == (2, 1, True)
    assert digest_file(path) == before
    mapped = app.imports.map(review['batch_id'], review['profile'])
    assert mapped['counts']['customers'] == 2
    assert finish(app, review['batch_id'])['balanced']


def test_key_zero_is_valid_but_blank_whitespace_is_not():
    assert source_key({'x': 0}, ['x']) == '["0"]'
    assert source_key({'x': '000'}, ['x']) == '["000"]'
    for invalid in (None, '', '  ', '\t', [], {}, False):
        with pytest.raises(AppError):
            source_key({'x': invalid}, ['x'])


def test_cent_validation_never_rounds_to_decimal_context_precision():
    from taller.access_mapping import cents
    assert cents('0.010000000000000000000000000000000000000') == 1
    for value in ('0.009999999999999999999999999999999999999', '-0.009999999999999999999999999999999999999', '1e-1000000000'):
        with pytest.raises(AppError, match='fracciones de céntimo'):
            cents(value)


def test_partial_archive_complete_lifecycle_and_source_accounting(app, tmp_path):
    data = archive()
    review = load_file(app, package(tmp_path, data))
    assert review['profile']['options']['preservation'] == 'partial'
    assert review['profile']['customers']['joins'][0]['fields']['city'] == 'cp_poblacion'
    mapped = app.imports.map(review['batch_id'], review['profile'])
    assert mapped['incident_counts']['error'] == 0
    assert sum(group['count'] for group in mapped['quarantine_groups'] if group['entity'] == 'vehicles') == 2
    with app.db.read() as conn:
        series = [dict(row) for row in conn.execute('SELECT * FROM series')]
    reconciled = finish(app, review['batch_id'])
    assert reconciled['balanced']
    assert reconciled['totals']['destination_invoices'] == 4
    assert reconciled['totals']['destination_lines'] == 4
    assert reconciled['totals']['destination_unknown_total_cents'] == 4
    assert reconciled['totals']['source_total_cents'] is None
    assert reconciled['totals']['destination_total_cents'] is None
    assert reconciled['entity_counts']['customers']['destination'] == 3
    assert reconciled['entity_counts']['vehicles']['destination'] == 1
    documents = {item['full_number']: app.documents.get(item['id']) for item in app.documents.list()['items']}
    assert documents['7']['issue_date'] is None
    assert documents['7']['payload']['date_candidates'] == ['2010-01-01', '2011-01-01']
    assert documents['7']['payload']['lines'][0]['amount_raw'] == '0.0050'
    assert documents['7']['payload']['lines'][1]['description'] == ''
    assert documents['7']['payload']['lines'][0]['base_cents'] is None
    assert documents['8']['payload']['lines'] == []
    assert documents['9']['payload']['header_state'] == 'recovered_from_lines'
    assert documents['9']['payload']['lines'][0]['amount_raw'] == '2.4690'
    assert documents['0']['full_number'] == '0'
    assert all(item['total_cents'] is None and item['pending_cents'] is None for item in documents.values())
    assert app.dashboard()['pending_cents'] == 0
    with Staging(app.imports._folder(review['batch_id'])).connect() as conn:
        assert conn.execute('SELECT count(*) FROM raw_rows').fetchone()[0] == sum(map(len, data.values()))
        assert conn.execute("SELECT count(*) FROM row_decisions WHERE entity='lines'").fetchone()[0] == 7
        assert conn.execute("SELECT count(*) FROM row_decisions WHERE entity='invoices'").fetchone()[0] == 6
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0
        assert series == [dict(row) for row in conn.execute('SELECT * FROM series')]
        assert conn.execute("SELECT country FROM customers WHERE legacy_code='1'").fetchone()[0] == ''
    assert app.imports.rollback(review['batch_id'], 'Reversión sintética')['originals_retained']
    assert app.documents.list()['total'] == app.contacts.list_customers()['total'] == 0


def test_partial_reordered_customer_header_rows_do_not_fake_source_changes(app, tmp_path):
    data = archive()
    first = load_file(app, package(tmp_path, data))
    app.imports.map(first['batch_id'], first['profile']); finish(app, first['batch_id'])
    data['Clientes'].reverse(); data['Facturas'].reverse()
    second = load_file(app, package(tmp_path, data, 'reordered.zip'), first['source_id'])
    mapped = app.imports.map(second['batch_id'], second['profile'])
    assert mapped['incident_counts']['error'] == 0
    assert mapped['actions'].get('replace', 0) == 0
    assert mapped['actions']['unchanged'] == 8
    assert finish(app, second['batch_id'])['balanced']


def test_partial_subcent_does_not_round_or_apply_global_tax(app, tmp_path):
    review = load_file(app, package(tmp_path, archive()))
    profile = review['profile']
    profile['historical_calculation'] = {'tax_rate': '21', 'evidence': 'Synthetic formula without period evidence'}
    app.imports.map(review['batch_id'], profile)
    finish(app, review['batch_id'])
    with app.db.read() as conn:
        assert conn.execute("SELECT count(*) FROM documents WHERE total_cents IS NOT NULL").fetchone()[0] == 0
    # Sum before/after cent rounding differs: neither result may become an invoice total.
    from decimal import Decimal, ROUND_HALF_UP
    values = [Decimal('0.0050'), Decimal('0.0050')]
    assert sum(values).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) == Decimal('.01')
    assert sum(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for value in values) == Decimal('.02')


def test_explicit_partial_canonical_still_rejects_invalid_known_fields(app):
    from taller.access_mapping import canonical_historical
    base = {'preservation': 'partial', 'full_number': 'P', 'issue_date': None, 'lines': []}
    assert canonical_historical(base)['total_cents'] is None
    for fields in ({'total_cents': 0.5}, {'issue_date': 'wrong'}, {'paid_cents': 10}, {'lines': [{'amount_raw': 'NaN'}]}):
        with pytest.raises(AppError):
            canonical_historical({**base, **fields})


def test_partial_duplicate_customer_identity_is_quarantined_before_simulation(app, tmp_path):
    data = archive()
    data['Clientes'].append({**data['Clientes'][0], 'Cliente': 'Otra identidad sintética'})
    review = load_file(app, package(tmp_path, data))
    preview = app.imports.map(review['batch_id'], review['profile'])
    assert preview['incident_counts']['error'] == 0
    assert any(group['reason'] == 'duplicate_source_identity' and group['count'] == 2 for group in preview['quarantine_groups'] if group['entity'] == 'customers')
    assert finish(app, review['batch_id'])['balanced']
    with app.db.read() as conn:
        assert not conn.execute("SELECT 1 FROM customers WHERE legacy_code='1'").fetchone()
