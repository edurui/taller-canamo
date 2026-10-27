"""Synthetic legacy vehicle descriptions remain visible, searchable and auditable."""
import json

import pytest

from test_access_imports import finish, load_file
from test_access_partial import package


def create_vehicle(app, owner, registration, **fields):
    return app.contacts.save_vehicle({'customer_id': owner['id'], 'plate': registration, **fields})['id']


def vehicle_import_record(app, identifier):
    with app.db.read() as conn:
        return dict(conn.execute("SELECT * FROM import_records WHERE entity='vehicles' AND target_id=?", (identifier,)).fetchone())


def test_imported_combined_description_survives_apis_and_edit_without_rewriting_evidence(app, tmp_path):
    description = 'Combi Ágil 50%_Especial\\Prueba'
    source_row = {'Cod_cli': '0042', 'Cliente': 'Cliente descripción sintética',
                  'Matricula': '7201TST', 'Tipo de Vehiculo': description}
    review = load_file(app, package(tmp_path, {'Clientes': [source_row]}))
    mapping = review['profile']['vehicles']['fields']
    assert mapping['kind'] == 'Tipo de Vehiculo'
    assert mapping['make'] == mapping['model'] == ''
    app.imports.map(review['batch_id'], review['profile'])
    assert finish(app, review['batch_id'])['balanced']

    item = app.contacts.vehicles_page()['items'][0]
    identifier = item['id']
    vehicle = app.contacts.vehicle(identifier)
    assert item['kind'] == vehicle['kind'] == description
    assert item['make'] == item['model'] == vehicle['make'] == vehicle['model'] == ''
    assert app.contacts.list_vehicles()[0]['kind'] == description
    assert app.contacts.customer(vehicle['customer_id'])['vehicles'][0]['kind'] == description
    assert vehicle['owners'][0]['reason'] == 'Importación: ' + review['batch_id']
    original_record = vehicle_import_record(app, identifier)
    assert json.loads(original_record['original_json'])['row'] == source_row
    imported_state = json.loads(original_record['imported_state'])
    assert imported_state['row']['kind'] == description
    assert imported_state['owners'][0]['reason'] == vehicle['owners'][0]['reason']

    app.contacts.save_vehicle({**vehicle, 'notes': 'Anotación posterior sintética'})
    edited = app.contacts.vehicle(identifier)
    assert edited['kind'] == description
    assert edited['make'] == edited['model'] == ''
    assert edited['owners'] == vehicle['owners']
    assert vehicle_import_record(app, identifier) == original_record
    assert app.db.check_audit()['ok']


@pytest.mark.parametrize('query,matching', [
    ('camion agil', 'both'),
    ('ÁGIL 50%', 'literal'),
    ('edicion_A', 'literal'),
    ('ruta\\B', 'literal'),
    ('sin coincidencia sintética', 'none'),
])
def test_kind_search_normalizes_accents_and_preserves_literal_like_characters(app, query, matching):
    owner = app.contacts.save_customer({'name': 'Titular sintético'})
    literal = create_vehicle(app, owner, '8001TST', kind='Camión Ágil 50% edición_A ruta\\B')
    other = create_vehicle(app, owner, '8002TST', kind='Camion agil 500 edicionXA rutaXB')
    expected = {'both': {literal, other}, 'literal': {literal}, 'none': set()}[matching]
    legacy = app.contacts.list_vehicles(query)
    paged = app.contacts.vehicles_page(query)
    assert {row['id'] for row in legacy} == expected
    assert {row['id'] for row in paged['items']} == expected
    assert paged['total'] == len(expected)


@pytest.mark.parametrize('query', ['marcaunica', 'modeloestrella', 'titular rafaga', '9010-TST',
                                 'modeloestrella titular rafaga'])
def test_make_model_customer_and_plate_search_are_preserved(app, query):
    owner = app.contacts.save_customer({'name': 'Titular Ráfaga'})
    identifier = create_vehicle(app, owner, '9010TST', make='MarcaÚnica', model='ModeloEstrella', kind='Turismo')
    assert [row['id'] for row in app.contacts.list_vehicles(query)] == [identifier]
    result = app.contacts.vehicles_page(query)
    assert result['total'] == 1
    assert [row['id'] for row in result['items']] == [identifier]


def test_kind_pagination_counts_active_vehicles_once_and_preserves_plate_order(app):
    owner = app.contacts.save_customer({'name': 'Primer titular sintético'})
    second_owner = app.contacts.save_customer({'name': 'Segundo titular sintético'})
    expected = []
    for number in reversed(range(53)):
        registration = f'{1000 + number}TST'
        identifier = create_vehicle(app, owner, registration, kind='Furgón histórico sintético')
        expected.append((registration, identifier))
    archived = create_vehicle(app, owner, '0999TST', kind='Furgón histórico sintético')
    create_vehicle(app, owner, '9999TST', kind='Otra descripción')
    with app.db.transaction() as conn:
        conn.execute('UPDATE vehicles SET archived=1 WHERE id=?', (archived,))
    transferred = app.contacts.vehicle(expected[0][1])
    app.contacts.transfer_vehicle(transferred['id'], second_owner['id'], 'Transferencia sintética', transferred['version'])
    assert len(app.contacts.vehicle(transferred['id'])['owners']) == 2

    first = app.contacts.vehicles_page('furgon historico', 0)
    second = app.contacts.vehicles_page('furgon historico', 1)
    past_end = app.contacts.vehicles_page('furgon historico', 2)
    assert first['total'] == second['total'] == past_end['total'] == 53
    assert [len(result['items']) for result in (first, second, past_end)] == [50, 3, 0]
    ids = [row['id'] for row in first['items'] + second['items']]
    assert ids == [identifier for _, identifier in sorted(expected)]
    assert len(set(ids)) == 53 and archived not in ids
    legacy = app.contacts.list_vehicles('furgon historico')
    assert len(legacy) == 53 and {row['id'] for row in legacy} == set(ids)
