"""Synthetic cross-module contracts for partial import, rendering and identity review."""
import base64
from copy import deepcopy
import io
import json

import pytest
from pypdf import PdfReader

from taller.access import Staging
from taller.access_mapping import canonical_historical, source_key
from taller.errors import AppError
from test_access_imports import finish, load_file
from test_access_partial import archive, package


def canonical_bundle(invoices):
    return {'format': 'canamo-import-v2', 'customers': [{'legacy_code': 'S1', 'name': 'Cliente sintético de contrato'}],
            'invoices': [{'preservation': 'partial', 'legacy_customer_code': 'S1', 'issue_date': '2001-01-01', 'lines': [], **invoice}
                         for invoice in invoices]}


def test_partial_tax_defaults_render_and_discrepancies_require_explicit_acceptance(app):
    invoice = {'legacy_key': 'S1/H1', 'full_number': 'H1', 'base_cents': 100, 'tax_cents': 21, 'total_cents': 121,
               'taxes': [{'base_cents': 80, 'tax_cents': 15}]}
    data = canonical_bundle([invoice])
    canonical = canonical_historical(deepcopy(data['invoices'][0]))
    assert 'kind' not in data['invoices'][0]['taxes'][0]
    assert canonical['taxes'] == [{'base_cents': 80, 'tax_cents': 15, 'rate': '', 'kind': 'historical', 'reason': ''}]
    assert canonical['amount_differences']['tax_groups_base_cents'] == -20
    assert canonical['amount_differences']['tax_groups_tax_cents'] == -6
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['error'] == 1
    with pytest.raises(AppError):
        app.imports.simulate(preview['batch_id'], acknowledge_warnings=True)
    key = 'invoices:' + source_key(invoice, ['legacy_key'])
    reviewed = app.imports.map(preview['batch_id'], preview['profile'], {
        key: {'accept_difference': True, 'reason': 'Diferencia conservada según copia sintética revisada'}})
    assert reviewed['incident_counts']['error'] == 0
    result = finish(app, preview['batch_id'])
    assert result['balanced']
    assert result['items'][0]['source_internal_differences']['tax_groups_tax_cents'] == -6
    doc = app.documents.get(app.documents.list()['items'][0]['id'])
    assert (doc['base_cents'], doc['tax_cents'], doc['total_cents']) == (100, 21, 121)
    assert doc['payload']['taxes'][0]['tax_cents'] == 15
    content = base64.b64decode(app.pdf(doc['id'])['content'])
    text = ' '.join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert 'IVA histórico' in text and '0,15 EUR' in text and '1,21 EUR' in text


def test_linking_nameless_customer_imports_dependents_without_overwriting_target(app, tmp_path):
    data = archive()
    data['Clientes'][2]['Matricula'] = '9012DEF'
    target = app.contacts.save_customer({'legacy_code': 'TARGET-3', 'name': 'Identidad sintética revisada', 'country': 'PT'})
    review = load_file(app, package(tmp_path, data))
    key = 'customers:' + source_key(data['Clientes'][2], ['Cod_cli'])
    mapped = app.imports.map(review['batch_id'], review['profile'], {
        key: {'link': target['id'], 'reason': 'Identidad contrastada con referencia sintética'}})
    assert mapped['incident_counts']['error'] == 0
    staged = app.imports.records(review['batch_id'], entity='invoices')['items']
    dependent = next(row for row in staged if row['payload'].get('full_number') == '10')
    assert dependent['action'] == 'insert'
    with Staging(app.imports._folder(review['batch_id'])).connect() as conn:
        decision = conn.execute("SELECT disposition,rule FROM row_decisions WHERE entity='customers' AND source_key=?",
                                (source_key(data['Clientes'][2], ['Cod_cli']),)).fetchone()
        assert tuple(decision) == ('mapped', 'explicit_identity_link')
    assert finish(app, review['batch_id'])['balanced']
    doc = next(row for row in app.documents.list()['items'] if row['full_number'] == '10')
    assert doc['customer_id'] == target['id'] and doc['total_cents'] is None
    stored = app.documents.get(doc['id'])
    assert stored['payload']['customer'] == {}  # Linking current identity cannot invent its historical snapshot.
    actual = app.contacts.customer(target['id'])
    assert (actual['legacy_code'], actual['name'], actual['country']) == ('TARGET-3', 'Identidad sintética revisada', 'PT')
    assert any(vehicle['plate'] == '9012DEF' for vehicle in actual['vehicles'])
    with app.db.read() as conn:
        linked = conn.execute("SELECT target_id FROM import_records WHERE source_id=? AND entity='customers' AND source_key=?",
                              (review['source_id'], source_key(data['Clientes'][2], ['Cod_cli']))).fetchone()
        assert linked['target_id'] == target['id']


def test_vehicle_link_without_owner_key_fails_during_mapping_before_simulation(app, tmp_path):
    data = archive()
    data['Vehiculos'] = [{'vehicle_id': 'ORPHAN', 'owner_id': None, 'plate': '9013GHI', 'km': '123'}]
    owner = app.contacts.save_customer({'legacy_code': 'TARGET-V', 'name': 'Propietario sintético revisado'})
    target = app.contacts.save_vehicle({'customer_id': owner['id'], 'plate': '9013GHI', 'km': 123})
    review = load_file(app, package(tmp_path, data))
    profile = review['profile']
    profile['vehicles'] = {'table': 'Vehiculos', 'key': ['vehicle_id'], 'customer_key': ['owner_id'],
                           'fields': {'plate': 'plate', 'km': 'km'}}
    key = 'vehicles:' + source_key(data['Vehiculos'][0], ['vehicle_id'])
    with pytest.raises(AppError, match='clave de cliente fiable'):
        app.imports.map(review['batch_id'], profile, {
            key: {'link': target['id'], 'reason': 'No debe suplir una identidad de propietario ausente'}})
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM import_records').fetchone()[0] == 0
        assert conn.execute('SELECT customer_id FROM vehicles WHERE id=?', (target['id'],)).fetchone()[0] == owner['id']
    assert not (app.imports._folder(review['batch_id']) / 'simulation.sqlite3').exists()


def test_reconciliation_all_unknown_aggregates_are_null_with_explicit_counts(app, tmp_path):
    review = load_file(app, package(tmp_path, archive()))
    app.imports.map(review['batch_id'], review['profile'])
    totals = finish(app, review['batch_id'])['totals']
    assert totals['source_invoices'] == totals['destination_invoices'] == 4
    for prefix in ('source', 'destination'):
        for field in ('base_cents', 'tax_cents', 'total_cents'):
            assert totals[prefix + '_' + field] is None
            assert totals[prefix + '_unknown_' + field] == 4


def test_reconciliation_known_zero_is_not_mistaken_for_all_unknown(app):
    data = canonical_bundle([
        {'legacy_key': 'ZERO', 'full_number': 'ZERO', 'base_cents': 0, 'tax_cents': 0, 'total_cents': 0},
        {'legacy_key': 'UNKNOWN', 'full_number': 'UNKNOWN'},
    ])
    preview = app.imports.preview(json.dumps(data), 'json')
    totals = finish(app, preview['batch_id'])['totals']
    for prefix in ('source', 'destination'):
        for field in ('base_cents', 'tax_cents', 'total_cents'):
            assert totals[prefix + '_' + field] == 0
            assert totals[prefix + '_unknown_' + field] == 1
