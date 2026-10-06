"""Independent synthetic integrity review of the partial Access path."""
import base64
import copy
import json

import pytest

from taller.access import Staging
from taller.access_mapping import canonical_historical
from taller.errors import AppError
from test_access_imports import finish, load_file
from test_access_partial import archive, package


def test_quarantined_duplicate_customer_blocks_new_attribution_even_after_prior_import(app, tmp_path):
    data = archive()
    first = load_file(app, package(tmp_path, data))
    app.imports.map(first['batch_id'], first['profile'])
    assert finish(app, first['batch_id'])['balanced']
    data['Clientes'].append({**data['Clientes'][0], 'Cliente': 'Otra identidad sintética'})
    data['Facturas'].append({'COD_CLI': 1, 'FACTURA': 90})
    data['DETALLE'].append({'COD_CLI': 1, 'FACTURA': 90, 'CONCEPTO': 'Atribución dudosa nueva', 'TOTAL': '9.1234'})
    second = load_file(app, package(tmp_path, data, 'ambiguous-later.zip'), first['source_id'])
    app.imports.map(second['batch_id'], second['profile'])
    with Staging(app.imports._folder(second['batch_id'])).connect() as conn:
        row = conn.execute("SELECT action FROM records WHERE entity='invoices' AND source_key=?", ('["1","90"]',)).fetchone()
        assert row['action'] == 'quarantine'


def test_explicit_invoice_skip_is_reflected_in_every_row_decision(app, tmp_path):
    review = load_file(app, package(tmp_path, archive()))
    app.imports.map(review['batch_id'], review['profile'], {
        'invoices:["1","7"]': {'skip': True, 'reason': 'Exclusión sintética documentada'},
    })
    with Staging(app.imports._folder(review['batch_id'])).connect() as conn:
        rows = conn.execute("SELECT entity,disposition FROM row_decisions WHERE source_key=? AND entity IN ('invoices','lines')", ('["1","7"]',)).fetchall()
        assert len(rows) == 4  # Both duplicate headers and both detail rows.
        assert all(row['disposition'] in ('skip', 'excluded') for row in rows)


def test_partial_preserves_explicit_unambiguous_invoice_vehicle_key(app, tmp_path):
    data = archive()
    for header in data['Facturas']:
        header['VEHICULO'] = '5678XYZ' if header.get('COD_CLI') == 4 else None
    review = load_file(app, package(tmp_path, data))
    profile = review['profile']
    profile['invoices']['vehicle_key'] = ['COD_CLI', 'VEHICULO']
    app.imports.map(review['batch_id'], profile)
    finish(app, review['batch_id'])
    with app.db.read() as conn:
        vehicle = conn.execute("SELECT id FROM vehicles WHERE plate='5678XYZ'").fetchone()
        document = conn.execute("SELECT vehicle_id FROM documents WHERE full_number='0' AND status='historical'").fetchone()
    assert vehicle is not None
    assert document is not None and document['vehicle_id'] == vehicle['id']


@pytest.mark.parametrize('number', [None, False, {'nested': 'not-a-number'}])
def test_partial_canonical_does_not_invent_invoice_numbers_by_stringifying_invalid_values(number):
    with pytest.raises(AppError):
        canonical_historical({'preservation': 'partial', 'full_number': number, 'issue_date': None, 'lines': []})


def test_partial_canonical_does_not_mutate_original_tax_breakdown():
    original = {'preservation': 'partial', 'full_number': 'SYN-1', 'issue_date': None, 'lines': [],
                'base_cents': 100, 'tax_cents': 16, 'total_cents': 116,
                'taxes': [{'base_cents': 100, 'tax_cents': 16}]}
    before = copy.deepcopy(original)
    canonical_historical(original)
    assert original == before


def test_partial_canonical_rejects_string_provenance_before_it_reaches_bootstrap():
    with pytest.raises(AppError):
        canonical_historical({'preservation': 'partial', 'full_number': 'SYN-1', 'issue_date': None,
                              'lines': [], 'amounts_provenance': 'not-json-or-a-provenance-object'})


def test_partial_invoice_with_quarantined_vehicle_keeps_history_without_assigning_owner(app, tmp_path):
    data = archive()
    for header in data['Facturas']:
        header['VEHICULO'] = '1234ABC' if header.get('COD_CLI') == 1 else None
    review = load_file(app, package(tmp_path, data))
    profile = review['profile']
    profile['invoices']['vehicle_key'] = ['COD_CLI', 'VEHICULO']
    mapped = app.imports.map(review['batch_id'], profile)
    assert mapped['incident_counts']['error'] == 0
    with Staging(app.imports._folder(review['batch_id'])).connect() as conn:
        warnings = [row['message'].casefold() for row in conn.execute(
            "SELECT message FROM incidents WHERE entity='invoices' AND source_key=? AND level='warning'", ('["1","7"]',))]
    assert any('vehículo' in warning and any(word in warning for word in ('revisión', 'cuarentena', 'titular')) for warning in warnings)
    assert finish(app, review['batch_id'])['balanced']
    with app.db.read() as conn:
        document = conn.execute("SELECT vehicle_id FROM documents WHERE full_number='7' AND status='historical'").fetchone()
    assert document is not None and document['vehicle_id'] is None


def test_complete_report_accounts_for_null_keys_and_dependent_quarantined_lines(app, tmp_path):
    data = archive()
    data['DETALLE'] = [data['DETALLE'][-1]]
    data['DETALLE'] += [{'COD_CLI': 1, 'FACTURA': None, 'CONCEPTO': f'No atribuible sintética {i}', 'TOTAL': '0.0050'} for i in range(281)]
    data['DETALLE'] += [{'COD_CLI': 3, 'FACTURA': 10, 'CONCEPTO': f'Cliente incompleto sintética {i}', 'TOTAL': '1.2345'} for i in range(45)]
    review = load_file(app, package(tmp_path, data))
    mapped = app.imports.map(review['batch_id'], review['profile'])
    assert mapped['incident_counts']['error'] == 0
    assert finish(app, review['batch_id'])['balanced']
    output = bytearray()
    offset = 0
    while True:
        chunk = app.imports.export_report_chunk(review['batch_id'], offset)
        output.extend(base64.b64decode(chunk['content']))
        if chunk['done']:
            break
        offset = chunk['next_offset']
    report = [json.loads(row) for row in output.splitlines()]
    raw = [item['value'] for item in report if item['type'] == 'raw_rows' and item['value']['table_name'] == 'DETALLE']
    assert len(raw) == 327
    assert [json.loads(row['data']) for row in sorted(raw, key=lambda value: value['row_number'])] == data['DETALLE']
    decisions = [item['value'] for item in report if item['type'] == 'row_decisions' and item['value']['entity'] == 'lines']
    assert len(decisions) == 327
    assert sum(row['rule'] == 'line_identity_incomplete' and row['disposition'] == 'quarantine' for row in decisions) == 281
    assert sum(row['rule'] == 'customer_identity_unresolved' and row['disposition'] == 'quarantine' for row in decisions) == 45
    assert sum(row['disposition'] == 'mapped' for row in decisions) == 1
