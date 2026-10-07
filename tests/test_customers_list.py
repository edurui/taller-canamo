"""Customer-list API semantics over isolated, synthetic SQLite data.

The compact list is for rendering/picking an identity. Editing still reads the
complete customer through customers.get. The global autocomplete is a separate
contract and retains its existing ranking and filtering behavior.
"""
import pytest


LIST_FIELDS = {'id', 'name', 'city', 'phone', 'tax_id', 'legacy_code', 'plates'}


def customer(app, name, **fields):
    return app.contacts.save_customer({'name': name, **fields})


def vehicle(app, owner, plate):
    return app.contacts.save_vehicle({'customer_id': owner['id'], 'plate': plate})


def identifiers(result):
    return [row['id'] for row in result['items']]


def test_customer_list_returns_compact_rendering_and_import_link_contract(app):
    saved = customer(app, 'Identidad sintética', city='Localidad sintética', phone='555 000 001',
                     tax_id='SYNTHETIC01', legacy_code='0001', address='Dirección de ensayo',
                     notes='NOTAS PRIVADAS SINTÉTICAS QUE NO NECESITA EL LISTADO')
    result = app.dispatch('customers.list')
    assert result['total'] == 1 and result['page'] == 0
    row = result['items'][0]
    assert set(row) == LIST_FIELDS
    assert row == {'id': saved['id'], 'name': saved['name'], 'city': saved['city'], 'phone': saved['phone'],
                   'tax_id': saved['tax_id'], 'legacy_code': '0001', 'plates': None}
    assert 'last_visit' not in row
    # A list response must never masquerade as the complete editable aggregate.
    complete = app.dispatch('customers.get', {'identifier': row['id']})
    assert complete['version'] == saved['version']
    assert complete['address'] == saved['address'] and complete['notes'] == saved['notes']


def test_empty_and_out_of_range_pages_keep_total_and_page_contract(app):
    assert app.contacts.list_customers() == {'items': [], 'total': 0, 'page': 0}
    saved = customer(app, 'Único cliente sintético')
    assert app.contacts.list_customers(page=9) == {'items': [], 'total': 1, 'page': 9}
    assert identifiers(app.contacts.list_customers()) == [saved['id']]
    assert app.contacts.list_customers(query='No existe sintético') == {'items': [], 'total': 0, 'page': 0}


def test_customer_pages_have_fifty_unique_customers_and_consistent_filtered_total(app):
    by_number = {}
    # Insertion order deliberately differs from display order.
    for number in reversed(range(55)):
        by_number[number] = customer(app, f'Paginación sintética {number:03d}')
    vehicle(app, by_number[0], '8000AAA')
    vehicle(app, by_number[0], '8001AAA')
    first = app.contacts.list_customers(query='paginacion sintetica', page=0)
    second = app.contacts.list_customers(query='PAGINACIÓN SINTÉTICA', page=1)
    end = app.contacts.list_customers(query='paginacion sintetica', page=2)
    assert first['total'] == second['total'] == end['total'] == 55
    assert len(first['items']) == 50 and len(second['items']) == 5 and end['items'] == []
    assert first['page'] == 0 and second['page'] == 1 and end['page'] == 2
    actual = identifiers(first) + identifiers(second)
    assert actual == [by_number[number]['id'] for number in range(55)]
    assert len(actual) == len(set(actual))
    assert identifiers(app.contacts.list_customers(query='paginacion sintetica', page=0)) == identifiers(first)


def test_list_order_and_name_matching_ignore_accents_case_and_extra_spaces(app):
    names = ['Zúñiga sintético', 'Álvaro sintético', 'Érica sintética', 'ÁNGEL sintético', 'Bernardo sintético', 'almendro sintético']
    saved = {name: customer(app, name) for name in names}
    assert [row['name'] for row in app.contacts.list_customers()['items']] == [
        'almendro sintético', 'Álvaro sintético', 'ÁNGEL sintético', 'Bernardo sintético', 'Érica sintética', 'Zúñiga sintético']
    for query in ('  ALVARO   SINTETICO ', 'álVaRo sintético', 'lvaro sint'):
        result = app.contacts.list_customers(query=query)
        assert result['total'] == 1 and identifiers(result) == [saved['Álvaro sintético']['id']]
    # Existing autocomplete remains accent insensitive too.
    assert [row['customer_id'] for row in app.contacts.search('ALVARO')] == [saved['Álvaro sintético']['id']]


