from datetime import date, timedelta

import pytest

from taller.errors import AppError
from taller.validation import today


def test_new_documents_apply_billing_settings_and_explicit_overrides(app, customer):
    app.settings.save('billing', {'vat': '10', 'payment_method': 'transfer', 'due_days': 12, 'quote_days': 23, 'labor_rate': '37.1250'})
    data = {'customer_id': customer['id'], 'lines': [{'description': 'Trabajo sintético', 'quantity': '1', 'unit_price': '100'}]}
    invoice = app.documents.save(data)
    quote = app.documents.save({**data, 'kind': 'quote'})
    assert invoice['due_date'] == (date.fromisoformat(today()) + timedelta(days=12)).isoformat()
    assert quote['due_date'] == (date.fromisoformat(today()) + timedelta(days=23)).isoformat()
    assert invoice['payload']['payment_method'] == 'transfer'
    assert invoice['total_cents'] == 11000
    assert app.settings.get()['billing']['labor_rate'] == '37.1250'
    explicit = app.documents.save({**data, 'due_date': '', 'payment_method': 'card',
                                    'lines': [{**data['lines'][0], 'tax_rate': '21'}]})
    assert explicit['due_date'] == '' and explicit['payload']['payment_method'] == 'card'
    assert explicit['total_cents'] == 12100


def test_configuration_change_does_not_rewrite_a_saved_document(app, draft):
    before = app.documents.get(draft['id'])
    app.settings.save('billing', {'due_days': 15, 'vat': '10', 'payment_method': 'card', 'footer': 'Nuevo pie'})
    after = app.documents.get(draft['id'])
    assert after == before


def test_continuous_series_keeps_number_across_years(app, customer):
    identifier = app.settings.save_series({'kind': 'invoice', 'label': 'Continua sintética', 'prefix': 'CONT-',
                                         'year': 0, 'padding': 4, 'next_number': 90})['id']
    data = {'customer_id': customer['id'], 'series_id': identifier,
            'lines': [{'description': 'Prueba de continuidad', 'quantity': '1', 'unit_price': '20'}]}
    first = app.documents.publish(app.documents.save({**data, 'issue_date': '2024-12-31'})['id'])
    second = app.documents.publish(app.documents.save({**data, 'issue_date': '2025-01-02'})['id'])
    assert (first['full_number'], second['full_number']) == ('CONT-0090', 'CONT-0091')
    series = next(row for row in app.settings.list_series() if row['id'] == identifier)
    with pytest.raises(AppError, match='utilizada'):
        app.settings.save_series({**series, 'next_number': 1})
    with pytest.raises(AppError, match='variable'):
        app.settings.save_series({'kind': 'invoice', 'label': 'Inválida', 'prefix': '{YYYY}-', 'year': 0, 'padding': 4, 'next_number': 1})


def test_unused_series_kind_edit_is_persisted_and_ambiguous_choice_requires_selection(app, customer):
    series = next(row for row in app.settings.list_series() if row['kind'] == 'quote')
    app.settings.save_series({**series, 'kind': 'invoice'})
    assert next(row for row in app.settings.list_series() if row['id'] == series['id'])['kind'] == 'invoice'
    draft = app.documents.save({'customer_id': customer['id'], 'lines': [{'description': 'Serie explícita', 'unit_price': '1'}]})
    with pytest.raises(AppError, match='varias series'):
        app.documents.publish(draft['id'])
    assert app.documents.get(draft['id'])['status'] == 'draft'
