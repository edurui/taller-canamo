"""Selectable A4 documents from stored snapshots, with flowing tables and totals."""
from __future__ import annotations

import io
import hashlib
import json
import re
from decimal import Decimal
from functools import lru_cache
from html import escape
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .errors import AppError, require

WIDTH, HEIGHT = A4
MARGIN = 36
CONTENT_WIDTH = WIDTH - 2 * MARGIN
INK = colors.HexColor('#1B1E24')
MUTED = colors.HexColor('#555C64')
YELLOW = colors.HexColor('#F4C91C')
FONT = 'CanamoDejaVu'
BOLD_FONT = 'CanamoDejaVu-Bold'


@lru_cache(maxsize=1)
def _font_characters():
    """Load the same embedded fonts on every OS; never depend on system fonts."""
    folder = Path(__file__).with_name('fonts')
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        characters = None
        for name, filename in ((FONT, 'DejaVuSans.ttf'), (BOLD_FONT, 'DejaVuSans-Bold.ttf')):
            path = folder / filename
            require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files_sha256'][filename],
                    'Las fuentes del PDF están dañadas. Reinstala la aplicación conservando los datos.', 'pdf_font')
            font = TTFont(name, str(path))
            pdfmetrics.registerFont(font)
            available = set(font.face.charToGlyph)
            characters = available if characters is None else characters & available
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD_FONT, italic=FONT, boldItalic=BOLD_FONT)
        return frozenset(characters or ())
    except (OSError, ValueError, KeyError) as error:
        raise AppError('No se pueden cargar las fuentes del PDF. Reinstala la aplicación conservando los datos.', 'pdf_font') from error


def validate_printable_text(document):
    """Prevent silent glyph substitution, including before assigning an invoice number."""
    available = _font_characters()

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from strings(child)

    missing = sorted({character for value in strings(document) for character in value
                      if character not in '\n\r\t' and ord(character) not in available})
    require(not missing,
            'Las fuentes del PDF no representan estos caracteres: ' +
            ', '.join(f'{char} (U+{ord(char):04X})' for char in missing[:8]) +
            '. El texto original se conserva. Consulta al soporte antes de emitir.', 'pdf_character')


def euros(cents):
    if cents is None:
        return 'No consta'
    value = f'{Decimal(cents) / 100:,.2f}'
    return value.replace(',', 'X').replace('.', ',').replace('X', '.') + ' EUR'


def date_label(value):
    return '/'.join(reversed(value.split('-'))) if value else 'No consta'


def unit_price_label(value):
    if value is None or value == '':
        return 'No consta'
    number = Decimal(str(value))
    require(number.is_finite(), 'Precio histórico no válido para imprimir.', 'pdf_number')
    places = max(2, -number.as_tuple().exponent)
    if places > 16 or number.adjusted() > 16:
        # Keep the exact stored decimal while avoiding exponent-driven expansion.
        return str(number).replace('.', ',') + ' EUR'
    return f'{number:,.{places}f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' EUR'