def test_normalized_name_ties_retain_existing_insertion_order_across_pages(app):
    # Names compare equal after normalization. IDs deliberately disagree with
    # insertion order, so adding an ID tie-breaker would change the old result.
    variants = ['Álvaro sintético', 'ALVARO SINTÉTICO', 'alvaro sintetico']
    saved = [customer(app, variants[index % len(variants)],
                      id=f'00000000-0000-4000-8000-{100 - index:012d}')
             for index in range(52)]
    for query in ('', 'ALVARO', '  álvaro   sintético '):
        first = app.contacts.list_customers(query=query)
        second = app.contacts.list_customers(query=query, page=1)
        assert first['total'] == second['total'] == 52
        assert identifiers(first) + identifiers(second) == [row['id'] for row in saved]
        assert identifiers(app.contacts.list_customers(query=query, page=1)) == identifiers(second)


def test_no_vehicle_and_multiple_vehicles_never_drop_or_duplicate_customer(app):
    empty = customer(app, 'A sin vehículo sintético')
    multiple = customer(app, 'B varios vehículos sintético')
    vehicle(app, multiple, '1122ABC')
    vehicle(app, multiple, '0540-BZD')
    result = app.contacts.list_customers()
    assert result['total'] == 2 and identifiers(result) == [empty['id'], multiple['id']]
    assert result['items'][0]['plates'] is None
    # The previous owner-index scan aggregated in insertion order, not by plate.
    assert result['items'][1]['plates'] == '1122ABC, 0540-BZD'
    for query in ('0540-bzd', '0540 bzd', '0540BZD', '540'):
        match = app.contacts.list_customers(query=query)
        assert match['total'] == 1 and identifiers(match) == [multiple['id']]
        assert match['items'][0]['plates'] == '1122ABC, 0540-BZD'
    # Several matching vehicles still represent a single row in this list.
    vehicle(app, multiple, '1122DEF')
    for query in ('1122', '0540'):
        match = app.contacts.list_customers(query=query)
        assert match['total'] == 1 and identifiers(match) == [multiple['id']]
        assert match['items'][0]['plates'] == '1122ABC, 0540-BZD, 1122DEF'


@pytest.mark.parametrize('field,value,query', [
    ('legacy_code', '000123', '000123'),
    ('tax_id', 'SYNTHETIC77', 'synthetic77'),
    ('city', 'Población de ensayo', 'poblacion de ensayo'),
    ('phone', '555 111 222', '555111222'),
    ('phone2', '555 333 444', '555333444'),
    ('email', 'contrato@example.invalid', 'contrato@example.invalid'),
])
def test_list_retains_existing_contact_text_search_fields(app, field, value, query):
    expected = customer(app, 'Coincidencia sintética', **{field: value})
    other = customer(app, 'Otro cliente sintético')
    vehicle(app, other, '9876XYZ')
    result = app.contacts.list_customers(query=query)
    assert result['total'] == 1 and identifiers(result) == [expected['id']]


@pytest.mark.parametrize('marker', ['%', '_', '\\'])
def test_embedded_sql_wildcards_and_backslash_are_literal_customer_text(app, marker):
    expected = customer(app, 'Nombre' + marker + 'literal sintético')
    customer(app, 'NombreXliteral sintético')
    customer(app, 'NombreXXliteral sintético')
    unrelated = customer(app, 'Vehículo ajeno sintético')
    vehicle(app, unrelated, '9876XYZ')
    result = app.contacts.list_customers(query='Nombre' + marker + 'literal')
    assert result['total'] == 1 and identifiers(result) == [expected['id']]


@pytest.mark.parametrize('marker', ['%', '_', '\\'])
def test_symbol_only_query_preserves_current_empty_plate_normalization_behavior(app, marker):
    # This behavior predates the performance change: the normalized plate query
    # is empty, so the vehicle EXISTS branch matches any vehicle owner. Preserve
    # it here; changing that product behavior needs a separate explicit decision.
    literal = customer(app, 'A símbolo sintético ' + marker)
    owner = customer(app, 'B propietario sintético')
    vehicle(app, owner, '9876XYZ')
    customer(app, 'C sin vehículo ni símbolo')
    result = app.contacts.list_customers(query=marker)
    assert result['total'] == 2 and identifiers(result) == [literal['id'], owner['id']]
    assert app.contacts.search(marker) == []  # Autocomplete has a different existing contract.


def test_archived_customer_filter_is_exclusive_and_keeps_global_search_hidden(app):
    active = customer(app, 'Cliente activo sintético')
    archived = customer(app, 'Cliente archivado sintético')
    vehicle(app, archived, '7777ZZZ')
    app.contacts.archive_customer(archived['id'])
    assert identifiers(app.contacts.list_customers()) == [active['id']]
    result = app.contacts.list_customers(archived=True)
    assert result['total'] == 1 and identifiers(result) == [archived['id']]
    assert identifiers(app.contacts.list_customers(query='7777ZZZ', archived=True)) == [archived['id']]
    assert app.contacts.list_customers(query='7777ZZZ')['total'] == 0
    assert app.contacts.search('7777ZZZ') == []


