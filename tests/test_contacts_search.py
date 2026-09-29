"""Synthetic contact/search regressions over real temporary SQLite."""
import pytest

from taller.errors import AppError


@pytest.mark.parametrize('field,query,values', [
    ('legacy_code', '001', ['001', '0019', '90019']),
    ('tax_id', '12345678Z', ['12345678Z', '12345678Z9', '912345678Z']),
    ('phone', '600123456', ['600 123 456', '600 123 456 7', '960 012 345 6']),
    ('phone2', '600-123-456', ['600 123 456', '600 123 456 7', '960 012 345 6']),
    ('plate', '0540-bzd', ['0540BZD', '0540BZD1', 'X0540BZD']),
    ('name', 'Taller exacto', ['Taller exacto', 'Taller exacto taller', 'A taller exacto']),
])
def test_exact_match_then_prefix_precede_contains_in_each_search_field(app, field, query, values):
    expected = []
    for index, value in enumerate(values):
        data = {'name': ['Z coincidencia exacta', 'Y prefijo', 'A coincidencia parcial'][index]}
        if field != 'plate':
            data[field] = value
        customer = app.contacts.save_customer(data)
        if field == 'plate':
            app.contacts.save_vehicle({'customer_id': customer['id'], 'plate': value})
        expected.append(customer['id'])
    assert [row['customer_id'] for row in app.contacts.search(query)] == expected


def test_exact_legacy_code_beats_a_plate_prefix_and_keeps_leading_zeroes(app):
    partial = app.contacts.save_customer({'name': 'A matrícula parcial'})
    app.contacts.save_vehicle({'customer_id': partial['id'], 'plate': '0010ABC'})
    exact = app.contacts.save_customer({'name': 'Z código exacto', 'legacy_code': '001'})
    rows = app.contacts.search('001')
    assert [row['customer_id'] for row in rows] == [exact['id'], partial['id']]
    assert rows[0]['legacy_code'] == '001'


def test_search_phone_separators_and_nif_separators_are_normalized(app):
    customer = app.contacts.save_customer({'name': 'Teléfono sintético', 'phone': '+34 600 123 456', 'tax_id': '12345678Z'})
    for query in ('+34-600-123-456', '+34 600 123 456', '34600123456', '12345678-z'):
        assert [row['customer_id'] for row in app.contacts.search(query)] == [customer['id']]
    for query in ('%', '_', '- / +', '   '):
        assert app.contacts.search(query) == []


def test_foreign_contact_preserves_country_and_postal_format_but_cannot_issue(app):
    app.settings.save('company', {'legal_name': 'TALLER SINTÉTICO', 'tax_id': '89890001K'})
    customer = app.contacts.save_customer({
        'name': 'Contacto extranjero sintético', 'country': 'gb', 'postal_code': 'SW1A 1AA',
        'address': 'Dirección sintética 1', 'city': 'Localidad sintética', 'tax_id': '12345678Z',
    })
    assert customer['country'] == 'GB' and customer['postal_code'] == 'SW1A 1AA'
    assert customer['email'] == ''
    draft = app.documents.save({'customer_id': customer['id'], 'lines': [{'description': 'Trabajo sintético', 'unit_price': '1'}]})
    with pytest.raises(AppError, match='internacionales'):
        app.documents.publish(draft['id'])
    assert app.documents.get(draft['id'])['status'] == 'draft'
    assert app.documents.get(draft['id'])['full_number'] is None
    assert not app.fiscal.records()


def test_country_defaults_and_postal_validation_do_not_require_tax_id(app):
    domestic = app.contacts.save_customer({'name': 'Contacto español', 'postal_code': '04100'})
    assert domestic['country'] == 'ES' and domestic['postal_code'] == '04100'
    assert domestic['tax_id'] == ''
    foreign = app.contacts.save_customer({'name': 'Contacto portugués', 'country': 'PT', 'postal_code': '4700-235'})
    assert foreign['postal_code'] == '4700-235'
    with pytest.raises(AppError, match='5 cifras'):
        app.contacts.save_customer({'name': 'CP español inválido', 'postal_code': 'SW1A 1AA'})
    with pytest.raises(AppError, match='país'):
        app.contacts.save_customer({'name': 'País inválido', 'country': 'España'})
