import base64
import io

from pypdf import PdfReader

from taller.pdf import render_document


def _read(content):
    return PdfReader(io.BytesIO(content))


def _text_positions(reader):
    points = []
    for index, page in enumerate(reader.pages):
        def visit(text, cm, tm, font, size):
            if text.strip():
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                points.append((index, text.strip(), x, y))
        page.extract_text(visitor_text=visit)
    return points


def test_pdf_many_tax_groups_fit_inside_printable_page(app, draft):
    document = app.documents.get(draft['id'])
    # Stress rendering independently of the issuer's supported fiscal operations.
    document['payload']['taxes'] = [
        {'kind': 'S1', 'rate': str(rate), 'tax_cents': 123, 'base_cents': 1000}
        for rate in range(10)
    ]
    reader = _read(render_document(document, app.settings.get(), app.db.root))
    positions = _text_positions(reader)
    assert any('TOTAL' in text for _, text, _, _ in positions)
    assert all(18 <= y <= 824 for _, _, _, y in positions), positions
    assert len([text for _, text, _, _ in positions if text.startswith('IVA ')]) == 10


def test_pdf_splits_very_long_concept_and_preserves_last_words(app, draft):
    document = app.documents.get(draft['id'])
    document['payload']['lines'][0]['description'] = ('Descripción de un piñón, revisión y reparación. ' * 90) + 'FIN DEL CONCEPTO'
    document['payload']['footer'] = ('Pie del documento largo. ' * 32) + 'FIN DEL PIE'
    reader = _read(render_document(document, app.settings.get(), app.db.root))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    normalized_text = ' '.join(text.split())
    assert len(reader.pages) >= 2
    assert 'FIN DEL CONCEPTO' in normalized_text
    assert 'FIN DEL PIE' in normalized_text
    assert text.count('Descripción') == 90
    assert 'piñón' in text
    assert all(18 <= y <= 824 for _, _, _, y in _text_positions(reader))
    assert text.count('Cantidad') >= 2


def test_historical_pdf_never_invents_issuer_or_brand_from_current_settings(app, draft):
    document = app.documents.get(draft['id'])
    document['status'] = 'historical'
    document['payload'].update({'historical': True, 'issuer': {}, 'branding': {}, 'customer': {'name': 'Receptor documentado'}})
    settings = app.settings.get()
    settings['company']['trading_name'] = 'NOMBRE ACTUAL QUE NO ESTABA DOCUMENTADO'
    text = '\n'.join(page.extract_text() for page in _read(render_document(document, settings, app.db.root)).pages)
    assert 'NOMBRE ACTUAL QUE NO ESTABA DOCUMENTADO' not in text
    assert 'HISTÓRICO' in text
    assert 'DOCUMENTO DE PRUEBA' not in text


def test_pdf_snapshot_is_byte_stable_after_customer_and_company_changes(app, draft):
    document = app.documents.publish(draft['id'])
    first = app.pdf(document['id'])['content']
    customer = app.contacts.customer(document['customer_id'])
    app.contacts.save_customer({**customer, 'name': 'Otro nombre actual', 'phone': '612999999'})
    app.settings.save('company', {'trading_name': 'Otra marca actual'})
    assert app.pdf(document['id'])['content'] == first


def test_pdf_failure_preserves_previous_cached_document(app, draft, monkeypatch):
    document = app.documents.publish(draft['id'])
    first = base64.b64decode(app.pdf(document['id'])['content'])
    # Cached issued invoices can still be read if the renderer is unavailable.
    def broken(*args, **kwargs):
        raise OSError('Fallo inyectado del renderizador')
    monkeypatch.setattr('taller.pdf.render_document', broken)
    assert base64.b64decode(app.pdf(document['id'])['content']) == first


def test_atomic_replacement_failure_keeps_existing_file(tmp_path, monkeypatch):
    from taller.files import atomic_write
    path = tmp_path / 'documento.pdf'
    path.write_bytes(b'original completo')
    def unavailable(*args):
        raise OSError('Destino bloqueado: fallo inyectado')
    monkeypatch.setattr('taller.files.os.replace', unavailable)
    import pytest
    with pytest.raises(OSError, match='Destino bloqueado'):
        atomic_write(path, b'nuevo documento')
    assert path.read_bytes() == b'original completo'
    assert list(tmp_path.iterdir()) == [path]


def test_rectification_prints_original_number_and_date(app, draft):
    original = app.documents.publish(draft['id'])
    corrective = app.documents.rectify(original['id'], 'Corrección parcial sintética')
    published = app.documents.publish(corrective['id'])
    text = '\n'.join(page.extract_text() for page in _read(base64.b64decode(app.pdf(published['id'])['content'])).pages)
    assert 'FACTURA RECTIFICATIVA' in text
    assert 'Rectifica: ' + original['full_number'] in text
    assert 'Fecha original:' in text