def test_archived_vehicle_is_omitted_from_display_but_keeps_existing_list_filter_semantics(app):
    owner = customer(app, 'Propietario de vehículos sintéticos')
    retired = vehicle(app, owner, '3333OLD')
    vehicle(app, owner, '4444NEW')
    # Historical imports can contain archived vehicles; there is no archive-vehicle RPC.
    with app.db.transaction() as conn:
        conn.execute('UPDATE vehicles SET archived=1 WHERE id=?', (retired['id'],))
    row = app.contacts.list_customers()['items'][0]
    assert row['plates'] == '4444NEW'
    filtered = app.contacts.list_customers(query='3333OLD')
    assert filtered['total'] == 1 and identifiers(filtered) == [owner['id']]
    assert filtered['items'][0]['plates'] == '4444NEW'
    assert app.contacts.search('3333OLD') == []
    assert [row['customer_id'] for row in app.contacts.search('4444NEW')] == [owner['id']]


def test_new_edit_archive_and_restore_are_visible_immediately_in_list_and_search(app):
    original = customer(app, 'Zeta sintético', notes='Nota sintética conservada', legacy_code='EDIT-001')
    assert identifiers(app.contacts.list_customers()) == [original['id']]
    added = customer(app, 'Alfa sintético')
    assert identifiers(app.contacts.list_customers()) == [added['id'], original['id']]
    complete = app.contacts.customer(original['id'])
    changed = app.contacts.save_customer({**complete, 'name': 'Áarón sintético', 'city': 'Nueva localidad sintética'})
    result = app.contacts.list_customers()
    assert identifiers(result) == [original['id'], added['id']]
    assert result['items'][0]['city'] == changed['city']
    assert app.contacts.list_customers(query='Zeta')['total'] == 0
    assert [row['customer_id'] for row in app.contacts.search('aaron')] == [original['id']]
    app.contacts.archive_customer(original['id'])
    assert identifiers(app.contacts.list_customers()) == [added['id']]
    assert identifiers(app.contacts.list_customers(archived=True)) == [original['id']]
    assert app.contacts.search('aaron') == []
    app.contacts.archive_customer(original['id'], archived=False)
    assert identifiers(app.contacts.list_customers()) == [original['id'], added['id']]
    assert app.contacts.list_customers(archived=True)['total'] == 0
    assert [row['customer_id'] for row in app.contacts.search('aaron')] == [original['id']]
    assert app.contacts.customer(original['id'])['notes'] == 'Nota sintética conservada'


def test_vehicle_edit_and_transfer_update_plate_filter_without_duplicate_customers(app):
    first = customer(app, 'A primer propietario sintético')
    second = customer(app, 'B segundo propietario sintético')
    created = vehicle(app, first, '1111OLD')
    vehicle(app, first, '1112STAY')
    current = app.contacts.vehicle(created['id'])
    app.contacts.save_vehicle({**current, 'plate': '2222NEW'})
    assert app.contacts.list_customers(query='1111OLD')['total'] == 0
    assert identifiers(app.contacts.list_customers(query='2222NEW')) == [first['id']]
    current = app.contacts.vehicle(created['id'])
    app.contacts.transfer_vehicle(created['id'], second['id'], 'Transferencia sintética comprobada', current['version'])
    assert identifiers(app.contacts.list_customers(query='2222-new')) == [second['id']]
    assert [row['customer_id'] for row in app.contacts.search('2222NEW')] == [second['id']]
    rows = {row['id']: row for row in app.contacts.list_customers()['items']}
    assert rows[first['id']]['plates'] == '1112STAY' and rows[second['id']]['plates'] == '2222NEW'
    assert app.contacts.list_customers()['total'] == 2