def render_document(document, settings, root: Path):
    validate_printable_text(document)
    payload = document['payload']
    # An empty historical snapshot means unknown, never today's company/logo.
    historical = bool(payload.get('historical') or document['status'] == 'historical')
    issued = document['status'] != 'draft'
    issuer = payload.get('issuer', {} if issued else settings['company']) or {}
    customer = payload.get('customer') or {}
    vehicle = payload.get('vehicle') or {}
    branding = payload.get('branding', {} if issued else settings['billing']) or {}
    validate_printable_text(issuer)
    is_test = not historical and payload.get('test_document', True)
    fiscal = payload.get('fiscal') if not historical else None
    output = io.BytesIO()
    title = {
        'invoice': 'FACTURA RECTIFICATIVA' if payload.get('invoice_type', 'F1').startswith('R') else 'FACTURA',
        'quote': 'PRESUPUESTO', 'order': 'ORDEN DE REPARACIÓN',
    }[document['kind']]
    number = document.get('full_number') or 'BORRADOR'
    body = ParagraphStyle('Body', fontName=FONT, fontSize=9, leading=13, textColor=INK)
    small = ParagraphStyle('Small', parent=body, fontSize=8, leading=11)
    right = ParagraphStyle('Right', parent=body, alignment=2)
    heading = ParagraphStyle('Heading', parent=body, fontName=BOLD_FONT, fontSize=13, leading=17)
    brand_style = ParagraphStyle('Brand', parent=heading, fontSize=14, leading=18)

    def paragraph(value, style=body):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)

    logo_id = branding.get('logo_id', '')
    logo = root / 'assets' / logo_id if re.fullmatch(r'[a-f0-9]{64}\.png', logo_id or '') else None
    qr_side = 35 * mm
    issuer_width = CONTENT_WIDTH - 80 - (qr_side + 12 if fiscal else 0)
    issuer_parts = [
        paragraph(issuer.get('trading_name') or issuer.get('legal_name') or 'Emisor no documentado', brand_style),
        paragraph('  ·  '.join(filter(None, [issuer.get('legal_name'), 'NIF: ' + issuer['tax_id'] if issuer.get('tax_id') else None])), small),
        paragraph(', '.join(filter(None, [issuer.get(k) for k in ('address', 'postal_code', 'city', 'province')])), small),
        paragraph('  ·  '.join(filter(None, [issuer.get('phone'), issuer.get('email')])), small),
    ]
    heights = [part.wrap(issuer_width, HEIGHT)[1] for part in issuer_parts]
    identity_height = max(52, sum(heights) + 9, qr_side + 14 if fiscal else 0)
    title_row = Table([[paragraph(title, heading), paragraph(number, right)]],
                      colWidths=[CONTENT_WIDTH * .57, CONTENT_WIDTH * .43])
    title_row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    title_height = title_row.wrap(CONTENT_WIDTH, HEIGHT)[1]
    legend = ('COPIA DE HISTÓRICO IMPORTADO · CONSERVE EL ORIGINAL' if historical else
              'DOCUMENTO DE PRUEBA - SIN VALIDEZ FISCAL' if is_test else '')
    if document['status'] == 'void':
        legend += ' · ANULADA'
    warning = paragraph(legend, small)
    warning_height = warning.wrap(CONTENT_WIDTH, HEIGHT)[1]
    header_bottom = HEIGHT - 30 - identity_height - 18 - title_height - warning_height - 12

    def draw_header(canvas, doc):
        canvas.saveState()
        if logo and logo.is_file():
            canvas.drawImage(ImageReader(str(logo)), MARGIN, HEIGHT - 82, width=64, height=52,
                             preserveAspectRatio=True, anchor='c', mask='auto')
        elif not historical:
            canvas.setFillColor(YELLOW)
            canvas.roundRect(MARGIN, HEIGHT - 80, 64, 48, 8, fill=1, stroke=0)
            canvas.setFillColor(INK)
            canvas.setFont(BOLD_FONT, 22)
            canvas.drawString(MARGIN + 15, HEIGHT - 64, 'EC')
        y = HEIGHT - 30
        for part, height in zip(issuer_parts, heights):
            y -= height
            part.drawOn(canvas, MARGIN + 80, y)
            y -= 3
        if fiscal:
            qr = QrCodeWidget(fiscal['qr_url'], barLevel='M')
            bounds = qr.getBounds()
            w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
            drawing = Drawing(qr_side, qr_side, transform=[qr_side / w, 0, 0, qr_side / h, 0, 0])
            drawing.add(qr)
            renderPDF.draw(drawing, canvas, WIDTH - MARGIN - qr_side, HEIGHT - 30 - qr_side)
            canvas.setFont(FONT, 6)
            canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 42 - qr_side,
                                  'QR tributario - PRUEBAS' if is_test else 'VERI*FACTU')
        y = HEIGHT - 30 - identity_height - 10
        canvas.setStrokeColor(YELLOW)
        canvas.setLineWidth(2)
        canvas.line(MARGIN, y, WIDTH - MARGIN, y)
        y -= title_height + 8
        title_row.drawOn(canvas, MARGIN, y)
        warning.drawOn(canvas, MARGIN, y - warning_height - 4)
        if logo and logo.is_file():
            canvas.setFillAlpha(float(branding.get('watermark_opacity', .06)))
            canvas.drawImage(ImageReader(str(logo)), 85, 220, width=425, height=300,
                             preserveAspectRatio=True, anchor='c', mask='auto')
        canvas.restoreState()

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.states = []

        def showPage(self):
            self.states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self.states)
            for state in self.states:
                self.__dict__.update(state)
                self.saveState()
                self.setFillColor(MUTED)
                self.setFont(FONT, 8)
                self.drawString(MARGIN, 24, str(number))
                self.drawRightString(WIDTH - MARGIN, 24, f'Página {self._pageNumber} de {total}')
                self.restoreState()
                super().showPage()
            super().save()

    pdf = SimpleDocTemplate(output, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                           topMargin=HEIGHT - header_bottom, bottomMargin=45,
                           title=title + ' ' + str(number), author=issuer.get('trading_name', ''))
    metadata = ['Fecha: ' + date_label(document['issue_date']),
                'Cliente: ' + str(customer.get('legacy_code') or customer.get('id', '')[:8] or 'No documentado')]
    if vehicle:
        metadata += ['Matrícula: ' + str(vehicle.get('plate') or 'No documentada'),
                     'Kilómetros: ' + str(payload.get('kilometres') if payload.get('kilometres') is not None else 'No consta')]
    if payload.get('reference'):
        reference = payload['reference']
        metadata += ['Rectifica: ' + str(reference.get('full_number', '')),
                     'Fecha original: ' + date_label(reference.get('issue_date'))]
    customer_text = '\n'.join(filter(None, [
        customer.get('name') or 'Receptor no documentado', customer.get('tax_id'), customer.get('address'),
        ' '.join(filter(None, [customer.get('postal_code'), customer.get('city')])), customer.get('province')]))
    meta_table = Table([[paragraph('\n'.join(metadata)), paragraph(customer_text)]],
                       colWidths=[CONTENT_WIDTH * .46, CONTENT_WIDTH * .54], splitInRow=1)
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    rows = [[paragraph(label, small) for label in ('Cantidad', 'Concepto', 'Precio', 'Dto.', 'Base')]]
    for line in payload['lines']:
        rows.append([
            paragraph('No consta' if line.get('quantity') in (None, '') else str(line['quantity']).replace('.', ','), right),
            paragraph((line.get('description') or 'No consta') + ('\nImporte original sin clasificación fiscal: ' + str(line['amount_raw']).replace('.', ',') if line.get('amount_raw') is not None else '')),
            paragraph(unit_price_label(line.get('unit_price')), right),
            paragraph('No consta' if line.get('discount') in (None, '') else str(line['discount']).replace('.', ',') + ' %', right), paragraph(euros(line.get('base_cents')), right)])
    table = Table(rows, colWidths=[49, CONTENT_WIDTH - 49 - 78 - 40 - 87, 78, 40, 87],
                  repeatRows=1, splitInRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F2')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, INK), ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#E5E5E5')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    tax_rows = [[paragraph('Base imponible'), paragraph(euros(document['base_cents']), right)]]
    for tax in payload['taxes']:
        label = ('IVA histórico (tipo no conservado)' if tax['kind'] == 'historical'
                 else 'IVA ' + str(tax['rate']) + ' %' if tax['kind'] == 'S1' else 'Exenta ' + tax['kind'])
        label += '\nBase: ' + euros(tax['base_cents'])
        tax_rows.append([paragraph(label), paragraph(euros(tax['tax_cents']), right)])
    if not payload['taxes']:
        tax_rows.append([paragraph('IVA (desglose no conservado)'), paragraph(euros(document['tax_cents']), right)])
    tax_rows.append([paragraph('TOTAL', heading), paragraph(euros(document['total_cents']), right)])
    totals = Table(tax_rows, colWidths=[160, 122], hAlign='RIGHT')
    totals.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, -1), (-1, -1), YELLOW), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story = [meta_table, Spacer(1, 8)]
    if historical and (not document['issue_date'] or any(document.get(key) is None for key in ('base_cents','tax_cents','total_cents'))):
        story += [paragraph('Histórico incompleto. Los datos ausentes figuran como «No consta». Los importes originales sin clasificación fiscal no acreditan la base, el IVA ni el total de la factura.', small), Spacer(1, 8)]
    if not payload['lines']:
        story += [paragraph('No constan líneas en el archivo histórico.', small), Spacer(1, 6)]
    if payload.get('operation_date'):
        story += [paragraph('Fecha de operación: ' + date_label(payload['operation_date']), small), Spacer(1, 6)]
    if payload.get('correction_mode') == 'tax_only':
        story += [paragraph('Rectificación exclusiva de cuota de IVA. No modifica la base imponible.', small), Spacer(1, 6)]
    story += [table, Spacer(1, 14), KeepTogether([totals])]
    for tax in payload['taxes']:
        reasons = [tax['reason']] if tax.get('reason') else sorted({
            line['tax_reason'] for line in payload['lines']
            if line.get('tax_kind') == tax['kind'] and str(line.get('tax_rate')) == str(tax['rate']) and line.get('tax_reason')})
        if reasons:
            label = 'Datos históricos: ' if tax['kind'] == 'historical' else 'Exención ' + tax['kind'] + ': '
            story += [Spacer(1, 6), paragraph(label + '; '.join(reasons), small)]
    if payload.get('notes'):
        story += [Spacer(1, 12), paragraph('Observaciones: ' + payload['notes'], small)]
    if document.get('due_date'):
        story += [Spacer(1, 8), paragraph(
            ('Válido hasta: ' if document['kind'] == 'quote' else 'Vencimiento: ') + date_label(document['due_date']), small)]
    method = {'cash': 'Efectivo', 'card': 'Tarjeta', 'transfer': 'Transferencia',
              'bizum': 'Bizum', 'other': 'Otro'}.get(payload.get('payment_method'))
    if method:
        story += [Spacer(1, 8), paragraph('Forma de pago: ' + method, small)]
    if branding.get('show_bank') and issuer.get('iban'):
        story += [paragraph('IBAN: ' + issuer['iban'], small)]
    if payload.get('footer'):
        story += [Spacer(1, 10), paragraph(payload['footer'], small)]
    pdf.build(story, onFirstPage=draw_header, onLaterPages=draw_header, canvasmaker=NumberedCanvas)
    return output.getvalue()
