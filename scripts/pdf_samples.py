"""Generate reproducible synthetic PDF specimens without opening workshop data."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from PIL import Image, ImageDraw
from pypdf import PdfReader
from taller.app import App


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='reports/pdf-layout')
    output = ROOT / parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'data': 'Exclusivamente sintéticos', 'files': []}
    with tempfile.TemporaryDirectory(prefix='canamo-pdf-á ') as folder:
        app = App(Path(folder))
        app.settings.save('company', {'legal_name': 'TALLER FICTICIO DE VERIFICACIÓN', 'tax_id': '89890001K',
                                    'phone': '600 000 000', 'email': 'prueba@example.invalid'})
        fixture = Image.new('RGBA', (400, 240), (245, 205, 30, 255))
        ImageDraw.Draw(fixture).text((50, 100), 'EC - IMAGEN SINTETICA', fill='black', font_size=25)
        encoded = io.BytesIO()
        fixture.save(encoded, 'PNG')
        app.settings.logo(base64.b64encode(encoded.getvalue()).decode())
        customer = app.contacts.save_customer({'name': 'Cliente sintético de impresión, S. L.', 'tax_id': '12345678Z',
                    'legacy_code': '000017', 'address': 'Calle de Pruebas, 42', 'postal_code': '41300', 'city': 'La Rinconada'})
        vehicle = app.contacts.save_vehicle({'customer_id': customer['id'], 'plate': '1234ZXY', 'make': 'Marca sintética', 'model': 'Modelo de prueba'})
        short = app.documents.save({'customer_id': customer['id'], 'vehicle_id': vehicle['id'], 'kilometres': 145021,
            'lines': [{'description': 'Mano de obra: revisión y montaje', 'quantity': '1.5', 'unit_price': '34', 'tax_rate': '21'},
                      {'description': 'Recambio con precio fraccionado', 'quantity': '3', 'unit_price': '12.3456', 'discount': '5', 'tax_rate': '21'}]})
        issued = app.documents.publish(short['id'])
        long = app.documents.save({'customer_id': customer['id'], 'lines': [
            {'description': f'Concepto sintético {i + 1}: comprobación, limpieza y ajuste de elementos. ' + ('Texto largo para verificar el salto entre páginas. ' * (18 if i == 12 else 2)),
             'quantity': '2.125', 'unit_price': '12.3456', 'discount': '2.5', 'tax_rate': ['21', '10', '4'][i % 3]}
            for i in range(42)], 'notes': 'Notas sintéticas de impresión. ' * 32})
        multi = app.documents.publish(long['id'])
        correction = app.documents.rectify(issued['id'], 'Devolución sintética de prueba')
        corrected = app.documents.publish(correction['id'])
        for label, document in [('factura', issued), ('multipagina', multi), ('rectificativa', corrected)]:
            data = base64.b64decode(app.pdf(document['id'])['content'])
            path = output / (label + '.pdf')
            path.write_bytes(data)
            manifest['files'].append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(),
                                      'pages': len(PdfReader(io.BytesIO(data)).pages), 'bytes': len(data)})
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