def test_pdf_preserves_unit_price_precision_and_per_rate_bases(app, customer):
    draft = app.documents.save({'customer_id': customer['id'], 'lines': [
        {'description': 'Precio fraccionado', 'quantity': '2.125', 'unit_price': '12.3456', 'tax_rate': '21'},
        {'description': 'Concepto exento documentado', 'quantity': '1', 'unit_price': '10',
         'tax_rate': '0', 'tax_kind': 'E1', 'tax_reason': 'Motivo legal sintético para prueba de impresión'},
    ]})
    text = '\n'.join(page.extract_text() for page in _read(base64.b64decode(app.pdf(draft['id'])['content'])).pages)
    assert '12,3456 EUR' in text
    assert '2,125' in text
    assert 'Base: 26,23 EUR' in text
    assert 'Base: 10,00 EUR' in text
    assert 'Motivo legal sintético' in text


def test_historical_pdf_labels_missing_values_without_inventing_vat_or_quantity(app, draft):
    document = {**draft, 'status': 'historical', 'full_number': 'HIST-001'}
    document['payload'].update({'historical': True, 'issuer': {}, 'branding': {}, 'customer': {}})
    document['payload']['lines'][0].update(quantity=None, unit_price=None, tax_rate='', tax_kind='historical')
    document['payload']['taxes'] = [{'kind': 'historical', 'rate': '', 'base_cents': draft['base_cents'], 'tax_cents': draft['tax_cents'], 'reason': 'Desglose histórico no conservado'}]
    text = '\n'.join(page.extract_text() for page in _read(render_document(document, app.settings.get(), app.db.root)).pages)
    assert ' '.join(text.split()).count('No consta') >= 2 and 'IVA histórico' in text
    assert 'Exenta historical' not in text and 'Exención historical' not in text
    assert 'Datos históricos: Desglose histórico no conservado' in text


def test_tax_only_pdf_identifies_legal_amounts_and_original_operation_date(app, customer):
    original = app.documents.publish(app.documents.save({'customer_id': customer['id'], 'operation_date': '2025-01-17',
        'lines': [{'description': 'Trabajo sintético', 'quantity': '1', 'unit_price': '100', 'tax_rate': '21'}]})['id'])
    correction = app.documents.rectify(original['id'], 'Incobro sintético documentado', 'R3', tax_adjustments=[{'tax_rate': '21', 'tax_cents': -2100}])
    issued = app.documents.publish(correction['id'])
    text = ' '.join(page.extract_text() for page in _read(base64.b64decode(app.pdf(issued['id'])['content'])).pages)
    text = ' '.join(text.split())
    assert 'Fecha de operación: 17/01/2025' in text
    assert 'Rectificación exclusiva de cuota de IVA. No modifica la base imponible.' in text
    assert 'Base: 0,00 EUR' in text and '-21,00 EUR' in text


def test_pdf_embeds_fonts_and_preserves_customer_and_concept_unicode(app, customer):
    name = 'Łukasz Петров sintético'
    description = 'Revisión Łódź y Δ presión'
    app.contacts.save_customer({**customer, 'name': name})
    document = app.documents.publish(app.documents.save({'customer_id': customer['id'],
        'lines': [{'description': description, 'quantity': '1', 'unit_price': '100', 'tax_rate': '21'}]})['id'])
    reader = _read(base64.b64decode(app.pdf(document['id'])['content']))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert name in text
    assert description in text
    fonts = [font.get_object() for page in reader.pages for font in page['/Resources']['/Font'].values()]
    embedded = [font for font in fonts if 'DejaVuSans' in str(font.get('/BaseFont'))]
    assert len(embedded) >= 2
    assert all(font['/FontDescriptor']['/FontFile2'].get_data() for font in embedded)


def test_unprintable_character_keeps_draft_and_number_without_substitution(app, customer):
    from taller.errors import AppError
    import pytest
    draft = app.documents.save({'customer_id': customer['id'],
        'lines': [{'description': 'Carácter sin glifo: \U00020000', 'quantity': '1', 'unit_price': '10', 'tax_rate': '21'}]})
    with app.db.read() as conn:
        numbers = [tuple(row) for row in conn.execute('SELECT id,next_number FROM series ORDER BY id')]
    with pytest.raises(AppError, match=r'U\+20000') as failure:
        app.documents.publish(draft['id'])
    assert failure.value.code == 'pdf_character'
    kept = app.documents.get(draft['id'])
    assert kept['status'] == 'draft' and kept['full_number'] is None
    assert '\U00020000' in kept['payload']['lines'][0]['description']
    with app.db.read() as conn:
        assert numbers == [tuple(row) for row in conn.execute('SELECT id,next_number FROM series ORDER BY id')]
        assert conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0