def test_compact_list_matches_previous_query_results_for_mixed_synthetic_contacts(app):
    from taller.contacts import sql_like
    from taller.validation import normalized, plate

    first = customer(app, 'Álvaro sintético', legacy_code='LEGACY-001', phone='555 123 456')
    customer(app, 'ALVARO SINTÉTICO', city='Población de ensayo')
    customer(app, 'Nombre%literal sintético')
    customer(app, 'Nombre_literal sintético')
    customer(app, 'Nombre\\literal sintético')
    only_retired = customer(app, 'Vehículo retirado sintético')
    archived = customer(app, 'Archivado sintético')
    customer(app, 'Sin vehículo sintético')
    vehicle(app, first, '1122ABC')
    vehicle(app, first, '0540-BZD')
    vehicle(app, first, '1122DEF')
    retired = vehicle(app, only_retired, '3333OLD')
    vehicle(app, archived, '0540ZZZ')
    app.contacts.archive_customer(archived['id'])
    with app.db.transaction() as conn:
        conn.execute('UPDATE vehicles SET archived=1 WHERE id=?', (retired['id'],))

    # Freeze the pre-optimization query as a semantic oracle: it uses correlated
    # EXISTS and plate aggregation, independently of the new IN/batch strategy.
    # Compare only the intentionally retained public fields, including plate order.
    def previous_list(query, page, archived):
        query = normalized(query)[:100]
        params = [int(bool(archived))]
        condition = 'c.archived=?'
        if query:
            condition += " AND (c.search_text LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM vehicles vv WHERE vv.customer_id=c.id AND vv.plate_normalized LIKE ? ESCAPE '\\'))"
            params.extend(['%' + sql_like(query) + '%', '%' + sql_like(plate(query)) + '%'])
        with app.db.read() as conn:
            total = conn.execute('SELECT count(*) FROM customers c WHERE ' + condition, params).fetchone()[0]
            rows = conn.execute('''SELECT c.*,
                (SELECT group_concat(v.plate, ', ') FROM vehicles v WHERE v.customer_id=c.id AND v.archived=0) AS plates,
                (SELECT max(d.issue_date) FROM documents d WHERE d.customer_id=c.id AND d.kind='invoice') AS last_visit
                FROM customers c WHERE ''' + condition + ' ORDER BY normalized(c.name) LIMIT 50 OFFSET ?',
                (*params, max(0, int(page)) * 50))
            return {'items': [{key: row[key] for key in LIST_FIELDS} for row in rows], 'total': total, 'page': page}

    queries = ('', '   ', 'ÁLVARO', 'alvaro   sintetico', 'poblacion', 'legacy-001', '555123456',
               '0540-bzd', '0540 bzd', '0540', '1122', '3333OLD', 'Nombre%literal',
               'Nombre_literal', 'Nombre\\literal', '%', '_', '\\', 'No existe')
    for query in queries:
        for archived_flag in (False, True):
            for page in (0, 1):
                actual = app.contacts.list_customers(query=query, page=page, archived=archived_flag)
                assert actual == previous_list(query, page, archived_flag), (query, page, archived_flag)


def test_list_reads_only_required_columns_and_batches_page_plates_with_owner_index(app, monkeypatch):
    import sqlite3

    saved = [customer(app, f'Plan sintético {number:03d}', notes='Contenido que el listado no necesita')
             for number in range(52)]
    for number, owner in enumerate(saved):
        vehicle(app, owner, f'{9000 + number}IDX')
    statements = []
    reads = []
    connect = app.db.connect
    allowed_customer_columns = (LIST_FIELDS - {'plates'}) | {'archived', 'search_text', ''}

    def authorize(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_READ:
            reads.append((table, column))
            if table == 'documents' or (table == 'customers' and column not in allowed_customer_columns):
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def constrained_connection():
        connection = connect()
        connection.set_authorizer(authorize)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(app.db, 'connect', constrained_connection)
    result = app.contacts.list_customers(query='plan sintetico', page=1)
    assert result['total'] == 52 and identifiers(result) == [saved[50]['id'], saved[51]['id']]
    assert all(set(row) == LIST_FIELDS for row in result['items'])
    assert [row['plates'] for row in result['items']] == ['9050IDX', '9051IDX']
    batches = [statement for statement in statements if 'GROUP_CONCAT' in statement.upper()]
    assert len(batches) == 1
    batch = batches[0]
    assert all(row['id'] in batch for row in result['items'])
    assert all(owner['id'] not in batch for owner in saved[:50])
    with app.db.read() as conn:
        plan = [row['detail'] for row in conn.execute('EXPLAIN QUERY PLAN ' + batch)]
    assert any('idx_vehicle_owner' in step for step in plan), plan
    assert not any(table == 'documents' for table, _ in reads)
    assert not any('documents' in statement.lower() for statement in statements)
    statements.clear()
    assert app.contacts.list_customers(query='plan sintetico', page=99) == {'items': [], 'total': 52, 'page': 99}
    selects = [statement for statement in statements if statement.lstrip().upper().startswith('SELECT')]
    assert len(selects) == 1 and selects[0].upper().startswith('SELECT COUNT(*)')
