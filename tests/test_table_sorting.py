"""Global ordering preserves pagination, absent values, originals and default order."""
from decimal import Decimal

import pytest

from taller.db import dumps
from taller.errors import AppError
from taller.sorting import STATUS_LABELS
from taller.validation import normalized


def ids(result):
    return [row['id'] for row in result['items']]


def pages(call, **options):
    first = call(**options)
    return first['items'] + [row for page in range(1, (first['total'] + 49) // 50)
                             for row in call(page=page, **options)['items']]


def expected(rows, key, direction='asc'):
    stable = sorted(rows, key=lambda row: row['id'])
    present = [row for row in stable if key(row) not in (None, '')]
    absent = [row for row in stable if key(row) in (None, '')]
    return [row['id'] for row in sorted(present, key=key, reverse=direction == 'desc') + absent]


def customers(app, count=65):
    with app.db.transaction() as conn:
        for index in reversed(range(count)):
            conn.execute('''INSERT INTO customers(id,name,city,phone,tax_id,legacy_code,search_text,archived,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (f'c{index:04}', ['Álvaro', 'ALVARO', 'Érica', 'Zeta'][index % 4],
                ['Ávila', 'Sevilla', ''][index % 3], '' if index % 5 == 0 else f'{index:03}',
                '' if index % 7 == 0 else f'SYN{index:03}', f'LEG{index:03}',
                'filtro %_\\ sintético' if index % 2 == 0 else 'otro sintetico',
                int(index == count-1), '2026-01-01', '2026-01-01'))
            for number in range(index % 3):
                value = f'{count-index:04}SYN{number}'
                conn.execute('''INSERT INTO vehicles(id,customer_id,plate,plate_normalized,make,model,kind,km,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''', (f'v{index:04}-{number}', f'c{index:04}', value, value,
                    '' if index % 4 == 0 else ['Álfa', 'Beta'][index % 2], '' if index % 4 == 0 else str(index % 3),
                    'Máquina' if index % 8 == 0 else '', index*10+number, '2026-01-01', '2026-01-01'))


@pytest.mark.parametrize('key', ['name', 'city', 'phone', 'tax_id', 'legacy_code', 'plates'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_customer_sort_is_global_stable_and_keeps_nulls_last(app, key, direction):
    customers(app)
    original = pages(app.contacts.list_customers)
    actual = pages(app.contacts.list_customers, sort_by=key, sort_direction=direction)
    assert len(actual) == 64 and len({row['id'] for row in actual}) == 64
    assert [row['id'] for row in actual] == expected(original, lambda row: normalized(row[key]), direction)
    assert {row['id']: row for row in actual} == {row['id']: row for row in original}


def test_customer_default_ties_filters_and_archive_remain_unchanged(app):
    customers(app)
    with app.db.read() as conn:
        before = [row[0] for row in conn.execute('SELECT id FROM customers WHERE archived=0 ORDER BY normalized(name)')]
    assert [row['id'] for row in pages(app.contacts.list_customers)] == before
    assert [row['id'] for row in pages(app.contacts.list_customers, sort_by='', sort_direction='desc')] == before
    filtered = pages(app.contacts.list_customers, query='filtro %_\\', sort_by='phone', sort_direction='desc')
    assert len(filtered) == 32 and all(int(row['id'][1:]) % 2 == 0 for row in filtered)
    assert [row['id'] for row in filtered] == expected(filtered, lambda row: row['phone'], 'desc')
    archived = app.contacts.list_customers(archived=True, sort_by='plates')
    assert archived['total'] == 1 and ids(archived) == ['c0064']
    assert app.contacts.list_customers(page=99, sort_by='plates')['items'] == []


@pytest.mark.parametrize('key', ['plate', 'description', 'customer_name', 'phone', 'km'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_vehicle_sort_matches_visible_description_and_numeric_km_before_paging(app, key, direction):
    customers(app, 80)
    original = pages(app.contacts.vehicles_page)
    def value(row):
        if key == 'km':
            return row['km']
        if key == 'description':
            return normalized(' '.join(part for part in [row['make'].strip(), row['model'].strip()] if part) or row['kind'])
        return normalized(row[key])
    actual = pages(app.contacts.vehicles_page, sort_by=key, sort_direction=direction)
    assert len(actual) > 50 and [row['id'] for row in actual] == expected(original, value, direction)
    assert {row['id']: row for row in actual} == {row['id']: row for row in original}
    with app.db.read() as conn:
        default = [row[0] for row in conn.execute('SELECT id FROM vehicles WHERE archived=0 ORDER BY plate,id')]
    assert [row['id'] for row in original] == default


def test_vehicle_legacy_limit_selects_global_sorted_300_and_keeps_query_filter(app):
    customers(app, 360)
    full = pages(app.contacts.vehicles_page, sort_by='km', sort_direction='desc')
    limited = app.contacts.list_vehicles(sort_by='km', sort_direction='desc')
    assert len(full) > 300 and limited == full[:300]
    filtered = app.contacts.vehicles_page(query='alfa', sort_by='plate')
    assert all(normalized(row['make']) == 'alfa' for row in filtered['items'])
    assert app.contacts.vehicles_page(query='%_\\', sort_by='plate')['total'] == 0


def documents(app, customer, count=65):
    with app.db.transaction() as conn:
        for index in reversed(range(count)):
            partial = index % 3 == 0
            total = None if partial else (index-30)*121
            missing_date = index % 13 == 0
            payload = {'historical': True, 'preservation': 'partial', 'payment_state': 'unknown' if partial else 'known',
                'date_state': 'unknown' if missing_date else 'known',
                'customer': {} if index % 2 else {'name': ['Álvaro', 'Zeta'][index % 4 // 2]},
                'vehicle': {'plate': f'SYN{index%10}'}, 'taxes': [],
                'lines': [{'amount_raw': None if index % 9 == 0 else str(index-30)}]}
            conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,due_date,full_number,payload,
                base_cents,tax_cents,total_cents,created_at,updated_at)
                VALUES(?,'invoice','historical',?,?,?,?,?,?,?,?,?,?)''',
                (f'd{index:04}', customer['id'], None if missing_date else f'2020-{index%12+1:02}-15',
                 '' if index % 5 == 0 else f'2021-{index%12+1:02}-15', f'SYN-{count-index:03}', dumps(payload),
                 None if partial else (index-30)*100, None if partial else (index-30)*21, total, '2026-01-01', '2026-01-01'))
            if not partial:
                conn.execute("INSERT INTO payments VALUES(?,?,?,'cash','2020-01-01','',NULL,?,'2026-01-01')",
                             (f'p{index}', f'd{index:04}', index%7, f'key{index}'))


def visible_total(row):
    if row['total_cents'] is not None:
        return row['total_cents']
    review = row.get('historical_review')
    return review['total_cents'] if review else None


@pytest.mark.parametrize('key', ['full_number', 'issue_date', 'due_date', 'customer_name', 'plate', 'total_cents', 'pending_cents'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_document_sorts_visible_amounts_identity_dates_and_known_balances_globally(app, customer, key, direction):
    documents(app, customer)
    original = pages(app.documents.list)
    def value(row):
        if key == 'total_cents':
            return visible_total(row)
        if key == 'pending_cents':
            return row['total_cents']-row['paid_cents'] if row['payment_known'] else None
        if key == 'customer_name':
            return normalized(row['customer_name'] or row['current_customer_name'])
        return normalized(row[key])
    actual = pages(app.documents.list, sort_by=key, sort_direction=direction)
    assert len(actual) == 65 and [row['id'] for row in actual] == expected(original, value, direction)
    assert {row['id']: row for row in actual} == {row['id']: row for row in original}
    with app.db.read() as conn:
        default = [row[0] for row in conn.execute("SELECT id FROM documents WHERE kind='invoice' AND status!='import_reverted' ORDER BY issue_date DESC,created_at DESC,id DESC")]
        assert conn.execute('SELECT count(*) FROM documents WHERE total_cents IS NULL').fetchone()[0] == 22
        assert not conn.execute('SELECT * FROM fiscal_records').fetchall()
    assert [row['id'] for row in original] == default


def test_document_original_total_precedes_review_and_unknown_dates_stay_last(app, customer):
    from test_reporting_historical_amounts import historical
    historical(app, customer, 'original-zero', original=(None, None, 0))
    historical(app, customer, 'original-negative', original=(None, None, -100))
    historical(app, customer, 'estimated', amount='100')
    historical(app, customer, 'verified', amount='100')
    app.historical_reviews.save('verified', 0, '18', 'Contraste sintético', True, 'Original sintético')
    historical(app, customer, 'unknown', amount=None)
    assert ids(app.documents.list(sort_by='total_cents')) == ['original-negative', 'original-zero', 'verified', 'estimated', 'unknown']
    assert ids(app.documents.list(sort_by='total_cents', sort_direction='desc')) == ['estimated', 'verified', 'original-zero', 'original-negative', 'unknown']
    assert ids(app.documents.list(sort_by='total_cents', review_state='verified')) == ['verified']
    assert app.documents.list(sort_by='total_cents', customer_id='missing')['total'] == 0


def test_document_filters_and_status_sort_use_visible_labels(app, customer):
    documents(app, customer)
    selected = app.documents.list(query='SYN-0', sort_by='issue_date', sort_direction='asc')
    assert selected['total'] == 65
    assert app.documents.list(query='%_\\', sort_by='full_number')['total'] == 0
    with app.db.transaction() as conn:
        for identifier, state in [('void', 'void'), ('draft', 'draft'), ('issued', 'issued')]:
            conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,payload,
                base_cents,tax_cents,total_cents,created_at,updated_at)
                VALUES(?,'invoice',?,?,'2020-01-01','{}',0,0,0,'2026-01-01','2026-01-01')''',
                         (identifier, state, customer['id']))
    ordered = pages(app.documents.list, sort_by='status')
    assert [row['status'] for row in ordered[:3]] == ['void', 'draft', 'issued']
    assert [row['id'] for row in ordered] == expected(ordered, lambda row: normalized(STATUS_LABELS[row['status']]))
    assert {row['status'] for row in pages(app.documents.list, status='historical', sort_by='status')} == {'historical'}


def test_movements_sort_exact_decimals_across_two_hundred_row_boundary(app):
    product = app.catalogue.save_product({'name': 'Artículo sintético'})
    values = ['10', '2', '1.010', '1.001', '-2', '0.100', '0.1']
    with app.db.transaction() as conn:
        for index in range(205):
            conn.execute('INSERT INTO stock_movements VALUES(?,?,?,?,NULL,?,?)',
                (f'm{index:04}', product['id'], values[index%len(values)], ['Álfa', 'ALFA', 'Zeta'][index%3],
                 f'move-{index}', '2020-01-01T00:00:00+00:00'))
    default = app.catalogue.movements(product['id']) + app.catalogue.movements(product['id'], page=1)
    assert [row['id'] for row in default] == [f'm{index:04}' for index in reversed(range(205))]
    for direction in ('asc', 'desc'):
        for key in ('quantity', 'reason', 'created_at'):
            rows = app.catalogue.movements(product['id'], sort_by=key, sort_direction=direction)
            rows += app.catalogue.movements(product['id'], page=1, sort_by=key, sort_direction=direction)
            value = (lambda row: Decimal(row['quantity'])) if key == 'quantity' else lambda row: normalized(row[key])
            assert [row['id'] for row in rows] == expected(default, value, direction)
    assert app.catalogue.movements('absent', sort_by='quantity') == []


def test_b2b_sort_is_global_before_limit_and_retains_default_and_filter(app):
    with app.db.transaction() as conn:
        for index in reversed(range(65)):
            conn.execute('''INSERT INTO b2b_documents VALUES(?,NULL,?,'UBL','<synthetic/>',?,'SYN-ISSUER','SYN-RECIPIENT',?,?,'EUR',?,1,'{}',?)''',
                (f'b{index:04}', 'inbound' if index%2 else 'outbound', f'digest{index}', f'SYN{65-index:03}',
                 f'2020-{index%12+1:02}-15', (index-30)*100, '2026-01-01'))
    default = pages(app.b2b.list)
    assert [row['id'] for row in default] == sorted(row['id'] for row in default)
    for direction in ('asc', 'desc'):
        for key in ('invoice_number', 'issue_date', 'total_cents', 'direction'):
            def value(row):
                if key == 'direction':
                    return 'Preparada' if row['direction'] == 'outbound' else 'Recibida'
                return row[key] if key == 'total_cents' else normalized(row[key])
            actual = pages(app.b2b.list, sort_by=key, sort_direction=direction)
            assert [row['id'] for row in actual] == expected(default, value, direction)
    assert all(row['direction'] == 'inbound' for row in pages(app.b2b.list, direction='inbound', sort_by='total_cents'))
    assert app.b2b.list(query='%_\\', sort_by='invoice_number')['total'] == 0


def test_fiscal_global_sort_uses_visible_labels_before_three_hundred_row_limit(app, customer):
    with app.db.transaction() as conn:
        for index in range(305):
            conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
                base_cents,tax_cents,total_cents,created_at,updated_at)
                VALUES(?,'invoice','issued',?,'2020-01-01',?,'{}',0,0,0,'2026-01-01','2026-01-01')''',
                         (f'fdoc{index:04}', customer['id'], f'SYN{305-index:04}'))
            conn.execute('''INSERT INTO fiscal_records(id,document_id,kind,environment,payload,xml,hash,
                previous_hash,created_at,idempotency_key) VALUES(?,?,?,?,'{}','<synthetic/>',?,'',?,?)''',
                         (f'f{index:04}', f'fdoc{index:04}', ['alta', 'anulacion', 'subsanacion'][index%3],
                          ['local_test', 'production', 'aeat_test'][index%3], f'hash{index}',
                          f'2020-{index%12+1:02}-15', f'fkey{index}'))
            conn.execute('INSERT INTO fiscal_outbox(record_id,status,next_attempt,updated_at) VALUES(?,?,?,?)',
                         (f'f{index:04}', ['accepted', 'pending', 'local_only'][index%3], '2026-01-01', '2026-01-01'))
        original = [dict(row) for row in conn.execute('''SELECT r.*,o.status,d.full_number FROM fiscal_records r
            JOIN fiscal_outbox o ON o.record_id=r.id JOIN documents d ON d.id=r.document_id ORDER BY r.seq''')]
    assert [row['seq'] for row in app.fiscal.records()] == list(reversed(range(6, 306)))
    for key in ('full_number', 'kind', 'environment', 'status', 'created_at'):
        def value(row):
            label = row[key]
            if key == 'status':
                label = STATUS_LABELS[label]
            if key == 'environment':
                label = {'local_test': 'Local', 'production': 'AEAT producción', 'aeat_test': 'AEAT pruebas'}[label]
            return normalized(label)
        for direction in ('asc', 'desc'):
            actual = app.fiscal.records(sort_by=key, sort_direction=direction)
            wanted = sorted(original, key=value, reverse=direction == 'desc')[:300]
            assert [row['id'] for row in actual] == [row['id'] for row in wanted]
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM fiscal_attempts').fetchone()[0] == 0


def test_balance_sort_includes_opening_baseline_and_reversals_without_inventing_receipts(app, customer):
    from test_reporting import historical
    first = historical(app, customer, 'H1', payment='unknown', total=12100)
    app.documents.record_payment_state(first['id'], 6000, 'Recibo sintético', 'opening-sort')
    paid = app.documents.pay(first['id'], '20', 'cash', '2020-01-15', 'receipt-sort')
    payment = next(row for row in paid['payments'] if row['method'] == 'cash')
    app.documents.reverse_payment(payment['id'], 'Reversión sintética')
    second = historical(app, customer, 'H2', payment='unpaid', total=6000)
    unknown = historical(app, customer, 'H3', payment='unknown', total=12100)
    before = app.reports()['receivables']
    assert ids(app.documents.list(sort_by='pending_cents')) == [second['id'], first['id'], unknown['id']]
    assert ids(app.documents.list(sort_by='pending_cents', sort_direction='desc')) == [first['id'], second['id'], unknown['id']]
    assert app.reports()['receivables'] == before


def test_balance_sort_leaves_drafts_and_void_displayed_as_absent_last_in_both_directions(app, customer):
    with app.db.transaction() as conn:
        for identifier, status, total in [('draft-low', 'draft', -999999), ('void-high', 'void', 999999),
                                          ('issued-zero', 'issued', 0), ('issued-positive', 'issued', 100)]:
            conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
                base_cents,tax_cents,total_cents,created_at,updated_at)
                VALUES(?,'invoice',?,?,'2020-01-01',?,'{}',?,0,?,'2026-01-01','2026-01-01')''',
                         (identifier, status, customer['id'], identifier, total, total))
    assert ids(app.documents.list(sort_by='pending_cents')) == [
        'issued-zero', 'issued-positive', 'draft-low', 'void-high']
    assert ids(app.documents.list(sort_by='pending_cents', sort_direction='desc')) == [
        'issued-positive', 'issued-zero', 'draft-low', 'void-high']
    # Ordering does not alter the original receipt metadata or invoice amounts.
    data = {row['id']: row for row in app.documents.list(sort_by='pending_cents')['items']}
    assert data['draft-low']['payment_known'] and data['draft-low']['total_cents'] == -999999
    assert data['void-high']['payment_known'] and data['void-high']['total_cents'] == 999999


@pytest.mark.parametrize('action,params', [('customers.list', {}), ('vehicles.page', {}), ('vehicles.list', {}),
    ('documents.list', {}), ('products.movements', {'product_id': 'missing'}), ('fiscal.list', {}), ('b2b.list', {})])
@pytest.mark.parametrize('sorting', [{'sort_by': 'name; DROP TABLE customers;--'}, {'sort_by': ['name']},
    {'sort_by': None}, {'sort_direction': 'DESC; DROP TABLE customers;--'}, {'sort_direction': True}])
def test_rpc_rejects_unknown_or_non_string_sorting_before_queries(app, action, params, sorting):
    with pytest.raises(AppError, match='ordenación'):
        app.dispatch(action, {**params, **sorting})
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM customers').fetchone()[0] == 0
